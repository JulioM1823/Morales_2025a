# Bokeh dispersion consistency audit — 2026-10-15

The later [native-profile consistency pass](DISPERSION_PROFILE_CONSISTENCY_REPORT.md)
supersedes this initial audit's coarse-density sourcing and magnetic-unit
assumptions. The sections below retain the earlier implementation record.

The six requested corrections are implemented in the Morales interfaces and their existing Vesa_2026 dependency. Slow and Fast remain separate models. No simulation arrays, manuscript files, existing notebook execution state, or unrelated Theory settings were changed by this task.

| Requested correction | Underlying issue and implemented correction |
|---|---|
| Exact numerical inputs | Sliders had no exact entry path. A reusable `ExactSlider` pairs each slider with a committed text input. Finite decimal/scientific notation is accepted without step quantization. Enter and blur commit; invalid/incomplete entries retain the last accepted model value and display an error. Valid entries beyond suggested bounds expand the slider with an explicit notice. Hard angle/index bounds are rejected. Disabled state is synchronized. Labels wrap above each slider/input row to avoid overlap. |
| Signed angles | NC inclination was limited to ±89°, and homogeneous modes to ±90°. All magnetic-model inclination/azimuth controls and validators now permit [-180°, 180°]. Signs are retained. The configured zero Alfvén speed is also accepted rather than being clipped to the previous 0.05 km/s slider minimum. |
| Atmospheric inputs | Exact Model/snapshot identity, variable metadata, units, native cell coordinates and bin membership are checked. Common height interpolation and interval integration are reused by every model. A legacy pipeline bug excluded zero-field cells from magnetic-strength means; those cells now contribute their valid zero magnitude. |
| Magnetic geometry | Existing forward field reconstruction already matched the reference. It is centralized and independently tested; the inverse uses atan2. Legacy paired-layer angles are now averaged as Cartesian unit vectors rather than independently averaging inclination and azimuth. Cancellation is reported as undefined. No absolute values or angle-sign changes are introduced. |
| Shared parameters | One document-local `SharedParameterState` propagates physically identified, unit-checked inputs to every dependent model and its exact field. Source edits calculate once; inactive models remain dirty until opened. Reset/dataset updates are batched. Display choices, solution choices and grid resolution remain model-local. Both integrated and native standalone documents use this architecture. |
| Squared buoyancy | The interface and active solver paths use signed `N2` in s^-2. Every former `self.N**2` term consumes `self.N2` directly. Legacy explicit positive-N model inputs remain compatible through a single square. Old atmospheric metadata is refreshed from its recorded stratification; an unsigned N alone is never claimed to recover a signed N². |

## Geometry and equations

