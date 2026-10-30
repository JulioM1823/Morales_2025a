'''
Purpose
-------
Publish and validate exact numerical plot-to-Bokeh contexts and recorded subplot
navigation.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for komega_bokeh_context.py.

Notes
-----
Explicit plot-to-Bokeh context, published with the numerical plot data.

The URL carries a versioned record, not a filename/label to reverse engineer.
Simulation averaging is delegated to the existing dispersion adapter.
'''
from __future__ import annotations
# Import the libraries and shared helpers used by this module
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode

import numpy as np
from astropy.io import fits

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SERVER_URL = 'http://127.0.0.1:5013'
PARAMETER_UNITS = {'a': 'km/s', 'cs': 'km/s', 'dz': 'km',
                   'theta_deg': 'deg', 'phi_deg': 'deg', 'N': 'rad/s', 'N2': 's^-2',
                   'wac': 'rad/s', 'H': 'km', 'gamma': 'dimensionless',
                   'g': 'km/s^2', 'tau': 's'}


def atmospheric_initializations(config, atmosphere, *, use_project_fallbacks=False):
    '''
    Purpose
    -------
    Bind available atmospheric values to every native model and disclose each fallback.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    atmosphere: dict
        Resolved atmospheric parameters, units, availability, and provenance.
    use_project_fallbacks: bool
        Use configured per-model project values before authoritative defaults when True.

    Outputs
    -------
    initializations, fallbacks: tuple of dict
        Per-model input dictionaries and missing-input provenance; fatal height
        inconsistencies raise ValueError.

    Notes
    -----
    Bind available physical inputs to each native model; disclose fallbacks.
    '''
    # Bind available atmospheric values to every native model and disclose each fallback
    if atmosphere.get('fatal'):
        raise ValueError('Inconsistent atmospheric height metadata: '+atmosphere['unavailable']['all'])
    from komega_explorer import load_dispersion_explorer
    vesa = load_dispersion_explorer(config['komega_comparison']['vesa_2026_dir'])
    from atmospheric_profiles import upgrade_atmosphere
    available = upgrade_atmosphere(atmosphere)['parameters']
    initializations, fallbacks = {}, {}
    for definition in vesa.MODEL_DEFINITIONS:
        values, missing = {}, {}
        project = config.get('komega_comparison', {}).get('models', {}).get(definition.key, {}).get('params', {}) if use_project_fallbacks else {}
        for item in definition.parameters:
            if item.key in available:
                values[item.key] = float(available[item.key])
            else:
                value = float(project[item.key] if item.key in project else
                              project['N']**2 if item.key == 'N2' and 'N' in project else item.default)
                values[item.key] = value
                reason = atmosphere['unavailable'].get(item.key,
                    atmosphere['unavailable'].get('all', 'Not supplied by these atmospheric profiles.'))
                missing[item.key] = dict(value=value, unit=PARAMETER_UNITS[item.key], reason=reason,
                                         source='existing project model setting' if item.key in project else 'authoritative Vesa model default')
        initializations[definition.key], fallbacks[definition.key] = values, missing
    return initializations, fallbacks


def with_atmosphere(context, config, atmosphere=None):
    '''
    Purpose
    -------
    Upgrade a launch context with portable atmospheric defaults and provenance.

    Inputs
    ------
    context: dict
        Existing numerical plot-to-Bokeh launch record.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    atmosphere: dict or None
        Explicit atmosphere record or None to resolve it from config.

    Outputs
    -------
    context: dict
        Deep-copied schema-version-2 launch record, or the original context when no
        atmosphere is available; fatal height inconsistency raises ValueError.

    Notes
    -----
    Upgrade a launch record, embedding scalar defaults/provenance for portability.
    '''
    # Upgrade a launch context with portable atmospheric defaults and provenance
    import copy
    from atmospheric_profiles import resolve_parameters
    atmosphere = resolve_parameters(config) if atmosphere is None else atmosphere
    if atmosphere is None:
        return context
    if atmosphere.get('fatal'):
        raise ValueError('Inconsistent atmospheric height metadata: '+atmosphere['unavailable']['all'])
    context = copy.deepcopy(context)
    from atmospheric_profiles import upgrade_atmosphere
    atmosphere = upgrade_atmosphere(atmosphere)
    values, fallbacks = atmospheric_initializations(config, atmosphere)
    atmosphere = copy.deepcopy(atmosphere)
    atmosphere['initializations'], atmosphere['fallbacks'] = values, fallbacks
    context.update(schema_version=2, atmosphere=atmosphere)
    context['model'].update(parameters=values['nc2009'],
        units={key: PARAMETER_UNITS[key] for key in values['nc2009']})
    return context


