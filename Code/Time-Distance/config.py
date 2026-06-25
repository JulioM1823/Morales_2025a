from copy import deepcopy
from math import sqrt
from pathlib import Path
import re


# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Global / Project Settings
# -----------------------------------------------------------------------------

# Shared project roots used by the pipeline and notebooks.
research_dir = '/Users/juliomorales/Research/Projects'
project_dir = '/Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a'

# Default output directories for data products and figures.
data_output_dir = f'{project_dir}/Data/Time-Distance'
figure_dir = f'{project_dir}/Morales 2025a et al/Figures/'
animation_dir = f'{figure_dir}Animations/'

# Reference data locations used by the default single-run inputs.
vesa_2025_dir = '/Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Vesa_2025/Data/25Apr2019'
vesa_2025_data_root = '/Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Vesa_2025/Data'
co5bold_batch_root = f'{research_dir}/Morales_2025a/Data/co5bold'
co5bold_dir = f'{co5bold_batch_root}/z0/0G'
model_atmosphere_path = f'{project_dir}/Data/Time-Distance/model_atmosphere.dat'


# -----------------------------------------------------------------------------
# 2. Mode Configuration & 1-pair-at-a-time Default Inputs
# -----------------------------------------------------------------------------

# Select the default runtime mode when this module is imported directly.
source_type = 'single_cube'  # options: paired_cubes, single_cube


# Default observational inputs for paired FITS cubes.
paired_cubes_inputs = {
        'v1_path': f'{vesa_2025_dir}/25Apr2019.ibis.to.hmi.vel.k7699.fits',
        'v2_path': f'{vesa_2025_dir}/25Apr2019.ibis.to.hmi.vel.fe7090.fits',
     'delta_z_km': 168,  # Physical height separation between the paired diagnostics.
        'p_dx_Mm': 68.8 / 160.0,
             'dt': 11.88,
}


# Default simulation inputs for a single NetCDF cube.
single_cube_inputs = {
                'file_path': f'{co5bold_dir}/simulation_z0_0G_14400s_28800s.nc',
               'observable': 'v3',  # options: v1, v2, v3, bb1, bb2, bb3, rho
                       'h1': 2,
                       'h2': 4,
    'model_atmosphere_path': model_atmosphere_path,
}


# -----------------------------------------------------------------------------
# 3. Processing Parameters
# -----------------------------------------------------------------------------

# Default filtering sequence and per-filter settings.
default_filtering = {
    'enabled': True,
    'filter_sequence': ['magnetogram', 'gaussian'],
    'gaussian': {
          'enabled': True,
        'central_k': 1.5,
          'width_k': 4.0,
        'central_f': 3.0,
          'width_f': 3.0,
    },
    'magnetogram': {
            'enabled': False,
          'selection': 'magnetic',
        'threshold_G': 3.0,
         'fill_value': 0.0,
    },
}


# -----------------------------------------------------------------------------
# 4. Magnetogram Configuration
# -----------------------------------------------------------------------------

# Simulation magnetogram sampling mode. Paired-cube magnetograms are always
# auto-discovered from each observational dataset directory.
magnetogram_mode = {'single_cube': 'bottom'} # options: bottom, per_height_pair


# -----------------------------------------------------------------------------
# 5. Analysis / Computation Settings
# -----------------------------------------------------------------------------

# Default time-distance geometry and runtime settings.
xcorr_geometry = 'annulus'  # options: annulus, east, west, north, south

default_time_distance = {
                     'width': 0,
                 'dx_pixels': 1.0,
                  'nworkers': 12,
                'maxdist_Mm': 10.0,
           'xcorr_geometry': xcorr_geometry,
             'xcorrj_engine': 'chunked',
           'xcorrj_parallel': True,
      'xcorrj_chunk_centers': 'auto',
    'xcorrj_chunk_memory_mb': 128.0}


# -----------------------------------------------------------------------------
# 6. Plotting-Relevant Toggles
# -----------------------------------------------------------------------------

# Plot-generation switches only. Plot aesthetics belong in plotting code.
default_plot_generate = {
    'cross_correlation': True,
     'phase_difference': True,
               'komega': True,
      'gaussian_filter': True,
          'dopplergram': True,
            'composite': True,
      'correlation_radius_animation': True,
    'correlation_vertical_animation': True,
            'phase_radius_animation': True,
          'phase_vertical_animation': True,
}


