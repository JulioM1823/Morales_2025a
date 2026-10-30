'''
Purpose
-------
Estimate measured annular/frequency-pooled magnitude-squared coherence independently of
dispersion models and display filters.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for spectral_coherence.py.

Notes
-----
Measured k–ω coherence, independent of dispersion solvers and display filters.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import convolve1d

import pipeline


@dataclass(frozen=True)
class CoherenceResult:
    '''
    Purpose
    -------
    Hold read-only pooled spectral estimates and their exact physical FFT coordinates.

    Inputs
    ------
    values: np.ndarray
        Magnitude-squared coherence in [0, 1], with undefined/low-power bins as NaN.
    kh: np.ndarray
        Exact angular horizontal-wavenumber bins in rad/Mm.
    nu: np.ndarray
        Nonnegative cyclic frequency bins in mHz.
    auto_lower: np.ndarray
        Pooled lower-height auto spectrum after independent velocity normalization.
    auto_higher: np.ndarray
        Pooled higher-height auto spectrum using the same normalization convention.
    cross: np.ndarray
        Complex lower-times-conjugate-higher pooled cross spectrum.
    samples: np.ndarray
        Pooled Fourier-coefficient counts, not independent degrees of freedom.
    metadata: dict
        FFT, pooling, physical sampling, delay, and numerical-validity provenance.

    Outputs
    -------
    result: CoherenceResult
        Dimensionless coherence and supporting spectra in project (n_kh, n_nu) order.
    '''

    values: np.ndarray                 # [kh, nu], like the pipeline products
    kh: np.ndarray                     # angular horizontal wavenumber [rad/Mm]
    nu: np.ndarray                     # cyclic frequency [mHz]; omega=2*pi*nu/1000
    auto_lower: np.ndarray
    auto_higher: np.ndarray
    cross: np.ndarray
    samples: np.ndarray                # pooled coefficients, not independent DOF
    metadata: dict


def estimate_coherence(v1, v2, dt_seconds, dx_Mm, *, dy_Mm=None,
                       frequency_bins=5, minimum_samples=5, relative_power_floor=1e-12,
                       phase_delay_seconds=0.):
    '''
    Purpose
    -------
    Estimate annular and neighboring-frequency pooled magnitude-squared coherence.

    Inputs
    ------
    v1: np.ndarray
        Lower-height cube in (t, y, x) order.
    v2: np.ndarray
        Matching higher-height cube in the same velocity units.
    dt_seconds: float
        Positive temporal cadence in seconds.
    dx_Mm: float
        Positive x pixel spacing in Mm.
    dy_Mm: float or None
        Positive y pixel spacing in Mm; defaults to dx_Mm.
    frequency_bins: int
        Odd smoothing-box width of at least three nonnegative frequency bins.
    minimum_samples: number
        Minimum pooled coefficient count required for a defined estimate, at least two.
    relative_power_floor: float
        Relative auto-power threshold in [0, 1).
    phase_delay_seconds: float
        Finite lower-minus-higher sampling delay corrected in the cross spectrum before
        pooling.

    Outputs
    -------
    result: CoherenceResult
        Read-only coherence, exact axes, pooled auto/cross spectra, counts, and
        provenance. Invalid shapes/sampling/averaging controls raise ValueError;
        undefined or weak-power bins remain NaN.

    Notes
    -----
    Pool spectra over physical annuli and neighboring positive frequencies.

    The full-record FFT, global mean removal, rectangular window and cross sign
    match TimeDistance.compute_komega_diagram. Unlike legacy endpoint plotting
    labels, coordinates here are exact fftfreq values. Equal-weight annular
    sums are pooled over an odd frequency boxcar BEFORE taking |S12|²/S11/S22.
    No per-coefficient coherence ratios or complex amplitudes are averaged.

    A spatial time series missing any sample at either height is excluded at
    BOTH heights (a common spatial window). No missing velocities are invented.
    Spectra use independently scaled velocities for numerical stability; the
    scales cancel exactly in coherence. Undefined/low-power bins remain NaN.
    '''
    # Estimate annular and neighboring-frequency pooled magnitude-squared coherence
    lower, higher = np.asarray(v1, dtype=float), np.asarray(v2, dtype=float)
    if lower.ndim != 3 or lower.shape != higher.shape:
        raise ValueError('Coherence requires matching [t,y,x] Dopplergram cubes.')
    nt, ny, nx = lower.shape
    dy_Mm = dx_Mm if dy_Mm is None else dy_Mm
    if min(nx, ny) < 4 or nt < 8:
        raise ValueError('Coherence requires at least 4×4 spatial and 8 temporal samples.')
    if not all(np.isfinite(v) and v > 0 for v in (dt_seconds, dx_Mm, dy_Mm)):
        raise ValueError('Coherence sampling must be finite and positive.')
    if not np.isfinite(phase_delay_seconds):
        raise ValueError('The observational sampling delay must be finite.')
    if frequency_bins < 3 or frequency_bins % 2 != 1 or int(frequency_bins) != frequency_bins:
        raise ValueError('Frequency averaging requires an odd integer of at least 3 bins.')
    if minimum_samples < 2 or not 0 <= relative_power_floor < 1:
        raise ValueError('Invalid coherence sample count or relative power floor.')
    spatial_valid = np.all(np.isfinite(lower) & np.isfinite(higher), axis=0)
    if not spatial_valid.any():
        raise ValueError('No complete, jointly finite spatial time series at the two heights.')

    scales = []
    transforms = []
    for cube in (lower, higher):
        valid = cube[:, spatial_valid]
        scale = float(np.max(np.abs(valid)))
        scales.append(scale)
        clean = np.zeros(cube.shape, dtype=float)
        if scale > 0:
            scaled = valid / scale
            clean[:, spatial_valid] = scaled - np.mean(scaled)
        # The existing radial averaging helper consumes [y,x,t] shifted FFTs.
        transforms.append(np.fft.fftshift(np.fft.fftn(clean.transpose(1, 2, 0))))
    first, second = transforms
    # Periodogram density normalization is common to all three spectra.
    normalization = float(dt_seconds) / (nt * nx * ny)

    kx = 2*np.pi*np.fft.fftshift(np.fft.fftfreq(nx, float(dx_Mm)))
    ky = 2*np.pi*np.fft.fftshift(np.fft.fftfreq(ny, float(dy_Mm)))
    dk = max(2*np.pi/(nx*dx_Mm), 2*np.pi/(ny*dy_Mm))
    maximum_k = min(np.max(np.abs(kx)), np.max(np.abs(ky)))
    kh = np.arange(int(np.floor(maximum_k/dk + 1e-10)) + 1) * dk
    radius = np.hypot(ky[:, None], kx[None, :])
    _, bins, _ = pipeline.build_radial_bin_lookup(radius/dk)
    # Native averaging retains bins 1..N. Offset by one to retain physical DC.
    bins = bins + 1
    bins[radius.ravel() > maximum_k + dk*1e-10] = len(kh) + 1
    counts = np.bincount(bins, minlength=len(kh)+2).astype(float)
    radial_counts = counts[1:len(kh)+1, None]
    nu = np.fft.fftshift(np.fft.fftfreq(nt, float(dt_seconds)))[nt//2:] * 1000
    kernel = np.ones(int(frequency_bins), dtype=float)
    # Pool sums rather than means, so small/edge annuli have their true weight.
    samples = convolve1d(np.broadcast_to(radial_counts, (len(kh), len(nu))),
                         kernel, axis=1, mode='constant', cval=0.)

    def average(spectrum, correct_phase=False):
        '''
        Purpose
        -------
        Average annular spectral sums over neighboring frequency bins with count
        weighting.

        Inputs
        ------
        spectrum: np.ndarray
            Shifted (y, x, t) auto or complex cross spectrum.
        correct_phase: bool
            Apply the enclosing physical delay correction before cross-spectrum pooling.

        Outputs
        -------
        spectrum: np.ndarray
            Pooled (n_kh, n_nu) auto/cross spectrum, with zeros where the pooled count
            is zero.
        '''

        # Average annular spectral sums over neighboring frequency bins with count
        # weighting
        annular = pipeline.azimuthal_average_positive_frequency_slices(
            spectrum, nt//2, len(kh), bins, counts)
        if correct_phase and phase_delay_seconds:
            # Same lower-minus-higher delay sign as the native phase pipeline,
            # on actual frequencies. Correct before pooling neighboring bins.
            annular = annular * np.exp(2j*np.pi*nu[None, :]*.001*phase_delay_seconds)
        pooled = convolve1d(annular * radial_counts, kernel, axis=1,
                            mode='constant', cval=0.)
        return np.divide(pooled, samples, out=np.zeros_like(pooled), where=samples > 0)

    # Reduce each large spectrum immediately; cache only the small 2-D products.
    p1 = average(np.abs(first) ** 2 * normalization)
    p2 = average(np.abs(second) ** 2 * normalization)
    s12 = average(first * np.conjugate(second) * normalization, correct_phase=True)
    del first, second, transforms, clean, valid
    valid = ((samples >= minimum_samples) & np.isfinite(p1) & np.isfinite(p2)
             & np.isfinite(s12) & (p1 > relative_power_floor*np.max(p1))
             & (p2 > relative_power_floor*np.max(p2)))
    # Sequential division avoids underflow in P11*P22 in low-power bins.
    coherence = np.full(p1.shape, np.nan)
    coherence[valid] = (np.abs(s12[valid])/np.sqrt(p1[valid])/np.sqrt(p2[valid]))**2
    coherence[valid] = np.clip(coherence[valid], 0., 1.)
    metadata = dict(method='annular_and_frequency_averaged_magnitude_squared_coherence',
        preprocessing='global mean removed; full-record rectangular window; common complete spatial time-series mask',
        running_difference_applied=False, frequency_bins=int(frequency_bins),
        phase_delay_seconds=float(phase_delay_seconds),
        frequency_width_mHz=float(frequency_bins*1000/(nt*dt_seconds)),
        kh_bin_width_rad_per_Mm=float(dk), minimum_pooled_coefficients=minimum_samples,
        relative_power_floor=relative_power_floor, velocity_scales=scales,
        spectral_units='periodogram density of independently normalized velocities; common factors cancel in coherence',
        complete_spatial_fraction=float(spatial_valid.mean()),
        sampling=dict(shape_t_y_x=list(lower.shape), dt_seconds=dt_seconds, dx_Mm=dx_Mm, dy_Mm=dy_Mm),
        axes='exact FFT coordinates; kh angular rad/Mm, nu cyclic mHz; omega=2*pi*nu/1000 rad/s',
        averaging_note='Pooled coefficient counts are not effective independent degrees of freedom; annular stationarity and local frequency smoothing are assumed.')
    for array in (coherence, kh, nu, p1, p2, s12, samples):
        array.setflags(write=False)
    return CoherenceResult(coherence, kh, nu, p1, p2, s12, samples, metadata)


def align_coherence(result, kh, nu):
    '''
    Purpose
    -------
    Interpolate measured coherence to a model image grid without extrapolating or
    crossing invalid support.

    Inputs
    ------
    result: CoherenceResult
        Measured coherence and exact source coordinates.
    kh: array-like
        Target horizontal-wavenumber coordinates in rad/Mm.
    nu: array-like
        Target cyclic frequencies in mHz.

    Outputs
    -------
    values: np.ndarray
        Dimensionless coherence with shape (len(nu), len(kh)); unsupported locations
        remain NaN.

    Notes
    -----
    Linear interpolation to a model's [nu,kh] grid, with no extrapolation.
    '''
    # Interpolate measured coherence to a model image grid without extrapolating or
    # crossing invalid support
    kh_grid, nu_grid = np.meshgrid(np.asarray(kh, dtype=float), np.asarray(nu, dtype=float))
    finite = np.isfinite(result.values)
    interpolator = RegularGridInterpolator((result.kh, result.nu), np.where(finite, result.values, 0.),
        bounds_error=False, fill_value=np.nan)
    points = np.stack((kh_grid, nu_grid), axis=-1)
    values = interpolator(points)
    support = RegularGridInterpolator((result.kh, result.nu), finite.astype(float),
        bounds_error=False, fill_value=0.)(points)
    values[support < 1.-1e-12] = np.nan
    return np.clip(values, 0., 1.)


def coherence_weights(values, threshold=0.):
    '''
    Purpose
    -------
    Convert finite threshold-qualified coherence values into bounded visibility weights.

    Inputs
    ------
    values: array-like
        Measured or aligned dimensionless coherence values.
    threshold: float
        Required coherence value between zero and one, inclusive.

    Outputs
    -------
    weights: np.ndarray
        Clipped [0, 1] values for qualifying finite cells and zero elsewhere; invalid
        thresholds raise ValueError.
    '''

    # Convert finite threshold-qualified coherence values into bounded visibility
    # weights
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Coherence threshold must be between 0 and 1.')
    values = np.asarray(values, dtype=float)
    return np.where(np.isfinite(values) & (values >= threshold), np.clip(values, 0., 1.), 0.)


def data_key(data):
    '''
    Purpose
    -------
    Build and validate the immutable baseline identity used to reuse measured coherence.

    Inputs
    ------
    data: ObservationData
        Loaded original/post-magnetogram cubes and their analysis configuration.

    Outputs
    -------
    key: tuple
        Dataset/cube identities, shape, physical settings, magnetic preprocessing, and
        source versions; missing inputs or changed files raise ValueError.

    Notes
    -----
    Invalidate on source versions, height/observable, sampling or preprocessing.

    Cube identity also protects source-less in-memory data. Loaded Dopplergrams
    are an immutable baseline; changes to the current Gaussian are display-only
    and intentionally absent from this key.
    '''
    # Build and validate the immutable baseline identity used to reuse measured
    # coherence
    if data is None or data.dopplergrams is None or data.analysis_config is None:
        raise ValueError('Original Dopplergrams and height-pair provenance are unavailable for this dataset.')
    config = data.analysis_config
    versions = config.get('_dopplergram_source_versions', [])
    for path, size, mtime, ctime in versions:
        stat = Path(path).stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (size, mtime, ctime):
            raise ValueError('Original Dopplergram changed; reselect the dataset before calculating coherence.')
    source = config['data']
    inputs = {key: source.get(key) for key in ('source_type', 'file', 'v1', 'v2', 'h1', 'h2',
        'observable', 'resolved_h1_index', 'resolved_h2_index', 'resolved_h1_km', 'resolved_h2_km')}
    return (data.observation.id, tuple(id(cube) for cube in data.dopplergrams),
        tuple(data.dopplergrams[0].shape), json.dumps(inputs, sort_keys=True),
        json.dumps(config['time_distance'], sort_keys=True, default=str),
        json.dumps(config.get('filtering', {}).get('magnetogram', {}), sort_keys=True),
        tuple(tuple(entry) for entry in versions))


def coherence_for_data(data):
    '''
    Purpose
    -------
    Compute measured coherence using the native lower/higher ordering and observational
    delay convention.

    Inputs
    ------
    data: ObservationData
        Selected original/post-magnetogram baseline before the current Gaussian
        adjustment.

    Outputs
    -------
    result: CoherenceResult
        Source-validated estimate with dataset, height-pair, ordering, and input
        provenance added to metadata.
    '''

    # Compute measured coherence using the native lower/higher ordering and
    # observational delay convention
    key = data_key(data)
    engine = pipeline.TimeDistance(data.analysis_config)
    lower, higher, order = engine.resolve_phase_analysis_cube_order(*data.dopplergrams)
    sampling = data.analysis_config['time_distance']
    delay = (0. if data.analysis_config['data']['source_type'] == 'single_cube'
             else float(order.get('phase_delay_seconds', 0.)))
    result = estimate_coherence(lower, higher, sampling['dt'], sampling['p_dx_Mm'],
                                phase_delay_seconds=delay)
    result.metadata.update(dataset_id=data.observation.id, height_pair={
        key: value for key, value in data.analysis_config['data'].items()
        if key in {'h1', 'h2', 'resolved_h1_index', 'resolved_h2_index', 'resolved_h1_km', 'resolved_h2_km', 'observable'}},
        lower_index=order.get('lower_index', 0), higher_index=order.get('higher_index', 1),
        input_provenance=data.metadata.get('analysis_input'),
        baseline='selected original/post-magnetogram cubes before current Gaussian')
    if data_key(data) != key:
        raise ValueError('Dopplergram inputs changed during coherence calculation.')
    return result
