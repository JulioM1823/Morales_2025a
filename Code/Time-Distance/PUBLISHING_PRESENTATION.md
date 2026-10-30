# Publishing presentation cleanup — 2026-10-19

The shared Bokeh workspace used by existing HTML launch links now omits retained-default disclosures, dataset match counts, Gaussian completion/unsaved notices, numerical warning messages, and mode/energy-propagation subplot titles. Solver diagnostics and fallback provenance remain in exported metadata; numerical masks and calculation errors retain their existing behavior.

The right model is labeled **Gaussian and Coherence Weighted Model**. **Apply Gaussian to Model** switches its Gaussian display weighting independently of dataset filtering and measured coherence. It does not repeat root solving or mutate the native solver fields. State, hover transmission, and export metadata record the switch.

Sampling Information now uses separate dataset sections and labeled sampling values. Each simulation entry embeds the existing four-panel atmospheric diagnostic using that exact cube, Model, snapshot, and profile file. Figures are cached by source and height pair. Every available curve, including twin-axis curves, has black dots at the selected two heights. Markers use interpolation on the displayed native curve. Undefined/missing physical curves remain undefined. The figure scrolls inside its panel on narrow screens.

Validation:

- 10 new presentation/weighting/source-selection tests passed, covering all seven models and independent Gaussian/coherence switches. Existing root results and dataset outputs remained unchanged.
- A separate marker check passed for all nine profile curves, including pressure and plasma beta, against independently interpolated expected positions.
- The selected regression suite had 140 passes, one optional skip, and one existing failure: `test_missing_source_and_empty_collection_report_errors`. The same failure reproduced after restoring the pre-change presentation methods in an isolated process. The test expects deletion of an intermediate FITS file to prevent loading, but the existing loader recovers it from recorded original cubes. That behavior was not changed.
- Two targeted checks passed after the final sampling-layout update.
- All seven native simulations from the existing 440–660 km HTML gallery produced distinct source-matched embedded figures; see `Code/Tests/validation/publishing_native_profiles_2026-10-19.json`.
- Browser verification followed an existing hx_100g HTML subplot link into its exact saved context on the restarted port-5013 service. Sampling showed 240 × 240 × 482, 30 s, 0.16 Mm; its diagnostic used SVGd3r16bhCcp1p at t = 44400 s with dots at 440 and 660 km. The Gaussian model switch was toggled off/on and restored. No browser error logs were captured.
- At the browser's 356 px viewport, expanded sampling content remained 308 px wide and document scroll width stayed 356 px. The 1000 px profile figure scrolled within its own container.

Logs and UI screenshots are saved under `Code/Tests/validation/publishing_*_2026-10-19.*`. Scientific source arrays, historical HTML exports, research filters, and registries were not changed by the presentation cleanup. The existing supervised Bokeh service was restarted to load the updated source.
