# Gaussian filter and dispersion k–ω explorer

This document's array weighting describes the **theoretical model-only** display.
Observed/simulated dataset panels now reconstruct both independently filtered
Dopplergrams and rerun the native pipeline; they never multiply phase maps.
See `FILTER_RECALCULATION_REPORT.md` for the distinction and validated data flow.

One Bokeh page now places the Gaussian filter on the left and all six Vesa_2026
dispersion models on the right. **Apply Filter** multiplies the model arrays by the current filter on
every solution of the selected model, and carries the same filter into other
model tabs. Pan/zoom coordinates are linked between both sides.
Wide windows keep both sides together; narrow windows stack the filter above
the models. Compact tab labels keep all seven models within reach.

## Launch

From the Morales_2025a repository root, use an environment with the existing
Bokeh, NumPy, SciPy, Matplotlib, and CMasher dependencies:

```bash
bokeh serve Code/Time-Distance/komega_bokeh_app --show
```

The already installed neighboring Vesa environment can also run it:

```bash
../Vesa_2026/.venv/bin/bokeh serve Code/Time-Distance/komega_bokeh_app --show
```

The previous `gaussian_filter_bokeh_app` launch path opens this combined tool too.
`komega_comparison['vesa_2026_dir']` in `config.py` locates the existing Vesa
solver and interactive modules. They are imported as a private package to avoid
collisions with notebook modules named `config` or `functions`. No copy of the
dispersion relations is maintained here.

## HTML feasibility

An ordinary standalone Bokeh HTML export cannot keep the current behavior:
model-slider callbacks run Python/SciPy polynomial solvers, continuity tracking,
branch matching, and boundary association. Exporting the page would preserve
its initial images but lose those live calculations. A browser-only version
would need a separate Python/WASM runtime or a port of the numerical solver,
plus validation of that runtime's numerical results. This implementation uses
the requested Bokeh fallback to preserve the existing calculations.

## Controls and filter meaning

The four filter sliders still read `filtering['gaussian']` from `config.py`:
central k [Mm⁻¹], k FWHM [Mm⁻¹], central frequency [mHz], and frequency FWHM
[mHz]. The displayed slice uses the pipeline's Gaussian width conversion,
low-frequency suppressor, Bartlett taper, f-mode/Lamb/5-mHz boundary, and
normalization. **Restore filter defaults** resets these four sliders.

The model tabs retain every physical control, all simultaneous k_z solutions,
phase/Re(k_z)/Im(k_z) views, warning mask, f-mode reference, resolution choices,
recalculation, caching, and restore-defaults controls. Models are solved lazily.
Where a configured default falls outside the original model's supported control
range (currently a=0 for three positive-a models), the slider starts at the
nearest supported endpoint and the adjustment is displayed beside that model.

**Apply Filter** starts off. When enabled, each diagram array is multiplied
element-wise by a Gaussian constructed directly on that diagram's k/ν axes.
The signed frequency half required by the existing Bartlett/Gaussian formulation
is reconstructed using the original nt parity. There is no interpolation,
overlay, additional mask, clipping, or application-time normalization. The
existing model plotting routine displays the multiplied phase/Re(k_z)/Im(k_z)
arrays and chooses its usual color scale; filtering does not override it.
The existing optional numerical-warning display mask remains independent.
Hover reports the displayed numerical values and filter response.

Filter changes update every already calculated model tab without a root solve.
**Remove Filter** restores cached originals immediately, without re-solving.
A newly opened tab receives the latest filter when its model finishes. Failed
calculations retain their visible error messages. Cache/grid/timing diagnostics
and filter-state paragraphs are omitted from the interface.
Filter and model state remain independent across browser sessions.

The Bunte zero-field special case previously disagreed with its omega-boundary
polynomial. The shared Vesa solver now uses the same rational coefficient at
zero and nonzero magnetic field. Bunte samples positive frequency cell centers
inside the unchanged 0–11 mHz plot domain because its wave equation has a pole
at zero frequency. Its two quadratic solutions are evaluated as explicit
±sqrt(-c0) sheets, retaining their identities through real/imaginary crossings
without ambiguous matching of unordered numerical roots. Actual failed solves,
residual errors, and degeneracies are still diagnosed. Height-only updates use
these same frequency coordinates.


## Verification

```bash
../Vesa_2026/.venv/bin/python -m pytest -q \
  Code/Tests/test_gaussian_filter_explorer.py \
  Code/Tests/test_komega_explorer.py Code/Tests/test_bunte_filter_tool.py
```

The checks compare all seven models with the original Vesa adapter, compare the
filter with the existing pipeline calculation, verify matching-grid multiplication and removal, and exercise toggles, all filter sliders, model/field/resolution
updates, failure recovery, cached tabs, and independent sessions.
