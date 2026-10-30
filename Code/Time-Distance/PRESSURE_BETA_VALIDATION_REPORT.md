# Pressure and plasma-beta integration — 2026-10-15

The supplied [KIS share](https://cloud9.leibniz-kis.de/s/aJzFwPSqDoeboxR)
contains nine updated **one-dimensional** atmospheric snapshots. Pressure and
density exist in all nine; plasma beta exists in the seven magnetic snapshots.
These are not spatial/time cubes. The matching and latest OPeNDAP snapshots
checked for all nine models expose neither pressure nor plasma beta. The seven
existing local time-series cubes likewise contain neither field.

## Saved data

Directory: `/Users/juliomorales/Research/Projects/Morales_2025a/Data/co5bold/co5bold_1d_profiles`.

- Nine `MODEL_tTIMEs_pressure_profile.h5` files.
- Seven `MODEL_tTIMEs_plasma_beta_profile.h5` files.
- `thermodynamic_profiles_manifest.json`, with source hashes, source URLs,
  identity checks, ranges, units, and limitations.
- Publisher originals retained in `thermodynamic_profile_sources/`.

All 120 heights are copied unchanged and exactly match existing thermal and
density profiles. Values are identical to the supplied pressure/beta arrays;
no further horizontal averaging, vertical binning, or interpolation is applied
to the saved files. Existing thermal/density files were not overwritten.
Publisher density agrees with independently downloaded native horizontal means
to below `2e-7` relative, consistent with its float32 accumulation/storage.
Model IDs and snapshot filename tokens match. Precise times are retained from
the corresponding independently retrieved density snapshots; publisher files
have no independent time attributes.

Pressure units are assigned using the CO5BOLD cgs convention, `dyn/cm^2`.
The [original manual's averaged-data example](https://www.astro.uu.se/~bf/co5bold/8_3Files_with_averaged_data.html)
explicitly labels pressure with that unit. The dimensionless ratio
`rho*cs^2/P` has median 1.59–1.63 across the nine files, supporting this convention.
This is a unit-consistency check, not an exact identity between independently
averaged thermodynamic quantities. Source files omit unit attributes; the
assigned convention is explicitly recorded rather than presented as source metadata.
Beta is dimensionless. Its publisher averaging definition is absent; it is
copied directly and is not recomputed as a ratio of averaged quantities.

## Implementation

| Source | Change |
|---|---|
| `simulation_observables.py` | Shared pressure/beta aliases, unit contracts, actual-field selection, and spatial display units. |
| `filter.py` | Optional pressure/beta selection requires an actual 4D field; records native units and preserves time/space samples. |
| `config.py`, `output_paths.py`, `pipeline.py` | Expose/document optional observables and canonical output names. |
| `plots.ipynb` | Pressure/beta maps use their physical units instead of velocity conversion and labels. |
| `download_files.sh` | Preserves optional thermodynamic fields through existing spatial binning/output instead of discarding them. |
| `download_density_profiles.py` | Reuses native-profile validation/reduction for additional stored scalar fields. |
| `download_thermodynamic_profiles.py` | Imports publisher snapshots or retrieves available full server fields, with grid/time/unit checks. |
| `atmospheric_profiles.py` | Fourth pressure/beta panel, separate logarithmic axes, matched native grid, common simulation height limits, and source-aware cache invalidation. |
| `agw_simulation.ipynb` | Refreshed displayed four-panel figure; its existing `save_diagnostic` call uses the updated shared renderer. |

Beta is undefined for zero magnetic field; those panels state this rather than
inventing a finite beta. All plotted profiles use the same origin and simulation
cell-centre limits. Display endpoints are interpolated; native files stay intact.
Pressure and beta are selectable only when the requested simulation cube
actually supplies the full field. A 1D snapshot cannot be used as a substitute
for `P(x,y,z,t)` or `beta(x,y,z,t)`.

## Verification

- Eight script regressions pass, including the real NCO downloader with vertical
  binning on/off, native-height preservation, missing units, and source identity.
- Nine thermodynamic-observable regressions and twenty atmospheric-profile
  regressions pass. Tests cover exact layer/time values, field aliases,
  rejecting 1D substitutes, pressure unit conversion, unchanged velocity
  behavior, the fourth panel, source-dependent cache refresh, and height bounds.
- All seven main-configuration four-panel diagnostics rendered; the notebook's
  displayed horizontal 10 G plot was visually inspected and refreshed.
- Python sources and both modified notebooks' code cells compile; downloader
  shell syntax validates.
- Broader selected regression run: **134 passed, 4 failed**. All four failures
  arise from synthetic single-cube filenames lacking an explicit `hx/vx/z0`
  output category in the current output-identity validator. This is separate
  from pressure/beta loading. Exact failures and traces are retained in
  `Code/Tests/validation/pressure_beta_2026-10-15.log`.
