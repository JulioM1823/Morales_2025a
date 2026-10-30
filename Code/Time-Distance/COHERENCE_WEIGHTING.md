# Measured coherence in the dispersion tools

`spectral_coherence.py` provides the shared estimator and grid alignment.
`coherence_bokeh.py` provides session-local controls, asynchronous calculation,
bounded caching and phase-preserving model visibility. The integrated workspace
and directly served legacy model app both use these components. The normal
`serve_komega_tools.py` routes already resolve to the integrated workspace.

## Estimator and coordinates

The estimator uses the selected pair's original/post-magnetogram Dopplergrams
before the current Gaussian filter. Height ordering, observable selection,
source reads and native cadence/pixel scale come from the existing
`ObservationData`, Dopplergram baseline loader and `TimeDistance` machinery.
It does not infer a velocity spectrum from an exported phase-only diagram.

Preprocessing follows the phase pipeline: full-record three-dimensional FFT,
global mean removal, rectangular window and `F_lower * conj(F_higher)` cross
sign. Unlike the separate historical Oana coherence product, this estimator
does not take a running difference or shorten the record. The historical
pipeline product is unchanged. Observational line-sampling delay is corrected
with the native sign at each exact Fourier frequency before frequency pooling;
simulation delay is zero.

Both auto-periodogram densities and the complex cross-periodogram density are
computed first. The existing radial lookup and positive-frequency averaging
helpers pool them over physical horizontal-wavenumber annuli. An equal-weight
five-bin frequency boxcar pools annular **sums**, using the same coefficient
counts for all three spectra. Only then is `abs(S12)**2 / (S11*S22)` formed.
Thus the calculation does not return the trivial per-coefficient ratio of one.
Periodograms use independently normalized velocity amplitudes to avoid numerical
under/overflow; those normalizations cancel in coherence and are recorded.

Annular width is the coarser horizontal FFT spacing. Rectangular fields and odd
sample counts are supported. `kh` is angular wavenumber in rad/Mm (the existing
plots label it Mm⁻¹); `nu` is cyclic frequency in mHz, and
`omega = 2*pi*nu/1000` rad/s. Actual `fftfreq` coordinates are used. The legacy
phase plots use endpoint `linspace` labels instead, which are not exact FFT
frequencies; those existing plots and scientific outputs were left unchanged.
Coherence is interpolated in physical coordinates onto each model's `[nu,kh]`
grid. Values outside measured support or requiring undefined neighbors remain
undefined, with zero model visibility. No extrapolation is performed.

At least five pooled coefficients and power above `1e-12` of each averaged
auto-spectrum's peak are required. Zero-power/unsupported bins are NaN;
finite coherence is clipped to [0,1]. A spatial time series missing any sample
at either height is omitted at both heights with a common spatial mask. The
retained fraction is recorded. These coefficient counts are not a claim of
independent statistical degrees of freedom: the estimator assumes annular
stationarity and locally smooth spectra, and the frequency boxcar limits
spectral resolution.

## Bokeh behavior

- **Apply Coherence Weighting** defaults off.
- **View Measured Coherence** displays an independent map with fixed [0,1]
  color limits, linked axes and native styling.
- **Minimum coherence C_min** has the existing exact numerical entry beside
  its slider, hard bounds [0,1], and default zero.
- All seven model tabs share one estimate: 3D MAG, Alfvén, slow, fast,
  Bunte 1993, MT1982 and MT1981. Every solution and all displayed fields retain
  the native solver and warning masks.

The current model outputs are signed phase and vertical wavenumber, not spectral
intensity. The existing Gaussian postprocessing defines the same baseline
display in both coherence states. The display now uses a **binary threshold
mask**: finite `C >= C_min` retains the exact baseline colors at full opacity;
bins below the threshold and undefined coherence bins are invisible. This avoids
the gray appearance produced by fading dark colors over a white background.
At the default zero threshold, supported C=0 bins are included. The combined numerical
spectral weighting is `Gaussian_amplitude * C * H(C-C_min)` (Gaussian omitted
in the legacy tool when its Apply Filter switch is off). This preserves the
existing Gaussian behavior without treating a signed phase as a power spectrum.
Surviving cells reproduce the disabled display byte for byte. Continuous
spectral weights remain available separately in hover/export data. Native scalar hover values retain the
existing Gaussian postprocessing; the underlying physical solver arrays remain
unchanged.

