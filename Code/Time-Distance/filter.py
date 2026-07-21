import hashlib
import json
import os
import time

from astropy.io import fits
import h5py
import numpy as np
import numpy.ma as ma
from pathlib import Path
import re
from scipy.signal.windows import bartlett, gaussian
from tqdm import tqdm



try:
    import netCDF4 as nc
except ModuleNotFoundError:
    nc = None


def require_netcdf4():

    '''
    Purpose
    -------
    Raise a clear error when NetCDF support is required but unavailable.

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

    # Stop immediately when the optional NetCDF dependency is unavailable.
    if nc is None:
        raise ModuleNotFoundError(
            "single_cube mode requires the 'netCDF4' package, but it is not installed in the current Python environment.")


MAGNETOGRAM_PATTERN = '*HMImag*.fits'
FILTER_CACHE_VERSION = 1
FILTER_CACHE_DIGEST_LENGTH = 64
FILTER_CACHE_DIRNAME = 'Filters'


def _filter_cache_slugify(value):

    '''
    Convert a cache filename fragment into the same slug style used by pipeline outputs.
    '''

    value = str(value).strip().lower()
    value = value.replace('å', 'a')
    value = re.sub(r'angstrom', 'a', value, flags = re.IGNORECASE)
    value = re.sub(r'[^0-9a-z]+', '_', value)
    value = re.sub(r'_+', '_', value)

    return value.strip('_')


def _filter_cache_join_slug(parts):

    '''
    Join cache filename fragments while dropping empty components.
    '''

    parts = [_filter_cache_slugify(part) for part in parts if str(part).strip() != '']
    parts = [part for part in parts if part != '']

    return '_'.join(parts).strip('_')


def _filter_cache_float_slug(value):

    '''
    Format a floating-point parameter using the existing compact output-token style.
    '''

    return _filter_cache_slugify(f'{float(value):g}')


def _filter_cache_shape_slug(shape):

    '''
    Build a deterministic shape token for cache filenames.
    '''

    return 'shape_' + 'x'.join(str(int(axis_length)) for axis_length in shape)


def resolve_filter_cache_dir(config):

    '''
    Resolve the persistent filter cache directory.
    '''

    paths = config.get('paths', {})
    project_dir = paths.get('project_dir', '')

    if project_dir not in ['', None]:
        return Path(project_dir).expanduser().resolve() / 'Data' / FILTER_CACHE_DIRNAME

    data_output_dir = paths.get('data_output_dir', '')

    if data_output_dir not in ['', None]:
        data_output_path = Path(data_output_dir).expanduser().resolve()

        for candidate_path in [data_output_path, *data_output_path.parents]:
            if candidate_path.name.lower() == 'data':
                return candidate_path / FILTER_CACHE_DIRNAME

        return data_output_path.parent / FILTER_CACHE_DIRNAME

    return Path(__file__).resolve().parents[2] / 'Data' / FILTER_CACHE_DIRNAME


def _filter_cache_jsonable(value):

    '''
    Convert cache metadata into a stable JSON-serializable structure.
    '''

    if isinstance(value, dict):
        return {
            str(key): _filter_cache_jsonable(value[key])
            for key in sorted(value)
        }

    if isinstance(value, (list, tuple)):
        return [_filter_cache_jsonable(item) for item in value]

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    return value


def _filter_cache_metadata_json(metadata):

    '''
    Serialize cache metadata deterministically for hashing and embedded diagnostics.
    '''

    return json.dumps(
        _filter_cache_jsonable(metadata),
        sort_keys = True,
        separators = (',', ':'),
    )


def _filter_cache_digest(metadata):

    '''
    Return a collision-resistant digest for a filter cache metadata payload.
    '''

    encoded_metadata = _filter_cache_metadata_json(metadata).encode('utf-8')

    return hashlib.sha256(encoded_metadata).hexdigest()


def _filter_cache_array_digest(array):

    '''
    Hash an array's dtype, shape, and contiguous bytes for cache key construction.
    '''

    contiguous_array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(contiguous_array.dtype).encode('utf-8'))
    digest.update(str(tuple(int(axis) for axis in contiguous_array.shape)).encode('utf-8'))
    digest.update(contiguous_array.view(np.uint8))

    return digest.hexdigest()


def _filter_cache_file(cache_dir, filename_prefix, metadata, extension):

    '''
    Build the final cache path and full metadata digest.
    '''

    digest = _filter_cache_digest(metadata)
    digest_token = digest[:FILTER_CACHE_DIGEST_LENGTH]
    filename = f'{_filter_cache_slugify(filename_prefix)}_{digest_token}.{extension}'

    return cache_dir / filename, digest


def _atomic_save_npy(file_path, array):

    '''
    Save a NumPy array atomically so concurrent readers never see partial files.
    '''

    file_path.parent.mkdir(parents = True, exist_ok = True)
    temporary_path = file_path.with_name(
        f'.{file_path.name}.{os.getpid()}.{time.time_ns()}.tmp'
    )

    try:
        with temporary_path.open('wb') as handle:
            np.save(handle, np.asarray(array), allow_pickle = False)

        if file_path.exists():
            temporary_path.unlink(missing_ok = True)
            return

        os.replace(temporary_path, file_path)
    except Exception:
        temporary_path.unlink(missing_ok = True)
        raise


def _atomic_save_npz(file_path, **arrays):

    '''
    Save one or more NumPy arrays atomically in a compressed NPZ artifact.
    '''

    file_path.parent.mkdir(parents = True, exist_ok = True)
    temporary_path = file_path.with_name(
        f'.{file_path.name}.{os.getpid()}.{time.time_ns()}.tmp'
    )

    try:
        with temporary_path.open('wb') as handle:
            np.savez_compressed(handle, **arrays)

        if file_path.exists():
            temporary_path.unlink(missing_ok = True)
            return

        os.replace(temporary_path, file_path)
    except Exception:
        temporary_path.unlink(missing_ok = True)
        raise


def build_gaussian_filter_cache_slug(gaussian_config):

    '''
    Build the Gaussian parameter slug used by both outputs and filter cache files.
    '''

    return _filter_cache_join_slug([
        'gauss',
        'ck', f"{float(gaussian_config['central_k']):g}",
        'wk', f"{float(gaussian_config['width_k']):g}",
        'cf', f"{float(gaussian_config['central_f']):g}",
        'wf', f"{float(gaussian_config['width_f']):g}",
    ])


def build_magnetogram_filter_cache_slug(selection, threshold_G):

    '''
    Build the magnetic-threshold slug used by output names and filter cache files.
    '''

    selection = str(selection).strip().lower()
    threshold_slug = _filter_cache_float_slug(threshold_G)

    if selection == 'nonmagnetic':
        relation = 'le'
    elif selection == 'magnetic':
        relation = 'gt'
    else:
        raise ValueError("magnetogram selection must be either 'magnetic' or 'nonmagnetic'.")

    return f'b_{relation}_{threshold_slug}g'


def resolve_dataset_directory(dataset_path):

    '''
    Purpose
    -------
    Resolve the dataset directory used for paired-cube magnetogram discovery.

    Inputs
    ------
    dataset_path: str or pathlib.Path
        Dataset directory or a cube path inside the dataset directory.

    Outputs
    -------
    dataset_directory: pathlib.Path
        Directory searched for the dataset magnetogram.
    '''

    path = Path(dataset_path).expanduser()

    if path.exists() and path.is_dir():
        return path.resolve()

    if path.exists() and path.is_file():
        return path.resolve().parent

    if path.suffix != '':
        return path.resolve().parent

    return path.resolve()


def _is_hmimag_fits(path):

    '''
    Return whether a file matches the paired-cubes HMImag magnetogram convention.
    '''

    return (
        path.is_file()
        and path.suffix.lower() == '.fits'
        and 'hmimag' in path.name.lower()
    )


def find_magnetogram(dataset_path, *, required = True):

    '''
    Purpose
    -------
    Find the unique HMImag FITS magnetogram for a paired-cubes dataset.

    Inputs
    ------
    dataset_path: str or pathlib.Path
        Dataset directory or a cube path inside the dataset directory.

    required: bool, optional
        If True, missing magnetograms raise FileNotFoundError. If False, return None.

    Outputs
    -------
    magnetogram_path: str or None
        Resolved HMImag FITS path, or None when optional and missing.
    '''

    dataset_directory = resolve_dataset_directory(dataset_path)

    if not dataset_directory.exists():
        raise FileNotFoundError(
            'Cannot locate paired_cubes magnetogram because the dataset directory does not exist. '
            f'Dataset path: {dataset_path}. Resolved directory: {dataset_directory}. '
            f'Expected pattern: {MAGNETOGRAM_PATTERN}.'
        )

    if not dataset_directory.is_dir():
        raise NotADirectoryError(
            'Cannot locate paired_cubes magnetogram because the dataset path is not a directory. '
            f'Dataset path: {dataset_path}. Resolved path: {dataset_directory}. '
            f'Expected pattern: {MAGNETOGRAM_PATTERN}.'
        )

    magnetograms = sorted(path for path in dataset_directory.iterdir() if _is_hmimag_fits(path))

    if len(magnetograms) == 0:
        if not required:
            return None
        raise FileNotFoundError(
            'No paired_cubes magnetogram found. '
            f'Dataset path: {dataset_path}. Searched directory: {dataset_directory}. '
            f'Expected pattern: {MAGNETOGRAM_PATTERN}.'
        )

    if len(magnetograms) > 1:
        raise ValueError(
            'Ambiguous paired_cubes magnetogram candidates. '
            f'Dataset path: {dataset_path}. Searched directory: {dataset_directory}. '
            f'Expected exactly one {MAGNETOGRAM_PATTERN}; found: '
            f"{', '.join(path.name for path in magnetograms)}."
        )

    return str(magnetograms[0].resolve())


def find_paired_cubes_magnetogram(v1_path, v2_path = None, *, data_dir = None, required = True):

    '''
    Purpose
    -------
    Find the dataset magnetogram corresponding to a paired-cubes file pair.

    Inputs
    ------
    v1_path, v2_path: str or pathlib.Path
        The paired diagnostic cube paths.

    data_dir: str or pathlib.Path, optional
        Resolved dataset directory when already known by the caller.

    required: bool, optional
        If True, missing magnetograms raise FileNotFoundError. If False, return None.

    Outputs
    -------
    magnetogram_path: str or None
        Resolved HMImag FITS path, or None when optional and missing.
    '''

    if v1_path not in ['', None]:
        dataset_directory = resolve_dataset_directory(v1_path)

        if v2_path not in ['', None]:
            v2_directory = resolve_dataset_directory(v2_path)
            if v2_directory != dataset_directory:
                raise ValueError(
                    'paired_cubes magnetogram discovery requires both cube paths to live in the same dataset directory. '
                    f'v1 directory: {dataset_directory}. v2 directory: {v2_directory}.'
                )
    elif data_dir not in ['', None]:
        dataset_directory = resolve_dataset_directory(data_dir)
    else:
        raise ValueError('paired_cubes magnetogram discovery requires paired cube paths or a dataset directory.')

    return find_magnetogram(dataset_directory, required = required)


def surface_fmodes(g, kh):

    '''
    Purpose
    -------
    Compute the dispersion relation for the f mode.

    Inputs
    ------
    g: float
        Solar gravity in km s^-2.

    kh: float or np.array
        Horizontal wavenumber in km^-1.

    Outputs
    -------
    omega: float or np.array
        Angular frequency in Hz.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Compute the f-mode frequency
    return np.sqrt(g*kh)


