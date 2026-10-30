# Dispersion parameter sourcing — 2026-10-15

The shared atmospheric loader now uses the matching native density and thermal
profiles for model inputs. The previous loader still differentiated the six-level
cube density and computed Alfvén speed from separately averaged components and
density, despite the availability of native profiles.

Definitions follow Newington & Cally (2010), §2 and Eqs. (2)–(4):
[journal article](https://academic.oup.com/mnras/article/402/1/386/1032976),
[accessible author manuscript](https://arxiv.org/pdf/0910.3233).

## Physical inputs

| Input | Current source and calculation |
|---|---|
| Sound speed `cs` | Native `sound_speed` profile, cm/s → km/s. |
| Alfvén speed `a` | Native supplied horizontal mean of local Alfvén speeds, cm/s → km/s. Native-layer checks independently establish its definition and units. Fallback uses physical components and the matched native density, evaluating the nonlinear speed before interval integration. |
| Density scale height `H` | `H_rho = -1/(d ln rho/dz)`, differentiated on the 120-level native grid before interpolation. Density inversions are retained; invalid positive-scale-height model inputs are disclosed. |
| Squared buoyancy frequency `N2` | `N² = -g d ln rho/dz - g²/cs²`, in s⁻². Signed values are retained; the stored real `N` diagnostic is not squared to infer unstable regions. |
| Isothermal cutoff `wac` | `omega_ci = cs/(2 H_rho)`, in rad/s, from the same native gradient. The non-isothermal diagnostic remains distinct. |
| Inclination/azimuth | Physical cube components use `theta=atan2(hypot(Bx,By),Bz)` and `phi=atan2(By,Bx)`. The common signed-angle convention and `k_parallel=kx sin(theta)cos(phi)+kz cos(theta)` remain in use. |
| Pressure and beta | Matching native profiles are loaded into the atmospheric state. Pressure supplies an independent hydrostatic/pressure-gradient check. Neither variable is inserted into dispersion relations that do not take it as an independent input. |
| Gravity `g` | Explicit solar magnitude 0.274 km/s²; no gravity profile is supplied. |
| Radiative `gamma`, `tau` | Existing model settings, with disclosed provenance. The effective `rho*cs²/P` diagnostic is not substituted for Cp/Cv, and no relaxation-time profile exists. |

All seven models receive shared inputs from this same state: 3D MAG, Alfvén,
separate Slow and Fast, Bunte 1993, MT1982, and MT1981. Different relations retain
their own physics and genuinely model-specific inputs. Point sampling and the
existing height-interval integration use matching physical heights; derivatives
are formed before averaging. One set of averaged coefficients remains a locally
uniform approximation rather than a full stratified wave-equation solution.

## Magnetic normalization and independent verification

The CO5BOLD raw `bb*` arrays use `B/sqrt(4pi)`. The server labels them `G`, but
the [original CO5BOLD MHD manual](https://www.astro.uu.se/~bf/co5bold/2_2Magnetohydrodynamics_W_S.html)
specifies conversion back to physical gauss by `sqrt(4pi)`. Independently measured
mean vertical components are 2.820948, 14.104739, and 28.209479 for the nominal
10, 50, and 100 G simulations, confirming this normalization.

The loader explicitly applies the configured internal convention to cubes
identified as CO5BOLD. An explicit `magnetic_field_convention='physical'` source
attribute overrides it for already converted exports. Generic physical-G sources
retain their declared units.

Native staggered fields and density were retrieved at layer 90 for horizontal
100 G and vertical 100 G snapshots. Face components were centred, physical local
`|B|/sqrt(mu0 rho)` was calculated, and the complete plane was averaged:

| Snapshot | Independently calculated km/s | Supplied profile km/s | Relative difference |
|---|---:|---:|---:|
| Horizontal 100 G | 22.2201264108 | 22.220125 | 6.35e-8 |
| Vertical 100 G | 32.3939099952 | 32.393910 | 1.47e-10 |

These checks explain why the native speed profile must not be replaced by the
speed of independently averaged magnetic/density profiles. No fitted scaling
factor was introduced.

## Validation and metadata

- Seven real configurations, 120 native density heights each, 105 distinct
  height pairs, and 735 model initialization checks passed.
- An independent SI implementation uses local quadratic fits rather than the
  loader's gradient routine. Maximum absolute `N²` discrepancy is below
  `2.4e-16 s^-2`. Cutoffs, sound speeds, native Alfvén speeds, pressure checks,
  and the three vertical-field fluxes also pass their independent comparisons.
- Pressure-derived hydrostatic acceleration departs from the imposed solar
  value in these dynamic snapshots. The median fractional departure over the
  full native profile ranges from approximately −4.1% to −0.5% across models;
  local departures are recorded in the audit. Equation (4) remains the selected
  reference-model definition, with its hydrostatic-background assumption
  explicitly recorded. Pressure-gradient buoyancy is retained as a diagnostic.
- Targeted regressions cover native derivatives, signed instability, native
  Alfvén sourcing, hydrostatic limiting behavior, magnetic normalization,
  cross-model initializations, cache invalidation, legacy metadata refresh,
  and rejection of mismatched native heights: **63 focused tests passed**.
- Combined dispersion/Bokeh/profile suite: **92 passed, 1 failed**. The failure
  is the existing demo-notebook test requiring every execution count to be
  empty; the demo contains an execution count of 1. It also failed before this
  parameter change. No unrelated notebook state was cleared to conceal it.
- The notebook profile diagnostic was regenerated with the corrected state.
  Spectral arrays and source simulation/profile files were not modified.

Algorithm provenance is now version 3, while the portable atmospheric schema
remains version 2. Older coarse-density records are refreshed from their exact
sources. Native profile file additions/changes invalidate the cache. Current
embedded exports remain usable without access to their original local files.

Modified source: `atmospheric_profiles.py`, the atmospheric unit/convention
settings in `config.py`, the notebook's displayed diagnostic output,
`audit_dispersion_atmospheres.py`, and the native-profile regression checks
now consolidated in `Code/Tests/test_atmospheric_profiles.py`.

Evidence: `DISPERSION_ATMOSPHERE_AUDIT.json`,
`Code/Tests/validation/native_alfven_profile_checks.json`, and
`Code/Tests/validation/native_dispersion_profiles_2026-10-15.log`.
