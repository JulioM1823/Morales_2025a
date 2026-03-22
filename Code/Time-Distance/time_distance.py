# Import the relevant libraries
import argparse
import configparser
import copy
import importlib.util
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
from astropy.io import fits
from tqdm import tqdm

try:
    import netCDF4 as nc
except ModuleNotFoundError:
    nc = None

# Define the global variables for running in parallel
_fft_lower = None
_fft_higher = None
_nx0 = None
_width = None
_extent = None
_dx_pixels = None
_maxpix_geom = None
_annulus_offsets_by_delta = None
_target_bounds_by_delta = None
_extent_size = None


def require_netcdf4():

    '''
    Purpose
    -------
    Raise a clear error when single-cube support is requested without `netCDF4`.

    Inputs
    ------
    None

    Outputs
    -------
    None

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    if nc is None:
        raise ModuleNotFoundError(
            "single_cube mode requires the 'netCDF4' package, but it is not installed in the current Python environment.")


def load_time_distance_config(config_file):

    '''
    Purpose
    -------
    Load the user-defined parameters for the time-distance calculation.

    Inputs
    ------
    config_file: pathlib.Path
        Path to the Python configuration file.

    Outputs
    -------
    config: dict
        Dictionary containing the input paths and calculation parameters.

    Author(s)
    ---------
    Julio M. Morales, March 12th, 2026
    '''

    config_module = load_config_module(config_file)

    if hasattr(config_module, 'get_config'):
        source_type = _normalize_source_type(getattr(config_module, 'source_type', ''))

        if source_type == 'paired_cubes':
            paired_inputs = copy.deepcopy(getattr(config_module, 'paired_cubes_inputs', {}))
            return config_module.get_config(source_type = source_type, **paired_inputs)

        if source_type == 'single_cube':
            single_inputs = copy.deepcopy(getattr(config_module, 'single_cube_inputs', {}))
            return config_module.get_config(source_type = source_type, **single_inputs)

        raise ValueError(
            "config.py exposes get_config(...), but the top-level source_type is invalid. "
            "Expected 'paired_cubes' or 'single_cube'.")

    return config_module.config


def _normalize_source_type(source_type):

    '''
    Purpose
    -------
    Normalize a source-type label to the canonical runtime name.

    Inputs
    ------
    source_type: object
        Raw source-type value from the config module or CLI.

    Outputs
    -------
    normalized_source_type: str
        Canonical source-type label used internally.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    source_type = str(source_type).strip().lower()

    if source_type == 'single_netcdf_cube':
        return 'single_cube'

    return source_type



def _normalize_element(element):

    '''
    Purpose
    -------
    Normalize a spectral-element token to title case.

    Inputs
    ------
    element: object
        Raw element label.

    Outputs
    -------
    normalized_element: str
        Element label with only the first character capitalized.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    if element in ['', None]:
        return ''

    element = str(element).strip()

    if element == '':
        return ''

    return element[0].upper() + element[1:].lower()



def _slugify(value):

    '''
    Purpose
    -------
    Convert a free-form label into a filesystem-friendly slug.

    Inputs
    ------
    value: object
        Raw string-like value to normalize.

    Outputs
    -------
    slug: str
        Lowercase slug with non-alphanumeric runs collapsed to underscores.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    value = str(value).strip().lower()
    value = value.replace('å', 'a')
    value = re.sub(r'angstrom', 'a', value, flags = re.IGNORECASE)
    value = re.sub(r'[^0-9a-z]+', '_', value)
    value = re.sub(r'_+', '_', value)

    return value.strip('_')



def _join_slug(parts):

    '''
    Purpose
    -------
    Join multiple slug fragments while dropping empty entries.

    Inputs
    ------
    parts: iterable
        Slug fragments or raw values.

    Outputs
    -------
    joined_slug: str
        Underscore-delimited slug assembled from the non-empty parts.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Normalize each fragment into slug form and drop whitespace-only entries.
    parts = [_slugify(part) for part in parts if str(part).strip() != '']

    # Drop any fragments that collapsed to an empty slug.
    parts = [part for part in parts if part != '']

    return '_'.join(parts).strip('_')


def _infer_observation_date_object(file_path):

    '''
    Purpose
    -------
    Extract an observation date from a file path when it follows the IBIS naming pattern.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input file path or filename.

    Outputs
    -------
    date_object: datetime.datetime or None
        Parsed observation date, or `None` when no date token is present.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Convert the input into a plain string before searching for the date token.
    file_path = str(file_path)
    match = re.search(r'(\d{1,2}[A-Za-z]{3}\d{4})', file_path)

    # Return `None` when the path does not encode an observation date.
    if match is None:
        return None

    # Parse the extracted token using the IBIS date format.
    return datetime.strptime(match.group(1), '%d%b%Y')



def _load_netcdf_coordinate(variable):

    '''
    Purpose
    -------
    Load a NetCDF coordinate and replace fill-value placeholders with `NaN`.

    Inputs
    ------
    variable: netCDF4.Variable
        Coordinate variable to read.

    Outputs
    -------
    values: np.array, float
        Coordinate values with invalid placeholders converted to `NaN`.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Load the coordinate values as float64 so the later checks behave consistently.
    values = np.asarray(variable[:], dtype = np.float64)
    fill_value = getattr(variable, '_FillValue', None)

    # Replace the declared NetCDF fill value with `NaN`.
    if fill_value is not None:
        values = np.where(values == fill_value, np.nan, values)

    # Treat extremely large placeholder values as invalid coordinates.
    values = np.where(np.abs(values) > 1.0e30, np.nan, values)

    return values



def _convert_netcdf_length_array_to_Mm(values, units, label):

    '''
    Purpose
    -------
    Convert a NetCDF length coordinate into megameters.

    Inputs
    ------
    values: np.array
        Length coordinate values.

    units: str
        Unit string stored in the NetCDF metadata.

    label: str
        Coordinate name used in error messages.

    Outputs
    -------
    values_Mm: np.array, float
        Coordinate values converted to Mm.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Normalize the unit string before matching it to the supported conversions.
    unit = str(units or '').strip().lower()

    # Select the conversion factor that maps the native coordinate units into Mm.
    if unit in ['', 'mm']:
        factor = 1.0
    elif unit == 'cm':
        factor = 1.0e-8
    elif unit == 'm':
        factor = 1.0e-6
    elif unit == 'km':
        factor = 1.0e-3
    else:
        raise ValueError(
            f'Unsupported length unit {units!r} for NetCDF coordinate {label}. '
            f'Use cm, m, km, or Mm.')

    # Apply the unit conversion in a single vectorized operation.
    return np.asarray(values, dtype = np.float64)*factor



def _normalize_single_cube_height_values_km(height_values_km):

    '''
    Purpose
    -------
    Re-reference single-cube heights so the first layer is treated as zero height.

    Inputs
    ------
    height_values_km: np.array
        Physical heights in km.

    Outputs
    -------
    normalized_height_values_km: np.array, float
        Heights shifted so that `xc3[0]` becomes the reference level.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Convert the height coordinate into float64 before checking and shifting it.
    height_values_km = np.asarray(height_values_km, dtype = np.float64)

    # Reject empty coordinate arrays before referencing the first layer.
    if height_values_km.size == 0:
        raise ValueError('Could not normalize single_cube heights because the xc3 coordinate is empty.')

    # Use the first layer as the photospheric reference height.
    photosphere_height_km = float(height_values_km[0])

    # Reject invalid reference heights so all later differences remain physical.
    if not np.isfinite(photosphere_height_km):
        raise ValueError(
            'Could not normalize single_cube heights because xc3[0] is invalid. '
            'The photospheric reference height must be finite.')

    # Shift all heights so the first layer is treated as zero height.
    return height_values_km - photosphere_height_km



def _convert_netcdf_time_array_to_seconds(values, units):

    '''
    Purpose
    -------
    Convert a NetCDF time coordinate into seconds.

    Inputs
    ------
    values: np.array
        Time coordinate values.

    units: str
        Unit string stored in the NetCDF metadata.

    Outputs
    -------
    values_seconds: np.array, float
        Time values converted to seconds.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Normalize the unit string before matching it to the supported conversions.
    unit = str(units or '').strip().lower()

    # Select the conversion factor that maps the native time units into seconds.
    if unit in ['', 's', 'sec', 'secs', 'second', 'seconds']:
        factor = 1.0
    elif unit in ['ms', 'millisecond', 'milliseconds']:
        factor = 1.0e-3
    elif unit in ['min', 'mins', 'minute', 'minutes']:
        factor = 60.0
    elif unit in ['h', 'hr', 'hrs', 'hour', 'hours']:
        factor = 3600.0
    else:
        raise ValueError(
            f'Unsupported time unit {units!r} for the NetCDF time coordinate. '
            f'Use s, ms, min, or h.')

    # Apply the unit conversion in a single vectorized operation.
    return np.asarray(values, dtype = np.float64)*factor



def _infer_uniform_step(values, label):

    '''
    Purpose
    -------
    Infer a uniform sampling step from a finite coordinate array.

    Inputs
    ------
    values: np.array
        Coordinate samples.

    label: str
        Coordinate label used in error messages.

    Outputs
    -------
    reference_step: float
        Inferred uniform sampling interval.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Keep only the finite samples before estimating the coordinate step.
    finite_values = np.asarray(values[np.isfinite(values)], dtype = np.float64)

    # A uniform step cannot be inferred from fewer than two valid samples.
    if finite_values.size < 2:
        raise ValueError(f'Need at least two finite samples to infer {label}.')

    # Compute the nonzero finite step sizes between adjacent samples.
    steps = np.diff(finite_values)
    steps = steps[np.isfinite(steps)]
    steps = steps[np.abs(steps) > 0.0]

    # Reject coordinates that contain only repeated or invalid values.
    if steps.size == 0:
        raise ValueError(f'Could not infer a nonzero step size for {label}.')

    # Use the median absolute step as the reference spacing.
    reference_step = float(np.median(np.abs(steps)))

    # Enforce uniform sampling so the Fourier metadata remain reliable.
    if not np.allclose(np.abs(steps), reference_step, rtol = 1.0e-9, atol = 1.0e-12):
        raise ValueError(f'{label} is not uniformly sampled in the NetCDF file.')

    return reference_step



def infer_netcdf_time_step_seconds(file_path):

    # Require NetCDF support before touching any single-cube files.
    require_netcdf4()

    # Resolve the file path once before checking its existence and opening it.
    file_path = Path(file_path).expanduser().resolve()

    # Reject missing files before trying to open the dataset.
    if not file_path.exists():
        raise FileNotFoundError(f'NetCDF cube file not found: {file_path}')

    # Open the NetCDF file and select the time coordinate used by the cube.
    with nc.Dataset(file_path) as netcdf_file:
        if 'time' in netcdf_file.variables:
            time_variable_name = 'time'
        elif 't' in netcdf_file.variables:
            time_variable_name = 't'
        else:
            raise ValueError(
                f'Could not find a time coordinate in {file_path}. '
                f'Expected a variable named time or t.')

        # Load the coordinate values and convert them into seconds.
        time_variable = netcdf_file.variables[time_variable_name]
        time_values = _load_netcdf_coordinate(time_variable)
        time_seconds = _convert_netcdf_time_array_to_seconds(time_values, getattr(time_variable, 'units', ''))

    # Infer the uniform cadence from the converted time coordinate.
    return _infer_uniform_step(time_seconds, 'dt')



def infer_netcdf_pixel_scale_Mm(file_path):

    # Require NetCDF support before touching any single-cube files.
    require_netcdf4()

    # Resolve the file path once before checking its existence and opening it.
    file_path = Path(file_path).expanduser().resolve()

    # Reject missing files before trying to open the dataset.
    if not file_path.exists():
        raise FileNotFoundError(f'NetCDF cube file not found: {file_path}')

    # Open the NetCDF file and inspect the candidate horizontal coordinate arrays.
    with nc.Dataset(file_path) as netcdf_file:
        horizontal_axes = []
        for axis_name in ['xb1', 'xb2', 'xc1', 'xc2']:

            # Skip coordinate names that are not present in this file.
            if axis_name not in netcdf_file.variables:
                continue

            # Load the current coordinate axis and discard invalid or placeholder values.
            axis_variable = netcdf_file.variables[axis_name]
            axis_values = _load_netcdf_coordinate(axis_variable)

            # Ignore axes that do not contain enough valid samples to define a spacing.
            if np.count_nonzero(np.isfinite(axis_values)) < 2:
                continue

            # Convert the coordinate to Mm and store its inferred step size.
            axis_values_Mm = _convert_netcdf_length_array_to_Mm(axis_values, getattr(axis_variable, 'units', ''), axis_name)
            horizontal_axes.append((axis_name, _infer_uniform_step(axis_values_Mm, axis_name)))

    # Reject files that do not expose any valid horizontal coordinate.
    if len(horizontal_axes) == 0:
        raise ValueError(
            f'Could not infer dx from {file_path}. The NetCDF file does not contain a valid '
            f'horizontal coordinate array in xb1, xb2, xc1, or xc2. '
            f'If this is one of the older uncorrected CO5BOLD files, regenerate it with the '
            f'coordinate-fixing download script first.')

    # Use the first valid horizontal axis as the reference pixel scale.
    dx_Mm = float(horizontal_axes[0][1])

    # Enforce consistent spacing across every valid horizontal coordinate array.
    for axis_name, axis_step in horizontal_axes[1:]:
        if not np.isclose(axis_step, dx_Mm, rtol = 1.0e-9, atol = 1.0e-12):
            raise ValueError(
                f'Horizontal coordinate spacing is inconsistent in {file_path}: '
                f'{horizontal_axes[0][0]} gives {dx_Mm:g} Mm while {axis_name} gives {axis_step:g} Mm.')

    return dx_Mm



def infer_netcdf_sampling(file_path):

    # Resolve the file path once before checking its existence.
    file_path = Path(file_path).expanduser().resolve()

    # Reject missing files before trying to infer any sampling metadata.
    if not file_path.exists():
        raise FileNotFoundError(f'NetCDF cube file not found: {file_path}')

    # Return both the cadence and pixel scale in one convenience dictionary.
    return {
        'dt_seconds': infer_netcdf_time_step_seconds(file_path),
              'dx_Mm': infer_netcdf_pixel_scale_Mm(file_path)}



def infer_netcdf_height_coordinates_km(file_path):

    # Require NetCDF support before touching any single-cube files.
    require_netcdf4()

    # Resolve the file path once before checking its existence and opening it.
    file_path = Path(file_path).expanduser().resolve()

    # Reject missing files before trying to open the dataset.
    if not file_path.exists():
        raise FileNotFoundError(f'NetCDF cube file not found: {file_path}')

    # Open the NetCDF file and load the hardcoded height coordinate used by the pipeline.
    with nc.Dataset(file_path) as netcdf_file:
        if 'xc3' not in netcdf_file.variables:
            raise ValueError(f'Could not find the hardcoded height coordinate xc3 in {file_path}.')

        # Read the coordinate values and preserve the declared units.
        height_variable = netcdf_file.variables['xc3']
        height_values = _load_netcdf_coordinate(height_variable)
        height_units = getattr(height_variable, 'units', '')

    # Keep only the finite samples when checking whether the coordinate is usable.
    finite_values = np.asarray(height_values[np.isfinite(height_values)], dtype = np.float64)

    # Reject files whose height coordinate is entirely missing or invalid.
    if finite_values.size == 0:
        raise ValueError(
            f'Could not infer physical heights from {file_path}. The xc3 coordinate is missing or invalid. '
            f'Regenerate the file with corrected coordinates first.')

    # Convert the height coordinate into km and re-reference it to the first layer.
    height_values_km = _convert_netcdf_length_array_to_Mm(height_values, height_units, 'xc3')*1000.0

    return _normalize_single_cube_height_values_km(height_values_km)



def infer_netcdf_height_pair_km(file_path, h1, h2):

    # Require NetCDF support before touching any single-cube files.
    require_netcdf4()

    # Resolve the file path once before checking its existence and opening it.
    file_path = Path(file_path).expanduser().resolve()

    # Reject missing files before trying to infer any height metadata.
    if not file_path.exists():
        raise FileNotFoundError(f'NetCDF cube file not found: {file_path}')

    # Parse the requested heights as integer layer indices.
    try:
        h1_index = int(str(h1).strip())
        h2_index = int(str(h2).strip())
    except ValueError as exc:
        raise ValueError('single_cube heights must be given as integer z indices in h1 and h2.') from exc

    # Load the full physical height coordinate so the requested layers can be validated.
    height_values_km = infer_netcdf_height_coordinates_km(file_path)

    # Reject layer indices that fall outside the available height range.
    if h1_index < 0 or h1_index >= height_values_km.size:
        raise IndexError(f'h1 = {h1_index} is out of range for xc3 with length {height_values_km.size}.')
    if h2_index < 0 or h2_index >= height_values_km.size:
        raise IndexError(f'h2 = {h2_index} is out of range for xc3 with length {height_values_km.size}.')

    # Reject requested layers whose physical heights are invalid.
    if not np.isfinite(height_values_km[h1_index]) or not np.isfinite(height_values_km[h2_index]):
        raise ValueError(
            f'Could not infer physical heights from {file_path}. The requested xc3 entries for h1 or h2 are invalid.')

    # Return both the indices and their physical heights for downstream metadata.
    return {
        'h1_index': h1_index,
        'h2_index': h2_index,
           'h1_km': float(height_values_km[h1_index]),
           'h2_km': float(height_values_km[h2_index])}


def load_model_atmosphere(model_file):

    '''
    Purpose
    -------
    Load and validate the tabulated model-atmosphere file used by single-cube diagnostics.

    Inputs
    ------
    model_file: str or pathlib.Path
        Path to the model-atmosphere table.

    Outputs
    -------
    atmosphere: dict
        Dictionary containing the sorted atmospheric profiles and derived sound speed in km s^-1.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Resolve the model-atmosphere path once before loading it from disk.
    model_file = Path(model_file).expanduser().resolve()

    # Reject missing model tables before trying to read them.
    if not model_file.exists():
        raise FileNotFoundError(f'Model atmosphere file not found: {model_file}')

    # Load the full atmosphere table as float64 for consistent interpolation.
    model_data = np.loadtxt(model_file, dtype = np.float64)

    # Promote single-row files to 2D so the column checks remain valid.
    if model_data.ndim == 1:
        model_data = model_data[np.newaxis, :]

    # Enforce the expected column count used by the later diagnostics.
    if model_data.ndim != 2 or model_data.shape[1] < 6:
        raise ValueError(
            f'Model atmosphere file {model_file} must contain at least six columns: '
            f'height, gravity, dP/dz, density, dRho/dz, and sound speed.')

    # Split the table into named atmospheric profiles.
    atmosphere = {
                    'file': str(model_file),
               'height_Mm': np.asarray(model_data[:, 0], dtype = np.float64),
            'gravity_cgs': np.asarray(model_data[:, 1], dtype = np.float64),
                 'dP_dz': np.asarray(model_data[:, 2], dtype = np.float64),
           'density_cgs': np.asarray(model_data[:, 3], dtype = np.float64),
               'dRho_dz': np.asarray(model_data[:, 4], dtype = np.float64),
       'sound_speed_cgs': np.asarray(model_data[:, 5], dtype = np.float64)}

    # Add the sound speed in km s^-1 for downstream reporting.
    atmosphere['sound_speed_km_s'] = atmosphere['sound_speed_cgs']*1.0e-5

    # Keep only the finite heights when validating the sampled range.
    finite_heights = np.asarray(atmosphere['height_Mm'][np.isfinite(atmosphere['height_Mm'])], dtype = np.float64)
    if finite_heights.size < 2:
        raise ValueError(f'Model atmosphere file {model_file} must contain at least two finite heights.')

    # Sort every atmospheric profile by height before interpolating it.
    sort_order = np.argsort(atmosphere['height_Mm'])
    for key in ['height_Mm', 'gravity_cgs', 'dP_dz', 'density_cgs', 'dRho_dz', 'sound_speed_cgs', 'sound_speed_km_s']:
        atmosphere[key] = np.asarray(atmosphere[key][sort_order], dtype = np.float64)

    # Enforce strictly increasing heights after sorting.
    if np.any(np.diff(atmosphere['height_Mm']) <= 0.0):
        raise ValueError(
            f'Model atmosphere file {model_file} must have strictly increasing heights after sorting.')

    return atmosphere


