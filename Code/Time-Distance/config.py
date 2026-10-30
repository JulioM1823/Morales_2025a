'''
Purpose
-------
Define project defaults, discover supported observational inputs, and construct
mode-aware pipeline configurations.

Inputs
------
None

Outputs
-------
config, batch_config, defaults, and configuration helpers
    Construct the default exported runtime and discover configured observational
    batch inputs at import time. Distances use km/Mm as named, cadence uses s,
    model angular frequencies use rad/s, and signed N2 uses s^-2.
'''

# Import the libraries and shared helpers used by this module
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
project_dir = str(Path(__file__).resolve().parents[2])

# Default output directories for data products and figures.
data_output_dir = f'{project_dir}/Data'
from figure_locations import canonical_figure_root
figure_dir = str(canonical_figure_root(Path(project_dir)/'Figures')) + '/'
animation_dir = f'{figure_dir}Animations/'

# Reference data locations used by the default single-run inputs.
vesa_2025_data_root = str(Path(project_dir)/'Data/observations_raw')
vesa_2025_dir = str(Path(vesa_2025_data_root)/'25Apr2019')
co5bold_batch_root = f'{project_dir}/Data/co5bold'
from portable_paths import bundle_root, co5bold_directory
if bundle_root():
    co5bold_batch_root = str(co5bold_directory())
    vesa_2025_data_root = str(bundle_root()/'Data/observations_raw')
    from portable_paths import data_directory
    if data_directory():
        vesa_2025_data_root = str(data_directory()/'observations_raw')
        data_output_dir = str(data_directory())
    vesa_2025_dir = str(Path(vesa_2025_data_root)/'25Apr2019')
co5bold_dir = f'{co5bold_batch_root}/z0/0G'
model_atmosphere_path = f'{project_dir}/Data/Time-Distance/model_atmosphere.dat'
vesa_2026_dir = str(Path(project_dir).parent / 'Vesa_2026')
if bundle_root():
    vesa_2026_dir = str(bundle_root()/'vendor/Vesa_2026')

# Snapshot profile units are absent in the legacy exports. Sound/frequency
# units and horizontal snapshot averaging were confirmed on 2026-10-13.
# Unitless z is separately verified against the cube's recorded vertical bins.
default_atmospheric_profiles = {
    'enabled': True,
    # Verified against native staggered fields and the supplied Alfven profile.
    # Only applied to cubes explicitly identified as CO5BOLD; physical-G
    # exports may override this using magnetic_field_convention='physical'.
    'co5bold_magnetic_convention': 'internal',
    'gravity_km_s2': 0.274,  # Positive solar magnitude; not supplied by the cubes.
    'directory': f'{co5bold_batch_root}/co5bold_1d_profiles',
    'model_files': {},  # Optional explicit Model -> profile file mapping.
    'legacy_units': {
        'sound_speed': 'cm/s', 'alfven_speed': 'cm/s', 'adiabatic_index': 'dimensionless',
        'brunt_vaisala_freq': 'rad/s',
        'acoustic_cutoff_freq_isothermal': 'rad/s',
        'acoustic_cutoff_freq_non_isothermal': 'rad/s', 'temperature': 'K',
    },
}


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
               'observable': 'v3',  # options: v1, v2, v3, bb1, bb2, bb3, rho, pressure, plasma_beta
               # pressure/plasma_beta require stored 4D variables in this file.
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
      'correlation_radius_animation': False,
    'correlation_vertical_animation': False,
            'phase_radius_animation': False,
          'phase_vertical_animation': False,
}


# -----------------------------------------------------------------------------
# 7. Dispersion / Model Settings
# -----------------------------------------------------------------------------

# Theory-based dispersion-curve defaults used by the diagnostic overlays.
cs: float = 7.8
a: float  = 0.33*cs
theta_deg: float = 80.0
phi_deg: float = 40.0
H: float = 125.0
g: float = 0.274
gamma: float = 5.0 / 3.0
N: float = sqrt((g / H) - (g ** 2 / cs ** 2))  # rad/s
tau: float = 200.0  # s
wac: float = cs / (2.0 * H)  # rad/s

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


