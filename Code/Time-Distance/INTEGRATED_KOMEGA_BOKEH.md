# Integrated k–ω dataset, model and Gaussian workspace

The installed macOS login service automatically runs the shared local server.
HTML figures use one **Open in Bokeh** button and a readiness bridge; no manual
server startup or dataset reselection is required. On another checkout, install
the same supervised service once with the existing scientific environment:

```sh
../Vesa_2026/.venv/bin/python Code/Time-Distance/manage_komega_service.py install
```

The application opens at `http://127.0.0.1:5013/integrated_komega_bokeh_app`.
The launcher also serves the separate `/magnetogram_bokeh_app` preprocessing
workspace. Its cached result handoff and ordered saved provenance are described
in [MAGNETOGRAM_FILTER_BOKEH.md](MAGNETOGRAM_FILTER_BOKEH.md).
The same launcher serves `/observation_komega_bokeh_app` and `/komega_bokeh_app`
as aliases of this workspace, so existing comparison-figure buttons and their
explicit dataset/simulation launch context continue to work. Their dataset ID,
default 3D MAG model, and named simulation-average inputs are retained. The
original individual app directories can still be served directly with Bokeh.
The pipeline also attaches snapshot-profile defaults and produces the shared
atmospheric diagnostic figure; its FFT and filtering equations remain unchanged.

Simulation-derived defaults are embedded for every supported model. Primary
dataset changes replace the defaults for its physical height interval and clear
stale model results. **Restore defaults** restores those values. A small status
line identifies the simulation, height interval and snapshot. Retained-default
disclosures and numerical warning messages are omitted from the publishing UI;
their scientific provenance remains in structured metadata. See
`Code/Time-Distance/ATMOSPHERIC_PROFILES_INTEGRATION.md` for unit/provenance and
averaging details.

The three sections occupy the available desktop width. The center receives 34%
of usable width and each outer section receives 33%; its former 280-pixel limit
is removed. On large monitors the outer plot pairs can sit side by side. Smaller
windows stack sections, with controls first, without horizontal scrolling.
Model controls and independent curve switches are in the center. Sampling is
read-only metadata in a collapsed **Extra Information** section at the top.
The primary dataset has a formatted sampling grid, including while comparison
mode is active. A primary simulation also includes the four
native atmospheric-profile panels from the selected cube and snapshot, with
black dots at the selected height pair on every available curve. Profile figures
are cached separately by source and height pair and embedded in the panel.
On narrow screens, the figure scrolls within the sampling panel.
Both dataset selectors use the same closed searchable dropdown, with filename
labels and an adjacent **Show full path** toggle that retains dataset IDs.

## Selections, calculations and callbacks

**Spatial Phase-Difference Analysis** is inline immediately below **Dispersion
Model Parameters**, with controls followed by the raw reference and filtered
selected-band maps in one column. It shares the primary dataset, native height
pair, actual reconstructed cubes, and unsaved Gaussian changes. Dataset and
filter changes synchronize automatically. Frequency edits reuse cached temporal
cross-spectra; magnetic thresholds update only contours. Observations without
registered vector fields retain the explicit LOS limitation. The separate launch,
return, and manual refresh buttons have been removed.

Gaussian, dispersion, spatial, measured coherence, and dataset sections expose
independent plot and control switches. Spatial subplots and comparison datasets
also have individual plot switches. These use native Bokeh visibility and local
JavaScript, retain models and data, and do not submit scientific work. The model
plot switch follows the current model/branch without serializing all inactive
figures into the document. See [SPATIAL_PHASE_ANALYSIS.md](SPATIAL_PHASE_ANALYSIS.md)
for the preserved numerical definitions and [BOKEH_INTERFACE_REPAIR.md](BOKEH_INTERFACE_REPAIR.md)
for lifecycle fixes and current validation.

`integrated_komega_explorer.py` composes the existing observation/simulation
explorer, Gaussian explorer and Vesa model explorer. The dataset explorer's new
`_load_settings` hook separates restoring saved settings from its unchanged
background-loading and stale-request handling. Both selectors share the
discovered catalog but retain independent search and selection state.

