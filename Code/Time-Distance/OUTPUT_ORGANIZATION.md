# Time-distance output organization

The output manager is `output_paths.py`. Numerical definitions, coordinate normalization,
Fourier grids, phase signs, lag conventions, Gaussian filtering and magnetogram masking
are unchanged. The zero-based NetCDF height indices remain zero-based in pair directory
names (`h0_vs_h2`); physical coordinates come from the existing native coordinate resolver,
including its existing photospheric origin convention.

Original simulation cubes and native profiles live under `Data/co5bold/`, separate
from diagnostic outputs. See [CO5BOLD_DATA_LOCATION.md](CO5BOLD_DATA_LOCATION.md)
for the verified relocation, current defaults, and historical-cache compatibility.

The manuscript's `Morales_2025a et al/Figures` is a relative symlink to the
project-level `Figures`. Plot writers and scoped HTML generation resolve both
paths to that single canonical tree. `figure_locations.py` reads the verified
replacement manifest to identify the distinct legacy archive; discovery and
migration never treat the manuscript alias as a second input tree. Historical
dataset IDs and asset names remain stable through `data_locations.py`, including
numerical Bokeh inputs retained in the archive. The batch notebook delegates
gallery placement to the scoped HTML writer rather than overriding it with
`HTML Figures/`.

Both output roots now use these prefixes:

```
Figures/ or Data/
  simulations/<observable>/<East|West|North|South|Annulus>/
    hx/h10G/ | hx/h50G/ | hx/h100G/
    vx/v10G/ | vx/v50G/ | vx/v100G/
    z0/
      <reference>_vs_<comparison>/
        phase_differences/  k_omega/  xcorr/  spatial/
      delta_z_<rounded kilometers>_km/
        phase_differences/  k_omega/  xcorr/  spatial/
  observations/<observational quantity>/<East|West|North|South|Annulus>/
    <recorded category, when applicable>/<reference line>_vs_<comparison line>/
      phase_differences/  k_omega/  xcorr/  spatial/
```

Supported simulation observable directories are `v1`, `v2`, `v3`, `bb1`, `bb2`,
`bb3`, `rho`, `temp`, and `pressure`. Geometry directories use the exact capitalization
above. Observations use the `doppler_velocity` quantity directory by default; `data.observation_observable` may supply an explicitly named observational quantity. Model strength (e.g. `h100G`)
is independent of the magnetogram mask threshold (e.g. `|B| > 3 G`). `z0` acquires
no new magnetic threshold.

The project-level `Figures/` is the new default. The prior
`Morales_2025a et al/Figures/` tree remains intact for existing HTML and manuscript
references. `Data/Time-Distance/` and the unrelated literature/model data remain intact.
New outputs are written to `Data/simulations/...` or `Data/observations/...`.

## The configuration actually present in this project

The audit found no separate text table containing a dataset/height-pair optimized-filter
mapping. The existing Store Parameters interface writes
`observation_filter_parameters.json`. It contains **one explicitly stored optimized
configuration**, for the original `hx/100G` simulation, `v3`, ordered indices 2 and 4.
Its Gaussian values are `central_k=0`, `width_k=5.65`, `central_f=6`, and `width_f=4.05`
(the JSON retains full precision). Its magnetogram stage is magnetic selection,
`threshold_G=0`, zero fill, bottom-layer sampling. These are recorded settings, not
newly estimated parameters.

`optimized_filter_config.py` validates that existing registry schema, extracts the original
input and ordered indices from `processing_chain.input`, and obtains magnetic settings
from its recorded magnetogram stage. Derived FITS/HTML filenames are not dataset identities.
Loads are cached by file size, modification time and change time. The effective configuration,
entry ID, full registry digest and manual overrides are recorded in product metadata.

The exported default `config` and batch base configurations use optimized mode. A missing
or ambiguous entry raises `ConfigurationError`; no default setting is silently substituted.
Historical per-filter text records and plot-export text files are provenance, not evidence
that a filter is optimized. Programmatic `get_config()` also uses optimized mode by default. Explicit `filtering=...`
arguments or `optimized_filtering={'mode':'manual'}` retain the supported manual path.

