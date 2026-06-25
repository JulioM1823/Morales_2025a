import copy

import numpy as np
import numpy.fft as fft
from scipy.signal.windows import bartlett, gaussian
from tqdm import tqdm

import isothermal_dispersion_equations


def conversion_arcseconds_to_Mm(distance):

    '''
    Purpose
    -------
    Convert an angular size on the sky from arcseconds to megameters on the Sun.

    Inputs
    ------
    distance: float
        Sun-Earth distance in km.

    Outputs
    -------
    distance_Mm_per_arcsec: float
        Physical scale corresponding to one arcsecond, in Mm.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Store the Sun-Earth distance explicitly to mirror the notebook derivation.
    sun_earth_distance_km = distance

    # Convert one arcsecond into radians.
    arcsec_to_rad = (1 / 3600) * (np.pi / 180)

    # Convert the angular size into a physical length on the solar surface.
    distance_km_per_arcsec = sun_earth_distance_km * arcsec_to_rad
    distance_Mm_per_arcsec = (distance_km_per_arcsec * 1000) * 10**(-6)

    return distance_Mm_per_arcsec


def cross_spectrum(time_series1, time_series2):

    '''
    Purpose
    -------
    Compute the complex cross-spectrum of two 3D time-series cubes.

    Inputs
    ------
    time_series1: np.array
        Lower-forming diagnostic cube in [x, y, t] order.

    time_series2: np.array
        Higher-forming diagnostic cube in [x, y, t] order.

    Outputs
    -------
    cross_power: np.array, complex
        Shifted complex cross-spectrum with the same shape as the inputs.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Fourier transform both cubes before combining them into a cross-spectrum.
    fft_1 = fft.fftn(time_series1)
    fft_2 = fft.fftn(time_series2)

    # Multiply one transform by the complex conjugate of the other and shift zero frequency to the center.
    cross_power = fft.fftshift(fft_1 * np.conjugate(fft_2))

    return cross_power


def cross_spectrum1D(time_series1, time_series2):

    '''
    Purpose
    -------
    Compute the complex cross-spectrum of two time-series cubes along the time axis only.

    Inputs
    ------
    time_series1: np.array
        Lower-forming diagnostic cube in [x, y, t] order.

    time_series2: np.array
        Higher-forming diagnostic cube in [x, y, t] order.

    Outputs
    -------
    cross_power: np.array, complex
        Shifted complex cross-spectrum with the same shape as the inputs.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Fourier transform only along the time axis to preserve the spatial layout.
    fft_1 = fft.fft(time_series1, axis = -1)
    fft_2 = fft.fft(time_series2, axis = -1)

    # Combine the time-axis transforms into a shifted cross-spectrum.
    cross_power = fft.fftshift(fft_1 * np.conjugate(fft_2), axes = -1)

    return cross_power


def power_spectrum(time_series):

    '''
    Purpose
    -------
    Compute the 3D power spectrum of a time-series cube.

    Inputs
    ------
    time_series: np.array
        Time-series cube in [x, y, t] order.

    Outputs
    -------
    power: np.array, float
        Power spectrum with the same shape as the input cube.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Fourier transform the cube and shift the origin for plotting and averaging.
    shifted_fft = fft.fftshift(fft.fftn(time_series))

    # Convert the complex Fourier amplitudes into power.
    power = np.abs(shifted_fft) ** 2

    return power


def compute_amplitude_spectrum(time_series):

    '''
    Purpose
    -------
    Compute the amplitude spectrum of a velocity cube.

    Inputs
    ------
    time_series: np.array
        Velocity cube in [x, y, t] order.

    Outputs
    -------
    amplitude: np.array, float
        Amplitude spectrum in the same units as the input velocity.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Fourier transform the cube and shift the origin for plotting and averaging.
    shifted_fft = fft.fftshift(fft.fftn(time_series))

    # Convert the complex Fourier amplitudes into power.
    power = np.abs(shifted_fft) ** 2

    # Apply the notebook normalization before converting power into amplitude.
    power = power / power.size**2
    amplitude = np.sqrt(4 * power)

    return amplitude


def phase_difference_correction(omega, mid_time, mid_space, dtau):

    '''
    Purpose
    -------
    Build the linear phase-delay correction for an azimuthally averaged spectrum.

    Inputs
    ------
    omega: float
        Nyquist angular frequency in rad s^-1.

    mid_time: int
        Number of retained positive frequencies.

    mid_space: int
        Number of retained positive wavenumbers.

    dtau: float
        Sampling delay in seconds.

    Outputs
    -------
    phase_correction: np.array, float
        Phase correction array with shape [mid_space, mid_time].

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Build the one-dimensional phase-delay correction along the frequency axis.
    phase_row = np.linspace(0.0, omega, mid_time) * dtau

    # Replicate the same correction for every retained radial bin.
    phase_correction = np.tile(phase_row, (mid_space, 1))

    return phase_correction