def interpolate_model_atmosphere_to_single_cube_layers(model_file, cube_file):

    '''
    Purpose
    -------
    Interpolate a model atmosphere onto the height layers of a single NetCDF cube.

    Inputs
    ------
    model_file: str or pathlib.Path
        Path to the model-atmosphere table.

    cube_file: str or pathlib.Path
        Path to the single-cube NetCDF file.

    Outputs
    -------
    interpolated_atmosphere: dict
        Layer-by-layer atmospheric properties sampled at the cube heights.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Load the source atmosphere and the target single-cube heights.
    atmosphere = load_model_atmosphere(model_file)
    layer_heights_km = infer_netcdf_height_coordinates_km(cube_file)
    layer_heights_Mm = np.asarray(layer_heights_km, dtype = np.float64)/1000.0

    # Keep only the finite target heights when checking the interpolation range.
    finite_layer_heights = np.asarray(layer_heights_Mm[np.isfinite(layer_heights_Mm)], dtype = np.float64)
    if finite_layer_heights.size == 0:
        raise ValueError(f'Could not infer any finite single_cube heights from {cube_file}.')

    # Store the valid interpolation range of the model atmosphere.
    min_height_Mm = float(np.min(atmosphere['height_Mm']))
    max_height_Mm = float(np.max(atmosphere['height_Mm']))

    # Reject single-cube layers that fall outside the tabulated atmosphere.
    if np.min(finite_layer_heights) < min_height_Mm - 1.0e-12 or np.max(finite_layer_heights) > max_height_Mm + 1.0e-12:
        raise ValueError(
            f'Single-cube heights from {cube_file} fall outside the model-atmosphere range '
            f'[{min_height_Mm:g}, {max_height_Mm:g}] Mm.')

    # Interpolate the density and sound speed onto the single-cube layers.
    density_cgs = np.interp(layer_heights_Mm, atmosphere['height_Mm'], atmosphere['density_cgs'])
    sound_speed_cgs = np.interp(layer_heights_Mm, atmosphere['height_Mm'], atmosphere['sound_speed_cgs'])

    # Return the interpolated atmosphere in the format expected by the pipeline.
    return {
         'model_atmosphere_file': atmosphere['file'],
                'layer_index': [int(value) for value in range(layer_heights_Mm.size)],
                  'height_km': [float(value) for value in layer_heights_km],
                  'height_Mm': [float(value) for value in layer_heights_Mm],
               'density_cgs': [float(value) for value in density_cgs],
           'sound_speed_cgs': [float(value) for value in sound_speed_cgs],
          'sound_speed_km_s': [float(value)*1.0e-5 for value in sound_speed_cgs]}


def compute_alfven_speed_cgs(field_strength_G, density_cgs, magnetic_permeability = 4.0*np.pi):

    '''
    Purpose
    -------
    Compute the Alfven speed in cgs units.

    Inputs
    ------
    field_strength_G: float
        Magnetic-field strength in Gauss.

    density_cgs: float
        Mass density in g cm^-3.

    magnetic_permeability: float, optional
        Magnetic permeability factor in cgs units.

    Outputs
    -------
    alfven_speed_cgs: float
        Alfven speed in cm s^-1, or `NaN` when the inputs are invalid.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Return `NaN` immediately when the caller did not provide valid inputs.
    if field_strength_G in ['', None] or density_cgs in ['', None]:
        return np.nan

    # Cast the inputs to float before checking their validity.
    field_strength_G = float(field_strength_G)
    density_cgs = float(density_cgs)
    magnetic_permeability = float(magnetic_permeability)

    # Reject non-finite inputs before evaluating the square root.
    if not np.isfinite(field_strength_G) or not np.isfinite(density_cgs) or not np.isfinite(magnetic_permeability):
        return np.nan

    # Reject non-physical density or permeability values.
    if density_cgs <= 0.0 or magnetic_permeability <= 0.0:
        return np.nan

    # Evaluate the Alfven speed in cgs units.
    return field_strength_G/np.sqrt(magnetic_permeability*density_cgs)


def summarize_single_cube_alfven_sound_ratio(single_cube_model_atmosphere, lower_height_index, upper_height_index, mean_field_strength_G):

    '''
    Purpose
    -------
    Summarize the mean Alfven-to-sound-speed ratio across the selected single-cube height range.

    Inputs
    ------
    single_cube_model_atmosphere: dict
        Interpolated model-atmosphere metadata for the single cube.

    lower_height_index: int
        Lower bound of the selected height range.

    upper_height_index: int
        Upper bound of the selected height range.

    mean_field_strength_G: float
        Mean magnetic-field strength between the selected heights.

    Outputs
    -------
    summary: dict
        Dictionary containing the averaged density, sound speed, Alfven speed, and their ratio.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Return an empty summary when the optional atmosphere metadata are unavailable.
    if single_cube_model_atmosphere in ['', None]:
        return {}

    # Normalize the requested height range so the lower index always comes first.
    lower_height_index = int(lower_height_index)
    upper_height_index = int(upper_height_index)
    lower_height_index, upper_height_index = min(lower_height_index, upper_height_index), max(lower_height_index, upper_height_index)

    # Load the interpolated density and sound-speed profiles for the single cube.
    density_cgs = np.asarray(single_cube_model_atmosphere.get('density_cgs', []), dtype = np.float64)
    sound_speed_cgs = np.asarray(single_cube_model_atmosphere.get('sound_speed_cgs', []), dtype = np.float64)

    # Return an empty summary when the atmosphere metadata are incomplete.
    if density_cgs.size == 0 or sound_speed_cgs.size == 0:
        return {}
    if upper_height_index >= density_cgs.size or upper_height_index >= sound_speed_cgs.size:
        return {}

    # Extract the selected height range and keep only finite positive values.
    density_window = density_cgs[lower_height_index:upper_height_index + 1]
    sound_speed_window = sound_speed_cgs[lower_height_index:upper_height_index + 1]
    finite_density = density_window[np.isfinite(density_window) & (density_window > 0.0)]
    finite_sound_speed = sound_speed_window[np.isfinite(sound_speed_window) & (sound_speed_window > 0.0)]

    # Return an empty summary when the selected height range is unusable.
    if finite_density.size == 0 or finite_sound_speed.size == 0:
        return {}

    # Average the plasma properties across the selected height range.
    mean_density_cgs = float(np.nanmean(finite_density))
    mean_sound_speed_cgs = float(np.nanmean(finite_sound_speed))
    alfven_speed_cgs = float(compute_alfven_speed_cgs(mean_field_strength_G, mean_density_cgs))

    # Compute the Alfven-to-sound-speed ratio only when both speeds are valid.
    if not np.isfinite(alfven_speed_cgs) or mean_sound_speed_cgs <= 0.0:
        alfven_to_sound_speed_ratio = np.nan
    else:
        alfven_to_sound_speed_ratio = float(alfven_speed_cgs/mean_sound_speed_cgs)

    # Return the averaged plasma diagnostics for later metadata export.
    return {
                 'height_index_range': [lower_height_index, upper_height_index],
       'mean_field_strength_G_between_heights': float(mean_field_strength_G),
           'mean_density_cgs_between_heights': mean_density_cgs,
       'mean_sound_speed_cgs_between_heights': mean_sound_speed_cgs,
      'mean_sound_speed_km_s_between_heights': mean_sound_speed_cgs*1.0e-5,
                       'alfven_speed_cgs': alfven_speed_cgs,
                      'alfven_speed_km_s': alfven_speed_cgs*1.0e-5 if np.isfinite(alfven_speed_cgs) else np.nan,
             'alfven_to_sound_speed_ratio': alfven_to_sound_speed_ratio}


def compute_phase_difference_correction(dtau_seconds, positive_frequency_count, mid_space, dt_seconds):

    '''
    Purpose
    -------
    Compute the linear phase-delay correction used in the original k-omega notebook.

    Inputs
    ------
    dtau_seconds: float
        Time delay between the two observables in seconds.

    positive_frequency_count: int
        Number of non-negative temporal frequencies retained in the azimuthal average.

    mid_space: int
        Number of positive horizontal-wavenumber bins.

    dt_seconds: float
        Cadence of the time series in seconds.

    Outputs
    -------
    phase_correction: np.array, float
        Correction array in radians with shape [mid_space, positive_frequency_count].

    Author(s)
    ---------
    Julio M. Morales, March 20th, 2026
    '''

    # Convert the cadence into the Nyquist angular frequency.
    omega_nyquist = np.pi/float(dt_seconds)

    # Match the original notebook exactly: construct the correction with
    # mid_time + 1 samples, then retain the same positive-frequency subset
    # used in the plotted/saved azimuthal average.
    phase_row_full = (
        np.linspace(0.0, omega_nyquist, int(positive_frequency_count) + 1, endpoint = True)
        * float(dtau_seconds)
    )
    phase_row = phase_row_full[:int(positive_frequency_count)]

    # Replicate the one-dimensional correction over the retained radial bins.
    return np.tile(phase_row, (int(mid_space), 1))


def build_komega_axes(cube_shape, dt_seconds, dx_Mm):

    '''
    Purpose
    -------
    Reconstruct the positive k and nu axes used by the original FFT notebook.

    Inputs
    ------
    cube_shape: tuple
        Cube shape in [t, y, x] order.

    dt_seconds: float
        Cadence of the time series in seconds.

    dx_Mm: float
        Spatial sampling in Mm per pixel.

    Outputs
    -------
    axes: dict
        Dictionary containing the k_h and nu axes plus their pixel-edge limits.

    Author(s)
    ---------
    Julio M. Morales, March 20th, 2026
    '''

    # Read the cube dimensions and keep the smaller horizontal extent for radial averaging.
    nt, ny, nx = [int(value) for value in cube_shape]
    end_time = nt
    end_space = min(nx, ny)
    mid_time = end_time // 2
    mid_space = end_space // 2
    positive_frequency_count = end_time - mid_time

    # Compute the Nyquist scales in wavenumber and temporal frequency.
    k_nyquist = np.pi/float(dx_Mm)
    nu_nyquist = (np.pi/float(dt_seconds))/(2.0*np.pi)*1.0e3

    # Reconstruct the positive axes used by the notebook products.
    k_axis = np.linspace(0.0, k_nyquist, mid_space, endpoint = True, dtype = np.float64)
    nu_axis = np.linspace(0.0, nu_nyquist, positive_frequency_count, endpoint = True, dtype = np.float64)

    # Infer the pixel spacing on each axis so the saved plots can recover their edges.
    if k_axis.size > 1:
        k_step = float(np.median(np.diff(k_axis)))
    else:
        k_step = float(k_nyquist if k_nyquist > 0.0 else 1.0)

    if nu_axis.size > 1:
        nu_step = float(np.median(np.diff(nu_axis)))
    else:
        nu_step = float(nu_nyquist if nu_nyquist > 0.0 else 1.0)

    # Return both the axes and the half-pixel limits used for plotting.
    return {
        'k_axis': k_axis,
        'nu_axis': nu_axis,
        'mid_space': mid_space,
        'positive_frequency_count': positive_frequency_count,
        'k_limits': (float(k_axis[0] - 0.5*k_step), float(k_axis[-1] + 0.5*k_step)),
        'nu_limits': (float(nu_axis[0] - 0.5*nu_step), float(nu_axis[-1] + 0.5*nu_step))}


def build_coherence_axes(cube_shape, dt_seconds, dx_Mm):

    '''
    Purpose
    -------
    Reconstruct the positive k and nu axes used by the Oana running-difference
    coherence calculation.

    Inputs
    ------
    cube_shape: tuple
        Running-difference cube shape in [t, y, x] order.

    dt_seconds: float
        Cadence of the time series in seconds.

    dx_Mm: float
        Spatial sampling in Mm per pixel.

    Outputs
    -------
    axes: dict
        Dictionary containing the k_h and nu axes used by the saved coherence product.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    # Read the cube dimensions and keep the smaller horizontal extent for radial averaging.
    nt, ny, nx = [int(value) for value in cube_shape]
    end_space = min(nx, ny)
    mid_space = end_space // 2
    mid_time = nt // 2

    # Compute the Nyquist scales in wavenumber and temporal frequency.
    k_nyquist = np.pi/float(dx_Mm)
    nu_nyquist = (np.pi/float(dt_seconds))/(2.0*np.pi)*1.0e3

    # Reconstruct the positive axes used by the coherence product.
    k_axis = np.linspace(0.0, k_nyquist, mid_space, endpoint = True, dtype = np.float64)
    nu_axis = np.linspace(0.0, nu_nyquist, mid_time, endpoint = True, dtype = np.float64)

    # Return both the axes and their key dimensions.
    return {
        'k_axis': k_axis,
        'nu_axis': nu_axis,
        'mid_space': mid_space,
        'mid_time': mid_time}


