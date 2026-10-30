'''
Purpose
-------
Resolve scoped HTML destinations and integrate explicit legacy navigation through
managed relative links.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for html_output_paths.py.

Notes
-----
Scoped HTML destinations and explicit, non-destructive legacy integration.

Scientific products stay canonical. HTML assets use relative links to those
products, never another dataset chosen by a similar filename.
'''
# Import the libraries and shared helpers used by this module
from pathlib import Path
import copy
import json

import output_paths as paths
from figure_locations import canonical_figure_root, figure_project_root, resolve_legacy_figure_source, legacy_figure_identity_path

SUPPORT_DIRECTORY = Path('misc_files') / 'comparison_views'


def is_managed_figure_root(root):
    '''
    Purpose
    -------
    Recognize a managed figure tree from its source/observable/direction organization.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    managed: bool
        True for complete source roots or an existing managed quantity/direction
        subtree.

    Notes
    -----
    Recognize a managed tree even when only one source type has run.
    '''
    # Recognize a managed figure tree from its source/observable/direction organization
    root=canonical_figure_root(root)
    sources=[root/name for name in ('simulations','observations')]
    if all(source.is_dir() for source in sources):
        return True
    # Historical layouts also used simulations/, but put filtering/category
    # before the observable. Only the managed quantity/direction layer counts.
    return any(directory.is_dir() for source in sources
               for geometry in paths.XCORR_GEOMETRIES
               for directory in source.glob('*/'+geometry.title()))


def html_directory(root, identity):
    '''
    Purpose
    -------
    Resolve the category and ordered-height-pair HTML entry directory.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    identity: dict
        Recorded output identity containing organization prefix, category, and height
        geometry.

    Outputs
    -------
    directory: pathlib.Path
        Canonical root/organization/category/height-pair/HTML path.
    '''

    # Resolve the category and ordered-height-pair HTML entry directory
    return (canonical_figure_root(root) / paths.terminal_directory(identity) /
            identity['geometry']['pair'] / 'HTML')


def support_directory(directory):
    '''
    Purpose
    -------
    Resolve the shared support directory below an HTML directory.

    Inputs
    ------
    directory: str or pathlib.Path
        HTML directory containing comparison support assets.

    Outputs
    -------
    directory: pathlib.Path
        HTML directory joined to misc_files/comparison_views.
    '''

    # Resolve the shared support directory below an HTML directory
    return Path(directory) / SUPPORT_DIRECTORY


def shared_support_directory(root, identity):
    '''
    Purpose
    -------
    Resolve height-pair support assets shared across category entrypoints.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    identity: dict
        Recorded identity supplying organization_prefix and geometry.pair.

    Outputs
    -------
    directory: pathlib.Path
        Observable/direction HTML support directory joined to the ordered height pair.
    '''

    # Resolve height-pair support assets shared across category entrypoints
    return (canonical_figure_root(root) / identity['organization_prefix'] / 'HTML' / SUPPORT_DIRECTORY /
            identity['geometry']['pair'])


def comparison_image_directory(root, config):
    '''
    Purpose
    -------
    Resolve the managed megaplot-image support directory for a configuration.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    directory: pathlib.Path
        Shared height-pair comparison directory joined to megaplots.
    '''

    # Resolve the managed megaplot-image support directory for a configuration
    identity = paths._context(config)['identity']
    return shared_support_directory(root, identity) / 'megaplots'


def link_asset(source, folder, *, project=None):
    '''
    Purpose
    -------
    Link an existing HTML asset under a stable original-identity-derived name.

    Inputs
    ------
    source: str or pathlib.Path
        Existing image or supporting artifact to link.
    folder: str or pathlib.Path
        Destination support folder created as needed.
    project: str or pathlib.Path or None
        Project root; None uses the module default when supported.

    Outputs
    -------
    target: pathlib.Path
        Created/reused relative symlink; unavailable sources or unrelated destination
        conflicts raise errors.
    '''

    # Link an existing HTML asset under a stable original-identity-derived name
    source = Path(source).expanduser().absolute()
    if not source.is_file():
        raise FileNotFoundError(f'HTML source asset is unavailable: {source}')
    name = paths.digest(str(legacy_figure_identity_path(source.resolve(),project)))[:24] + '_' + source.name
    target = Path(folder) / name
    paths._ensure_link(target, source)
    return target