# -----------------------------------------------------------------------------
# 7. Dispersion / Model Settings
# -----------------------------------------------------------------------------

# Theory-based dispersion-curve defaults used by the diagnostic overlays.
cs: float = 7.8
a: float = 0.33*cs
theta_deg: float = 80.0
phi_deg: float = 40.0
H: float = 125.0
g: float = 0.274
gamma: float = 5.0 / 3.0
N: float = sqrt((g / H) - (g ** 2 / cs ** 2))  # Hz
tau: float = 200.0  # s
wac: float = cs / (2.0 * H)  # Hz

# Dispersion-curve model settings used by the k-omega and filter overlays.
default_dispersion_curves = {
    'mode': 'simulation_based',  # options: simulation_based, theory_based
    'simulation_based': {
        'reference_model_file': f'{project_dir}/Code/Time-Distance/Oana_codes/CSM_A.dat',
         'height_index': 1005,
          'gravity_cgs': 27400.0,
        'gravity_km_s2': 0.274,
        'curves': {
            'enabled': True,
        },
    },
    'theory_based': {
        'include_fmode': True,
        'models': [
            {
                  'model': 'nc2009',  # options: sf1966, mt1981, mt1982, bunte1993, nc2009
                'enabled': True,
                 'params': {
                        # Physical parameters:
                        'cs': cs,
                         'a': a,
                 'theta_deg': theta_deg,
                   'phi_deg': phi_deg,
                         'H': H,
                         'g': g,
                     'gamma': gamma,
                         'N': N,
                       'tau': tau,
                       'wac': wac,
                },
            },
        ],
    },
}


# Editable dispersion-curve model inputs.
dispersion_curve_inputs = deepcopy(default_dispersion_curves)


# =============================================================================
# BATCH CONFIGURATION
# =============================================================================

# Gaussian sweep lists are zip-style: index i across all four lists defines one
# filter. Keep the lists equal length.
batch_gaussian_filter_params = {
    'central_k': [2.0, 0.5, 2.0, 1.0, 1.5, 1.5],
      'width_k': [1.5, 1.5, 5.0, 1.0, 1.0, 4.0],
    'central_f': [2.0, 2.0, 2.0, 3.0, 3.0, 3.0],
      'width_f': [2.0, 2.0, 3.5, 3.0, 4.0, 3.0],
}


paired_cube_batch_supported_suffixes = {'.fits', '.fit', '.fts', '.h5', '.hdf5'}
paired_cube_batch_excluded_tokens = (
    'aia',
    'hmimag',
    'hmicont',
    'coherence',
    'filtered',
    'komega',
    'phase',
    'cache',
    'tmp',
    'temp',
)


def _has_hidden_path_component(file_path):
    return any(part.startswith('.') for part in Path(file_path).parts)


def _is_temporary_or_cache_file(file_path):
    name = Path(file_path).name.lower()

    if name.startswith(('._', '~')) or name.endswith(('~', '.bak', '.cache', '.crdownload', '.download', '.part', '.tmp')):
        return True

    return False


def is_valid_paired_cube_batch_input_file(file_path):
    '''
    Return whether a file is a supported non-AIA observational batch input.
    '''

    path = Path(file_path)
    name = path.name.lower()

    if not path.is_file():
        return False

    if _has_hidden_path_component(path) or _is_temporary_or_cache_file(path):
        return False

    if path.suffix.lower() not in paired_cube_batch_supported_suffixes:
        return False

    if any('aia' in part.lower() for part in path.parts):
        return False

    if any(token in name for token in paired_cube_batch_excluded_tokens):
        return False

    if '.int.' in name or '.to.hmi.int.' in name:
        return False

    if re.search(r'hmi[\s_.-]*dop', name, flags = re.IGNORECASE):
        return True

    if re.search(r'(^|[._-])(?:vel|velocity)([._-]|$)', name, flags = re.IGNORECASE):
        return True

    return False