def context_path(image_path):
    '''
    Purpose
    -------
    Locate the current or historical Bokeh-context sidecar for an image.

    Inputs
    ------
    image_path: str or pathlib.Path
        Figure image whose numerical launch context is described.

    Outputs
    -------
    path: pathlib.Path
        Existing preferred or expected .bokeh.json sidecar.
    '''

    # Locate the current or historical Bokeh-context sidecar for an image
    return find_json_sidecar(image_path, '.bokeh.json')


def navigation_path(image_path):
    '''
    Purpose
    -------
    Locate the current or historical subplot-navigation sidecar for an image.

    Inputs
    ------
    image_path: str or pathlib.Path
        Comparison figure whose subplot navigation is described.

    Outputs
    -------
    path: pathlib.Path
        Existing preferred or expected .subplots.json sidecar.
    '''

    # Locate the current or historical subplot-navigation sidecar for an image
    return find_json_sidecar(image_path, '.subplots.json')


def _write_json(path, value):
    '''
    Purpose
    -------
    Write a managed JSON companion through synchronized atomic replacement.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    value: JSON-serializable object
        Context or navigation metadata to persist.

    Outputs
    -------
    None
        Creates json_files parents, rejects nonfinite JSON literals, replaces the
        destination, and cleans temporary files.
    '''

    # Write a managed JSON companion through synchronized atomic replacement
    path = json_output_path(path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def simulation_parameters(config, metadata):
    '''
    Purpose
    -------
    Resolve explicit simulation height-pair averages without using demonstration
    fallbacks.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    metadata: dict
        Native layer or between-height average metadata associated with the displayed
        phase spectrum.

    Outputs
    -------
    parameters: dict
        Alfven speed and optional sound speed in km/s, inclination/azimuth in degrees,
        and separation in km; missing recorded averages raise ValueError.
    '''

    # Resolve explicit simulation height-pair averages without using demonstration
    # fallbacks
    from dispersion_comparison import resolve_height_pair_context
    layer_metadata = metadata.get('dispersion_height_pair', metadata)
    has_layers = ('a_by_height_km_s' in layer_metadata or
                  {'a_h1_km_s', 'a_h2_km_s'} <= set(layer_metadata))
    if has_layers:
        pair = resolve_height_pair_context(config, metadata, allow_standalone_fallback=False)
    else:
        # Older products export the between-height atmosphere average CAAVG.
        # Use that explicit average, never the standalone demonstration values.
        import copy
        legacy = copy.deepcopy(metadata)
        legacy['a_km_s'] = metadata.get('a_km_s', metadata.get('alfven_speed_km_s'))
        strict_config = copy.deepcopy(config)
        strict_config.setdefault('komega_comparison', {})['standalone_pair'] = {}
        pair = resolve_height_pair_context(strict_config, legacy, allow_standalone_fallback=True)
        if pair['standalone_fallback_used']:
            raise ValueError('Simulation averages are missing from this plot’s metadata.')
    parameters = {'a': pair['a_km_s'], 'theta_deg': pair['theta_deg'],
                  'phi_deg': pair['phi_deg'], 'dz': pair['dz_km']}
    # Sound speed is a separate atmosphere average, already exported by pipeline.
    sound_speed = metadata.get('mean_sound_speed_km_s_between_heights')
    if sound_speed is None:
        sound_speed = metadata.get('alfven_sound_ratio', {}).get('mean_sound_speed_km_s_between_heights')
    if sound_speed is not None and np.isfinite(sound_speed) and float(sound_speed) > 0:
        parameters['cs'] = float(sound_speed)
    return parameters


def validate_context(value):
    '''
    Purpose
    -------
    Validate exact dataset identity, processing reference, model inputs, and atmospheric
    consistency.

    Inputs
    ------
    value: dict
        Schema-version-1 or -2 launch context decoded from a URL or sidecar.

    Outputs
    -------
    observation: Observation
        Canonical dataset reference, upgraded to recorded_input when the saved product
        is missing but explicit original provenance exists. Malformed/inconsistent
        contexts raise ValueError.
    '''

    # Validate exact dataset identity, processing reference, model inputs, and
    # atmospheric consistency
    if not isinstance(value, dict) or value.get('schema_version') not in {1, 2}:
        raise ValueError('Unsupported or malformed k–ω launch context.')
    dataset = value['dataset']
    if not isinstance(dataset, dict) or not isinstance(dataset.get('file'), str):
        raise ValueError('Launch context requires a numerical dataset file path.')
    source_type = dataset['source_type']
    if source_type not in {'paired_cubes', 'single_cube'}:
        raise ValueError('Unknown dataset source type in launch context.')
    from observation_datasets import dataset_from_fits
    path = Path(dataset['file']).expanduser()
    path = (PROJECT_DIR / path).absolute() if not path.is_absolute() else path.absolute()
    observation = dataset_from_fits(path, source_type, PROJECT_DIR)
    if dataset['id'] != observation.id:
        raise ValueError('Dataset ID and numerical source path disagree.')
    # Verify recorded processing flags, source type, direction, and optional live
    # sidecar equality
    processing = value.get('processing')
    if processing is not None:
        from output_paths import normalize_xcorr_geometry
        if not isinstance(processing, dict) or not isinstance(processing.get('input_reference'), dict):
            raise ValueError('Launch processing requires the recorded input reference.')
        reference = processing['input_reference']
        if reference.get('schema_version') != 1 or not isinstance(reference.get('filtering'), dict):
            raise ValueError('Invalid recorded processing reference.')
        for stage in (reference['filtering'], reference['filtering'].get('gaussian', {}),
                      reference['filtering'].get('magnetogram', {})):
            if 'enabled' in stage and type(stage['enabled']) is not bool:
                raise ValueError('Recorded filtering enabled flags must be booleans.')
        geometry = normalize_xcorr_geometry(processing.get('xcorr_geometry'))
        if reference.get('data', {}).get('source_type') != source_type:
            raise ValueError('Selected subplot source type disagrees with its input reference.')
        recorded_geometry = reference.get('time_distance', {}).get('xcorr_geometry')
        if recorded_geometry is not None and normalize_xcorr_geometry(recorded_geometry) != geometry:
            raise ValueError('Selected subplot direction disagrees with its input reference.')
        sidecar = find_json_sidecar(path, '.inputs.json')
        if sidecar.is_file() and json.loads(sidecar.read_text()) != reference:
            raise ValueError('Selected subplot processing no longer matches its numerical product.')
    # Require the exact comparison-model contract and its named physical values
    if not isinstance(value.get('model'), dict) or value['model'].get('key') != 'nc2009':
        raise ValueError('The comparison launch model must be 3MAG (nc2009).')
    parameters = value['model'].get('parameters', {})
    if not isinstance(parameters, dict):
        raise ValueError('Simulation model parameters must be named values.')
    if source_type == 'paired_cubes' and parameters:
        raise ValueError('Observational plots cannot supply simulation parameters.')
    if set(parameters) - set(PARAMETER_UNITS):
        raise ValueError('Unknown simulation model input in launch context.')
    # Check finite numeric model inputs and their supported physical domains
    for key, number in parameters.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f'Simulation parameter {key} must be numeric.')
        number = float(number)
        if not np.isfinite(number):
            raise ValueError(f'Nonfinite simulation parameter: {key}.')
        if (key in {'cs', 'H', 'tau', 'g'} and number <= 0) or (key in {'a', 'dz', 'N', 'wac'} and number < 0):
            raise ValueError(f'Invalid physical simulation parameter: {key}.')
        if (key == 'theta_deg' and not -180 <= number <= 180) or (key == 'phi_deg' and not -180 <= number <= 180):
            raise ValueError(f'Invalid simulation angle: {key}.')
    if source_type == 'single_cube' and not {'a', 'dz', 'theta_deg', 'phi_deg'} <= set(parameters):
        raise ValueError('Simulation launch context lacks height-pair averages.')
    # Require atmospheric defaults and selected physical heights to agree with model
    # initialization
    if value['schema_version'] == 2:
        atmosphere = value.get('atmosphere', {})
        if source_type != 'single_cube' or not isinstance(atmosphere.get('initializations'), dict):
            raise ValueError('Atmospheric launch context requires explicit simulation model initializations.')
        if atmosphere['initializations'].get('nc2009') != parameters:
            raise ValueError('Atmospheric defaults and launch model parameters disagree.')
        for model_key, inputs in atmosphere['initializations'].items():
            if not isinstance(inputs, dict) or any(key not in PARAMETER_UNITS or
                isinstance(number, bool) or not isinstance(number, (int, float)) or not np.isfinite(number)
                for key, number in inputs.items()):
                raise ValueError(f'Invalid atmospheric initialization for {model_key}.')
        if atmosphere.get('status') == 'available':
            heights = atmosphere.get('height_pair_km', [])
            if len(heights) != 2 or not np.isfinite(heights).all() or not np.isclose(
                    abs(heights[1]-heights[0]), parameters['dz'], rtol=1e-9, atol=1e-6):
                raise ValueError('Atmospheric heights and model separation disagree.')
    # Recover a missing optional phase product only through explicit original-input
    # provenance
    if not observation.files[0].is_file() and processing is not None:
        from observation_datasets import recorded_input_observation
        observation = recorded_input_observation(observation, processing['input_reference'], value.get('atmosphere'))
    return observation