def _canonical_index(root):
    '''
    Purpose
    -------
    Index migrated canonical products by their resolved original source location.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    index: dict
        Original physical source paths mapped to existing canonical products with
        matching extensions.
    '''

    # Index migrated canonical products by their resolved original source location
    result = {}
    for sidecar in Path(root).rglob('*.metadata.json'):
        if sidecar.is_symlink():
            continue
        record = json.loads(sidecar.read_text())
        original = record.get('extra', {}).get('migration_source')
        if original:
            # Preserve extensions: metadata for FITS and figures share a stem.
            product = paths.product_from_json_sidecar(sidecar, Path(original).suffix)
            if product.is_file():
                result[str(resolve_legacy_figure_source(original, figure_project_root(root)))] = product.absolute()
    return result


def _processing_context(value, reference, config):
    '''
    Purpose
    -------
    Attach explicit processing and scope metadata to a copied Bokeh launch context.

    Inputs
    ------
    value: dict
        Existing numerical Bokeh context copied before modification.
    reference: dict
        Recorded original-input processing reference.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    links: dict
        Regenerated launch links carrying input/filter/geometry/height/category
        provenance.
    '''

    # Attach explicit processing and scope metadata to a copied Bokeh launch context
    from komega_bokeh_context import launch_links
    value = copy.deepcopy(value)
    value['processing'] = dict(input_reference=reference,
        xcorr_geometry=paths.resolve_output_geometry(config),
        filter_configuration=copy.deepcopy(config.get('filter_configuration', {'mode': 'historical'})))
    value['scope'] = dict(source_type=config['data']['source_type'],
        observable=paths.resolve_output_observable(config),
        geometry=paths.resolve_output_geometry(config),
        height_pair=paths.height_geometry(config),
        category=paths.resolve_category(config).as_posix())
    return launch_links(value)


