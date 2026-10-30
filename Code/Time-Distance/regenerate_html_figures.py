'''
Purpose
-------
Restore explicit historical numerical launch records and regenerate their HTML galleries
without rewriting source figure images.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for regenerate_html_figures.py.

Notes
-----
Restore historical numerical launch records and regenerate the HTML galleries.

Uses the notebook's existing loaders/FFT for unfiltered figures and the exact
saved FITS for Gaussian figures. Original figure images are never rewritten.
'''
# Import the libraries and shared helpers used by this module
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar
import argparse
import copy
import gc
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from data_locations import CO5BOLD_ROOT
from figure_locations import canonical_figure_root

import numpy as np

import comparison_gallery as gallery
import komega_bokeh_context as context
from gaussian_filter_explorer import _load_config, CONFIG_FILE


def notebook_helpers():
    '''
    Purpose
    -------
    Execute the existing plotting notebook's initial helper cells in a separate
    namespace.

    Inputs
    ------
    None

    Outputs
    -------
    namespace: dict
        Plot-loader/helper definitions imported from the first two plots.ipynb cells;
        their existing import/setup effects occur during execution.
    '''

    # Execute the existing plotting notebook's initial helper cells in a separate
    # namespace
    notebook = json.loads((CONFIG_FILE.parent / 'plots.ipynb').read_text())
    namespace = {'__name__': 'historical_figure_loaders'}
    for cell in notebook['cells'][:2]:
        if cell['cell_type'] == 'code':
            exec(compile(''.join(cell['source']), 'plots.ipynb', 'exec'), namespace)
    return namespace


def filter_products(data_root):
    '''
    Purpose
    -------
    Index explicitly recorded Gaussian-only phase products by exact filter and original
    filename.

    Inputs
    ------
    data_root: pathlib.Path
        Numerical-product root containing historical filter folders or managed metadata
        sidecars.

    Outputs
    -------
    products: dict
        (Gaussian processing slug, product name) keys mapped to numerical FITS files;
        incompatible duplicate identities raise ValueError.

    Notes
    -----
    Index only verified Gaussian-only products, preserving filter identity.
    '''
    # Index explicitly recorded Gaussian-only phase products by exact filter and
    # original filename
    result = {}
    for parameter_file in sorted(data_root.glob('filter_*/filter_parameters.txt')):
        fields = dict(line.split(': ', 1) for line in parameter_file.read_text().splitlines()
                      if ': ' in line)
        if fields.get('filtering.filter_sequence') != '[gaussian]':
            continue
        try:
            numbers = [f'{float(fields["filtering.gaussian." + key]):g}'.replace('.', '_')
                       for key in ('central_k', 'width_k', 'central_f', 'width_f')]
        except (KeyError, ValueError):
            continue
        slug = 'gaussian_filtered_gauss_ck_{}_wk_{}_cf_{}_wf_{}'.format(*numbers)
        for product in parameter_file.parent.rglob('*_komega.fits'):
            key = (slug, product.name)
            if key in result and result[key].read_bytes() != product.read_bytes():
                raise ValueError(f'Ambiguous numerical source: {key}')
            result[key] = product
    # Canonical products store filtering beside each product, not in a folder.
    import output_paths as manager
    # Index managed Gaussian-only products without collapsing conflicting recorded
    # sources
    for metadata in data_root.rglob('*.metadata.json'):
        if metadata.is_symlink() or any(p.startswith('delta_z_') for p in metadata.parts): continue
        record = json.loads(metadata.read_text())
        if record.get('product')!='komega_diagram': continue
        filtering=record['identity']['filtering']
        if not filtering.get('enabled') or filtering.get('filter_sequence')!=['gaussian']: continue
        numbers=[f'{float(filtering["gaussian"][key]):g}'.replace('.', '_')
                 for key in ('central_k','width_k','central_f','width_f')]
        slug='gaussian_filtered_gauss_ck_{}_wk_{}_cf_{}_wf_{}'.format(*numbers)
        product=product_from_json_sidecar(metadata, '.fits')
        if product.is_file():
            original=record.get('extra', {}).get('migration_source')
            name=Path(original).name if original else manager.strip_run_suffix(product.stem)+'.fits'
            key=(slug,name)
            if key in result and not result[key].samefile(product):
                raise ValueError(f'Ambiguous recorded numerical source: {key}')
            result[key]=product
    return result