```python
cfg = get_config(..., optimized_filtering={
    'mode': 'optimized',
    'file': '/absolute/path/to/observation_filter_parameters.json',
    'selection': 'magnetic',
    'overrides': {'gaussian': {'width_k': 2.0}},
})
# Existing explicit filtering dictionaries remain supported:
cfg = get_config(..., filtering=my_effective_filtering)
```

`entry_id` optionally selects a specific matching registry record. Manual overrides are
applied after optimized selection; the effective values determine result identity.
Interactive explorer controls and historical replays use their explicit current/recorded
settings, rather than reapplying optimized defaults on top of them.

## Physical coordinates and ordering

`delta_z = abs(z2-z1)` uses the existing kilometer coordinates. Rounding uses Python's
nearest-integer `round`, including ties-to-even. No equally spaced layers are assumed.
Input order is preserved in pair labels and metadata; ordering for browsing never swaps
scientific inputs.

Separation aliases use a fixed-width decimal IEEE-754 sortable prefix for descending upper height, then
descending lower height, followed by readable `z<low>_to_z<high>_km` coordinates and the
canonical filename. This handles negative heights, fractional/nonuniform layers, and ties.
Dataset/run identifiers break remaining ties deterministically. Adding a new pair never
changes existing prefixes or requires rank renaming. Both alphabetical and Finder natural-name sorting put
the highest pair first; changing Finder to another sort criterion changes its display order.

Most historical observations record a separation but **not absolute formation heights**
or a simulation field orientation. They remain under `observations/doppler_velocity/<geometry>/<line pair>/`
with an explicit unavailable-grouping status. No absolute heights or hx/vx/z0 category are
invented. An explicitly recorded `output.height_values_km=[z_ref,z_comparison]` enables their
separation grouping. `output.category` and `output.field_strength_G` support explicit,
scientifically applicable classifications. Coordinates must agree with recorded separation.

## Identity, reuse, and intermediates

Canonical filenames contain a shortened SHA256 run ID; the full identity is checked
in `.metadata.json`. It includes source dataset/file versions, ordered physical heights,
observable, geometry, effective complete filtering/sequence, magnetogram sampling mode,
processing parameters, line-delay calibration fingerprint and scientific implementation
fingerprints. Worker counts/chunk memory settings do not change filenames. Filter changes
produce different filenames within the same diagnostic directory. Per-product SHA256
verification and live source/version checks gate reuse, including mutations of an already
prepared configuration.

The four native FITS products retain their existing float32 disk precision. An atomic,
data-only `_run_state/` NPZ stores exact in-memory diagnostic arrays and axes for repeated
runs. `filtered_dopplergrams/` optionally stores the pair's effective filtered cubes;
`output.save_filtered_dopplergrams=False` disables that persistence. Filters can vary by
height pair, so the cube-pair cache uses the complete effective identity. Existing shared
Gaussian-transfer/mask caches and immutable preprocessing-tool results remain under
`Data/Filters/`, where they can be reused across diagnostics/pairs. No duplicate large
numerical files are created for the separation view.

Separation entries are relative symbolic links to canonical products and their metadata.
Legacy migration canonical entries are also links to retained originals. The filesystem
used here supports those links. Grouped figures can be opened directly in Finder.
Atomic FITS/NPZ/JSON publication avoids treating partial files as completed products.
Repeated `TimeDistance.run()` reuses a validated complete run without filtering or FFTs.
Batch skip logic validates metadata/checksums instead of checking file existence alone.

Plotting notebooks delegate runtime/path resolution to the pipeline. Live k-omega HTML
exports use the same hierarchy below the selected export root; spatial Save Plot also
persists native spatial phase arrays, axes and frequency-band/contour provenance under
`Data/.../spatial/`. Model-profile summary figures are shared non-pair diagnostics. Historical
unfiltered k-omega plot behavior remains explicit in the plotting notebook; filtered
comparison panels load their own effective filtered products.

