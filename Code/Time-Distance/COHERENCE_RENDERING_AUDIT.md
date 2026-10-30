# Coherence rendering and switching audit — 2026-10-16

Display update, 2026-10-19: the user selected a binary coherence threshold mask.
Finite C >= C_min now retains the original colors at full opacity; other bins
are hidden. Continuous spectral weights remain separate. The relative-alpha
behavior described below records the earlier audit, not the current display.

## Scope and diagnosed causes

The audit inspected the attached phase-diagram screenshot, native Vesa Fourier/
dispersion/rendering code, Dopplergram loading, measured coherence, integrated
and legacy controllers, shared filters and generated megaplot launch contexts.
The estimator and physical solver were retained.

1. Coherence-on previously substituted Gaussian opacity for the existing Gaussian
   multiplication of displayed fields. Thus even C=1 changed the baseline colors.
   The baseline now stays identical in both states; coherence applies once as
   relative alpha. The full precision combined weight is T*C*H(C-C_min).
2. Rendering previously switched between scalar and RGBA glyphs, with independently
   updated sources/mappers and native clears. Every model branch now uses one
   persistent RGBA glyph in both states. A complete owned contiguous pixel buffer
   and its geometry replace the source together. Pending/failed solves explicitly
   clear visibility. Native scalar sources remain for hover and export.
3. Native image extents used the endpoint sample coordinates as image edges. Pixel
   centers therefore did not match solver/interpolation coordinates. Half-cell
   edges now register model pixels and scalar hover sources to the solver grid.
4. A native two-stage queued root callback had no generation/parameter ticket.
   A callback queued before switching away and back could still execute. The local
   controller rejects superseded generations/states while retaining native solves.
5. Profiling found repeated graph traversal and curve/layout reconstruction as the
   switching bottleneck. In the profiled pre-change run, 21 unweighted switches
   spent 34.0 of 38.6 s in 750 Bokeh graph recomputations. Persistent curve slots,
   per-model control layouts, complete display cache keys and graph batching remove
   this redundant work. Existing solver and branch-order caches are unchanged.
6. Responsive JavaScript previously synchronized display-only grid/size edits back
   to Python. A layout edit containing an older model could race a newer server
   selection. Those edits now use Bokeh setv with sync:false. An executable JS
   regression checks narrow/wide layouts, preserved selected model identity and
   zero outbound presentation writes. It fails against the captured pre-fix code
   and passes with the correction.

The screenshot alone does not identify its exact parameter/branch history.
Fresh default solver rasters did not reproduce its mixed horizontal color bands.
Real solutions can contain phase sign discontinuities and branch ambiguities;
these have not been smoothed away or removed to change their appearance.

## Estimator, alignment and scientific invariants

The selected original/post-magnetogram height-pair cubes feed the existing native
loader and time-distance preprocessing. A full-record rectangular 3D FFT follows
global mean removal and a common complete spatial time-series mask. Both auto
spectra and the complex lower-times-conjugate-higher cross spectrum are pooled
in horizontal-wavenumber annuli and five neighboring positive-frequency bins
**before** taking |S12|²/(S11*S22). Native line-sampling delay is corrected before
frequency pooling. The legacy historical coherence product is unchanged.

Coordinates use exact FFT angular kh in rad/Mm, cyclic nu in mHz and
omega=2*pi*nu/1000 in rad/s, with each dataset's native sampling. Physical
bilinear interpolation onto [nu,kh] model grids performs no extrapolation and
rejects undefined neighbors. Power floors, pooled coefficient counts, NaNs and
zero-power cases are tested; finite values are bounded [0,1]. Pooling coefficient
counts are not claimed to be independent statistical degrees of freedom.

These model diagrams are signed phase/wavenumber fields, not a modeled PSD.
Accordingly C changes relative visibility, preserving the phase color and all
physical roots. The pre-existing Gaussian displayed-field behavior remains the
baseline. C=1 is byte-identical to disabling coherence where supported; C=0 is
invisible. Full precision weights equal T*C*H numerically. RGB/alpha rasters use
8-bit display channels; physical arrays and weights retain floating precision.
The independent measured map retains fixed [0,1] limits and the threshold retains
both slider and exact numeric entry, default zero.

## Measured performance

Separate sequential processes used the same native 48 kh × 56 nu interactive
resolution, all seven models, identical immutable synthetic input and Gaussian
settings, and three complete cached cycles (21 switches) per coherence state.
Times measure the complete Python selection callback, excluding dataset I/O,
WebSocket transport and browser painting. cProfile was disabled for these timings.
No resolution, tolerances, polynomial equations or physical assumptions changed.

| Cached switch | Before median ms | After median ms | Before p95 ms | After p95 ms |
|---|---:|---:|---:|---:|
| unweighted | 920.18 | 26.41 | 1426.00 | 29.55 |
| weighted | 1019.84 | 28.63 | 1718.64 | 31.91 |

