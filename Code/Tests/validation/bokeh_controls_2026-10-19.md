# Bokeh controls and coherence display — 2026-10-19

- Coherence display uses a finite C >= C_min mask at full opacity, as selected by the user. Surviving pixels retain the exact baseline palette bytes; undefined and below-threshold bins are hidden. The phase arrays, roots, Gaussian baseline, estimator, and continuous numerical spectral weights are preserved.
- Successful coherence estimates no longer display the dataset path or estimator paragraph. Pending/error messages remain visible.
- Removed solution/zoom instructions and the masking checkbox from the interface. Existing numerical masking remains active.
- Calculation grid has exactly two options: Default (exact dataset axes when available; otherwise the native interactive grid), and Custom grid size. Custom counts use the native 8–220 sample limits and enter solve/cache/stale-result state.
- Exact parameter controls share a compact two-column layout at center widths >= 360 px and one column below that, without recreating scientific widgets.

Validation: 119 passed, 1 skipped across test_integrated_komega_explorer, test_komega_explorer, test_coherence_switching, test_spectral_coherence, test_komega_layout_sync, test_bokeh_responsiveness, and test_integrated_visibility. Python AST parsing passed for all three edited source modules. The tests include inclusive thresholds, supported C=0, undefined bins, exact original colors, physical-array preservation, invalid/valid custom sizes, default restoration, all seven models, and model/filter callback races.

Browser checks used an explicit synthetic source-backed NetCDF/FITS fixture on a temporary loopback server: full-color threshold masking, absence of removed text/checkbox, two-column inputs at 1280 px, a two-option grid menu, rejection of 7 samples, and a valid 36 x 40 grid. This is not a visual audit of every production dataset. The temporary tab/server were closed after verification.

The existing production launchd service on port 5013 was restarted. Its health endpoint returned {"service": "morales-komega"}. Existing browser sessions require one reload.
