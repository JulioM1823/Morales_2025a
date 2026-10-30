# Filtering and k–ω recalculation investigation

## Calculation path before changes

- `AGWFilter.load_dopplergrams` in `filter.py` loads paired observed cubes or two selected NetCDF height slices into `[t,y,x]` arrays.
- `magnetogram_workflow.prepare_dataset` caches these original arrays and aligned magnetic maps. `compute_result` constructs separate threshold masks with `compute_magnetogram_filter_masks`, applies them in physical space with `apply_magnetogram_filter`, and calls `TimeDistance.compute_komega_diagram`. This path already uses the correct domain and recalculation order. Its persistent result supplies both masked cubes to the Gaussian tool.
- Batch `AGWFilter.apply_gaussian_filter` transposes each cube to `[x,y,t]`, constructs a full signed 3-D Gaussian/Bartlett transfer, invokes `filter_data` independently for both cubes, and transposes back. `filter_data` performs an FFT, transfer multiplication and inverse FFT. The caller previously took `.real` without checking residuals.
- The interactive `ObservationKomegaExplorer._refresh_preview` and integrated `DatasetPair._refresh_preview` instead multiply the saved **phase in degrees** by a two-dimensional diagram filter. They neither filter the cubes nor recalculate the cross-spectrum. Raw-pair loading previously discarded its loaded cubes, while saved phase FITS generally carried no cube references. This confirms the suspected error for the interactive Gaussian dataset view; an absent inverse FFT is not the batch/Magnetogram diagnosis.
- The native diagnostic resolves lower/higher ordering and observational line delay, transposes to `[y,x,t]`, subtracts each global mean, performs NumPy's default-normalized all-axis FFT with `fftshift`, forms `F_lower * conjugate(F_higher)`, takes phase **before** native rounded-radius azimuthal averaging, retains the existing nonnegative frequency bins, and adds the configured delay correction. It applies no extra window/detrend. The running-difference coherence routine is a separate diagnostic and must not replace this definition.
- The model panels weight theoretical phase/kz fields for display. Those arrays are theoretical solutions, not Dopplergram cross-spectra; this distinction must remain explicit.

## Initial measured defects

An identity Fourier transfer reconstructs the original cube to approximately 2.3e-15 maximum absolute error in small double-precision probes. A rectangular `[10,8,24]` input fails in the native transfer builder because it assigns `[j,i]` rather than `[i,j]`. The builder also reuses a frequency work array between spatial bins. Even-length transfers need an explicit Hermitian check: the low-frequency suppressor is centred between indices, whereas FFT zero frequency is an integer index. Residual measurements, corrections and numerical/browser acceptance results are recorded below.

## Corrected data flow

`original cubes -> native spatial Magnetogram masks (when selected) -> independent full 3-D Gaussian Fourier transfers -> checked inverse FFTs -> original TimeDistance.compute_komega_diagram -> Bokeh image and hover sources`.

The immutable Magnetogram result supplies the two already masked cubes and its analysis runtime. Gaussian adjustments start from these supplied arrays every time; the spatial mask is not applied twice. Direct observed/simulation products recover their original cubes through generated `.inputs.json` references. Historical Gaussian processing is removed from the new baseline, while recorded Magnetogram processing is retained. An explicitly configured Gaussian-before-Magnetogram sequence is also preserved by using the original raw pair and the existing native ordered `apply_filters` routine.

`dopplergram_recalculation.py` centralizes source references, source-version caching, native baseline construction and recalculation. It delegates all filtering mathematics to `AGWFilter` and all phase calculation to `TimeDistance`. No new cross-spectrum, azimuthal average, normalization, phase convention or interpolation algorithm was introduced. The physical cubes retain their dimensions, coordinate sampling and source units; the filter transfer is dimensionless. Existing coordinate/WCS validation is reused from the Magnetogram workflow. Incompatible sampling edits are rejected instead of silently resizing data.

Each comparison dataset constructs its own 3-D transfer using its own cube geometry and sampling, with the shared four Gaussian settings. Both cubes within a dataset must already be aligned and have matching shapes. Original negative-frequency, FFT shift/normalization, mean subtraction, phase-order/delay and positive-frequency reduction conventions are retained. Phase colors remain −80 to +80 degrees.

## Fourier transfer corrections

1. Clear the frequency work profile for every spatial Fourier cell; previous k-bin state no longer leaks into a later bin.
2. Assign `[i,j,:]` in the declared `[x,y,t]` order, including rectangular grids.
3. Explicitly form the Hermitian symmetric real transfer `G_H(k) = [G(k) + G(-k)]/2` using FFT conjugate indices, including self-conjugate bins. The Gaussian envelope, FWHM conversion, Bartlett/raised-cosine construction, low-frequency suppressor, f-mode/Lamb/cap boundaries and conditional normalization remain the same formulations. The 2-D filter visualization uses the same frequency symmetry.
4. Check finite input/output and inverse-transform imaginary residuals before extracting a real cube. The tolerance is `max(1e-12, 1e-10 * max(abs(real)))` in source units. Significant residuals and NaN-filled Dopplergrams produce explicit errors; no implicit imputation is performed.
5. Recognize an exact identity transfer and return an exact copy, avoiding needless roundoff in undefined zero-power phase bins.