# Detailed k-omega comparison settings.  These model parameters are consumed
# by the authoritative Vesa_2026 DiagnosticDiagram implementation.  The
# production height-pair interface replaces a, theta, phi, and dz with values
# from the selected atmospheric layers.  The standalone notebook has explicit
# config fallbacks below so it can run without a simulation/model atmosphere.
default_komega_comparison = {
    'enabled': True,
    'bokeh_server_url': 'http://127.0.0.1:5013',
    'vesa_2026_dir': vesa_2026_dir,
    'max_k_samples': 64,
    'max_frequency_samples': 64,
    # Opt in to the slower mpmath cross-check at flagged k_z grid points.
    'high_precision_validation': False,
    'composite_width_px': 1800,
    'phase_limits_deg': [-80.0, 80.0],
    # Mirror the publication-style k-omega plot defaults in plots.ipynb.
    'plot_style': {
        'figsize': [10.0, 6.0],
        'cmap': 'cmr.fusion',
        'xlim_Mm_inverse': [0.0, 7.0],
        'ylim_mHz': [0.0, 10.0],
        'panel_box_aspect': 1.55,
        'dpi': 300,
        'use_tex': True,
        'font_family': 'serif',
    },
    # Used only by komega_single_model_demo.ipynb when the selected FITS file
    # does not contain simulation-derived layer metadata.  Production HTML
    # generation remains strict and does not consume this fallback.
    'standalone_pair': {
        'a_km_s': a,
        'theta_deg': theta_deg,
        'phi_deg': phi_deg,
        'dz_km': paired_cubes_inputs['delta_z_km'],
    },
    # Used only if a standalone notebook FITS file lacks k/frequency WCS cards.
    'standalone_sampling': {
        'p_dx_Mm': paired_cubes_inputs['p_dx_Mm'],
        'dt_s': paired_cubes_inputs['dt'],
    },
    'models': {
        'nc2009': {
            'params': {
                'cs': cs,
                'g': g,
                'N': N,
                'wac': wac,
            },
        },
        'alfven_mode': {
            'params': {},
        },
        'slow_fast_mode': {
            'params': {
                'cs': cs,
            },
        },
        'slow_mode': {
            'params': {
                'cs': cs,
            },
        },
        'fast_mode': {
            'params': {
                'cs': cs,
            },
        },
        'bunte1993': {
            'params': {
                'cs': cs,
                'g': g,
                'gamma': gamma,
                'H': H,
                'tau': tau,
                'epsilon': 0.0,
            },
        },
        'mt1982': {
            'params': {
                'cs': cs,
                'g': g,
                'gamma': gamma,
                'H': H,
                'N': N,
                'tau': tau,
            },
        },
        'mt1981': {
            'params': {
                'cs': cs,
                'g': g,
                'H': H,
                'N': N,
            },
        },
    },
}


komega_comparison_inputs = deepcopy(default_komega_comparison)


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
    '''
    Purpose
    -------
    Detect any hidden filesystem component in an input path.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input-file path used to resolve dataset metadata.

    Outputs
    -------
    hidden: bool
        True when at least one component begins with a period.
    '''

    # Detect any hidden filesystem component in an input path
    return any(part.startswith('.') for part in Path(file_path).parts)


def _is_temporary_or_cache_file(file_path):
    '''
    Purpose
    -------
    Identify temporary, backup, partial-download, and cache filenames.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input-file path used to resolve dataset metadata.

    Outputs
    -------
    excluded: bool
        True for a recognized temporary/backup/cache prefix or suffix.
    '''

    # Identify temporary, backup, partial-download, and cache filenames
    name = Path(file_path).name.lower()

    if name.startswith(('._', '~')) or name.endswith(('~', '.bak', '.cache', '.crdownload', '.download', '.part', '.tmp')):
        return True

    return False


def is_valid_paired_cube_batch_input_file(file_path):
    '''
    Purpose
    -------
    Identify supported observational velocity cubes while excluding derived and
    auxiliary products.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input-file path used to resolve dataset metadata.

    Outputs
    -------
    accepted: bool
        True only for existing supported nonhidden files matching the recognized
        Doppler/velocity naming conventions.

    Notes
    -----
    Return whether a file is a supported non-AIA observational batch input.
    '''

    # Identify supported observational velocity cubes while excluding derived and
    # auxiliary products
    path = Path(file_path)
    name = path.name.lower()

    if not path.is_file():
        return False

    # Exclude hidden, partial, unsupported, and auxiliary data products
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

    # Accept only the recognized Doppler/velocity input naming conventions
    if re.search(r'hmi[\s_.-]*dop', name, flags = re.IGNORECASE):
        return True

    if re.search(r'(^|[._-])(?:vel|velocity)([._-]|$)', name, flags = re.IGNORECASE):
        return True

    return False