def lamb_frequency(cs, kh):

    '''
    Purpose
    -------
    Compute the isothermal Lamb-wave dispersion relation.

    Inputs
    ------
    cs: float
        Sound speed in km s^-1.

    kh: float or np.array
        Horizontal wavenumber in km^-1.

    Outputs
    -------
    omega: float or np.array
        Angular frequency in Hz.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Compute the Lamb-wave frequency
    return cs*kh


def create_filter(array, frequency_array, wavenumber_array_kx, wavenumber_array_ky, central_f, width_f, central_k, width_k):

    '''
    Purpose
    -------
    Build the Gaussian AGW filter under the f mode and Lamb line.

    Inputs
    ------
    array: np.array, float
        Input cube in [x, y, t] order.

    frequency_array: np.array, float
        Frequency array in mHz.

    wavenumber_array_kx: np.array, float
        Horizontal-wavenumber array along x in Mm^-1.

    wavenumber_array_ky: np.array, float
        Horizontal-wavenumber array along y in Mm^-1.

    central_f: float
        Central frequency of the Gaussian ball in mHz.

    width_f: float
        Frequency width of the Gaussian ball in mHz.

    central_k: float
        Central horizontal wavenumber of the Gaussian ball in Mm^-1.

    width_k: float
        Horizontal-wavenumber width of the Gaussian ball in Mm^-1.

    Outputs
    -------
    filt3D: np.array, float
        Gaussian AGW filter with the same shape as the input cube.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Read the cube dimensions and convert the filter widths into Gaussian sigma values.
    nx, ny, nt = array.shape
    fsig = float(width_f) / 2.355
    ksig = float(width_k) / 2.355
    cs = 7.0
    grav = 0.274

    # Create the output filter cube
    filt3D = np.zeros(array.shape, dtype = np.float64)

    # Build the 1D suppressor for the very low frequencies
    gaussian_arr = gaussian(nt, (nt - 1.0) / (2.0*150.0))
    gaussian_arr = 1.0 - gaussian_arr
    e1 = np.exp(-((frequency_array - float(central_f))**2.0)/(2.0*fsig**2.0)) + np.exp(
        -((frequency_array + float(central_f))**2.0)/(2.0*fsig**2.0))

    # Reuse the same 1D work array to match the original filter implementation
    filt1D = np.zeros(frequency_array.shape, dtype = np.float64)

    # Build the full 3D filter
    for i in tqdm(range(0, nx), desc = 'Creating Filter'):
        for j in range(0, ny):

            # Compute the horizontal-wavenumber magnitude for the current spatial pixel.
            k_horizontal = np.sqrt(wavenumber_array_kx[i]**2.0 + wavenumber_array_ky[j]**2.0)
            e2 = np.exp(-((k_horizontal - float(central_k))**2.0)/(2.0*ksig**2.0))

            # Only evaluate the mode boundaries where the horizontal wavenumber is large enough.
            if k_horizontal >= 0.1:
                fm = surface_fmodes(grav, k_horizontal/1000.0)*1000.0/(2.0*np.pi)
                fc = lamb_frequency(cs, np.abs(k_horizontal)/1000.0)*1000.0/(2.0*np.pi)
                lim = min([fm, fc, 5.0])
                inds = np.flatnonzero((frequency_array <= lim) & (frequency_array >= -lim))

                # Build the smooth Bartlett taper over the allowed frequency range.
                if inds.size > 0:
                    bartlett_window = bartlett(int(inds.size))
                    bartlett_max = np.max(bartlett_window)

                    if bartlett_max != 0.0:
                        filt1D[inds] = bartlett_window / bartlett_max

                # Combine the taper with the Gaussian envelopes in frequency and wavenumber.
                filt1D = (1 - np.cos(np.pi*filt1D)) / 2.0
                filt1D = filt1D*gaussian_arr*e1*e2

                # Renormalize only when the filter peak exceeds unity.
                max_freq_filter = np.max(filt1D)
                if (max_freq_filter != 0.0) and (max_freq_filter > 1.0):
                    filt1D = filt1D / max_freq_filter

                # Store the one-dimensional filter profile at the current spatial pixel.
                filt3D[j, i, :] = filt1D

    return filt3D


