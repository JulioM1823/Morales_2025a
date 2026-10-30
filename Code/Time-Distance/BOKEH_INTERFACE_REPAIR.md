# Integrated Bokeh interface repair — 18 October 2026

The source implementation now presents spatial analysis directly below Dispersion Model Parameters, with independent plot and control visibility. The native dispersion solvers, atmospheric calculations, Gaussian filtering, spatial cross-spectra, magnetic geometry, palettes, phase conventions, and scientific export definitions are unchanged.

## Established causes and scope of the fixes

- **Obsolete callback execution:** the linked model incremented `_solve_generation` but did not check it when a deferred callback executed. Its current-state predicate compared physical inputs, activity and dirty state; switching away and back could make an older callback eligible again. Running the captured pre-change implementation reproduced execution of the old queued solve after that sequence. Deferred callbacks now check dispatch generation; background results additionally check model activation generation and the exact physical inputs/grid. Diagram-only edits during a valid background solve still reuse its exact roots through the native postprocessor.
- **Indirect model activation:** the integrated selector previously changed an unmounted native Tabs model and relied on its callback to activate the solver. It now explicitly changes the controllers' active state, only when that state differs. Model-specific controls and remembered solution branches still use the existing controllers. This removes a presentation dependency; an ordinary single model switch was not universally broken in the baseline tests.
- **Unsettled submission errors:** executor submission errors had no Future and therefore no completion callback to replace the busy status. Submission failures now enter the existing calculation-error display and a later valid request can recover. Fault-injection tests cover this path; it was not observed as a production executor failure.
- **Combined collapse and spatial navigation:** the old Gaussian switch hid its inputs and preview together, while spatial analysis replaced the main interface and synchronized only in that navigation mode. Plot and control switches now act separately; spatial synchronization follows the primary dataset/filter state continuously. The separate launch, return and manual refresh controls are removed.
- **Stale unavailable-source presentation:** an inline spatial section must also handle phase-only or failed sources. It now clears old dataset labels, maps and contours and disables unsupported inputs, retaining their numerical values. It shows the source limitation instead of presenting a previous dataset's geometry.

The baseline's existing exact-input and shared-parameter mechanisms were retained, including the visible mHz controls backed by native N²/angular-frequency values. No duplicate parameter widgets or replacement physical equations were introduced. Ordinary baseline tests passed; the evidence does not establish that every historically reported stalled update had one identical cause.

## Layout and state

`integrated_komega_explorer.py` composes the existing SpatialPhaseExplorer into the middle column immediately after Dispersion Model Parameters. Its controls, unfiltered full-positive-frequency reference and filtered selected-band map are arranged vertically. There remains one Bokeh document, one selected primary dataset and one Gaussian state. Native height order, line-delay corrections, sampling, simulation defaults and source identity come from the existing loader and launch context.

The shared `CollapsibleSection` and `visibility_toggle` helpers provide local JavaScript visibility/label updates with native Bokeh layout reflow. Gaussian, dispersion, spatial, coherence and dataset sections have separate plot/control switches. Spatial subplots and comparison dataset plots also have independent plot switches. The model plot switch follows the currently mounted model/branch and does not retain every inactive figure in the document merely to control visibility. Comparison-mode plots and comparison-dataset controls have their own switches; their controls can remain visible while primary controls are hidden.

Visibility changes do not clear data, reset parameters or submit scientific work. Models remain attached where needed, and frequency/threshold values survive collapse. Spatial changes use the existing temporal-spectrum cache; magnetic thresholds and contour smoothing update only the contour source. Narrow spatial columns put the toolbar at the right to keep it within the column. The native CMasher fusion palette, −80° to +80° display limits, physical aspect ratio and colorbars remain in use. Native magnetic selection remains inclusive at its existing thresholds (Bh >= 10 G and inclination >= 45° initially); no numerical threshold convention was changed.

## HTML pipeline

The context schema is unchanged. HTML source references now also resolve the managed tree after its move into the manuscript directory. Existing megaplot and individual-figure links open the revised shared application automatically. A representative existing h2/h3 simulation megaplot collection was regenerated into `/tmp/morales-interface-regenerated-html` through `write_default_comparison_viewers`: **3 galleries, 314 HTML pages and 97 logically validated launch contexts**. This validates generation/context compatibility, not availability of every referenced physical file. Production figure/data directories and saved filter registries were not reorganized by this repair.

The existing local Bokeh service at port 5013 was restarted to load the changes. Live Python numerical callbacks still require that already-existing service. Standalone plot exports retain their existing self-contained pan/zoom/hover behavior; they do not acquire a new browser implementation of the Python solvers. No new service or package dependency was added.

## Validation