def recover_unfiltered(helpers, modules, cfg, saved_metadata):
    '''
    Purpose
    -------
    Recover the native unfiltered phase diagnostic while retaining verified historical
    atmospheric metadata.

    Inputs
    ------
    helpers: dict
        Existing plotting-notebook loader/construction callables.
    modules: dict
        Project module namespace returned by the notebook helpers.
    cfg: dict
        Resolved pipeline configuration for the current dataset.
    saved_metadata: dict or None
        Historical atmosphere/orientation metadata reused only after native parameter
        validation.

    Outputs
    -------
    data: dict
        Existing loaded plot data or newly computed degree-valued spectrum, physical
        axes, cube shape, and numerical provenance.

    Notes
    -----
    Run the native unfiltered FFT and retain the historical atmosphere metadata.

    Gaussian-only filtering does not change the cube's magnetic/atmosphere
    metadata. Reuse those saved values instead of rereading every magnetic layer.
    They are used only for model initialization, never for the FFT calculation.
    '''
    # Recover the native unfiltered phase diagnostic while retaining verified historical
    # atmospheric metadata
    plot_cfg = helpers['build_unfiltered_komega_plot_config'](cfg)
    path = helpers['resolve_komega_plot_data_file'](cfg)
    if path.is_file():
        return helpers['load_komega_plot_data'](cfg, modules=modules)
    if saved_metadata is None:
        return helpers['load_komega_plot_data'](cfg, modules=modules)
    try:
        context.simulation_parameters(cfg, saved_metadata)
    except ValueError:
        # In particular, historical zero-field products can omit undefined
        # angles. Recover complete native metadata instead of borrowing defaults.
        return helpers['load_komega_plot_data'](cfg, modules=modules)
    _, _, pipeline = modules['time_distance_module'].build_pipeline(
        config_file=CONFIG_FILE, config_override=copy.deepcopy(plot_cfg))
    pipeline.orientation_validation_outfile = None
    first, second = pipeline.load_raw_dopplergrams()
    spectrum, kh, nu, metadata = pipeline.compute_komega_diagram(first, second)
    data = helpers['build_in_memory_komega_plot_data'](path, spectrum, kh, nu, metadata)
    data.update(orientation=saved_metadata, cube_shape=list(first.shape), computed_for_plot=True)
    return data


