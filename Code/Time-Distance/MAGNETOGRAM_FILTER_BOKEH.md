# Magnetogram Dopplergram filtering workspace

The installed macOS login service starts the shared launcher automatically.
For another checkout, use the scientific environment listed in
`requirements-observation-komega.txt`, including `netCDF4`, and install once:

```sh
../Vesa_2026/.venv/bin/python Code/Time-Distance/manage_komega_service.py install
```

Open `http://127.0.0.1:5013/magnetogram_bokeh_app`. The existing Gaussian workspace
and its old URL aliases remain available on the same server. The magnetogram
workspace is a Bokeh server application: it needs Python for cube loading, FFTs,
persistent caching and the handoff. A standalone HTML export cannot execute those operations.

Select a raw observation pair or a simulation file, choose the retained magnetic
pixels, threshold and replacement value, and inspect the frame comparison. For
simulations, choose the magnetic sampling mode, optional magnetic variable and
two height indices. The displayed diagnostic selector switches between the two
inputs without changing the processing result. The frame selector also only
changes the display. Open Gaussian & Models Filter Tool continues with the
current, fully computed result. The button is disabled while scientific inputs
are invalid or an updated result is pending.

The shared dataset dropdown is closed by default, supports filename/path search,
and closes after selection. **Show full path** changes labels only, preserving
the canonical dataset ID. Scientific controls form one vertical panel above the
plots. Both Dopplergram images have colorbars tied to their shared native mapper;
units and ranges update with the selected data/frame. The frame label is a
separate text component so Bokeh cannot duplicate its number or append a colon.
There are no plot legends.

The four plots use two columns on desktop screens and stack in narrower windows.
After Bokeh measures the axes, colorbars and toolbars, the spatial frames retain
the physical `dw/dh` aspect ratio and the k–ω frame remains square. Resizing
changes frame dimensions only; the image arrays, pixel mappings and data-range
bounds are retained. Titles and colorbars have their own space.

The dataset browser reuses observational batch eligibility and pairing within
each dataset directory. Simulation discovery uses configured single-cube/batch
paths and the simulation root. Optional launcher arguments are `--raw-root`,
`--simulation-root`, `--result-cache`, `--registry`, `--config`, and `--port`.
Repeated explicit raw/simulation roots replace their respective default discovery roots.
Derived k–ω FITS files are not original cube inputs and cannot be used to reconstruct
Dopplergrams. Missing original data or magnetograms produce an informative error.

## Scientific paths

`magnetogram_workflow.py` wraps the existing `AGWFilter` and `TimeDistance` methods.
It does not call the batch output or time-distance correlation routines.

- Observations load two native FITS/HDF5 cubes, discover the unique aligned
  `*HMImag*.fits` in the same directory, divide its deci-Gauss values by ten, and
  use that one map for both diagnostics. Their configured cadence and pixel
  scale remain explicit controls. The native line ordering and observational
  sampling-delay correction are retained in the recalculated phase spectrum.
- Simulations extract the configured observable at the selected NetCDF height
  indices. Cadence, spatial scale and physical heights use the pipeline's own
  coordinate inference. Bottom mode shares the map at the lowest physical
  height; per-height-pair mode applies each height's own map independently.
  Existing zero-field simulation behavior is retained. Simulations receive no
  observational line-sampling correction.
- The original threshold inequalities, absolute magnetic field, replacement
  values and NaN comparison behavior are retained. No reprojection, interpolation
  or automatic resizing is added. Cube/map shapes must agree exactly. Any shared
  explicit observational spatial WCS is checked for incompatibility. Inputs with
  no spatial WCS must already be aligned, as required by the native pipeline.
- Native FFT mean subtraction, phase formation and radial averaging happen
  inside `TimeDistance.compute_komega_diagram` on the magnetogram-filtered
  cubes. A NaN replacement can propagate through the FFT to a nonfinite spectrum;
  the UI reports that outcome. Dopplergram values retain native source units.
  The comparison uses one color mapper. Simulation spatial/time coordinates
  are retained; observations display relative pixel positions and elapsed time.

Only requested NetCDF layers are read into memory by the shared native loader.
This targeted change also benefits the existing simulation processing path.

