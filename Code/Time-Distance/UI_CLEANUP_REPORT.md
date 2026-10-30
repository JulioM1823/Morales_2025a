# HTML and combined Bokeh cleanup report

## Validation follow-up — October 30, 2026

This section supersedes the validation limits recorded in the cleanup sections
below. Application and scientific source code were not changed during this
follow-up: all 66 non-test Python source hashes match the completed cleanup.
The existing research presets, numerical reference values, tolerances,
notebooks, figures, manuscript, and released bundles were retained.

Resolved test/environment issues:

- Installed notebook, NetCDF, and high-precision validation dependencies in
  isolated temporary directories, without changing deployed environments.
  Root `requirements.txt` now also declares the existing NetCDF workflows'
  dependencies: `netCDF4==1.7.4`, `xarray==2023.12.0`, and
  `dask[array]==2023.12.1`. `nbformat` and `mpmath` were already declared.
- Updated the obsolete `time_distance` test import to its current owner,
  `pipeline`. Standalone dispersion tests now set their sibling-module path.
- Corrected the sampling assertion to verify the existing primary-only Extra
  Information display, including while comparison mode is active.
- Froze theory golden-test physical inputs to their original recorded values.
  Editable research defaults had changed; the original golden values pass
  with the original inputs. No golden numbers, tolerances, scientific
  configuration, or solver implementation was changed.
- Corrected stale tests to accept successfully executed saved notebook outputs,
  distinguish recoverable phase-export deletion from missing original inputs,
  provide required synthetic output identity, and assert the existing retired
  orientation-plot behavior. Scientific numerical assertions were retained.
- Updated saved-context discovery to read the current embedded workspace
  contexts in 60 real subplot metadata files, retaining standalone/archive
  compatibility. The previously skipped real saved-context check now passes.

Final validation:

- **687 tests passed, zero failures/errors/skips**, with seven passing
  subtests: 685 tests in the final four-worker suite and two transport replay
  tests in a separate completed run. The final main run took 158.44 seconds;
  the transport run took 422.20 seconds. Both optional checks now execute,
  including the 50-digit numerical comparison and real saved launch context.
- All **109 Python files compile**. The previous 15 representative numerical,
  HTML, image/navigation, and normalized Bokeh-document records still match
  their cleanup baseline in the completed validation environment.
- **25 actual before/after NetCDF CLI case pairs (50 executions) match** in
  data, coordinates, dimensions, global/variable attributes, encodings,
  filenames, and console output; only elapsed progress text was normalized.
  Coverage includes direct/package execution, progress on/off, Dask/no-Dask,
  existing/new time dimensions, binning to a separate directory or in place,
  and a default-threaded replay. The larger matrix used synchronous Dask for
  determinism. Thirteen of 24 matrix pairs are also byte-identical; other raw
  HDF5 byte differences do not change compared logical content or encodings.
- **10 browser screenshot pairs / 13,310,000 pixels have zero differences**
  at 1440×1100 and 980×1100 in headless Chrome 156, without masks or
  normalization. Checks cover the integrated workspace, expanded native
  atmospheric profile, Gaussian input changes, NC2009-to-Slow switching, and
  standalone figure pages. Native array states match and browser errors are
  absent. Temporary servers/browser were stopped; live port 5013 was untouched.

Validation repairs add 48 Python lines to the earlier cleanup result. The
current combined reduction remains **4 files and 77 Python source lines**:
113 files / 42,322 lines before cleanup, 109 files / 42,245 lines now.

All **112,142 original research/release files remain present**, with unchanged
sizes and symlink status. The 641 provenance-verified synthetic test outputs
were copied to `/private/tmp/morales-validation-20261030/test-artifacts/`,
SHA-256 verified before removal from research trees, and checked again after
archival. No original file or directory was removed. Six original modification
times differ by −117 to +118 ns; exact timestamp preservation is therefore not
claimed. No original content size changed, and the real saved subplot metadata
still matches its recorded SHA-256.

Evidence, exact environments, test logs/XML, CLI outputs, browser screenshots,
source checks, and artifact provenance are under
`/private/tmp/morales-validation-20261030/`. The main run used pytest 9.2.0
with temporary pytest-xdist 3.6.1; the application runtime remains unchanged.

