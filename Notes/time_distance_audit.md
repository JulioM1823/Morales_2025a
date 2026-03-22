# Time-Distance Pipeline Performance Audit

Date: 2026-03-21
Primary target: `Code/Time-Distance/time_distance.py`
Configuration profiled: default `Code/Time-Distance/config.py` paired-cubes run

## Ground Truth

Fresh baseline outputs were generated before any code edits:

- Baseline data products: `Data/Time-Distance/performance-audit/baseline-current/data/`
- Baseline timing/profile summary: `Data/Time-Distance/performance-audit/baseline-current/baseline_summary.json`
- Baseline cProfile dump: `Data/Time-Distance/performance-audit/baseline-current/baseline_cprofile.txt`

Post-refactor validation outputs were written to:

- Refactored data products: `Data/Time-Distance/performance-audit/refactored-current/data/`
- Refactored timing/profile summary: `Data/Time-Distance/performance-audit/refactored-current/refactored_summary.json`
- Refactored cProfile dump: `Data/Time-Distance/performance-audit/refactored-current/refactored_cprofile.txt`

## Baseline Findings

Measured baseline runtime:

- Wall time: `64.189 s`
- Peak RSS: `3.778 GB`

Dominant stages:

- `xcorrj`: `50.005 s`
- `compute_coherence_diagram`: `8.414 s`
- Filtered Dopplergram load + filtering path: `5.308 s`
- `compute_komega_diagram`: `1.238 s`

Top cProfile bottlenecks:

- `parallel_loop` inside `xcorrj` dominated the run.
- Repeated per-center annulus reductions (`np.mean` / `ufunc.reduce`) consumed a large fraction of CPU time.
- The Oana-style coherence azimuthal average repeatedly rebuilt annulus masks and flattened arrays.
- Disk I/O was not dominant after the initial FITS loads.

Classification:

- Primary: CPU-bound
- Secondary: memory-bandwidth-sensitive in `xcorrj`
- Not I/O-bound for this workload

## Refactor Summary

Implemented changes:

1. `xcorrj` now precomputes annulus geometry once per run and reuses it for every radius.
2. `parallel_loop` no longer materializes large `[center, lag]` temporary cubes before averaging.
   It accumulates cross-correlation and phase sums directly while preserving the legacy center traversal order.
3. The `nworkers == 1` path now runs sequentially instead of paying `ThreadPoolExecutor` overhead for a single worker.
4. The Oana coherence azimuthal average was rewritten with exact radial-bin `bincount` reductions.
5. Shared magnetogram inputs are loaded only once when both channels point to the same file.
6. Added regression coverage for:
   - `xcorrj` versus a direct legacy reference implementation
   - `azimuthal_average_fft_complex_oana` versus the legacy loop
   - shared-magnetogram load reuse

## Measured Improvements

Measured refactored runtime:

- Wall time: `54.001 s`
- Peak RSS: `3.490 GB`

Before/after:

- End-to-end speedup: `1.189x`
- `compute_coherence_diagram`: `8.414 s -> 1.460 s` (`5.761x`)
- `xcorrj`: `50.005 s -> 47.530 s` (`1.052x`)
- Filtered Dopplergram load + filtering path: `5.308 s -> 4.114 s` (`1.290x`)
- Peak RSS reduction: about `7.6%`

Parallelization conclusion:

- The workload remains memory-sensitive.
- The conservative default of one worker is still reasonable for the profiled paired-cubes case.
- For this dataset, forcing more threads did not produce a meaningful enough gain to justify higher default contention.

## Validation

Numerical comparison against the frozen baseline:

- `outfile`: exact match
- `komega_outfile`: exact match
- `coherence_outfile`: exact match
- `phase_outfile`: matched to machine precision
  - max absolute difference: `9.64e-15`

Visual comparison:

- Raw baseline/refactored renders are identical for `outfile`, `komega_outfile`, and `coherence_outfile`
- `phase_outfile` differs by at most `1` image level in the raw PNG rendering, with mean absolute pixel difference `1.24e-05`
- Visual comparison summary: `Data/Time-Distance/performance-audit/visual_comparison_raw.json`

Conclusion:

- Scientific outputs were preserved.
- No meaningful numerical or visual regression was introduced.
- The pipeline is still dominated by `xcorrj`, but the non-`xcorrj` overhead is substantially lower and the overall run is measurably faster and lighter on memory.
