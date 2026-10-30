'''
Purpose
-------
Plan or link historical products into managed physical-height hierarchies using recorded
provenance.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for migrate_geometry_outputs.py.

Notes
-----
Non-destructive migration using recorded source/height/filter provenance.

Legacy bytes remain in place. Canonical and separation views use relative links.
Incomplete identities are reported; historical settings are never called optimized.
Run without --apply for a plan. Repeat --apply is idempotent.
'''
# Import the libraries and shared helpers used by this module
from pathlib import Path
from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar
import argparse
import json
import re

import output_paths as paths
from figure_locations import legacy_figure_root, legacy_figure_identity_path

SUFFIXES = {'_phase_diff':'phase_difference','_coherence':'coherence_diagram',
            '_komega':'komega_diagram','_xc':'time_distance'}
SIMULATION = re.compile(r'^(hx|vx|z0)_(\d+(?:_\d+)?)g_(v[123]|bb[123]|rho|temp|pressure)_(\d+(?:_\d+)?)km_(\d+(?:_\d+)?)km')


def base_name(path):
    '''
    Purpose
    -------
    Separate a recognized diagnostic suffix from a historical FITS stem.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    stem, product: tuple
        Base stem and registered product kind, or (None, None) for an unrecognized
        suffix.
    '''

    # Separate a recognized diagnostic suffix from a historical FITS stem
    stem = Path(path).stem
    for suffix in sorted(SUFFIXES, key=len, reverse=True):
        if stem.endswith(suffix): return stem[:-len(suffix)], SUFFIXES[suffix]
    return None, None


def filtering_file(path):
    '''
    Purpose
    -------
    Find the nearest ancestor's historical filter_parameters.txt file.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    file: pathlib.Path or None
        First existing ancestor parameter file, or None when absent.
    '''

    # Find the nearest ancestor's historical filter_parameters.txt file
    for parent in Path(path).parents:
        file = parent/'filter_parameters.txt'
        if file.is_file(): return file
    return None


def parse_filter_file(path):
    '''
    Purpose
    -------
    Decode dotted historical filter settings into a nested dictionary.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    filtering: dict
        Parsed scalar/list settings; missing enabled or filter_sequence fields raise
        ValueError.
    '''

    # Decode dotted historical filter settings into a nested dictionary
    result = {}
    for line in Path(path).read_text().splitlines():
        key, sep, raw = line.partition(':')
        if not sep or not key.startswith('filtering.'): continue
        raw = raw.strip()
        if raw in ('true','false'): value = raw=='true'
        elif raw.startswith('['): value = [v.strip() for v in raw[1:-1].split(',') if v.strip()]
        elif raw=='null': value = None
        else:
            try: value = float(raw)
            except ValueError: value = raw
        target = result
        parts = key.split('.')[1:]
        for part in parts[:-1]: target = target.setdefault(part,{})
        target[parts[-1]] = value
    if 'enabled' not in result or 'filter_sequence' not in result: raise ValueError('Incomplete legacy filter record.')
    return result


def record_key(path, filtering=None):
    '''
    Purpose
    -------
    Construct the historical product/filter identity used for provenance matching.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    filtering: dict or None
        Explicit recorded filtering settings; otherwise read the nearest parameter file
        when present.

    Outputs
    -------
    stem, filtering_json: tuple
        Cleaned source stem and canonical recorded filter JSON, or None for unavailable
        filtering metadata.
    '''

    # Construct the historical product/filter identity used for provenance matching
    stem, _ = base_name(path)
    if stem is None:
        stem=Path(path).stem
        for tail in ('_komega_magnetic_orientation_validation','_composite','_gaussian_filter'):
            if stem.endswith(tail): stem=stem[:-len(tail)];break
        match=SIMULATION.match(stem)
        if match: stem=match[0]
    clean = Path(paths.clean_output_filename(stem+'.fits')).stem
    if filtering is None:
        file = filtering_file(path)
        if file: filtering = parse_filter_file(file)
    return clean, paths.canonical_json(filtering) if filtering is not None else None