## Migration and compatibility

```
../Vesa_2026/.venv/bin/python Code/Time-Distance/migrate_geometry_outputs.py --apply
```

Without `--apply`, this command only plans destinations. It uses `.inputs.json`, recorded
filter text and uniquely matching original-product provenance. Unknown filter values,
conflicting identities and assets with no single-pair identity are flagged. Multi-model
comparison assets stay in the legacy tree because they do not have a single magnetic
category/source pair. Original bytes and HTML paths are retained.

`Data/geometry_migration_manifest.json` records every classified/flagged candidate and
its new destination. Numerical links are verified to resolve to the same underlying file.
Locally materialized products additionally receive SHA256 verification. Google Drive
cloud-only (`UF_DATALESS`) files are linked without forcing bulk downloads; their content
hash is deferred, explicitly recorded, and they are not eligible for automatic reuse.
Legacy products missing full computation/implementation metadata are likewise not silently
substituted for a fully specified new run. They remain directly loadable by their explicit
new or original paths; `.inputs.json` and `.atmosphere.json` companions remain accessible.

The old hierarchy migration CLI entry points forward to the geometry migration command.
Legacy parsing helpers remain available solely to identify archived products. The explorer
catalog, gallery and HTML regeneration tools recognize canonical metadata and avoid
counting height-separation aliases as independent datasets. Old manuscript HTML remains
usable because its original figure/data assets were not moved.

## Validation

`Code/Tests/test_geometry_outputs.py` covers all observable/geometry prefixes, all model
categories, nonuniform/negative/reversed heights, rounded-separation collisions, stable
alphabetical ordering, checksum/source/config invalidation, repeated runs, missing/ambiguous
optimized matches, actual saved settings, manual overrides, and non-destructive idempotent
migration. Existing science/runtime/batch/explorer tests supply further coverage.

`Code/Tests/validation/time_distance_geometry_numerical.json` records the bounded real
observational before/after comparison: identical filtered 64 x 32 x 32 cubes, native k-omega,
coherence, phase-difference and cross-correlation arrays/axes. Every compared array was
bit-for-bit equal. Scientific method/coordinate ASTs matched the frozen pre-edit snapshot,
and `filter.py` was byte-identical to that snapshot. Full-size batch computations were not
repeated merely to reorganize existing products.

## Completed audit results

- 4,755 products linked: 4,337 numerical files and 418 figures. All original files remain.
- All 4,755 canonical links and 216 separation diagnostic groups passed read-back,
  required-directory and descending-height ordering verification.
- 2,959 cloud-only files have deferred content hashes; same-file link identity was verified.
- 9,643 candidates were retained and flagged: 7,988 multi-panel/unclassified assets,
  1,610 ambiguous or missing source/filter associations, and 45 unknown filter records.
- 223 integration tests passed; 135 overlapping final focused checks passed, including
  profile-figure paths. The spatial suite also verified saved numerical maps and axes.
- The bounded real-data before/after comparison had maximum absolute difference zero
  for k-omega, coherence, cross-correlations, phase differences and their axes.
- Test-generated scientific outputs were archived outside the project output views.

Machine-readable evidence is in `Code/Tests/validation/time_distance_geometry_*.json`;
the per-product audit is `Data/geometry_migration_manifest.json`.

## Files changed by this refactor

- Core: `config.py`, `pipeline.py`, `output_paths.py`; new `optimized_filter_config.py`.
- Notebooks: `batch.ipynb`, `plots.ipynb`.
- Provenance/discovery: `dopplergram_recalculation.py`, `observation_datasets.py`,
  `magnetogram_workflow.py`.
- Figures: `komega_plot_export.py`, `integrated_komega_explorer.py`,
  `spatial_phase_explorer.py`, `atmospheric_profiles.py`, `comparison_gallery.py`,
  `regenerate_html_figures.py`. Shared atmospheric summary figures now use
  `simulations/<observable>/<geometry>/<category>/_atmospheric_profiles/`.
- Migration: new `migrate_geometry_outputs.py`; both old migration CLI entry points
  forward to it.