def import_legacy_comparisons(legacy_root, figure_root, data_root, config_file):
    '''
    Purpose
    -------
    Integrate exact recorded megaplots and launch contexts without recomputing
    scientific arrays.

    Inputs
    ------
    legacy_root: str or pathlib.Path
        Distinct legacy figure archive carrying explicit subplot metadata.
    figure_root: str or pathlib.Path
        Managed destination figure root.
    data_root: str or pathlib.Path
        Managed numerical-product root for recorded source links.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    report: dict
        Imported/flagged comparisons after writing managed links, sidecars, and the HTML
        integration manifest. Incomplete or inconsistent identities are flagged rather
        than inferred.

    Notes
    -----
    Reuse exact recorded megaplots/contexts; no FFTs, filtering, or model solves.

    Legacy images without complete explicit navigation are reported, never
    promoted using inferred numerical or filtering identities.
    '''
    # Integrate exact recorded megaplots and launch contexts without recomputing
    # scientific arrays
    figure_root=canonical_figure_root(figure_root)
    legacy_root=Path(legacy_root).expanduser().resolve()
    if legacy_root==figure_root:
        raise ValueError('Legacy figure input resolves to the active Figures tree; select the recorded legacy archive.')
    import comparison_gallery as gallery
    from dopplergram_recalculation import resolve_input_reference
    from komega_bokeh_context import validate_context
    import migrate_geometry_outputs as migration
    migration.DATA_ROOT, migration.FIGURE_ROOT = Path(data_root).resolve(), Path(figure_root).resolve()
    data_index = _canonical_index(data_root)
    figure_index = _canonical_index(figure_root)
    report = dict(imported=[], flagged=[])
    for plot in gallery.discover_comparison_plots(legacy_root):
        sidecar = paths.find_json_sidecar(plot.path, '.subplots.json')
        if not sidecar.is_file():
            report['flagged'].append(dict(source=str(plot.path), reason='No explicit subplot metadata.'))
            continue
        record = json.loads(sidecar.read_text())
        parts = gallery._parse_comparison_plot_name(plot)
        if not record.get('all_axes') or parts is None:
            report['flagged'].append(dict(source=str(plot.path), reason='Incomplete explicit comparison identity.'))
            continue
        # Validate every launch before publishing any HTML for this megaplot.
        targets = copy.deepcopy(record['targets'])
        configs, identities = [], {}
        try:
            for target in targets:
                launch = target.get('bokeh', {}).get('workspace')
                if not launch:
                    continue
                observation = validate_context(launch['context'])
                source = observation.files[0]
                reference = resolve_input_reference(source, config_file, observable=parts.observable)
                reference = copy.deepcopy(reference)
                reference.setdefault('time_distance', {})['xcorr_geometry'] = plot.xcorr_geometry
                cfg = migration.migration_config(reference, source, plot.path)
                cfg['time_distance']['xcorr_geometry'] = plot.xcorr_geometry
                # Explicit direction is part of the processing identity.
                paths.build_runtime_output_paths(cfg, data_root, figure_root, create=False)
                identity = cfg['_output_context']['identity']
                identity['implementation'] = {'status': 'recorded historical implementation'}
                cfg['_output_context']['run_id'] = paths.digest(identity)
                canonical = data_index.get(str(source.resolve()))
                existing_reference = None if canonical is None else paths.find_json_sidecar(canonical, '.inputs.json')
                if canonical is None or not existing_reference.is_file() or json.loads(existing_reference.read_text()) != reference:
                    canonical = paths.build_output_file(data_root, cfg, 'komega_diagram',
                        'html_source_' + paths.digest(str(source.resolve()))[:24] + '_komega.fits')
                    paths._ensure_link(canonical, source)
                    paths.atomic_json(paths.json_sidecar_path(canonical, '.inputs.json'), reference)
                    atmosphere = paths.find_json_sidecar(source, '.atmosphere.json')
                    if atmosphere.is_file():
                        paths._ensure_link(paths.json_sidecar_path(canonical, '.atmosphere.json'), atmosphere)
                    paths.register_output(canonical, cfg, 'komega_diagram', root=data_root,
                        extra={'migration_source': str(source), 'html_context_source': str(plot.path)}, checksum=False)
                value = copy.deepcopy(launch['context'])
                # Symlink-aware dataset IDs remain identical; the visible file
                # reference points into the managed Data tree.
                value['dataset']['file'] = str(canonical)
                links = _processing_context(value, reference, cfg)
                target['bokeh'] = links
                configs.append(cfg)
                key = paths.terminal_directory(identity).as_posix() + '/' + identity['geometry']['pair']
                identities[key] = identity
            if not configs:
                raise ValueError('No exact numerical Bokeh context was recorded.')
            scope_keys = {(c['data']['source_type'], paths.resolve_output_observable(c),
                           paths.resolve_output_geometry(c), tuple(paths.height_geometry(c)['labels'])) for c in configs}
            if len(scope_keys) != 1:
                raise ValueError('Megaplot combines different observables, directions, or ordered height pairs.')
            anchor = sorted(identities)[0]
            shared = shared_support_directory(figure_root, identities[anchor])
            source_image = link_asset(plot.path, shared/'megaplots',project=figure_project_root(figure_root))
            for target in targets:
                if target.get('missing') or target.get('crop') or not target.get('sourceFile'):
                    target['sourceFile'] = str(source_image)
                    continue
                source = resolve_legacy_figure_source(target['sourceFile'],figure_project_root(figure_root))
                target['sourceFile'] = str(figure_index.get(str(source.resolve())) or link_asset(source, shared/'source_figures',project=figure_project_root(figure_root)))
                for row in target.get('comparisonRows', []):
                    source = Path(row.get('sourcePath', row.get('src', '')))
                    if not source.is_absolute():
                        source = Path(legacy_root) / source
                    source=resolve_legacy_figure_source(source,figure_project_root(figure_root))
                    row['sourceFile'] = str(figure_index.get(str(source.resolve())) or link_asset(source, shared/'source_figures',project=figure_project_root(figure_root)))
            record.update(targets=targets, html_scope=dict(
                source_type=configs[0]['data']['source_type'], observable=paths.resolve_output_observable(configs[0]),
                geometry=paths.resolve_output_geometry(configs[0]), height_pair=paths.height_geometry(configs[0]),
                identities=list(identities.values())), legacy_source=str(plot.path))
            paths.atomic_json(paths.json_sidecar_path(source_image, '.subplots.json'), record)
            report['imported'].append(dict(source=str(plot.path), destination=str(source_image), scopes=list(identities)))
        except (ValueError, KeyError, OSError) as exc:
            report['flagged'].append(dict(source=str(plot.path), reason=str(exc)))
    paths.atomic_json(paths.json_output_path(Path(figure_root)/'html_integration_manifest.json'), report)
    return report