def reference_catalog(data_root):
    '''
    Purpose
    -------
    Index existing FITS products that have readable explicit input sidecars.

    Inputs
    ------
    data_root: str or pathlib.Path
        Historical numerical-product tree scanned for .inputs.json sidecars.

    Outputs
    -------
    catalog: defaultdict of list
        Product/filter keys mapped to (product path, recorded input reference)
        candidates.
    '''

    # Index existing FITS products that have readable explicit input sidecars
    catalog = defaultdict(list)
    for sidecar in sorted(Path(data_root).rglob('*.inputs.json')):
        if sidecar.is_symlink(): continue
        product = product_from_json_sidecar(sidecar, '.fits')
        if not product.is_file(): continue
        try:
            reference = json.loads(sidecar.read_text())
            key = record_key(product, reference['filtering'])
            if key: catalog[key].append((product,reference))
        except (ValueError, KeyError): continue
    return catalog


def source_reference(path, catalog):
    '''
    Purpose
    -------
    Resolve one unambiguous original-input reference for a historical artifact.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    catalog: mapping
        Candidate product/reference lists keyed by cleaned historical identity.

    Outputs
    -------
    reference, source: tuple
        Recorded input dictionary and numerical FITS source; absent or conflicting
        provenance raises ValueError.
    '''

    # Resolve one unambiguous original-input reference for a historical artifact
    direct = find_json_sidecar(path, '.inputs.json')
    if direct.is_file(): return json.loads(direct.read_text()), product_from_json_sidecar(direct, '.fits')
    stem, product = base_name(path)
    candidates = catalog.get(record_key(path), [])
    # Historical filenames that explicitly encode the complete recorded filter
    # can be matched against provenance; do not invent missing filter settings.
    if not candidates:
        clean = record_key(path)[0]
        for (key, _), entries in catalog.items():
            if key != clean: continue
            for source, reference in entries:
                filtering = reference['filtering']
                active = filtering.get('enabled',False)
                from pipeline import build_processing_slug
                token = build_processing_slug({'filtering':filtering})
                name = Path(path).stem
                if (not active and 'unfiltered' in name) or (active and token in name):
                    candidates.append((source,reference))
    unique = {paths.canonical_json(ref): (source,ref) for source,ref in candidates}
    if len(unique)!=1: raise ValueError(f'Original dataset/ordered heights/filter identity not unique ({len(unique)} candidates).')
    source, reference = next(iter(unique.values()))
    return deepcopy(reference),source


@lru_cache(maxsize=2048)
def source_header(source):
    '''
    Purpose
    -------
    Read and cache the primary FITS header for a source product.

    Inputs
    ------
    source: str or pathlib.Path
        Numerical FITS product whose header is read.

    Outputs
    -------
    header: astropy.io.fits.Header
        Cached source header; FITS read errors propagate.
    '''

    # Read and cache the primary FITS header for a source product
    from astropy.io import fits
    return fits.getheader(source)


