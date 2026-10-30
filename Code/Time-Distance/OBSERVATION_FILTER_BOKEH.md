# Observation and simulation Gaussian k–ω filter explorer

This independent application reuses `GaussianFilterExplorer`,
`compute_filter_result`, and `compute_diagram_filter` shared with the model
explorer. The original model application remains available.
The interface has a searchable native scrolling observation/simulation list, the original
four Gaussian sliders, linked dataset/filter/result plots, **Apply Filter**, **Remove Filter**,
**Restore filter defaults**, and **Store Parameters**.

## Launch and workflow

From the repository root:

```bash
../Vesa_2026/.venv/bin/bokeh serve Code/Time-Distance/observation_komega_bokeh_app --show
```

The existing Vesa Bokeh environment now also contains tqdm and h5py for the
observational pipeline. Its existing numerical packages were left unchanged.
In another environment install the normal scientific dependencies:

```bash
python -m pip install 'bokeh>=3.2,<4' numpy scipy astropy cmasher matplotlib tqdm h5py
```

Bokeh serves an HTML page with Python callbacks. A detached `file://` HTML export
cannot load arbitrary dataset files or safely overwrite the project registry;
this app deliberately uses the same Bokeh-server architecture as the model tool.
Keep the server running while using its browser page. Standard Bokeh disconnect
notifications indicate when the server is no longer available.

1. Search by filename, date, diagnostic, simulation name (such as `hx_100g`,
   `vx_10g`, or `z0_0g`), or filter-run path; scroll the list and
   select one entry. Its full path is shown under the controls. Repeated filenames
   in different processing runs are separate datasets.
2. Stored settings load automatically; otherwise the four controls initialize
   from `filtering.gaussian` in `config.py`. The native grid comes from that
   dataset's sampling. **Apply Filter** independently Fourier-filters and reconstructs both original Dopplergrams, then recalculates their native diagnostic; **Remove Filter**
   restores the cached original without loading the dataset again.
3. Click **Store Parameters**. The confirmation appears beside the button only
   after the Python callback completes the registry write. Revised settings
   replace that dataset's entry, preserving all other observations and simulations.

Optional paths can be provided without editing model configuration:

```bash
../Vesa_2026/.venv/bin/bokeh serve Code/Time-Distance/observation_komega_bokeh_app --show --args \
  --data-root Data/Time-Distance \
  --raw-root /path/to/original/observations \
  --registry Code/Time-Distance/observation_filter_parameters.json
```

`--data-root` and `--raw-root` can be repeated. `--config` selects a compatible
project configuration. Without overrides, discovery uses `data_output_dir`,
configured paired-cube batch inputs, and the explicit paired-cube defaults.

## Data and numerical conventions

Dataset reads and raw FFTs run in background workers so the browser stays
responsive. A stale load cannot replace a newly selected dataset. A FITS
read that exceeds 30 seconds (120 seconds for raw pairs) displays a load error;
download cloud-backed source files and their run's `filter_parameters.txt`
locally, then reselect. The timed-out worker's result is ignored. Eight loads
may run concurrently across sessions; blocked cloud reads still occupy worker
slots until the filesystem responds.

`observation_datasets.py` discovers numerical project k–ω FITS products. The app
includes observations and saved simulation diagrams from the same product roots.
Simulation files are recognized by the `simulations` directory, the `hx_`, `vx_`,
or `z0_` filename prefixes, or FITS `SRCMODE=single_cube` for renamed/exported
products. Observation-only callers retain the default discovery behavior; the
app explicitly enables `include_simulations=True`. Original observational
diagnostic cubes use the configuration's existing
batch eligibility rules and all pairs within a dataset directory, matching
`batch.ipynb`. FITS and HDF5 raw cubes use the existing `AGWFilter.load_cube`;
raw-pair phase diagrams use `TimeDistance.compute_komega_diagram` with its lower/
higher diagnostic ordering and phase-delay correction. Discovery/loading does
not run the filtering/output pipeline or modify input files.

The existing saved FITS contract is **array [k_h, ν]** with CTYPE1=KH and CTYPE2=NU,
even though normal FITS NAXIS ordering might suggest the opposite. The app reads
axes as `plots.ipynb` does and displays `values.T`, retaining NaNs, k_h in Mm⁻¹,
frequency in mHz, increasing axes, pixel-edge footprints, CMasher Fusion, and
fixed −80 to +80 degree phase colors. Pan/zoom coordinates match the model tool.

The Gaussian formulation, FWHM conversion (2.355), symmetric frequency envelope,
low-frequency suppression, Bartlett/raised-cosine taper, f-mode/Lamb/5 mHz caps,
k_h < 0.1 cutoff, and conditional per-k normalization come directly from the
shared calculation. The application constructs the Gaussian directly on each
dataset's stored k/ν axes. It reconstructs the signed frequency half needed
by that formulation using nt parity and returns exactly the image's dimensions.
This two-dimensional response is a filter visualization, not an operation on
phase in degrees. The dataset result uses the full three-dimensional transfer
and native cube reconstruction/recalculation in `dopplergram_recalculation.py`.
The plotting routine retains its usual phase palette/scale. Nonfinite cube
inputs and significant imaginary residuals are reported rather than silently
filled or discarded. Phase-only products without recoverable cube provenance
remain viewable but cannot produce a claimed filtered diagnostic. The
filter panel retains its existing peak-based color scale.

