'''
Purpose
-------
Resolve original cube provenance and rebuild Gaussian-filtered phase diagnostics through
the native pipeline.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for dopplergram_recalculation.py.

Notes
-----
Resolve numerical cube provenance and recalculate with the native pipeline.

Phase-only products cannot be Fourier filtered. Input sidecars carry the original
cube identity, heights, sampling and physical-domain preprocessing separately.
'''
from __future__ import annotations
# Import the libraries and shared helpers used by this module
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import copy
import json
import re
import time
from threading import RLock

import numpy as np
import pipeline


@dataclass
class Baseline:
    '''
    Purpose
    -------
    Hold reusable original/post-magnetogram cubes and their native phase diagnostic.

    Inputs
    ------
    cubes: tuple of np.ndarray
        Two matching baseline cubes in (t, y, x) order.
    config: dict
        Resolved runtime configuration used by the native diagnostic.
    values: np.ndarray
        Degree-valued phase spectrum in (n_kh, n_nu) project order.
    kh: np.ndarray
        Horizontal-wavenumber axis in Mm^-1.
    nu: np.ndarray
        Frequency axis in mHz.
    metadata: dict
        Native diagnostic, source-version, coordinate, and input-reference metadata.
    raw_cubes: tuple or None
        Raw inputs retained when Gaussian-before-magnetogram order must be
        reconstructed.

    Outputs
    -------
    baseline: Baseline
        Cached cube arrays, resolved runtime configuration, spectrum, axes, and
        provenance.
    '''

    cubes: tuple
    config: dict
    values: np.ndarray
    kh: np.ndarray
    nu: np.ndarray
    metadata: dict
    raw_cubes: tuple | None = None


def input_path(product):
    '''
    Purpose
    -------
    Construct the managed original-input sidecar path for a product.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.

    Outputs
    -------
    path: pathlib.Path
        Product companion ending in .inputs.json under json_files.
    '''

    # Construct the managed original-input sidecar path for a product
    return json_sidecar_path(product, '.inputs.json')


def input_reference(config, *, provenance='pipeline runtime configuration'):
    '''
    Purpose
    -------
    Serialize the resolved original-input, sampling, filtering, and output provenance.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    provenance: str
        Description of the source of the recorded runtime settings.

    Outputs
    -------
    reference: dict
        Schema-version-1 record with explicit original paths/heights, cadence in
        seconds, spatial scale in Mm, and copied stage settings.
    '''

    # Serialize the resolved original-input, sampling, filtering, and output provenance
    data = config['data']
    keys = ('source_type','file','v1','v2','h1','h2','observable','delta_z_km',
            'resolved_h1_index','resolved_h2_index','resolved_h1_km','resolved_h2_km',
            'resolved_delta_z_km','paired_cubes','dataset_id','category','field_strength_G','height_labels','observation_observable')
    return dict(schema_version=1, data={key: data[key] for key in keys if key in data},
        sampling={key: float(config['time_distance'][key]) for key in ('dt','p_dx_Mm')},
        time_distance=copy.deepcopy(config['time_distance']),
        output=copy.deepcopy(config.get('output', {})),
        filter_configuration=copy.deepcopy(config.get('filter_configuration', {'mode': 'manual'})),
        filtering=copy.deepcopy(config['filtering']),
        magnetogram_mode=copy.deepcopy(config.get('magnetogram_mode', {'single_cube':'bottom'})),
        provenance=provenance)


def write_input_reference(product, config, *, provenance='pipeline runtime configuration'):
    '''
    Purpose
    -------
    Publish an original-input sidecar only when its exact contents changed.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    provenance: str
        Source explanation stored with the processing reference.

    Outputs
    -------
    reference: dict
        Existing-equivalent or atomically written input reference.
    '''

    # Publish an original-input sidecar only when its exact contents changed
    from komega_bokeh_context import _write_json
    value = input_reference(config, provenance=provenance)
    path = input_path(product)
    if path.is_file() and json.loads(path.read_text()) == value:
        return value
    _write_json(path, value)
    return value