The convention is that of [Newington & Cally (2010), Section 2 and Eqs. (3)–(5)](https://arxiv.org/pdf/0910.3233):

\[
\mathbf B=B(\sin\theta\cos\phi,\sin\theta\sin\phi,\cos\theta),\qquad
k_\parallel=k_x\sin\theta\cos\phi+k_z\cos\theta.
\]

\[
B=\operatorname{hypot}(\operatorname{hypot}(B_x,B_y),B_z),\quad
\theta=\operatorname{atan2}(\operatorname{hypot}(B_x,B_y),B_z),\quad
\phi=\operatorname{atan2}(B_y,B_x).
\]

The actual cube metadata identifies `bb1`, `bb2`, `bb3` as Cartesian x, y, z field components, with `xc3` increasing upward. The reference propagation plane is `xc1`–`xc3`. Canonical extracted inclination lies on [0°,180°]; manual signed values retain their exact representation. Zero/vertical fields use a neutral zero azimuth for model inputs. Existing orientation diagnostics keep their undefined-direction masks.

The NC polynomial was checked directly against the published determinant, including its decoupled Alfvén factor at phi=0. Homogeneous Alfvén, Slow and Fast retain their existing equations and mode separation. Numerically singular horizontal/zero-field cases retain the solver's explicit non-isolated-root handling.

## Atmospheric source and units

| Quantity | Extraction or derivation |
|---|---|
| Height, time | Unit-bearing `xc3` centres relative to `xc3[0]`; snapshot filename time must match exactly one cube time entry. Unitless legacy profile `z` is verified in cm against native `xb3` bins. The height origin is not asserted to be optical-depth unity. |
| Sound speed | Native `sound_speed` profile, cm/s → km/s by 1e-5, with the explicit legacy-unit contract in configuration. |
| Density | Exact snapshot `rho`, already a horizontal mean on six binned levels; declared g/cm³ (or supported SI units). No local density field is invented. |
| Field and Alfvén speed | Exact snapshot Cartesian component profiles, horizontal averaging retained from the existing atmospheric workflow. G → T by 1e-4 and g/cm³ → kg/m³ by 1000. `a=|B|/sqrt(mu0*rho)` converted to km/s. Nonlinear height integration occurs before interval averaging. |
| Density scale height | `H_rho=-1/(d ln rho/dz)`, using a nonuniform-coordinate derivative of the available density profile. Only finite positive scale heights initialize the existing stratified-model H controls; the signed derivative remains available for N². |
| N² | `-g*d ln rho/dz - g²/cs²`, with positive g=0.274 km/s² by explicit configuration. Derived before height averaging, preserving negative values. Stored real `brunt_vaisala_freq` is retained as a diagnostic, not used to infer a lost sign. No directly stored signed N² was found in these files. |
| Acoustic cutoff | `omega_c=cs/(2 H_rho)` for the existing locally isothermal NC relation, derived on the same common grid. Stored isothermal/non-isothermal diagnostics remain available for comparison. Frequencies are angular rad/s. |
| Temperature | Stored `temperature` in K under the explicit legacy-unit contract; diagnostic only. |
| Pressure, pressure scale height | Not present in the inspected cubes/profiles. Specific internal energy `ei` is not pressure; no EOS or pressure profile is fabricated. These are not direct controls in the implemented dispersion models. |
| gamma, tau, g | The exported adiabatic-index diagnostic has no verified Cp/Cv definition, and tau/gravity profiles are absent. Existing model constants are retained and disclosed. Gravity used to derive N² is recorded separately in provenance. |

Thermal quantities are interpolated on a common grid containing the actual cube endpoints. No boundary extrapolation or interpolation across invalid profile cells is allowed. A selected height pair uses integral/separation; identical heights use point sampling. All models initialize from this same state. N² controls use angular s^-2; the diagnostic conversion to cyclic mHz² is multiplication by `(1000/(2*pi))**2`.

## Verification and evidence

| Check | Result |
|---|---|
| Real simulation audit | All seven configured snapshots, 42 native height points and 105 height intervals passed. Independent local quadratic derivatives and SI calculations matched N² within 1.67e-17 s^-2. Three horizontal-field snapshots contain negative N² in the sampled domain. |
| Legacy solver regression | 108 omega/kz coefficient arrays were bit-for-bit identical before/after for explicit legacy positive-N inputs. |
| Targeted scientific/UI suite | 81 passed after the input/layout changes; includes vector round trips, limiting/equivalent angles, exact precision, invalid values, range expansion, Enter commitment, callback counts, shared state, source migration, signed N² and zero-field averaging. |
| Final geometry/static comparison suite | 43 passed, one unrelated notebook test deselected, after preserving the original radians arithmetic order in the shared reconstruction. |
| Broader relevant integration run | 182 passed, 1 skipped, 1 unrelated notebook test deselected. |
| Full collectable repository suite | 345 passed, 1 skipped, 11 failed; one additional collection error. The failures and error are detailed below. |
| Browser | Verified exact MAG → Slow → MAG edits, negative N², invalid-angle rejection, simulation selection/defaults, live plot updates, and zero JavaScript errors. Verified the real hx_100g 440–660 km initialization: a=3.432089399730252 km/s, cs=6.6625338403860725 km/s, N²=0.0006361083357250786 s^-2, omega_c=0.028312622197831695 rad/s. |

The real-data audit is reproducible with `Code/Tests/audit_dispersion_atmospheres.py`; its output is `DISPERSION_ATMOSPHERE_AUDIT.json`. Raw test logs are saved in `Code/Tests/validation/dispersion_*_2026-10-15.log`.

Ten full-suite failures belong to `Code/Tests/test_functions.py`, which imports the separate `Code/Theory` implementation. Its existing working-tree constants differ from the saved golden configuration (tau, a, theta and phi). All 28 tests in that file pass when run in memory with the committed configuration; the user's current settings were preserved. The remaining failure requires an already executed demo notebook to have no execution count, and was present in the baseline run. Collection of `test_time_distance_helpers.py` fails because its imported legacy `time_distance` module is absent. These are not hidden or reported as a clean full-suite pass.

## Files changed by this task

| Location | Files and purpose |
|---|---|
| `Morales_2025a/Code/Time-Distance` | `atmospheric_profiles.py`: signed stratification, cutoff, metadata migration/provenance; `vesa_support.py`: load shared dependency utilities; `komega_explorer.py`: shared state and exact-control composition; `komega_bokeh_context.py`: N²/signed-angle launch support; `dispersion_comparison.py`: geometry and N² for static calculations; `pipeline.py`: inverse geometry and unbiased zero-field magnitude means; `config.py`: explicit gravity magnitude. |
| Same directory, UI composition | `gaussian_filter_explorer.py`, `observation_komega_explorer.py`, `integrated_komega_explorer.py`, `spatial_phase_explorer.py`, `magnetogram_explorer.py`: reuse exact slider/input rows, including filter, spatial and frame controls. Unrelated concurrent coherence work was preserved. |
| `Vesa_2026/Code/diagnostic_diagram` | `numeric_controls.py`: exact inputs/validation/shared state; `magnetic_geometry.py`: common forward/inverse/projection utilities; `interactive_models.py`: signed ranges, physical validation and N² adapter; `interactive_bokeh.py`: numerical controls, shared standalone state and reset handling; `functions.py`: direct signed N² consumption with legacy compatibility; `config.py`: correct angular-frequency unit comments. |
| `Morales_2025a/Code/Tests` | Added `test_dispersion_consistency.py` and `audit_dispersion_atmospheres.py`; updated relevant expectations in `test_atmospheric_profiles.py`, `test_dispersion_comparison.py`, `test_bunte_filter_tool.py`, `test_komega_bokeh_integration.py`. |

## Scientific and operational limitations

Equation (4) assumes a hydrostatic adiabatic background. Without pressure and verified Gamma1 profiles, the general pressure-gradient buoyancy definition and hydrostatic balance cannot be independently checked for these dynamic MHD snapshots. The reported N² is the reference model's definition evaluated on the available stratification.

Density has six vertical bins and is already horizontally averaged. The current atmospheric workflow uses the Alfvén speed of averaged component/density profiles, not the horizontal mean of local Alfvén speed. One snapshot represents the k–omega time series. These limitations are recorded in provenance; spatial-analysis arrays retain their existing spatial structure.

The k_h diagrams are horizontally azimuth-averaged, so phi is relative to a stated xc1 reference plane, not an observed unique horizontal propagation direction. MT1982's pre-existing omega polynomial uses g whereas its kz expression uses N²; unverified omega boundaries remain diagnosed rather than falsely presented as valid. No equation redesign was performed.

Models coexist within each Bokeh document, so shared state is session-local. Separate browser sessions remain independent. Existing server processes retain imported Python code until restarted; the corrected source was verified in an isolated process on port 5017. No pre-existing user server was stopped or republished. Legacy atmospheric sidecars are upgraded when read; numerical FITS data and archived figures are unchanged.
