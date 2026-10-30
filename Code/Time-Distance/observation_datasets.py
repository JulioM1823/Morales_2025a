'''
Purpose
-------
Discover and load saved phase products or explicitly referenced original
observational/simulation cubes.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for observation_datasets.py.

Notes
-----
Load observational/simulation FITS products and raw observational pairs.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path
import copy
import hashlib
import re
from data_locations import current_source_path, source_identity_path

import numpy as np
from astropy.io import fits

import pipeline
from gaussian_filter_explorer import CONFIG_FILE, PreviewGeometry

FITS_SUFFIXES = {'.fits', '.fit', '.fts'}
DATE_PATTERN = re.compile(r'\d{1,2}(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{4}', re.I)


@dataclass(frozen=True)
class Observation:
    '''
    Purpose
    -------
    Describe one canonical dataset selection without loading its arrays.

    Inputs
    ------
    id: str
        Canonical dataset identifier retaining original source identity labels.
    label: str
        Human-readable selection label.
    kind: str
        Dataset loader kind such as raw_pair, fits, simulation_fits, or recorded_input.
    files: tuple of pathlib.Path
        Ordered numerical product or original input paths.
    input_reference: dict or None
        Optional explicit recorded-input or processing-result metadata.

    Outputs
    -------
    observation: Observation
        Frozen dataset identity, label, source kind, files, and optional processing
        reference.
    '''

    id: str
    label: str
    kind: str
    files: tuple[Path, ...]
    input_reference: dict | None = None


@dataclass
class ObservationData:
    '''
    Purpose
    -------
    Hold the loaded phase spectrum, sampling, provenance, and optional original cubes.

    Inputs
    ------
    observation: Observation
        Selected dataset identity and files.
    values: np.ndarray
        Phase-difference array in degrees with shape (n_kh, n_nu).
    kh: np.ndarray
        One-dimensional horizontal-wavenumber axis in Mm^-1.
    nu: np.ndarray
        One-dimensional nonnegative frequency axis in mHz.
    geometry: PreviewGeometry
        Original cube nx/nt and cadence/pixel sampling.
    ny: int
        Original y sample count.
    metadata: dict
        Source fingerprints, processing provenance, sampling, and axis conventions.
    dopplergrams: tuple or None
        Optional two matching original/post-magnetogram cubes in (t, y, x) order.
    analysis_config: dict or None
        Resolved runtime configuration for native diagnostic recalculation.
    pre_gaussian_raw: tuple or None
        Optional raw cubes needed to preserve a Gaussian-before-magnetogram stage order.

    Outputs
    -------
    data: ObservationData
        Shared explorer input contract; phase values remain in project [k_h, nu] order.
    '''

    observation: Observation
    values: np.ndarray  # Project contract: [k_h, nu], despite FITS CTYPE ordering.
    kh: np.ndarray
    nu: np.ndarray
    geometry: PreviewGeometry
    ny: int
    metadata: dict
    dopplergrams: tuple | None = None
    analysis_config: dict | None = None
    pre_gaussian_raw: tuple | None = None


@lru_cache(maxsize=4)
def configuration(config_file: str):
    '''
    Purpose
    -------
    Load and cache the requested pipeline configuration module.

    Inputs
    ------
    config_file: str
        Configuration-module filename used as the memoization key.

    Outputs
    -------
    module: types.ModuleType
        Loaded configuration module, cached by its path string.
    '''

    # Load and cache the requested pipeline configuration module
    return pipeline.load_config_module(Path(config_file))


def _identifier(kind, files, project_dir):
    '''
    Purpose
    -------
    Build a stable dataset identifier from original path labels.

    Inputs
    ------
    kind: str
        Dataset-kind prefix.
    files: iterable of path-like
        Ordered product/input files.
    project_dir: pathlib.Path
        Project root used to make original labels relative when possible.

    Outputs
    -------
    identifier: str
        Kind-prefixed ordered relative or absolute source labels, using portable
        identity mappings when available.
    '''

    # Build a stable dataset identifier from original path labels
    from portable_paths import identifier
    portable = identifier(kind, files)
    if portable is not None:
        return portable
    names = []
    for path in files:
        path = source_identity_path(path)
        try:
            names.append(path.relative_to(project_dir).as_posix())
        except ValueError:
            names.append(str(path))
    # Full paths distinguish repeated filenames and filter-run variants.
    return kind + ':' + '|'.join(names)


def dataset_from_fits(path, source_type, project_dir):
    '''
    Purpose
    -------
    Build the canonical saved-product identity used by discovery and explicit launches.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    source_type: str
        single_cube selects simulation_fits; other supported mode is paired_cubes.
    project_dir: str or pathlib.Path
        Project root used for relative dataset identity labels.

    Outputs
    -------
    observation: Observation
        Simulation or observational FITS reference using the verified current path and
        stable original identity.

    Notes
    -----
    Use the same canonical identity for discovery and explicit plot launches.
    '''
    # Build the canonical saved-product identity used by discovery and explicit launches
    path = Path(path).expanduser().absolute()
    path=current_source_path(path)
    kind = 'simulation_fits' if source_type == 'single_cube' else 'fits'
    return Observation(_identifier(kind, (path,), Path(project_dir).resolve()),
                       f'{path.name} — {path.parent}', kind, (path,))


def discover_observations(*, config_file=CONFIG_FILE, product_roots=None, raw_roots=None,
                          include_simulations=False):
    '''
    Purpose
    -------
    Discover distinct saved phase products and deterministic eligible raw observational
    pairs.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    product_roots: iterable of path-like or None
        Saved-product trees to scan; defaults to the configured numerical-output root.
    raw_roots: iterable of path-like or None
        Raw observational roots; None uses configured discovery/default inputs.
    include_simulations: bool
        Include saved single-cube simulation phase products when True.

    Outputs
    -------
    observations: list of Observation
        Stable sorted choices, preserving separate product identities and pairing raw
        files only within their dataset directory.

    Notes
    -----
    Return every numerical observation product and deterministic raw file pair.

    Products are kept separately even when filenames recur in several filter
    directories. Raw diagnostics use the batch configuration's eligibility
    checks and are paired within their dataset directory, as batch.ipynb does.
    The shared explorer also includes saved single-cube simulation diagrams.
    '''
    # Discover distinct saved phase products and deterministic eligible raw
    # observational pairs
    config_file = Path(config_file).resolve()
    module = configuration(str(config_file))
    project = Path(getattr(module, 'project_dir', config_file.parent.parents[1])).expanduser().resolve()
    roots = product_roots if product_roots is not None else [Path(module.data_output_dir)]
    records = {}
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue
        for path in root.rglob('*'):
            if any(part.startswith('delta_z_') for part in path.relative_to(root).parts):
                continue
            if path.suffix.lower() not in FITS_SUFFIXES or 'komega' not in path.stem.lower():
                continue
            if any(part.startswith('.') for part in path.relative_to(root).parts):
                continue
            parts = {part.lower() for part in path.parts}
            simulation = 'simulations' in parts or bool(re.match(r'^(hx|vx|z0)_', path.name, re.I))
            observational = 'observations' in parts or bool(DATE_PATTERN.search(path.name))
            if not simulation and not observational:
                try:
                    source_mode = fits.getheader(path).get('SRCMODE')
                    observational = source_mode == 'paired_cubes'
                    simulation = source_mode == 'single_cube'
                except (OSError, ValueError):
                    continue
            if simulation and not include_simulations:
                continue
            if not observational and not simulation:
                continue
            path = path.absolute()
            kind = 'simulation_fits' if simulation else 'fits'
            identity = _identifier(kind, (path,), project)
            try:
                relative = path.relative_to(root)
                label = path.name if relative.parent == Path('.') else f'{path.name} — {relative.parent}'
            except ValueError:
                label = str(path)
            candidate = Observation(identity, label, kind, (path,))
            previous = records.get(identity)
            if previous is None or ('simulations' in path.parts or 'observations' in path.parts):
                records[identity] = candidate

    # Discover eligible original observing cubes independently of saved phase products
    raw_paths = set()
    if raw_roots is None:
        configured_root = getattr(module, 'vesa_2025_data_root', None)
        if configured_root is not None and not Path(configured_root).is_dir():
            # The original observing cubes were relocated with Vesa_2026.
            # Explicit caller roots still take precedence over this fallback.
            relocated = Path(getattr(module,'vesa_2026_dir',''))/'Data'
            if relocated.is_dir(): configured_root = relocated
        if configured_root is not None:
            raw_paths.update(Path(p).resolve() for p in
                             module.discover_paired_cube_batch_input_paths(configured_root))
        for value in module.batch_config.get('paired_cubes', {}).get('input_paths', []):
            path = Path(value).expanduser().resolve()
            if module.is_valid_paired_cube_batch_input_file(path):
                raw_paths.add(path)
        defaults = module.paired_cubes_inputs
        for key in ('v1_path', 'v2_path'):
            path = Path(defaults[key]).expanduser().resolve()
            if module.is_valid_paired_cube_batch_input_file(path):
                raw_paths.add(path)
    else:
        for root in raw_roots:
            raw_paths.update(Path(p).resolve() for p in module.discover_paired_cube_batch_input_paths(root))
            # The batch helper expects a parent of dataset folders. Also accept
            # a handpicked dataset folder with eligible cubes directly in it.
            folder = Path(root).expanduser()
            if folder.is_dir():
                raw_paths.update(p.resolve() for p in folder.iterdir()
                                 if module.is_valid_paired_cube_batch_input_file(p))
    # Pair original diagnostics only within their common dataset directory
    groups = {}
    for path in sorted(raw_paths):
        groups.setdefault(path.parent, []).append(path)
    for parent, paths in groups.items():
        for pair in combinations(paths, 2):
            identity = _identifier('raw_pair', pair, project)
            label = f'Raw / {parent.name} / {pair[0].name} + {pair[1].name}'
            records[identity] = Observation(identity, label, 'raw_pair', pair)
    return sorted(records.values(), key=lambda item: (item.kind != 'raw_pair', item.label.casefold(), item.id))


def file_fingerprint(path):
    '''
    Purpose
    -------
    Hash a current source while retaining its original verified identity label.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    fingerprint: dict
        Original path label, current byte size, and SHA-256 digest.
    '''

    # Hash a current source while retaining its original verified identity label
    path = current_source_path(path)
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(source_identity_path(path)), 'size_bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def _positive_float(value, label):
    '''
    Purpose
    -------
    Validate a strictly positive finite numeric sampling value.

    Inputs
    ------
    value: number
        Cadence or spatial-sampling value to validate.
    label: str
        Physical quantity and units used in validation errors.

    Outputs
    -------
    value: float
        Converted value; invalid numbers raise ValueError with the supplied label.
    '''

    # Validate a strictly positive finite numeric sampling value
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be positive and finite.')
    return value


def load_observation(observation, *, config_file=CONFIG_FILE):
    '''
    Purpose
    -------
    Load a selected dataset through its recorded source-kind contract.

    Inputs
    ------
    observation: Observation
        Saved FITS, raw pair, recorded input, or processing-result selection.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    data: ObservationData
        Phase values/axes/provenance, with original cubes restored when available.
        Unsupported shapes/units or inconsistent source metadata raise ValueError;
        recalculation-unavailable details may be retained in metadata.
    '''

    # Load a selected dataset through its recorded source-kind contract
    if observation.kind == 'processing_result':
        from processing_results import load_processing_observation
        return load_processing_observation(observation)
    if observation.kind == 'raw_pair':
        return _load_raw_pair(observation, config_file)
    if observation.kind == 'recorded_input':
        return _load_recorded_input(observation, config_file)
    path = observation.files[0]
    if not path.is_file():
        # A saved phase export is optional when its exact original inputs and
        # preprocessing are recorded. Never infer a replacement from filenames.
        from dopplergram_recalculation import resolve_input_reference
        reference = resolve_input_reference(path, config_file)
        return _load_recorded_input(recorded_input_observation(observation, reference), config_file)
    # Read the exact saved spectrum and require its supported phase/sampling conventions
    module = configuration(str(Path(config_file).resolve()))
    with fits.open(path, memmap=False) as hdus:
        values = np.array(hdus[0].data, dtype=float, copy=True)
        header = hdus[0].header.copy()
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError('Expected a two-dimensional project k–ω FITS array in [k_h, nu] order.')
    source_mode = header.get('SRCMODE', 'single_cube' if observation.kind == 'simulation_fits' else 'paired_cubes')
    if source_mode not in {'paired_cubes', 'single_cube'}:
        raise ValueError('Expected an observational paired-cube or simulation single-cube product.')
    if str(header.get('BUNIT', 'deg')).strip().lower() not in {'deg', 'degree', 'degrees'}:
        raise ValueError('The existing k–ω phase view requires phase differences in degrees.')
    defaults = module.paired_cubes_inputs
    # Simulation cadence/pixel scale differ from observations. Require their
    # saved sampling rather than falling back to observational configuration.
    if source_mode == 'single_cube' and any(key not in header for key in ('DT_S', 'DX_MM')):
        raise ValueError('Simulation FITS products require DT_S and DX_MM sampling metadata.')
    dt = _positive_float(header.get('DT_S', defaults['dt']), 'Cadence [s]')
    dx = _positive_float(header.get('DX_MM', defaults['p_dx_Mm']), 'Pixel scale [Mm]')
    # Reconstruct physical coordinates from recorded WCS or explicitly disclosed
    # sampling defaults
    axes = []
    for index, count, limit in ((1, values.shape[0], np.pi / dx), (2, values.shape[1], 500. / dt)):
        if f'CRVAL{index}' in header and f'CDELT{index}' in header:
            axis = float(header[f'CRVAL{index}']) + np.arange(count) * float(header[f'CDELT{index}'])
        else:
            axis = np.linspace(0., limit, count)
        if not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0) or axis[0] < 0:
            raise ValueError('Expected increasing, nonnegative k_h and nu axes in project FITS convention.')
        axes.append(axis)
    if header.get('CUNIT1', '1/Mm').strip().lower() not in {'1/mm', 'mm^-1', 'mm-1'}:
        raise ValueError('Unsupported horizontal-wavenumber units; expected 1/Mm.')
    if header.get('CUNIT2', 'mHz').strip().lower() != 'mhz':
        raise ValueError('Unsupported frequency units; expected mHz.')
    # Older outputs have no cube sample counts. Keep the assumption explicit and
    # editable; a positive-frequency count alone cannot distinguish odd/even nt.
    # Retain explicit original sample counts and disclose historical even-square
    # assumptions
    nx = int(header.get('NX_ORIG', 2 * values.shape[0]))
    nt = int(header.get('NT_ORIG', 2 * values.shape[1]))
    ny = int(header.get('NY_ORIG', nx))
    inferred = any(key not in header for key in ('NX_ORIG', 'NY_ORIG', 'NT_ORIG'))
    processing = _processing_metadata(path)
    metadata = {
        'source_fingerprints': [file_fingerprint(path)],
        'axis_convention': 'Morales pipeline FITS array [k_h, nu]; displayed as values.T',
        'axis_source': 'FITS CRVAL/CDELT' if 'CDELT1' in header and 'CDELT2' in header else 'sampling-derived axes',
        'source_type': source_mode,
        'sampling_source': 'inferred even square cube; confirm nx and nt against original cube' if inferred else 'FITS original cube metadata',
        'sampling_inferred': inferred,
        'sampling_defaults_used': 'DT_S' not in header or 'DX_MM' not in header,
        'source_processing': processing,
        'phase_delay_seconds': float(header.get('PHSCORR', 0.)),
        'phase_correction_applied': bool(header.get('PHSAPP', False)),
        'source_shape_k_nu': list(values.shape),
    }
    if source_mode == 'single_cube':
        from atmospheric_profiles import read_sidecar
        atmosphere = read_sidecar(path)
        if atmosphere is not None:
            metadata['atmospheric_parameters'] = atmosphere
    if nx < 2 or ny < 2 or nt < 3:
        raise ValueError('Original cube sample counts are invalid.')
    data = ObservationData(observation, values, *axes,
        PreviewGeometry(nx, nt, dt, dx, f'{nx} spatial × {nt} temporal samples'), ny, metadata)
    # Restore actual original/post-magnetogram cubes when their processing reference is
    # available
    try:
        from dopplergram_recalculation import resolve_input_reference,load_baseline
        reference = resolve_input_reference(path,config_file)
        baseline = load_baseline(reference,config_file)
    except (ValueError,KeyError,OSError) as exc:
        metadata['recalculation_error'] = str(exc)
    else:
        # A previously Gaussian-filtered phase export is not the baseline for
        # a new Gaussian. Restore its actual unfiltered/post-magnetogram cubes.
        nt,ny,nx = baseline.cubes[0].shape
        data.values,data.kh,data.nu = baseline.values,baseline.kh,baseline.nu
        data.geometry = PreviewGeometry(nx,nt,baseline.config['time_distance']['dt'],
            baseline.config['time_distance']['p_dx_Mm'],'Original Dopplergram sampling')
        data.ny,data.dopplergrams,data.analysis_config = ny,baseline.cubes,baseline.config
        data.pre_gaussian_raw = baseline.raw_cubes
        metadata.update(baseline.metadata)
        metadata.update(sampling_inferred=False,sampling_source='original Dopplergram arrays',
            source_processing=dict(description='Original cubes with recorded spatial magnetogram preprocessing; Gaussian rebuilt from this baseline',gaussian_preprocessed=False))
    return data


def recorded_input_observation(observation, reference, atmosphere=None):
    '''
    Purpose
    -------
    Attach explicit original-input provenance while retaining a launch product's dataset
    identity.

    Inputs
    ------
    observation: Observation
        Original product-path dataset reference.
    reference: dict
        Schema-version-1 original-cube processing reference.
    atmosphere: dict or None
        Optional recorded atmospheric defaults/provenance.

    Outputs
    -------
    observation: Observation
        recorded_input reference with deep-copied input/atmosphere metadata; unsupported
        reference schemas raise ValueError.

    Notes
    -----
    Attach provenance without changing the launch's product-path contract.
    '''
    # Attach explicit original-input provenance while retaining a launch product's
    # dataset identity
    if reference.get('schema_version') != 1:
        raise ValueError('Unsupported Dopplergram input reference.')
    return Observation(observation.id, observation.label, 'recorded_input', observation.files,
        dict(reference=copy.deepcopy(reference), atmosphere=copy.deepcopy(atmosphere)))


def _load_recorded_input(observation, config_file):
    '''
    Purpose
    -------
    Restore the cached native cube baseline for an explicitly recorded-input selection.

    Inputs
    ------
    observation: Observation
        recorded_input selection with reference and optional atmosphere metadata.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    data: ObservationData
        Original/post-magnetogram cubes, native phase spectrum, physical axes, runtime
        configuration, and source fingerprints.

    Notes
    -----
    Use the same cached baseline and native diagnostics as saved FITS loads.
    '''
    # Restore the cached native cube baseline for an explicitly recorded-input selection
    from dopplergram_recalculation import load_baseline
    from processing_results import fingerprint
    reference = observation.input_reference['reference']
    inputs = reference['data']
    keys = ('file',) if inputs['source_type'] == 'single_cube' else ('v1', 'v2')
    # Loaded-data fingerprints/storage refer to the files actually read. The
    # validated launch retains its historical product path for HTML writers.
    observation = Observation(observation.id, observation.label, observation.kind,
        tuple(current_source_path(inputs[key]) for key in keys), observation.input_reference)
    baseline = load_baseline(reference, config_file)
    metadata = copy.deepcopy(baseline.metadata)
    metadata.update(source_type=reference['data']['source_type'],
        source_fingerprints=[fingerprint(path) for path in observation.files],
        source_shape_k_nu=list(baseline.values.shape),
        axis_convention='pipeline.build_komega_axes; values [k_h, nu], displayed as values.T',
        sampling_inferred=False, sampling_defaults_used=False,
        sampling_source='recorded original Dopplergram arrays',
        source_processing=dict(description='Original cubes with recorded spatial magnetogram preprocessing; Gaussian rebuilt from this baseline',
                               gaussian_preprocessed=False))
    atmosphere = observation.input_reference.get('atmosphere')
    if atmosphere is not None:
        metadata['atmospheric_parameters'] = atmosphere
    nt, ny, nx = baseline.cubes[0].shape
    geometry = PreviewGeometry(nx, nt, baseline.config['time_distance']['dt'],
        baseline.config['time_distance']['p_dx_Mm'], 'Original Dopplergram sampling')
    return ObservationData(observation, baseline.values, baseline.kh, baseline.nu,
        geometry, ny, metadata, baseline.cubes, baseline.config, baseline.raw_cubes)


def _processing_metadata(path):
    '''
    Purpose
    -------
    Describe historical Gaussian preprocessing from recorded folder text or explicit
    filename markers.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    metadata: dict
        Processing description, optional parameter text, and known/unknown
        Gaussian-preprocessed flag.
    '''

    # Describe historical Gaussian preprocessing from recorded folder text or explicit
    # filename markers
    filter_folder = next((parent for parent in path.parents if re.fullmatch(r'filter_\d+', parent.name)), None)
    if filter_folder and (filter_folder / 'filter_parameters.txt').is_file():
        text = (filter_folder / 'filter_parameters.txt').read_text()
        return {'description': f'Existing {filter_folder.name} processed product', 'filter_parameters_text': text,
                'gaussian_preprocessed': 'filtering.gaussian.enabled: true' in text.lower()}
    if 'unfiltered' in path.name.lower():
        return {'description': 'Unfiltered FITS product', 'gaussian_preprocessed': False}
    return {'description': 'Previously processed or legacy FITS product; original amplitudes unavailable',
            'gaussian_preprocessed': True if 'gaussian_filtered' in path.name.lower() else None}


def _load_raw_pair(observation, config_file):
    '''
    Purpose
    -------
    Load matching raw observational cubes and compute their native unfiltered phase
    diagnostic.

    Inputs
    ------
    observation: Observation
        Ordered raw_pair selection containing two original cube paths.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    data: ObservationData
        Read-only matching (t, y, x) cubes, degree-valued [k_h, nu] spectrum, axes,
        sampling, and provenance. Changed inputs or shape mismatches raise ValueError.
    '''

    # Load matching raw observational cubes and compute their native unfiltered phase
    # diagnostic
    module = configuration(str(Path(config_file).resolve()))
    config = copy.deepcopy(module.config)
    config['data'].update(source_type='paired_cubes', v1=str(observation.files[0]),
                          v2=str(observation.files[1]), h1=0, h2=1)
    # TimeDistance's constructor expects runtime output keys, even for its
    # read-only compute method. No output method is invoked by this explorer.
    config['data'].setdefault('coherence_outfile', '')
    config['_module_dir'] = str(Path(config_file).resolve().parent)
    defaults = module.paired_cubes_inputs
    config['time_distance'].update(dt=defaults['dt'], p_dx_Mm=defaults['p_dx_Mm'])
    # Loading cubes uses the project's existing FITS/HDF5 loader, without
    # running the filtering/output pipeline or allocating a 3-D filter.
    loader = pipeline.load_agw_filter_class(config_file)(config)
    from dopplergram_recalculation import _version
    versions = _version(observation.files)
    cubes = [loader.load_cube(path) for path in observation.files]
    if cubes[0].ndim != 3 or cubes[0].shape != cubes[1].shape:
        raise ValueError('Paired observational cubes must have the same [t, y, x] shape.')
    engine = pipeline.TimeDistance(config)
    values, kh, nu, metadata = engine.compute_komega_diagram(*cubes)
    nt, ny, nx = cubes[0].shape
    metadata = {key: value for key, value in metadata.items() if key not in {'k_axis', 'nu_axis'}}
    metadata.update(source_fingerprints=[file_fingerprint(p) for p in observation.files],
        axis_convention='pipeline.build_komega_axes; values [k_h, nu], displayed as values.T',
        source_shape_k_nu=list(values.shape), sampling_source='original raw cube shape',
        sampling_inferred=False, sampling_defaults_used=True,
        source_processing={'description': 'Unfiltered raw observational pair; pipeline phase/delay conventions',
                           'gaussian_preprocessed': False})
    geometry = PreviewGeometry(nx, nt, defaults['dt'], defaults['p_dx_Mm'], f'{nx} × {ny} spatial × {nt} temporal samples')
    if _version(observation.files) != versions:
        raise ValueError('Original Dopplergram changed during loading; reselect the dataset.')
    config['_dopplergram_source_versions'] = versions
    for cube in cubes:
        cube.setflags(write=False)
    return ObservationData(observation, values, kh, nu, geometry, ny, metadata,tuple(cubes),config)


def reproducibility_metadata(data, geometry):
    '''
    Purpose
    -------
    Collect the exact dataset identity, axes, original sampling, and processing
    provenance.

    Inputs
    ------
    data: ObservationData
        Loaded selection whose arrays and metadata are described.
    geometry: PreviewGeometry
        Effective original sample counts and physical cadence/pixel scale.

    Outputs
    -------
    metadata: dict
        Portable registry/export dataset record with kh in Mm^-1, nu in mHz, cadence in
        seconds, and spatial scale in Mm.

    Notes
    -----
    Dataset identity, original axes, and sampling needed for future batch use.
    '''
    # Collect the exact dataset identity, axes, original sampling, and processing
    # provenance
    return {
        'id': data.observation.id, 'label': data.observation.label, 'kind': data.observation.kind,
        'files': [str(p) for p in data.observation.files],
        'metadata': data.metadata,
        'axes': {'kh_Mm_inverse': data.kh.tolist(), 'nu_mHz': data.nu.tolist()},
        'sampling': {'nx': geometry.nx, 'ny': data.ny, 'nt': geometry.nt,
                     'dt_seconds': geometry.dt_seconds, 'dx_Mm': geometry.dx_Mm},
    }