def _legacy_filters(product):
    '''
    Purpose
    -------
    Recover explicit historical filtering settings or recognized unfiltered-product
    state.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.

    Outputs
    -------
    filtering: dict
        Parsed historical stage settings; missing/incomplete preprocessing provenance
        raises ValueError.
    '''

    # Recover explicit historical filtering settings or recognized unfiltered-product
    # state
    folder = next((p for p in Path(product).parents if re.fullmatch(r'filter_\d+', p.name)), None)
    path = None if folder is None else folder/'filter_parameters.txt'
    if path is None or not path.is_file():
        # Explicit unfiltered recovered products contain only the original FFT.
        if 'bokeh_datasets' in Path(product).parts or 'unfiltered' in Path(product).stem:
            return dict(enabled=False, filter_sequence=[], magnetogram={'enabled':False}, gaussian={'enabled':False})
        raise ValueError('Saved product has no preprocessing provenance; a phase map alone cannot identify its baseline cubes.')
    result = {}
    for line in path.read_text().splitlines():
        key, sep, raw = line.partition(':')
        if not sep or not key.startswith('filtering.'): continue
        raw = raw.strip()
        if raw.lower() in {'true','false'}: value = raw.lower() == 'true'
        elif raw.startswith('['): value = [part.strip() for part in raw.strip('[]').split(',') if part.strip()]
        else:
            try: value = float(raw)
            except ValueError: value = raw
        target = result
        parts = key.split('.')[1:]
        for part in parts[:-1]: target = target.setdefault(part,{})
        target[parts[-1]] = value
    if 'enabled' not in result or 'filter_sequence' not in result:
        raise ValueError('Incomplete saved filter sequence.')
    return result


@lru_cache(maxsize=4)
def _navigation_observables(figure_root):
    '''
    Purpose
    -------
    Index explicit saved launch contexts by their recorded comparison observable.

    Inputs
    ------
    figure_root: str or pathlib.Path
        Managed figure root, with any distinct verified legacy archive included in
        discovery.

    Outputs
    -------
    observables: dict
        Numerical product paths mapped to canonical observables; conflicting recorded
        values raise ValueError.
    '''

    # Index explicit saved launch contexts by their recorded comparison observable
    import comparison_gallery as gallery
    from figure_locations import canonical_figure_root, figure_project_root, legacy_figure_root
    result = {}
    roots=[canonical_figure_root(figure_root)]
    legacy=legacy_figure_root(figure_project_root(roots[0]))
    if legacy is not None and legacy not in roots: roots.append(legacy)
    plots = {str(p.path.with_suffix('')): p for root in roots for p in gallery.discover_comparison_plots(root)}
    for path in (p for root in roots for p in root.rglob('*.subplots.json')):
        record = json.loads(path.read_text())
        # The existing parser reads the generator's canonical scientific name,
        # not the opaque individual-figure hash.
        plot = plots.get(str(product_from_json_sidecar(path, '.jpeg').with_suffix('')))
        if plot is None: continue
        observable = gallery._parse_comparison_plot_name(plot).observable
        for target in record.get('targets',[]):
            context = target.get('bokeh',{}).get('workspace',{}).get('context')
            if context:
                from komega_bokeh_context import validate_context
                product = str(validate_context(context).files[0])
                if product in result and result[product] != observable:
                    raise ValueError('Conflicting observable provenance for '+product)
                result[product] = observable
    return result