The focused implementation suite passed **87 tests** before the final source-unavailability regression was added. **Combined final coverage is 285 passed and 2 skipped across 287 unique cases.** The broad suite covered 285 cases (283 passed, 2 skipped); the final 12-test control/activation run included two additional cases and passed completely. The skipped cases were the optional mpmath high-precision cross-check (mpmath is absent) and the legacy saved-context lookup (its `.bokeh.json` artifacts are absent). Current scoped HTML contexts were checked separately by regeneration.

Browser tests used a real Bokeh server and temporary source-backed observational FITS pairs and simulation NetCDF cubes, including registered vector magnetic fields. They verified:

- Typed sound speed 8.125 reached both the exact input and the accepted native solver result; a subsequent slider edit synchronized back to the exact input.
- Shared sound speed persisted across model selection; rapid sequences across the seven available models settled on the final selection with no browser JavaScript errors.
- Model plots stayed hidden through model changes while controls remained usable; restoring visibility retained the selected model and values.
- A spatial frequency edit changed the filtered map hash and preserved the raw-reference hash exactly.
- Simulation selection updated the spatial dataset and native height pair; LOS-only observations disabled vector thresholds with the existing explanation.
- Raising the strength threshold, and separately the inclination threshold, changed the fixture contour count from 1 to 0 while preserving both phase-map hashes exactly. Restoring defaults recovered the contour and original maps.
- Independent spatial plot/control collapse removed about **1775.79 pixels** from the rendered vertical layout. Restoration preserved both map hashes, frequency bounds and contours. Data/model plot and control switches were also exercised independently.

Two Google Drive reads blocked the uninterrupted broad run: a FontTools bytecode file and an existing derived Gaussian cache. Validation used the exact installed FontTools version 4.63.0 from a SHA-256-verified official wheel unpacked only under `/tmp`; the remaining 34 tests redirected only the persistent Gaussian cache location to `/tmp` and passed. Native filtering, cache keys and all solver code remained unchanged. No permanent dependency or cache-path setting was changed. The first 251 completed case results and remaining-case results are preserved in the combined test manifest.

Automated checks include exact-input/shared-unit synchronization, all model/branch switches, cached root reuse, stale generations and latest-request publication, submission/numerical error recovery, JavaScript execution without server visibility writebacks, source replacement, native spatial phase/line-delay definitions, magnetic units/contours, Gaussian reconstruction, atmospheric profiles, solver numerics, HTML launch context and standalone exports. Rendering checks complement those numerical tests; screenshots alone are not used as numerical evidence. Browser checks at 600 and 360 pixels had client width equal to scroll width, and the viewport override was reset afterward.

## Replacement figure directory and original-source loading

The initial missing-backup finding described an obsolete intermediate export,
not missing original simulation data. The manuscript's `Figures` is now a real
replacement directory, and the outer `Figures` contains only directory
scaffolding. Configuration and scoped HTML helpers now recognize the active
`Morales_2025a et al/Figures` tree. Recorded outer-root image references resolve
to their exact counterpart there when it exists; custom output roots retain
their explicit destinations. Historical Bokeh IDs continue to use their original
logical labels independently of whether the old backup exists.

A saved launch whose intermediate FITS is absent now uses its explicit
`processing.input_reference` to load the original simulation cube or
observational pair with the existing cached `load_baseline` workflow. No similar
filename, alternate dataset, resampling, or inferred filtering is substituted.
The validated launch retains its original product-path contract for HTML and
sidecar writers. Loaded-data fingerprints identify the original files actually
read, so parameter storage and source-change checks remain functional. Context
ID, recorded filtering and direction checks are retained. Missing products
without sufficient original-input provenance still fail explicitly.

Concurrent requests for one baseline share a per-reference lock around the
existing cache: the two dataset panels cannot duplicate the same cache-miss cube
read and FFT. Interactive recalculation retains native atmospheric parameters
but sets `make_figure=False` to avoid publishing/verifying batch diagnostic
PDF/PNG files on every FFT. That publication had blocked on a Google Drive
manifest read. Batch calculations retain the default publication behavior;
array and atmospheric-parameter identity are covered by regression tests.

The actual horizontal-10 G, v3, h2/h3 launch now loads successfully from
`Data/co5bold/hx/10G/simulation_hx_10G_33570s_48000s.nc`: **120 × 241** k–ω samples
and **482 × 240 × 240** Dopplergrams, with no recalculation error. A direct native
load completed in **14.54 s**. In the rendered production service, the spatial
section showed 440–660 km, both phase maps and magnetic contours. Switching
3D MAG → MT1981 → 3D MAG completed. Editing the frequency band to 1–2.5 mHz
selected 22 FFT bins; restoring 0.7–3.1 mHz restored 34 bins. Independent control
collapse/restoration retained the loaded plots and defaults; no JavaScript
errors were reported during those interactions. The deliberate service restart
produced expected disconnected-WebSocket messages before reload; the final
reloaded session passed another frequency edit/restore with no new console errors.