def _comparison_search_root(root, scope):
    '''
    Purpose
    -------
    Restrict an optional HTML scope to the managed figure tree.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    scope: str or pathlib.Path or None
        Optional relative subtree restricting this operation.

    Outputs
    -------
    search: pathlib.Path
        Root or resolved scoped subtree; escaping the root raises ValueError.
    '''

    # Restrict an optional HTML scope to the managed figure tree
    search=root if scope is None else (root/Path(scope)).resolve()
    if not search.is_relative_to(root):
        raise ValueError('HTML scope must lie inside the managed figure root.')
    return search


def _require_recorded_megaplots(search):
    '''
    Purpose
    -------
    Require recorded comparison images before regenerating their entry pages.

    Inputs
    ------
    search: pathlib.Path
        Managed subtree scanned for explicit subplot sidecars.

    Outputs
    -------
    None
        Raises FileNotFoundError when a recorded recognized comparison has no available
        image product.

    Notes
    -----
    Do not overwrite working entry pages when recorded images disappear.
    '''
    # Require recorded comparison images before regenerating their entry pages
    import comparison_gallery as gallery
    for sidecar in search.rglob('*.subplots.json'):
        if sidecar.is_symlink() or any(p.startswith('delta_z_') for p in sidecar.parts):
            continue
        record=json.loads(sidecar.read_text())
        if record.get('comparison_type') not in gallery.COMPARISON_VIEWERS:
            continue
        candidates=[paths.product_from_json_sidecar(sidecar, suffix)
                    for suffix in gallery.IMAGE_EXTENSIONS]
        if not any(p.is_file() for p in candidates):
            raise FileNotFoundError('Recorded megaplot image is unavailable; HTML was not regenerated: '+str(candidates[0]))


def scoped_comparison_groups(root, *, scope=None):
    '''
    Purpose
    -------
    Group recorded megaplots by their validated category and ordered-height-pair HTML
    scope.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    scope: str or pathlib.Path or None
        Optional relative subtree restricting this operation.

    Outputs
    -------
    groups: dict
        HTML directories mapped to comparison plots; missing or mixed scope metadata
        raises ValueError.

    Notes
    -----
    Group recorded megaplots by canonical category/ordered-pair HTML scope.
    '''
    # Group recorded megaplots by their validated category and ordered-height-pair HTML
    # scope
    root=canonical_figure_root(root)
    search=_comparison_search_root(root, scope)
    _require_recorded_megaplots(search)
    import comparison_gallery as gallery
    groups = {}
    for plot in gallery.discover_comparison_plots(search):
        record = json.loads(paths.find_json_sidecar(plot.path, '.subplots.json').read_text())
        scope = record.get('html_scope')
        if scope is None:
            raise ValueError(f'Comparison lacks explicit HTML scope: {plot.path}')
        configurations = {(identity['source_type'], identity['observable'], identity['organization_prefix'],
                           identity['geometry']['pair']) for identity in scope['identities']}
        if len(configurations) != 1:
            raise ValueError(f'Comparison mixes unrelated HTML configurations: {plot.path}')
        for identity in scope['identities']:
            directory = html_directory(root, identity)
            groups.setdefault(directory, []).append(plot)
    return groups