def make_fourier_grid(dt, dx, array, threeD = False):

    '''
    Purpose
    -------
    Build the Fourier grid used by the Gaussian AGW filter.

    Inputs
    ------
    dt: float
        Cadence of the time series in seconds.

    dx: float
        Spatial sampling in Mm per pixel.

    array: np.array, float
        Input cube in [x, y, t] order.

    threeD: bool, optional
        Whether to build the full 3D grid instead of the reduced 2D grid.

    Outputs
    -------
    omega: float
        Nyquist angular frequency in s^-1.

    wavenumber_array_x: np.array, float
        Horizontal-wavenumber array along x in Mm^-1.

    wavenumber_array_y: np.array, float
        Horizontal-wavenumber array along y in Mm^-1.

    freq_array: np.array, float
        Frequency array in mHz.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Read the cube dimensions and compute the Nyquist scales.
    nx, ny, nt = array.shape
    kx = np.pi / float(dx)
    omega = np.pi / float(dt)
    v = omega / (2.0*np.pi)
    frq = v * 1000.0

    print("Nyquist wavenumber: %s 1/Mm" % (kx))
    print("Nyquist frequency: %s mHz" % frq)

    end_time = nt
    mid_time = end_time // 2
    end_space_x = nx
    end_space_y = ny
    mid_space_x = end_space_x // 2
    mid_space_y = end_space_y // 2

    # Build either the full signed axes or the reduced positive-only axes.
    if threeD == True:
        if nt % 2 == 0:
            freq_array = np.linspace(-frq, frq, end_time, endpoint = False)
        else:
            freq_array = np.linspace(-frq, frq, end_time, endpoint = True)

        if nx % 2 == 0:
            wavenumber_array_x = np.linspace(-kx, kx, end_space_x, endpoint = False)
        else:
            wavenumber_array_x = np.linspace(-kx, kx, end_space_x, endpoint = True)

        if ny % 2 == 0:
            wavenumber_array_y = np.linspace(-kx, kx, end_space_y, endpoint = False)
        else:
            wavenumber_array_y = np.linspace(-kx, kx, end_space_y, endpoint = True)
    else:
        wavenumber_array_x = np.linspace(0.0, kx, mid_space_x, endpoint = True)
        wavenumber_array_y = np.linspace(0.0, kx, mid_space_y, endpoint = True)
        freq_array = np.linspace(0.0, frq, int(mid_time), endpoint = True)

    return omega, wavenumber_array_x, wavenumber_array_y, freq_array


def filter_data(filter_cube, data_cube):

    '''
    Purpose
    -------
    Apply a Fourier-space filter to a data cube and transform it back to real space.

    Inputs
    ------
    filter_cube: np.array, float
        Filter cube with the same shape as the data cube.

    data_cube: np.array, float
        Data cube in [x, y, t] order.

    Outputs
    -------
    final_res: np.array, complex
        Filtered cube after the inverse Fourier transform.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Shift the filter back to the uncentered FFT ordering.
    shift_filter = np.fft.ifftshift(filter_cube)

    # Fourier transform the data cube in the same uncentered ordering.
    fft_cube = np.fft.fftn(np.fft.ifftshift(data_cube))

    # Apply the filter in Fourier space and shift the result back for inspection.
    final_res = np.fft.ifftn(fft_cube * shift_filter)
    final_res = np.fft.fftshift(final_res)

    return final_res