def request_context(doc):
    '''
    Purpose
    -------
    Decode and validate an optional exact launch context from Bokeh request arguments.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.

    Outputs
    -------
    context: dict or None
        Validated decoded context, or None without a context argument; repeated or
        malformed context arguments raise errors.
    '''

    # Decode and validate an optional exact launch context from Bokeh request arguments
    session = doc.session_context
    arguments = {} if session is None else session.request.arguments
    encoded = arguments.get('context', [])
    if not encoded:
        return None
    if len(encoded) != 1:
        raise ValueError('Provide exactly one k–ω launch context.')
    value = json.loads(encoded[0].decode('utf-8') if isinstance(encoded[0], bytes) else encoded[0])
    validate_context(value)
    return value


def launch_links(context, server_url=DEFAULT_SERVER_URL):
    '''
    Purpose
    -------
    Construct one canonical integrated-workspace link for a validated exact context.

    Inputs
    ------
    context: dict
        Exact launch context validated before URL construction.
    server_url: str
        Bokeh service base URL, defaulting to the local configured origin.

    Outputs
    -------
    links: dict
        Workspace URL and original context encoded without nonfinite JSON values.

    Notes
    -----
    Publish one canonical integrated workspace for an exact plot context.
    '''
    # Construct one canonical integrated-workspace link for a validated exact context
    validate_context(context)
    query = urlencode({'context': json.dumps(context, separators=(',', ':'), allow_nan=False)})
    base = server_url.rstrip('/')
    return {'workspace': {
        'url': base + '/integrated_komega_bokeh_app?' + query,
        'context': context,
    }}


