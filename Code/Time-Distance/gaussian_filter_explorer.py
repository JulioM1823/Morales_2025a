'''
Purpose
-------
Construct native Gaussian komega filter previews and debounced exact Python products on
physical Fourier grids.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for gaussian_filter_explorer.py.

Notes
-----
Interactive Bokeh explorer for the Morales_2025a Gaussian k-omega filter.
'''

from __future__ import annotations

# Import the libraries and shared helpers used by this module
import importlib.util
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from bokeh.document import Document
from bokeh.events import DocumentReady
from bokeh.layouts import column, row
from bokeh.models import (
    BasicTicker,
    ColorBar,
    ColumnDataSource,
    CustomJS,
    Div,
    HoverTool,
    Label,
    LinearColorMapper,
    Range1d,
    Slider,
)
from bokeh.palettes import Viridis256
from bokeh.plotting import figure


MODULE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = MODULE_DIR / "config.py"
PARAMETER_KEYS = ("central_k", "width_k", "central_f", "width_f")

# These are the dimensions and sampling of the default simulation selected by
# config.py. They keep the explorer usable when the optional NetCDF dependency
# or the configured data file is unavailable.
FALLBACK_NX = 240
FALLBACK_NT = 481
FALLBACK_DT_SECONDS = 30.0
FALLBACK_DX_MM = 0.16

# Fixed quantities in spectral_analysis.create_filter/filter.create_filter.
FILTER_SOUND_SPEED_KM_S = 7.0
FILTER_GRAVITY_KM_S2 = 0.274
FILTER_FREQUENCY_CAP_MHZ = 5.0


def _bartlett_window(length: int) -> np.ndarray:
    '''
    Purpose
    -------
    Construct the default symmetric Bartlett window without importing SciPy.

    Inputs
    ------
    length: int
        Number of window samples, converted to an integer.

    Outputs
    -------
    window: np.ndarray
        Float64 window; empty for length below one and unity for length one.

    Notes
    -----
    Return SciPy's default symmetric Bartlett window without importing SciPy.
    '''
    # Construct the default symmetric Bartlett window without importing SciPy
    length = int(length)
    if length < 1:
        return np.empty(0, dtype=np.float64)
    if length == 1:
        return np.ones(1, dtype=np.float64)

    samples = np.arange(length, dtype=np.float64)
    midpoint = (length - 1.0) / 2.0
    return 1.0 - np.abs((samples - midpoint) / midpoint)


def _gaussian_window(length: int, standard_deviation: float) -> np.ndarray:
    '''
    Purpose
    -------
    Construct the default symmetric Gaussian window without importing SciPy.

    Inputs
    ------
    length: int
        Number of window samples.
    standard_deviation: float
        Positive finite Gaussian standard deviation in sample-index units.

    Outputs
    -------
    window: np.ndarray
        Unnormalized float64 symmetric samples; empty for length below one. Invalid
        standard deviation raises ValueError for nonempty windows.

    Notes
    -----
    Return SciPy's default symmetric Gaussian window without importing SciPy.
    '''
    # Construct the default symmetric Gaussian window without importing SciPy
    length = int(length)
    standard_deviation = float(standard_deviation)
    if length < 1:
        return np.empty(0, dtype=np.float64)
    if not np.isfinite(standard_deviation) or standard_deviation <= 0.0:
        raise ValueError("Gaussian-window standard deviation must be positive and finite")

    samples = np.arange(length, dtype=np.float64) - (length - 1.0) / 2.0
    return np.exp(-0.5 * (samples / standard_deviation) ** 2)


@dataclass(frozen=True)
class PreviewGeometry:
    '''
    Purpose
    -------
    Describe the original Fourier-grid sampling needed by a filter preview.

    Inputs
    ------
    nx: int
        Original x sample count.
    nt: int
        Original temporal sample count.
    dt_seconds: float
        Temporal cadence in seconds.
    dx_Mm: float
        Spatial x pixel spacing in Mm.
    description: str
        Human-readable source or fallback-grid explanation.

    Outputs
    -------
    geometry: PreviewGeometry
        Frozen hashable geometry used in native filter-result cache keys.

    Notes
    -----
    Fourier-grid geometry needed to display the filter response.
    '''

    nx: int
    nt: int
    dt_seconds: float
    dx_Mm: float
    description: str


@dataclass(frozen=True)
class FilterResult:
    '''
    Purpose
    -------
    Hold a read-only positive-frequency filter image and its physical axes.

    Inputs
    ------
    kh: np.ndarray
        Nonnegative horizontal-wavenumber coordinates in Mm^-1.
    nu: np.ndarray
        Nonnegative cyclic-frequency coordinates in mHz.
    transmission: np.ndarray
        Dimensionless transfer image with shape (n_nu, n_kh).

    Outputs
    -------
    result: FilterResult
        Frozen result container whose numerical arrays are marked read-only by
        compute_filter_result.

    Notes
    -----
    Positive-frequency filter image plus its coordinate axes.
    '''

    kh: np.ndarray
    nu: np.ndarray
    transmission: np.ndarray