In the `[32,32,482]` probe, the old imaginary/real L2 ratio was **0.0807336720**. The corrected ratio is **4.44e-16**. Projecting the old transfer alone reproduces the former `.real` result within **5.55e-17** maximum absolute error, demonstrating that this symmetry operation makes the old implicit real projection explicit. The independent work-array/index corrections are substantive bug fixes: the corrected transfer differs from the projected old transfer by up to **0.4219444** in that probe. Old Gaussian results are therefore not falsely claimed to be numerically unchanged. Filter caches and newly saved algorithm provenance use `agw_create_filter_bartlett_gaussian_hermitian_v2`; legacy approved parameter values remain readable.

## Provenance, compatibility and performance

Future pipeline saves and HTML context publication automatically write cube references beside numerical FITS products. Existing HTML links and dataset IDs remain unchanged; no generated HTML was patched. The metadata migration uses the existing numerical catalog and saved megaplot metadata, with validated canonical-name fallback only where older metadata is absent. The relocated original observed files are discovered under the existing Vesa_2026 Data directory when the configured Vesa_2025 root is missing. Explicit caller roots retain precedence.

The completed catalog audit found **1,540 numerical products**. Source companions are present for **1,197**: **874 simulation products** and **323 observed pairs**, referencing **26 original source files**. The other **343 products** use AIA/CIV intensity inputs outside the existing Dopplergram eligibility rules; they remain viewable as saved diagrams and explicitly refuse cube filtering without supported provenance. This pass did not reinterpret intensity as Doppler velocity. Existing HTML does not need regeneration to use the new loader; the migrated companions and updated application provide the corrected workflow.

Three archival 25 April products lacked complete preprocessing metadata. Their native generator tags and original zero-fill default were checked against the actual saved diagrams using the pre-correction native Gaussian implementation. All three agree in **479 well-transmitted cells**, with maximum phase error **4.7151e-7 degrees** and RMS **1.3345e-7 degrees**. Their recovered input references record this evidence and its limits. Full-map differences reach 169.43 degrees outside the passband, where phase is numerically undefined after signal suppression; those cells were not used to infer the settings. This is numerical identification of a consistent configuration, not a claim that a phase-only map uniquely determines every possible original amplitude field.

Original cube pairs and baseline diagnostics are cached by scientific reference and source filesystem versions, with a bounded two-entry cache. Native persistent transfer caches are reused by shape/sampling/parameters/version. Gaussian reconstruction and diagnostic calculations run on a single worker outside the Bokeh document thread. Obsolete queued work is cancelled; generation, dataset identity and current parameter checks reject stale running completions. Pending result/hover arrays are cleared. Model changes do not trigger unrelated data FFTs. The existing model panels remain Gaussian-weighted theoretical displays, explicitly labeled; they are not Dopplergram recalculations.

The transparent implementation deliberately retains inverse reconstruction followed by the original native analysis. No unproven Fourier-domain shortcut was installed. Measured full-size filtering/recalculation times were **4.395 s** for observed cubes and **8.675 s** for simulation cubes. Disk loading is cached separately; these timings include the numerical filtering and native diagnostic, not just UI rendering.

## Numerical acceptance results

| Check | Result |
| --- | --- |
| No filtering vs native original diagnostic | Exact array equality, observed and simulated |
| Identity transfer vs original cubes and diagnostic | Exact equality through the public filtering/recalculation route |
| Independent NumPy FFT/IFFT reconstruction | Agreement at rtol 1e-12 / atol 1e-14 for even, odd and rectangular grids |
| Gaussian vs separate native batch filtering + native diagnostic | Exact equality of both reconstructed cubes, phase maps and axes |
| Magnetogram + Gaussian | Exact native agreement for observed and simulated fixtures; spatial masks retain their native semantics |
| Gaussian-before-Magnetogram order | Explicitly tested separately from the default forward order |
| Parameter changes and repeat settings | Baseline arrays unchanged; returning to a setting reproduces the original result exactly |
| Rapid/stale callbacks | An older completion cannot replace a newer control state |
| Phase-only inputs without cube provenance | Remain viewable; no falsely filtered diagram is produced |

Full-size independent comparisons used an observed pair of **840 × 160 × 160** samples with the original **3.26 s** line-delay correction and a simulation pair of **482 × 240 × 240** with **0 s** correction. Maximum differences in reconstructed cubes, recalculated phase, k axes and frequency axes were all **0.0**. The simulation baseline also reproduced its saved unfiltered HTML launch product exactly. Evidence is saved in `filter-recalculation-real-data-validation.json`, `filter-hermitian-validation.json` and `archival-filter-recovery-validation.json` in the validation artifact directory.