def publish_context(image_path, data, config):
    '''
    Purpose
    -------
    Publish the exact displayed numerical data and its portable launch/processing
    context.

    Inputs
    ------
    image_path: str or pathlib.Path
        Figure image receiving the launch sidecar.
    data: dict
        Displayed degree-valued phase array, kh/nu axes, numerical source path, and
        optional sampling/atmosphere metadata.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    record: dict
        Validated context and workspace links written to a Bokeh sidecar. Plot-only
        arrays are persisted separately when needed; input and atmospheric provenance
        are also published.

    Notes
    -----
    Publish the exact displayed array; preserve existing FITS IDs when possible.
    '''
    # Publish the exact displayed numerical data and its portable launch/processing
    # context
    from observation_datasets import dataset_from_fits
    image_path = Path(image_path).resolve()
    source = Path(data['data_file']).absolute()
    source_type = config['data']['source_type']
    metadata = data.get('orientation', {})
    from atmospheric_profiles import resolve_parameters, write_sidecar
    atmosphere = (data.get('atmospheric_parameters') or metadata.get('atmospheric_parameters')
                  or resolve_parameters(config)) if source_type == 'single_cube' else None
    parameters = ({} if atmosphere is not None else simulation_parameters(config, metadata)) if source_type == 'single_cube' else {}
    persisted_for_plot = data.get('computed_for_plot', False) or not source.is_file()
    if persisted_for_plot:
        # Plot-only unfiltered FFTs previously had no numerical file to open.
        # Persist them separately rather than substituting a filtered product.
        if '_output_context' in config:
            from output_paths import build_output_file
            source = build_output_file(config['paths']['data_output_dir'], config, 'komega_diagram',
                image_path.stem + '_komega.fits')
        else:
            source = image_path.parent / 'bokeh_datasets' / (image_path.stem + '_komega.fits')
        source.parent.mkdir(parents=True, exist_ok=True)
        kh, nu = np.asarray(data['k_axis']), np.asarray(data['nu_axis'])
        header = fits.Header(dict(SRCMODE=source_type, BUNIT='deg',
            CTYPE1='KH', CTYPE2='NU', CUNIT1='1/Mm', CUNIT2='mHz',
            CRVAL1=float(kh[0]), CDELT1=float(kh[1]-kh[0]),
            CRVAL2=float(nu[0]), CDELT2=float(nu[1]-nu[0]),
            DT_S=float(config['time_distance']['dt']), DX_MM=float(config['time_distance']['p_dx_Mm'])))
        cube_shape = data.get('cube_shape')
        if cube_shape is not None:
            header['NT_ORIG'], header['NY_ORIG'], header['NX_ORIG'] = map(int, cube_shape)
        fd, temporary = tempfile.mkstemp(dir=source.parent, suffix='.fits')
        os.close(fd)
        try:
            fits.writeto(temporary, np.asarray(data['values']), header, overwrite=True)
            with open(temporary, 'rb') as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, source)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if persisted_for_plot and '_output_context' in config:
        from output_paths import register_output
        register_output(source, config, 'komega_diagram', root=config['paths']['data_output_dir'])
    observation = dataset_from_fits(source, source_type, PROJECT_DIR)
    from dopplergram_recalculation import write_input_reference
    reference = write_input_reference(source, config)
    try:
        file_name = source.relative_to(PROJECT_DIR).as_posix()
    except ValueError:
        file_name = str(source)
    context = {'schema_version': 1,
        'dataset': {'id': observation.id, 'file': file_name, 'source_type': source_type},
        'model': {'key': 'nc2009', 'parameters': parameters,
                  'units': {key: PARAMETER_UNITS[key] for key in parameters}}}
    context['processing'] = {'input_reference': reference,
        'xcorr_geometry': config.get('time_distance', {}).get('xcorr_geometry', 'annulus'),
        'filter_configuration': config.get('filter_configuration', {'mode': 'manual'})}
    if atmosphere is not None:
        context = with_atmosphere(context, config, atmosphere)
        write_sidecar(source, context['atmosphere'])
    links = launch_links(context, config.get('komega_comparison', {}).get('bokeh_server_url', DEFAULT_SERVER_URL))
    record = {'context': context, 'links': links}
    _write_json(context_path(image_path), record)
    return record


