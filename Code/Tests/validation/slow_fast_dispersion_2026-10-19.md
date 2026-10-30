# Separate Slow and Fast model debug verification — 2026-10-19

The blank panels were caused by the shared Vesa solver's mode-ambiguity mask. It combined uncertainty across all four tracked magnetoacoustic root sheets with the selected two-root mode. A sheet with no dominant global family made every cell ambiguous, including cells where the requested pair was locally identified by the frequency eigenvalues. The default warning mask then hid all values.

The mask correction in `../Vesa_2026/Code/diagnostic_diagram/functions.py`, `_select_magnetoacoustic_mode`, bases the selected-mode mask on whether the requested pair was resolved. The original all-root ambiguity diagnostic is retained as `all_roots_mode_ambiguous_mask`. Missing or overfull mode selections and the equipartition degeneracy remain masked. The dispersion polynomial, local classifications, selected roots, phase arrays, units, and native sampling are unchanged.

A second live-browser defect affected the first draw of a newly computed model: `render_model_pixels` attached an empty RGBA source to the plot, then filled it while Bokeh's model graph was frozen. The initial renderer-reference event could therefore publish an empty source, without a subsequent attached-source event to supply its pixels. The shared renderer now populates the RGBA source before attaching it to the plot. Existing renderers still receive the same pixel arrays through normal updates. Both new attachment-time tests failed before this change and pass after it.

## Regression evidence

- Before correction: both new nearly horizontal-field regression cases failed because every cell was flagged as ambiguous.
- Final validation: 116 relevant checks passed across the numerical, integration, coherence, and static-comparison checks; 2 checks skipped (optional mpmath cross-check and unavailable generated-megaplot launch fixture). The broader run reported 109 passed, 4 failed, and 2 skipped while unrelated filter-status implementation/assertions were edited concurrently. All four affected status cases passed on a targeted rerun against the current files. The three static-comparison checks also passed. No unrelated status changes were reverted.
- Filtered and unfiltered Bokeh renderers both contain finite values with warning masking enabled, for both solutions of both models.
- The seven models' phase and complex vertical-wavenumber arrays match their pre-change snapshots exactly, including NaN positions. The five other models' warning masks also match exactly.
- The exact source Dopplergrams from the screenshot were reloaded using their explicit saved input reference. Their native grid has 120 horizontal-wavenumber bins and 241 frequency bins; no resampling was used.

## Native-grid evidence

| Model | Visible cells per solution | Masked cells | Maximum normalized residual in displayed roots |
| --- | ---: | ---: | ---: |
| slow_mode | 10,897 | 18,023 / 28,920 | 3.068e-15 |
| fast_mode | 10,659 | 18,261 / 28,920 | 1.456e-15 |

Parameters: a = 14.6 km/s; c_s = 7.05246440457191 km/s; inclination = -87 degrees; azimuth = 0.26121180203181327 degrees; separation = 100 km. The returned solutions are labeled by upward/downward vertical group velocity. Unresolved mode regions remain masked; this correction does not claim to resolve their root-sheet identities.

The homogeneous MHD polynomial and fast/slow eigenvalue distinction were checked against [Richard Fitzpatrick's UT Austin MHD Waves derivation, Eqs. 8.41 and 8.45](https://farside.ph.utexas.edu/teaching/plasma/lectures/node107.html).

The existing local service on port 5013 was restarted and its `/health` endpoint verified.

For the screenshot's filter (k0 = 1.5, FWHM k = 10 Mm^-1; nu0 = 3, FWHM nu = 12 mHz), the existing Lamb-boundary/frequency-cap filter has zero amplitude at every resolved Slow/Fast mode bin in the visible 0–8 Mm^-1, 0–11 mHz domain. Thus the weighted panel's finite phase values are zero (white); unresolved cells retain their undefined color. This is distinct from an empty first-render payload or an all-ambiguous mask. The native visible domain contains 4,610 resolved cells per Slow solution and 4,481 per Fast solution.

Live acceptance: Fast was checked after a service restart on the first completed draw, with numerical masking enabled and without toggling a display control. Both Slow and Fast valid phase regions rendered on their first completed draw. The original dataset, exact model inputs, filter settings, and spatial frequency band were restored for the browser check.

Browser evidence: `slow_fast_browser_fast_2026-10-19.png` and `slow_fast_browser_slow_2026-10-19.png`. Final browser selection: Slow, solution 1, phase difference, native dataset grid, warning masking enabled.