Coverage remains representative: every large dataset/model/solution combination,
physical devices, Safari, Windows/Linux browsers, and following a launch link
into the live production service were not exercised. Full content hashing of
all original large research artifacts was not performed.

## Additional behavior-preserving consolidation — October 30, 2026

The current files on disk, including all pre-existing working-tree changes,
were captured before editing. This pass follows the October 29 cleanup below;
its counts are additional reductions from the October 30 baseline.

| Deleted source file | Consolidated into |
| --- | --- |
| `sampling_information.py` | `integrated_komega_explorer.py` |
| `Code/Tests/test_model_switch_rendering.py` | `Code/Tests/test_coherence_switching.py` |
| `Code/Tests/test_komega_layout_sync.py` | `Code/Tests/test_bokeh_responsiveness.py` |
| `Code/Tests/test_native_dispersion_profiles.py` | `Code/Tests/test_atmospheric_profiles.py` |

`concatenate_netcdf_time.py` now imports its five identical progress-formatting,
logging, and file-size-monitor helpers from `apply_vertical_binning.py`.
Both direct and package CLI entry points remain. All numerical processing
functions in both scripts are unchanged. Imports and current documentation
were updated; historical validation logs and packaged releases were retained.

All Python files under `Code`, including the three unchanged MESA reference
scripts, decreased from **113 files / 42,322 physical lines** to
**109 files / 42,197 physical lines**: **4 fewer files and 125 fewer source
lines**. No source was minified and no new source files were added.

Validation and equivalence evidence:

- Full collection preserves all **624 test IDs** after normalizing the three
  moved module paths. The same three pre-existing collection errors remain:
  missing `nbformat` in two modules and missing `time_distance` in one.
- The explorer suite has the same result before and after: **115 passed and
  one unchanged baseline failure**, with five passing subtests. That failure
  expects comparison-dataset text in Extra Information, while the baseline
  implementation supplies the primary dataset only.
- The affected consolidated tests match baseline: **59 passed, 1 skipped**.
  All 55 affected test/helper declarations have identical syntax trees.
- Portable packaging/setup checks: **9 passed**, including the loopback HTTP
  fixture rerun with permission to bind its temporary local socket.
- All **109 Python files compile**. All three moved sampling helpers have
  exactly identical syntax trees. An initial dependency-binding regression
  was detected, corrected, and rechecked with the affected atmospheric test
  and complete 60-test group.
- All **21 representative output records match**: individual HTML variants,
  launch bridge, JPEG/navigation metadata, Gaussian and synthetic time-distance
  arrays, slugs, Gaussian/integrated Bokeh documents, and six sampling/profile
  HTML variants including embedded PNGs. Only generated Bokeh model IDs and
  elapsed-time status text were normalized in the document comparison.
- Shared progress helpers preserve formatting, stderr output, disabled/active
  and missing-file monitoring, and actual thread shutdown. Direct/package
  imports and CLI help match; help checks used an import-only `xarray` stub.
- The five cache-fingerprinted modules (`pipeline.py`, `filter.py`,
  `magnetogram_workflow.py`, `dopplergram_recalculation.py`, and
  `processing_results.py`) are byte-for-byte unchanged.

A fully passing full suite is not established because the existing collection
errors and sampling assertion remain. Browser pixel equivalence, every large
research dataset, and actual NetCDF concatenation/binning outputs were not
verified; available runtimes lack `xarray` and `dask`. Bare explorer import now
binds the atmospheric helpers earlier; both implementations load them during
initial document construction. The original helper bindings and cache behavior
are preserved. Scientific methods, output formats, figures, manuscripts,
references, standalone applications, migration utilities, and uncertain files
were retained.

All **112,142 pre-existing research/release artifact files** remain present
with unchanged sizes, modification times, and symlink status; full content
hashing of the large original data trees was not performed. The tests created
373 provenance-verified synthetic files (352 processing configurations, six
TEST atmosphere metadata records, 12 linked PNG/PDF figures, and three empty
locks). Those new files were copied to
`/private/tmp/morales-cleanup-20261030/test-artifacts/`, verified by SHA-256,
and removed from the research trees. No original artifact or directory was
removed. Existing release bundles were not regenerated.

Baseline snapshots, logs, output hashes, declaration checks, artifact archival
proof, and the cleanup patch are under `/private/tmp/morales-cleanup-20261030/`.