Currently discovery finds 666 observational and 769 simulation FITS products, all from previous
processing runs. Their prior processing remains saved as provenance, without
an extra paragraph above the plots. Cache/sampling/filter-state diagnostics
are omitted; persistence confirmations and failures remain visible.
The configured Vesa_2025 raw-cube directory is absent on this machine.
Supply the original cubes with `--raw-root` to inspect unfiltered pairs; they are
preferred at the top of the collection when available. Image-only PNG/JPEG plots
cannot substitute for numerical spectra and are not dataset entries.

Older saved FITS files omit original nx/ny/nt. For them, the app assumes
an even, square cube: nx=ny=2×the stored k count, nt=2×the positive-frequency count.
This cannot distinguish odd/even original nt or recover nonsquare spatial shape.
Confirm the **Spatial/Temporal samples** against the source cube when known.
Cadence/pixel scale come from FITS DT_S/DX_MM. Observations retain their explicit
configuration fallback. Simulation products require these saved header values
so their sampling cannot silently fall back to the observational configuration.
Sampling controls define the native filter preview; nt parity also determines
the reconstructed signed frequency half on the selected dataset grid. These controls
do not relabel the already stored dataset axes. The selected sample counts and cadence/pixel scale are
saved and restored, including odd nt. The nx-based radial slice is the same slice
shown by the existing Gaussian tool; ny is recorded for future 3-D batch filtering.

## Registry for later batch processing

`observation_filter_parameters.json` is the dedicated JSON registry. It starts
empty; validation and browser tests use temporary registries, so they do not
invent optimal scientific settings. IDs include a kind prefix and full project-
relative source path (absolute for external sources), distinguishing filter-run
variants and raw pairs. Simulation records use the `simulation_fits:` prefix;
existing observation IDs and saved records remain unchanged. Both types use the
same registry's `observations` object, preserving compatibility with existing
Python readers. Each dataset record contains:

- dataset ID, label, kind, source paths, SHA-256 fingerprints and prior processing;
- original display axes and phase-correction metadata;
- nx, ny, nt, dt_seconds, dx_Mm used for the filter;
- all four Gaussian controls with units, algorithm version and fixed constants;
- Gaussian normalization, direct-grid multiplication, display conventions, and UTC save time.

Python can read it without Bokeh:

```python
import json
from pathlib import Path
records = json.loads(Path('Code/Time-Distance/observation_filter_parameters.json').read_text())['observations']
for observation_id, record in records.items():
    parameters = record['gaussian']['parameters']
    sampling = record['dataset']['sampling']
    # Resolve record['dataset']['files'], verify fingerprints, then apply the
    # shared compute_diagram_filter using parameters, axes and this sampling.
```

Alternatively, `observation_filter_registry.read_registry(path)` validates the
schema and numerical settings before batch use. A missing registry is treated
as empty and created on first save. Malformed JSON, duplicate keys, nonfinite
numbers, unsupported schema/algorithm, and incomplete records produce a visible
error; storing refuses to overwrite an invalid registry. Repair it externally
and reselect the observation. If source contents/axes changed, saved controls are
not silently restored; the UI reports the mismatch and defaults remain available
for review. Saving checks that the currently loaded source is still unchanged.

Writes lock a sibling `.json.lock`, read the latest registry, replace one keyed
record, flush/fsync a temporary file in the same directory, and atomically replace
the destination. Interrupted replacement preserves the old file. Concurrent
sessions on the same machine preserve other observations; for one observation,
the last successful save wins. The directory must be writable. File locking is
POSIX, matching this project's macOS environment. Network/cloud sync across
multiple machines requires a separately coordinated registry/backend.

## Verification

```bash
MPLCONFIGDIR=/tmp/morales-komega-mpl ../Vesa_2026/.venv/bin/python -m pytest -q \
  Code/Tests/test_observation_komega_explorer.py

MPLCONFIGDIR=/tmp/morales-komega-mpl ../Vesa_2026/.venv/bin/python -m pytest -q \
  Code/Tests/test_gaussian_filter_explorer.py Code/Tests/test_komega_explorer.py
```

Tests cover mixed observation/simulation discovery, raw-pair pipeline calculations, FITS axis orientation,
legacy assumptions, searchable/scrollable controls, source selection, every
Gaussian control, exact array multiplication, original/NaN preservation, removal, save/update,
other-record preservation, restoration in a fresh session, source changes,
invalid/missing registries, interrupted atomic replacement, concurrent writes,
invalid sampling, and source-loading errors. The browser workflow is additionally
checked against real observation and simulation files with a separate temporary registry.

All 666 real FITS products have been verified to load (356 with shape 80×410,
184 with shape 80×400, and 126 with shape 80×420). All 769 simulation products
also load and accept the same direct-grid filter, with shape 120×241. Browser
checks cover filtering and removal, search, scrolling, observation/simulation
selection, storing both kinds in one registry, revisiting and updating settings.
Tests use temporary registries; the production registry remains available for
scientifically chosen values.