def migration_config(reference, source, legacy_file):
    '''
    Purpose
    -------
    Reconstruct only recorded processing settings and mark missing legacy implementation
    provenance.

    Inputs
    ------
    reference: dict
        Saved original-input, sampling, and filtering metadata.
    source: pathlib.Path
        Numerical product supplying provenance and historical geometry naming.
    legacy_file: pathlib.Path
        Retained artifact argument; currently unused by configuration reconstruction.

    Outputs
    -------
    config: dict
        Noncreating runtime output context with explicitly incomplete legacy
        implementation identity. Missing physical simulation heights raise ValueError.
    '''

    # Reconstruct only recorded processing settings and mark missing legacy
    # implementation provenance
    data = deepcopy(reference['data'])
    sampling = reference['sampling']
    config = dict(data=data, filtering=deepcopy(reference['filtering']),
        time_distance=dict(sampling,xcorr_geometry='annulus'),
        magnetogram_mode=deepcopy(reference.get('magnetogram_mode', {})),
        filter_configuration={'mode':'historical', 'provenance':str(source.with_suffix('.inputs.json'))},
        paths={'data_output_dir':str(DATA_ROOT),'figure_dir':str(FIGURE_ROOT)})
    # The legacy naming function encoded every non-annulus geometry in the
    # filename. No FITS read/download is needed to recover that convention.
    from migrate_output_hierarchy import infer_geometry_from_name
    config['time_distance']['xcorr_geometry'] = infer_geometry_from_name(source.name)
    if data['source_type']=='single_cube':
        if 'resolved_h1_km' not in data or 'resolved_h2_km' not in data:
            raise ValueError('Absolute simulation heights not recorded.')
        data['resolved_delta_z_km']=abs(data['resolved_h2_km']-data['resolved_h1_km'])
    context=paths.build_runtime_output_paths(config,DATA_ROOT,FIGURE_ROOT,create=False)
    # The legacy writer omitted annulus width/max radius, array precision and
    # implementation version. Keep provenance truthful and never silently reuse
    # the historical file as a fully specified modern run.
    context['identity']['implementation']={'status':'legacy implementation not fully recorded'}
    context['identity']['legacy_provenance']={'reference':reference,'source':str(source),
        'processing_parameters_status':'only recorded parameters; remaining values unknown'}
    context['run_id']=paths.digest(context['identity'])
    return config


def migration_product(path):
    '''
    Purpose
    -------
    Infer a supported single-pair product from a historical artifact name.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    product: str or None
        Registered product kind; retired orientation-validation and unrecognized
        products return None.
    '''

    # Infer a supported single-pair product from a historical artifact name
    stem,product=base_name(path)
    if product:return product
    name=path.stem
    if '_magnetic_orientation_validation' in name:return None
    if name.endswith('_composite'):return 'composite_diagnostics'
    if 'gaussian_filter' in name:return 'gaussian_filter'
    if re.search(r'_dopplergram(?:_t\d+)?$',name):return 'filtered_dopplergram'
    if 'spatial' in name:return 'spatial_phase'
    return None