def build_kh_nu_fits_header(k_axis, nu_axis, dx_Mm, dt_seconds, bunit, bunit_comment):

    '''
    Purpose
    -------
    Build a standard FITS header for saved k_h-nu data products.

    Inputs
    ------
    k_axis: np.array, float
        Horizontal-wavenumber axis in 1/Mm.

    nu_axis: np.array, float
        Temporal-frequency axis in mHz.

    dx_Mm: float
        Spatial sampling in Mm per pixel.

    dt_seconds: float
        Temporal cadence in seconds.

    bunit: str
        FITS BUNIT value.

    bunit_comment: str
        FITS BUNIT comment.

    Outputs
    -------
    header: astropy.io.fits.Header
        Header containing the shared axis metadata.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    # Start from a blank FITS header and populate the shared axis metadata.
    header = fits.Header()
    header['BUNIT'] = (str(bunit), str(bunit_comment))
    header['CTYPE1'] = ('KH', 'Horizontal wavenumber')
    header['CUNIT1'] = ('1/Mm', 'Horizontal-wavenumber units')
    header['CTYPE2'] = ('NU', 'Temporal frequency')
    header['CUNIT2'] = ('mHz', 'Temporal-frequency units')
    header['CRPIX1'] = 1.0
    header['CRPIX2'] = 1.0
    header['CRVAL1'] = float(k_axis[0]) if np.asarray(k_axis).size > 0 else 0.0
    header['CRVAL2'] = float(nu_axis[0]) if np.asarray(nu_axis).size > 0 else 0.0
    # Store the axis increments only when more than one sample is available.
    if np.asarray(k_axis).size > 1:
        header['CDELT1'] = float(np.median(np.diff(k_axis)))
    if np.asarray(nu_axis).size > 1:
        header['CDELT2'] = float(np.median(np.diff(nu_axis)))

    # Store the original spatial and temporal sampling for downstream recovery.
    header['DX_MM'] = float(dx_Mm)
    header['DT_S'] = float(dt_seconds)

    return header


def _extract_netcdf_height_slice(variable, axis_order, height_index):

    '''
    Purpose
    -------
    Extract a single height plane from a 4D NetCDF variable and reorder it to `[t, y, x]`.

    Inputs
    ------
    variable: netCDF4.Variable
        4D field variable.

    axis_order: dict
        Mapping from logical axis names to integer axis positions.

    height_index: int
        Requested z-index.

    Outputs
    -------
    slice_data: np.array, float
        Extracted height slice in `[t, y, x]` order.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Build an all-slice selection and then replace the height axis with the requested index.
    selection = [slice(None)]*variable.ndim
    selection[int(axis_order['z'])] = int(height_index)

    # Extract the requested height plane as float64.
    slice_data = np.asarray(variable[tuple(selection)], dtype = np.float64)

    # Track the remaining logical axes so the slice can be reordered to [t, y, x].
    remaining_axes = [
        logical_axis
        for _, logical_axis in sorted(
            ((original_axis, logical_axis) for logical_axis, original_axis in axis_order.items() if logical_axis != 'z'),
            key = lambda item: item[0])]
    transpose_order = tuple(remaining_axes.index(axis_name) for axis_name in ['t', 'y', 'x'])

    # Reorder the extracted slice into the pipeline's standard cube layout.
    return np.transpose(slice_data, transpose_order)



def derive_magnetic_orientation_epsilon(*field_components):

    '''
    Purpose
    -------
    Derive a stable minimum field-strength threshold for magnetic-orientation diagnostics.

    Inputs
    ------
    field_components: tuple
        Magnetic-field component arrays.

    Outputs
    -------
    magnitude_epsilon: float
        Small positive threshold used to reject nearly zero field magnitudes.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Collect the largest finite magnitude found in each component array.
    finite_maxima = []

    for component in field_components:

        # Convert each component to float64 before checking its finite range.
        component = np.asarray(component, dtype = np.float64)
        finite_component = component[np.isfinite(component)]

        # Skip arrays that contain no finite values.
        if finite_component.size == 0:
            continue

        # Store the maximum absolute field strength for this component.
        finite_maxima.append(float(np.nanmax(np.abs(finite_component))))

    # Fall back to a conservative floor when no finite values are present.
    if len(finite_maxima) == 0:
        return 1.0e-12

    # Scale the epsilon to the largest finite field magnitude.
    scale = max(1.0, max(finite_maxima))

    return max(1.0e-12, 128.0*np.finfo(np.float64).eps*scale)



def compute_magnetic_orientation_angles(bx, by, bz, magnitude_epsilon = None):

    '''
    Purpose
    -------
    Compute inclination and azimuth angles from three magnetic-field components.

    Inputs
    ------
    bx, by, bz: np.array
        Magnetic-field components with matching shapes.

    magnitude_epsilon: float, optional
        Minimum magnitude used to define valid angle measurements.

    Outputs
    -------
    orientation: dict
        Dictionary containing the inclination, azimuth, field magnitude, and validity masks.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Convert every field component to float64 before comparing shapes or magnitudes.
    bx = np.asarray(bx, dtype = np.float64)
    by = np.asarray(by, dtype = np.float64)
    bz = np.asarray(bz, dtype = np.float64)

    # Enforce a shared geometry so the angle calculations remain pointwise.
    if bx.shape != by.shape or bx.shape != bz.shape:
        raise ValueError(
            'Magnetic-field components must have the same shape to compute the orientation diagnostics.')

    # Derive or validate the minimum field-strength threshold used to define valid angles.
    if magnitude_epsilon in ['', None]:
        magnitude_epsilon = derive_magnetic_orientation_epsilon(bx, by, bz)
    else:
        magnitude_epsilon = max(float(magnitude_epsilon), 0.0)

    # Allocate the output angle arrays and the supporting magnitude fields.
    theta_deg = np.full(bx.shape, np.nan, dtype = np.float64)
    phi_deg = np.full(bx.shape, np.nan, dtype = np.float64)
    field_magnitude = np.sqrt(bx*bx + by*by + bz*bz)
    horizontal_magnitude = np.hypot(bx, by)

    # Define where the inclination and azimuth are numerically meaningful.
    valid_theta = np.isfinite(field_magnitude) & (field_magnitude > magnitude_epsilon)
    valid_phi = valid_theta & np.isfinite(horizontal_magnitude) & (horizontal_magnitude > magnitude_epsilon)

    # Compute the inclination and azimuth only on the valid subsets.
    with np.errstate(invalid = 'ignore', divide = 'ignore'):
        theta_deg[valid_theta] = np.rad2deg(
            np.arccos(np.clip(bz[valid_theta]/field_magnitude[valid_theta], -1.0, 1.0)))
        phi_deg[valid_phi] = np.rad2deg(np.arctan2(by[valid_phi], bx[valid_phi]))

    # Return both the angles and the validity information used to derive them.
    return {
              'theta_deg': theta_deg,
                'phi_deg': phi_deg,
        'field_magnitude': field_magnitude,
          'valid_theta': valid_theta,
            'valid_phi': valid_phi,
     'magnitude_epsilon': float(magnitude_epsilon)}



def circular_mean_degrees(values_deg):

    '''
    Purpose
    -------
    Compute the circular mean of angular samples expressed in degrees.

    Inputs
    ------
    values_deg: np.array
        Angle samples in degrees.

    Outputs
    -------
    mean_deg: float
        Circular mean in degrees, or `NaN` when the result is undefined.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Convert the input angles to float64 and drop invalid samples.
    values_deg = np.asarray(values_deg, dtype = np.float64)
    finite_values = values_deg[np.isfinite(values_deg)]

    # Return `NaN` when there are no valid angles to average.
    if finite_values.size == 0:
        return np.nan

    # Convert to radians and compute the mean unit-vector components.
    finite_radians = np.deg2rad(finite_values)
    mean_sin = float(np.mean(np.sin(finite_radians)))
    mean_cos = float(np.mean(np.cos(finite_radians)))
    mean_resultant = np.hypot(mean_sin, mean_cos)

    # Return `NaN` when the circular mean is undefined.
    if mean_resultant <= 1.0e-12:
        return np.nan

    # Convert the mean direction back into degrees.
    mean_deg = float(np.rad2deg(np.arctan2(mean_sin, mean_cos)))

    # Snap the wrapped -180 value to +180 for stable presentation.
    if np.isclose(mean_deg, -180.0, rtol = 0.0, atol = 1.0e-12):
        return 180.0

    return mean_deg



def _format_orientation_height_label(height_km, height_index):

    '''
    Purpose
    -------
    Format a compact height label for the magnetic-orientation validation plots.

    Inputs
    ------
    height_km: float
        Physical height in km.

    height_index: int
        Fallback layer index.

    Outputs
    -------
    height_label: str
        Display label for the selected height.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Fall back to the layer index when no physical height is available.
    if height_km in ['', None] or not np.isfinite(height_km):
        return f'z = {int(height_index)}'

    # Format the physical height compactly while preserving integer labels when possible.
    height_km = float(height_km)
    if height_km.is_integer():
        return f'{int(height_km)} km'

    return f'{height_km:g} km'



def summarize_magnetic_orientation(theta_deg, phi_deg, height_indices, height_values_km = None, magnitude_epsilon = None):

    '''
    Purpose
    -------
    Summarize magnetic-orientation diagnostics across the selected height layers.

    Inputs
    ------
    theta_deg: np.array
        Inclination-angle cube with shape `[height, time, y, x]`.

    phi_deg: np.array
        Azimuth-angle cube with shape `[height, time, y, x]`.

    height_indices: iterable
        Height indices represented in the diagnostic arrays.

    height_values_km: iterable, optional
        Physical heights associated with `height_indices`.

    magnitude_epsilon: float, optional
        Minimum field magnitude used when computing valid angles.

    Outputs
    -------
    summary: dict
        Mean angles and valid-pixel fractions for each requested height.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Convert the angle cubes to float64 before validating and averaging them.
    theta_deg = np.asarray(theta_deg, dtype = np.float64)
    phi_deg = np.asarray(phi_deg, dtype = np.float64)

    # Enforce the shared shape required for pointwise angle summaries.
    if theta_deg.shape != phi_deg.shape:
        raise ValueError('theta_deg and phi_deg must have the same shape.')
    if theta_deg.ndim != 4:
        raise ValueError(
            'Magnetic-orientation diagnostics must be summarized from arrays with shape [height, time, y, x].')

    # Fall back to NaN heights when no physical heights were provided.
    if height_values_km in ['', None]:
        height_values_km = [np.nan]*theta_deg.shape[0]

    # Initialize the per-height summary lists.
    theta_means_deg = []
    phi_means_deg = []
    theta_valid_fraction = []
    phi_valid_fraction = []

    # Loop through each selected height and summarize its angle statistics.
    for height_position in range(theta_deg.shape[0]):
        theta_panel = theta_deg[height_position]
        phi_panel = phi_deg[height_position]
        finite_theta = np.isfinite(theta_panel)
        finite_phi = np.isfinite(phi_panel)

        # Average the inclination only when the current panel contains valid data.
        if np.any(finite_theta):
            theta_means_deg.append(float(np.nanmean(theta_panel)))
        else:
            theta_means_deg.append(np.nan)

        # Compute the circular azimuth mean and the valid-data fractions.
        phi_means_deg.append(float(circular_mean_degrees(phi_panel)))
        theta_valid_fraction.append(float(np.count_nonzero(finite_theta))/float(theta_panel.size))
        phi_valid_fraction.append(float(np.count_nonzero(finite_phi))/float(phi_panel.size))

    # Return the summarized per-height orientation metadata.
    return {
              'height_indices': [int(value) for value in height_indices],
           'height_values_km': [float(value) if value not in ['', None] and np.isfinite(value) else np.nan for value in height_values_km],
            'theta_means_deg': theta_means_deg,
              'phi_means_deg': phi_means_deg,
       'theta_valid_fraction': theta_valid_fraction,
         'phi_valid_fraction': phi_valid_fraction,
         'phi_mean_method': 'circular',
       'magnitude_epsilon': np.nan if magnitude_epsilon in ['', None] else float(magnitude_epsilon)}



def save_magnetic_orientation_validation_plot(theta_snapshots_deg, phi_snapshots_deg, metadata, output_file):

    '''
    Purpose
    -------
    Save a validation plot for the magnetic-orientation snapshots.

    Inputs
    ------
    theta_snapshots_deg: np.array
        Inclination snapshots with shape `[height, y, x]`.

    phi_snapshots_deg: np.array
        Azimuth snapshots with shape `[height, y, x]`.

    metadata: dict
        Summary metadata used to annotate the plot.

    output_file: str or pathlib.Path
        Destination image file.

    Outputs
    -------
    output_file: pathlib.Path
        Saved plot path.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Import matplotlib lazily so the pipeline only requires it when plotting.
    try:
        import matplotlib
        matplotlib.use('Agg', force = True)
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "single_cube magnetic-orientation validation plots require the 'matplotlib' package.") from exc

    # Convert the validation snapshots to float64 before plotting them.
    theta_snapshots_deg = np.asarray(theta_snapshots_deg, dtype = np.float64)
    phi_snapshots_deg = np.asarray(phi_snapshots_deg, dtype = np.float64)

    # Enforce the expected `[height, y, x]` snapshot layout.
    if theta_snapshots_deg.shape != phi_snapshots_deg.shape:
        raise ValueError('Theta and phi validation snapshots must have the same shape.')
    if theta_snapshots_deg.ndim != 3:
        raise ValueError(
            'Validation snapshots must have shape [height, y, x] before plotting.')

    # Resolve the output path and create its parent directory before saving the figure.
    output_file = Path(output_file).expanduser()
    output_file.parent.mkdir(parents = True, exist_ok = True)

    # Load the metadata used to annotate each panel.
    height_indices = metadata.get('height_indices', list(range(theta_snapshots_deg.shape[0])))
    height_values_km = metadata.get('height_values_km', [np.nan]*theta_snapshots_deg.shape[0])
    theta_means_deg = metadata.get('theta_means_deg', [np.nan]*theta_snapshots_deg.shape[0])
    phi_means_deg = metadata.get('phi_means_deg', [np.nan]*theta_snapshots_deg.shape[0])
    theta_valid_fraction = metadata.get('theta_valid_fraction', [0.0]*theta_snapshots_deg.shape[0])
    phi_valid_fraction = metadata.get('phi_valid_fraction', [0.0]*theta_snapshots_deg.shape[0])
    snapshot_time_index = int(metadata.get('validation_time_index', 0))

    # Disable TeX inside the plotting context to keep the validation plot self-contained.
    with matplotlib.rc_context({'text.usetex': False}):
        fig, axes = plt.subplots(theta_snapshots_deg.shape[0], 2, figsize = (10.0, 4.25*theta_snapshots_deg.shape[0]), constrained_layout = True)
        axes = np.asarray(axes, dtype = object)

        # Promote the axes array to 2D when only one height is plotted.
        if axes.ndim == 1:
            axes = axes[np.newaxis, :]

        # Track the image handles so shared colorbars can be added later.
        theta_image = None
        phi_image = None

        # Build one row per height, with theta on the left and phi on the right.
        for height_position in range(theta_snapshots_deg.shape[0]):
            height_label = _format_orientation_height_label(height_values_km[height_position], height_indices[height_position])
            theta_ax = axes[height_position, 0]
            phi_ax = axes[height_position, 1]

            # Draw the inclination and azimuth snapshots with fixed physical ranges.
            theta_image = theta_ax.imshow(
                theta_snapshots_deg[height_position],
                origin = 'lower',
                cmap = 'cividis',
                vmin = 0.0,
                vmax = 180.0)
            phi_image = phi_ax.imshow(
                phi_snapshots_deg[height_position],
                origin = 'lower',
                cmap = 'twilight_shifted',
                vmin = -180.0,
                vmax = 180.0)

            theta_ax.set_title(
                f"{height_label}: theta | <theta> = {theta_means_deg[height_position]:.1f} deg | valid = {100.0*theta_valid_fraction[height_position]:.1f} pct")
            phi_ax.set_title(
                f"{height_label}: phi | <phi> = {phi_means_deg[height_position]:.1f} deg | valid = {100.0*phi_valid_fraction[height_position]:.1f} pct")

            # Label both panels with pixel coordinates for quick visual inspection.
            for ax in [theta_ax, phi_ax]:
                ax.set_xlabel('x pixel')
                ax.set_ylabel('y pixel')

        # Add shared colorbars and the global figure title before saving.
        fig.colorbar(theta_image, ax = axes[:, 0], label = 'Inclination angle [deg]', shrink = 0.92)
        fig.colorbar(phi_image, ax = axes[:, 1], label = 'Azimuth angle [deg]', shrink = 0.92)
        fig.suptitle(f'Magnetic orientation validation | t index = {snapshot_time_index}', y = 1.02)
        fig.savefig(output_file, dpi = 200, bbox_inches = 'tight')
        plt.close(fig)

    return output_file