def discover_paired_cube_batch_input_paths(data_root):
    '''
    Recursively discover supported observational paired-cube batch inputs.
    '''

    root = Path(data_root).expanduser()
    if not root.exists():
        return []
    if not root.is_dir():
        raise NotADirectoryError(f'Paired-cube batch root is not a directory: {root}')

    discovered_paths = []
    dataset_dirs = sorted(
        (
            path for path in root.iterdir()
            if path.is_dir() and not _has_hidden_path_component(path.relative_to(root))
        ),
        key = lambda path: str(path.relative_to(root)).lower(),
    )

    for dataset_dir in dataset_dirs:
        candidate_files = sorted(
            (path for path in dataset_dir.rglob('*') if path.is_file()),
            key = lambda path: str(path.relative_to(root)).lower(),
        )

        for candidate_file in candidate_files:
            if is_valid_paired_cube_batch_input_file(candidate_file):
                discovered_paths.append(str(candidate_file.resolve()))

    return discovered_paths


# Batch inputs and overrides consumed directly by batch.ipynb.
batch_config = {
    'single_netcdf_cube': {
        'source_type': 'single_netcdf_cube',

        # Batch paths.
        'input_paths': [
            f'{co5bold_batch_root}/hx/10G/simulation_hx_10G_33570s_48000s.nc',
            f'{co5bold_batch_root}/hx/50G/simulation_hx_50G_33570s_48000s.nc',
            f'{co5bold_batch_root}/hx/100G/simulation_hx_100G_33570s_48000s.nc',
            f'{co5bold_batch_root}/vx/10G/simulation_vx_10G_33570s_47970s.nc',
            f'{co5bold_batch_root}/vx/50G/simulation_vx_50G_47970s_62370s.nc',
            f'{co5bold_batch_root}/vx/100G/simulation_vx_100G_33570s_47970s.nc',
            f'{co5bold_batch_root}/z0/0G/simulation_z0_0G_14400s_28800s.nc',
        ],

        # Batch metadata.
                     'observable': single_cube_inputs['observable'],
          'model_atmosphere_path': model_atmosphere_path,
                   'height_pairs': 'all',

        # Parameter sweeps.
         'gaussian_filter_params': deepcopy(batch_gaussian_filter_params),

        # Batch execution flags.
                  'skip_existing': True,
              'continue_on_error': True,
                   'run_analysis': True,
               'analysis_timeout': 3600,
        'run_time_distance_batch': True,
        'comparison_run_analysis': True,
             'comparison_timeout': 3600,
    },
    'paired_cubes': {
        'source_type': 'paired_cubes',

        # Batch paths.
        'input_paths': discover_paired_cube_batch_input_paths(vesa_2025_data_root),
          'recursive': True,
         'file_pairs': [],

        # Batch metadata.
        'delta_z_km': paired_cubes_inputs['delta_z_km'],
           'p_dx_Mm': paired_cubes_inputs['p_dx_Mm'],
                'dt': paired_cubes_inputs['dt'],

        # Parameter sweeps.
         'gaussian_filter_params': deepcopy(batch_gaussian_filter_params),

        # Batch execution flags.
                  'skip_existing': True,
              'continue_on_error': True,
                   'run_analysis': True,
               'analysis_timeout': 3600,
        'run_time_distance_batch': True,
        'comparison_run_analysis': True,
             'comparison_timeout': 5400,
    },
}


# =============================================================================
# CONFIGURATION HELPERS
# =============================================================================