def refresh_catalog_atmospheres(base, cubes, figure_root):
    '''
    Purpose
    -------
    Refresh catalog simulation products missing current verified atmospheric provenance.

    Inputs
    ------
    base: dict
        Base runtime configuration and declared legacy profile units.
    cubes: dict
        Canonical historical simulation case labels mapped to original cube paths.
    figure_root: str or pathlib.Path
        Destination figure root used for native atmospheric diagnostics.

    Outputs
    -------
    None
        Resolves unique native cube/layer identities, writes upgraded atmosphere
        sidecars, and reports a count; ambiguous or inconsistent heights/sources raise
        errors.

    Notes
    -----
    Migrate catalog products omitted from the historical megaplot selection.

    Legacy filenames are the last resort only when no saved height metadata exist.
    Every inferred layer is checked against the original coordinate before use.
    '''
    # Refresh catalog simulation products missing current verified atmospheric
    # provenance
    from astropy.io import fits
    from atmospheric_profiles import read_sidecar, resolve_parameters, write_sidecar
    from observation_datasets import discover_observations
    from pipeline import infer_netcdf_height_coordinates_km
    import atmospheric_profiles
    implementation = sha256(Path(atmospheric_profiles.__file__).read_bytes()).hexdigest()
    def current(record):
        '''
        Purpose
        -------
        Check whether a record matches current atmospheric implementation, source
        versions, and units.

        Inputs
        ------
        record: dict or None
            Existing atmospheric sidecar record.

        Outputs
        -------
        current: bool
            True only for available records whose source files, hashes/version metadata,
            and unit provenance remain current.
        '''

        # Check whether a record matches current atmospheric implementation, source
        # versions, and units
        provenance = (record or {}).get('provenance', {})
        if (record or {}).get('status') != 'available' or provenance.get('implementation_sha256') != implementation:
            return False
        for name in ('cube', 'profile'):
            source = provenance.get(name, {})
            path = Path(source.get('path', ''))
            if not path.is_file():
                return False
            stat = path.stat()
            if (source.get('size_bytes'), source.get('mtime_ns')) != (stat.st_size, stat.st_mtime_ns):
                return False
        declared = base.get('atmospheric_profiles', {}).get('legacy_units', {})
        return all(entry['source'] == 'file attribute' or entry['unit'] == declared.get(field)
                   for field, entry in provenance.get('source_units', {}).items())
    # Restrict legacy filename recovery to recognized simulation products and explicit
    # heights
    pattern = re.compile(r'^(hx_\d+g|vx_\d+g|z0_0g)_(v[123]|bb[123]|rho)_(\d+(?:_\d+)?)km_(\d+(?:_\d+)?)km_komega$', re.I)
    cache, count = {}, 0
    for item in discover_observations(product_roots=[base['paths']['data_output_dir']],
                                      raw_roots=[], include_simulations=True):
        if item.kind != 'simulation_fits':
            continue
        product = item.files[0]
        existing = read_sidecar(product)
        if current(existing):
            continue
        header = fits.getheader(product)
        matched = pattern.fullmatch(product.stem)
        if matched is None or matched[1].lower() not in cubes:
            raise ValueError(f'Cannot identify a unique original cube for legacy product: {product}')
        cube = cubes[matched[1].lower()]
        # Prefer saved physical-height cards and disclose filename-derived height
        # uncertainty otherwise
        if 'H1_KM' in header and 'H2_KM' in header:
            heights = [float(header[key]) for key in ('H1_KM', 'H2_KM')]
            height_source = 'saved FITS H1_KM/H2_KM metadata'
            tolerance = 1e-6
        else:
            heights = [float(matched[i].replace('_', '.')) for i in (3, 4)]
            height_source = 'legacy canonical pipeline filename; no height metadata in FITS; independently verified against native cube coordinates'
            tolerance = max(.5*10**(-len(matched[i].split('_',1)[1]))
                            if '_' in matched[i] else .5 for i in (3,4))+1e-6
        key = (str(cube), tuple(heights))
        if key not in cache:
            actual = infer_netcdf_height_coordinates_km(cube)
            with atmospheric_profiles.netCDF4.Dataset(cube) as source:
                native = atmospheric_profiles._length_km(source['xc3'][:],source['xc3'].units)
            # Require the recorded height pair to select one unique native layer pair
            possibilities = {}
            for datum,coordinate in [('pipeline-relative',actual),('native',native)]:
                candidates = [np.flatnonzero(np.isclose(coordinate,height,rtol=0.,atol=tolerance))
                              for height in heights]
                if all(len(matches)==1 for matches in candidates):
                    possibilities.setdefault(tuple(int(matches[0]) for matches in candidates),datum)
            if len(possibilities) != 1:
                raise ValueError(f'Legacy heights do not identify one unambiguous native layer pair: {product} / {heights}')
            indices,datum = next(iter(possibilities.items()))
            cfg = copy.deepcopy(base)
            cfg['paths']['figure_dir'] = str(figure_root)
            cfg['data'].update(file=str(cube), h1=indices[0], h2=indices[1],
                resolved_h1_index=indices[0], resolved_h2_index=indices[1],
                resolved_h1_km=float(actual[indices[0]]), resolved_h2_km=float(actual[indices[1]]))
            atmosphere = resolve_parameters(cfg)
            if atmosphere['status'] != 'available':
                raise ValueError(f'Cannot derive legacy product atmosphere: {product} / {atmosphere}')
            cache[key] = cfg, atmosphere, datum
        cfg, atmosphere, datum = cache[key]
        atmosphere = copy.deepcopy(atmosphere)
        atmosphere['height_identification'] = height_source+'; matched '+datum+' coordinate convention'
        atmosphere['simulation_identification'] = 'canonical pipeline case; matched original cube Model and exact snapshot'
        value = dict(schema_version=1, dataset=dict(id=item.id, file=str(product),source_type='single_cube'),
                     model=dict(key='nc2009',parameters={},units={}))
        # Validate the complete upgraded context before publishing atmospheric sidecars
        upgraded = context.with_atmosphere(value, cfg, atmosphere)
        context.validate_context(upgraded)
        write_sidecar(product, upgraded['atmosphere'])
        count += 1
    print(f'Added atmospheric metadata to {count} additional catalog products.', flush=True)