def register_panel(axis, data, config):
    '''
    Purpose
    -------
    Attach explicit data and runtime context to a Matplotlib axis until its figure is
    saved.

    Inputs
    ------
    axis: matplotlib.axes.Axes
        Subplot carrying the exact numerical source/context.
    data: dict
        Displayed numerical phase data and provenance.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    None
        Stores (data, config) in axis._komega_bokeh_data.

    Notes
    -----
    Keep explicit data/context on an axis until its megaplot is saved.
    '''
    # Attach explicit data and runtime context to a Matplotlib axis until its figure is
    # saved
    axis._komega_bokeh_data = (data, config)


def publish_comparison_navigation(figure, image_path, pad_inches=0.18):
    '''
    Purpose
    -------
    Record actual saved subplot geometry and exact launch contexts without layout
    inference.

    Inputs
    ------
    figure: matplotlib.figure.Figure
        Drawn comparison figure whose visible axes are inspected.
    image_path: str or pathlib.Path or None
        Saved figure image used for exact pixel dimensions.
    pad_inches: float
        Tight-bounding-box export padding in inches, matching the saved figure.

    Outputs
    -------
    None
        Writes navigation sidecars and available standalone HTML/context pages; returns
        immediately when image_path is None.

    Notes
    -----
    Record actual axes geometry and context; no filename/layout inference.
    '''
    # Record actual saved subplot geometry and exact launch contexts without layout
    # inference
    if image_path is None:
        return
    from PIL import Image
    image_path = Path(image_path).resolve()
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    saved_bbox = figure.get_tightbbox(renderer).padded(pad_inches)
    with Image.open(image_path) as image:
        width, height = image.size

    def subplot_geometry(axis):
        '''
        Purpose
        -------
        Convert a subplot's saved-figure bounds into percentage and pixel crop
        coordinates.

        Inputs
        ------
        axis: matplotlib.axes.Axes
            Visible subplot measured against the enclosing saved figure bounds.

        Outputs
        -------
        bounds, crop: tuple of dict
            left/top/width/height in percentages and rounded image pixels.

        Notes
        -----
        Use the saved figure bounds for both plain and k–ω subplots.
        '''
        # Convert a subplot's saved-figure bounds into percentage and pixel crop
        # coordinates
        bbox = axis.get_window_extent(renderer).transformed(figure.dpi_scale_trans.inverted())
        bounds = {'left': 100*(bbox.x0-saved_bbox.x0)/saved_bbox.width,
                  'top': 100*(saved_bbox.y1-bbox.y1)/saved_bbox.height,
                  'width': 100*bbox.width/saved_bbox.width,
                  'height': 100*bbox.height/saved_bbox.height}
        crop = {key: round(value/100 * (width if key in {'left', 'width'} else height)) for key, value in bounds.items()}
        return bounds, crop

    targets = []
    for axis in figure.axes:
        # Colorbar axes belong to their image, rather than being subplots.
        # Disabled filter panels can intentionally contain only text, with the
        # axes switched off; they still need the same individual figure link.
        if not axis.get_visible() or hasattr(axis, '_colorbar'):
            continue
        panel = getattr(axis, '_komega_bokeh_data', None)
        if panel is None:
            if not axis.has_data() and not axis.texts and not axis.get_title():
                continue
            bounds, crop = subplot_geometry(axis)
            panel_id = sha256(json.dumps(bounds, sort_keys=True).encode()).hexdigest()[:20]
            label = axis.get_title() or axis.get_ylabel() or f'Subplot {len(targets) + 1}'
            targets.append({'id': 'subplot-' + panel_id, 'label': label, 'alt': label,
                'src': '../' + image_path.name, 'sourcePath': image_path.name,
                'sourceFile': str(image_path), 'crop': crop, 'bounds': bounds,
                'pixelBounds': crop, 'missing': False, 'panelKind': 'figure'})
            continue
        data, config = panel
        identity = sha256(str(data['data_file']).encode()).hexdigest()[:20]
        # Separate image contexts let repeated plots share the numerical FITS.
        plot_identity = sha256(str(image_path).encode()).hexdigest()[:16]
        asset = image_path.parent / 'komega_contexts' / (plot_identity + '_' + identity + '.jpeg')
        record = publish_context(asset, data, config)
        bounds, crop = subplot_geometry(axis)
        panel_id = sha256((identity + json.dumps(bounds, sort_keys=True)).encode()).hexdigest()[:20]
        target = {'id': 'dataset-' + panel_id + '-komega', 'label': Path(data['data_file']).name,
            'alt': Path(data['data_file']).name, 'src': '../' + image_path.name,
            'sourcePath': image_path.name, 'sourceFile': str(image_path),
            'crop': crop, 'bounds': bounds, 'pixelBounds': crop, 'missing': False,
            'panelKind': 'komega', 'bokeh': record['links']}
        # Keep full standalone images/dispersion rows when they already exist.
        from output_paths import mirror_hierarchy_from_data_file
        figure_root = config.get('paths', {}).get('figure_dir', image_path.parent)
        standalone = mirror_hierarchy_from_data_file(figure_root, data['data_file'],
                                                     Path(data['data_file']).stem + '.jpeg', create=False)
        if standalone.is_file():
            standalone_record = publish_context(standalone, data, config)
            write_standalone_html(standalone, standalone_record)
            target['sourceFile'] = str(standalone)
            target['crop'] = None
            from comparison_gallery import _load_komega_comparison_rows
            rows = _load_komega_comparison_rows(standalone, Path(figure_root))
            if rows:
                target['comparisonRows'] = rows
        targets.append(target)
    if targets:
        record = {'schema_version': 1, 'all_axes': True, 'targets': targets}
        comparison_type = getattr(figure, '_komega_comparison_type', None)
        if comparison_type:
            record['comparison_type'] = comparison_type
            data_config = next(axis._komega_bokeh_data[1] for axis in figure.axes
                               if hasattr(axis, '_komega_bokeh_data'))['data']
            record['height_pair_km'] = [data_config.get('resolved_h1_km'), data_config.get('resolved_h2_km')]
        panel_configs = [axis._komega_bokeh_data[1] for axis in figure.axes if hasattr(axis, '_komega_bokeh_data')]
        if panel_configs and all('_output_context' in cfg for cfg in panel_configs):
            from output_paths import _context, resolve_output_geometry, resolve_output_observable
            identities = [_context(cfg)['identity'] for cfg in panel_configs]
            record['html_scope'] = dict(source_type=panel_configs[0]['data']['source_type'],
                observable=resolve_output_observable(panel_configs[0]), geometry=resolve_output_geometry(panel_configs[0]),
                height_pair=identities[0]['geometry'], identities=identities)
        _write_json(navigation_path(image_path), record)


def write_standalone_html(image_path, record):
    '''
    Purpose
    -------
    Publish the shared standalone figure/launch template for one saved image.

    Inputs
    ------
    image_path: str or pathlib.Path
        Standalone source image.
    record: dict
        Published context record containing links.workspace.

    Outputs
    -------
    path: pathlib.Path
        Output from comparison_gallery.write_figure_page, carrying the recorded
        workspace link.

    Notes
    -----
    Use the same figure/launch template as every megaplot subplot.
    '''
    # Publish the shared standalone figure/launch template for one saved image
    from comparison_gallery import write_figure_page
    return write_figure_page(image_path, workspace=record['links']['workspace'], komega=True)