def resolve_input_reference(product, config_file, *, observable=None):
    '''
    Purpose
    -------
    Resolve an explicit input sidecar or uniquely recover supported recorded legacy
    input provenance.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    observable: str or None
        Explicit simulation field name when it cannot be recovered from canonical
        navigation metadata.

    Outputs
    -------
    reference: dict
        Schema-version-1 original cube/height/filter/sampling record. Unsupported
        schemas, ambiguous inputs, and insufficient phase-only provenance raise
        ValueError.
    '''

    # Resolve an explicit input sidecar or uniquely recover supported recorded legacy
    # input provenance
    product = Path(product).absolute()
    if find_json_sidecar(product, '.inputs.json').is_file():
        value = json.loads(find_json_sidecar(product, '.inputs.json').read_text())
        if value.get('schema_version') != 1: raise ValueError('Unsupported Dopplergram input reference.')
        return value
    from observation_datasets import configuration
    from atmospheric_profiles import read_sidecar
    module = configuration(str(Path(config_file).resolve()))
    cfg = copy.deepcopy(module.config)
    cfg['filtering'] = _legacy_filters(product)
    # Recover simulation cube and ordered heights only from recorded atmospheric
    # provenance
    atmosphere = read_sidecar(product)
    if atmosphere and atmosphere.get('status') == 'available':
        if observable is None:
            match = re.match(r'^(?:hx_\d+g|vx_\d+g|z0_0g)_(v[123]|bb[123]|rho)_',product.stem,re.I)
            observable = match[1] if match else _navigation_observables(str(Path(module.figure_dir).resolve())).get(str(product))
        if not observable: raise ValueError('Simulation product lacks an explicit original observable.')
        cube = Path(atmosphere['provenance']['cube']['path'])
        h1,h2 = atmosphere['height_indices']
        cfg['data'].update(source_type='single_cube',file=str(cube),observable=observable,h1=h1,h2=h2,
            resolved_h1_index=h1,resolved_h2_index=h2,
            resolved_h1_km=atmosphere['height_pair_km'][0],resolved_h2_km=atmosphere['height_pair_km'][1])
        provenance = 'saved atmospheric cube/height provenance; observable from canonical pipeline name or saved megaplot metadata'
    else:
        # Resolve legacy observational line pairs only when each original cube is unique
        match = re.fullmatch(r'(\d{1,2}[a-z]{3}\d{4})_([a-z]+\d+)_([a-z]+\d+)(?:_(?:annulus|east|west|north|south))?_komega',product.stem,re.I)
        if not match: raise ValueError('No original Dopplergram reference for this phase-only product.')
        roots = [Path(module.vesa_2025_data_root),Path(module.vesa_2026_dir)/'Data']
        candidates = {Path(p).resolve() for root in roots if root.is_dir()
                      for p in module.discover_paired_cube_batch_input_paths(root)}
        pair = []
        for line in (match[2],match[3]):
            matches = [p for p in candidates if match[1].lower() in p.name.lower()
                       and pipeline.normalize_paired_line_token(p).lower() == line.lower()]
            if len(matches) != 1: raise ValueError(f'Cannot identify one original {match[1]} {line} Dopplergram ({len(matches)} matches).')
            pair.append(str(matches[0]))
        cfg['data'].update(source_type='paired_cubes',v1=pair[0],v2=pair[1],h1=0,h2=1)
        provenance = 'legacy canonical paired-line product name; unique eligible original cubes in configured observation roots'
    from astropy.io import fits
    # Retain the saved cadence and pixel scale in the recovered input reference
    header = fits.getheader(product)
    cfg['time_distance'].update(dt=float(header['DT_S']),p_dx_Mm=float(header['DX_MM']))
    return input_reference(cfg,provenance=provenance)


def runtime_config(reference, config_file):
    '''
    Purpose
    -------
    Reconstruct a native runtime configuration from recorded original-input settings.

    Inputs
    ------
    reference: dict
        Schema-version-1 data, sampling, filter, and output reference.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    config: dict
        Prepared manual-mode configuration with remapped I/O paths and checked original
        cadence/pixel scale; inconsistent recorded sampling raises ValueError.
    '''

    # Reconstruct a native runtime configuration from recorded original-input settings
    from observation_datasets import configuration
    module = configuration(str(Path(config_file).resolve()))
    from portable_paths import remap_data
    data = remap_data(reference['data']); sampling = reference['sampling']
    if data['source_type']=='paired_cubes':
        delta = data.get('resolved_delta_z_km',data.get('paired_cubes',{}).get('delta_z_km',module.paired_cubes_inputs['delta_z_km']))
        cfg = module.get_config(source_type='paired_cubes',v1_path=data['v1'],v2_path=data['v2'],
            delta_z_km=delta,dt=sampling['dt'],p_dx_Mm=sampling['p_dx_Mm'])
    else:
        cfg = module.get_config(source_type='single_cube',file_path=data['file'],
            observable=data['observable'],h1=data['h1'],h2=data['h2'])
    cfg['time_distance'].update(reference.get('time_distance', {}))
    cfg['time_distance'].update(reference['sampling'])
    cfg['output'] = copy.deepcopy(reference.get('output', {}))
    cfg['data'].update({k: v for k, v in data.items() if k not in {'source_type', 'file', 'v1', 'v2'}})
    cfg['filtering'] = copy.deepcopy(reference['filtering'])
    cfg['optimized_filtering'] = {'mode': 'manual'}
    cfg['magnetogram_mode'] = copy.deepcopy(reference['magnetogram_mode'])
    cfg['_module_dir'] = str(Path(config_file).resolve().parent)
    cfg['dispersion_curves']['mode'] = 'theory_based'
    cfg = pipeline.prepare_runtime_config(cfg)
    cfg['data']['orientation_validation_outfile'] = ''
    # Interactive FFTs need the native atmospheric parameters, not repeated
    # publication/verification of the batch's PDF and PNG diagnostics.
    cfg.setdefault('atmospheric_profiles', {})['make_figure'] = False
    for key,value in sampling.items():
        if not np.isclose(cfg['time_distance'][key],value,rtol=1e-8,atol=1e-12):
            raise ValueError(f'Recorded {key} disagrees with the original cube coordinates.')
    return cfg