One persistent colored RGBA glyph renders each branch in both states, below the
unchanged reference curves. Each update replaces its complete, owned, contiguous
pixel array and geometry together. The native scalar source remains available
for hover/export but its image glyph is hidden. Native clears/failures hide
RGBA pixels explicitly. Image extents use half-cell edges around actual solver
sample centers, matching interpolation, scalar hover data and raster pixels.
The existing palette and color limits are retained. Disabling coherence restores
the previous Gaussian baseline immediately, without an FFT or root solve.
Observed/simulated data panels retain their native cube-filter/recalculation
behavior. Coherence weighting is a model display operation.

Calculations run off the Bokeh IOLoop. One worker limits peak FFT memory;
large spectra are reduced immediately and only small 2-D products are cached.
Up to four pair estimates and per-model-grid interpolations are retained per
session. Threshold, display-field, Gaussian, model and toggle edits reuse those
arrays. Dataset, height/observable, native sampling, preprocessing or source
version changes invalidate the current association. Generation checks reject
stale asynchronous completions, and session destruction releases caches.
Source changes require reloading the dataset rather than weighting stale cubes.

Plot exports retain the physical arrays, RGBA visibility and estimator,
height-pair, sampling, threshold and alignment metadata. An unavailable/pending
coherence estimate cannot be exported as a completed weighted model.

## Validation

`Code/Tests/test_spectral_coherence.py` checks the estimator against independently
pooled Fourier coefficients, synthetic coherent waves and independent noise;
odd/even rectangular grids; exact units; missing/zero/tiny power; delay correction;
interpolation boundaries; repeatability; source changes; cache reuse; stale
workers; all models/fields; exact numerical controls; backward compatibility;
and exported opacity/provenance. Existing explorer, observation, integration
and dispersion-consistency regression suites are also exercised.

The original estimator/integration validation passed 130 tests. The subsequent
rendering and performance audit adds independent pixel-bin/orientation checks,
unity/zero/half-coherence identities, analytic grid alignment for every model,
stable glyph/layout reuse, stale second-stage callback rejection, cached/fresh
solver equality and latest saved megaplot context validation. See
`COHERENCE_RENDERING_AUDIT.md` for the current combined test run and timings.

For the fixed synthetic cases, coherence at injected wave components is
0.99986956 (128×32×40 samples, 30 s, 0.16 Mm) and 0.99988762
(129×33×41 samples, 11.88 s, 0.43 Mm). Independent noise has mean coherence
0.00415965, 99th percentile 0.03107009 and maximum 0.06153734 in the tested
interior region. All finite estimates lie within [0,1], and repeated estimates
are array-identical. Numerical tests use actual FITS-pair and NetCDF-height-pair
loaders; these are controlled synthetic data, not an empirical accuracy audit
of every production dataset.

Browser verification on a temporary local Bokeh server confirmed the independent
coherence image, fixed [0,1] color bar, committed 0.4 numerical threshold,
filtered model visibility, and retained controls when switching model tabs.
The server used controlled source-backed FITS/NetCDF fixtures under `/tmp`.

Definition reference: [SciPy coherence documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.coherence.html).
The estimator here uses annular/frequency pooling rather than Welch segments.

## Switching and cache behavior

Model selection reuses persistent curve renderers, model control layouts and
already-rendered filtered results. A display cache key includes the physical
result, field/masks, selected data/filter, Gaussian inputs, coherence estimate
and threshold. Bokeh model-graph changes are batched, while native Python
callbacks retain synchronous ordering. Generation/state checks reject queued
root callbacks superseded by parameter edits or switching away and back. Native
physical solver and branch-order caches are unchanged; no resolution,
convergence criterion or physical approximation was altered.
Responsive browser grid/size updates use `setv(..., {sync: false})`, preventing
an older presentation update from overwriting a newer server-side model
selection. The executable layout regression fails against the pre-fix callback
and passes with the correction across narrow and wide layouts.