Primary selection restores that dataset's saved Gaussian parameters and sampling,
or the existing `config.py` defaults. Secondary selection uses the shared current
Gaussian without changing the primary controls or loading another approved
filter. Each dataset's filter is constructed directly on its own axes, using its
own sampling/parity. By default, every model solves on the primary diagram's
exact frequency and horizontal-wavenumber bin coordinates and sample counts.
**Calculation grid → Default** matches the primary dataset's exact bins, follows
primary dataset changes, and is restored by **Restore defaults**. The second
option, **Custom grid size**, exposes independent horizontal-wavenumber and
frequency sample counts (8–220 per dimension, the native solver limits). The
interactive, balanced and detailed presets have been removed from the menu.
Dataset grids are not truncated to
the preset solver's 220-sample limit; numerical warnings still mask undefined
cells, including zero-frequency poles. Both model panels and their hover cells
use the same bin geometry as the dataset. Root and panel caches include the full
axes, so equal-size datasets with different bin spacing cannot share stale roots.

The comparison toggles mirror one another intentionally: the right pair is always
the filtered counterpart of the left pair. Hiding a model retains all six model
controllers, their inputs, display settings, calculated results and selected
solution. The **Model solution** selector exposes every existing branch while
keeping one model plot beside the dataset. Model input, field, warning-mask,
reference-boundary and grid controls retain their original behavior.

The dataset panels now apply the full signed three-dimensional transfer separately
to their two original (or supplied post-Magnetogram) Dopplergram cubes, check the
inverse FFT's imaginary residual, and call `TimeDistance.compute_komega_diagram`.
Saved phase maps are never multiplied by a Gaussian. `.inputs.json` sidecars
preserve original source, height, sampling and preprocessing references. Original
arrays and Gaussian transfers are cached; a single background worker and generation
checks prevent old completions replacing newer controls. Every adjustment starts
from the same baseline, without accumulating prior Gaussian filters.

The native model controller solves once and renders the original solution and
the **Gaussian and Coherence Weighted Model**. **Apply Gaussian to Model** toggles
Gaussian model weighting independently of measured coherence and dataset
filtering. Switching it reuses the existing solver result. Mode and propagation
titles are omitted above the model subplots. This model weighting is a display
operation. The four Gaussian
controls retain their existing debounce; they do not solve the model or modify
the left-side arrays. Existing plotting masks and natural color scales remain.
Model
outputs remain cleared during a pending root solve, including if the Gaussian
changes in the meantime. The native completion callback refreshes both images.
Dataset switches rebuild image geometry and all hover columns together.

Every applicable diagram shares native branch-associated boundary sources and
the native f-mode source. Each curve has its own visibility toggle, retained
across updates. Plot legends are detached, including their reserved margins.

`WorkspaceState` explicitly records primary/secondary IDs, model inputs, current
and approved Gaussian settings/sampling, both comparison states, and original
and filtered arrays. Load, filter, model, registry and export errors are visible
in the relevant panel. Cache/timing diagnostics are not included in the layout.

## Save Filter Parameters

This action saves **only the primary dataset**, including in comparison mode.
It uses the existing `observation_filter_registry.py` implementation and schema-1
`observation_filter_parameters.json`. Existing keys are preserved:

```json
{
  "schema_version": 1,
  "observations": {
    "fits:Data/Time-Distance/.../example_komega.fits": {
      "dataset": {"id": "...", "files": ["..."], "sampling": {}, "axes": {}, "metadata": {}},
      "gaussian": {"algorithm": "agw_create_filter_bartlett_gaussian_v1", "parameters": {}, "units": {}, "constants": {}},
      "stored_at_utc": "..."
    }
  }
}
```

The example abbreviates the populated metadata. Actual records contain all four
inputs (`central_k`, `width_k`, `central_f`, `width_f`), units, Gaussian constants,
normalization, grid convention, source SHA-256 fingerprints, exact diagram axes,
and sampling (`nx`, `ny`, `nt`, `dt_seconds`, `dx_Mm`). IDs come directly from the
existing dataset loader: source kind plus project-relative path, or a canonical
absolute path for external sources; raw pairs retain their existing compound ID.
Separate processing-run products remain distinct datasets. Model configuration
and comparison state are excluded from the approval registry.