## Behavior-preserving source consolidation — October 29, 2026

This cleanup uses the existing files on disk as its baseline. The working tree
already contained changes before the cleanup; Git HEAD was not used as the
functional baseline. Imports, notebook references, CLI and Bokeh entry points,
service configuration, dynamic module loaders, and portable packaging were
checked before consolidation. Standalone applications, migration utilities,
launch scripts, and uncertain legacy modules were retained.

| Consolidated file | Current location |
| --- | --- |
| `frequency_controls.py` | `bokeh_ui_helpers.py`: existing frequency conversions and linked controls |
| `model_updates.py` | `bokeh_ui_helpers.py`: existing bounded executor and latest-request runner |
| `html_figure_helpers.py` | `comparison_gallery.py`: existing individual pages, relative links, and launch bridge |
| `Code/Scripts/test_download_density_profiles.py` | `Code/Scripts/test_download_thermodynamic_profiles.py` |
| `Code/Scripts/test_downloader_thermodynamic_fields.py` | `Code/Scripts/test_download_thermodynamic_profiles.py` |

The moved functions and test classes retain identical syntax trees. The two
subplot-navigation branches now share the same bounds/crop calculation, and
the unreferenced private `output_paths._infer_observation_date_slug` helper and
its unused datetime import were removed. All affected imports and documentation
were updated. No research calculation or output template was changed.

The audited Python source set decreased from **111 files / 41,041 physical
lines** to **106 files / 40,993 physical lines**: **5 fewer files and 48 fewer
source lines**. No source was minified. No new source or documentation files
were added.

Validation was performed after each pass:

- Baseline focused checks: 157 passed; downloader baseline: 8 passed.
- Bokeh consolidation: 45 passed, including startup aliases, linked frequency
  controls, and latest-request publication.
- HTML consolidation: 159 passed; six notebook-dependent cases were deselected
  because `nbformat` is unavailable in the deployed runtime.
- Consolidated downloader and portable-tools checks: 17 passed in total. The
  loopback HTTP fixture passed when rerun with permission to bind a local socket.
- All 106 remaining Python files compile. Full collection retains the same 624
  tests and the same three pre-existing collection errors: unavailable
  `nbformat` in two modules and an absent `time_distance` module in one.
- All 15 representative output records match the preserved source baseline:
  three individual HTML variants, the launch bridge, a saved JPEG, subplot
  navigation JSON, Gaussian arrays, synthetic time-distance arrays, slug values,
  and Gaussian/integrated Bokeh documents. Only generated Bokeh model IDs and
  elapsed-time status text were normalized for document comparison.

The broader pre-edit run was interrupted during the expensive model/solution
transport replay after 332 passes, 14 failures, one skip, and the three collection
errors. Ten failures were existing theory golden-value mismatches; four were
notebook-writer tests requiring the unavailable `nbformat` package. A completely
passing full suite and completion of that transport replay are not established.
Browser pixel equivalence, every large research dataset, and Windows/Linux
launcher execution were not verified by this cleanup.

The five scientific modules fingerprinted by processing-result caches remain
byte-for-byte unchanged, preserving those implementation fingerprints. The
existing Data, manuscript/figure tree, and packaged deliverables were retained;
their recorded file sizes and modification times were checked. Five existing
Gaussian cache timestamps differed only below 0.1 microsecond after reads;
full content hashing of the large research artifact trees was not performed.
Existing release bundles and ZIPs were not regenerated. The existing tests also
generated 189 new synthetic configuration/figure files in the research output
trees. Their temporary pytest inputs and TEST-model provenance were verified;
they were archived under `/tmp/morales-cleanup-test-artifacts` and removed from
the research trees. No pre-existing artifact was removed.

Implementation and acceptance evidence for the requested cleanup, October 7, 2026.

All changes are at source/generator level. Original scientific images and existing numerical products were retained. Generated individual crops/pages, navigation records and 105 missing unfiltered FITS were produced through the shared generator and native numerical code.

## Changed files