def build_radial_bin_lookup(radial_meshgrid):

    '''
    Purpose
    -------
    Precompute rounded radial-bin indices and counts for azimuthal averages.

    Inputs
    ------
    radial_meshgrid: np.array, float
        Radial-distance mesh used to define the annuli.

    Outputs
    -------
    radial_bins: np.array, int
        Rounded radial-bin index for each spatial pixel.

    flat_bins: np.array, int
        Flattened radial-bin indices in C order.

    counts: np.array, float
        Pixel counts for each rounded radial bin.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    # Round the radial mesh to the nearest integer bin index.
    radial_bins = np.floor(np.asarray(radial_meshgrid, dtype = np.float64) + 0.5).astype(np.int64)

    # Flatten the bin lookup in C order to match later flattened FFT slices.
    flat_bins = radial_bins.ravel(order = 'C')

    # Count how many pixels contribute to each radial bin.
    counts = np.bincount(flat_bins, minlength = int(flat_bins.max()) + 1).astype(np.float64)

    return radial_bins, flat_bins, counts


def azimuthal_average_positive_frequency_slices(array, mid_time, mid_space, flat_bins, counts):

    '''
    Purpose
    -------
    Azimuthally average the positive-frequency half of a 3D FFT cube.

    Inputs
    ------
    array: np.array
        Real or complex FFT cube in [x, y, nu] order.

    mid_time: int
        Index of the zero-frequency plane in the shifted FFT cube.

    mid_space: int
        Number of positive radial bins to retain.

    flat_bins: np.array, int
        Flattened radial-bin indices in C order.

    counts: np.array, float
        Pixel counts for each rounded radial bin.

    Outputs
    -------
    azimuthal_average: np.array
        Azimuthally averaged positive-frequency cube in [k_h, nu] order.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    # Determine the positive-frequency size and the valid radial-bin counts.
    positive_frequency_count = int(array.shape[2] - mid_time)
    valid_counts = np.asarray(counts[1:mid_space + 1], dtype = np.float64)
    is_complex = np.iscomplexobj(array)
    output_dtype = np.complex128 if is_complex else np.float64

    # Allocate the output array using a dtype that matches the input cube.
    azimuthal_average = np.zeros((mid_space, positive_frequency_count), dtype = output_dtype)

    # Loop over the retained positive-frequency slices.
    for ifreq, cube_index in enumerate(range(int(mid_time), int(array.shape[2]))):

        # Flatten the current FFT slice in the same C order as the radial lookup.
        flat_slice = np.asarray(array[:, :, cube_index]).ravel(order = 'C')

        # Accumulate the radial-bin sums separately for the real and imaginary parts when needed.
        if is_complex:
            real_sums = np.bincount(flat_bins, weights = flat_slice.real, minlength = counts.size).astype(np.float64)
            imag_sums = np.bincount(flat_bins, weights = flat_slice.imag, minlength = counts.size).astype(np.float64)
            radial_sums = real_sums + 1j*imag_sums
        else:
            radial_sums = np.bincount(flat_bins, weights = flat_slice, minlength = counts.size).astype(np.float64)

        # Divide the radial sums by the bin populations to obtain the azimuthal mean.
        valid_sums = radial_sums[1:mid_space + 1]
        azimuthal_average[:, ifreq] = np.divide(
            valid_sums,
            valid_counts,
            out = np.zeros_like(valid_sums, dtype = output_dtype),
            where = valid_counts > 0.0)

    return azimuthal_average