Corrective validation passed **79 tests**, including six additional cases for
removed exports, exact source-backed array equality, parameter storage,
concurrent baseline reuse, moved-root resolution and HTML link regeneration.
The prior interface test results above remain separate from this final focused
run. An import-order problem in the notebook-writer tests was isolated by
restoring the gallery module after notebook reloads; generic figure navigation
is no longer rejected by scientific-panel filename rules.

The replacement tree contains **1,455 saved launch records**, **735 distinct
dataset IDs**, and references to **seven original simulation sources**; all
seven files are present. This is an inventory/source-existence audit, not 735
full numerical reruns. An attempted all-context sidecar cross-check blocked on
another Google Drive JSON read and was stopped. The real launch and fixture
sidecar checks completed successfully. The static-gallery repair below separately
restores the existing manuscript images for `simulations/v3/Annulus`; the native
Bokeh loading checks above do not depend on those raster exports.

Evidence: [corrective tests](../Tests/validation/bokeh_replacement_tests_2026-10-18.log),
[native source load](../Tests/validation/bokeh_replacement_native_load_2026-10-18.log),
[real browser interactions](../Tests/validation/bokeh_replacement_browser_2026-10-18.json),
and [source inventory and limitations](../Tests/validation/bokeh_replacement_sources_2026-10-18.json).

Full-resolution exact solves and cube FFTs remain computationally expensive. One obsolete in-flight solve can finish before the latest pending request starts; obsolete results cannot publish into a later activation. Existing numerical warnings and observational vector-data limitations remain visible.

Evidence is saved under `Code/Tests/validation/bokeh_interface_*_2026-10-18.*` and the browser captures in this chat's visualization directory.

Validation manifest: [combined tests](../Tests/validation/bokeh_interface_tests_2026-10-18.json), [browser state and hashes](../Tests/validation/bokeh_interface_browser_2026-10-18.json), [remaining scientific and pipeline checks](../Tests/validation/bokeh_interface_broad_part2_2026-10-18.log), and [final controls and activation](../Tests/validation/bokeh_interface_latest_controls_2026-10-18.log).

## Static gallery repair: v3/Annulus

The blank Safari galleries were caused by broken image symlinks pointing to the
removed `Figures_backup_2026-10-17` directory. The current originals still exist
in the manuscript's Google Drive `Figures/Simulations` folder but were absent
from the local streamed tree. This is separate from the numerical-input and
callback failures described above.

Recovered **486 current original images**, including all **60 megaplots**, into
their existing managed locations under `Morales_2025a et al/Figures/simulations/v3/Annulus`.
All 316 available historical image checksums match; the remaining 170 images
match their recorded byte sizes and pass JPEG validation. No Git image or backup
restore, new raster calculation, or scientific-model change was involved. The
per-image source IDs, hashes and prior aliases are recorded in
[`v3_annulus_html_asset_repair_2026-10-18.json`](../../Data/json_files/v3_annulus_html_asset_repair_2026-10-18.json).

Regenerated the three observable/direction entry pages and their 60
full-resolution supporting pages: 15 field-strength comparisons, 15
field-orientation comparisons and 30 Gaussian-filter comparisons. The source
writer accepts an explicit managed scope and preserves each observable/direction's
own HTML directory. A preflight rejects missing recorded megaplot images before
overwriting existing galleries. Regression tests cover scope isolation, intact
entry pages after missing-image failures and rejection of paths outside the
managed figure root. The focused HTML, root-resolution and Bokeh-integration
suite passes **42 tests**.

The completed audit checks **9,564 HTML files** (including preserved supporting
pages), **32,769 local URL/provenance references** and **1,455 embedded launch
contexts**. There are no missing image/page references, broken image aliases or
active archive references; every embedded launch records `v3/annulus`. All 486
recovered files also pass a second SHA-256, dimension, byte-size and JPEG check.

Evidence: [regeneration](../Tests/validation/v3_annulus_html_regeneration_2026-10-18.json),
[local-link audit](../Tests/validation/v3_annulus_html_links_2026-10-18.json),
and [focused tests](../Tests/validation/v3_annulus_html_tests_2026-10-18.log).
Browser automation rejects local `file://` navigation, so this static-gallery
repair is validated through file resolution, exact image hashes and decoding;
it is not claimed as a rendered-browser test. Other observables and cardinal
directions were outside this regeneration scope.