| File | Change |
| --- | --- |
| [Code/Time-Distance/bokeh_ui_helpers.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/bokeh_ui_helpers.py>) | Shared file selector, label-only path toggle, dispersion/f-mode controls, and legend removal. |
| [Code/Time-Distance/magnetogram_explorer.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/magnetogram_explorer.py>) | Selector, status, frame label, Dopplergram colorbars, controls above plots, responsive grid and physical image aspect ratios. |
| [Code/Time-Distance/observation_komega_explorer.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/observation_komega_explorer.py>) | Shared selector and selection-preserving search for the dataset portion of the combined tool. |
| [Code/Time-Distance/integrated_komega_explorer.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/integrated_komega_explorer.py>) | Wider responsive layout, Model headers, read-only sampling disclosure, synchronized previews, and pending-solve callback guards. |
| [Code/Time-Distance/manage_komega_service.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/manage_komega_service.py>) | Install/manage the automatic supervised macOS loopback service. |
| [Code/Time-Distance/serve_komega_tools.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/serve_komega_tools.py>) | Health endpoint, restricted file/loopback health CORS, and legacy URLs routed to the single combined application. |
| [Code/Time-Distance/komega_bokeh_context.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/komega_bokeh_context.py>) | Publish all applicable subplot contexts, including generic/text panels; exclude colorbar-only axes; shared standalone template. |
| [Code/Time-Distance/comparison_gallery.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/comparison_gallery.py>) | Common individual-figure template and readiness bridge; individual figure links/crops, exact filter/image identity, Gaussian filename digest verification, corrected panel partitioning, annotation click regions and preserved zoom/drag behavior. |
| [Code/Time-Distance/regenerate_html_figures.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/regenerate_html_figures.py>) | Recover exact historical numerical contexts through native loaders/FFT; resume safely; regenerate HTML Figures; refresh historical geometry without changing contexts. |
| [Code/Tests/test_integrated_komega_explorer.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Tests/test_integrated_komega_explorer.py>) | Actual timeout/next-tick pipeline, rapid changes, pending-solve race, source identity, independent curve visibility, sampling and selector regression tests. |
| [Code/Tests/test_magnetogram_workflow.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Tests/test_magnetogram_workflow.py>) | Native filtering/frame behavior, selector identity, units/colorbars, revised UI, and rectangular physical image geometry. |
| [Code/Tests/test_observation_komega_explorer.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Tests/test_observation_komega_explorer.py>) | Shared selector, retained active dataset during search, explicit simulation selection. |
| [Code/Tests/test_komega_bokeh_integration.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Tests/test_komega_bokeh_integration.py>) | Three galleries, exact observational/simulation handoff, original arrays/sampling, invalid context, all panels, filter identity, uniform seven-column geometry and nonoverlapping click cells. |
| [Code/Tests/test_td_batch.py](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Tests/test_td_batch.py>) | Individual HTML figure targets and retained gallery/notebook output behavior. |
| [Code/Time-Distance/INTEGRATED_KOMEGA_BOKEH.md](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/INTEGRATED_KOMEGA_BOKEH.md>) | Combined layout, controls and callback documentation. |
| [Code/Time-Distance/MAGNETOGRAM_FILTER_BOKEH.md](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/MAGNETOGRAM_FILTER_BOKEH.md>) | Automatic startup, selector, controls, colorbars, frame display and aspect-ratio documentation. |
| [Code/Time-Distance/KOMEGA_HTML_BOKEH_INTEGRATION.md](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Code/Time-Distance/KOMEGA_HTML_BOKEH_INTEGRATION.md>) | Handoff, historical recovery and launch/test documentation. |
| [.gitignore](</Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/.gitignore>) | Ignore the generated local service log/Matplotlib runtime directory. |

This report is an additional documentation artifact. The installer also generated `/Users/juliomorales/Library/LaunchAgents/com.juliomorales.morales2025a.komega.plist`; service logs/runtime files are ignored.

## Root causes and fixes

