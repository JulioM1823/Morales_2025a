# HTML and Bokeh integration with geometry-managed outputs

The three mega-gallery entry files are generated directly under the observable/direction `HTML/` directory. They aggregate all recorded height pairs and magnetic cases for that observable/direction, retaining the original mega-gallery layouts. Scientific diagnostics keep their category/height-pair hierarchy.

```text
Figures/simulations/<observable>/<direction>/
  <category>/<ordered pair>/{k_omega,phase_differences,xcorr,spatial}/
  HTML/
    field_strength_comparison.html
    field_orientation_comparison.html
    gaussian_filter_comparison.html
    misc_files/comparison_views/<ordered pair>/...
Figures/observations/<observational quantity>/<direction>/
  <ordered line pair>/{k_omega,phase_differences,xcorr,spatial}/
  HTML/{field_strength_comparison.html,field_orientation_comparison.html,gaussian_filter_comparison.html,misc_files/}
```

`Figures` in the hierarchy above means the active managed figure root. After
the replacement directory was moved into the manuscript, that root is
`Morales_2025a et al/Figures`. The shared resolver recognizes the move, preserves
custom output roots, and rebases recorded outer-root image references when the
corresponding asset exists in the replacement tree. Numerical Bokeh launches
with recorded original inputs can rebuild their native baseline without the
removed backup's intermediate phase export.

Previously generated category/pair entry pages remain available for compatibility; the default generator now publishes the mega entry files at the direction level.

The default observational quantity is `doppler_velocity`; `data.observation_observable` explicitly names another quantity. Observations are not assigned a simulated magnetic category or fabricated absolute formation heights. Existing observational entries were relocated under this quantity layer with their bytes and relative-link targets preserved. Original legacy scientific trees remain intact.

Mega-gallery entry pages are scoped by source type, observable and direction, and include all recorded ordered height pairs. Individual supporting views retain their exact ordered-pair context. A field-strength or field-orientation comparison intentionally includes the other recorded magnetic cases for that same observable/direction/pair. Gaussian comparisons retain every recorded filter variant; historical filters are not relabeled optimized. Missing comparison types have an explicit “No comparison plots found” entry page, rather than substituted data.

Shared supporting assets live once per observable/direction/ordered pair:

```text
Figures/<source>/<observable or quantity>/<direction>/HTML/
  misc_files/comparison_views/<ordered pair>/
    <full-resolution comparison pages>
    individual_figures/
    subplot_assets/
    source_figures/
    megaplots/
      json_files/
    bokeh-launch.html
```

Small entry pages link to these common assets across magnetic categories. Large images and numerical sources use canonical files or relative symbolic links. Generated image URLs preserve the visible managed alias, rather than resolving the alias back to an obsolete directory. JSON companions remain under `json_files/`. Scientific arrays are not copied or recalculated to generate galleries.

## Generation and discovery

`plots.ipynb` resolves the current manuscript figure root before saving, stores
comparison images through `comparison_image_directory`, and publishes actual
axes and complete processing identities. Its execution cell refreshes the three
HTML galleries for the active source/observable/direction after the requested
figures are saved. The `batch.ipynb` in-process plotting backend performs the
same refresh and reports its HTML directories and generation time; it does not
depend on running the final notebook gallery cell. HTML failures propagate to
the notebook/batch status.

`comparison_gallery.write_default_comparison_viewers` canonicalizes the root
and recognizes managed quantity/direction folders with either simulations or
observations present. It delegates to `write_scoped_comparison_viewers`; explicit
legacy HTML destinations remain supported. A full discovery run generates a
separate three-page set for every recorded observable/direction. `delta_z_*`
grouping aliases are excluded so a newly saved megaplot appears once. The
gallery preflight rejects missing recorded master images before overwriting
entry pages.

`regenerate_html_figures.py` uses the same root and dispatch rules, preserving
its check-only validation and optional atmosphere refresh without repeating
scientific FFTs.

To regenerate existing managed HTML:

```sh
../Vesa_2026/.venv/bin/python Code/Time-Distance/html_output_paths.py
```

Both HTML command-line entry points accept `--scope` for a specific managed
source/observable/direction, for example:

```sh
../Vesa_2026/.venv/bin/python Code/Time-Distance/html_output_paths.py --scope simulations/v3/Annulus
../Vesa_2026/.venv/bin/python Code/Time-Distance/regenerate_html_figures.py --scope simulations/v3/Annulus
```

Without `--scope`, all recorded configurations are regenerated into their own
directories. Neither command requires a backup directory for managed outputs.
An explicit one-time import from a distinct legacy archive remains available
with `--legacy-figures`; the current manuscript figure tree is rejected as a
legacy input. Import requires recorded axes/navigation and exact numerical
contexts. Missing/ambiguous provenance is reported in
`Figures/json_files/html_integration_manifest.json`, never guessed. Subsequent
runs reuse existing numerical products and shared view publication within each run.

## Exact subplot initialization

Each supported k–omega subplot retains its embedded versioned launch context and readiness bridge to the current integrated workspace. The context carries the canonical numerical source, stable dataset ID, ordered source heights, observable, direction, actual filtering sequence and parameters, magnetogram selection/mode, sampling, processing provenance, and saved atmosphere/model defaults. URL encoding and embedded context must agree.