def _load_config(config_file: Path = CONFIG_FILE) -> dict[str, Any]:
    '''
    Purpose
    -------
    Execute the requested configuration module and return its exported runtime
    dictionary.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    config: dict
        Module.config without modifying it here; unavailable import specifications or
        module errors propagate.

    Notes
    -----
    Load the exported runtime config without modifying it.
    '''

    # Execute the requested configuration module and return its exported runtime
    # dictionary
    config_file = Path(config_file).expanduser().resolve()
    spec = importlib.util.spec_from_file_location(
        f"morales_2025a_filter_config_{id(config_file)}", config_file
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load configuration file: {config_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.config


def load_gaussian_defaults(config_file: Path = CONFIG_FILE) -> dict[str, float]:
    '''
    Purpose
    -------
    Read and validate the four configured Gaussian shape defaults.

    Inputs
    ------
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    defaults: dict
        Finite central_k/width_k in Mm^-1 and central_f/width_f in mHz, with positive
        FWHM widths. Missing keys or invalid domains raise errors.

    Notes
    -----
    Read the four Gaussian shape parameters directly from config.py.
    '''

    # Read and validate the four configured Gaussian shape defaults
    config = _load_config(config_file)
    gaussian_config = config.get("filtering", {}).get("gaussian", {})
    missing = [key for key in PARAMETER_KEYS if key not in gaussian_config]
    if missing:
        raise KeyError(
            "The Gaussian filter configuration is missing: " + ", ".join(missing)
        )

    defaults = {key: float(gaussian_config[key]) for key in PARAMETER_KEYS}
    if not all(np.isfinite(value) for value in defaults.values()):
        raise ValueError("All Gaussian filter parameters must be finite.")
    if defaults["central_k"] < 0.0 or defaults["central_f"] < 0.0:
        raise ValueError("Gaussian central k and frequency must be non-negative.")
    if defaults["width_k"] <= 0.0 or defaults["width_f"] <= 0.0:
        raise ValueError("Gaussian filter widths must be positive.")
    return defaults


def _coordinate_step(values: np.ndarray, units: str, *, is_time: bool) -> float:
    '''
    Purpose
    -------
    Convert the median absolute finite coordinate increment into seconds or Mm.

    Inputs
    ------
    values: np.ndarray
        Native coordinate samples used to estimate the median increment.
    units: str
        Declared time/length units; empty labels use the existing native fallback
        convention.
    is_time: bool
        True converts time to seconds; False converts length to Mm.

    Outputs
    -------
    step: float
        Converted native step; fewer than two finite samples or unsupported unit labels
        raise ValueError.

    Notes
    -----
    Convert a uniform NetCDF coordinate step to seconds or Mm.
    '''

    # Convert the median absolute finite coordinate increment into seconds or Mm
    values = np.asarray(values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        raise ValueError("A coordinate must contain at least two finite samples.")
    step = float(np.median(np.abs(np.diff(finite))))
    unit = str(units or "").strip().lower()
    if is_time:
        factors = {
            "": 1.0,
            "s": 1.0,
            "sec": 1.0,
            "seconds": 1.0,
            "ms": 1.0e-3,
            "min": 60.0,
            "minutes": 60.0,
        }
    else:
        factors = {"": 1.0, "mm": 1.0, "cm": 1.0e-8, "m": 1.0e-6, "km": 1.0e-3}
    if unit not in factors:
        raise ValueError(f"Unsupported coordinate unit: {units!r}")
    return step * factors[unit]


def resolve_preview_geometry(config: dict[str, Any]) -> PreviewGeometry:
    '''
    Purpose
    -------
    Infer configured simulation sampling from metadata or use the disclosed default
    preview grid.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    geometry: PreviewGeometry
        Cube sample counts/cadence/pixel scale when readable, otherwise the module
        fallback values; scalar field values are not loaded.

    Notes
    -----
    Infer the configured cube geometry without loading its data values.
    '''

    # Infer configured simulation sampling from metadata or use the disclosed default
    # preview grid
    data = config.get("data", {})
    if data.get("source_type") == "single_cube":
        settings = data.get("single_cube", {})
        cube_file = Path(str(settings.get("file", ""))).expanduser()
        observable = str(settings.get("observable", ""))
        # Read configured NetCDF dimensions and physical coordinate increments without
        # loading the field
        try:
            import netCDF4 as nc  # type: ignore

            if cube_file.is_file():
                with nc.Dataset(cube_file) as dataset:
                    variable = dataset.variables[observable]
                    dimensions = dict(zip(variable.dimensions, variable.shape))
                    nt = int(dimensions.get("time", dimensions.get("t", variable.shape[0])))
                    nx = int(dimensions.get("xc1", variable.shape[-1]))
                    time_name = "time" if "time" in dataset.variables else "t"
                    time_variable = dataset.variables[time_name]
                    dt_seconds = _coordinate_step(
                        time_variable[:], getattr(time_variable, "units", ""), is_time=True
                    )
                    spatial_name = next(
                        name for name in ("xc1", "xb1", "xc2", "xb2") if name in dataset.variables
                    )
                    spatial_variable = dataset.variables[spatial_name]
                    dx_Mm = _coordinate_step(
                        spatial_variable[:], getattr(spatial_variable, "units", ""), is_time=False
                    )
                # Use the matched source geometry when metadata resolution succeeds
                return PreviewGeometry(
                    nx=nx,
                    nt=nt,
                    dt_seconds=dt_seconds,
                    dx_Mm=dx_Mm,
                    description=f"{cube_file.name}: {nx} spatial × {nt} temporal samples",
                )
        except (ImportError, KeyError, OSError, StopIteration, ValueError):
            pass

    return PreviewGeometry(
        nx=FALLBACK_NX,
        nt=FALLBACK_NT,
        dt_seconds=FALLBACK_DT_SECONDS,
        dx_Mm=FALLBACK_DX_MM,
        description=(
            f"default pipeline grid: {FALLBACK_NX} spatial × {FALLBACK_NT} temporal samples"
        ),
    )


def build_filter_axes(geometry: PreviewGeometry) -> tuple[np.ndarray, np.ndarray]:
    '''
    Purpose
    -------
    Reproduce the native signed Fourier-label axes with original sample-count parity.

    Inputs
    ------
    geometry: PreviewGeometry
        Original nx/nt sample counts, cadence in seconds, and spatial pixel scale in Mm.

    Outputs
    -------
    kh, frequency: tuple of np.ndarray
        Nonnegative horizontal wavenumbers in Mm^-1 and complete signed cyclic
        frequencies in mHz. Invalid sample counts or nonpositive sampling raise
        ValueError.

    Notes
    -----
    Reproduce the signed Fourier axes used by make_fourier_grid.
    '''

    # Reproduce the native signed Fourier-label axes with original sample-count parity
    if geometry.nx < 2 or geometry.nt < 3:
        raise ValueError("The preview grid is too small to define a k-omega filter.")
    if geometry.dt_seconds <= 0.0 or geometry.dx_Mm <= 0.0:
        raise ValueError("Cadence and spatial sampling must be positive.")

    k_nyquist = np.pi / float(geometry.dx_Mm)
    nu_nyquist = 500.0 / float(geometry.dt_seconds)
    full_k = np.linspace(
        -k_nyquist,
        k_nyquist,
        int(geometry.nx),
        endpoint=bool(geometry.nx % 2),
        dtype=np.float64,
    )
    full_nu = np.linspace(
        -nu_nyquist,
        nu_nyquist,
        int(geometry.nt),
        endpoint=bool(geometry.nt % 2),
        dtype=np.float64,
    )
    return full_k[full_k >= 0.0], full_nu


def _validate_parameters(
    central_k: float, width_k: float, central_f: float, width_f: float
) -> tuple[float, float, float, float]:
    '''
    Purpose
    -------
    Normalize the four Gaussian shape inputs and enforce their finite physical domains.

    Inputs
    ------
    central_k: float
        Nonnegative Gaussian horizontal-wavenumber center in Mm^-1.
    width_k: float
        Positive Gaussian horizontal-wavenumber full width at half maximum in Mm^-1.
    central_f: float
        Nonnegative Gaussian cyclic-frequency center in mHz.
    width_f: float
        Positive Gaussian cyclic-frequency full width at half maximum in mHz.

    Outputs
    -------
    values: tuple of float
        central_k, width_k, central_f, width_f in that order; invalid centers or widths
        raise ValueError.
    '''

    # Normalize the four Gaussian shape inputs and enforce their finite physical domains
    values = tuple(float(value) for value in (central_k, width_k, central_f, width_f))
    if not all(np.isfinite(value) for value in values):
        raise ValueError("All Gaussian filter parameters must be finite.")
    if values[0] < 0.0 or values[2] < 0.0:
        raise ValueError("Gaussian central k and frequency must be non-negative.")
    if values[1] <= 0.0 or values[3] <= 0.0:
        raise ValueError("Gaussian filter widths must be positive.")
    return values


@lru_cache(maxsize=8)
def _filter_grid(kh_values, frequency_values):
    '''
    Purpose
    -------
    Cache parameter-independent passband, low-frequency suppression, and
    conjugate-reflection indices.

    Inputs
    ------
    kh_values: tuple of float
        Hashable radial wavenumber samples in Mm^-1.
    frequency_values: tuple of float
        Hashable complete signed cyclic-frequency samples in mHz.

    Outputs
    -------
    passband, suppressor, reflected: tuple of np.ndarray
        Read-only (n_kh,n_frequency) passband, temporal suppressor, and integer
        reflection map.

    Notes
    -----
    Cache only the parameter-independent passband and FFT reflection map.
    '''
    # Cache parameter-independent passband, low-frequency suppression, and
    # conjugate-reflection indices
    kh_axis, frequency_axis = np.asarray(kh_values), np.asarray(frequency_values)
    nt = frequency_axis.size
    suppressor = 1.0 - _gaussian_window(nt, (nt - 1.0) / (2.0 * 150.0))
    passband = np.zeros((kh_axis.size, nt))
    for index, kh in enumerate(kh_axis):
        if kh < .1:
            continue
        limit = min(np.sqrt(FILTER_GRAVITY_KM_S2 * kh / 1000.) * 1000. / (2.*np.pi),
                    FILTER_SOUND_SPEED_KM_S * abs(kh) / (2.*np.pi), FILTER_FREQUENCY_CAP_MHZ)
        indices = np.flatnonzero((frequency_axis <= limit) & (frequency_axis >= -limit))
        if not indices.size:
            continue
        window = _bartlett_window(indices.size)
        peak = window.max()
        if peak:
            passband[index, indices] = (1. - np.cos(np.pi * (window / peak))) / 2.
    # Equivalent to fftshift(ifftshift(profile)[-arange(nt) % nt]).
    reflected = (2 * (nt // 2) - np.arange(nt)) % nt
    for array in (passband, suppressor, reflected):
        array.setflags(write=False)
    return passband, suppressor, reflected


def compute_gaussian_filter_slice(
    kh_axis: np.ndarray,
    frequency_axis: np.ndarray,
    *,
    central_k: float,
    width_k: float,
    central_f: float,
    width_f: float,
) -> np.ndarray:
    '''
    Purpose
    -------
    Evaluate the native Gaussian AGW transfer on its exact radial frequency slice.

    Inputs
    ------
    kh_axis: np.ndarray
        One-dimensional finite radial wavenumbers in Mm^-1.
    frequency_axis: np.ndarray
        One-dimensional finite signed cyclic frequencies in mHz.
    central_k: float
        Nonnegative Gaussian horizontal-wavenumber center in Mm^-1.
    width_k: float
        Positive Gaussian horizontal-wavenumber full width at half maximum in Mm^-1.
    central_f: float
        Nonnegative Gaussian cyclic-frequency center in mHz.
    width_f: float
        Positive Gaussian cyclic-frequency full width at half maximum in mHz.

    Outputs
    -------
    transmission: np.ndarray
        Dimensionless (n_kh,n_frequency) Hermitian-symmetrized transfer using FWHM/2.355
        widths and conditional peak normalization. Invalid axes/parameters or nonfinite
        output raise errors.

    Notes
    -----
    Evaluate the existing Gaussian AGW filter on its displayed radial slice.

    This is the same per-wavenumber calculation used by ``create_filter``:
    identical Gaussian FWHM conversion, low-frequency suppressor, Bartlett
    passband, f-mode/Lamb/5-mHz boundary, and conditional normalization.  It
    avoids allocating and filling the unused three-dimensional filter cube.
    '''

    # Evaluate the native Gaussian AGW transfer on its exact radial frequency slice
    central_k, width_k, central_f, width_f = _validate_parameters(
        central_k, width_k, central_f, width_f
    )
    kh_axis = np.asarray(kh_axis, dtype=np.float64)
    frequency_axis = np.asarray(frequency_axis, dtype=np.float64)
    if kh_axis.ndim != 1 or frequency_axis.ndim != 1:
        raise ValueError("k and frequency axes must be one-dimensional.")
    if not np.all(np.isfinite(kh_axis)) or not np.all(np.isfinite(frequency_axis)):
        raise ValueError("k and frequency axes must contain only finite values.")

    # Convert FWHM widths to standard deviations and reuse the parameter-independent
    # native passband
    nt = frequency_axis.size
    fsig = width_f / 2.355
    ksig = width_k / 2.355
    passband, low_frequency_suppressor, reflected = _filter_grid(
        tuple(kh_axis), tuple(frequency_axis))
    frequency_envelope = np.exp(
        -((frequency_axis - central_f) ** 2.0) / (2.0 * fsig**2.0)
    ) + np.exp(-((frequency_axis + central_f) ** 2.0) / (2.0 * fsig**2.0))
    radial_envelope = np.exp(-((kh_axis - central_k) ** 2.0) / (2.0 * ksig**2.0))
    # Combine radial/frequency Gaussian envelopes with the native low-frequency
    # suppression
    result = passband * (low_frequency_suppressor[None, :] * frequency_envelope[None, :]
                         * radial_envelope[:, None])
    # Normalize only profiles exceeding unity and enforce the conjugate-index symmetry
    if nt:
        peak = result.max(axis=1)
        np.divide(result, peak[:, None], out=result, where=peak[:, None] > 1.)
    result = .5 * (result + result[:, reflected])

    if not np.all(np.isfinite(result)):
        raise FloatingPointError("The Gaussian filter produced NaN or infinite values.")
    return result


def compute_diagram_filter(kh, nu, geometry: PreviewGeometry, **parameters) -> np.ndarray:
    '''
    Purpose
    -------
    Construct the native Gaussian transfer directly on diagram coordinates in image
    order.

    Inputs
    ------
    kh: array-like
        One-dimensional horizontal-wavenumber coordinates in Mm^-1.
    nu: array-like
        One-dimensional cyclic-frequency coordinates in mHz.
    geometry: PreviewGeometry
        Original nx/nt sample counts, cadence in seconds, and spatial pixel scale in Mm.
    parameters: dict
        Keyword Gaussian central_k/width_k (Mm^-1) and central_f/width_f (mHz), with
        FWHM widths.

    Outputs
    -------
    transmission: np.ndarray
        Dimensionless (n_nu,n_kh) image, reconstructing the negative-frequency half with
        original nt parity when required. Frequencies must increase with at least two
        samples.

    Notes
    -----
    Construct the Gaussian on the diagram's coordinates, in image order.

    Rebuild the negative-frequency half needed by the existing symmetric
    Bartlett/Gaussian construction. No interpolation of a preview image is
    involved; the returned [frequency, k] array matches the diagram exactly.
    '''
    # Construct the native Gaussian transfer directly on diagram coordinates in image
    # order
    kh, nu = np.asarray(kh, dtype=float), np.asarray(nu, dtype=float)
    if nu.ndim != 1 or nu.size < 2 or np.any(np.diff(nu) <= 0):
        raise ValueError("Diagram frequencies must be increasing with at least two samples.")
    if nu[0] < 0:
        return compute_gaussian_filter_slice(kh, nu, **parameters).T
    if nu[0] == 0:
        negative = (-nu[:0:-1] if geometry.nt % 2
                    else -(nu + (nu[1] - nu[0]))[::-1])
    else:
        negative = -nu[::-1]
    frequencies = np.concatenate((negative, nu))
    return compute_gaussian_filter_slice(kh, frequencies, **parameters)[:, negative.size:].T


@lru_cache(maxsize=64)
def compute_filter_result(
    geometry: PreviewGeometry,
    central_k: float,
    width_k: float,
    central_f: float,
    width_f: float,
) -> FilterResult:
    '''
    Purpose
    -------
    Calculate and cache the read-only nonnegative-frequency filter image.

    Inputs
    ------
    geometry: PreviewGeometry
        Original nx/nt sample counts, cadence in seconds, and spatial pixel scale in Mm.
    central_k: float
        Nonnegative Gaussian horizontal-wavenumber center in Mm^-1.
    width_k: float
        Positive Gaussian horizontal-wavenumber full width at half maximum in Mm^-1.
    central_f: float
        Nonnegative Gaussian cyclic-frequency center in mHz.
    width_f: float
        Positive Gaussian cyclic-frequency full width at half maximum in mHz.

    Outputs
    -------
    result: FilterResult
        Physical axes and (n_nu,n_kh) transfer image; the shared LRU cache retains up to
        64 exact geometry/parameter combinations.

    Notes
    -----
    Compute and cache the positive-frequency image shown by the app.
    '''

    # Calculate and cache the read-only nonnegative-frequency filter image
    kh_axis, frequency_axis = build_filter_axes(geometry)
    full_slice = compute_gaussian_filter_slice(
        kh_axis,
        frequency_axis,
        central_k=central_k,
        width_k=width_k,
        central_f=central_f,
        width_f=width_f,
    )
    positive_frequency = frequency_axis >= 0.0
    nu_axis = frequency_axis[positive_frequency]
    transmission = full_slice[:, positive_frequency].T
    kh_axis.setflags(write=False)
    nu_axis.setflags(write=False)
    transmission.setflags(write=False)
    return FilterResult(kh=kh_axis, nu=nu_axis, transmission=transmission)


def axis_limits(axis: np.ndarray) -> tuple[float, float]:
    '''
    Purpose
    -------
    Expand sampled coordinate centers to their outer image-cell edges.

    Inputs
    ------
    axis: np.ndarray
        Coordinate centers in consistent physical units.

    Outputs
    -------
    low, high: tuple of float
        First/last centers extended by half the median increment; a singleton uses unit
        spacing and an empty axis raises ValueError.

    Notes
    -----
    Return the outer pixel-edge limits used by the plotting notebook.
    '''

    # Expand sampled coordinate centers to their outer image-cell edges
    axis = np.asarray(axis, dtype=np.float64)
    if axis.size == 0:
        raise ValueError("Cannot determine plot limits for an empty axis.")
    step = float(np.median(np.diff(axis))) if axis.size > 1 else 1.0
    return float(axis[0] - 0.5 * step), float(axis[-1] + 0.5 * step)


def filter_boundaries(kh_axis: np.ndarray) -> dict[str, np.ndarray]:
    '''
    Purpose
    -------
    Evaluate the native f-mode, Lamb, and fixed-cap frequencies used by the filter
    passband.

    Inputs
    ------
    kh_axis: np.ndarray
        Horizontal-wavenumber samples in Mm^-1.

    Outputs
    -------
    boundaries: dict of np.ndarray
        f_mode, lamb, and cap cyclic-frequency arrays in mHz.

    Notes
    -----
    Return the three boundaries used inside the Gaussian filter.
    '''

    # Evaluate the native f-mode, Lamb, and fixed-cap frequencies used by the filter
    # passband
    kh_axis = np.asarray(kh_axis, dtype=np.float64)
    return {
        "f_mode": np.sqrt(FILTER_GRAVITY_KM_S2 * kh_axis / 1000.0)
        * 1000.0
        / (2.0 * np.pi),
        "lamb": FILTER_SOUND_SPEED_KM_S * kh_axis / (2.0 * np.pi),
        "cap": np.full(kh_axis.shape, FILTER_FREQUENCY_CAP_MHZ),
    }


class GaussianFilterExplorer:
    '''
    Purpose
    -------
    Coordinate continuous browser filter previews and debounced exact Python results.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    schedule_initial: bool
        Schedule the initial calculation after document construction when True.

    Outputs
    -------
    explorer: GaussianFilterExplorer
        Document-root layout, parameter controls, physical grid, and filter sources
        initialized from the requested configuration.

    Notes
    -----
    Continuous browser preview with debounced, exact Python products.
    '''

    def __init__(
        self,
        doc: Document,
        *,
        config_file: Path = CONFIG_FILE,
        schedule_initial: bool = True,
    ) -> None:
        '''
        Purpose
        -------
        Build the native filter controls, plot, local-preview bridge, and initial
        document state.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        config_file: str or pathlib.Path
            Configuration-module path used to reconstruct the runtime settings.
        schedule_initial: bool
            Schedule the initial calculation after document construction when True.

        Outputs
        -------
        None
            Loads configuration/defaults, resolves sampling, adds the layout to doc, and
            optionally schedules the exact initial Python calculation.
        '''

        # Build the native filter controls, plot, local-preview bridge, and initial
        # document state
        self.doc = doc
        self.config_file = Path(config_file).expanduser().resolve()
        self.config = _load_config(self.config_file)
        self.defaults = load_gaussian_defaults(self.config_file)
        self.geometry = resolve_preview_geometry(self.config)
        self._scheduled_callback: Any = None
        self._suppress_callbacks = False
        self._preview_geometry = None

        # Create persistent filter, hover, color, and error sources before assembling
        # controls
        self.image_source = ColumnDataSource(
            data={"image": [np.full((2, 2), np.nan)], "x": [0.0], "y": [0.0], "dw": [1.0], "dh": [1.0]},
            name="gaussian_filter:image_source",
        )
        self.hover_source = ColumnDataSource(
            data={"kh": [], "nu": [], "transmission": []},
            name="gaussian_filter:hover_source",
        )
        self.mapper = LinearColorMapper(
            palette=Viridis256, low=0.0, high=1.0, nan_color="#ffffff"
        )
        self.status = Div(
            text="Waiting for the initial filter calculation…",
            width=330,
            name="gaussian_filter:status",
        )
        self.error_label = Label(
            x=3.5,
            y=5.0,
            text="",
            text_align="center",
            text_font_size="14pt",
            text_color="#991b1b",
            background_fill_color="#ffffff",
            background_fill_alpha=0.92,
            visible=False,
        )
        # Build the exact controls and attach the existing local preview before
        # composing the document root
        self.numeric_controls = {}
        self.sliders = self._build_sliders()
        self.plot = self._build_plot()
        self._install_live_preview()
        self.layout = self._build_layout()
        self.doc.add_root(self.layout)
        self.doc.title = "Morales 2025a Gaussian k–ω Filter Explorer"

        if schedule_initial:
            self.doc.add_next_tick_callback(self._perform_recompute)

    def _build_sliders(self) -> dict[str, Slider]:
        '''
        Purpose
        -------
        Construct exact-value Gaussian controls from validated native defaults.

        Inputs
        ------
        None

        Outputs
        -------
        sliders: dict of bokeh.models.Slider
            Four parameter-key sliders with ExactSlider wrappers stored separately and
            change callbacks registered.
        '''

        # Construct exact-value Gaussian controls from validated native defaults
        slider_specs = {
            "central_k": ("Central horizontal wavenumber k₀ [Mm⁻¹]", 0.0, 7.0, 0.05),
            "width_k": ("Horizontal-wavenumber FWHM Δk [Mm⁻¹]", 0.1, 10.0, 0.05),
            "central_f": ("Central frequency ν₀ [mHz]", 0.0, 10.0, 0.05),
            "width_f": ("Frequency FWHM Δν [mHz]", 0.1, 12.0, 0.05),
        }
        sliders: dict[str, Slider] = {}
        for key, (title, start, end, step) in slider_specs.items():
            default = self.defaults[key]
            slider = Slider(
                title=title,
                start=min(start, default),
                end=max(end, default),
                value=default,
                step=step,
                width=320,
                name=f"gaussian_filter:slider:{key}",
            )
            from vesa_support import support_module
            self.numeric_controls[key] = support_module('numeric_controls').ExactSlider(slider, key)
            slider.width = 215
            slider.on_change("value", self._on_slider_change)
            sliders[key] = slider
        return sliders

    def _build_plot(self):
        '''
        Purpose
        -------
        Build the native filter image, physical references, hover overlay, and color
        bar.

        Inputs
        ------
        None

        Outputs
        -------
        plot: bokeh.models.Plot
            Retained filter plot with native styling and error label; source arrays are
            populated by preview/recompute updates.
        '''

        # Build the native filter image, physical references, hover overlay, and color
        # bar
        plot = figure(
            title="Gaussian Filter k–ω Diagram",
            width=760,
            height=980,
            x_range=Range1d(0.0, 7.0),
            y_range=Range1d(0.0, 10.0),
            x_axis_label="kₕ [Mm⁻¹]",
            y_axis_label="ν / 2π [mHz]",
            tools="pan,wheel_zoom,box_zoom,reset,save",
            active_scroll=None,
            toolbar_location="above",
            name="gaussian_filter:plot",
        )
        plot.grid.visible = False
        plot.background_fill_color = "white"
        plot.border_fill_color = "white"
        plot.outline_line_color = "black"
        plot.title.text_font = "Times New Roman"
        plot.title.text_font_size = "20pt"
        plot.title.text_font_style = "normal"
        for axis in (plot.xaxis[0], plot.yaxis[0]):
            axis.axis_label_text_font = "Times New Roman"
            axis.axis_label_text_font_size = "20pt"
            axis.axis_label_text_font_style = "normal"
            axis.major_label_text_font = "Times New Roman"
            axis.major_label_text_font_size = "18pt"
            axis.major_tick_in = 8
            axis.major_tick_out = 0
            axis.minor_tick_in = 4
            axis.minor_tick_out = 0

        # Draw the native transfer image and add invisible cells for exact numerical
        # hover values
        plot.image(
            image="image",
            x="x",
            y="y",
            dw="dw",
            dh="dh",
            source=self.image_source,
            color_mapper=self.mapper,
            level="image",
        )
        hover_renderer = plot.rect(
            x="kh",
            y="nu",
            width=0.17,
            height=0.07,
            source=self.hover_source,
            fill_alpha=0.0,
            line_alpha=0.0,
        )
        plot.add_tools(
            HoverTool(
                renderers=[hover_renderer],
                tooltips=[
                    ("kₕ", "@kh{0.000} Mm⁻¹"),
                    ("ν / 2π", "@nu{0.000} mHz"),
                    ("Transmission", "@transmission{0.0000}"),
                ],
                point_policy="follow_mouse",
            )
        )

        # Overlay the same f-mode, Lamb, and frequency-cap references used by the filter
        kh_axis, _ = build_filter_axes(self.geometry)
        boundaries = filter_boundaries(kh_axis)
        plot.line(kh_axis, boundaries["f_mode"], color="#8c8c8c", line_width=4)
        plot.line(kh_axis, boundaries["lamb"], color="black", line_width=3, line_dash="dashed")
        plot.line(kh_axis, boundaries["cap"], color="black", line_width=2, line_dash="dotted")

        # Add native transmission scaling and a retained calculation-error annotation
        color_bar = ColorBar(
            color_mapper=self.mapper,
            ticker=BasicTicker(),
            title="Filter Transmission",
            title_text_font="Times New Roman",
            title_text_font_size="18pt",
            major_label_text_font="Times New Roman",
            major_label_text_font_size="16pt",
            width=24,
        )
        plot.add_layout(color_bar, "right")
        plot.add_layout(self.error_label)
        return plot

    def _build_layout(self):
        '''
        Purpose
        -------
        Compose parameter controls, status, and the native filter plot.

        Inputs
        ------
        None

        Outputs
        -------
        layout: bokeh.models.Column
            Standalone explorer layout using existing parameter wrappers and plot
            models.
        '''

        # Compose parameter controls, status, and the native filter plot
        controls = column(
            Div(text="<h2 style='margin:0'>Gaussian filter parameters</h2>", width=330),
            Div(
                text=(
                    "<p style='margin:4px 0 10px;color:#475569'>Defaults are read "
                    "from <code>filtering.gaussian</code> in <code>config.py</code>.</p>"
                ),
                width=330,
            ),
            *[self.numeric_controls[key].layout for key in PARAMETER_KEYS],
            self.status,
            Div(
                text=(
                    "<p style='color:#475569'>Scroll normally over the plot. Select "
                    "<b>Wheel Zoom</b> in the toolbar for in-plot wheel zoom.</p>"
                ),
                width=330,
            ),
            width=350,
            styles={"padding": "12px"},
        )
        return column(
            Div(
                text="<h1 style='margin:6px 0'>Morales 2025a Gaussian k–ω Filter Explorer</h1>",
                width=1120,
            ),
            row(controls, self.plot, sizing_mode="stretch_width"),
            sizing_mode="stretch_width",
        )

    def _on_slider_change(self, attr: str, old: float, new: float) -> None:
        '''
        Purpose
        -------
        Schedule exact Python products after an unsuppressed Gaussian parameter edit.

        Inputs
        ------
        attr: str
            Bokeh property name supplied by the change callback.
        old: object
            Previous property value supplied by Bokeh.
        new: object
            Updated property value supplied by Bokeh.

        Outputs
        -------
        None
            Uses the existing debounce request; browser preview updates are handled
            independently.
        '''

        # Schedule exact Python products after an unsuppressed Gaussian parameter edit
        if not self._suppress_callbacks:
            self.schedule_recompute()

    def _install_live_preview(self):
        '''
        Purpose
        -------
        Attach the existing local preview script while retaining Python ownership of
        scientific products.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Creates the parameter-independent preview-grid source, installs
            slider/document callbacks, and disables synchronization of browser-local
            image/hover display sources.

        Notes
        -----
        Continuous local preview; Python still owns all scientific products.
        '''
        # Attach the existing local preview script while retaining Python ownership of
        # scientific products
        self.preview_grid = ColumnDataSource(data=dict(kh=[], frequency=[], passband=[],
            suppressor=[], reflected=[], positive=[]), name='gaussian_filter:preview_grid')
        self.image_source.syncable = self.hover_source.syncable = self.mapper.syncable = False
        self.error_label.syncable = False
        callback = CustomJS(args=dict(grid=self.preview_grid, sliders=self.sliders,
            image=self.image_source, hover=self.hover_source, mapper=self.mapper,
            error=self.error_label), code=Path(__file__).with_name('gaussian_preview.js').read_text())
        self.preview_callback = callback
        for slider in self.sliders.values():
            slider.js_on_change('value', callback)
        self.preview_grid.js_on_change('data', callback)
        self.doc.js_on_event(DocumentReady, callback)

    def _sync_preview_grid(self):
        '''
        Purpose
        -------
        Publish a changed geometry's native axes, passband, suppressor, and reflection
        map.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Updates the local-preview grid only when its geometry changes.
        '''

        # Publish a changed geometry's native axes, passband, suppressor, and reflection
        # map
        if self._preview_geometry == self.geometry:
            return
        kh, frequency = build_filter_axes(self.geometry)
        passband, suppressor, reflected = _filter_grid(tuple(kh), tuple(frequency))
        self.preview_grid.data = dict(kh=[kh], frequency=[frequency], passband=[passband.ravel()],
            suppressor=[suppressor], reflected=[reflected], positive=[np.flatnonzero(frequency >= 0)])
        self._preview_geometry = self.geometry

    def schedule_recompute(self, delay_ms: int = 120) -> None:
        '''
        Purpose
        -------
        Replace a pending timeout with a debounced exact Python filter calculation.

        Inputs
        ------
        delay_ms: int
            Document timeout delay in milliseconds.

        Outputs
        -------
        None
            Does not delay continuous browser-local preview rendering.

        Notes
        -----
        Debounce derived Python products; the preview updates every frame.
        '''

        # Replace a pending timeout with a debounced exact Python filter calculation
        if self._scheduled_callback is not None:
            try:
                self.doc.remove_timeout_callback(self._scheduled_callback)
            except ValueError:
                pass
        self._scheduled_callback = self.doc.add_timeout_callback(
            self._perform_recompute, delay_ms
        )

    def _current_parameters(self) -> dict[str, float]:
        '''
        Purpose
        -------
        Read the accepted Gaussian values from all four native sliders.

        Inputs
        ------
        None

        Outputs
        -------
        parameters: dict of float
            Centers/FWHM widths in Mm^-1 and mHz.
        '''

        # Read the accepted Gaussian values from all four native sliders
        return {key: float(self.sliders[key].value) for key in PARAMETER_KEYS}

    def _clear_failed_result(self, message: str) -> None:
        '''
        Purpose
        -------
        Clear invalid filter preview/products and display the calculation failure.

        Inputs
        ------
        message: str
            Calculation failure text displayed by the existing error-label/status path.

        Outputs
        -------
        None
            Replaces sources with empty/NaN values, invalidates preview geometry, and
            shows error/status text.
        '''

        # Clear invalid filter preview/products and display the calculation failure
        self._preview_geometry = None
        self.preview_grid.data = dict(kh=[], frequency=[], passband=[], suppressor=[], reflected=[], positive=[])
        self.image_source.data = {
            "image": [np.full((2, 2), np.nan)],
            "x": [0.0],
            "y": [0.0],
            "dw": [7.0],
            "dh": [10.0],
        }
        self.hover_source.data = {"kh": [], "nu": [], "transmission": []}
        self.error_label.text = message
        self.error_label.visible = True
        self.status.text = f"<b>Calculation failed:</b> {message}"

    def _perform_recompute(self) -> None:
        '''
        Purpose
        -------
        Calculate exact cached filter products and update status or offline display
        sources.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Synchronizes preview geometry, validates finite output, and updates offline
            images/hover data without overwriting newer browser-local previews. Failures
            clear the result.
        '''

        # Calculate exact cached filter products and update status or offline display
        # sources
        self._scheduled_callback = None
        started = time.perf_counter()
        parameters = self._current_parameters()
        try:
            self._sync_preview_grid()
            result = compute_filter_result(
                self.geometry,
                parameters["central_k"],
                parameters["width_k"],
                parameters["central_f"],
                parameters["width_f"],
            )
            k_limits = axis_limits(result.kh)
            nu_limits = axis_limits(result.nu)
            image = np.asarray(result.transmission)
            finite = image[np.isfinite(image)]
            if finite.size == 0:
                raise FloatingPointError("No finite filter transmission values were produced.")
            # Live sessions render locally, so a late Python response cannot
            # replace a newer slider preview. Headless/export documents retain
            # the same native sources for numerical checks and saved figures.
            if self.doc.session_context is None:
                self.mapper.low = 0.0
                self.mapper.high = max(float(np.max(finite)), 1.0e-12)
                self.image_source.data = {
                    "image": [image],
                    "x": [k_limits[0]],
                    "y": [nu_limits[0]],
                    "dw": [k_limits[1] - k_limits[0]],
                    "dh": [nu_limits[1] - nu_limits[0]],
                }
                kh_mesh, nu_mesh = np.meshgrid(result.kh, result.nu)
                self.hover_source.data = {
                    "kh": kh_mesh.ravel(),
                    "nu": nu_mesh.ravel(),
                    "transmission": image.ravel(),
                }
            self.error_label.visible = False
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            cache_info = compute_filter_result.cache_info()
            self.status.text = (
                f"Updated in {elapsed_ms:.1f} ms; peak transmission "
                f"{float(np.max(finite)):.4f}. Grid: {self.geometry.description}. "
                f"Cache: {cache_info.hits} hit(s)."
            )
        except Exception as exc:  # keep one invalid choice from crashing the app
            self._clear_failed_result(str(exc))


def build_document(
    doc: Document,
    *,
    config_file: Path = CONFIG_FILE,
    schedule_initial: bool = True,
) -> GaussianFilterExplorer:
    '''
    Purpose
    -------
    Build the standalone native Gaussian-filter Bokeh document.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    schedule_initial: bool
        Schedule the initial calculation after document construction when True.

    Outputs
    -------
    explorer: GaussianFilterExplorer
        Created explorer with its layout attached to doc and optional initial
        calculation scheduled.

    Notes
    -----
    Build the standalone Bokeh-server document.
    '''

    # Build the standalone native Gaussian-filter Bokeh document
    return GaussianFilterExplorer(
        doc, config_file=config_file, schedule_initial=schedule_initial
    )


__all__ = [
    "CONFIG_FILE",
    "FILTER_FREQUENCY_CAP_MHZ",
    "FILTER_GRAVITY_KM_S2",
    "FILTER_SOUND_SPEED_KM_S",
    "FilterResult",
    "GaussianFilterExplorer",
    "PARAMETER_KEYS",
    "PreviewGeometry",
    "axis_limits",
    "build_document",
    "build_filter_axes",
    "compute_filter_result",
    "compute_gaussian_filter_slice",
    "filter_boundaries",
    "load_gaussian_defaults",
    "resolve_preview_geometry",
]