def discover_paired_cube_batch_input_paths(data_root):
    '''
    Purpose
    -------
    Discover supported observational inputs below each visible dataset directory.

    Inputs
    ------
    data_root: str or pathlib.Path
        Root whose visible direct subdirectories are searched recursively.

    Outputs
    -------
    paths: list of str
        Sorted resolved input-file paths; nonexistent roots return an empty list and
        non-directory roots raise NotADirectoryError.

    Notes
    -----
    Recursively discover supported observational paired-cube batch inputs.
    '''

    # Discover supported observational inputs below each visible dataset directory
    root = Path(data_root).expanduser()
    if not root.exists():
        return []
    if not root.is_dir():
        raise NotADirectoryError(f'Paired-cube batch root is not a directory: {root}')

    discovered_paths = []
    # Search visible dataset folders in stable relative-path order
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

        # Apply the same observational eligibility contract to every discovered file
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

    # Validate simulation magnetogram-selection mode settings
    if magnetogram_mode_value in ['', None]:
        magnetogram_mode_value = magnetogram_mode

    # Reject malformed or unsupported mode-specific settings before normalization
    if not isinstance(magnetogram_mode_value, dict):
        raise TypeError('magnetogram_mode must be a dictionary.')

    unsupported_keys = sorted(set(magnetogram_mode_value.keys()) - {'single_cube'})
    if len(unsupported_keys) > 0:
        raise ValueError(
            "magnetogram_mode only supports the 'single_cube' key. "
            f"Unsupported keys: {', '.join(unsupported_keys)}."
        )

    # Validate the simulation magnetic sampling mode while observations remain automatic
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

    # Validate the configured cross-correlation geometry
    if xcorr_geometry_value in ['', None]:
        return 'annulus'

    # Normalize and validate the supported annulus or directional averaging label
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
    Purpose
    -------
    Normalize an independent filter configuration and exclude inactive stages.

    Inputs
    ------
    filtering_config: dict
        Filter-stage settings and their requested execution sequence.

    Outputs
    -------
    filtering: dict
        Deep-copied settings with deduplicated enabled stages and a consistent top-level
        enabled flag; invalid containers raise TypeError.

    Notes
    -----
    Normalize filtering settings so disabled filter stages are not active.
    '''

    # Normalize an independent filter configuration and exclude inactive stages
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

    # Preserve order while removing duplicate, blank, and disabled filter stages
    for filter_name in raw_filter_sequence:
        normalized_filter_name = str(filter_name).strip().lower()

        if normalized_filter_name == '' or normalized_filter_name in seen_filter_names:
            continue

        filter_config = normalized_filtering.get(normalized_filter_name, {})
        if bool(filter_config.get('enabled', False)):
            normalized_filter_sequence.append(normalized_filter_name)
            seen_filter_names.add(normalized_filter_name)

    # Keep the top-level enabled flag consistent with the effective active sequence
    normalized_filtering['filter_sequence'] = normalized_filter_sequence
    normalized_filtering['enabled'] = bool(normalized_filtering.get('enabled', False)) and len(normalized_filter_sequence) > 0

    return normalized_filtering


def _normalize_dispersion_curve_toggle(curves_value):

    '''
    Purpose
    -------
    Convert current or historical curve toggles to one enabled flag.

    Inputs
    ------
    curves_value: dict, scalar, or None
        Current enabled flag or historical curve-selection settings.

    Outputs
    -------
    toggle: dict
        Single Boolean enabled value derived from the explicit flag, legacy child flags,
        or scalar truth value.

    Notes
    -----
    Normalize the legacy dispersion-curve toggle to a single enabled flag.
    '''

    # Convert current or historical curve toggles to one enabled flag
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
    komega_comparison = None,
    atmospheric_profiles = None,
    magnetogram_mode = None,
    optimized_filtering = None,
    output = None,
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

    komega_comparison: dict, optional
        Parameters and sampling controls for the eight-row detailed k-omega
        comparison generated with the authoritative Vesa_2026 solver.

    magnetogram_mode: dict, optional
        Optional simulation magnetogram mode settings. Only the `single_cube`
        key is supported. Paired-cube magnetograms are always auto-discovered.

    atmospheric_profiles: dict, optional
        Matched-profile discovery, verified legacy units, gravity in km/s^2,
        and native atmospheric diagnostic settings merged into the defaults.

    optimized_filtering: dict, optional
        Manual/optimized registry selection, optional entry/selection filters,
        and explicit filter overrides. When omitted, supplying filtering selects
        manual mode; otherwise the existing optimized registry mode is retained.

    output: dict, optional
        Output identity options, including explicit model category/field strength
        and selected absolute height coordinates in km.

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
    komega_comparison_config = _deep_merge(default_komega_comparison, komega_comparison)
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
        'optimized_filtering': deepcopy(optimized_filtering if optimized_filtering is not None else
            {'mode': 'manual' if filtering is not None else 'optimized',
             'file': str(Path(__file__).with_name('observation_filter_parameters.json'))}),
        'output': deepcopy(output or {}),
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
        'komega_comparison': komega_comparison_config,
        'atmospheric_profiles': _deep_merge(default_atmospheric_profiles, atmospheric_profiles),
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
    optimized_filtering = {'mode': 'optimized', 'file': str(Path(__file__).with_name('observation_filter_parameters.json'))},
    **(deepcopy(paired_cubes_inputs) if _normalize_source_type(source_type) == 'paired_cubes' else deepcopy(single_cube_inputs)),
    dispersion_curves = deepcopy(dispersion_curve_inputs),
    komega_comparison = deepcopy(komega_comparison_inputs),
    magnetogram_mode = deepcopy(magnetogram_mode),
)