def _normalize_source_type(source_type_value):

    '''
    Purpose
    -------
    Normalize the configured source-type label to the canonical runtime name.

    Inputs
    ------
    source_type_value: object
        Raw source-type value from the configuration module.

    Outputs
    -------
    normalized_source_type: str
        Canonical source-type label used by the pipeline.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Normalize the label before validating it downstream.
    normalized_source_type = str(source_type_value).strip().lower()

    # Preserve compatibility with the older single-cube alias.
    if normalized_source_type == 'single_netcdf_cube':
        return 'single_cube'

    return normalized_source_type


def _deep_merge(defaults, overrides):

    '''
    Purpose
    -------
    Recursively merge a user-override dictionary into a default dictionary.

    Inputs
    ------
    defaults: object
        Default value or mapping.

    overrides: object
        User override value or mapping.

    Outputs
    -------
    merged_value: object
        Deep-copied merged result.

    Author(s)
    ---------
    Julio M. Morales, April 6th, 2026.
    '''

    # Replace missing overrides with a deep copy of the defaults.
    if overrides in ['', None]:
        return deepcopy(defaults)

    # Replace scalar values and lists outright instead of merging them itemwise.
    if not isinstance(defaults, dict) or not isinstance(overrides, dict):
        return deepcopy(overrides)

    # Merge nested dictionaries recursively so callers can override just one branch.
    merged = deepcopy(defaults)
    for key, value in overrides.items():
        if key in merged:
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)

    return merged


def _normalize_magnetogram_mode(magnetogram_mode_value):

    '''
    Purpose
    -------
    Validate and normalize the mode-specific magnetogram selection settings.

    Inputs
    ------
    magnetogram_mode_value: dict or None
        User-facing magnetogram mode configuration.

    Outputs
    -------
    normalized_magnetogram_mode: dict
        Validated magnetogram mode dictionary.

    Author(s)
    ---------
    Julio M. Morales, April 28th, 2026.
    '''

    if magnetogram_mode_value in ['', None]:
        magnetogram_mode_value = magnetogram_mode

    if not isinstance(magnetogram_mode_value, dict):
        raise TypeError('magnetogram_mode must be a dictionary.')

    unsupported_keys = sorted(set(magnetogram_mode_value.keys()) - {'single_cube'})
    if len(unsupported_keys) > 0:
        raise ValueError(
            "magnetogram_mode only supports the 'single_cube' key. "
            f"Unsupported keys: {', '.join(unsupported_keys)}."
        )

    single_cube_mode = str(magnetogram_mode_value.get('single_cube', 'bottom')).strip().lower()
    allowed_single_cube_modes = {'bottom', 'per_height_pair'}
    if single_cube_mode not in allowed_single_cube_modes:
        raise ValueError(
            "magnetogram_mode['single_cube'] must be either 'bottom' or 'per_height_pair'. "
            f"Received {single_cube_mode!r}."
        )

    return {'single_cube': single_cube_mode}


def _normalize_xcorr_geometry(xcorr_geometry_value):

    '''
    Purpose
    -------
    Validate and normalize the configured cross-correlation averaging geometry.

    Inputs
    ------
    xcorr_geometry_value: str or None
        User-facing cross-correlation geometry label.

    Outputs
    -------
    normalized_xcorr_geometry: str
        Canonical geometry label.

    Author(s)
    ---------
    Julio M. Morales, May 12th, 2026.
    '''

    if xcorr_geometry_value in ['', None]:
        return 'annulus'

    normalized_xcorr_geometry = str(xcorr_geometry_value).strip().lower()
    allowed_xcorr_geometries = {'annulus', 'east', 'west', 'north', 'south'}
    if normalized_xcorr_geometry not in allowed_xcorr_geometries:
        raise ValueError(
            "xcorr_geometry must be one of 'annulus', 'east', 'west', 'north', or 'south'. "
            f"Received {normalized_xcorr_geometry!r}."
        )

    return normalized_xcorr_geometry


def _normalize_filtering_config(filtering_config):

    '''
    Normalize filtering settings so disabled filter stages are not active.
    '''

    if not isinstance(filtering_config, dict):
        raise TypeError('filtering must be a dictionary.')

    normalized_filtering = deepcopy(filtering_config)
    raw_filter_sequence = normalized_filtering.get('filter_sequence', [])

    if raw_filter_sequence in ['', None]:
        raw_filter_sequence = []
    if not isinstance(raw_filter_sequence, (list, tuple)):
        raise TypeError("filtering['filter_sequence'] must be a list or tuple.")

    normalized_filter_sequence = []
    seen_filter_names = set()

    for filter_name in raw_filter_sequence:
        normalized_filter_name = str(filter_name).strip().lower()

        if normalized_filter_name == '' or normalized_filter_name in seen_filter_names:
            continue

        filter_config = normalized_filtering.get(normalized_filter_name, {})
        if bool(filter_config.get('enabled', False)):
            normalized_filter_sequence.append(normalized_filter_name)
            seen_filter_names.add(normalized_filter_name)

    normalized_filtering['filter_sequence'] = normalized_filter_sequence
    normalized_filtering['enabled'] = bool(normalized_filtering.get('enabled', False)) and len(normalized_filter_sequence) > 0

    return normalized_filtering


def _normalize_dispersion_curve_toggle(curves_value):

    '''
    Normalize the legacy dispersion-curve toggle to a single enabled flag.
    '''

    if curves_value in ['', None]:
        return {'enabled': False}

    if isinstance(curves_value, dict):
        if 'enabled' in curves_value:
            return {'enabled': bool(curves_value.get('enabled', False))}

        legacy_curve_flags = [
            bool(curve_spec.get('enabled', False))
            for curve_spec in curves_value.values()
            if isinstance(curve_spec, dict)
        ]
        return {'enabled': any(legacy_curve_flags)}

    return {'enabled': bool(curves_value)}


def _require(raw_value, field_name):

    '''
    Purpose
    -------
    Enforce that a required configuration value is present.

    Inputs
    ------
    raw_value: object
        Candidate value to validate.

    field_name: str
        Name used in the error message when the value is missing.

    Outputs
    -------
    validated_value: object
        The original value when it is present.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Reject empty values before the pipeline starts building paths or casts.
    if raw_value in ['', None]:
        raise ValueError(f'{field_name} is required.')

    return raw_value