## Persistent results and handoff

`processing_results.py` implements a reusable processing-result interface. The
default cache is `Data/Filters/processing_results`, with a directory for each
SHA-256 result identifier. Each directory contains a JSON manifest and numeric
`.npy` arrays (loaded through memory maps; no pickle).

There are two stages: aligned unfiltered cube/map/coordinate inputs, and a result
containing filtered cubes, removal masks, k–ω phase and k/frequency axes. Threshold,
selection or replacement changes reuse the aligned inputs. Repeated complete
configurations reuse the filtered cubes and spectrum too.

The key hashes canonical sorted JSON containing source paths, content SHA-256 and
sizes, observation/simulation type, height/observable selection, cadence, spatial
scale, phase-order/delay metadata, magnetic sampling/variable, filter values and
implementation fingerprints/version. A NaN replacement is serialized as `"NaN"`.
Source hashes are reused only while size, nanosecond modification/change times and
inode agree. If metadata changes during hashing, a second content hash distinguishes
sync-provider metadata updates from actual byte changes. Array content, dimensions,
dtype and manifest metadata are verified.
Stale or damaged entries are recomputed by the preprocessing workflow; invalid
handoffs show an error. Per-key file locks prevent duplicate concurrent writes.
All arrays and the manifest are flushed in a staging directory before an atomic
directory rename publishes the complete result.

Filtering, hashing, file reads and FFTs run in one worker process. A 250 ms debounce
and one pending request per document coalesce successive parameter edits. Stale
completions cannot overwrite a newer selection. Completed products are cached even
when the user has moved on. No cache/sampling diagnostics appear in the interface.

The handoff URL contains only `?result=<identifier>`. The shared launcher supplies
the cache root to both applications. The normal Gaussian background loader opens
a generic `processing_result` dataset with the supplied filtered cube pair,
precomputed phase/axes, sampling, source identity and ordered provenance. It does
not recalculate the source phase or load model data in place of the supplied data.
Normal launches without a result keep their existing discovery/default behavior.

## Saved provenance and compatibility

The existing JSON registry remains schema version 1. Gaussian-only saves keep the
same record structure. A preprocessed input adds a `processing_chain` containing:

1. Original dataset identity and inputs.
2. Magnetogram stage: original source fingerprints, dataset type, sampling,
   magnetic variable/mode, resolved alignment metadata, selection, threshold,
   replacement and implementation fingerprints.
3. Gaussian diagram stage: cached input reference, exact Gaussian definition,
   parameters, sampling and axes.

The selected model's inputs, units, base configuration and display controls are
stored separately as `model_context`; model previews are not recorded as
Dopplergram preprocessing. The Gaussian dataset calculation now applies its
three-dimensional Fourier transfer separately to the supplied cube pair,
reconstructs real-space cubes with a checked inverse FFT, and calls the native
`TimeDistance.compute_komega_diagram`. The immutable Magnetogram result is the
baseline for every adjustment; the spatial mask is not applied again. The saved
analysis runtime preserves phase ordering, cadence and coordinate conventions.

The registry still uses locked read/modify/write and atomic replacement, preserves
other dataset records, restores saved Gaussian settings and refuses to overwrite
malformed registry files. Source paths and processing parameters are retained so
the chain can be recomputed if a cache directory is removed. Cache references
themselves require the original source files to remain unchanged and accessible.

## Validation

`Code/Tests/test_magnetogram_workflow.py` covers native observational conversion,
simulation bottom/per-height separation, permuted NetCDF dimensions, native phase
recalculation, hashes, cache reuse/invalidation/corruption, missing/alignment/invalid
inputs, NaN behavior, searchable/scrollable selection, display-only frame updates,
job coalescing, stale-completion handling, generic handoff, Gaussian defaults,
registry compatibility, provenance, replacement, restoration and synced-file metadata changes.

The existing orientation regression
`test_single_cube_magnetic_orientation_metadata_includes_alfven_ratio` expects
zero-field pixels to contribute to layer field-strength means; the unchanged
pipeline excludes those pixels. That pre-existing assertion mismatch remains.