def masked_magnetic_maps(magnetogram_array, mask_value, fill_value = np.nan):

    '''
    Purpose
    -------
    Build magnetic and nonmagnetic masks from a magnetogram cube.

    Inputs
    ------
    magnetogram_array: np.array, float
        Magnetogram cube.

    mask_value: float
        Threshold used to separate magnetic from nonmagnetic pixels.

    fill_value: float, optional
        Fill value applied to the masked arrays.

    Outputs
    -------
    magnetic_map: np.ma.MaskedArray
        Magnetogram masked below the requested threshold.

    nonmagnetic_map: np.ma.MaskedArray
        Magnetogram masked above the requested threshold.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Build the magnetic and nonmagnetic masks
    cop_mag = np.abs(np.array(magnetogram_array, copy = True))
    magnetic_map = ma.masked_less_equal(cop_mag, mask_value, copy = True)
    ma.set_fill_value(magnetic_map, fill_value)
    nonmagnetic_map = ma.masked_greater(cop_mag, mask_value, copy = True)
    ma.set_fill_value(nonmagnetic_map, fill_value)

    return magnetic_map, nonmagnetic_map


def masked_IBIS_cubes_based_on_masked_magnetogram(diagnostic_map, magnetic_map_mask, fill_value = np.nan):

    '''
    Purpose
    -------
    Mask a diagnostic cube using the mask from a magnetogram cube.

    Inputs
    ------
    diagnostic_map: np.array, float
        Diagnostic cube that will be masked.

    magnetic_map_mask: np.ma.MaskedArray
        Magnetogram mask used to define the masked pixels.

    fill_value: float, optional
        Fill value applied to the masked cube.

    Outputs
    -------
    masked_cube: np.ma.MaskedArray
        Masked diagnostic cube.

    Author(s)
    ---------
    Julio M. Morales, March 16th, 2026
    '''

    # Apply the magnetogram mask to the requested cube
    grab_mask = np.ma.getmask(ma.array(magnetic_map_mask, copy = True))
    masked_cube = np.ma.masked_array(
        np.array(diagnostic_map, copy = True),
        mask = grab_mask,
        fill_value = fill_value,
        hard_mask = True)

    return masked_cube


class spectral_analysis:
    make_fourier_grid = staticmethod(make_fourier_grid)
    create_filter = staticmethod(create_filter)
    filter_data = staticmethod(filter_data)


class isothermal_dispersion_equations:
    surface_fmodes = staticmethod(surface_fmodes)
    lamb_frequency = staticmethod(lamb_frequency)


def normalize_source_type(source_type):

    '''
    Purpose
    -------
    Normalize the configured source_type string.

    Inputs
    ------
    source_type: str
        Requested source-type label from the configuration file.

    Outputs
    -------
    normalized_source_type: str
        Canonical source-type label used by the runtime code.

    Author(s)
    ---------
    Julio M. Morales, March 19th, 2026
    '''

    source_type = str(source_type).strip().lower()

    if source_type == 'single_netcdf_cube':
        return 'single_cube'

    return source_type


class AGWFilter:

    def __init__(self, config):

        self.config = config
        self.data = config['data']
        self.time_distance = config['time_distance']
        self.filtering = config.get('filtering', {})

    @staticmethod
    def is_zero_field_simulation_path(file_path):

        '''
        Return whether a simulation path encodes the zero-field z0/0G case.
        '''

        path = Path(file_path)
        component = ''
        strength_token = ''

        for part in path.parts:
            lower_part = part.lower()

            if lower_part == 'z0':
                component = lower_part

            if re.fullmatch(r'0+(?:[._]0+)?g', lower_part):
                strength_token = lower_part

        if component == '' or strength_token == '':
            match = re.search(
                r'(z0)[_\-/](0+(?:[._]0+)?g)',
                str(path),
                flags = re.IGNORECASE)

            if match is not None:
                component = match.group(1).lower()
                strength_token = match.group(2).lower()

        return component == 'z0' or strength_token != ''

    @staticmethod
    def is_netcdf_magnetic_variable_name(variable_name):

        '''
        Return whether a NetCDF variable name is a recognized magnetic component.
        '''

        normalized_name = str(variable_name).strip().lower()
        magnetic_names = {
            'bb1', 'bb2', 'bb3',
            'b1', 'b2', 'b3',
            'bx', 'by', 'bz',
            'b_x', 'b_y', 'b_z',
            'los_b', 'b_los',
            'magx', 'magy', 'magz'}

        return normalized_name in magnetic_names

    def load_fits_cube(self, file_path):

        '''
        Purpose
        -------
        Load a FITS Dopplergram or magnetogram cube from disk.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the FITS cube to be loaded.

        Outputs
        -------
        cube: np.array, float
            Loaded cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the FITS cube from disk
        with fits.open(file_path, memmap = True) as hdul:
            if hdul[0].data is None:
                raise ValueError(f"Primary HDU has no data in {file_path}")
            cube = np.asarray(hdul[0].data, dtype = np.float64)

        return cube

    def select_hdf5_dataset(self, hdf5_file):

        '''
        Purpose
        -------
        Select the most likely 3D data cube from an HDF5 file.

        Inputs
        ------
        hdf5_file: h5py.File
            Open HDF5 file handle.

        Outputs
        -------
        dataset_name: str
            Name of the selected 3D dataset.

        dataset: h5py.Dataset
            Selected 3D dataset handle.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Collect the 3D datasets that could be used as cubes
        datasets = {}

        def visit_datasets(name, obj):
            if isinstance(obj, h5py.Dataset) and obj.ndim == 3:
                datasets[name] = obj

        hdf5_file.visititems(visit_datasets)

        if len(datasets) == 0:
            raise ValueError(f'No 3D datasets were found in {hdf5_file.filename}.')

        preferred_names = ['vz', 'velocity', 'vel', 'data', 'cube', 'bz', 'bx', 'by']
        dataset_lookup = {Path(name).name.lower(): (name, dataset) for name, dataset in datasets.items()}

        for preferred_name in preferred_names:
            if preferred_name in dataset_lookup:
                return dataset_lookup[preferred_name]

        if len(datasets) == 1:
            dataset_name, dataset = next(iter(datasets.items()))
            return dataset_name, dataset

        available = ', '.join(sorted(datasets.keys()))
        raise ValueError(
            f'Could not determine which 3D dataset to load from {hdf5_file.filename}. '
            f'Available 3D datasets: {available}')

    def infer_hdf5_axis_order(self, hdf5_file, dataset):

        '''
        Purpose
        -------
        Infer the axis order of an HDF5 cube from its dimension metadata.

        Inputs
        ------
        hdf5_file: h5py.File
            Open HDF5 file handle.

        dataset: h5py.Dataset
            Selected 3D dataset handle.

        Outputs
        -------
        axis_names: list or None
            List of axis names for the dataset dimensions when they can be inferred.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the NetCDF-style dimension scales when they are available
        dimension_list = dataset.attrs.get('DIMENSION_LIST', None)

        if dimension_list is None:
            return None

        axis_names = []
        for dimension_refs in dimension_list:
            if len(dimension_refs) == 0:
                axis_names.append(None)
                continue

            dimension_scale = hdf5_file[dimension_refs[0]]
            axis_names.append(Path(dimension_scale.name).name.lower())

        if set(['t', 'y', 'x']).issubset(axis_names):
            return axis_names

        return None

    def load_hdf5_cube(self, file_path):

        '''
        Purpose
        -------
        Load an HDF5 Dopplergram or magnetogram cube from disk.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the HDF5 cube to be loaded.

        Outputs
        -------
        cube: np.array, float
            Loaded cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the HDF5 cube from disk and select the 3D dataset
        with h5py.File(file_path, 'r') as hdf5_file:
            dataset_name, dataset = self.select_hdf5_dataset(hdf5_file)
            axis_names = self.infer_hdf5_axis_order(hdf5_file, dataset)
            has_xyz_t_axes = all(axis_name in hdf5_file for axis_name in ['x', 'y', 't'])
            cube = np.asarray(dataset[...], dtype = np.float64)

        # Reorder the cube to [t, y, x] when the axis metadata are available
        if axis_names is not None:
            cube = np.transpose(cube, (axis_names.index('t'), axis_names.index('y'), axis_names.index('x')))
        elif has_xyz_t_axes:
            # The Vigeesh NetCDF-style HDF5 cubes store the data in [x, y, t] order.
            cube = np.transpose(cube, (2, 1, 0))
        else:
            raise ValueError(
                f'Could not infer the axis order for dataset {dataset_name} in {file_path}.')

        return cube

    def load_cube(self, file_path):

        '''
        Purpose
        -------
        Load a Dopplergram or magnetogram cube from disk.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the cube to be loaded.

        Outputs
        -------
        cube: np.array, float
            Loaded cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Detect the input file type and read the cube accordingly
        file_path = Path(file_path).expanduser().resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"Required data cube not found: {file_path}")

        suffix = file_path.suffix.lower()

        if suffix in ['.fits', '.fit', '.fts']:
            cube = self.load_fits_cube(file_path)
        elif suffix in ['.h5', '.hdf5']:
            cube = self.load_hdf5_cube(file_path)
        else:
            raise ValueError(f'Unsupported cube format for {file_path}.')

        if cube.ndim != 3:
            raise ValueError(f"Expected a 3D cube in {file_path}, got shape {cube.shape}")

        return cube

    def normalize_netcdf_observable_name(self, observable_name):

        '''
        Purpose
        -------
        Normalize a user-facing observable name to the corresponding NetCDF variable name.

        Inputs
        ------
        observable_name: str
            User-facing observable name from the configuration file.

        Outputs
        -------
        normalized_observable_name: str
            Canonical NetCDF variable name.

        Author(s)
        ---------
        Julio M. Morales, March 19th, 2026
        '''

        observable_name = str(observable_name).strip()

        if observable_name == '':
            return ''

        alias_lookup = {
               'vx': 'v1',
               'vy': 'v2',
               'vz': 'v3',
               'bx': 'bb1',
               'by': 'bb2',
               'bz': 'bb3',
               'b1': 'bb1',
               'b2': 'bb2',
               'b3': 'bb3'}

        return alias_lookup.get(observable_name.lower(), observable_name)

    def select_netcdf_observable_variable(self, netcdf_file):

        '''
        Purpose
        -------
        Select the requested 4D observable variable from a NetCDF file.

        Inputs
        ------
        netcdf_file: netCDF4.Dataset
            Open NetCDF file handle.

        Outputs
        -------
        variable_name: str
            Name of the selected 4D observable variable.

        variable: netCDF4.Variable
            Selected NetCDF variable handle.

        Author(s)
        ---------
        Julio M. Morales, March 19th, 2026
        '''

        configured_variable = self.normalize_netcdf_observable_name(
            self.data.get('observable', self.data.get('cube_variable', '')).strip())
        preferred_names = ['v3', 'v2', 'v1', 'bb3', 'bb2', 'bb1', 'velocity', 'vel', 'data', 'cube']

        return self.select_netcdf_field_variable(
            netcdf_file,
            configured_variable,
            preferred_names,
            'observable')

    def select_netcdf_field_variable(self, netcdf_file, configured_variable, preferred_names, field_label):

        '''
        Purpose
        -------
        Select a requested 4D field variable from a NetCDF file.

        Inputs
        ------
        netcdf_file: netCDF4.Dataset
            Open NetCDF file handle.

        configured_variable: str
            Optional variable name provided by the configuration file.

        preferred_names: list
            Ordered list of preferred variable names to try when the config does not specify one.

        field_label: str
            Field label used in the error messages.

        Outputs
        -------
        variable_name: str
            Name of the selected 4D variable.

        variable: netCDF4.Variable
            Selected NetCDF variable handle.

        Author(s)
        ---------
        Julio M. Morales, March 19th, 2026
        '''

        # Collect the 4D variables that could be used as the requested field cube
        variables = {name: variable for name, variable in netcdf_file.variables.items() if variable.ndim == 4}

        if len(variables) == 0:
            raise ValueError(f'No 4D variables were found in {netcdf_file.filepath()}.')

        if configured_variable != '':
            variable_lookup = {name.lower(): (name, variable) for name, variable in variables.items()}
            configured_variable_lower = configured_variable.lower()

            if configured_variable in variables:
                return configured_variable, variables[configured_variable]
            if configured_variable_lower in variable_lookup:
                return variable_lookup[configured_variable_lower]

            if configured_variable_lower.startswith('b') and configured_variable_lower in ['bx', 'by', 'bz', 'b1', 'b2', 'b3']:
                normalized_variable = self.normalize_netcdf_observable_name(configured_variable_lower)
                if normalized_variable.lower() in variable_lookup:
                    return variable_lookup[normalized_variable.lower()]

            if configured_variable_lower.startswith('v') and configured_variable_lower in ['vx', 'vy', 'vz']:
                normalized_variable = self.normalize_netcdf_observable_name(configured_variable_lower)
                if normalized_variable.lower() in variable_lookup:
                    return variable_lookup[normalized_variable.lower()]

            if configured_variable not in variables:
                available = ', '.join(sorted(variables.keys()))
                raise ValueError(
                    f'Configured NetCDF {field_label} variable {configured_variable} was not found in '
                    f'{netcdf_file.filepath()}. Available 4D variables: {available}')

        variable_lookup = {name.lower(): (name, variable) for name, variable in variables.items()}

        for preferred_name in preferred_names:
            if preferred_name in variable_lookup:
                return variable_lookup[preferred_name]

        if len(variables) == 1:
            variable_name, variable = next(iter(variables.items()))
            return variable_name, variable

        available = ', '.join(sorted(variables.keys()))
        raise ValueError(
            f'Could not determine which 4D {field_label} variable to load from {netcdf_file.filepath()}. '
            f'Available 4D variables: {available}')

    def select_netcdf_magnetic_variable(self, netcdf_file):

        '''
        Purpose
        -------
        Select the line-of-sight magnetic-field variable from a NetCDF file.

        Inputs
        ------
        netcdf_file: netCDF4.Dataset
            Open NetCDF file handle.

        Outputs
        -------
        variable_name: str
            Name of the selected 4D magnetic-field variable.

        variable: netCDF4.Variable
            Selected NetCDF variable handle.

        Author(s)
        ---------
        Julio M. Morales, March 19th, 2026
        '''

        # Prefer the line-of-sight magnetic component used to build the synthetic magnetogram
        magnetogram_config = self.filtering.get('magnetogram', {})
        configured_variable = self.normalize_netcdf_observable_name(magnetogram_config.get('observable', magnetogram_config.get('cube_variable', '')).strip())
        preferred_names = ['bb3', 'b3', 'bz', 'b_z', 'los_b', 'b_los', 'magz']

        return self.select_netcdf_field_variable(
            netcdf_file,
            configured_variable,
            preferred_names,
            'magnetic-field')

    def infer_netcdf_axis_order(self, variable):

        '''
        Purpose
        -------
        Infer the axis order of a NetCDF 4D cube from its dimension names.

        Inputs
        ------
        variable: netCDF4.Variable
            Selected NetCDF variable handle.

        Outputs
        -------
        axis_order: dict
            Mapping from logical axis names to the corresponding integer axis indices.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Match the NetCDF dimensions to time, height, y, and x
        axis_aliases = {
             't': ['time', 't'],
             'z': ['xc3', 'x3', 'z', 'height', 'depth'],
             'y': ['xc2', 'x2', 'y'],
             'x': ['xc1', 'x1', 'x']}

        dimensions = [dimension.lower() for dimension in variable.dimensions]
        axis_order = {}

        for axis_name, aliases in axis_aliases.items():
            for alias in aliases:
                if alias in dimensions:
                    axis_order[axis_name] = dimensions.index(alias)
                    break

        if set(['t', 'z', 'y', 'x']).issubset(axis_order):
            return axis_order

        raise ValueError(
            f'Could not infer the axis order for variable {variable.name}. '
            f'Found dimensions: {variable.dimensions}')

    def load_netcdf_height_coordinates(self, netcdf_file, variable):

        '''
        Purpose
        -------
        Load the height coordinate for a NetCDF 4D cube when it is available.

        Inputs
        ------
        netcdf_file: netCDF4.Dataset
            Open NetCDF file handle.

        variable: netCDF4.Variable
            Selected NetCDF variable handle.

        Outputs
        -------
        height_coordinates: np.array or None
            Height coordinate array when it can be read and is valid.

        height_variable_name: str or None
            Name of the height coordinate variable when it exists.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Use the hardcoded CO5BOLD height coordinate
        height_variable_name = 'xc3'

        if height_variable_name not in netcdf_file.variables:
            return None, None

        height_variable = netcdf_file.variables[height_variable_name]
        height_coordinates = np.asarray(height_variable[:], dtype = np.float64)
        fill_value = getattr(height_variable, '_FillValue', None)

        if fill_value is not None:
            height_coordinates = np.where(height_coordinates == fill_value, np.nan, height_coordinates)

        # Treat placeholder-filled coordinate arrays as missing coordinates
        if np.all(~np.isfinite(height_coordinates)) or np.nanmax(np.abs(height_coordinates)) > 1.0e30:
            return None, height_variable_name

        return height_coordinates, height_variable_name

    def resolve_netcdf_height_index(self, selector, nz, label):

        '''
        Purpose
        -------
        Resolve a requested NetCDF height into a valid z-index.

        Inputs
        ------
        selector: int or float
            Requested height selector from the configuration file.

        nz: int
            Number of z slices in the 4D cube.

        label: str
            Label used in error messages to identify the requested height.

        Outputs
        -------
        height_index: int
            Selected z-index in the NetCDF cube.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Enforce index-based height selection for single_cube
        try:
            height_index = int(str(selector).strip())
        except ValueError as exc:
            raise ValueError(
                f'{label} = {selector!r} is not a valid z-index. '
                f'Use integer height indices such as 0 through {nz - 1}.') from exc

        if height_index < 0 or height_index >= nz:
            raise IndexError(
                f'{label} resolved to z-index {height_index}, but the NetCDF cube only has {nz} heights.')

        return height_index

    def load_netcdf_height_pair(self, file_path):

        '''
        Purpose
        -------
        Load a single NetCDF 4D cube and extract the two requested height slices.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the NetCDF file that contains the 4D velocity cube.

        Outputs
        -------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        require_netcdf4()

        # Read the 4D NetCDF velocity cube and extract the two requested z slices
        file_path = Path(file_path).expanduser().resolve()
        h1 = self.data['h1']
        h2 = self.data['h2']

        with nc.Dataset(file_path) as netcdf_file:
            variable_name, variable = self.select_netcdf_observable_variable(netcdf_file)
            axis_order = self.infer_netcdf_axis_order(variable)
            height_coordinates, height_variable_name = self.load_netcdf_height_coordinates(netcdf_file, variable)
            cube = np.asarray(variable[:], dtype = np.float64)

        cube = np.transpose(cube, (axis_order['t'], axis_order['z'], axis_order['y'], axis_order['x']))
        nz = cube.shape[1]
        height_index_1 = self.resolve_netcdf_height_index(h1, nz, 'h1')
        height_index_2 = self.resolve_netcdf_height_index(h2, nz, 'h2')

        # Store the resolved heights for downstream inspection and plotting
        self.data['resolved_h1_index'] = height_index_1
        self.data['resolved_h2_index'] = height_index_2
        self.data['observable'] = variable_name

        if height_coordinates is not None:
            self.data['resolved_h1_value'] = float(height_coordinates[height_index_1])
            self.data['resolved_h2_value'] = float(height_coordinates[height_index_2])
            self.data['height_coordinate'] = 'xc3'

        v1 = cube[:, height_index_1, :, :]
        v2 = cube[:, height_index_2, :, :]

        return v1, v2

    def load_netcdf_magnetic_cube(self, file_path):

        '''
        Purpose
        -------
        Load the line-of-sight magnetic field cube from a NetCDF simulation file.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the NetCDF file that contains the 4D magnetic-field cube.

        Outputs
        -------
        cube: np.array, float
            Magnetic-field cube in [t, z, y, x] order.

        variable_name: str
            Name of the selected magnetic-field variable.

        height_coordinates: np.array or None
            Height coordinate values when available.

        height_variable_name: str or None
            Name of the height coordinate variable when available.

        Author(s)
        ---------
        Julio M. Morales, April 28th, 2026.
        '''

        require_netcdf4()

        # Read the 4D magnetic-field cube once so mode-specific selection stays centralized.
        file_path = Path(file_path).expanduser().resolve()

        with nc.Dataset(file_path) as netcdf_file:
            synthetic_zero_field = False

            try:
                variable_name, variable = self.select_netcdf_magnetic_variable(netcdf_file)
            except ValueError:
                if not self.is_zero_field_simulation_path(file_path):
                    raise

                variable_name, variable = self.select_netcdf_observable_variable(netcdf_file)
                synthetic_zero_field = True

            if self.is_zero_field_simulation_path(file_path) and not self.is_netcdf_magnetic_variable_name(variable_name):
                variable_name, variable = self.select_netcdf_observable_variable(netcdf_file)
                synthetic_zero_field = True

            axis_order = self.infer_netcdf_axis_order(variable)
            height_coordinates, height_variable_name = self.load_netcdf_height_coordinates(netcdf_file, variable)
            if synthetic_zero_field:
                cube = np.zeros(variable.shape, dtype = np.float64)
                variable_name = 'synthetic_zero_field'
            else:
                cube = np.asarray(variable[:], dtype = np.float64)

        cube = np.transpose(cube, (axis_order['t'], axis_order['z'], axis_order['y'], axis_order['x']))

        return cube, variable_name, height_coordinates, height_variable_name

    def resolve_netcdf_bottom_height_index(self, height_coordinates, nz):

        '''
        Resolve the lowest simulation height index for bottom-mode magnetograms.
        '''

        if height_coordinates is not None and np.any(np.isfinite(height_coordinates)):
            return int(np.nanargmin(height_coordinates))

        return 0

    def load_netcdf_bottom_layer_magnetogram(self, file_path):

        '''
        Purpose
        -------
        Load the line-of-sight magnetic field from the lowest simulation height.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the NetCDF file that contains the 4D magnetic-field cube.

        Outputs
        -------
        magnetogram: np.array, float
            Synthetic magnetogram cube in [t, y, x] order.
        '''

        cube, variable_name, height_coordinates, height_variable_name = self.load_netcdf_magnetic_cube(file_path)
        nz = cube.shape[1]
        bottom_height_index = self.resolve_netcdf_bottom_height_index(height_coordinates, nz)

        if height_coordinates is not None and np.any(np.isfinite(height_coordinates)):
            self.data['resolved_magnetogram_bottom_value'] = float(height_coordinates[bottom_height_index])
            self.data['magnetogram_height_coordinate'] = height_variable_name

        self.data['resolved_magnetogram_bottom_index'] = bottom_height_index
        self.data['magnetogram_cube_variable'] = variable_name

        return cube[:, bottom_height_index, :, :]

    def load_netcdf_height_pair_magnetograms(self, file_path):

        '''
        Purpose
        -------
        Load magnetic-field maps from the two configured single-cube height indices.

        Inputs
        ------
        file_path: str or pathlib.Path
            Path to the NetCDF file that contains the 4D magnetic-field cube.

        Outputs
        -------
        magnetograms: tuple
            Magnetic maps for h1 and h2 in [t, y, x] order.
        '''

        cube, variable_name, height_coordinates, height_variable_name = self.load_netcdf_magnetic_cube(file_path)
        nz = cube.shape[1]

        if self.data.get('h1', '') in ['', None] or self.data.get('h2', '') in ['', None]:
            raise ValueError(
                "single_cube magnetogram_mode = 'per_height_pair' requires resolved h1 and h2 height indices."
            )

        height_index_1 = self.resolve_netcdf_height_index(self.data['h1'], nz, 'h1 magnetogram')
        height_index_2 = self.resolve_netcdf_height_index(self.data['h2'], nz, 'h2 magnetogram')

        self.data['resolved_magnetogram_h1_index'] = height_index_1
        self.data['resolved_magnetogram_h2_index'] = height_index_2
        self.data['magnetogram_cube_variable'] = variable_name

        if height_coordinates is not None and np.any(np.isfinite(height_coordinates)):
            self.data['resolved_magnetogram_h1_value'] = float(height_coordinates[height_index_1])
            self.data['resolved_magnetogram_h2_value'] = float(height_coordinates[height_index_2])
            self.data['magnetogram_height_coordinate'] = height_variable_name

        return cube[:, height_index_1, :, :], cube[:, height_index_2, :, :]

    def load_netcdf_top_layer_magnetogram(self, file_path):

        '''
        Backward-compatible alias for the explicit bottom-layer magnetogram mode.
        '''

        return self.load_netcdf_bottom_layer_magnetogram(file_path)

    def load_dopplergrams(self):

        '''
        Purpose
        -------
        Load the two Dopplergram cubes defined in the configuration file.

        Inputs
        ------
        None

        Outputs
        -------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the Dopplergram cubes that will be used in the pipeline
        # Normalize the configured source type before branching on the input format.
        source_type = normalize_source_type(self.data.get('source_type', 'paired_cubes'))

        if source_type == 'paired_cubes':
            # Load the two requested FITS or HDF5 cubes independently.
            files = [self.data['v1'], self.data['v2']]
            cubes = []
            for file in tqdm(files, desc = 'Loading Dopplergrams', unit = 'file'):
                cubes.append(self.load_cube(file))

            v1, v2 = cubes
        elif source_type == 'single_cube':
            # Reuse one NetCDF cube and extract the two requested height slices.
            cube_file = self.data.get('file', self.data.get('cube_file', ''))
            if cube_file == '':
                raise ValueError("source_type = 'single_cube' requires data['file'].")

            with tqdm(total = 1, desc = 'Loading Dopplergrams', unit = 'file') as pbar:
                v1, v2 = self.load_netcdf_height_pair(cube_file)
                pbar.update(1)
        else:
            raise ValueError(
                "data['source_type'] must be either 'paired_cubes' or 'single_cube'.")

        return v1, v2

    def build_gaussian_filter(self, cube):

        '''
        Purpose
        -------
        Build the 3D Gaussian AGW filter for a Dopplergram cube.

        Inputs
        ------
        cube: np.array, float
            Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        filter3D: np.array, float
            Gaussian AGW filter in Fourier space.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the Gaussian filter parameters from the runtime config.
        gaussian_config = self.filtering.get('gaussian', {})
        dt = float(self.time_distance['dt'])
        dx_Mm = float(self.time_distance['p_dx_Mm'])
        pf0 = float(gaussian_config['central_f'])
        pfwid = float(gaussian_config['width_f'])
        pk0 = float(gaussian_config['central_k'])
        pkwid = float(gaussian_config['width_k'])

        # Reorder the cube to [x, y, t] because the spectral helper expects that layout.
        cube_xyt = np.transpose(cube, (2, 1, 0))
        cube_xyt_shape = tuple(int(axis_length) for axis_length in cube_xyt.shape)

        # Reuse a persistent Fourier-space filter when this exact parameter set exists.
        cache_metadata = {
            'filter_cache_version': FILTER_CACHE_VERSION,
            'filter_type': 'gaussian_fourier',
            'algorithm': 'agw_create_filter_bartlett_gaussian_v1',
            'shape_xyt': cube_xyt_shape,
            'dt_s': dt,
            'dx_Mm': dx_Mm,
            'central_f_mHz': pf0,
            'width_f_mHz': pfwid,
            'central_k_inv_Mm': pk0,
            'width_k_inv_Mm': pkwid,
            'fourier_grid': 'threeD',
        }
        cache_dir = resolve_filter_cache_dir(self.config)
        cache_prefix = _filter_cache_join_slug([
            'gaussian_filter',
            build_gaussian_filter_cache_slug(gaussian_config),
            _filter_cache_shape_slug(cube_xyt_shape),
            'dt', _filter_cache_float_slug(dt),
            'dx', _filter_cache_float_slug(dx_Mm),
        ])
        cache_file, cache_digest = _filter_cache_file(
            cache_dir,
            cache_prefix,
            cache_metadata,
            'npy',
        )
        self.data['gaussian_filter_cache_file'] = str(cache_file)
        self.data['gaussian_filter_cache_key'] = cache_digest

        if cache_file.exists():
            try:
                filter3D = np.load(cache_file, allow_pickle = False)

                if tuple(filter3D.shape) == cube_xyt_shape:
                    self.data['gaussian_filter_cache_hit'] = True
                    print(f'Loaded Gaussian filter cache: {cache_file}')
                    return filter3D

                print(
                    'Ignoring Gaussian filter cache with unexpected shape: '
                    f'{cache_file} has {filter3D.shape}, expected {cube_xyt_shape}'
                )
            except (OSError, ValueError) as exc:
                print(f'Ignoring unreadable Gaussian filter cache {cache_file}: {exc}')

        self.data['gaussian_filter_cache_hit'] = False
        omega, kx_array, ky_array, freq_array = spectral_analysis.make_fourier_grid(dt, dx_Mm, cube_xyt, threeD = True)

        # Build the three-dimensional Gaussian AGW filter on the reordered grid.
        filter3D = spectral_analysis.create_filter(cube_xyt, freq_array, kx_array, ky_array, pf0, pfwid, pk0, pkwid)
        _atomic_save_npy(cache_file, filter3D)
        print(f'Saved Gaussian filter cache: {cache_file}')

        return filter3D

    def apply_gaussian_filter(self, v1, v2):

        '''
        Purpose
        -------
        Apply the Gaussian AGW filter to the two Dopplergram cubes.

        Inputs
        ------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        v1_filt: np.array, float
            Gaussian-filtered first Dopplergram cube in [t, y, x] order.

        v2_filt: np.array, float
            Gaussian-filtered second Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Build one shared filter from the first cube geometry.
        filter3D = self.build_gaussian_filter(v1)

        # Reorder both cubes to [x, y, t] before filtering them.
        v1_xyt = np.transpose(v1, (2, 1, 0))
        v2_xyt = np.transpose(v2, (2, 1, 0))

        # Filter the first cube and keep the timing information for progress logs.
        print('Applying Gaussian filter in Fourier space to cube 1/2')
        t0 = time.time()
        v1_filt = spectral_analysis.filter_data(filter3D, v1_xyt).real
        print(f'Finished Gaussian filter for cube 1/2 in {time.time() - t0:.2f} s')

        # Filter the second cube with the same Fourier-space mask.
        print('Applying Gaussian filter in Fourier space to cube 2/2')
        t0 = time.time()
        v2_filt = spectral_analysis.filter_data(filter3D, v2_xyt).real
        print(f'Finished Gaussian filter for cube 2/2 in {time.time() - t0:.2f} s')

        # Restore the filtered cubes to the pipeline standard [t, y, x] order.
        return np.transpose(v1_filt, (2, 1, 0)), np.transpose(v2_filt, (2, 1, 0))

    def load_magnetograms(self):

        '''
        Purpose
        -------
        Load the magnetogram input needed for the mode-specific magnetogram filter.

        Inputs
        ------
        None

        Outputs
        -------
        magnetograms: np.array or tuple
            One magnetogram array for paired_cubes and single_cube bottom mode,
            or a two-item tuple for single_cube per_height_pair mode.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Normalize the configured source type before branching on the input format.
        source_type = normalize_source_type(self.data.get('source_type', 'paired_cubes'))

        if source_type == 'single_cube':
            cube_file = self.data.get('file', self.data.get('cube_file', ''))

            if cube_file == '':
                raise ValueError("source_type = 'single_cube' requires data['file'].")

            single_cube_mode = self.get_single_cube_magnetogram_mode()

            if single_cube_mode == 'bottom':
                self.data['magnetogram_mode'] = 'bottom'
                return self.load_netcdf_bottom_layer_magnetogram(cube_file)

            if single_cube_mode == 'per_height_pair':
                self.data['magnetogram_mode'] = 'per_height_pair'
                return self.load_netcdf_height_pair_magnetograms(cube_file)

            raise ValueError(
                "magnetogram_mode['single_cube'] must be either 'bottom' or 'per_height_pair'. "
                f"Received {single_cube_mode!r}."
            )

        # Locate the dataset-specific HMImag magnetogram from the paired cube paths.
        paired_data = self.data.get('paired_cubes', {})
        data_dir = self.data.get('data_dir', paired_data.get('data_dir', ''))
        v1_path = self.data.get('v1', paired_data.get('v1', paired_data.get('file_1', '')))
        v2_path = self.data.get('v2', paired_data.get('v2', paired_data.get('file_2', '')))
        magnetogram_path = Path(
            find_paired_cubes_magnetogram(
                v1_path,
                v2_path,
                data_dir = data_dir,
                required = True,
            )
        ).expanduser().resolve()
        self.data['resolved_magnetogram_file'] = str(magnetogram_path)
        self.data['magnetogram_mode'] = 'dataset'

        # Paired observational diagnostics share the one HMImag cube in their dataset directory.
        loaded_magnetogram = self.load_cube(magnetogram_path)

        # Match the observational notebook convention: HMImag FITS values are
        # stored in deci-Gauss and must be converted to Gauss before applying
        # any magnetic-field threshold in physical units.
        def convert_observational_hmi_magnetogram(cube, file_path):
            # Convert HMImag FITS cubes from deci-Gauss to Gauss before thresholding.
            path = Path(file_path)
            name = path.name.lower()
            if path.suffix.lower() in ['.fits', '.fit', '.fts'] and 'hmimag' in name:
                return np.asarray(cube, dtype = np.float64)/10.0
            return np.asarray(cube, dtype = np.float64)

        return convert_observational_hmi_magnetogram(loaded_magnetogram, magnetogram_path)

    def get_single_cube_magnetogram_mode(self):

        '''
        Return the validated single_cube magnetogram mode.
        '''

        mode_config = self.config.get('magnetogram_mode', {})
        if mode_config in ['', None]:
            mode_config = {}
        if not isinstance(mode_config, dict):
            raise TypeError('magnetogram_mode must be a dictionary.')
        if 'paired_cubes' in mode_config:
            raise ValueError(
                "magnetogram_mode must not define paired_cubes. Observational magnetograms are always auto-discovered."
            )

        single_cube_mode = str(mode_config.get('single_cube', 'bottom')).strip().lower()
        if single_cube_mode not in {'bottom', 'per_height_pair'}:
            raise ValueError(
                "magnetogram_mode['single_cube'] must be either 'bottom' or 'per_height_pair'. "
                f"Received {single_cube_mode!r}."
            )

        return single_cube_mode

    def standardize_magnetogram_pair(self, magnetograms, source_type):

        '''
        Normalize a single magnetogram or two magnetograms into one mask input per cube.
        '''

        source_type = normalize_source_type(source_type)
        is_sequence = isinstance(magnetograms, (tuple, list))

        if source_type == 'paired_cubes':
            if is_sequence:
                if len(magnetograms) != 1:
                    raise ValueError(
                        'paired_cubes magnetogram filtering requires exactly one auto-discovered dataset magnetogram.'
                    )
                magnetogram = magnetograms[0]
            else:
                magnetogram = magnetograms

            return magnetogram, magnetogram, {
                'magnetogram_kind': 'single',
                'magnetogram_mode': 'dataset',
            }

        if source_type == 'single_cube':
            single_cube_mode = self.get_single_cube_magnetogram_mode()
            if is_sequence:
                if len(magnetograms) != 2:
                    raise ValueError(
                        "single_cube magnetogram_mode = 'per_height_pair' requires exactly two magnetograms."
                    )
                return magnetograms[0], magnetograms[1], {
                    'magnetogram_kind': 'pair',
                    'magnetogram_mode': single_cube_mode,
                }

            return magnetograms, magnetograms, {
                'magnetogram_kind': 'single',
                'magnetogram_mode': single_cube_mode,
            }

        raise ValueError("data['source_type'] must be either 'paired_cubes' or 'single_cube'.")

    def compute_magnetogram_filter_masks(self, abs_magnetogram_for_v1, abs_magnetogram_for_v2, selection, threshold_G):

        '''
        Build boolean magnetogram masks from absolute magnetic-field maps.
        '''

        # Build the boolean masks for the requested magnetic-field selection.
        if selection == 'magnetic':
            removed_mask_v1 = abs_magnetogram_for_v1 <= threshold_G
            removed_mask_v2 = abs_magnetogram_for_v2 <= threshold_G
        elif selection == 'nonmagnetic':
            removed_mask_v1 = abs_magnetogram_for_v1 > threshold_G
            removed_mask_v2 = abs_magnetogram_for_v2 > threshold_G
        else:
            raise ValueError("magnetogram selection must be either 'magnetic' or 'nonmagnetic'.")

        return removed_mask_v1, removed_mask_v2

    def load_magnetogram_filter_masks(self):

        '''
        Purpose
        -------
        Load the magnetogram cubes and build the boolean masks used by the magnetic filter.

        Inputs
        ------
        None

        Outputs
        -------
        removed_mask_v1: np.array, bool
            Boolean mask marking the first Dopplergram pixels removed by the magnetic filter.

        removed_mask_v2: np.array, bool
            Boolean mask marking the second Dopplergram pixels removed by the magnetic filter.

        mask_metadata: dict
            Dictionary containing the masking selection, threshold, and magnetograms.

        Author(s)
        ---------
        Julio M. Morales, March 18th, 2026
        '''

        # Read the magnetogram filter parameters
        magnetogram_config = self.filtering.get('magnetogram', {})
        selection = magnetogram_config.get('selection', 'nonmagnetic').lower()
        threshold_G = float(magnetogram_config['threshold_G'])

        # Load and standardize the mode-aware magnetogram input into one mask source per cube.
        source_type = normalize_source_type(self.data.get('source_type', 'paired_cubes'))
        loaded_magnetograms = self.load_magnetograms()
        magnetogram_for_v1, magnetogram_for_v2, magnetogram_metadata = self.standardize_magnetogram_pair(
            loaded_magnetograms,
            source_type,
        )
        magnetogram_for_v1 = np.asarray(magnetogram_for_v1, dtype = np.float64)
        magnetogram_for_v2 = np.asarray(magnetogram_for_v2, dtype = np.float64)

        # Threshold the absolute magnetic field so polarity does not matter.
        abs_magnetogram_for_v1 = np.abs(magnetogram_for_v1)
        abs_magnetogram_for_v2 = np.abs(magnetogram_for_v2)

        if magnetogram_metadata['magnetogram_kind'] == 'single':
            magnetogram_metadata['magnetogram'] = magnetogram_for_v1
            magnetogram_metadata['abs_magnetogram'] = abs_magnetogram_for_v1
        else:
            magnetogram_metadata['magnetograms'] = (magnetogram_for_v1, magnetogram_for_v2)
            magnetogram_metadata['abs_magnetograms'] = (abs_magnetogram_for_v1, abs_magnetogram_for_v2)

        # Return both masks together with the magnetogram metadata used to build them.
        mask_metadata = {
                       'selection': selection,
                     'threshold_G': threshold_G,
        'resolved_magnetogram_file': self.data.get('resolved_magnetogram_file', ''),
            **magnetogram_metadata}

        cache_metadata = {
            'filter_cache_version': FILTER_CACHE_VERSION,
            'filter_type': 'magnetogram_mask',
            'algorithm': 'absolute_field_threshold_mask_v1',
            'selection': selection,
            'threshold_G': threshold_G,
            'shape_v1': tuple(int(axis_length) for axis_length in abs_magnetogram_for_v1.shape),
            'shape_v2': tuple(int(axis_length) for axis_length in abs_magnetogram_for_v2.shape),
            'abs_magnetogram_v1_sha256': _filter_cache_array_digest(abs_magnetogram_for_v1),
            'abs_magnetogram_v2_sha256': _filter_cache_array_digest(abs_magnetogram_for_v2),
        }
        cache_dir = resolve_filter_cache_dir(self.config)
        cache_prefix = _filter_cache_join_slug([
            'magnetogram_filter',
            build_magnetogram_filter_cache_slug(selection, threshold_G),
            'v1', _filter_cache_shape_slug(abs_magnetogram_for_v1.shape),
            'v2', _filter_cache_shape_slug(abs_magnetogram_for_v2.shape),
        ])
        cache_file, cache_digest = _filter_cache_file(
            cache_dir,
            cache_prefix,
            cache_metadata,
            'npz',
        )
        self.data['magnetogram_filter_cache_file'] = str(cache_file)
        self.data['magnetogram_filter_cache_key'] = cache_digest

        if cache_file.exists():
            try:
                with np.load(cache_file, allow_pickle = False) as cached_masks:
                    removed_mask_v1 = np.asarray(cached_masks['removed_mask_v1'], dtype = bool)
                    removed_mask_v2 = np.asarray(cached_masks['removed_mask_v2'], dtype = bool)

                if (
                    removed_mask_v1.shape == abs_magnetogram_for_v1.shape
                    and removed_mask_v2.shape == abs_magnetogram_for_v2.shape
                ):
                    self.data['magnetogram_filter_cache_hit'] = True
                    print(f'Loaded magnetogram filter cache: {cache_file}')
                    return removed_mask_v1, removed_mask_v2, mask_metadata

                print(
                    'Ignoring magnetogram filter cache with unexpected shapes: '
                    f'{cache_file} has {removed_mask_v1.shape}/{removed_mask_v2.shape}, '
                    f'expected {abs_magnetogram_for_v1.shape}/{abs_magnetogram_for_v2.shape}'
                )
            except (KeyError, OSError, ValueError) as exc:
                print(f'Ignoring unreadable magnetogram filter cache {cache_file}: {exc}')

        self.data['magnetogram_filter_cache_hit'] = False
        removed_mask_v1, removed_mask_v2 = self.compute_magnetogram_filter_masks(
            abs_magnetogram_for_v1,
            abs_magnetogram_for_v2,
            selection,
            threshold_G,
        )
        _atomic_save_npz(
            cache_file,
            removed_mask_v1 = np.asarray(removed_mask_v1, dtype = bool),
            removed_mask_v2 = np.asarray(removed_mask_v2, dtype = bool),
            cache_metadata_json = np.asarray(_filter_cache_metadata_json(cache_metadata)),
        )
        print(f'Saved magnetogram filter cache: {cache_file}')

        return removed_mask_v1, removed_mask_v2, mask_metadata

    def apply_magnetogram_filter(self, v1, v2):

        '''
        Purpose
        -------
        Apply the magnetogram mask to the two Dopplergram cubes.

        Inputs
        ------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        v1_filt: np.array, float
            Magnetogram-filtered first Dopplergram cube in [t, y, x] order.

        v2_filt: np.array, float
            Magnetogram-filtered second Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Read the magnetogram filter parameters and build the boolean masks
        magnetogram_config = self.filtering.get('magnetogram', {})
        fill_value = float(magnetogram_config.get('fill_value', 0.0))
        removed_mask_v1, removed_mask_v2, _ = self.load_magnetogram_filter_masks()

        # Apply the boolean masks to copies of the two Dopplergram cubes.
        v1_filt = np.ma.masked_array(np.array(v1, copy = True), mask = removed_mask_v1, fill_value = fill_value, hard_mask = True)
        v2_filt = np.ma.masked_array(np.array(v2, copy = True), mask = removed_mask_v2, fill_value = fill_value, hard_mask = True)

        # Fill the masked pixels with the configured replacement value.
        return np.asarray(v1_filt.filled(fill_value), dtype = np.float64), np.asarray(v2_filt.filled(fill_value), dtype = np.float64)

    def apply_filters(self, v1, v2):

        '''
        Purpose
        -------
        Apply the configured filters to the two Dopplergram cubes in sequence.

        Inputs
        ------
        v1: np.array, float
            First Dopplergram cube in [t, y, x] order.

        v2: np.array, float
            Second Dopplergram cube in [t, y, x] order.

        Outputs
        -------
        v1_filt: np.array, float
            Filtered first Dopplergram cube in [t, y, x] order.

        v2_filt: np.array, float
            Filtered second Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Apply each configured filter in order
        for filter_name in self.filtering.get('filter_sequence', []):

            # Apply the Gaussian AGW filter when it appears in the configured sequence.
            if filter_name == 'gaussian':
                if self.filtering.get('gaussian', {}).get('enabled', False):
                    print('Applying Gaussian filter to the Dopplergrams')
                    v1, v2 = self.apply_gaussian_filter(v1, v2)

            # Apply the magnetogram mask when it appears in the configured sequence.
            elif filter_name == 'magnetogram':
                if self.filtering.get('magnetogram', {}).get('enabled', False):
                    print('Applying magnetogram filter to the Dopplergrams')
                    v1, v2 = self.apply_magnetogram_filter(v1, v2)
            else:
                raise ValueError(f"Unknown filter name: {filter_name}")

        return v1, v2

    def run(self):

        '''
        Purpose
        -------
        Load the Dopplergrams and optionally apply the configured filters.

        Inputs
        ------
        None

        Outputs
        -------
        v1_filt: np.array, float
            Final first Dopplergram cube in [t, y, x] order.

        v2_filt: np.array, float
            Final second Dopplergram cube in [t, y, x] order.

        Author(s)
        ---------
        Julio M. Morales, March 13th, 2026
        '''

        # Load the Dopplergrams that will be passed into the time-distance pipeline
        v1, v2 = self.load_dopplergrams()

        # Return the raw cubes immediately when filtering is disabled globally.
        if not self.filtering.get('enabled', False):
            print('Filtering disabled; using raw Dopplergrams')
            return v1, v2

        # Return the raw cubes when no filters were listed in the configured sequence.
        if len(self.filtering.get('filter_sequence', [])) == 0:
            print("Filtering enabled but no filters are listed in filtering['filter_sequence']; using raw Dopplergrams")
            return v1, v2

        # Otherwise apply the configured filters in sequence.
        return self.apply_filters(v1, v2)