def phase_difference_correction_3D(omega, end_time, end_space, dtau):

    '''
    Purpose
    -------
    Build the linear phase-delay correction for the full 3D FFT cube.

    Inputs
    ------
    omega: float
        Nyquist angular frequency in rad s^-1.

    end_time: int
        Full temporal length of the FFT cube.

    end_space: int
        Full spatial length of the FFT cube.

    dtau: float
        Sampling delay in seconds.

    Outputs
    -------
    phase_correction: np.array, float
        Phase correction array with shape [end_space, end_space, end_time].

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Build the one-dimensional phase-delay correction along the full frequency axis.
    phase_row = np.linspace(-omega, omega, end_time) * dtau

    # Replicate the same correction over both horizontal wavenumber dimensions.
    phase_correction = np.tile(phase_row, (end_space, end_space, 1))

    return phase_correction


def find(condition):

    '''
    Purpose
    -------
    Return the flattened indices where a boolean condition is true.

    Inputs
    ------
    condition: np.array, bool
        Boolean array to inspect.

    Outputs
    -------
    result: np.array, int
        Flattened C-order indices where the condition is true.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Flatten in C order so the returned indices match the later flattening calls.
    (result,) = np.nonzero(np.ravel(condition, order = 'C'))

    return result


def azimuthal_averaging(mid_time, end_time, array, mid_space, radial_meshgrid):

    '''
    Purpose
    -------
    Azimuthally average the positive-frequency half of a 3D FFT cube.

    Inputs
    ------
    mid_time: int
        Half the temporal length of the FFT cube.

    end_time: int
        Full temporal length of the FFT cube.

    array: np.array
        3D FFT cube in [x, y, t] order.

    mid_space: int
        Half the spatial length of the FFT cube.

    radial_meshgrid: np.array, float
        Radial grid used to define the annuli.

    Outputs
    -------
    azimuthal_average: np.array, float
        Azimuthally averaged 2D spectrum.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Allocate the positive-frequency output array with the original even/odd handling.
    if end_time % 2 == 0:
        azimuthal_average = np.zeros([mid_space, mid_time])
    else:
        azimuthal_average = np.zeros([mid_space, mid_time + 1])

    # Copy the input cube so the averaging routine never mutates the caller's array.
    cube_copy = copy.copy(array)

    # Match the original half-pixel radial bin width.
    annulus_half_width = 0.5

    # Loop over the retained positive frequencies.
    for time_index in tqdm(range(mid_time, end_time), desc = 'Azimuthal Averaging'):

        # Extract the 2D Fourier slice for the current frequency.
        fft_slice = cube_copy[:, :, time_index]

        # Loop over the positive radial bins.
        for radius_index in range(1, int(mid_space) + 1):

            # Select the pixels that fall inside the current annulus.
            annulus_mask = np.logical_and(
                radial_meshgrid >= radius_index - annulus_half_width, radial_meshgrid < radius_index + annulus_half_width)

            # Convert the annulus mask into flattened C-order indices.
            annulus_inds = find(annulus_mask == True)

            # Flatten the Fourier slice using the same memory order as the index lookup.
            flat_slice = fft_slice.flatten(order = 'C')

            # Average the Fourier values inside the current annulus.
            annulus_mean = np.mean(flat_slice[annulus_inds])

            # Store the annular mean at the matching radial and frequency index.
            azimuthal_average[radius_index - 1, time_index - int(mid_time)] = annulus_mean

    return azimuthal_average


def azimuthal_averaging2(mid_time, end_time, array, mid_space, radial_meshgrid, w = 0.5):

    '''
    Purpose
    -------
    Azimuthally average the positive-frequency half of a 3D FFT cube with a configurable bin width.

    Inputs
    ------
    mid_time: int
        Half the temporal length of the FFT cube.

    end_time: int
        Full temporal length of the FFT cube.

    array: np.array
        3D FFT cube in [x, y, t] order.

    mid_space: int
        Half the spatial length of the FFT cube.

    radial_meshgrid: np.array, float
        Radial grid used to define the annuli.

    w: float, optional
        Half-width of the radial annulus in pixels.

    Outputs
    -------
    azimuthal_average: np.array, float
        Azimuthally averaged 2D spectrum.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Allocate the positive-frequency output array with the original even/odd handling.
    if end_time % 2 == 0:
        azimuthal_average = np.zeros([mid_space, mid_time])
    else:
        azimuthal_average = np.zeros([mid_space, mid_time + 1])

    # Copy the input cube so the averaging routine never mutates the caller's array.
    cube_copy = copy.copy(array)

    # Loop over the retained positive frequencies.
    for time_index in tqdm(range(mid_time, end_time), desc = 'Azimuthal Averaging'):

        # Extract the 2D Fourier slice for the current frequency.
        fft_slice = cube_copy[:, :, time_index]

        # Loop over the positive radial bins.
        for radius_index in range(1, int(mid_space) + 1):

            # Select the pixels that fall inside the current annulus.
            annulus_mask = np.logical_and(radial_meshgrid >= radius_index - w, radial_meshgrid < radius_index + w)

            # Convert the annulus mask into flattened C-order indices.
            annulus_inds = find(annulus_mask == True)

            # Flatten the Fourier slice using the same memory order as the index lookup.
            flat_slice = fft_slice.flatten(order = 'C')

            # Average the Fourier values inside the current annulus.
            annulus_mean = np.mean(flat_slice[annulus_inds])

            # Store the annular mean at the matching radial and frequency index.
            azimuthal_average[radius_index - 1, time_index - int(mid_time)] = annulus_mean

    return azimuthal_average