def megaplot_html_directory(root, identity):
    '''
    Purpose
    -------
    Resolve the three aggregate galleries directly under the observable/direction HTML
    directory.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    identity: dict
        Recorded output identity supplying organization_prefix.

    Outputs
    -------
    directory: pathlib.Path
        Canonical root/organization-prefix/HTML path.

    Notes
    -----
    The three mega galleries belong directly to the observable/direction.
    '''
    # Resolve the three aggregate galleries directly under the observable/direction HTML
    # directory
    return canonical_figure_root(root) / identity['organization_prefix'] / 'HTML'


def write_scoped_comparison_viewers(root, *, scope=None):
    '''
    Purpose
    -------
    Publish aggregate comparison galleries from validated explicit pair scopes.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    scope: str or pathlib.Path or None
        Optional relative subtree restricting this operation.

    Outputs
    -------
    outputs: dict
        Gallery directory to viewer-kind/output mappings; shared megaplots are published
        once and linked from their recorded scopes.
    '''

    # Publish aggregate comparison galleries from validated explicit pair scopes
    root=canonical_figure_root(root)
    import comparison_gallery as gallery
    # Validate each recorded pair scope before aggregating the mega galleries.
    scoped=scoped_comparison_groups(root, scope=scope)
    # Category entry points can reference one shared megaplot. Publish it once,
    # retaining the observable/direction prefix from its recorded identity.
    unique={plot.path:plot for group in scoped.values() for plot in group}
    groups, view_directories = {}, {}
    for plot in unique.values():
        record = json.loads(paths.find_json_sidecar(plot.path, '.subplots.json').read_text())
        identity = record['html_scope']['identities'][0]
        directory = megaplot_html_directory(root, identity)
        groups.setdefault(directory, []).append(plot)
        view_directories[plot.path] = shared_support_directory(root, identity)
    outputs, published_views = {}, {}
    for directory, plots in sorted(groups.items()):
        pairs = gallery.comparison_height_pairs(plots)
        outputs[str(directory)] = {kind: gallery.write_comparison_viewer(root, kind, plots, pairs,
            html_dir=directory, support_dir=support_directory(directory),
            view_directories=view_directories, published_views=published_views)
            for kind in gallery.COMPARISON_VIEWERS}
    return outputs


def refresh_managed_contexts(root, config_file, *, check_only=False, refresh_atmosphere=False, scope=None):
    '''
    Purpose
    -------
    Validate exact managed launch contexts and optionally refresh native atmosphere
    metadata.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    check_only: bool
        Validate and report without applying the optional refresh operation.
    refresh_atmosphere: bool
        Regenerate native single-cube atmospheric defaults when True and check_only is
        False.
    scope: str or pathlib.Path or None
        Optional relative subtree restricting this operation.

    Outputs
    -------
    report: dict
        Validated-context count and effective atmosphere-refresh flag; enabled refresh
        writes updated subplot and atmosphere sidecars.

    Notes
    -----
    Validate exact contexts, optionally refreshing native atmospheric defaults.
    '''
    # Validate exact managed launch contexts and optionally refresh native atmosphere
    # metadata
    import comparison_gallery as gallery
    from komega_bokeh_context import validate_context, with_atmosphere, launch_links
    count = 0
    search=_comparison_search_root(canonical_figure_root(root), scope)
    for plot in gallery.discover_comparison_plots(search):
        sidecar = paths.find_json_sidecar(plot.path, '.subplots.json')
        record = json.loads(sidecar.read_text())
        for target in record['targets']:
            launch = target.get('bokeh', {}).get('workspace')
            if launch is None:
                continue
            observation = validate_context(launch['context'])
            count += 1
            if refresh_atmosphere and not check_only and launch['context']['dataset']['source_type'] == 'single_cube':
                from dopplergram_recalculation import runtime_config
                from atmospheric_profiles import write_sidecar
                reference = launch['context']['processing']['input_reference']
                cfg = runtime_config(reference, config_file)
                value = with_atmosphere(launch['context'], cfg)
                target['bokeh'] = launch_links(value)
                write_sidecar(observation.files[0], value['atmosphere'])
        if refresh_atmosphere and not check_only:
            paths.atomic_json(sidecar, record)
    return {'validated_launch_contexts': count, 'refreshed_atmospheres': refresh_atmosphere and not check_only}