def _version(paths):
    '''
    Purpose
    -------
    Record the current physical versions of ordered source paths.

    Inputs
    ------
    paths: iterable of path-like
        Original input paths resolved through verified relocation mappings.

    Outputs
    -------
    versions: tuple
        Original path labels with current size, mtime_ns, and ctime_ns for cache
        invalidation.
    '''

    # Record the current physical versions of ordered source paths
    from data_locations import current_source_path
    return tuple((str(p),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
                 for p in paths for stat in (current_source_path(p).stat(),))


def load_baseline(reference, config_file):
    '''
    Purpose
    -------
    Reuse a source-versioned baseline while serializing simultaneous cache misses.

    Inputs
    ------
    reference: dict
        Recorded original-input, sampling, and filtering provenance.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    baseline: Baseline
        Loaded original/post-magnetogram cubes and native phase diagnostic; relevant
        observational magnetograms participate in invalidation.
    '''

    # Reuse a source-versioned baseline while serializing simultaneous cache misses
    data = reference['data']
    paths = [Path(data['file'])] if data['source_type']=='single_cube' else [Path(data[key]) for key in ('v1','v2')]
    # Include associated magnetograms in cache invalidation when they are used.
    if reference['filtering'].get('enabled') and reference['filtering'].get('magnetogram',{}).get('enabled') and data['source_type']=='paired_cubes':
        F = pipeline.load_agw_filter_class(Path(config_file))
        path = F.load_magnetograms.__globals__['find_paired_cubes_magnetogram'](*paths)
        if path: paths.append(Path(path))
    key=json.dumps(reference,sort_keys=True),str(Path(config_file).resolve())
    # functools' cache permits duplicate simultaneous misses. Both dataset
    # panels can request the same launch, so share its native cube read/FFT.
    with _baseline_lock(key):
        return _load_baseline_cached(*key,_version(paths))


@lru_cache(maxsize=8)
def _baseline_lock(key):
    '''
    Purpose
    -------
    Reuse a reentrant lock for one normalized baseline cache key.

    Inputs
    ------
    key: tuple
        Canonical reference JSON and configuration path identifying the baseline.

    Outputs
    -------
    lock: threading.RLock
        Cached per-input lock used to avoid duplicate simultaneous loads/FFTs.
    '''

    # Reuse a reentrant lock for one normalized baseline cache key
    return RLock()


@lru_cache(maxsize=2)
def _load_baseline_cached(reference_json, config_file, versions):
    '''
    Purpose
    -------
    Load matching original cubes, apply recorded magnetic preprocessing, and cache their
    native diagnostic.

    Inputs
    ------
    reference_json: str
        Canonical JSON encoding of the recorded input reference.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    versions: tuple
        File paths and filesystem-version values included in the cache key.

    Outputs
    -------
    baseline: Baseline
        Read-only baseline cubes and phase axes/provenance, with raw cubes retained for
        reversed filter ordering. Changed sources or incompatible shapes raise
        ValueError.
    '''

    # Load matching original cubes, apply recorded magnetic preprocessing, and cache
    # their native diagnostic
    reference = json.loads(reference_json)
    cfg = runtime_config(reference,config_file)
    F = pipeline.load_agw_filter_class(Path(config_file))
    loader = F(cfg)
    raw = loader.load_dopplergrams()
    if len(raw)!=2 or raw[0].ndim!=3 or raw[0].shape!=raw[1].shape:
        raise ValueError('Original Dopplergrams must have matching [t,y,x] dimensions; no resizing is applied.')
    from magnetogram_workflow import DopplerDataset,_coordinates
    data=cfg['data']
    files=(Path(data['file']),) if data['source_type']=='single_cube' else tuple(Path(data[key]) for key in ('v1','v2'))
    dataset=DopplerDataset('resolved-input','Original numerical input',data['source_type'],files,{})
    _,coordinate_metadata=_coordinates(dataset,cfg,raw[0].shape,files)
    filters = cfg['filtering']
    magnetogram_active = filters.get('enabled') and filters.get('magnetogram',{}).get('enabled') and 'magnetogram' in filters.get('filter_sequence',[])
    cubes = loader.apply_magnetogram_filter(*raw) if magnetogram_active else raw
    values,kh,nu,meta = pipeline.TimeDistance(cfg).compute_komega_diagram(*cubes)
    meta = {key:value for key,value in meta.items() if key not in {'k_axis','nu_axis'}}
    meta['analysis_input'] = reference
    meta['coordinates'] = coordinate_metadata
    meta['dopplergram_source_versions'] = list(versions)
    cfg['_dopplergram_source_versions'] = list(versions)
    sequence = filters.get('filter_sequence',[])
    reverse = magnetogram_active and 'gaussian' in sequence and sequence.index('gaussian') < sequence.index('magnetogram')
    if _version([Path(entry[0]) for entry in versions]) != versions:
        raise ValueError('Original cube changed during loading; reselect it.')
    for cube in cubes: cube.setflags(write=False)
    return Baseline(tuple(cubes),cfg,values,kh,nu,meta,tuple(raw) if reverse else None)


def recalculate(cubes, config, parameters=None, *, raw_cubes=None):
    '''
    Purpose
    -------
    Rebuild filtered cubes from an unchanged baseline and run the native phase
    diagnostic.

    Inputs
    ------
    cubes: sequence of two np.ndarray
        Matching baseline Dopplergram cubes in (t, y, x) order.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    parameters: dict or None
        Gaussian center/FWHM inputs in Mm^-1 and mHz; None keeps the supplied cubes
        unfiltered here.
    raw_cubes: sequence of two np.ndarray or None
        Original cubes used to reconstruct the complete recorded filter sequence when
        stage order requires it.

    Outputs
    -------
    values, kh, nu, metadata, filtered: tuple
        Degree-valued [k_h, nu] phase array, Mm^-1/mHz axes, recalculation provenance,
        and the two filtered (t, y, x) cubes. Source changes or incompatible cubes raise
        ValueError.

    Notes
    -----
    Always reconstruct each filtered cube and call the original diagnostic.
    '''
    # Rebuild filtered cubes from an unchanged baseline and run the native phase
    # diagnostic
    started = time.perf_counter()
    cfg = copy.deepcopy(config)
    versions = tuple(tuple(entry) for entry in cfg.get('_dopplergram_source_versions',[]))
    if versions and _version([Path(entry[0]) for entry in versions]) != versions:
        raise ValueError('Original Dopplergram changed; reselect the dataset before recalculation.')
    if len(cubes)!=2 or np.shape(cubes[0])!=np.shape(cubes[1]) or np.ndim(cubes[0])!=3:
        raise ValueError('Recalculation requires two matching [t,y,x] Dopplergram cubes.')
    filtered = tuple(cubes)
    if parameters is not None:
        from observation_filter_registry import validate_parameters
        cfg['filtering']['gaussian'] = dict(validate_parameters(parameters),enabled=True)
        F = pipeline.load_agw_filter_class(Path(cfg['_module_dir'])/'config.py')
        loader = F(cfg)
        if raw_cubes is None:
            filtered = loader.apply_gaussian_filter(*cubes)
        else:
            cfg['filtering']['enabled'] = True
            filtered = loader.apply_filters(*raw_cubes)
    values,kh,nu,metadata = pipeline.TimeDistance(cfg).compute_komega_diagram(*filtered)
    if versions and _version([Path(entry[0]) for entry in versions]) != versions:
        raise ValueError('Original Dopplergram changed during recalculation; reselect it.')
    metadata['recalculation'] = dict(method='independent cube Fourier filtering -> checked real inverse FFT -> native TimeDistance.compute_komega_diagram',
        gaussian_parameters=parameters, baseline='unchanged input cubes on every adjustment',seconds=time.perf_counter()-started)
    return values,kh,nu,metadata,filtered


def migrate_inputs(config_file):
    '''
    Purpose
    -------
    Publish missing original-input sidecars for discovered saved products.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    counts: dict
        Published-sidecar count and product-specific unavailable reasons; existing input
        sidecars are retained.

    Notes
    -----
    Publish input provenance for saved products through the existing catalog.
    '''
    # Publish missing original-input sidecars for discovered saved products
    from observation_datasets import configuration,discover_observations
    from komega_bokeh_context import _write_json
    module = configuration(str(Path(config_file).resolve()))
    products = {str(item.files[0]) for item in discover_observations(config_file=config_file,raw_roots=[],include_simulations=True)}
    products.update(_navigation_observables(str(Path(module.figure_dir).resolve())))
    counts = dict(published=0,unavailable=[])
    for product in sorted(products):
        try:
            reference = resolve_input_reference(product,config_file)
            if not input_path(product).is_file():
                _write_json(input_path(product),reference);counts['published']+=1
        except (ValueError,KeyError,OSError) as exc:
            counts['unavailable'].append(dict(product=product,error=str(exc)))
    return counts


if __name__ == '__main__':
    from gaussian_filter_explorer import CONFIG_FILE
    print(json.dumps(migrate_inputs(CONFIG_FILE),indent=2))