| First-use selection plus exact solve | Before ms | After ms |
|---|---:|---:|
| nc2009 | 1952.5 | 1909.8 |
| alfven_mode | 966.0 | 329.9 |
| slow_mode | 1703.7 | 1363.7 |
| fast_mode | 1798.9 | 1526.2 |
| bunte1993 | 1366.3 | 613.0 |
| mt1982 | 2682.7 | 1391.6 |
| mt1981 | 2674.7 | 1588.4 |

Cached Python switches improved about 35–36 times. First-use calculations still
require exact roots and branch tracking; the reduced display overhead brings
these totals to 0.33–1.91 s. Native solver timings remain comparable; no solver
algorithm speedup is claimed. Resolution and fidelity were unchanged.
`Code/Tests/benchmark_coherence_switching.py` reproduces the measurement;
`--baseline-dir` accepts a pre-change module snapshot and `--profile` exposes the
call profile. Raw measurements are in `COHERENCE_SWITCH_BENCHMARK.json`.

## Numerical and dataset validation

- All 21 full-resolution phase/Re(kz)/Im(kz) arrays, across all seven models, are
  array-identical to the captured pre-change implementation (including NaNs).
- Cached and fresh native solver arrays match. Repeated model/branch returns retain
  the same physical objects and identical raster buffers, without FFT/root calls.
- Independent Fourier pooling, correlated waves, independent noise, rectangular
  odd/even sampling, delay correction, low/missing power, repeatability and source
  version invalidation are tested. Synthetic wave coherence is approximately
  0.99987; independent-noise mean is 0.00416 and its 99th percentile is 0.03107.
- Analytic bilinear coherence is recovered on every model grid. Zero, half and
  unity coherence tests independently check RGB preservation, alpha and T*C.
- The newest saved megaplot context selects the exact dataset and retains current
  authoritative atmospheric parameter initialization. Its schema-1 atmosphere is
  upgraded by the existing profile machinery; legacy saved parameter values are
  not substituted for current verified profile inputs.
- Real source verification used `vx_100g_v3_880km_1100km_komega.fits`, native layers
  4 and 5 (880 and 1100 km), 481×240×240 samples, dt=30 s and dx=dy=0.16 Mm.
  Finite C ranged 0.0000017403–0.99473418, mean 0.18335729, with 99.986% supported
  bins. Pair loading took 10.26 s and first coherence calculation 3.04 s in that
  standalone audit. Model/threshold/toggle changes reuse the estimate.

## Regression and browser verification

Final combined test result: **210 passed, 1 skipped** in 211.35 s. Covered checks
are now located in these modules after source consolidation:
`test_spectral_coherence`, `test_coherence_switching`, `test_bokeh_responsiveness`,
`test_integrated_komega_explorer`, `test_komega_explorer`,
`test_komega_bokeh_integration`, `test_observation_komega_explorer`,
`test_dispersion_consistency`, `test_atmospheric_profiles`,
and `test_vesa_solver_numerics`. The responsive-layout checks are now in
`test_bokeh_responsiveness`; native-profile checks are now consolidated in
`test_atmospheric_profiles`.
The skipped test is the optional high-precision cross-check whose mpmath dependency is
unavailable. An initial run found an assertion that still compared the visible
frequency entry directly to native N2. Current local frequency controls use mHz;
that assertion now independently checks the conversion to signed angular N2 and
shared displayed values. The frequency-control implementation was not changed
by this correction. The final run also includes current dataset-matched grid
handling added elsewhere in the workspace during this audit. Coherence identity
and interpolation fixtures now use the actual selected data coordinates. All
fixed-resolution before/after comparisons still use 48×56, rather than reducing
resolution for the performance measurement.
Browser verification used Bokeh 3.2.2 on a temporary local server and the real
880–1100 km simulation pair. All seven models were opened, followed by 21 rapid
cached selections and returning to 3D MAG. Twelve subsequent coherence-toggle
clicks completed without reloading. An exact 0.4 threshold committed to the
slider; the final comparison restored threshold zero. Measured coherence and
its fixed [0,1] color scale rendered correctly. A weighted MT1981 screenshot
before and after an off/on cycle was **pixel-identical**; disabling coherence
changed 17,147 screenshot pixels. No browser errors were recorded.

Bokeh emitted nonfatal `reference already known` warnings during rapid layout
reattachment. One automation click timed out during the combined rapid-switch/
toggle batch; the page remained responsive and the separate twelve-click test
completed. The tests do not claim a zero-warning browser session. The final layout correction
also passed a fresh source-backed synthetic simulation browser run: 21 rapid
selections, correct final MT1981 controls and plot, twelve toggle clicks and no
browser errors. The independent map and zero threshold were retained. Screenshots
are retained under the task visualization directory.

Direct file:// megaplot browsing is blocked by the browser tool's URL policy.
Generated links and the newest saved launch context are checked automatically;
the HTTP Bokeh workspace is checked directly. This is not a claim that every
production dataset, branch or all generated megaplots were visually audited.

The verified existing launchd Bokeh service was restarted after the final changes;
`http://127.0.0.1:5013/health` returned `{"service":"morales-komega"}`.
Existing open sessions need one reload to load the updated source. Subsequent
coherence toggle/threshold/model edits operate within that session without a reload.