def azimuthal_averaging_coherence(mid_time, end_time, array, mid_space, radial_meshgrid):

    '''
    Purpose
    -------
    Azimuthally average a complex 3D FFT cube for coherence calculations.

    Inputs
    ------
    mid_time: int
        Half the temporal length of the FFT cube.

    end_time: int
        Full temporal length of the FFT cube.

    array: np.array
        3D FFT cube in [x, y, t] order.

    mid_space: int
        Half the spatial length of the FFT cube.

    radial_meshgrid: np.array, float
        Radial grid used to define the annuli.

    Outputs
    -------
    azimuthal_average: np.array, complex
        Azimuthally averaged 2D spectrum stored as complex values.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Allocate the positive-frequency output array with the original complex dtype.
    if end_time % 2 == 0:
        azimuthal_average = np.zeros([mid_space, mid_time], np.complex128)
    else:
        azimuthal_average = np.zeros([mid_space, mid_time + 1], np.complex128)

    # Copy the input cube so the averaging routine never mutates the caller's array.
    cube_copy = copy.copy(array)

    # Match the original half-pixel radial bin width.
    annulus_half_width = 0.5

    # Loop over the retained positive frequencies.
    for time_index in tqdm(range(mid_time, end_time), desc = 'Azimuthal Averaging'):

        # Extract the 2D Fourier slice for the current frequency.
        fft_slice = cube_copy[:, :, time_index]

        # Loop over the positive radial bins.
        for radius_index in range(1, int(mid_space) + 1):

            # Select the pixels that fall inside the current annulus.
            annulus_mask = np.logical_and(
                radial_meshgrid >= radius_index - annulus_half_width,
                radial_meshgrid < radius_index + annulus_half_width,
            )

            # Convert the annulus mask into flattened C-order indices.
            annulus_inds = find(annulus_mask == True)

            # Flatten the Fourier slice using the same memory order as the index lookup.
            flat_slice = fft_slice.flatten(order = 'C')

            # Average the Fourier values inside the current annulus.
            annulus_mean = np.mean(flat_slice[annulus_inds])

            # Store the annular mean at the matching radial and frequency index.
            azimuthal_average[radius_index - 1, time_index - int(mid_time)] = annulus_mean

    return azimuthal_average


def create_filter(
    array,
    frequency_array,
    wavenumber_array_kx,
    wavenumber_array_ky,
    central_f,
    width_f,
    central_k,
    width_k,
):

    '''
    Purpose
    -------
    Create the Gaussian AGW filter that isolates power beneath the f-mode and Lamb line.

    Inputs
    ------
    array: np.array
        Data cube in [x, y, t] order.

    frequency_array: np.array
        Frequency array in mHz.

    wavenumber_array_kx: np.array
        Horizontal-wavenumber array along x in 1/Mm.

    wavenumber_array_ky: np.array
        Horizontal-wavenumber array along y in 1/Mm.

    central_f: float
        Central filter frequency in mHz.

    width_f: float
        Frequency width in mHz.

    central_k: float
        Central horizontal wavenumber in 1/Mm.

    width_k: float
        Horizontal-wavenumber width in 1/Mm.

    Outputs
    -------
    filt3D: np.array, float
        Three-dimensional Gaussian AGW filter with the same shape as the input cube.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Read the cube dimensions in the expected [x, y, t] order.
    nx, ny, nt = array.shape

    # Convert the FWHM-like widths into Gaussian sigma values.
    pk0 = central_k
    pkwid = width_k
    pf0 = central_f
    pfwid = width_f
    fsig = pfwid / 2.355
    ksig = pkwid / 2.355

    # Define the fixed solar parameters used by the original filter.
    cs = 7.0
    grav = 0.274

    # Allocate the full three-dimensional filter cube.
    filt3D = np.zeros(array.shape)

    # Build the one-dimensional low-frequency suppressor used in the notebook implementation.
    gaussian_arr = gaussian(nt, (nt - 1.0) / (2.0 * 150.0))
    gaussian_arr = 1.0 - gaussian_arr

    # Build the symmetric frequency Gaussian around +/- central_f.
    e1 = np.exp(-((frequency_array - pf0) ** 2.0) / (2.0 * fsig**2.0)) + np.exp(
        -((frequency_array + pf0) ** 2.0) / (2.0 * fsig**2.0)
    )

    # Reuse a one-dimensional work array for each spatial wavenumber pair.
    filt1D = np.zeros(frequency_array.shape)

    # Loop through the horizontal wavenumber grid to build the full 3D filter.
    for i in tqdm(range(0, nx), desc = 'Creating Filter'):
        for j in range(0, ny):

            # Compute the horizontal wavenumber magnitude for the current pixel.
            k_horizontal = np.sqrt(
                wavenumber_array_kx[i] ** 2.0 + wavenumber_array_ky[j] ** 2.0
            )

            # Apply the radial Gaussian envelope in wavenumber space.
            e2 = np.exp(-((k_horizontal - pk0) ** 2.0) / (2.0 * ksig**2.0))

            # Only define the filter where the horizontal wavenumber is large enough to evaluate the mode boundaries.
            if k_horizontal >= 0.1:

                # Compute the f-mode boundary in mHz.
                fm = (
                    isothermal_dispersion_equations.surface_fmodes(
                        grav, k_horizontal / 1000.0
                    )
                    * 1000.0
                    / (2.0 * np.pi)
                )

                # Compute the Lamb-wave boundary in mHz.
                fc = (
                    isothermal_dispersion_equations.lamb_frequency(
                        cs, np.abs(k_horizontal) / 1000.0
                    )
                    * 1000.0
                    / (2.0 * np.pi)
                )

                # Limit the passband to the smaller of the two mode boundaries and 5 mHz.
                lim = min([fm, fc, 5.0])

                # Select the frequencies that lie inside the allowed passband.
                desired_condition = np.logical_and(
                    frequency_array <= lim, frequency_array >= -lim
                )
                inds = find(desired_condition == True)

                # Build the smooth taper inside the passband.
                inds_max = np.max(inds.shape)
                bartlett_window = bartlett(inds_max)
                bartlett_max = np.max(bartlett_window)

                # Normalize the Bartlett window before inserting it into the filter profile.
                if bartlett_max != 0.0:
                    filt1D[inds] = bartlett_window / bartlett_max

                # Multiply the taper by the frequency and wavenumber Gaussians.
                filt1D = (1 - np.cos(np.pi * filt1D)) / 2.0
                filt1D = filt1D * gaussian_arr * e1 * e2

                # Renormalize only if the constructed profile exceeds unity.
                max_freq_filter = np.max(filt1D)
                if (max_freq_filter != 0.0) and (max_freq_filter > 1.0):
                    filt1D = filt1D / np.max(filt1D)

                # Store the one-dimensional filter profile at the current spatial pixel.
                filt3D[j, i, :] = filt1D

    return filt3D