The selected subplot’s effective Gaussian settings take precedence over unrelated saved registry settings. This precedence applies to the launched dataset; ordinary dataset changes retain the established registry workflow. Launch validation rejects changed input metadata, mismatched source types and inconsistent directions. Dopplergram replay now preserves the recorded time-distance geometry and output geometry instead of dropping them while reconstructing the original baseline. Optimized registry configuration remains a pipeline responsibility: a saved historical plot always initializes its own effective processing values.

The integrated workspace, all seven existing dispersion choices, shared numeric inputs, coherence weighting, spatial frequency averaging and magnetic contours are retained. No model equations, Fourier definitions, phase signs or native coordinate conventions are changed. Observations without vector magnetic fields retain their explicit LOS limitation.

## Validation

Automated regressions cover scoped discovery, observable/direction/pair isolation, shared publication, relative-link resolution, legacy JSON compatibility, stable symlink-aware dataset identities, selected-subplot Gaussian initialization, invalid/stale processing contexts, numerical Dopplergram recalculation, model parameter synchronization, coherence, spatial output readback, atmospheric profiles and magnetogram workflows.

`Code/Tests/audit_scoped_html.py` validates every generated relative reference and embedded launch, checks URL/context equality and scope consistency, and writes `Code/Tests/validation/time_distance_html_integration.json`. The real-tree audit covers 60 imported megaplots, 315 gallery entries across 105 scopes, 4,980 total HTML pages, 4,575 subplot targets and 1,455 numerical launch contexts. Six Google Drive empty symlink placeholders were recovered using exact recorded provenance; scientific files were not replaced.

Live browser checks use isolated observational and simulation source cubes through the existing local Bokeh service. The in-app browser rejects `file://` navigation, so direct-file megaplot clicking cannot be browser-tested in this environment. Direct-file relative references and launch payloads are audited on disk; actual Bokeh controls are exercised over localhost HTTP. Temporary test server configuration and registry are isolated under `/tmp/td-html-browser`.

## Modified integration surfaces

- `html_output_paths.py`: centralized scope, supporting paths, shared publication, import, observation relocation and managed refresh.
- `comparison_gallery.py`: symlink-preserving relative URLs, scoped discovery, common supporting views, navigation and metadata-based product validation.
- `komega_bokeh_context.py`: exact processing context, validation, managed numerical exports and complete comparison scope publication.
- `dopplergram_recalculation.py`, `observation_datasets.py`, `observation_komega_explorer.py`, `komega_explorer.py`: complete input replay, stable alias identities and selected-panel effective Gaussian initialization.
- `output_paths.py`: observational quantity hierarchy and compatibility interpretation of recorded older observation prefixes.
- `plots.ipynb`, `regenerate_html_figures.py`: common scoped generation and explicit failures.
- `test_scoped_html_outputs.py`, existing integration/path/spatial tests, `audit_scoped_html.py`: regression and real-tree validation.
- `test_pipeline_html_generation.py`: public generation for both source types
  and all five geometries, automatic manuscript-root routing, real notebook
  JPEG/navigation output, duplicate-alias exclusion and in-process publication.

The 2026-10-18 pipeline-generation regression run passed **162 tests**. These
include all ten supported simulation observables and the observational
`doppler_velocity` quantity across Annulus, East, West, North and South. Real
Matplotlib JPEGs are saved through both notebook writers; their generated pages
retain the exact numerical source, direction and ordered source heights. The
plotting execution cell and direct in-process batch publication are executed in
isolated fixtures. Both standalone HTML command-line routines also complete a
scoped generation with every local link resolving, no source-image mutation and
no changes to another direction. Read-only discovery still finds all 60 existing
`v3/Annulus` megaplots in the current manuscript root.

One unrelated existing test,
`test_all_models_demo_notebook_is_small_valid_and_user_editable`, is excluded
from that passing run and fails independently because the user's demonstration
notebook has a saved execution count of 1 where the test requires `None`. Its
contents, execution counts and outputs were left unchanged.

Evidence: [pipeline tests](../Tests/validation/pipeline_html_tests_2026-10-18.log),
[CLI generation](../Tests/validation/pipeline_html_cli_2026-10-18.json),
[existing scope](../Tests/validation/pipeline_html_existing_scope_2026-10-18.json),
and [validation manifest](../Tests/validation/pipeline_html_generation_2026-10-18.json).

The combined regression run passed 221 tests; three subsequently added scope/context checks also passed (224 distinct checks). Live browser interactions verified selected observational/simulation datasets, 3D MAG/slow/fast/Alfvén switching, exact numerical edits, coherence weighting, frequency-band averaging (11 bins to 3), vector threshold/inclination controls and disabling contour smoothing. Launch validation also accepts numerically equivalent JSON representations such as `1` and `1.0`, while retaining strict boolean flags and rejecting changed scientific settings.

Observed launch contexts also initialize model height separation from the recorded observational interval, without supplying invented atmospheric inputs. Live validation confirmed Gaussian values `(0.75, 2.25, 3.0, 2.0)` and the recorded 100-km separation initialized automatically.

The supervised project Bokeh service was refreshed after validation; its production `/health` endpoint returned `morales-komega`. The isolated validation registry did not replace the project optimized-filter registry.