Saving locks the registry, reads and validates existing records, replaces only
the primary record, stages a same-directory temporary file, flushes/fsyncs it,
and atomically replaces the registry. Malformed files are reported and retained.
Source hashes are checked before saving. On revisit, changed source hashes or
axes prevent silent reuse and show a warning with default controls instead.
The panel distinguishes approved settings from unsaved Gaussian/sampling changes.
Tests and browser validation use a separate temporary registry; no tested values
are installed as approved research filters.

For the future batch workflow, use these existing/new reusable interfaces:

```python
from observation_filter_registry import load_filter_parameters, read_registry
from gaussian_filter_explorer import PreviewGeometry, compute_diagram_filter

parameters = load_filter_parameters(dataset.id, registry_path)  # None if absent
record = read_registry(registry_path)['observations'][dataset.id]
sampling = record['dataset']['sampling']
geometry = PreviewGeometry(sampling['nx'], sampling['nt'], sampling['dt_seconds'],
                           sampling['dx_Mm'], 'stored sampling')
# Verify record source fingerprints and axes against the loaded source first.
transmission = compute_diagram_filter(data.kh, data.nu, geometry, **parameters)
filtered_image = data.values.T * transmission
```

`gaussian_metadata(parameters)` is the canonical filter description shared by
registry saving and plot metadata. Future raw-cube processing can use the same
saved inputs with the existing pipeline Gaussian; it is not implemented here.

## Save Plot

`komega_plot_export.py` serializes and clones the **actual displayed pair** into
standalone, self-contained Bokeh HTML using inline resources. Plot arrays, glyphs,
hover, boundaries, warning masks, mapper scales and current ranges are
preserved; original plots remain attached to the live session. Both exported
plots are side by side. No screenshot/selenium dependency or second scientific
plotting implementation is required.

- Left: the currently displayed unfiltered pair.
- Right: its filtered counterpart.
- Middle: the same filtered pair, with Gaussian metadata presented first.

Every action also creates a structured `.txt` file with named sections and
indented JSON values. It includes both sources independently, filenames, IDs,
source metadata/fingerprints, sampling/axes, model reference, all adjustable and
fixed inputs/units, calculated inputs, grid/field/solution, warning-mask and
reference settings, full Gaussian definition, current versus approved settings,
plot palette/limits/ranges/dimensions, comparison state, and UTC timestamp.
Names contain export type, a short source-ID digest, model/comparison label and
timestamp. Both files are staged before publication, and handled publication
failures clean up a partial pair. Each file replacement is atomic; two files
cannot be committed as a single filesystem transaction across a process crash.

The default output is `Code/Time-Distance/komega_exports`. The middle panel's
**Plot export directory**, or launcher `--export-dir`, selects another directory.
Confirmation lists both files; invalid directories, pending/missing data or
model results, and failed filters show errors instead of success.
`--registry`, repeated `--data-root`, and repeated `--raw-root` are also supported.

## Source interpretation and validation

“Unfiltered” means the loaded source before the current interactive Gaussian.
When exact original-input provenance exists, the native loader rebuilds the
baseline from those original cubes and their recorded spatial preprocessing;
the current Gaussian is then applied once. A removed intermediate phase FITS
does not prevent a saved launch with that provenance from loading. Phase-only
products without original inputs cannot support recalculation. Raw-pair loads
retain the existing pipeline's unfiltered calculation. Processing provenance is
included in the exported and saved dataset metadata.

The current managed figure tree is `Morales_2025a et al/Figures`, now a real
replacement directory. Configuration and scoped HTML generation resolve it
through `figure_locations.py`. Historical dataset IDs remain stable; the removed
`Figures_backup_2026-10-17` is not needed for source-backed Bokeh launches.

`Code/Tests/test_integrated_komega_explorer.py` checks all seven models and their
fields/branches, exact filtering on different data grids, untouched left arrays,
no root re-solve on filter changes, synchronized mode switches, retained model
inputs/solutions, dataset-specific registry save/update/reload, malformed files,
sampling approval state, figure launch context for observations and simulations,
all three HTML/text export paths in both comparison modes, and handled failures.
The original Gaussian, dataset, model, Bunte and figure-integration regression
tests are also retained.