def restore(figure_root, cube_root, *, check_only=False, refresh_navigation=False, refresh_atmosphere=False, scope=None):
    '''
    Purpose
    -------
    Validate or restore exact numerical launch contexts and regenerate managed or
    historical galleries.

    Inputs
    ------
    figure_root: str or pathlib.Path
        Managed or historical figure tree to validate/regenerate.
    cube_root: str or pathlib.Path
        Original simulation tree used to resolve exact historical cases.
    check_only: bool
        Validate and report without applying the optional refresh operation.
    refresh_navigation: bool
        Refresh historical saved subplot geometry while retaining explicit numerical
        identities.
    refresh_atmosphere: bool
        Refresh native matched atmospheric defaults and sidecars when not check_only.
    scope: str or pathlib.Path or None
        Optional relative subtree restricting this operation.

    Outputs
    -------
    outputs: dict or None
        Managed-scope validation/gallery results are returned; the historical recovery
        path reports progress and returns None. Optional refreshes write
        navigation/atmosphere metadata and recovered numerical sidecars.
    '''

    # Validate or restore exact numerical launch contexts and regenerate managed or
    # historical galleries
    figure_root, cube_root = canonical_figure_root(figure_root), Path(cube_root).resolve()
    from html_output_paths import is_managed_figure_root, write_scoped_comparison_viewers, refresh_managed_contexts
    if scope is not None or is_managed_figure_root(figure_root):
        audit = refresh_managed_contexts(figure_root, CONFIG_FILE, check_only=check_only,
            refresh_atmosphere=refresh_atmosphere, scope=scope)
        if check_only:
            print(audit, flush=True)
            return audit
        results = write_scoped_comparison_viewers(figure_root, scope=scope)
        print(f'Regenerated scoped galleries in {len(results)} configurations.', flush=True)
        return results
    base = copy.deepcopy(_load_config(CONFIG_FILE))
    base['optimized_filtering'] = {'mode':'manual'}  # Replay recorded historical processing, not new optimized settings.
    products = filter_products(Path(base['paths']['data_output_dir']))
    cubes = {re.search(r'simulation_(.+?)_\d+s_', p.name)[1].lower(): p
             for p in cube_root.rglob('*.nc') if re.search(r'simulation_(.+?)_\d+s_', p.name)}
    jobs = []
    numerical_count = 0
    atmospheric_cache = {}
    for plot in gallery.discover_comparison_plots(figure_root):
        if refresh_navigation and not check_only:
            saved_path = context.navigation_path(plot.path)
            if saved_path.is_file():
                saved = json.loads(saved_path.read_text())
                builder = (gallery._build_gaussian_comparison_targets
                           if plot.comparison_type == 'gaussian_filter_comparison'
                           else gallery._build_field_comparison_targets)
                detected = {t['id']: t for t in builder(plot,
                    gallery.COMPARISON_VIEWERS[plot.comparison_type]['title'],
                    f'{plot.h1_km:g}–{plot.h2_km:g} km', figure_dir=figure_root)}
                if set(detected) != {t['id'] for t in saved['targets']}:
                    raise ValueError(f'Changed subplot identities: {plot.path}')
                for target in saved['targets']:
                    geometry = detected[target['id']]
                    target.update(bounds=geometry['bounds'], pixelBounds=geometry['pixelBounds'])
                    if target.get('crop') is not None:
                        target['crop'] = geometry['pixelBounds']
                context._write_json(saved_path, saved)
        targets = gallery.build_subplot_navigation_targets(plot,
            gallery.COMPARISON_VIEWERS[plot.comparison_type]['title'],
            f'{plot.h1_km:g}–{plot.h2_km:g} km', figure_dir=figure_root)
        parts = gallery._parse_comparison_plot_name(plot)
        needs_recovery = any(gallery._target_panel_kind(t) == 'komega' and not t.get('bokeh')
                             for t in targets)
        slugs = (gallery._discover_gaussian_processing_slugs(figure_root, 'z0_0g', parts,
                    gallery._extract_gaussian_filter_count(parts))
                 if plot.comparison_type == 'gaussian_filter_comparison' and needs_recovery else [])
        for target in targets:
            if gallery._target_panel_kind(target) != 'komega':
                continue
            numerical_count += 1
            if target.get('bokeh'):
                context.validate_context(target['bokeh']['workspace']['context'])
                if refresh_atmosphere and not check_only:
                    from atmospheric_profiles import resolve_parameters, write_sidecar
                    # Legacy exports retain explicit subplot case IDs and a
                    # saved height pair. Verify those heights against the native
                    # cube coordinate before upgrading; never derive heights
                    # from an individual figure's filename.
                    case = target['id'].split('-')[0]
                    cube = cubes[case]
                    saved_navigation = json.loads(context.navigation_path(plot.path).read_text())
                    heights = saved_navigation.get('height_pair_km')
                    if heights is None:
                        raise ValueError(f'Explicit historical height metadata missing: {plot.path}')
                    key = (str(cube), tuple(heights))
                    if key not in atmospheric_cache:
                        from pipeline import infer_netcdf_height_coordinates_km
                        actual = infer_netcdf_height_coordinates_km(cube)
                        indices = []
                        for height in heights:
                            matches = np.flatnonzero(np.isclose(actual, height, rtol=1e-5, atol=1e-6))
                            if len(matches) != 1:
                                raise ValueError(f'Ambiguous or invalid historical layer: {cube} / {height}')
                            indices.append(int(matches[0]))
                        cfg = copy.deepcopy(base)
                        cfg['paths']['figure_dir'] = str(figure_root)
                        cfg['data'].update(file=str(cube), h1=indices[0], h2=indices[1],
                            resolved_h1_index=indices[0], resolved_h2_index=indices[1],
                            resolved_h1_km=float(actual[indices[0]]), resolved_h2_km=float(actual[indices[1]]))
                        atmosphere = resolve_parameters(cfg)
                        if atmosphere['status'] != 'available':
                            raise ValueError(f'Cannot upgrade {case} / {heights}: {atmosphere}')
                        atmospheric_cache[key] = (cfg, atmosphere)
                    cfg, atmosphere = atmospheric_cache[key]
                    upgraded = context.with_atmosphere(target['bokeh']['workspace']['context'], cfg, atmosphere)
                    target['bokeh'] = context.launch_links(upgraded)
                    source = context.validate_context(upgraded).files[0]
                    write_sidecar(source, upgraded['atmosphere'])
                    record = dict(context=upgraded, links=target['bokeh'])
                    asset_id = sha256((str(plot.path)+':'+target['id']).encode()).hexdigest()[:24]
                    context._write_json(context.context_path(figure_root/'komega_contexts'/(asset_id+'.jpeg')), record)
                    durable = figure_root/'komega_contexts'/(sha256(str((str(cube), plot.h1_km, plot.h2_km)).encode()).hexdigest()[:24]+'.jpeg')
                    if context.context_path(durable).is_file() and context.context_path(durable) != context.context_path(figure_root/'komega_contexts'/(asset_id+'.jpeg')):
                        old = json.loads(context.context_path(durable).read_text())
                        if old['context']['dataset']['id'] == upgraded['dataset']['id']:
                            context._write_json(context.context_path(durable), record)
                continue
            case = target['id'].split('-')[0]
            if case not in cubes:
                raise FileNotFoundError(f'Original cube for {case}')
            product = None
            if slugs:
                index = int(re.search(r'-filter-(\d+)-', target['id'])[1]) - 1
                name = f'{case}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_komega.fits'
                product = products.get((slugs[index], name))
                if product is None:
                    raise FileNotFoundError(f'Exact filtered source: {slugs[index]} / {name}')
            jobs.append((plot, target, parts, cubes[case], product))
        # Keep targets together so the generated record covers every subplot.
        plot_targets = (plot, targets)
        if refresh_atmosphere and not check_only:
            context._write_json(context.navigation_path(plot.path), dict(schema_version=1,
                comparison_type=plot.comparison_type, height_pair_km=heights,
                all_axes=True, targets=targets))
        for job in jobs:
            if job[0] is plot:
                job[1]['_record'] = plot_targets
    print(f'Verified {numerical_count} numerical handoffs across '
          f'{len(gallery.discover_comparison_plots(figure_root))} megaplots '
          f'({len(jobs)} to recover).', flush=True)
    if check_only:
        return
    if refresh_atmosphere:
        refresh_catalog_atmospheres(base, cubes, figure_root)
    helpers = notebook_helpers()
    modules = helpers['load_project_modules'](CONFIG_FILE)
    cache = {}
    records = {}
    with tempfile.TemporaryDirectory(prefix='morales-html-context-') as temporary:
        base = copy.deepcopy(base)
        base['paths'].update(data_output_dir=temporary + '/data', figure_dir=temporary + '/figures')
        for number, (plot, target, parts, cube, product) in enumerate(jobs, 1):
            records[str(plot.path)] = target.pop('_record')
            key = (str(cube), plot.h1_km, plot.h2_km)
            if key not in cache:
                heights = helpers['infer_netcdf_height_coordinates_km'](cube)
                indices = [int(np.flatnonzero(np.isclose(heights, height))[0])
                           for height in (plot.h1_km, plot.h2_km)]
                cfg = helpers['build_field_strength_comparison_runtime_config'](
                    base, cube, *indices, observable=parts.observable)
                cache[key] = (cfg, None)
            cfg, unfiltered = cache[key]
            asset_id = sha256((str(plot.path) + ':' + target['id']).encode()).hexdigest()[:24]
            asset = figure_root / 'komega_contexts' / (asset_id + '.jpeg')
            durable = figure_root / 'komega_contexts' / (sha256(str(key).encode()).hexdigest()[:24] + '.jpeg')
            if context.context_path(asset).is_file():
                record = json.loads(context.context_path(asset).read_text())
                context.validate_context(record['context'])
            elif product is None and context.context_path(durable).is_file():
                # Resume safely after interruption and reuse FFTs across galleries.
                record = json.loads(context.context_path(durable).read_text())
                context.validate_context(record['context'])
                context._write_json(context.context_path(asset), record)
            else:
                if product is not None:
                    data = helpers['load_komega_data'](product, cfg)
                    try:
                        context.simulation_parameters(cfg, data['orientation'])
                    except ValueError:
                        # A zero-field FITS may omit undefined orientation angles.
                        # The same cube/height pair's native recovery already
                        # established its inputs; reuse those exact named values.
                        native = json.loads(context.context_path(durable).read_text())
                        parameters = native['context']['model']['parameters']
                        if parameters['a'] != 0:
                            raise
                        data['orientation'] = {'dispersion_height_pair': {
                            'a_by_height_km_s': [0., 0.],
                            'theta_by_height_deg': [parameters['theta_deg']] * 2,
                            'phi_by_height_deg': [parameters['phi_deg']] * 2,
                            'height_values_km': [cfg['data']['resolved_h1_km'], cfg['data']['resolved_h2_km']]},
                            'mean_sound_speed_km_s_between_heights': parameters.get('cs')}
                else:
                    if unfiltered is None:
                        product_name = f'{cube.stem.split("simulation_", 1)[1].rsplit("_", 2)[0].lower()}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_komega.fits'
                        reference = next((p for (_, name), p in products.items() if name == product_name), None)
                        saved_metadata = (helpers['load_komega_data'](reference, cfg)['orientation']
                                          if reference is not None else None)
                        unfiltered = recover_unfiltered(helpers, modules, cfg, saved_metadata)
                        # Publish one durable numerical array for repeated panels.
                        saved = context.publish_context(durable, unfiltered, cfg)
                        unfiltered['data_file'] = context.validate_context(saved['context']).files[0]
                        unfiltered['computed_for_plot'] = False
                        cache[key] = (cfg, unfiltered)
                    data = unfiltered
                record = context.publish_context(asset, data, cfg)
            target.update(bokeh=record['links'], panelKind='komega')
            if target.get('missing'):
                target.update(sourceFile=str(plot.path), sourcePath=plot.path.name,
                              src='../' + plot.path.name, crop=target['pixelBounds'], missing=False)
            print(f'[{number}/{len(jobs)}] {target["id"]}: {plot.h1_km:g}–{plot.h2_km:g} km', flush=True)
            if number % 50 == 0:
                gc.collect()
    for plot, targets in records.values():
        context._write_json(context.navigation_path(plot.path), dict(schema_version=1,
            comparison_type=plot.comparison_type, height_pair_km=[plot.h1_km, plot.h2_km],
            all_axes=True, targets=targets))
    results = gallery.write_default_comparison_viewers(
        figure_root, html_dir=figure_root / 'HTML Figures')
    if refresh_atmosphere and (figure_root/'field_strength_comparison.html').is_file():
        # Older exports also live directly in Figures. Upgrade those existing
        # pages through the same generator so neither entry point stays stale.
        gallery.write_default_comparison_viewers(figure_root, html_dir=figure_root)
        print('Refreshed the existing figure-root HTML galleries too.', flush=True)
    print({key: len(value['full_resolution_output_files']) for key, value in results.items()}, flush=True)