def _normalize_path(path_like):

    '''
    Purpose
    -------
    Expand a path-like input to a normalized user path string.

    Inputs
    ------
    path_like: str or pathlib.Path
        Path value from the configuration inputs.

    Outputs
    -------
    normalized_path: str
        Expanded path string.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Expand `~` so all downstream code receives concrete paths.
    return str(Path(path_like).expanduser())


def get_config(
    source_type,
    v1_path = None,
    v2_path = None,
    delta_z_km = None,
    p_dx_Mm = None,
    dt = None,
    file_path = None,
    observable = None,
    h1 = None,
    h2 = None,
    model_atmosphere_path = None,
    *,
    data_output_dir = data_output_dir,
    figure_dir = figure_dir,
    animation_dir = animation_dir,
    filtering = None,
    time_distance = None,
    plot_generate = None,
    dispersion_curves = None,
    magnetogram_mode = None,
):

    '''
    Purpose
    -------
    Build the mode-aware configuration dictionary used by the time-distance pipeline.

    Inputs
    ------
    source_type: str
        Pipeline mode. Supported values are `paired_cubes` and `single_cube`.

    v1_path, v2_path, delta_z_km, p_dx_Mm, dt: optional
        Required inputs when `source_type = 'paired_cubes'`.

    file_path, observable, h1, h2: optional
        Required inputs when `source_type = 'single_cube'`.

    model_atmosphere_path: str or pathlib.Path, optional
        Optional model-atmosphere table for single-cube runs.

    data_output_dir, figure_dir, animation_dir: str or pathlib.Path, optional
        Output directories used by the pipeline and notebooks.

    filtering, time_distance, plot_generate: dict, optional
        Optional overrides for the default runtime settings.

    dispersion_curves: dict, optional
        Optional overrides for the default dispersion-curve settings used by
        the k-omega and Gaussian-filter overlays.

    magnetogram_mode: dict, optional
        Optional simulation magnetogram mode settings. Only the `single_cube`
        key is supported. Paired-cube magnetograms are always auto-discovered.

    Outputs
    -------
    config: dict
        Runtime configuration dictionary with normalized paths and mode-specific inputs.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Normalize the mode label before validating the rest of the inputs.
    source_type = _normalize_source_type(source_type)

    # Reject unsupported modes early so the error is explicit.
    if source_type not in ['paired_cubes', 'single_cube']:
        raise ValueError("source_type must be either 'paired_cubes' or 'single_cube'.")

    # Copy the defaults so callers can override nested settings safely.
    filtering_config = deepcopy(default_filtering if filtering is None else filtering)
    time_distance_config = deepcopy(default_time_distance if time_distance is None else time_distance)
    plot_generate_config = deepcopy(default_plot_generate if plot_generate is None else plot_generate)
    dispersion_curve_config = _deep_merge(default_dispersion_curves, dispersion_curves)
    magnetogram_mode_config = _normalize_magnetogram_mode(magnetogram_mode)
    time_distance_config.setdefault('xcorr_geometry', xcorr_geometry)
    time_distance_config['xcorr_geometry'] = _normalize_xcorr_geometry(
        time_distance_config.get('xcorr_geometry', xcorr_geometry))

    # Ensure known filter sections exist, then remove disabled stages from the active sequence.
    filtering_config.setdefault('gaussian', {})
    filtering_config.setdefault('magnetogram', {})
    filtering_config = _normalize_filtering_config(filtering_config)

    # Normalize the optional simulation-based reference model path when present.
    simulation_curve_config = dispersion_curve_config.get('simulation_based', {})
    if simulation_curve_config.get('reference_model_file', '') not in ['', None]:
        simulation_curve_config['reference_model_file'] = _normalize_path(
            simulation_curve_config['reference_model_file']
        )
    simulation_curve_config['curves'] = _normalize_dispersion_curve_toggle(
        simulation_curve_config.get('curves', {'enabled': True})
    )

    # Build the shared runtime structure used by both source modes.
    config = {
        'paths': {
            'project_dir': project_dir,
            'data_output_dir': _normalize_path(data_output_dir),
            'figure_dir': _normalize_path(figure_dir),
            'animation_dir': _normalize_path(animation_dir),
        },
        'data': {
            'source_type': source_type,
            'paired_cubes': {},
            'single_cube': {},
            'outfile': '',
            'phase_outfile': '',
            'komega_outfile': '',
            'orientation_validation_outfile': '',
        },
        'filtering': filtering_config,
        'time_distance': time_distance_config,
        'dispersion_curves': dispersion_curve_config,
        'magnetogram_mode': magnetogram_mode_config,
        'plots': {
            'generate': plot_generate_config,
        },
    }

    # Populate the paired-cube settings and validate the required physical inputs.
    if source_type == 'paired_cubes':
        v1_path = _normalize_path(_require(v1_path, 'v1_path'))
        v2_path = _normalize_path(_require(v2_path, 'v2_path'))
        delta_z_km = float(_require(delta_z_km, 'delta_z_km'))
        p_dx_Mm = float(_require(p_dx_Mm, 'p_dx_Mm'))
        dt = float(_require(dt, 'dt'))

        # Enforce the basic physical constraints expected by the pipeline.
        if delta_z_km < 0.0:
            raise ValueError('delta_z_km must be non-negative.')
        if p_dx_Mm <= 0.0:
            raise ValueError('p_dx_Mm must be positive.')
        if dt <= 0.0:
            raise ValueError('dt must be positive.')

        # Store the resolved paired-cube inputs in the runtime config.
        config['data']['paired_cubes'] = {
            'data_dir': str(Path(v1_path).expanduser().parent),
            'v1': v1_path,
            'v2': v2_path,
            'delta_z_km': delta_z_km,
            'p_dx_Mm': p_dx_Mm,
            'dt': dt,
        }
    else:
        # Populate the single-cube inputs and enforce index-style height selection.
        file_path = _normalize_path(_require(file_path, 'file_path'))
        observable = str(_require(observable, 'observable')).strip()
        h1 = int(_require(h1, 'h1'))
        h2 = int(_require(h2, 'h2'))

        # Reject empty observables and negative layer indices before runtime inference.
        if observable == '':
            raise ValueError('observable is required.')
        if h1 < 0 or h2 < 0:
            raise ValueError('h1 and h2 must be non-negative indices.')

        # Store the resolved single-cube inputs in the runtime config.
        config['data']['single_cube'] = {
            'file': file_path,
            'observable': observable,
            'h1': h1,
            'h2': h2,
        }

        # Include the optional model atmosphere only when the caller provided it.
        if model_atmosphere_path not in ['', None]:
            config['data']['single_cube']['model_atmosphere_path'] = _normalize_path(model_atmosphere_path)

    return config


# =============================================================================
# EXPORTED CONFIGURATION
# =============================================================================

# Build the default exported config object for direct imports and notebooks.
config = get_config(
    source_type = source_type,
    **(deepcopy(paired_cubes_inputs) if _normalize_source_type(source_type) == 'paired_cubes' else deepcopy(single_cube_inputs)),
    dispersion_curves = deepcopy(dispersion_curve_inputs),
    magnetogram_mode = deepcopy(magnetogram_mode),
)