| Issue | Root cause | Implementation |
| --- | --- | --- |
| Subplot navigation | Historical hotspots used local hash/crop navigation; some rows lacked individual exports. | Every applicable target receives an individual HTML page. Existing exact images are reused; otherwise the exact megaplot region is exported. Relative encoded links work from the output directory. Annotation/colorbar margins use separate click bounds without changing crop/data geometry. |
| Historical column mapping/click margins | Connected raster panels were recursively halved, producing uneven partitions for seven columns; floating percentage edges could defeat neighbor detection. A short Gaussian row's expanded horizontal margins could cross a neighboring row's expanded vertical margins. | Allocate proportional subdivision counts before cutting, preserve uniform abutting columns, tolerate numerical edge rounding, and refresh historical geometry while keeping dataset IDs/contexts unchanged. Compute horizontal click footprints first, then vertical separators from those completed footprints. |
| Filter-specific image links | Cleaned basenames repeat across processing directories; shortened Gaussian filenames concealed the column order. | Match saved filter metadata, verify the original filename SHA-1 suffix, and use an exact crop when a source cannot be verified. |
| Launch buttons/startup | Separate dataset/model links assumed a manually running server. Older image-only exports lacked numerical contexts. | One Open in Bokeh button, shared bridge, installed launchd supervisor, exact saved FITS or native unfiltered recovery. All legacy server aliases use the same combined application. |
| Combined width | Narrow fixed containers and a compressed center column. | Responsive desktop allocation of roughly 33%/34%/33%, with stacked sections below the desktop breakpoint. Center measured 461 px at 1440 px and about 610 px at 1920 px. |
| File menus/path labels | Expanded MultiSelect blocks and full-path dataset labels. | Shared FileSelector uses a closed searchable MultiChoice normalized to one canonical ID, closes/blurs after selection, and changes only labels with Show full path. Active selection survives searches. |
| Magnetogram status/frame | Generic status; Bokeh slider titles append a colon/value and duplicate the frame number. | Exact two-line Selected status with bold prefix and dataset class; separate Frame N:  t = x sec Div with slider numeric text disabled. |
| Dopplergram headers/colorbars | Inconsistent header and reference image lacked a colorbar. | Exact filtered header, visible colorbars on both Dopplergrams using their native shared mapper/range and unit labels. |
| Magnetogram controls/aspect | Controls were below/beside plots; four plots in one fixed-height row left extremely narrow image frames after axes/colorbars. | One consistently sized vertical control panel above a responsive two-column plot grid, stacked on narrower windows. Measure actual Bokeh frame margins and set spatial frame width/height to native physical dw/dh; k–ω has a square frame. Arrays and range bounds are unchanged. |
| Gaussian sampling/model controls | Editable sampling widgets occupied central space while model controls were compressed. | Read-only Sampling Information details section at the top, collapsed by default; internal sampling state retained for calculations. Model controls grouped in the central column, Model headers above model views/controls. |
| Dispersion/f-mode coverage | Plot-specific lines/sources and legend-based visibility. | Original native branch boundary/f-mode sources are shared across unfiltered data/model, Gaussian visualization and filtered data/model. Independent toggles control each boundary and f-mode. Native Gaussian Lamb/cap references are shared too. |
| Live filtered results | Preview gate used the other filter state; geometry/hover columns could be stale; a diagram/Gaussian change during a pending root solve could redisplay the old result. | Use the shared current filter, each dataset’s own geometry, replace image/hover fields together, clear stale model previews while dirty, coalesce native callbacks, and apply the latest filter to the accepted native result. |
| Legends | Legends remained attached to plot layout sides and reserved space. | Shared removal detaches Legend models from every layout side. Dedicated curve controls remain. |

## Exact HTML to Bokeh handoff

Each figure record contains a validated schema-1 canonical dataset ID, numerical source, source class, and named model inputs with units. The individual page links through bokeh-launch.html. The bridge polls the local /health endpoint and then forwards the unchanged encoded context to /integrated_komega_bokeh_app. The combined document selects that exact dataset before displaying it. Simulation a, θ, φ, Δz and available cₛ come from its native/saved atmosphere metadata; observational contexts retain observational classification and do not supply simulation overrides. Missing/invalid contexts cannot silently substitute a different dataset.

The installed RunAtLoad/KeepAlive service is already running on 127.0.0.1:5013, so the user needs no terminal/server/reselection step. The health endpoint allows file-origin null and loopback HTTP preview origins. Static HTML does not itself execute Python; the supervised local service supplies that functionality.

Historical recovery used the seven original NetCDF cubes under `/Users/juliomorales/Research/Projects/Morales_2025a/Data/co5bold`. The 105 unfiltered cube/height combinations use the existing raw loader and FFT. Gaussian panels use their exact existing filtered FITS. Saved Gaussian-only atmosphere metadata is reused only for the same native cube/height inputs; missing zero-field orientation metadata is obtained from native recovery, not demonstration defaults.

