'''
Purpose
-------
Prepare aligned native Dopplergrams and magnetic maps, then publish source-validated
magnetic-filter processing results.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for magnetogram_workflow.py.

Notes
-----
Native observation/simulation processing, independent of Bokeh widgets.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import copy
import math

import numpy as np
from astropy.io import fits

import pipeline
from gaussian_filter_explorer import CONFIG_FILE
from komega_plot_export import json_value
from observation_datasets import (_identifier, configuration,
                                  discover_observations)
from processing_results import (DEFAULT_RESULT_CACHE, ResultError, ResultStore,
                                fingerprint, result_key)


@dataclass(frozen=True)
class DopplerDataset:
    '''
    Purpose
    -------
    Describe one original observational pair or simulation cube before loading its
    arrays.

    Inputs
    ------
    id: str
        Canonical raw dataset identifier.
    label: str
        Human-readable dataset selection label.
    source_type: str
        paired_cubes or single_cube.
    files: tuple of pathlib.Path
        Ordered original input files.
    inputs: dict
        Mode-specific default sampling, field, or height selections.

    Outputs
    -------
    dataset: DopplerDataset
        Frozen selection identity, ordered files, source mode, and editable input
        defaults.
    '''

    id: str
    label: str
    source_type: str
    files: tuple
    inputs: dict


@lru_cache(maxsize=4)
def filter_class():
    '''
    Purpose
    -------
    Load and cache the native AGW filter class from the configured source module.

    Inputs
    ------
    None

    Outputs
    -------
    filter_class: type
        Pipeline-resolved AGWFilter implementation, cached for reuse.
    '''

    # Load and cache the native AGW filter class from the configured source module
    return pipeline.load_agw_filter_class(CONFIG_FILE)


def discover_dopplergrams(*, config_file=CONFIG_FILE, raw_roots=None, simulation_roots=None):
    '''
    Purpose
    -------
    Discover original observational pairs and eligible NetCDF simulation cubes.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    raw_roots: iterable of path-like or None
        Observational roots forwarded to deterministic raw-pair discovery.
    simulation_roots: iterable of path-like or None
        Simulation trees/files; None also includes configured defaults and batch inputs.

    Outputs
    -------
    datasets: list of DopplerDataset
        Stable sorted native-input choices with copied mode-specific defaults.
    '''

    # Discover original observational pairs and eligible NetCDF simulation cubes
    module = configuration(str(Path(config_file).resolve()))
    records = []
    for item in discover_observations(config_file=config_file, product_roots=[], raw_roots=raw_roots):
        inputs = copy.deepcopy(module.paired_cubes_inputs)
        inputs.update(v1_path=str(item.files[0]), v2_path=str(item.files[1]))
        records.append(DopplerDataset(item.id, item.label, 'paired_cubes', item.files,
                                     inputs))
    defaults = copy.deepcopy(module.single_cube_inputs)
    candidates = set()
    if simulation_roots is None:
        candidates.add(Path(defaults['file_path']).expanduser().resolve())
        candidates.update(Path(p).expanduser().resolve() for p in
            module.batch_config.get('single_netcdf_cube', {}).get('input_paths', []))
    roots = simulation_roots if simulation_roots is not None else [module.co5bold_batch_root]
    for root in roots:
        root = Path(root).expanduser().resolve()
        candidates.update(root.rglob('*.nc') if root.is_dir() else [root])
    for path in sorted(candidates):
        if path.is_file() and path.suffix.lower() == '.nc':
            identity = _identifier('raw_simulation', (path,), Path(module.project_dir))
            inputs = dict(defaults, file_path=str(path))
            records.append(DopplerDataset(identity, 'Simulation / ' + path.name + ' — ' + str(path.parent),
                                          'single_cube', (path,), inputs))
    return sorted(records, key=lambda item: (item.source_type, item.label.casefold()))


def validate_parameters(parameters):
    '''
    Purpose
    -------
    Validate magnetic selection, threshold, replacement value, and sampling mode.

    Inputs
    ------
    parameters: dict
        selection, threshold_G, fill_value, mode, and optional observable settings.

    Outputs
    -------
    parameters: dict
        Normalized magnetic/nonmagnetic selection, gauss threshold, mode, optional
        magnetic observable, and fill value with NaN represented as text. Invalid
        domains raise ValueError.
    '''

    # Validate magnetic selection, threshold, replacement value, and sampling mode
    required = {'selection', 'threshold_G', 'fill_value', 'mode'}
    if not required.issubset(parameters) or set(parameters) - required - {'observable'}:
        raise ValueError('Specify selection, threshold_G, fill_value and mode.')
    selection = str(parameters['selection']).lower()
    mode = str(parameters['mode'])
    threshold = float(parameters['threshold_G'])
    fill = float(parameters['fill_value'])
    if selection not in {'magnetic', 'nonmagnetic'}:
        raise ValueError('Select magnetic or nonmagnetic pixels.')
    if mode not in {'dataset', 'bottom', 'per_height_pair'}:
        raise ValueError('Unsupported magnetogram sampling mode.')
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError('Magnetic threshold must be finite and nonnegative, in Gauss.')
    if math.isinf(fill):
        raise ValueError('Replacement value must be finite or NaN.')
    observable = str(parameters.get('observable', '')).strip()
    if observable and not filter_class().is_netcdf_magnetic_variable_name(observable):
        raise ValueError('Choose a magnetic-field variable (e.g. bb3) or leave it blank for native automatic selection.')
    return dict(selection=selection, mode=mode, threshold_G=threshold, observable=observable,
                fill_value='NaN' if math.isnan(fill) else fill)


def defaults(config_file, source_type):
    '''
    Purpose
    -------
    Resolve and validate mode-specific native magnetic-filter defaults.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    source_type: str
        paired_cubes or single_cube source mode.

    Outputs
    -------
    parameters: dict
        Validated magnetic defaults; observations use dataset mode and automatic field
        selection.
    '''

    # Resolve and validate mode-specific native magnetic-filter defaults
    module = configuration(str(Path(config_file).resolve()))
    values = module.default_filtering['magnetogram']
    return validate_parameters(dict(selection=values['selection'], threshold_G=values['threshold_G'],
        fill_value=values['fill_value'], mode='dataset' if source_type == 'paired_cubes'
        else module.magnetogram_mode['single_cube'],
        observable='' if source_type == 'paired_cubes' else values.get('observable', values.get('cube_variable', ''))))


def _algorithms(config):
    '''
    Purpose
    -------
    Record numerical implementation and calibration checksums for processing-result
    identities.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    algorithms: dict
        Version, NumPy version, and source/calibration file SHA-256 values;
        documentation edits can change these source hashes.
    '''

    # Record numerical implementation and calibration checksums for processing-result
    # identities
    directory = Path(__file__).resolve().parent
    paths = [directory / name for name in ('filter.py', 'pipeline.py', 'magnetogram_workflow.py', 'processing_results.py','dopplergram_recalculation.py')]
    reference = Path(config['_module_dir'])
    paths.extend(p for p in (reference/'Oana_codes/AGWs_config.ini', reference/'Oana Codes/AGWs_config.ini')
                 if p.is_file())
    return {'version': 1, 'numpy': np.__version__,
            'code_sha256': {str(p): fingerprint(p)['sha256'] for p in paths}}


def runtime_config(dataset, inputs, mode, config_file):
    '''
    Purpose
    -------
    Build a checked manual-mode runtime for one original dataset and sampling choice.

    Inputs
    ------
    dataset: DopplerDataset
        Original dataset choice.
    inputs: dict
        Observational cadence/pixel scale/separation or simulation observable/height
        indices.
    mode: str
        dataset for observations, bottom or per_height_pair for simulation magnetic
        sampling.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    config: dict
        Prepared runtime with Gaussian disabled and no active filter sequence; invalid
        mode/sampling/height selections raise ValueError.
    '''

    # Build a checked manual-mode runtime for one original dataset and sampling choice
    module = configuration(str(Path(config_file).resolve()))
    if dataset.source_type == 'paired_cubes':
        if mode != 'dataset':
            raise ValueError('Observations use their one aligned dataset HMImag cube.')
        for key in ('dt', 'p_dx_Mm', 'delta_z_km'):
            value = float(inputs[key])
            if not math.isfinite(value) or value < 0 or (key != 'delta_z_km' and value == 0):
                raise ValueError(f'Invalid observational {key}; use finite positive sampling and nonnegative separation.')
        config = module.get_config(source_type='paired_cubes', v1_path=str(dataset.files[0]),
            v2_path=str(dataset.files[1]), delta_z_km=inputs['delta_z_km'],
            p_dx_Mm=inputs['p_dx_Mm'], dt=inputs['dt'])
    elif dataset.source_type == 'single_cube':
        for key in ('h1', 'h2'):
            if isinstance(inputs[key], bool) or int(inputs[key]) != inputs[key] or inputs[key] < 0:
                raise ValueError('Simulation heights must be nonnegative integer indices.')
        config = module.get_config(source_type='single_cube', file_path=str(dataset.files[0]),
            observable=inputs['observable'], h1=inputs['h1'], h2=inputs['h2'],
            magnetogram_mode={'single_cube': mode})
    else:
        raise ValueError('Unsupported dataset type; expected paired_cubes or single_cube.')
    config['_module_dir'] = str(Path(config_file).resolve().parent)
    config['optimized_filtering'] = {'mode': 'manual'}
    config['filtering']['gaussian']['enabled'] = False
    config['filtering']['filter_sequence'] = []
    # No outputs or reference-model diagnostics are required to calculate phase.
    config['dispersion_curves']['mode'] = 'theory_based'
    config = pipeline.prepare_runtime_config(config)
    config['data']['orientation_validation_outfile'] = ''
    return config


def _coordinates(dataset, config, shape, paths):
    '''
    Purpose
    -------
    Resolve original physical coordinates and verify spatial registration where metadata
    permit.

    Inputs
    ------
    dataset: DopplerDataset
        Source type and original file paths.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    shape: tuple of int
        Required Dopplergram (nt, ny, nx) dimensions.
    paths: sequence of pathlib.Path
        Original source paths used for observational FITS alignment checks.

    Outputs
    -------
    coordinates, metadata: tuple of dict
        Native x/y coordinates in Mm and time in seconds, plus coordinate/source-unit
        provenance. Incompatible WCS or dimensions raise ValueError.
    '''

    # Resolve original physical coordinates and verify spatial registration where
    # metadata permit
    nt, ny, nx = shape
    dt, dx = config['time_distance']['dt'], config['time_distance']['p_dx_Mm']
    if dataset.source_type == 'single_cube':
        with pipeline.nc.Dataset(dataset.files[0]) as source:
            x = pipeline._convert_netcdf_length_array_to_Mm(pipeline._load_netcdf_coordinate(source['xc1']),
                                                          getattr(source['xc1'], 'units', ''), 'xc1')
            y = pipeline._convert_netcdf_length_array_to_Mm(pipeline._load_netcdf_coordinate(source['xc2']),
                                                          getattr(source['xc2'], 'units', ''), 'xc2')
            name = 'time' if 'time' in source.variables else 't'
            t = pipeline._convert_netcdf_time_array_to_seconds(pipeline._load_netcdf_coordinate(source[name]),
                                                             getattr(source[name], 'units', ''))
            unit = getattr(source[config['data']['observable']], 'units', 'native source units')
        description = 'Native NetCDF xc1/xc2/time coordinates, converted using pipeline unit conventions'
    else:
        headers = [fits.getheader(path) for path in paths if path.suffix.lower() in {'.fits', '.fit', '.fts'}]
        # Native observational inputs must already be aligned. Check any shared,
        # explicit spatial WCS rather than silently resizing or reprojecting them.
        if len(headers) == len(paths):
            keys = [f'{key}{axis}' for axis in (1, 2) for key in ('CRVAL', 'CRPIX', 'CDELT', 'CTYPE', 'CUNIT')]
            keys += [f'{key}{i}_{j}' for key in ('CD', 'PC') for i in (1, 2) for j in (1, 2)]
            for header in headers[1:]:
                for key in keys:
                    if key in headers[0] and key in header:
                        a, b = headers[0][key], header[key]
                        equal = str(a).strip() == str(b).strip() if isinstance(a, str) else np.isclose(a, b, rtol=1e-9, atol=1e-12)
                        if not equal:
                            raise ValueError(f'Observational spatial alignment mismatch in FITS {key}. Supply pre-aligned cubes.')
        unit = headers[0].get('BUNIT', 'native source units') if headers else 'native source units'
        x, y, t = np.arange(nx)*dx, np.arange(ny)*dx, np.arange(nt)*dt
        description = 'Relative pixel-center coordinates [Mm] and elapsed time [s]; configured observational sampling'
    if len(x) != nx or len(y) != ny or len(t) != nt or not all(np.all(np.isfinite(a)) for a in (x, y, t)):
        raise ValueError('Spatial/temporal coordinates do not match the Dopplergram dimensions.')
    return dict(x_mm=np.asarray(x), y_mm=np.asarray(y), time_seconds=np.asarray(t)), dict(description=description, dopplergram_units=unit)


def prepare_dataset(dataset, parameters, *, inputs=None, config_file=CONFIG_FILE,
                    cache_root=DEFAULT_RESULT_CACHE):
    '''
    Purpose
    -------
    Cache original Dopplergrams and mode-specific aligned magnetic maps independently of
    threshold selection.

    Inputs
    ------
    dataset: DopplerDataset
        Original observational pair or simulation cube selection.
    parameters: dict
        Validated magnetic settings used to choose mode and magnetic observable.
    inputs: dict or None
        Mode-specific input overrides; defaults to dataset.inputs.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    cache_root: str or pathlib.Path
        Content-addressed aligned-input/result cache directory.

    Outputs
    -------
    prepared, config: tuple
        Validated aligned-input ProcessingResult and resolved runtime configuration.
        Source changes, shape/registration mismatches, or unavailable magnetograms raise
        errors.

    Notes
    -----
    Cache unfiltered cubes and aligned, mode-specific magnetic maps independently.
    '''
    # Cache original Dopplergrams and mode-specific aligned magnetic maps independently
    # of threshold selection
    parameters = validate_parameters(parameters)
    inputs = dict(dataset.inputs if inputs is None else inputs)
    if dataset.source_type == 'paired_cubes':
        inputs.update(v1_path=str(dataset.files[0]), v2_path=str(dataset.files[1]))
    elif dataset.source_type == 'single_cube':
        inputs.update(file_path=str(dataset.files[0]))
    config = runtime_config(dataset, inputs, parameters['mode'], config_file)
    config['filtering']['magnetogram']['observable'] = parameters['observable']
    loader = filter_class()(config)
    paths = list(dataset.files)
    if dataset.source_type == 'paired_cubes':
        paths.append(Path(loader.find_paired_cubes_magnetogram(*dataset.files)))
    # Fingerprint all required cube and magnetogram inputs before building the cache
    # identity
    sources = [fingerprint(p) for p in paths]
    data = config['data']
    scientific = {key: data[key] for key in ('source_type', 'h1', 'h2', 'resolved_delta_z_km')}
    for key in ('observable', 'resolved_h1_km', 'resolved_h2_km'):
        if key in data:
            scientific[key] = data[key]
    scientific['sampling'] = {key: config['time_distance'][key] for key in ('dt', 'p_dx_Mm')}
    scientific['phase_order'] = pipeline.resolve_paired_cube_phase_delay_metadata(config, config['_module_dir'])
    scientific['magnetogram_mode'] = parameters['mode']
    scientific['magnetogram_observable'] = parameters['observable']
    identity = dict(stage='aligned_inputs', dataset_id=dataset.id, sources=sources,
                    scientific=scientific, algorithms=_algorithms(config))
    key = result_key(identity)
    store = ResultStore(cache_root)
    # Reuse a validated aligned-input result or serialize the complete native load
    with store.lock(key):
        try:
            return store.load(key), config
        except ResultError:
            pass
        # Load and standardize native magnetic maps before checking exact cube
        # registration
        v1, v2 = loader.load_dopplergrams()
        mag1, mag2, details = loader.standardize_magnetogram_pair(loader.load_magnetograms(), dataset.source_type)
        arrays = dict(original_v1=np.asarray(v1), original_v2=np.asarray(v2),
                      magnetogram_v1=np.asarray(mag1), magnetogram_v2=np.asarray(mag2))
        if v1.ndim != 3 or v1.shape != v2.shape or min(v1.shape) < 3:
            raise ValueError('Dopplergrams must have matching [t, y, x] cubes with at least three samples per axis.')
        if mag1.shape != v1.shape or mag2.shape != v2.shape:
            raise ValueError('Magnetogram/Dopplergram spatial or temporal alignment mismatch. '
                             'This pipeline requires pre-aligned cubes with identical [t, y, x] dimensions.')
        # Retain native coordinate/unit provenance and recheck sources before atomic
        # publication
        coordinates, coordinate_meta = _coordinates(dataset, config, v1.shape, paths)
        arrays.update(coordinates)
        if [fingerprint(p) for p in paths] != sources:
            raise ResultError('Source changed during loading; please retry.')
        details.update({key: value for key, value in loader.data.items()
                        if key.startswith('resolved_magnetogram') or key == 'magnetogram_cube_variable'})
        metadata = dict(dataset=dict(id=dataset.id, label=dataset.label, source_type=dataset.source_type,
                                     inputs=json_value(inputs)), alignment=json_value(details),
                        runtime_data=json_value(loader.data))
        metadata['coordinates'] = coordinate_meta
        return store.publish(identity, metadata, arrays), config


def compute_result(prepared, config, parameters, *, cache_root=DEFAULT_RESULT_CACHE):
    '''
    Purpose
    -------
    Apply the native magnetic masks to original cubes and recompute their native phase
    spectrum.

    Inputs
    ------
    prepared: ProcessingResult
        Aligned-input cache entry containing original cubes and registered magnetic
        maps.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    parameters: dict
        Magnetic selection, gauss threshold, fill value, mode, and optional observable.
    cache_root: str or pathlib.Path
        Content-addressed cache root used for the final processing result.

    Outputs
    -------
    result: ProcessingResult
        Cached or newly published filtered Dopplergrams, removed masks, degree-valued
        [k_h,nu] phase array, Mm^-1/mHz axes, and complete processing provenance.
        Changed inputs/settings or source versions raise errors.

    Notes
    -----
    Apply the native masks to original cubes, then recompute native k–ω phase.
    '''
    # Apply the native magnetic masks to original cubes and recompute their native phase
    # spectrum
    parameters = validate_parameters(parameters)
    scientific = prepared.manifest['identity']['scientific']
    if (parameters['mode'] != scientific['magnetogram_mode']
            or parameters['observable'] != scientific['magnetogram_observable']):
        raise ValueError('Sampling mode changed; reload the aligned magnetograms first.')
    for key in ('source_type', 'h1', 'h2', 'resolved_delta_z_km', 'observable', 'resolved_h1_km', 'resolved_h2_km'):
        expected, actual = scientific.get(key), config['data'].get(key)
        if key == 'observable' and key in scientific:
            normalize = filter_class()(config).normalize_netcdf_observable_name
            expected, actual = normalize(expected), normalize(actual)
        if key in scientific and expected != actual:
            raise ValueError('Scientific inputs changed; reload the aligned dataset before computing.')
    # Require the prepared scientific sampling and phase-delay convention to remain
    # unchanged
    sampling = {key: config['time_distance'][key] for key in ('dt', 'p_dx_Mm')}
    phase_order = pipeline.resolve_paired_cube_phase_delay_metadata(config, config['_module_dir'])
    if sampling != scientific['sampling'] or phase_order != scientific['phase_order']:
        raise ValueError('Sampling or phase metadata changed; reload the aligned dataset before computing.')
    # Give each validated magnetic parameter state its own content-addressed result
    # identity
    identity = dict(stage='processing_result', sources=prepared.manifest['identity']['sources'],
        prepared_result=prepared.id, dataset_type=config['data']['source_type'],
        parameters=parameters, algorithms=_algorithms(config))
    key = result_key(identity)
    store = ResultStore(cache_root)
    with store.lock(key):
        try:
            return store.load(key)
        except ResultError:
            pass
        if any(fingerprint(p['path']) != p for p in identity['sources']):
            raise ResultError('Source changed; select the dataset again before filtering.')
        config = copy.deepcopy(config)
        config['filtering']['magnetogram'] = dict(parameters, enabled=True)
        loader = filter_class()(config)
        arrays = prepared.arrays
        # Apply the native absolute-field selection to each original Dopplergram
        # independently
        masks = loader.compute_magnetogram_filter_masks(np.abs(arrays['magnetogram_v1']),
            np.abs(arrays['magnetogram_v2']), parameters['selection'], parameters['threshold_G'])
        v1, v2 = loader.apply_magnetogram_filter(arrays['original_v1'], arrays['original_v2'], masks=masks)
        # Recompute native lower/higher phase and verify its axes and observational
        # delay
        values, kh, nu, spectrum_meta = pipeline.TimeDistance(config).compute_komega_diagram(v1, v2)
        expected_delay = phase_order['phase_delay_seconds'] if config['data']['source_type'] == 'paired_cubes' else 0.
        if spectrum_meta['phase_delay_seconds'] != expected_delay:
            raise ResultError('Phase metadata changed during calculation; reload the dataset.')
        if values.shape != (len(kh), len(nu)):
            raise ValueError('Pipeline k–ω output dimensions do not match its coordinate axes.')
        # Publish filtered arrays with the complete original-input and
        # magnetic-processing chain
        stage = dict(operation='magnetogram', algorithm='AGWFilter.apply_magnetogram_filter',
                     dataset_type=config['data']['source_type'], parameters=parameters,
                     sources=identity['sources'], alignment=prepared.manifest['metadata']['alignment'],
                     scientific=prepared.manifest['identity']['scientific'],
                     algorithms=identity['algorithms'], prepared_result=prepared.id)
        metadata = dict(dataset=prepared.manifest['metadata']['dataset'],
                        coordinates=prepared.manifest['metadata']['coordinates'],
                        processing_chain={'input': prepared.manifest['metadata']['dataset'], 'stages': [stage]},
                        komega=json_value({k: v for k, v in spectrum_meta.items() if k not in {'k_axis', 'nu_axis'}}),
                        sampling=dict(nx=v1.shape[2], ny=v1.shape[1], nt=v1.shape[0],
                            dt_seconds=config['time_distance']['dt'], dx_Mm=config['time_distance']['p_dx_Mm']))
        from dopplergram_recalculation import input_reference
        metadata['analysis_input'] = input_reference(config,provenance='Magnetogram tool native recalculation runtime')
        return store.publish(identity, metadata, dict(dopplergram_v1=v1, dopplergram_v2=v2,
            removed_mask_v1=masks[0], removed_mask_v2=masks[1], komega=values, kh=kh, nu=nu))