def make_fourier_grid(dt, dx, array, threeD = False):

    '''
    Purpose
    -------
    Build the Fourier axes used by the filter and azimuthal-averaging routines.

    Inputs
    ------
    dt: float
        Cadence of the time series in seconds.

    dx: float
        Spatial sampling in Mm per pixel.

    array: np.array
        Data cube in [x, y, t] order.

    threeD: bool, optional
        Whether to return the full signed axes instead of the positive halves.

    Outputs
    -------
    omega: float
        Nyquist angular frequency in rad s^-1.

    wavenumber_array_x: np.array
        Horizontal-wavenumber axis along x.

    wavenumber_array_y: np.array
        Horizontal-wavenumber axis along y.

    freq_array: np.array
        Frequency axis in mHz.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Read the cube dimensions in the expected [x, y, t] order.
    nx, ny, nt = array.shape

    # Compute the Nyquist wavenumber and frequency.
    kx = np.pi / dx
    omega = np.pi / dt
    v = omega / (2.0 * np.pi)
    frq = v * 1000.0

    # Print the Nyquist scales to match the original helper behavior.
    print('Nyquist wavenumber: %s 1/Mm' % (kx))
    print('Nyquist frequency: %s mHz' % frq)

    # Determine the full and half lengths of the temporal and spatial axes.
    end_time = nt
    mid_time = end_time // 2
    end_space_x = nx
    end_space_y = ny
    mid_space_x = end_space_x // 2
    mid_space_y = end_space_y // 2

    # Build the full signed grids when the caller needs the 3D Fourier axes.
    if threeD == True:

        # Center zero frequency exactly as in the original notebook implementation.
        if nt % 2 == 0:
            freq_array = np.linspace(-frq, frq, end_time, endpoint = False)
        else:
            freq_array = np.linspace(-frq, frq, end_time, endpoint = True)

        # Center zero horizontal wavenumber along x.
        if nx % 2 == 0:
            wavenumber_array_x = np.linspace(-kx, kx, end_space_x, endpoint = False)
        else:
            wavenumber_array_x = np.linspace(-kx, kx, end_space_x, endpoint = True)

        # Center zero horizontal wavenumber along y.
        if ny % 2 == 0:
            wavenumber_array_y = np.linspace(-kx, kx, end_space_y, endpoint = False)
        else:
            wavenumber_array_y = np.linspace(-kx, kx, end_space_y, endpoint = True)
    else:

        # Keep only the non-negative wavenumbers for azimuthal averaging and plotting.
        wavenumber_array_x = np.linspace(0.0, kx, mid_space_x, endpoint = True)
        wavenumber_array_y = np.linspace(0.0, kx, mid_space_y, endpoint = True)

        # Keep only the non-negative frequencies for azimuthal averaging and plotting.
        freq_array = np.linspace(0.0, frq, int(mid_time), endpoint = True)

    return omega, wavenumber_array_x, wavenumber_array_y, freq_array


def azimuthal_averaging_grid(array):

    '''
    Purpose
    -------
    Build the radial pixel-distance grid used for azimuthal averaging.

    Inputs
    ------
    array: np.array
        Data cube in [x, y, t] order.

    Outputs
    -------
    radial_dist: np.array, float
        Radial distance from the Fourier origin for each spatial pixel.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Read the cube dimensions in the expected [x, y, t] order.
    nx, ny, _ = array.shape

    # Determine the full and half lengths of the spatial axes.
    end_space_x = nx
    end_space_y = ny
    mid_space_x = end_space_x // 2
    mid_space_y = end_space_y // 2

    # Build the signed pixel coordinates around the Fourier origin.
    x = np.linspace(-mid_space_x, mid_space_x - 1, end_space_x)
    y = np.linspace(-mid_space_y, mid_space_y - 1, end_space_y)

    # Combine the pixel coordinates into a 2D radial-distance grid.
    X, Y = np.meshgrid(x, y)
    radial_dist = np.hypot(X, Y)

    return radial_dist


def filter_data(filter_cube, data_cube):

    '''
    Purpose
    -------
    Apply a Fourier-space filter to a time-series cube and transform it back to real space.

    Inputs
    ------
    filter_cube: np.array
        Fourier-space filter cube.

    data_cube: np.array
        Data cube to filter.

    Outputs
    -------
    filtered_cube: np.array, complex
        Filtered cube after the inverse Fourier transform.

    Author(s)
    ---------
    Julio M. Morales, March 22nd, 2026.
    '''

    # Shift the filter back to the uncentered FFT ordering used by `fftn`.
    shift_filter = np.fft.ifftshift(filter_cube)

    # Fourier transform the input cube in the same uncentered ordering.
    fft_cube = np.fft.fftn(np.fft.ifftshift(data_cube))

    # Apply the filter in Fourier space and transform the result back to real space.
    filtered_cube = np.fft.ifftn(fft_cube * shift_filter)
    filtered_cube = np.fft.fftshift(filtered_cube)

    return filtered_cube