def relocate_observation_directories(root):
    '''
    Purpose
    -------
    Insert the Doppler-velocity quantity layer while retaining file bytes and link
    targets.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    count: int
        Number of moved entries; destination conflicts or broken source links raise
        before the moves. Rebuilds symlinks and removes empty legacy directories.

    Notes
    -----
    Insert the observational quantity layer, preserving bytes and link targets.
    '''
    # Insert the Doppler-velocity quantity layer while retaining file bytes and link
    # targets
    import os
    root = Path(root).absolute()
    moves = {}
    for direction in paths.XCORR_GEOMETRIES:
        old = root/'observations'/direction.title()
        if not old.is_dir():
            continue
        for source in old.rglob('*'):
            if source.is_file() or source.is_symlink():
                moves[source] = root/'observations'/'doppler_velocity'/direction.title()/source.relative_to(old)
    # Record original symlink targets and reject conflicts before moving any entries
    links = {old: Path(os.path.abspath(old.parent/os.readlink(old)))
             for old in moves if old.is_symlink()}
    for old, new in moves.items():
        if new.exists() or new.is_symlink():
            raise FileExistsError(f'Observation relocation would overwrite {new}')
        if old in links and not old.exists():
            raise FileNotFoundError(f'Observation relocation found an unavailable link: {old}')
        new.parent.mkdir(parents=True, exist_ok=True)
    # Move ordinary files and rebuild relative links against their relocated targets
    for old, new in moves.items():
        if old not in links:
            old.rename(new)
    for old, target in links.items():
        new = moves[old]
        new.symlink_to(os.path.relpath(moves.get(target, target), new.parent))
        old.unlink()
    # Verify rebuilt links before removing empty legacy directories
    for old in links:
        assert moves[old].exists(), moves[old]
    for direction in paths.XCORR_GEOMETRIES:
        old = root/'observations'/direction.title()
        if old.is_dir():
            for folder in sorted((p for p in old.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                if not any(folder.iterdir()): folder.rmdir()
            if not any(old.iterdir()): old.rmdir()
    return len(moves)


def main():
    '''
    Purpose
    -------
    Parse HTML integration options and publish scoped managed comparison galleries.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv, relocates historical observational quantity folders, optionally
        imports legacy comparisons, and writes aggregate HTML viewers.
    '''

    # Parse HTML integration options and publish scoped managed comparison galleries
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figures', type=Path, default=Path(__file__).resolve().parents[2]/'Figures')
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parents[2]/'Data')
    parser.add_argument('--legacy-figures', type=Path)
    parser.add_argument('--scope', type=Path, help='Managed source/observable/direction, e.g. simulations/v3/Annulus')
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.py'))
    args = parser.parse_args()
    args.figures=canonical_figure_root(args.figures)
    for root in (args.figures, args.data):
        relocated = relocate_observation_directories(root)
        if relocated: print(f'Relocated {relocated} observational entries under the quantity layer in {root}', flush=True)
    if args.legacy_figures:
        report = import_legacy_comparisons(args.legacy_figures, args.figures, args.data, args.config)
        print(f"Imported {len(report['imported'])}; flagged {len(report['flagged'])} comparisons", flush=True)
    outputs = write_scoped_comparison_viewers(args.figures, scope=args.scope)
    print(f'Generated {3*len(outputs)} galleries in {len(outputs)} configuration scopes', flush=True)


if __name__ == '__main__':
    main()