The final relevant regression run passed **148 tests in 127.34 s** across filtering/recalculation, integrated and observational explorers, atmospheric profiles, HTML/Bokeh context integration, runtime and Magnetogram workflows. All **11 changed production modules** passed Python compilation. The tests cover analytical identity reconstruction, independent FFT/IFFT calculations, rectangular/odd/even grids, significant imaginary residual rejection, both filter orders, repeated adjustments, source-version validation and stale asynchronous completions. The 2,900 emitted warnings are retained in the test log; they are not test failures.

Live browser checks followed a simulation HTML subplot through its single Bokeh launch button, changed Gaussian parameters rapidly, and confirmed native recalculation. For the observed 25 April pair, changing the Magnetogram retain mode and threshold generated a new native result; its Gaussian launch selected the supplied immutable masked pair automatically. Changing the Gaussian frequency FWHM to **3.1 mHz** updated the result. The ordinary Bokeh **Save Plot** action exported the actual rendered filtered image, which was decoded independently and compared with native filtering and analysis of the supplied cubes: **maximum absolute phase error 0.0 degrees**, image shape **420 × 80**. Both tools' parameter controls remained editable; user filter-registry values were not saved or changed during verification. No console errors were recorded in the successfully tested sessions.

An initial attempt to read the 6 May pair failed with the external filesystem error `Resource deadlock avoided`; those files had the macOS data-less cloud-placeholder flag. This is a source-availability limitation, not a successful dataset test. The available 25 April pair completed the entire observed workflow. The browser layout was checked at a large desktop viewport and at the narrow default viewport; native data plots and controls remained separate. The loopback application service remains running.

Validation artifacts are in [/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c). This includes `filter-recalculation-input-audit.json`, `filter-recalculation-live-browser-validation.json`, the numerical evidence above, and [the desktop browser capture](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/filter-recalculation-observed-gaussian-desktop.png). The final test log is [/tmp/morales-filter-final-suite.log](/tmp/morales-filter-final-suite.log).

## Source files changed in this pass

- `Code/Time-Distance/dopplergram_recalculation.py` — new shared baseline/reference/recalculation component and metadata migration.
- `Code/Time-Distance/filter.py` — transfer-builder defects, Hermitian symmetry, residual checks and cache version.
- `Code/Time-Distance/pipeline.py` — input-reference publication only; native FFT/phase calculations unchanged.
- `Code/Time-Distance/gaussian_filter_explorer.py` — symmetric frequency transfer in the filter visualization.
- `Code/Time-Distance/observation_datasets.py` — retain raw cubes/runtime; restore numerical baselines; relocated observed-source discovery.
- `Code/Time-Distance/observation_komega_explorer.py` — shared background native recalculation, stale-result protection, source/sampling validation and rendered updates.
- `Code/Time-Distance/integrated_komega_explorer.py` — delegate dataset calculation, retain model-only visualization distinction, update export provenance.
- `Code/Time-Distance/magnetogram_workflow.py` — publish analysis runtime and include shared-component fingerprint; physical masks unchanged.
- `Code/Time-Distance/processing_results.py` — restore the analysis runtime for immutable supplied masked cubes.
- `Code/Time-Distance/komega_bokeh_context.py` — publish source-input companions for future HTML launches.
- `Code/Time-Distance/observation_filter_registry.py` — new algorithm/application provenance with legacy parameter-record compatibility.
- `Code/Tests/test_dopplergram_recalculation.py` — independent numerical, domain/order, identity, no-compounding and stale-callback checks.
- `Code/Tests/test_integrated_komega_explorer.py` and `Code/Tests/test_observation_komega_explorer.py` — replace phase-multiplication expectations with real cube/native-pipeline comparisons; preserve independent phase-only loading tests.
- `Code/Time-Distance/INTEGRATED_KOMEGA_BOKEH.md`, `OBSERVATION_FILTER_BOKEH.md`, `MAGNETOGRAM_FILTER_BOKEH.md`, `GAUSSIAN_FILTER_BOKEH.md`, `KOMEGA_HTML_BOKEH_INTEGRATION.md` and this report — corrected scientific workflow documentation.

No notebook, atmospheric-profile calculation, dispersion equation, raw input cube or archived numerical FITS array was rewritten in this pass.

## Remaining numerical assumptions

The native phase-before-azimuthal-average diagnostic and its existing signed-linspace coordinate contract are preserved. Phases where Fourier power is zero or negligible are undefined/roundoff-sensitive; the native routine's behavior in those cells was not silently replaced with a different estimator or an invented power threshold. Theoretical model weighting remains a display operation, separately labeled. Sources still stored only as cloud placeholders may raise filesystem errors until their numerical bytes are available; no substitute dataset or fabricated diagnostic is displayed.