def main():
    '''
    Purpose
    -------
    Parse gallery-restoration options and execute the selected validation or refresh
    scope.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv, constructs manual historical-replay settings, and runs
        restore().
    '''

    # Parse gallery-restoration options and execute the selected validation or refresh
    # scope
    parser = argparse.ArgumentParser(description=__doc__)
    base = copy.deepcopy(_load_config(CONFIG_FILE))
    base['optimized_filtering'] = {'mode':'manual'}  # Replay recorded historical processing, not new optimized settings.
    parser.add_argument('--figure-root', default=base['paths']['figure_dir'])
    parser.add_argument('--cube-root', default=str(CO5BOLD_ROOT))
    parser.add_argument('--scope', type=Path, help='Managed source/observable/direction, e.g. simulations/v3/Annulus')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--refresh-navigation', action='store_true',
                        help='Re-detect historical panel geometry while retaining exact numerical contexts')
    parser.add_argument('--refresh-atmosphere', action='store_true',
                        help='Upgrade saved simulation contexts from matching snapshot profiles without repeating FFTs')
    args = parser.parse_args()
    restore(args.figure_root, args.cube_root, check_only=args.check_only,
            refresh_navigation=args.refresh_navigation, refresh_atmosphere=args.refresh_atmosphere, scope=args.scope)


if __name__ == '__main__':
    main()