def migrate(legacy_data, figures, data_root, *, figure_root=None, apply=False):
    '''
    Purpose
    -------
    Plan or create verified relative links from legacy products into managed output
    trees.

    Inputs
    ------
    legacy_data: str or pathlib.Path
        Historical numerical FITS tree carrying recorded input sidecars.
    figures: str or pathlib.Path
        Distinct legacy figure archive scanned for single-pair image products.
    data_root: str or pathlib.Path
        Destination numerical-product root.
    figure_root: str or pathlib.Path or None
        Destination managed figure root, defaulting to figures.
    apply: bool
        Create links/metadata and verify linked artifacts when True; otherwise build a
        plan.

    Outputs
    -------
    report: dict
        Planned/linked/skipped/flagged records and counts. With apply=True, writes
        links, metadata, and a migration manifest; original product bytes remain in
        place.
    '''

    # Plan or create verified relative links from legacy products into managed output
    # trees
    global DATA_ROOT,FIGURE_ROOT
    DATA_ROOT=Path(data_root).resolve()
    FIGURE_ROOT=Path(figure_root or figures).resolve()
    if Path(figures).resolve()==FIGURE_ROOT and (FIGURE_ROOT/'simulations').is_dir():
        raise ValueError('Legacy figure input resolves to the active managed Figures tree; use the recorded legacy archive.')
    catalog=reference_catalog(legacy_data)
    records=[]
    candidates=[p for p in Path(legacy_data).rglob('*.fits') if not p.is_symlink()]
    candidates += [p for p in Path(figures).rglob('*') if p.suffix.lower() in {'.jpeg','.png','.pdf'} and not p.is_symlink()]
    for index, source in enumerate(sorted(candidates)):
        if index and index % 1000 == 0: print(f'Inspected {index}/{len(candidates)} products', flush=True)
        # Exclude derived aliases from this/previous migration.
        relative=source.relative_to(Path(legacy_data) if source.is_relative_to(Path(legacy_data)) else Path(figures))
        if relative.parts[0] in {'hx','vx','z0','observations'} or any(p.startswith('delta_z_') for p in relative.parts[:-1]):
            continue
        if '_magnetic_orientation_validation' in source.stem:
            records.append(dict(source=str(source),status='skipped',reason='Retired display-only magnetic orientation validation plot.'))
            continue
        product=migration_product(source)
        if product is None:
            records.append(dict(source=str(source),status='flagged',reason='No single-pair diagnostic identity (includes comparison assets).'))
            continue
        try:
            reference, numerical_source=source_reference(source,catalog)
            config=migration_config(reference,numerical_source,source)
            root=DATA_ROOT if source.is_relative_to(Path(legacy_data)) else FIGURE_ROOT
            # Files under old diagnostic folders can share their basename. A
            # content hash prevents overwriting distinct legacy bytes with the
            # same incomplete processing provenance.
            dataless=bool(getattr(source.stat(), 'st_flags', 0) & 0x40000000)
            checksum=None if dataless else paths.file_sha256(source)
            # Stable across Google Drive hydration changes: file identity does
            # not switch from a path digest to a content digest on download.
            identifier=paths.digest(str(legacy_figure_identity_path(source.resolve(),FIGURE_ROOT.parent)))
            filename=source.stem[:80]+'__legacy_'+identifier[:16]+source.suffix
            destination=paths.build_output_file(root,config,product,filename,create=apply)
            if apply:
                paths._ensure_link(destination,source.resolve())
                for suffix in ('.inputs.json','.atmosphere.json'):
                    sidecar=find_json_sidecar(source, suffix)
                    if sidecar.is_file():paths._ensure_link(json_sidecar_path(destination, suffix),sidecar.resolve())
                paths.register_output(destination,config,product,root=root,
                    extra={'migration_source':str(source.resolve()),'source_sha256':checksum,'automatic_reuse':False,
                           'verification':'same underlying file via relative symlink; content hash deferred for cloud-only files' if dataless else 'same underlying file and SHA256'},
                    checksum=not dataless)
                if not destination.samefile(source): raise ValueError('Migrated link verification failed.')
                if checksum and paths.file_sha256(destination)!=checksum:raise ValueError('Migrated content verification failed.')
            geometry=config['_output_context']['identity']['geometry']
            records.append(dict(source=str(source),destination=str(destination),status='linked' if apply else 'planned',
                sha256=checksum,category=config['_output_context']['identity']['category'],
                organization_prefix=config['_output_context']['identity']['organization_prefix'],
                grouping_status=geometry['grouping_status']))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            records.append(dict(source=str(source),status='flagged',reason=str(exc)))
    report=dict(schema_version=1,applied=apply,counts=dict(Counter(r['status'] for r in records)),records=records)
    if apply:paths.atomic_json(json_output_path(DATA_ROOT/'geometry_migration_manifest.json'),report)
    return report


def main():
    '''
    Purpose
    -------
    Parse geometry-migration options and report their status counts.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv and plans or applies recorded-provenance migration; missing
        distinct legacy figure roots are rejected.
    '''

    # Parse geometry-migration options and report their status counts
    project=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-data',type=Path,default=project/'Data/Time-Distance')
    parser.add_argument('--figures',type=Path,default=legacy_figure_root(project))
    parser.add_argument('--data-root',type=Path,default=project/'Data')
    parser.add_argument('--figure-root',type=Path,default=project/'Figures')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.figures is None:parser.error('No separate legacy Figures directory was found; provide --figures explicitly.')
    report=migrate(args.legacy_data,args.figures,args.data_root,figure_root=args.figure_root,apply=args.apply)
    print(json.dumps(report['counts'],sort_keys=True))

if __name__=='__main__':main()