## Live update and scientific preservation

Widget change → current parameters → native Gaussian/model calculation → complete ColumnDataSource image/geometry/hover update → native mapper/range refresh → Bokeh render. A pending root solve clears the filtered model image until its accepted result arrives. Subsequent Gaussian/diagram changes use the latest controls, including edits made during the pending solve. Tests invoke the real timeout and next-tick callbacks and compare filtered values against the native transmission and model result.

No FFT equation, Gaussian equation, dispersion root solver, threshold inequality, height-selection meaning, classification, unit conversion, pixel mapping or scientific default was changed. The numerical changes are update orchestration, source consistency and native historical recovery. Legend/visibility and aspect-ratio changes affect display only. Existing numerical degeneracy/masking warnings remain visible.

## Acceptance evidence

- Scientific/tool regression suite: 72 passed. Latest focused reruns include 35 combined/context checks, 5 context/path/live checks and 13 Magnetogram checks after the aspect correction.
- Latest gallery/context/notebook suite: 36 passed; 27 unrelated tests deselected. Includes a regression for a short filter row below a wider row. Earlier gallery runs passed as well; repeated runs are not added to the counts.
- Python source compilation passed.
- All 60 historical simulation megaplots regenerated in the requested HTML Figures directory: 15 strength, 15 orientation, 30 Gaussian. All 4,575 subplot targets and individual pages resolve; all 1,455 k–ω targets have exactly one enabled launch button and a validated exact numerical source. Subplot warning logs are empty of warnings.
- Native geometry refresh retains numerical contexts. All 4,575 click bounds contain their plot regions with zero overlaps; all 45 seven-column rows have uniform widths within one raster pixel. The final source fix was followed by regeneration and another audit of the generated pages.
- Browser: production strength, orientation and Gaussian galleries; diagnostic and k–ω individual links; automatic zero-field, vertical-field and exact filter-8 horizontal-field launches. Additional launches used two real saved observational FITS and several recovered simulation products through the same templates. After the final geometry fix, sixth-column vx/50G and seventh-column vx/100G links opened distinct individual figures and initialized their exact datasets/model values automatically, with no console errors in the fresh session.
- Direct Finder/file opening: confirmed by the user to open the correct dataset automatically. Automated browser testing used a loopback HTTP preview because file:// is blocked by the browser tool. Relative targets and Origin:null health response separately passed.
- Desktop combined layout: three columns at 1440/1920; wider center; stacked layout at 980; no horizontal overflow in measured layouts. Magnetogram: two columns at 1440/1920 and one at 980, titles/colorbars visible, spatial images retain square physical geometry for the real square simulation grids. Rectangular geometry is covered by the native observational fixture test.
- Magnetogram browser: hx/100G and hx/50G load/filter/recalculate; searchable dropdown opens and closes; filename/full-path modes preserve selection; correct success text; frame 0→1 updates with native absolute seconds; diagnostic switching works. Scientific control behavior is covered by native workflow tests.
- Gaussian browser: shared filename/full-path selector, collapsible read-only sampling, model controls/headers, independent curve toggles. Rapid Gaussian and model changes ran without an unrelated button press. Screenshot comparison showed both filtered views changed and both unfiltered views stayed pixel-identical for a Gaussian-only edit.
- Final working combined and Magnetogram browser sessions had no console errors. Dependency deprecations remain. Server logs also contain old restart/reconnect token-expiry/patch warnings and process-pool shutdown cleanup warnings from service reloads; fresh launches and current sessions worked. Native model degeneracy warnings are scientific diagnostics, not suppressed.

## Test limitation

The configured observational raw Dopplergram/magnetogram directory is unavailable at both the configured and corresponding local Research paths. Real saved observational k–ω handoffs were tested, and native observational filtering/recalculation/status/geometry tests passed using fixtures. A browser run of Magnetogram filtering on the user’s original observational raw cubes remains unverified. Their location has been requested to finish this acceptance check. The source cleanup and regeneration are finished; full acceptance remains pending this data-dependent check.

## Visual evidence

![Combined desktop layout](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/combined-tool-desktop.jpg)

![Magnetogram controls and corrected plot proportions](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/magnetogram-tool-desktop.jpg)