- Tests: new `test_geometry_outputs.py`, updated runtime/batch/migration/explorer
  fixtures and checks, and explicit manual settings in the two existing benchmark
  drivers so they continue to compare identical filters.

Pre-existing unrelated working-tree edits were preserved. `filter.py` and the scientific
spatial-analysis module were not changed by this refactor.

### JSON companions

Machine-readable output companions live in a `json_files/` subdirectory of their product directory, including separation-group links and intermediate processing configuration files. Numerical products and figures remain directly browsable. Readers accept legacy adjacent sidecars, while new writes use `json_files/`. `organize_json_outputs.py` relocates existing managed sidecars, verifies unchanged bytes and relative-link targets, and is safe to repeat. Source configuration registries and original legacy scientific trees retain their existing locations.

### Full simulation sweep from the terminal

```bash
cd "$HOME/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a" &&
../Vesa_2026/.venv/bin/python -Bu Code/Time-Distance/pipeline.py \
  --all-simulations --all-observables --all-height-pairs --all-geometries \
  --default-gaussian --no-magnetogram --skip-existing
```

`--all-simulations` selects simulation mode and discovers NetCDF files recursively
under `config.py`'s `co5bold_batch_root`; `--simulation-root /absolute/path` can
override that discovery root. Hidden paths and repeated resolved file paths are
excluded. `--all-observables` selects each available 4D field once per file,
including `ei`; absent magnetic or thermodynamic fields are not synthesized.
Observable aliases that select the same field are not repeated.
`--all-height-pairs` selects each distinct `h1 < h2` pair on the individual file's
native height grid. `--all-geometries` selects Annulus, East, West, North, and
South; repeated `--geometry East --geometry North` requests a subset.

`--default-gaussian` uses exactly one set from `default_filtering['gaussian']`
(currently `central_k=1.5`, `width_k=4.0`, `central_f=3.0`, `width_f=3.0`), with no
Gaussian sweep or optimized-registry substitution. `--no-magnetogram` disables
that stage and removes it from the active sequence. Together these flags select
manual Gaussian-only filtering for every run, with no field-strength or
inclination mask. Magnetic-orientation metadata remains part of the existing
pipeline and does not mask the analyzed data.

`--skip-existing` enables the existing complete-run reuse mechanism, which checks
scientific identity, source versions, implementation fingerprints, and artifact
checksums. CLI-only changes do not alter the scientific implementation
fingerprint. Outputs retain the managed `Data/` and `Figures/` hierarchy,
run identifiers, separation aliases, and `json_files/` companions.

Append `--dry-run` to expand and count the plan using only source metadata,
without preparing output directories or running calculations. The current seven
files produce 3,450 unique configurations: six magnetic files with seven 4D
fields and one nonmagnetic file with four, each with 15 height pairs and five
geometries. Existing commands without these new flags retain their configured
filtering and single-run coverage; repeated identical explicit inputs are
deduplicated without reversing the order of height pairs.

### Scoped HTML megaplots

`html_output_paths.py` owns gallery placement, shared asset links, explicit legacy import, and context validation. See `HTML_OUTPUT_INTEGRATION.md` for the complete layout and regression evidence.

### Retired magnetic-orientation validation images

The pipeline no longer generates `*_magnetic_orientation_validation.png` plots.
They were optional visual checks, never numerical inputs or Bokeh resources.
Magnetic orientation, field strength, and Alfvén/sound-speed metadata are still
computed and cached with the scientific results. The compatibility key
`orientation_validation_outfile` is empty, and historical configured image paths
are ignored by `TimeDistance`. Legacy migrations skip these retired plots.
The standalone rendering helper remains available for older imports.

Gaussian comparison galleries discover filter settings from real k–ω diagrams
and their metadata, or recorded filter configurations. They do not depend on
validation-image filenames. Historical cached numerical metadata may retain the
original `validation_plot_file` as provenance; no active reader opens that path.
Deleting the validation images does not invalidate numerical caches or change
the scientific implementation fingerprint.