def azimuthal_average_fft_phase(phase_cube):

    '''
    Purpose
    -------
    Azimuthally average the positive-frequency half of a 3D FFT phase cube.

    Inputs
    ------
    phase_cube: np.array, float
        FFT phase cube in [x, y, nu] order after fftshift.

    Outputs
    -------
    azimuthal_average: np.array, float
        Azimuthally averaged phase array in [k_h, nu] order.

    radial_bins: np.array, int
        Rounded radial-bin index for each spatial pixel.

    Author(s)
    ---------
    Julio M. Morales, March 20th, 2026
    '''

    # Read the phase-cube dimensions and derive the positive-frequency geometry.
    nx, ny, nt = phase_cube.shape
    end_space = min(nx, ny)
    mid_space = end_space // 2
    mid_time = nt // 2

    # Build the centered pixel grid used to define the radial bins.
    x = np.linspace(-nx // 2, nx // 2 - 1, nx, dtype = np.float64)
    y = np.linspace(-ny // 2, ny // 2 - 1, ny, dtype = np.float64)
    x_grid, y_grid = np.meshgrid(x, y, indexing = 'xy')
    radial_dist = np.hypot(x_grid, y_grid)

    # Build the radial lookup and average the positive-frequency slices.
    radial_bins, flat_bins, counts = build_radial_bin_lookup(radial_dist)
    azimuthal_average = np.asarray(
        azimuthal_average_positive_frequency_slices(
            np.asarray(phase_cube, dtype = np.float64),
            mid_time,
            mid_space,
            flat_bins,
            counts),
        dtype = np.float64)

    return azimuthal_average, radial_bins


def azimuthal_average_fft_complex_oana(mid_time, end_time, array, mid_space, radial_meshgrid):

    '''
    Purpose
    -------
    Reproduce the Oana_codes azimuthal averaging routine for complex FFT data.

    Inputs
    ------
    mid_time: int
        Half the temporal length of the FFT cube.

    end_time: int
        Total length of the FFT cube along the time/frequency axis.

    array: np.array, complex
        Complex or real FFT cube in [x, y, nu] order.

    mid_space: int
        Half the spatial extent of the FFT cube.

    radial_meshgrid: np.array, float
        Radial-distance mesh used to define the annuli.

    Outputs
    -------
    azim: np.array, complex
        Oana-style azimuthally averaged array.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    # Build the radial lookup used by the original Oana-style averaging routine.
    radial_bins, flat_bins, counts = build_radial_bin_lookup(radial_meshgrid)
    expected_positive_frequency_count = end_time - int(mid_time)

    # Average the positive-frequency portion of the FFT cube.
    azim = azimuthal_average_positive_frequency_slices(
        np.asarray(array),
        mid_time,
        mid_space,
        flat_bins,
        counts)

    # Guard against mismatches between the requested and realized frequency counts.
    if azim.shape[1] != expected_positive_frequency_count:
        raise ValueError(
            'The azimuthal-average positive-frequency count does not match the requested end_time and mid_time.')

    return np.asarray(azim, dtype = np.complex128)



def parse_spectral_line(value):

    '''
    Purpose
    -------
    Extract a spectral-line identifier from a filename or metadata string.

    Inputs
    ------
    value: object
        Candidate filename, path, or metadata token.

    Outputs
    -------
    spectral_line: str
        Parsed line identifier, or an empty string when no match is found.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    if value in ['', None]:
        return ''

    value = str(value)
    basename = Path(value).name

    # HMI Doppler and continuum products are Fe6173 even when the filename omits the line.
    if re.search(r'hmi[\s_.-]*(?:dop|cont)', basename, flags = re.IGNORECASE) or re.search(r'hmi[\s_.-]*(?:dop|cont)', value, flags = re.IGNORECASE):
        return '6173'

    patterns = [
        r'fe[\s_.-]*(\d{4,5})',
        r'([a-z]{1,2})[\s_.-]*(\d{4,5})',
        r'(\d{4,5})(?=\D*(?:fits|fit|fts|h5|hdf5|nc|$))',
        r'(\d{4,5})']

    for pattern in patterns:
        match = re.search(pattern, basename, flags = re.IGNORECASE)
        if match is not None:
            return match.group(match.lastindex)

    for pattern in patterns:
        match = re.search(pattern, value, flags = re.IGNORECASE)
        if match is not None:
            return match.group(match.lastindex)

    return ''



def parse_spectral_identifier(value):

    '''
    Purpose
    -------
    Parse a spectral element and line identifier from a filename or metadata string.

    Inputs
    ------
    value: object
        Candidate filename, path, or metadata token.

    Outputs
    -------
    spectral_id: dict
        Dictionary containing the normalized element and line tokens.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    spectral_id = {
        'element': '',
           'line': ''}

    if value in ['', None]:
        return spectral_id

    value = str(value)
    basename = Path(value).name
    candidates = [basename, value]

    element_line_patterns = [
        r'(?:^|[^A-Za-z])([A-Za-z]{1,2})[\s_.-]*(\d{4,5})(?:\s*(?:a|å|angstrom))?(?=[^0-9]|$)',
        r'(?:^|[^A-Za-z])([A-Za-z]{1,2})\s+[A-Za-z]*\s*(\d{4,5})(?:\s*(?:a|å|angstrom))?(?=[^0-9]|$)']

    for candidate in candidates:
        for pattern in element_line_patterns:
            match = re.search(pattern, candidate, flags = re.IGNORECASE)
            if match is not None:
                spectral_id['element'] = _normalize_element(match.group(1))
                spectral_id['line'] = match.group(2)
                return spectral_id

    token = str(value).lower()
    if re.search(r'hmi[\s_.-]*(?:dop|cont)', token, flags = re.IGNORECASE):
        spectral_id['element'] = 'Fe'
        spectral_id['line'] = '6173'
        return spectral_id

    spectral_id['line'] = parse_spectral_line(value)

    return spectral_id



def read_fits_spectral_identifier(path):

    '''
    Purpose
    -------
    Read spectral-identification hints from the FITS header.

    Inputs
    ------
    path: str or pathlib.Path
        FITS file to inspect.

    Outputs
    -------
    spectral_id: dict
        Dictionary containing any element and line tokens inferred from the header.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    spectral_id = {
        'element': '',
           'line': ''}

    path = Path(path)

    if str(path) in ['', '.'] or path.suffix.lower() not in ['.fits', '.fit', '.fts']:
        return spectral_id

    try:
        header = fits.getheader(path)
    except Exception:
        return spectral_id

    header_keys = [
        'LINE',
        'LINENAME',
        'WAVELNTH',
        'WAVELENG',
        'WAVE_LEN',
        'WAVELEN',
        'CONTENT',
        'BANDPASS',
        'SPECTRAL']

    for key in header_keys:
        if key in header:
            parsed = parse_spectral_identifier(header[key])

            if spectral_id['element'] == '' and parsed['element'] != '':
                spectral_id['element'] = parsed['element']

            if spectral_id['line'] == '' and parsed['line'] != '':
                spectral_id['line'] = parsed['line']

    return spectral_id



def resolve_paired_cube_spectral_identifier(file_path):

    '''
    Purpose
    -------
    Resolve the paired-cube spectral identifier from the filename and, when needed, the FITS header.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input paired-cube file.

    Outputs
    -------
    spectral_id: dict
        Dictionary containing the resolved element and line tokens.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    spectral_id = parse_spectral_identifier(file_path)

    if spectral_id['element'] != '' and spectral_id['line'] != '':
        return spectral_id

    header_id = read_fits_spectral_identifier(file_path)

    if spectral_id['element'] == '' and header_id['element'] != '':
        spectral_id['element'] = header_id['element']

    if spectral_id['line'] == '' and header_id['line'] != '':
        spectral_id['line'] = header_id['line']

    return spectral_id



def normalize_observable_slug(observable):

    '''
    Purpose
    -------
    Normalize an observable name to the canonical slug used in output filenames.

    Inputs
    ------
    observable: object
        Raw observable token.

    Outputs
    -------
    observable_slug: str
        Canonical observable slug.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    alias_lookup = {
        'bx': 'bb1',
        'by': 'bb2',
        'bz': 'bb3',
        'b1': 'bb1',
        'b2': 'bb2',
        'b3': 'bb3'}

    observable = str(observable or '').strip().lower()

    return alias_lookup.get(observable, observable)



def infer_observational_context(file_path):

    '''
    Purpose
    -------
    Infer a human-readable context label for an observational paired-cube file.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input observational file path.

    Outputs
    -------
    context: dict
        Title and slug labels derived from the observation date or parent directory.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    file_path = str(file_path)
    match = re.search(r'(\d{1,2}[A-Za-z]{3}\d{4})', file_path)

    if match is not None:
        date_token = match.group(1)
        date_obj = datetime.strptime(date_token, '%d%b%Y')
        return {
            'title': date_obj.strftime('%d %B %Y'),
             'slug': date_obj.strftime('%d%b%Y').lower()}

    path = Path(file_path)

    return {
        'title': path.parent.name,
         'slug': _slugify(path.parent.name)}



def infer_simulation_context(file_path):

    '''
    Purpose
    -------
    Infer a human-readable context label for a simulation cube path.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input simulation file path.

    Outputs
    -------
    context: dict
        Title and slug labels derived from the simulation component and field strength.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    path = Path(file_path)
    component = ''
    strength = ''

    for part in path.parts:
        lower_part = part.lower()
        if lower_part in ['hx', 'vx', 'z0']:
            component = lower_part
        if re.fullmatch(r'\d+g', lower_part):
            strength = lower_part

    if component == '' or strength == '':
        match = re.search(r'(hx|vx|z0)[_\-/](\d+g)', str(path), flags = re.IGNORECASE)
        if match is not None:
            component = match.group(1).lower()
            strength = match.group(2).lower()

    title_parts = []
    slug_parts = []

    if component != '':
        title_parts.append(component)
        slug_parts.append(component)
    if strength != '':
        title_parts.append(strength.upper())
        slug_parts.append(strength)

    if len(title_parts) == 0:
        title_parts.append(path.stem)
        slug_parts.append(_slugify(path.stem))

    return {
        'title': ' '.join(title_parts),
         'slug': _join_slug(slug_parts)}



def build_context_labels(config):

    '''
    Purpose
    -------
    Build the shared title and slug labels used by the saved products.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    Outputs
    -------
    context_labels: dict
        Prefix and suffix labels for figure titles and output slugs.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    data = config['data']
    source_type = _normalize_source_type(data['source_type'])

    if source_type == 'paired_cubes':
        paired = data.get('paired_cubes', {})
        default_v1 = paired.get('v1', paired.get('file_1', ''))
        context = infer_observational_context(data.get('v1', default_v1))
    elif source_type == 'single_cube':
        context = infer_simulation_context(data.get('file', data['single_cube'].get('file', '')))
    else:
        raise ValueError(f'Unsupported source_type: {source_type}')

    return {
        'title_prefix': context['title'],
        'title_suffix': '',
        'slug_prefix': context['slug'],
        'slug_suffix': ''}



def build_magnetic_mask_slug(config):

    '''
    Purpose
    -------
    Build the output-slug fragment that describes the magnetic-mask selection.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    Outputs
    -------
    magnetic_slug: str
        Magnetic-mask slug fragment, or an empty string when the mask is inactive.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    filtering = config.get('filtering', {})
    filter_sequence = filtering.get('filter_sequence', [])
    magnetogram_config = filtering.get('magnetogram', {})

    if not filtering.get('enabled', False):
        return ''

    if 'magnetogram' not in filter_sequence:
        return ''

    if not magnetogram_config.get('enabled', False):
        return ''

    selection = magnetogram_config.get('selection', 'nonmagnetic').lower()
    threshold_G = float(magnetogram_config['threshold_G'])
    threshold_slug = _slugify(f'{threshold_G:g}')

    if selection == 'nonmagnetic':
        relation = 'le'
    elif selection == 'magnetic':
        relation = 'gt'
    else:
        raise ValueError("magnetogram selection must be either 'magnetic' or 'nonmagnetic'.")

    return f'b_{relation}_{threshold_slug}g'



def build_gaussian_parameter_slug(config):

    '''
    Purpose
    -------
    Build the output-slug fragment that describes the Gaussian filter parameters.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    Outputs
    -------
    gaussian_slug: str
        Gaussian-filter slug fragment, or an empty string when the filter is inactive.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    filtering = config.get('filtering', {})
    filter_sequence = filtering.get('filter_sequence', [])
    gaussian_config = filtering.get('gaussian', {})

    if not filtering.get('enabled', False):
        return ''

    if 'gaussian' not in filter_sequence:
        return ''

    if not gaussian_config.get('enabled', False):
        return ''

    return _join_slug([
        'gauss',
        'ck', f"{float(gaussian_config['central_k']):g}",
        'wk', f"{float(gaussian_config['width_k']):g}",
        'cf', f"{float(gaussian_config['central_f']):g}",
        'wf', f"{float(gaussian_config['width_f']):g}"])



def normalize_paired_line_token(file_path):

    '''
    Purpose
    -------
    Normalize a paired-cube spectral identifier to the compact line token used in metadata lookups.

    Inputs
    ------
    file_path: str or pathlib.Path
        Input paired-cube file path.

    Outputs
    -------
    line_token: str
        Compact element-line token used by the phase-delay metadata.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    spectral_id = resolve_paired_cube_spectral_identifier(file_path)

    if spectral_id['element'] != '' and spectral_id['line'] != '':
        return f"{spectral_id['element'].lower()}{spectral_id['line']}"

    return _slugify(parse_spectral_line(file_path))


def infer_paired_cube_phase_delay_seconds(config, reference_dir = None):

    '''
    Purpose
    -------
    Infer the IBIS line-sampling delay used by the original k-omega notebook.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    reference_dir: str or pathlib.Path, optional
        Directory containing the legacy AGWs_config.ini file.

    Outputs
    -------
    phase_delay_seconds: float
        Signed phase-delay correction in seconds. Returns zero when no matching
        observational calibration entry can be inferred.

    Author(s)
    ---------
    Julio M. Morales, March 20th, 2026
    '''

    data = config.get('data', {})

    if _normalize_source_type(data.get('source_type', 'paired_cubes')) != 'paired_cubes':
        return 0.0

    v1_file = data.get('v1', '')
    v2_file = data.get('v2', '')
    if v1_file in ['', None] or v2_file in ['', None]:
        return 0.0

    date_object = _infer_observation_date_object(v1_file)
    if date_object is None:
        return 0.0

    phase_delay_metadata = resolve_paired_cube_phase_delay_metadata(config, reference_dir = reference_dir)

    return float(phase_delay_metadata['phase_delay_seconds'])


def resolve_paired_cube_phase_delay_metadata(config, reference_dir = None):

    '''
    Purpose
    -------
    Resolve the observational line-sampling delay and lower/higher line order
    using the legacy AGWs_config.ini metadata.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    reference_dir: str or pathlib.Path, optional
        Directory containing the legacy Oana Codes reference assets.

    Outputs
    -------
    metadata: dict
        Dictionary containing the inferred phase delay and the lower/higher
        paired-cube ordering expected by the reference notebook.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    data = config.get('data', {})

    metadata = {
          'phase_delay_seconds': 0.0,
                   'line_1': '',
                   'line_2': '',
          'forward_key_used': '',
          'reverse_key_used': '',
              'lower_index': 0,
             'higher_index': 1}

    if _normalize_source_type(data.get('source_type', 'paired_cubes')) != 'paired_cubes':
        return metadata

    v1_file = data.get('v1', '')
    v2_file = data.get('v2', '')
    if v1_file in ['', None] or v2_file in ['', None]:
        return metadata

    metadata['line_1'] = normalize_paired_line_token(v1_file)
    metadata['line_2'] = normalize_paired_line_token(v2_file)

    if metadata['line_1'] == '' or metadata['line_2'] == '':
        return metadata

    date_object = _infer_observation_date_object(v1_file)
    if date_object is None:
        return metadata

    if reference_dir in ['', None]:
        reference_dir = Path(__file__).resolve().parent
    else:
        reference_dir = Path(reference_dir).expanduser().resolve()

    candidate_config_paths = [
        reference_dir / 'Oana Codes' / 'AGWs_config.ini',
        reference_dir / 'Oana_codes' / 'AGWs_config.ini']
    config_ini = next((path for path in candidate_config_paths if path.exists()), None)
    if config_ini is None:
        return metadata

    config_parser = configparser.ConfigParser(inline_comment_prefixes = ('#', ';'))
    config_parser.read(config_ini)

    section_name = date_object.strftime('%m%d%Y')
    if section_name not in config_parser:
        return metadata

    section = config_parser[section_name]
    forward_key = f"dt_{metadata['line_1']}_{metadata['line_2']}"
    reverse_key = f"dt_{metadata['line_2']}_{metadata['line_1']}"

    if forward_key in section:
        metadata['phase_delay_seconds'] = float(section.get(forward_key))
        metadata['forward_key_used'] = forward_key
        metadata['lower_index'] = 0
        metadata['higher_index'] = 1
        return metadata

    if reverse_key in section:
        metadata['phase_delay_seconds'] = float(section.get(reverse_key))
        metadata['reverse_key_used'] = reverse_key
        metadata['lower_index'] = 1
        metadata['higher_index'] = 0
        return metadata

    return metadata



def build_processing_slug(config):

    '''
    Purpose
    -------
    Build the output-slug fragment that records which filters were applied.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    Outputs
    -------
    processing_slug: str
        Slug describing the enabled processing steps.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    filtering = config.get('filtering', {})
    filter_sequence = filtering.get('filter_sequence', [])
    enabled_filters = []

    for filter_name in filter_sequence:
        filter_config = filtering.get(filter_name, {})
        if filter_config.get('enabled', True):
            enabled_filters.append(filter_name)

    if filtering.get('enabled', False) and len(enabled_filters) > 0:
        filter_slug = '_'.join([_slugify(filter_name) for filter_name in enabled_filters])
        magnetic_slug = build_magnetic_mask_slug(config)
        gaussian_parameter_slug = build_gaussian_parameter_slug(config)
        processing_parts = [f'{filter_slug}_filtered']

        if gaussian_parameter_slug != '':
            processing_parts.append(gaussian_parameter_slug)

        if magnetic_slug != '':
            processing_parts.append(magnetic_slug)

        return _join_slug(processing_parts)

    return 'unfiltered'



def build_source_slug(config):

    '''
    Purpose
    -------
    Build the source-specific slug fragment for the saved products.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    Outputs
    -------
    source_slug: str
        Slug describing the observational lines or single-cube observable and heights.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    data = config['data']
    source_type = _normalize_source_type(data['source_type'])

    if source_type == 'paired_cubes':
        spectral_id_v1 = resolve_paired_cube_spectral_identifier(data.get('v1', ''))
        spectral_id_v2 = resolve_paired_cube_spectral_identifier(data.get('v2', ''))

        if spectral_id_v1['element'] == '' or spectral_id_v1['line'] == '' or spectral_id_v2['element'] == '' or spectral_id_v2['line'] == '':
            raise ValueError(
                'Could not determine the paired-cube spectral identifiers from the input file names or FITS headers.')

        return f"{spectral_id_v1['element'].lower()}{spectral_id_v1['line']}_{spectral_id_v2['element'].lower()}{spectral_id_v2['line']}"

    if source_type == 'single_cube':
        observable_slug = normalize_observable_slug(data.get('observable', ''))
        h1_km = data['resolved_h1_km']
        h2_km = data['resolved_h2_km']
        h1_slug = f"{_slugify(f'{h1_km:g}')}km"
        h2_slug = f"{_slugify(f'{h2_km:g}')}km"

        return _join_slug([observable_slug, h1_slug, h2_slug])

    raise ValueError(f'Unsupported source_type: {source_type}')



def build_base_slug(config):

    '''
    Purpose
    -------
    Assemble the shared base slug used by all saved output products.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    Outputs
    -------
    base_slug: str
        Shared slug prefix for the saved outputs.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    context = build_context_labels(config)
    source_slug = build_source_slug(config)
    processing_slug = build_processing_slug(config)

    return _join_slug([context['slug_prefix'], source_slug, processing_slug, context['slug_suffix']])



def build_output_stem(config, product):

    '''
    Purpose
    -------
    Build the output filename stem for a specific saved product.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    product: str
        Output product identifier.

    Outputs
    -------
    output_stem: str
        Filename stem used for the requested product.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    base_slug = build_base_slug(config)

    if product == 'time_distance':
        return _join_slug([base_slug, 'xc'])

    if product == 'phase_difference':
        return _join_slug([base_slug, 'phase_diff'])

    if product == 'komega_diagram':
        return _join_slug([base_slug, 'komega'])

    if product == 'coherence_diagram':
        return _join_slug([base_slug, 'coherence'])

    raise ValueError(f'Unsupported output product: {product}')



def prepare_runtime_config(config):

    '''
    Purpose
    -------
    Expand the user configuration into the fully resolved runtime configuration.

    Inputs
    ------
    config: dict
        User-defined configuration dictionary.

    Outputs
    -------
    runtime_config: dict
        Runtime configuration with resolved paths, sampling, heights, and output files.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    runtime_config = copy.deepcopy(config)
    data = runtime_config['data']
    paths = runtime_config.get('paths', {})
    source_type = _normalize_source_type(data['source_type'])
    data['source_type'] = source_type

    if source_type == 'paired_cubes':
        paired = copy.deepcopy(data.get('paired_cubes', {}))
        data['data_dir'] = paired.get('data_dir', data.get('data_dir', ''))
        data['v1'] = paired.get('v1', paired.get('file_1', data.get('v1', '')))
        data['v2'] = paired.get('v2', paired.get('file_2', data.get('v2', '')))
        data['h1'] = paired.get('h1', data.get('h1', ''))
        data['h2'] = paired.get('h2', data.get('h2', ''))

        if 'p_dx_Mm' not in paired or 'dt' not in paired or 'delta_z_km' not in paired:
            raise ValueError(
                "source_type = 'paired_cubes' requires data['paired_cubes']['delta_z_km'], "
                "data['paired_cubes']['p_dx_Mm'], and data['paired_cubes']['dt'].")

        data['resolved_delta_z_km'] = abs(float(paired['delta_z_km']))
        runtime_config['time_distance']['p_dx_Mm'] = float(paired['p_dx_Mm'])
        runtime_config['time_distance']['dt'] = float(paired['dt'])
    elif source_type == 'single_cube':
        simulation = copy.deepcopy(data.get('single_cube', {}))
        data['file'] = simulation.get('file', data.get('file', ''))
        data['observable'] = simulation.get('observable', data.get('observable', ''))
        data['h1'] = simulation.get('h1', data.get('h1', ''))
        data['h2'] = simulation.get('h2', data.get('h2', ''))
        data['model_atmosphere_path'] = simulation.get('model_atmosphere_path', data.get('model_atmosphere_path', ''))
        sampling = infer_netcdf_sampling(data['file'])
        resolved_heights = infer_netcdf_height_pair_km(data['file'], data['h1'], data['h2'])
        runtime_config['time_distance']['dt'] = float(sampling['dt_seconds'])
        runtime_config['time_distance']['p_dx_Mm'] = float(sampling['dx_Mm'])
        data['h1'] = int(resolved_heights['h1_index'])
        data['h2'] = int(resolved_heights['h2_index'])
        data['resolved_h1_index'] = int(resolved_heights['h1_index'])
        data['resolved_h2_index'] = int(resolved_heights['h2_index'])
        data['resolved_h1_km'] = float(resolved_heights['h1_km'])
        data['resolved_h2_km'] = float(resolved_heights['h2_km'])
        data['resolved_delta_z_km'] = abs(float(resolved_heights['h2_km']) - float(resolved_heights['h1_km']))
        if data['model_atmosphere_path'] not in ['', None]:
            data['single_cube_model_atmosphere'] = interpolate_model_atmosphere_to_single_cube_layers(
                data['model_atmosphere_path'],
                data['file'])
        else:
            data['single_cube_model_atmosphere'] = None
    else:
        raise ValueError(f'Unsupported source_type: {source_type}')

    data_output_dir = Path(paths['data_output_dir']).expanduser().resolve()
    figure_output_dir = Path(paths.get('figure_dir', data_output_dir)).expanduser().resolve()
    data['outfile'] = str(data_output_dir / f"{build_output_stem(runtime_config, 'time_distance')}.fits")
    data['phase_outfile'] = str(data_output_dir / f"{build_output_stem(runtime_config, 'phase_difference')}.fits")
    data['komega_outfile'] = str(data_output_dir / f"{build_output_stem(runtime_config, 'komega_diagram')}.fits")
    data['coherence_outfile'] = str(data_output_dir / f"{build_output_stem(runtime_config, 'coherence_diagram')}.fits")
    if source_type == 'single_cube':
        data['orientation_validation_outfile'] = str(
            figure_output_dir / f"{build_output_stem(runtime_config, 'komega_diagram')}_magnetic_orientation_validation.png")
    else:
        data['orientation_validation_outfile'] = ''

    return runtime_config


def recommend_xcorrj_worker_count(config, cube_shape, num_radii):

    '''
    Purpose
    -------
    Recommend a conservative worker count for the xcorrj radius loop.

    Inputs
    ------
    config: dict
        Runtime configuration dictionary.

    cube_shape: tuple
        Shape of the Dopplergram cube in [t, y, x] order.

    num_radii: int
        Number of radii to process.

    Outputs
    -------
    recommended_workers: int
        Recommended number of worker threads.

    Author(s)
    ---------
    Julio M. Morales, March 20th, 2026
    '''

    num_radii = max(1, int(num_radii))
    cpu_count = max(1, os.cpu_count() or 1)
    cube_size = int(np.prod(cube_shape))
    source_type = _normalize_source_type(config.get('data', {}).get('source_type', 'paired_cubes'))

    if num_radii == 1:
        return 1

    if source_type == 'paired_cubes':
        if cube_size >= 2.0e7:
            return 1
        if cube_size >= 5.0e6:
            return min(num_radii, 2)
        return min(num_radii, cpu_count, 4)

    if cube_size >= 1.0e8:
        return min(num_radii, 2)
    if cube_size >= 2.0e7:
        return min(num_radii, 2)

    return min(num_radii, cpu_count, 4)


def prepare_xcorrj_geometry(ny, nx, deltas, width, dx_pixels):

    '''
    Purpose
    -------
    Precompute the annulus offsets and valid target-box bounds for xcorrj.

    Inputs
    ------
    ny: int
        Number of pixels along the y axis.

    nx: int
        Number of pixels along the x axis.

    deltas: np.array, int
        Annulus radii, in pixels.

    width: int
        Annulus half-width used by xcorrj.

    dx_pixels: float
        Pixel width used to define the annulus bin edges.

    Outputs
    -------
    annulus_offsets_by_delta: dict
        Mapping from radius to a list of annulus offset arrays and their counts.

    target_bounds_by_delta: dict
        Mapping from radius to the valid target-box bounds and center count.

    Author(s)
    ---------
    Julio M. Morales, March 21st, 2026
    '''

    y = np.arange(-ny // 2, ny // 2, dtype = np.int64)
    x = np.arange(-nx // 2, nx // 2, dtype = np.int64)
    xgrid, ygrid = np.meshgrid(x, y)
    fullgrid = np.hypot(xgrid, ygrid)
    center = fullgrid.shape[0] // 2
    x0 = nx // 2
    y0 = ny // 2
    extent = np.arange(-width, width + 1, dtype = int)
    annulus_offsets_by_delta = {}
    target_bounds_by_delta = {}

    for delta in deltas:
        delta = int(delta)
        bsize = int(np.floor((min(nx, ny) - 2*delta - 1)/2) - (2*width + 1))
        ntarg = 2*bsize + 1

        if bsize < 0 or ntarg <= 0:
            raise ValueError(
                f'Radius {delta} is too large for the current cube geometry. '
                f'Maximum valid radius is {int(np.floor((min(nx, ny) - 4*width - 3)/2))} pixels for this run.')

        target_bounds_by_delta[delta] = {
                 'y_start': y0 - bsize,
                  'y_stop': y0 + bsize + 1,
                 'x_start': x0 - bsize,
                  'x_stop': x0 + bsize + 1,
            'center_count': ntarg*ntarg}

        per_ring_offsets = []

        for offset in extent:
            yy, xx = np.nonzero(
                ((delta + offset - dx_pixels/2.0) < fullgrid)
                & (fullgrid <= (delta + offset + dx_pixels/2.0))
            )

            per_ring_offsets.append({
                'yy_shift': np.asarray(yy - center, dtype = np.int64),
                'xx_shift': np.asarray(xx - center, dtype = np.int64),
                'count': int(yy.size)})

        annulus_offsets_by_delta[delta] = per_ring_offsets

    return annulus_offsets_by_delta, target_bounds_by_delta


def parallel_loop(delta):

    '''
    Purpose
    -------
    Compute the azimuthally averaged cross-correlation for a single radius.

    Inputs
    ------
    delta: int
        Radius, in pixels, for which to compute the time-distance signal.

    Outputs
    -------
    result: tuple
        Tuple containing the radius, cross-correlation array, and phase-difference array.

    Author(s)
    ---------
    Julio M. Morales, March 12th, 2026
    '''

    # Normalize the radius and recover the precomputed shared geometry for this worker.
    delta = int(delta)
    _, _, nt = _fft_lower.shape
    target_bounds = _target_bounds_by_delta[delta]
    annulus_offsets = _annulus_offsets_by_delta[delta]
    center_count = int(target_bounds['center_count'])

    # Reject degenerate geometries before entering the expensive loops.
    if center_count <= 0:
        raise ValueError(f'Radius {delta} produced an empty target box.')

    # Accumulate the complex cross-correlation and the phase-difference signal across centers.
    xcorr_sum = np.zeros(nt, dtype = np.complex128)
    phase_sum = np.zeros(nt, dtype = np.float64)

    # Match the legacy xcorrj center ordering exactly: x-major traversal over
    # the valid target box, which corresponds to the original Fortran-order
    # flatten/unravel path.
    for indx in range(int(target_bounds['x_start']), int(target_bounds['x_stop'])):
        for indy in range(int(target_bounds['y_start']), int(target_bounds['y_stop'])):

            # Read the lower-height Fourier spectrum at the current annulus center.
            phi1 = _fft_lower[indy, indx, :]
            phi2 = np.zeros(nt, dtype = np.complex128)

            # Average the higher-height Fourier spectrum over the precomputed annulus offsets.
            for ring_offsets in annulus_offsets:
                yy = ring_offsets['yy_shift'] + indy
                xx = ring_offsets['xx_shift'] + indx
                phi2 += _fft_higher[yy, xx, :].sum(axis = 0)/float(ring_offsets['count'])

            # Normalize the annular average and accumulate the correlation products.
            phi2 /= float(_extent_size)
            xcorr_sum += np.fft.ifft(np.conj(phi1)*phi2)
            phi1_phase = phi1 - phi1.mean()
            phi2_phase = phi2 - phi2.mean()
            phase_sum += np.rad2deg(np.angle(np.fft.fftshift(phi1_phase*np.conj(phi2_phase))))

    # Keep the saved time-distance product in raw units. Plotting code can
    # normalize selected display contexts without changing the pipeline output.
    xc = np.fft.fftshift(xcorr_sum/float(center_count)).real
    phase_diff = phase_sum/float(center_count)

    # Return the results for this radius
    return delta, xc, phase_diff


class TimeDistance:

    def __init__(self, config):

        # Store the shared runtime configuration and its key sub-dictionaries.
        self.config = config
        self.data = config['data']
        self.filtering = config['filtering']
        self.time_distance = config['time_distance']

        # Cache the key input indices and resolved output paths.
        self.h1 = self.data['h1']
        self.h2 = self.data['h2']
        self.outfile = Path(self.data['outfile']).expanduser()
        self.phase_outfile = Path(self.data['phase_outfile']).expanduser()
        self.komega_outfile = Path(self.data['komega_outfile']).expanduser()
        self.coherence_outfile = Path(self.data['coherence_outfile']).expanduser()
        self.orientation_validation_outfile = Path(self.data['orientation_validation_outfile']).expanduser() if self.data.get('orientation_validation_outfile', '') not in ['', None] else None
        self.single_cube_model_atmosphere = copy.deepcopy(self.data.get('single_cube_model_atmosphere'))
        self.module_dir = Path(self.config.get('_module_dir', Path(__file__).resolve().parent))

        # Initialize the runtime caches populated after the pipeline runs.
        self.results = None
        self.magnetic_orientation_metadata = None

    def load_dopplergrams(self):

        '''
        Purpose
        -------
        Load the Dopplergram cubes and apply the configured filters if requested.

        Inputs
        ------
        None

        Outputs
        -------
        v1: np.array, float
            Lower-height Dopplergram cube.

        v2: np.array, float
            Higher-height Dopplergram cube.

        Author(s)
        ---------
        Julio M. Morales, March 12th, 2026
        '''

        # Load the Dopplergrams through the optional filtering pipeline
        filtering = AGWFilter(self.config)
        v1, v2 = filtering.run()

        return v1, v2

    def load_raw_dopplergrams(self):

        '''
        Purpose
        -------
        Load the raw Dopplergram cubes without applying any optional filters.

        Inputs
        ------
        None

        Outputs
        -------
        v1: np.array, float
            First raw Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second raw Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 21st, 2026
        '''

        loader = AGWFilter(self.config)

        return loader.load_dopplergrams()

    def resolve_phase_analysis_cube_order(self, cube_1, cube_2):

        '''
        Purpose
        -------
        Resolve the lower and higher atmospheric cubes used by the reference
        phase-difference implementations.

        Inputs
        ------
        cube_1: np.array, float
            First cube in [t, y, x] order.

        cube_2: np.array, float
            Second cube in [t, y, x] order.

        Outputs
        -------
        lower_cube: np.array, float
            Lower-forming cube in [t, y, x] order.

        higher_cube: np.array, float
            Higher-forming cube in [t, y, x] order.

        metadata: dict
            Dictionary containing the resolved ordering and paired-cube
            phase-delay metadata when available.

        Author(s)
        ---------
        Julio M. Morales, March 21st, 2026
        '''

        # Normalize the source type and keep the input cubes in indexable order.
        source_type = _normalize_source_type(self.data.get('source_type', 'paired_cubes'))
        cubes = [cube_1, cube_2]

        if source_type == 'paired_cubes':
            # Use the legacy observational metadata to recover the lower and higher line ordering.
            metadata = resolve_paired_cube_phase_delay_metadata(self.config, reference_dir = self.module_dir)
            lower_index = int(metadata.get('lower_index', 0))
            higher_index = int(metadata.get('higher_index', 1))

            # Reorder the paired cubes to match the observational phase-analysis convention.
            lower_cube = cubes[lower_index]
            higher_cube = cubes[higher_index]
            metadata = copy.deepcopy(metadata)
            metadata['resolved_from'] = 'paired_cubes'

            return lower_cube, higher_cube, metadata

        # Default to the original input ordering for single-cube runs.
        lower_cube = cube_1
        higher_cube = cube_2
        resolved_h1_km = float(self.data.get('resolved_h1_km', np.nan))
        resolved_h2_km = float(self.data.get('resolved_h2_km', np.nan))

        # Start from the default metadata for the single-cube ordering.
        metadata = {
              'phase_delay_seconds': 0.0,
                  'lower_index': 0,
                 'higher_index': 1,
                 'resolved_from': 'single_cube'}

        # Swap the cubes when the first requested height is physically above the second.
        if np.isfinite(resolved_h1_km) and np.isfinite(resolved_h2_km) and resolved_h1_km > resolved_h2_km:
            lower_cube = cube_2
            higher_cube = cube_1
            metadata['lower_index'] = 1
            metadata['higher_index'] = 0

        return lower_cube, higher_cube, metadata

    def compute_single_cube_magnetic_orientation_metadata(self):

        '''
        Purpose
        -------
        Compute the single-cube magnetic-orientation metadata used by the saved k-omega products.

        Inputs
        ------
        None

        Outputs
        -------
        metadata: dict or None
            Magnetic-orientation summary metadata for single-cube runs, or `None` for paired cubes.

        Author(s)
        ---------
        Julio M. Morales, March 22nd, 2026.
        '''

        # Return immediately when the run is not using a single NetCDF cube.
        source_type = _normalize_source_type(self.data.get('source_type', 'paired_cubes'))
        if source_type != 'single_cube':
            return None

        # Resolve the input cube path before loading any magnetic-field metadata.
        require_netcdf4()
        cube_file = self.data.get('file', self.data.get('cube_file', ''))
        if cube_file in ['', None]:
            raise ValueError("source_type = 'single_cube' requires data['file'].")

        cube_file = Path(cube_file).expanduser().resolve()
        loader = AGWFilter(self.config)

        # Define the magnetic-field components and their preferred NetCDF aliases.
        component_specs = [
            ('bx', 'bx', ['bb1', 'b1', 'bx', 'b_x', 'magx']),
            ('by', 'by', ['bb2', 'b2', 'by', 'b_y', 'magy']),
            ('bz', 'bz', ['bb3', 'b3', 'bz', 'b_z', 'magz'])]

        # Read the two requested height indices and their already resolved physical heights.
        requested_height_indices = [int(self.data['h1']), int(self.data['h2'])]
        height_values_km = [
            float(self.data.get('resolved_h1_km', np.nan)),
            float(self.data.get('resolved_h2_km', np.nan))]

        # Initialize the containers that collect the per-component and per-height metadata.
        component_names = {}
        component_variables = {}
        component_axis_orders = {}
        theta_means_deg = []
        phi_means_deg = []
        theta_valid_fraction = []
        phi_valid_fraction = []
        theta_snapshots_deg = []
        phi_snapshots_deg = []
        magnitude_epsilons = []
        mean_field_strengths_G_between_heights = []
        validation_time_index = None
        height_coordinate_name = ''
        selected_height_range = None

        # Open the cube once and reuse the loaded variable handles across all diagnostics.
        with nc.Dataset(cube_file) as netcdf_file:
            resolved_height_indices = None
            reference_shape = None
            reference_nz = None

            # Resolve each magnetic-field component and verify that all components share the same z axis.
            for component_label, configured_variable, preferred_names in component_specs:
                variable_name, variable = loader.select_netcdf_field_variable(
                    netcdf_file,
                    configured_variable,
                    preferred_names,
                    f'{component_label} magnetic-field')
                axis_order = loader.infer_netcdf_axis_order(variable)
                height_coordinates, current_height_coordinate_name = loader.load_netcdf_height_coordinates(netcdf_file, variable)
                nz = int(variable.shape[int(axis_order['z'])])

                if resolved_height_indices is None:

                    # Resolve the requested heights from the first component and record the selected range.
                    resolved_height_indices = [
                        loader.resolve_netcdf_height_index(requested_height_indices[0], nz, 'h1'),
                        loader.resolve_netcdf_height_index(requested_height_indices[1], nz, 'h2')]
                    selected_height_range = (
                        min(resolved_height_indices),
                        max(resolved_height_indices))
                    reference_nz = nz
                    if current_height_coordinate_name not in ['', None]:
                        height_coordinate_name = str(current_height_coordinate_name)
                elif nz != reference_nz:
                    raise ValueError(
                        'The single_cube magnetic-field components do not share the same z-axis length.')

                # Store the resolved component metadata for the later slice extraction.
                component_names[component_label] = variable_name
                component_variables[component_label] = variable
                component_axis_orders[component_label] = axis_order

            # Summarize the inclination and azimuth statistics at the two requested heights.
            for height_position, height_index in enumerate(resolved_height_indices):
                bx = _extract_netcdf_height_slice(component_variables['bx'], component_axis_orders['bx'], height_index)
                by = _extract_netcdf_height_slice(component_variables['by'], component_axis_orders['by'], height_index)
                bz = _extract_netcdf_height_slice(component_variables['bz'], component_axis_orders['bz'], height_index)

                if reference_shape is None:

                    # Record the shared [t, y, x] shape and use the temporal midpoint for the validation snapshot.
                    reference_shape = bx.shape
                    validation_time_index = bx.shape[0] // 2
                elif bx.shape != reference_shape or by.shape != reference_shape or bz.shape != reference_shape:
                    raise ValueError(
                        'The single_cube magnetic-field components do not share the same [t, y, x] geometry.')

                # Compute the orientation diagnostics and summarize their valid pixels.
                orientation = compute_magnetic_orientation_angles(bx, by, bz)
                theta_deg = orientation['theta_deg']
                phi_deg = orientation['phi_deg']
                finite_theta = np.isfinite(theta_deg)
                finite_phi = np.isfinite(phi_deg)

                # Average the inclination only when valid samples are present.
                if np.any(finite_theta):
                    theta_means_deg.append(float(np.nanmean(theta_deg)))
                else:
                    theta_means_deg.append(np.nan)

                # Store the azimuth average, valid-data fractions, and validation snapshots.
                phi_means_deg.append(float(circular_mean_degrees(phi_deg)))
                theta_valid_fraction.append(float(np.count_nonzero(finite_theta))/float(theta_deg.size))
                phi_valid_fraction.append(float(np.count_nonzero(finite_phi))/float(phi_deg.size))
                theta_snapshots_deg.append(np.asarray(theta_deg[validation_time_index], dtype = np.float64))
                phi_snapshots_deg.append(np.asarray(phi_deg[validation_time_index], dtype = np.float64))
                magnitude_epsilons.append(float(orientation['magnitude_epsilon']))

            # Average the magnetic-field strength across every layer between the two selected heights.
            for height_index in range(selected_height_range[0], selected_height_range[1] + 1):
                bx = _extract_netcdf_height_slice(component_variables['bx'], component_axis_orders['bx'], height_index)
                by = _extract_netcdf_height_slice(component_variables['by'], component_axis_orders['by'], height_index)
                bz = _extract_netcdf_height_slice(component_variables['bz'], component_axis_orders['bz'], height_index)
                orientation = compute_magnetic_orientation_angles(bx, by, bz)
                field_magnitude = np.asarray(orientation['field_magnitude'], dtype = np.float64)
                valid_field = np.isfinite(field_magnitude) & (field_magnitude > float(orientation['magnitude_epsilon']))

                if np.any(valid_field):
                    mean_field_strengths_G_between_heights.append(float(np.nanmean(field_magnitude[valid_field])))
                else:
                    mean_field_strengths_G_between_heights.append(np.nan)

        # Collapse the per-layer mean field strengths into one representative value.
        finite_mean_field_strengths_G = np.asarray(
            [value for value in mean_field_strengths_G_between_heights if np.isfinite(value)],
            dtype = np.float64)
        if finite_mean_field_strengths_G.size > 0:
            mean_field_strength_G_between_heights = float(np.nanmean(finite_mean_field_strengths_G))
        else:
            mean_field_strength_G_between_heights = np.nan

        # Combine the field-strength summary with the interpolated atmosphere diagnostics.
        alfven_sound_ratio = summarize_single_cube_alfven_sound_ratio(
            self.single_cube_model_atmosphere,
            selected_height_range[0],
            selected_height_range[1],
            mean_field_strength_G_between_heights)

        # Assemble the full orientation metadata dictionary exported with the saved products.
        metadata = {
                 'height_indices': [int(value) for value in resolved_height_indices],
              'height_values_km': height_values_km,
               'theta_means_deg': theta_means_deg,
                 'phi_means_deg': phi_means_deg,
          'theta_valid_fraction': theta_valid_fraction,
            'phi_valid_fraction': phi_valid_fraction,
            'phi_mean_method': 'circular',
          'magnitude_epsilon': float(max(magnitude_epsilons)) if len(magnitude_epsilons) > 0 else np.nan,
              'component_names': component_names,
        'field_strength_G_between_heights': mean_field_strengths_G_between_heights,
            'alfven_sound_ratio': alfven_sound_ratio,
            'height_coordinate': height_coordinate_name,
         'validation_time_index': int(validation_time_index if validation_time_index is not None else 0),
           'validation_plot_file': ''}

        # Save the optional validation plot when an output path was configured.
        if self.orientation_validation_outfile is not None:
            saved_plot = save_magnetic_orientation_validation_plot(
                np.asarray(theta_snapshots_deg, dtype = np.float64),
                np.asarray(phi_snapshots_deg, dtype = np.float64),
                metadata,
                self.orientation_validation_outfile)
            metadata['validation_plot_file'] = str(saved_plot)

        self.magnetic_orientation_metadata = metadata

        return metadata

    def compute_komega_diagram(self, v1, v2):

        '''
        Purpose
        -------
        Compute the azimuthally averaged k-omega phase-difference diagram.

        Inputs
        ------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        spectrum: np.array, float
            Azimuthally averaged k-omega phase-difference map in degrees.

        k_axis: np.array, float
            Positive horizontal-wavenumber axis in 1/Mm.

        nu_axis: np.array, float
            Positive frequency axis in mHz.

        metadata: dict
            Dictionary describing the applied phase correction and saved FITS metadata.

        Author(s)
        ---------
        Julio M. Morales, March 20th, 2026
        '''

        # Read the temporal cadence and pixel scale used by the spectral products.
        dt_seconds = float(self.time_distance['dt'])
        dx_Mm = float(self.time_distance['p_dx_Mm'])

        # Resolve the lower and higher cube ordering before building the spectrum.
        lower_cube, higher_cube, order_metadata = self.resolve_phase_analysis_cube_order(v1, v2)

        # Build the k-omega diagram from the same Dopplergrams passed into the
        # rest of the pipeline, so any enabled Gaussian or magnetogram
        # filtering has already been applied in the configured sequence.
        lower_cube = np.transpose(np.asarray(lower_cube, dtype = np.float64), (1, 2, 0))
        higher_cube = np.transpose(np.asarray(higher_cube, dtype = np.float64), (1, 2, 0))
        lower_cube = lower_cube - np.mean(lower_cube)
        higher_cube = higher_cube - np.mean(higher_cube)

        # Rebuild the positive-frequency plotting axes from the reordered cubes.
        axes = build_komega_axes((lower_cube.shape[2], lower_cube.shape[0], lower_cube.shape[1]), dt_seconds, dx_Mm)
        source_type = _normalize_source_type(self.data.get('source_type', 'paired_cubes'))

        # Apply the observational line-sampling delay only to paired-cube runs.
        if source_type == 'single_cube':
            # Simulations do not require the observational line-sampling delay
            # correction used for paired IBIS diagnostics.
            phase_delay_seconds = 0.0
        else:
            phase_delay_seconds = float(order_metadata.get('phase_delay_seconds', 0.0))

        print('Computing k-omega phase-difference diagram')
        # Fourier transform the two cubes and form their complex cross power.
        fft_lower = np.fft.fftshift(np.fft.fftn(lower_cube))
        fft_higher = np.fft.fftshift(np.fft.fftn(higher_cube))
        cross_power = fft_lower*np.conjugate(fft_higher)

        # Convert the cross power to phase and azimuthally average it.
        phase_cube = np.angle(cross_power, deg = False)
        azimuthal_phase, _ = azimuthal_average_fft_phase(phase_cube)

        # Add the line-sampling correction and convert the final spectrum to degrees.
        phase_correction = compute_phase_difference_correction(
            phase_delay_seconds,
            azimuthal_phase.shape[1],
            azimuthal_phase.shape[0],
            dt_seconds)
        spectrum = np.rad2deg(azimuthal_phase + phase_correction)

        # Record the saved-product metadata together with the applied correction.
        metadata = {
            'phase_delay_seconds': float(phase_delay_seconds),
            'dx_Mm': dx_Mm,
            'dt_seconds': dt_seconds,
            'k_axis': np.asarray(axes['k_axis'], dtype = np.float64),
            'nu_axis': np.asarray(axes['nu_axis'], dtype = np.float64),
            'lower_index': int(order_metadata.get('lower_index', 0)),
            'higher_index': int(order_metadata.get('higher_index', 1)),
            'phase_correction_applied': bool(abs(phase_delay_seconds) > 0.0)}

        if self.magnetic_orientation_metadata is not None:
            metadata['magnetic_orientation'] = copy.deepcopy(self.magnetic_orientation_metadata)

        return np.asarray(spectrum, dtype = np.float64), metadata['k_axis'], metadata['nu_axis'], metadata

    def compute_coherence_diagram(self, v1, v2):

        '''
        Purpose
        -------
        Compute the Oana-style running-difference k-omega coherence diagram.

        Inputs
        ------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        coherence: np.array, float
            Azimuthally averaged magnitude-squared coherence map.

        k_axis: np.array, float
            Positive horizontal-wavenumber axis in 1/Mm.

        nu_axis: np.array, float
            Positive frequency axis in mHz.

        metadata: dict
            Dictionary describing the applied Oana-style preprocessing.

        Author(s)
        ---------
        Julio M. Morales, March 21st, 2026
        '''

        # Read the temporal cadence and pixel scale used by the coherence product.
        dt_seconds = float(self.time_distance['dt'])
        dx_Mm = float(self.time_distance['p_dx_Mm'])

        # Resolve the lower and higher cube ordering before building the spectrum.
        lower_cube, higher_cube, order_metadata = self.resolve_phase_analysis_cube_order(v1, v2)
        lower_cube = np.transpose(np.asarray(lower_cube, dtype = np.float64), (1, 2, 0))
        higher_cube = np.transpose(np.asarray(higher_cube, dtype = np.float64), (1, 2, 0))

        # Enforce a shared geometry before taking running differences and FFTs.
        if lower_cube.shape != higher_cube.shape:
            raise ValueError('The coherence calculation requires Dopplergram cubes with the same shape.')

        print('Computing Coherence Map')

        # Match the Oana-style preprocessing by taking a running difference along time.
        lower_cube = np.diff(lower_cube, axis = -1)
        higher_cube = np.diff(higher_cube, axis = -1)
        lower_cube = lower_cube - np.mean(lower_cube)
        higher_cube = higher_cube - np.mean(higher_cube)

        # Rebuild the centered radial grid used for the azimuthal averages.
        ny, nx, nt = lower_cube.shape
        end_space = min(nx, ny)
        mid_space = end_space // 2
        mid_time = nt // 2
        x = np.linspace(-mid_space, mid_space - 1, end_space, dtype = np.float64)
        y = np.linspace(-mid_space, mid_space - 1, end_space, dtype = np.float64)
        x_grid, y_grid = np.meshgrid(x, y)
        radial_dist = np.hypot(x_grid, y_grid)

        # Fourier transform the running-difference cubes and build the power spectra.
        fft_lower = np.fft.fftshift(np.fft.fftn(lower_cube))
        fft_higher = np.fft.fftshift(np.fft.fftn(higher_cube))
        cross_power = fft_lower*np.conjugate(fft_higher)
        lower_power = np.abs(fft_lower)**2
        higher_power = np.abs(fft_higher)**2

        # Azimuthally average the cross power and the two auto-power spectra.
        azimuthal_cross_power = azimuthal_average_fft_complex_oana(
            mid_time,
            nt,
            cross_power,
            mid_space,
            radial_dist)
        azimuthal_lower_power = np.real(
            azimuthal_average_fft_complex_oana(
                mid_time,
                nt,
                lower_power,
                mid_space,
                radial_dist))
        azimuthal_higher_power = np.real(
            azimuthal_average_fft_complex_oana(
                mid_time,
                nt,
                higher_power,
                mid_space,
                radial_dist))

        # Convert the azimuthally averaged spectra into magnitude-squared coherence.
        denominator = azimuthal_lower_power*azimuthal_higher_power
        coherence_full = np.divide(
            np.abs(azimuthal_cross_power)**2,
            denominator,
            out = np.zeros_like(np.abs(azimuthal_cross_power), dtype = np.float64),
            where = denominator > 0.0)
        coherence = np.asarray(coherence_full[:, :mid_time], dtype = np.float64)
        axes = build_coherence_axes((nt, ny, nx), dt_seconds, dx_Mm)

        # Record the saved-product metadata for the coherence diagram.
        metadata = {
            'method': 'oana_running_difference_magnitude_squared_coherence',
            'running_difference_applied': True,
            'dx_Mm': dx_Mm,
            'dt_seconds': dt_seconds,
            'lower_index': int(order_metadata.get('lower_index', 0)),
            'higher_index': int(order_metadata.get('higher_index', 1)),
            'k_axis': np.asarray(axes['k_axis'], dtype = np.float64),
            'nu_axis': np.asarray(axes['nu_axis'], dtype = np.float64)}

        if self.magnetic_orientation_metadata is not None:
            metadata['magnetic_orientation'] = copy.deepcopy(self.magnetic_orientation_metadata)

        return coherence, metadata['k_axis'], metadata['nu_axis'], metadata

    def xcorrj(self, v1, v2):

        '''
        Purpose
        -------
        Compute the MATLAB-matched time-distance diagram in parallel by radius.

        Inputs
        ------
        v1: np.array, float
            Lower-height Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Higher-height Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        xc: np.array, float
            Time-distance cross-correlation array.

        phase_diff: np.array, float
            Radius-frequency phase-difference array in degrees.

        radii_pixels: np.array, float
            Annulus radii in pixels.

        time_lags: np.array, float
            Time lags in seconds.

        frequencies: np.array, float
            Temporal frequencies in mHz.

        Author(s)
        ---------
        Julio M. Morales, March 12th, 2026
        '''

        global _fft_lower, _fft_higher, _nx0, _width, _extent, _dx_pixels, _maxpix_geom
        global _annulus_offsets_by_delta, _target_bounds_by_delta, _extent_size

        # Read the user-defined geometry and sampling parameters.
        width = int(self.time_distance['width'])
        dx_pixels = float(self.time_distance['dx_pixels'])
        dx_Mm = float(self.time_distance['p_dx_Mm'])
        dt = float(self.time_distance['dt'])
        maxdist_Mm = float(self.time_distance['maxdist_Mm'])

        # Reorder the cubes to [y, x, t] because xcorrj works in that layout.
        nt, ny0, nx0 = v1.shape
        v1 = np.transpose(v1, (1, 2, 0))
        v2 = np.transpose(v2, (1, 2, 0))

        # Fourier transform the time axis once so every radius reuses the same spectra.
        fft_lower = np.fft.fft(v1, axis = 2)
        fft_higher = np.fft.fft(v2, axis = 2)

        # Convert the requested maximum distance from Mm to pixels and clip it to the cube geometry.
        requested_maxpix = int(np.floor(maxdist_Mm/dx_Mm))
        maxpix_geom = int(np.floor((min(nx0, ny0) - 4*width - 3)/2))

        if maxpix_geom < 0:
            raise ValueError('The cube is too small for xcorrj with the requested annulus width.')

        maxpix = min(requested_maxpix, maxpix_geom)
        if requested_maxpix > maxpix_geom:
            maxdist_geom = maxpix_geom*dx_Mm
            print(
                f'Requested maxdist_Mm = {maxdist_Mm:.3f} exceeds the cube geometry; '
                f'clipping to {maxdist_geom:.3f} Mm ({maxpix_geom} pixels).')

        # Build the annulus-width offsets and the list of radii to evaluate.
        extent = np.arange(-width, width + 1, dtype = int)
        deltas = np.arange(0, maxpix + 1, dtype = int)

        # Publish the shared arrays and geometry caches for the worker loop.
        _fft_lower = fft_lower
        _fft_higher = fft_higher
        _nx0 = min(nx0, ny0)
        _width = width
        _extent = extent
        _dx_pixels = dx_pixels
        _maxpix_geom = maxpix_geom
        _extent_size = max(1, extent.size)
        _annulus_offsets_by_delta, _target_bounds_by_delta = prepare_xcorrj_geometry(
            ny0,
            nx0,
            deltas,
            width,
            dx_pixels)

        # Run each radius in parallel with threads so the shared FFT arrays stay in one process.
        # This workload is typically memory-bandwidth bound, so large thread counts often slow it down.
        requested_workers = self.time_distance.get('nworkers', 'auto')
        recommended_workers = recommend_xcorrj_worker_count(self.config, (nt, ny0, nx0), deltas.size)
        if requested_workers == 'auto':
            ncores = recommended_workers
        else:
            configured_workers = min(deltas.size, max(1, int(requested_workers)))
            ncores = min(configured_workers, recommended_workers)
            if configured_workers > recommended_workers:
                print(
                    f'Configured nworkers = {configured_workers}; '
                    f'capping to {recommended_workers} for this workload.')
        print(f'Running xcorrj across {ncores} worker threads')

        # Compute the radii in parallel and surface worker errors immediately
        results = []
        if ncores == 1:
            for delta in tqdm(deltas, desc = 'Computing skip distances', unit = 'radius'):
                try:
                    results.append(parallel_loop(int(delta)))
                except Exception as exc:
                    raise RuntimeError(f'Radius {int(delta)} failed during xcorrj.') from exc
        else:
            with ThreadPoolExecutor(max_workers = ncores) as executor:
                future_to_delta = {executor.submit(parallel_loop, int(delta)): int(delta) for delta in deltas}

                with tqdm(total = deltas.size, desc = 'Computing skip distances', unit = 'radius') as pbar:
                    for future in as_completed(future_to_delta):
                        delta = future_to_delta[future]
                        try:
                            results.append(future.result())
                        except Exception as exc:
                            raise RuntimeError(f'Radius {delta} failed during xcorrj.') from exc
                        pbar.update(1)

        # Sort the completed radii and rebuild the final output arrays.
        results.sort(key = lambda item: item[0])
        radii_pixels = np.array([item[0] for item in results], dtype = np.float64)
        xc = np.array([item[1] for item in results], dtype = np.float64)
        phase_diff = np.array([item[2] for item in results], dtype = np.float64)

        # Build the physical time-lag and frequency axes for the saved products.
        time_lags = ((np.arange(xc.shape[1]) - xc.shape[1]//2)*dt).astype(np.float64)
        frequencies = np.fft.fftshift(np.fft.fftfreq(xc.shape[1], d = dt))*1.0e3

        return xc, phase_diff, radii_pixels, time_lags, frequencies

    def save_time_distance(
        self,
        xc,
        phase_diff,
        komega_spectrum = None,
        k_axis = None,
        nu_axis = None,
        komega_metadata = None,
        coherence_spectrum = None,
        coherence_k_axis = None,
        coherence_nu_axis = None,
        coherence_metadata = None):

        '''
        Purpose
        -------
        Save the final time-distance array to a FITS file.

        Inputs
        ------
        xc: np.array, float
            Time-distance cross-correlation array.

        phase_diff: np.array, float
            Radius-frequency phase-difference array in degrees.

        komega_spectrum: np.array, float, optional
            Azimuthally averaged k-omega phase-difference map in degrees.

        k_axis: np.array, float, optional
            Positive horizontal-wavenumber axis in 1/Mm.

        nu_axis: np.array, float, optional
            Positive frequency axis in mHz.

        komega_metadata: dict, optional
            Metadata describing the saved k-omega product.

        coherence_spectrum: np.array, float, optional
            Azimuthally averaged running-difference coherence map.

        coherence_k_axis: np.array, float, optional
            Positive horizontal-wavenumber axis for the saved coherence product in 1/Mm.

        coherence_nu_axis: np.array, float, optional
            Positive frequency axis for the saved coherence product in mHz.

        coherence_metadata: dict, optional
            Metadata describing the saved coherence product.

        Outputs
        -------
        None

        Author(s)
        ---------
        Julio M. Morales, March 12th, 2026
        '''

        # Create the output directory and write the core time-distance products.
        self.outfile.parent.mkdir(parents = True, exist_ok = True)
        fits.writeto(self.outfile, np.asarray(xc, dtype = np.float32), overwrite = True)
        fits.writeto(self.phase_outfile, np.asarray(phase_diff, dtype = np.float32), overwrite = True)

        # Save the optional k-omega phase-difference product and its metadata.
        if komega_spectrum is not None:
            k_header = build_kh_nu_fits_header(
                k_axis,
                nu_axis,
                self.time_distance['p_dx_Mm'],
                self.time_distance['dt'],
                'deg',
                'Phase-difference units')
            k_header['SRCMODE'] = str(self.data.get('source_type', ''))
            if komega_metadata is not None:

                # Store the applied phase-delay correction in the FITS header.
                k_header['PHSCORR'] = (float(komega_metadata.get('phase_delay_seconds', 0.0)), 'Applied line-sampling delay [s]')
                k_header['PHSAPP'] = (bool(komega_metadata.get('phase_correction_applied', False)), 'Line-sampling phase correction applied')
                magnetic_orientation = komega_metadata.get('magnetic_orientation', {})
                if len(magnetic_orientation) > 0:

                    # Export the magnetic-orientation summary when single-cube metadata are available.
                    theta_means_deg = magnetic_orientation.get('theta_means_deg', [])
                    phi_means_deg = magnetic_orientation.get('phi_means_deg', [])
                    alfven_sound_ratio = magnetic_orientation.get('alfven_sound_ratio', {})
                    if len(theta_means_deg) > 0 and np.isfinite(theta_means_deg[0]):
                        k_header['THAVG1'] = (float(theta_means_deg[0]), 'Mean inclination at h1 [deg]')
                    if len(theta_means_deg) > 1 and np.isfinite(theta_means_deg[1]):
                        k_header['THAVG2'] = (float(theta_means_deg[1]), 'Mean inclination at h2 [deg]')
                    if len(phi_means_deg) > 0 and np.isfinite(phi_means_deg[0]):
                        k_header['PHAVG1'] = (float(phi_means_deg[0]), 'Mean azimuth at h1 [deg]')
                    if len(phi_means_deg) > 1 and np.isfinite(phi_means_deg[1]):
                        k_header['PHAVG2'] = (float(phi_means_deg[1]), 'Mean azimuth at h2 [deg]')
                    k_header['PHICIRC'] = (
                        str(magnetic_orientation.get('phi_mean_method', '')).strip().lower() == 'circular',
                        'Phi averages use a circular mean')
                    if np.isfinite(float(magnetic_orientation.get('magnitude_epsilon', np.nan))):
                        k_header['BMAGEPS'] = (
                            float(magnetic_orientation['magnitude_epsilon']),
                            'Minimum |B| used for valid angles')
                    if len(alfven_sound_ratio) > 0:
                        if np.isfinite(float(alfven_sound_ratio.get('mean_field_strength_G_between_heights', np.nan))):
                            k_header['BAVG_G'] = (
                                float(alfven_sound_ratio['mean_field_strength_G_between_heights']),
                                'Mean |B| between selected heights [G]')
                        if np.isfinite(float(alfven_sound_ratio.get('mean_density_cgs_between_heights', np.nan))):
                            k_header['RHOAVG'] = (
                                float(alfven_sound_ratio['mean_density_cgs_between_heights']),
                                'Mean rho between selected heights [g cm^-3]')
                        if np.isfinite(float(alfven_sound_ratio.get('mean_sound_speed_km_s_between_heights', np.nan))):
                            k_header['CSAVG'] = (
                                float(alfven_sound_ratio['mean_sound_speed_km_s_between_heights']),
                                'Mean cs between selected heights [km s^-1]')
                        if np.isfinite(float(alfven_sound_ratio.get('alfven_speed_km_s', np.nan))):
                            k_header['CAAVG'] = (
                                float(alfven_sound_ratio['alfven_speed_km_s']),
                                'Mean cA between selected heights [km s^-1]')
                        if np.isfinite(float(alfven_sound_ratio.get('alfven_to_sound_speed_ratio', np.nan))):
                            k_header['CACSRAT'] = (
                                float(alfven_sound_ratio['alfven_to_sound_speed_ratio']),
                                'Mean cA/cs between selected heights')
            # Write the finished k-omega product to disk.
            fits.PrimaryHDU(np.asarray(komega_spectrum, dtype = np.float32), header = k_header).writeto(
                self.komega_outfile,
                overwrite = True)

        # Save the optional coherence product and its metadata.
        if coherence_spectrum is not None:
            c_header = build_kh_nu_fits_header(
                coherence_k_axis,
                coherence_nu_axis,
                self.time_distance['p_dx_Mm'],
                self.time_distance['dt'],
                '1',
                'Magnitude-squared coherence')
            c_header['SRCMODE'] = str(self.data.get('source_type', ''))
            if coherence_metadata is not None:

                # Store the coherence-method metadata in the FITS header.
                c_header['COHMETH'] = (
                    str(coherence_metadata.get('method', '')),
                    'Coherence calculation method')
                c_header['RUNDIFF'] = (
                    bool(coherence_metadata.get('running_difference_applied', False)),
                    'Running difference applied before FFT')
                c_header['LOWINDX'] = (
                    int(coherence_metadata.get('lower_index', 0)),
                    'Lower-forming cube index')
                c_header['HIGINDX'] = (
                    int(coherence_metadata.get('higher_index', 1)),
                    'Higher-forming cube index')
            # Write the finished coherence product to disk.
            fits.PrimaryHDU(np.asarray(coherence_spectrum, dtype = np.float32), header = c_header).writeto(
                self.coherence_outfile,
                overwrite = True)

    def load_time_distance_output(self):

        '''
        Purpose
        -------
        Load the saved time-distance output from disk.

        Inputs
        ------
        None

        Outputs
        -------
        xc: np.array, float
            Saved time-distance cross-correlation array.

        Author(s)
        ---------
        Julio M. Morales, March 12th, 2026
        '''

        # Read the saved time-distance array
        return np.asarray(fits.getdata(self.outfile), dtype = np.float64)

    def load_phase_difference_output(self):

        '''
        Purpose
        -------
        Load the saved phase-difference output from disk.

        Inputs
        ------
        None

        Outputs
        -------
        phase_diff: np.array, float
            Saved radius-frequency phase-difference array in degrees.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the saved phase-difference array
        return np.asarray(fits.getdata(self.phase_outfile), dtype = np.float64)

    def load_komega_output(self):

        '''
        Purpose
        -------
        Load the saved k-omega phase-difference output from disk.

        Inputs
        ------
        None

        Outputs
        -------
        spectrum: np.array, float
            Saved k-omega phase-difference array in degrees.

        Author(s)
        ---------
        Julio M. Morales, March 20th, 2026
        '''

        return np.asarray(fits.getdata(self.komega_outfile), dtype = np.float64)

    def load_coherence_output(self):

        '''
        Purpose
        -------
        Load the saved k-omega coherence output from disk.

        Inputs
        ------
        None

        Outputs
        -------
        coherence: np.array, float
            Saved azimuthally averaged running-difference coherence array.

        Author(s)
        ---------
        Julio M. Morales, March 21st, 2026
        '''

        return np.asarray(fits.getdata(self.coherence_outfile), dtype = np.float64)

    def run(self):

        '''
        Purpose
        -------
        Run the full Dopplergram time-distance pipeline.

        Inputs
        ------
        None

        Outputs
        -------
        results: dict
            Dictionary containing the cross-correlation array, phase-difference array, axes, and output paths.

        Author(s)
        ---------
        Julio M. Morales, March 12th, 2026
        '''

        # Load the working Dopplergram cubes through the configured filter pipeline.
        v1, v2 = self.load_dopplergrams()
        self.magnetic_orientation_metadata = None

        # Build the optional single-cube magnetic-orientation metadata before the spectral products.
        if _normalize_source_type(self.data.get('source_type', 'paired_cubes')) == 'single_cube':
            self.magnetic_orientation_metadata = self.compute_single_cube_magnetic_orientation_metadata()

        # Compute the three core spectral products from the same filtered cubes.
        komega_spectrum, k_axis, nu_axis, komega_metadata = self.compute_komega_diagram(v1, v2)
        coherence_spectrum, coherence_k_axis, coherence_nu_axis, coherence_metadata = self.compute_coherence_diagram(v1, v2)
        analysis_v1, analysis_v2, _ = self.resolve_phase_analysis_cube_order(v1, v2)
        xc, phase_diff, radii_pixels, time_lags, frequencies = self.xcorrj(analysis_v1, analysis_v2)

        # Convert the radii to Mm and save the output
        radii = radii_pixels*float(self.time_distance['p_dx_Mm'])
        self.save_time_distance(
            xc,
            phase_diff,
            komega_spectrum = komega_spectrum,
            k_axis = k_axis,
            nu_axis = nu_axis,
            komega_metadata = komega_metadata,
            coherence_spectrum = coherence_spectrum,
            coherence_k_axis = coherence_k_axis,
            coherence_nu_axis = coherence_nu_axis,
            coherence_metadata = coherence_metadata)

        # Store the results for plotting and reuse
        self.results = {
            'xc': xc,
            'phase_diff': phase_diff,
            'komega': komega_spectrum,
            'komega_kh': k_axis,
            'komega_frequencies': nu_axis,
            'coherence': coherence_spectrum,
            'coherence_kh': coherence_k_axis,
            'coherence_frequencies': coherence_nu_axis,
            'radii_pixels': radii_pixels,
            'radii': radii,
            'time_lags': time_lags,
            'frequencies': frequencies,
            'magnetic_orientation': copy.deepcopy(self.magnetic_orientation_metadata),
            'outfile': self.outfile,
            'phase_outfile': self.phase_outfile,
            'komega_outfile': self.komega_outfile,
            'coherence_outfile': self.coherence_outfile,
            'orientation_validation_outfile': self.orientation_validation_outfile}

        return self.results

# Populate this module-level reference when the pipeline imports `agw_filter.py`.
AGWFilter = None


def resolve_config_file(config_file = None):

    '''
    Purpose
    -------
    Resolve the configuration file path used to build the pipeline.

    Inputs
    ------
    config_file: str or pathlib.Path, optional
        Explicit configuration path.

    Outputs
    -------
    resolved_config_file: pathlib.Path
        Absolute path to the configuration file.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Prefer the explicitly provided config path when one was supplied.
    if config_file not in ['', None]:
        resolved_config_file = Path(config_file)
    else:
        resolved_config_file = Path('config.py')

    # Fall back to the project-local default config when needed.
    if not resolved_config_file.exists():
        resolved_config_file = Path.cwd() / 'Code' / 'Time-Distance' / 'config.py'

    return resolved_config_file.resolve()


def load_config_module(config_file):

    '''
    Purpose
    -------
    Import a configuration module from a file path.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration file to import.

    Outputs
    -------
    config_module: module
        Imported Python configuration module.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Build the import specification and instantiate the config module object.
    config_spec = importlib.util.spec_from_file_location('time_distance_config', config_file)
    config_module = importlib.util.module_from_spec(config_spec)

    # Execute the config module so its exported attributes become available.
    config_spec.loader.exec_module(config_module)

    return config_module


def load_agw_filter_class(config_file):

    '''
    Purpose
    -------
    Import the `AGWFilter` class that lives next to the active configuration file.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration file used to locate `agw_filter.py`.

    Outputs
    -------
    AGWFilter: class
        Imported Gaussian- and magnetogram-filter pipeline class.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Resolve the sibling `agw_filter.py` path next to the active config.
    agw_filter_file = config_file.parent / 'agw_filter.py'
    agw_filter_spec = importlib.util.spec_from_file_location('agw_filter', agw_filter_file)
    agw_filter_module = importlib.util.module_from_spec(agw_filter_spec)

    # Execute the module and return its exported filter class.
    agw_filter_spec.loader.exec_module(agw_filter_module)

    return agw_filter_module.AGWFilter


def build_pipeline(config_file = None, config_override = None):

    '''
    Purpose
    -------
    Build the fully configured time-distance pipeline.

    Inputs
    ------
    config_file: str or pathlib.Path, optional
        Configuration file path.

    config_override: dict, optional
        In-memory configuration override.

    Outputs
    -------
    resolved_config_file: pathlib.Path
        Absolute path to the configuration file.

    config: dict
        Fully prepared runtime configuration.

    pipeline: TimeDistance
        Configured time-distance pipeline instance.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    global AGWFilter

    # Resolve the configuration path before loading or overriding the runtime config.
    resolved_config_file = resolve_config_file(config_file)

    # Load the config from disk unless the caller already provided an in-memory override.
    if config_override is None:
        config = load_time_distance_config(resolved_config_file)
    else:
        config = copy.deepcopy(config_override)

    # Import the sibling filter class and expand the runtime metadata before instantiating the pipeline.
    AGWFilter = load_agw_filter_class(resolved_config_file)
    config = prepare_runtime_config(config)
    config['_module_dir'] = str(resolved_config_file.parent)
    pipeline = TimeDistance(config)

    return resolved_config_file, config, pipeline


def run_time_distance(config_file = None, config_override = None):

    '''
    Purpose
    -------
    Build and execute the time-distance pipeline in one call.

    Inputs
    ------
    config_file: str or pathlib.Path, optional
        Configuration file path.

    config_override: dict, optional
        In-memory configuration override.

    Outputs
    -------
    results: dict
        Pipeline output dictionary returned by `TimeDistance.run()`.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Build the pipeline and execute it in one convenience call.
    _, _, pipeline = build_pipeline(config_file = config_file, config_override = config_override)

    return pipeline.run()


def parse_cli_args(argv = None):

    '''
    Purpose
    -------
    Parse the command-line arguments used by the batch pipeline entry point.

    Inputs
    ------
    argv: list, optional
        Optional argument list passed to `argparse`.

    Outputs
    -------
    args: argparse.Namespace
        Parsed CLI arguments.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    parser = argparse.ArgumentParser(
        description = 'Run the time-distance pipeline using config.py defaults or batch CLI overrides.')
    parser.add_argument('--config', default = None,
        help = 'Path to the configuration Python file. Defaults to config.py in the current directory or Code/Time-Distance/config.py.')
    parser.add_argument('--source-type', choices = ['single_cube', 'paired_cubes'], default = None)
    parser.add_argument('--file', dest = 'files', action = 'append', default = None,
        help = 'Repeat to run multiple single_cube files through the same pipeline.')
    parser.add_argument('--observable', default = None,
        help = 'Override the single_cube observable for all generated runs.')
    parser.add_argument('--h1', type = int, default = None,
        help = 'Override the first height index for a single single_cube run.')
    parser.add_argument('--h2', type = int, default = None,
        help = 'Override the second height index for a single single_cube run.')
    parser.add_argument('--height-pair', nargs = 2, type = int, action = 'append', default = None,
        metavar = ('H1', 'H2'),
        help = 'Repeat to run multiple single_cube height-index pairs.')
    parser.add_argument('--file-1', default = None,
        help = 'Override the first paired_cubes file for a single run.')
    parser.add_argument('--file-2', default = None,
        help = 'Override the second paired_cubes file for a single run.')
    parser.add_argument('--file-pair', nargs = 2, action = 'append', default = None,
        metavar = ('FILE_1', 'FILE_2'),
        help = 'Repeat to run multiple paired_cubes file pairs.')
    parser.add_argument('--delta-z-km', dest = 'delta_z_km', type = float, default = None,
        help = 'Override the paired_cubes physical height separation used for the propagation-angle axis.')
    parser.add_argument('--p-dx-mm', dest = 'p_dx_Mm', type = float, default = None,
        help = 'Override the paired_cubes pixel scale.')
    parser.add_argument('--dt', type = float, default = None,
        help = 'Override the paired_cubes cadence.')

    return parser.parse_args(argv)


def iter_run_configs(base_config, args):

    '''
    Purpose
    -------
    Expand one base configuration into the per-run configurations requested on the CLI.

    Inputs
    ------
    base_config: dict
        Base configuration dictionary.

    args: argparse.Namespace
        Parsed CLI arguments.

    Outputs
    -------
    run_configs: list
        List of per-run configuration dictionaries.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    base_run_config = copy.deepcopy(base_config)
    data = base_run_config['data']
    active_source_type = _normalize_source_type(args.source_type or data['source_type'])

    if active_source_type == 'single_cube':
        if any([
            args.file_1 not in ['', None],
            args.file_2 not in ['', None],
            args.file_pair not in [None, []],
            args.delta_z_km is not None,
            args.p_dx_Mm is not None,
            args.dt is not None]):
            raise ValueError(
                "paired_cubes-only overrides (--file-1, --file-2, --file-pair, --delta-z-km, --p-dx-mm, --dt) "
                "cannot be used when source_type = 'single_cube'.")

        single_cube_config = copy.deepcopy(data.get('single_cube', {}))
        file_list = list(args.files) if args.files not in [None, []] else [single_cube_config['file']]
        height_pairs = [tuple(pair) for pair in args.height_pair] if args.height_pair not in [None, []] else [(
            int(args.h1 if args.h1 is not None else single_cube_config['h1']),
            int(args.h2 if args.h2 is not None else single_cube_config['h2']))]
        observable = args.observable if args.observable not in ['', None] else single_cube_config.get('observable', '')

        run_configs = []
        for file_path in file_list:
            for h1_value, h2_value in height_pairs:
                run_config = copy.deepcopy(base_run_config)
                run_config['data']['source_type'] = active_source_type
                run_config['data']['single_cube']['file'] = file_path
                run_config['data']['single_cube']['observable'] = observable
                run_config['data']['single_cube']['h1'] = int(h1_value)
                run_config['data']['single_cube']['h2'] = int(h2_value)
                run_configs.append(run_config)

        return run_configs

    if any([
        args.files not in [None, []],
        args.observable not in ['', None],
        args.height_pair not in [None, []],
        args.h1 is not None,
        args.h2 is not None]):
        raise ValueError(
            "single_cube-only overrides (--file, --observable, --h1, --h2, --height-pair) "
            "cannot be used when source_type = 'paired_cubes'.")

    paired_config = copy.deepcopy(data.get('paired_cubes', {}))
    default_file_1 = paired_config.get('v1', paired_config.get('file_1', ''))
    default_file_2 = paired_config.get('v2', paired_config.get('file_2', ''))
    file_pairs = [tuple(pair) for pair in args.file_pair] if args.file_pair not in [None, []] else [(
        args.file_1 if args.file_1 not in ['', None] else default_file_1,
        args.file_2 if args.file_2 not in ['', None] else default_file_2)]
    delta_z_km = float(args.delta_z_km if args.delta_z_km is not None else paired_config['delta_z_km'])
    p_dx_Mm = float(args.p_dx_Mm if args.p_dx_Mm is not None else paired_config['p_dx_Mm'])
    dt = float(args.dt if args.dt is not None else paired_config['dt'])

    run_configs = []
    for file_1, file_2 in file_pairs:
        run_config = copy.deepcopy(base_run_config)
        run_config['data']['source_type'] = active_source_type
        run_config['data']['paired_cubes']['v1'] = file_1
        run_config['data']['paired_cubes']['v2'] = file_2
        run_config['data']['paired_cubes']['file_1'] = file_1
        run_config['data']['paired_cubes']['file_2'] = file_2
        run_config['data']['paired_cubes']['delta_z_km'] = delta_z_km
        run_config['data']['paired_cubes']['p_dx_Mm'] = p_dx_Mm
        run_config['data']['paired_cubes']['dt'] = dt
        run_configs.append(run_config)

    return run_configs


def main(argv = None):

    '''
    Purpose
    -------
    Run the command-line time-distance pipeline entry point.

    Inputs
    ------
    argv: list, optional
        Optional command-line argument list.

    Outputs
    -------
    status_code: int
        Process exit status.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    args = parse_cli_args(argv)
    resolved_config_file = resolve_config_file(args.config)
    base_config = copy.deepcopy(load_time_distance_config(resolved_config_file))
    run_configs = iter_run_configs(base_config, args)

    total_runs = len(run_configs)

    for run_index, run_config in enumerate(run_configs, start = 1):
        if total_runs > 1:
            print(f'Running time-distance pipeline [{run_index}/{total_runs}]')

        results = run_time_distance(config_file = resolved_config_file, config_override = run_config)

        print(results['outfile'])
        print(results['phase_outfile'])
        print(results['xc'].shape)
        print(results['phase_diff'].shape)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
