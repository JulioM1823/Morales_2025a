# Embedded spatial phase-difference analysis

## Existing calculations inspected

The available `Code/Toy-Box-Simulation/agw_simulation.ipynb` has 30 cells. Cells 15–17 calculate synthetic height-extracted x–frequency phase; cells 22–25 compare analytic complex wavefunctions on coordinates read from the horizontal-10 G simulation. They do not load a pair of simulated Dopplergram planes or produce a two-dimensional x–y frequency-band map. The example's `2*arcsin(sin(phase))` fold is not equivalent to ordinary cyclic phase wrapping and is not applied to the new spatial diagnostic. Cells 26–29 contain atmospheric-profile/WKB calculations and remain unchanged.

The existing two-height x–y spatial calculation is in `Code/Time-Distance/vorticity.ipynb`, cell 5. Cell 0 identifies the horizontal-100 G NetCDF, `v3`, `bb1`, `bb2`, `bb3`, native time and spatial axes. Cell 5 uses `vz[:,1]` and `vz[:,2]`, removes the temporal mean at each pixel, takes FFTs along time only, constructs `F1*conj(F2)`, retains strictly positive frequencies, averages the complex cross power over 0.7–3.1 mHz, and then takes its angle in degrees. Its separately calculated coherence-weighted phase is a different output, not the phase map requested here. Cell 4 displays the first magnetic snapshot; the new overlay makes the selected height explicit rather than using an unrelated global bottom layer.

The new component reproduces that existing spatial definition. It does not replace the native k–ω diagnostic, which takes phase before spatial azimuthal reduction. No notebook, native FFT/filter implementation, dispersion equation or generated HTML was rewritten for this addition.

## Navigation and inherited state

The combined application now contains **Spatial Phase-Difference Analysis**. It is inline immediately below **Dispersion Model Parameters**, with its controls and two plots arranged vertically in one column of the same Bokeh document. Independent plot/control switches replace the former launch, return, and manual refresh buttons. Existing HTML retains its single **Open in Bokeh** button and the same launch context. No HTML regeneration is needed.

The new view receives the primary `ObservationData` object, its native runtime configuration and height pair, coordinates, original-source provenance, and the current shared Gaussian state. It consumes the **actual reconstructed pair** accepted by the current native k–ω recalculation. There is no second Gaussian implementation or separate collection of Gaussian widgets. Unsaved Gaussian changes are inherited. A pending/replaced filter clears the filtered map until the current cubes are ready; stale completions cannot overwrite it. Dataset and Gaussian changes propagate automatically, including while the section is collapsed; visibility changes themselves do not trigger scientific work.

The unfiltered reference uses the original cubes before either Magnetogram or Gaussian filtering, over all strictly positive temporal FFT bins. For a Magnetogram processing result, the raw pair is restored from its recorded original sources once. The filtered map uses the supplied masked baseline and current Gaussian reconstruction, preserving the native processing order and preventing filters from accumulating. When Gaussian filtering is disabled, its disabled state is explicitly inherited. An unsupported phase-only product displays its missing-Dopplergram limitation inline.

## Mathematical definition

For each pixel, subtract the temporal mean and compute the temporal transform. The existing native runtime resolves the lower/higher atmospheric order. The spatial map is

`arg(mean(F_lower(x,y,ν) * conjugate(F_higher(x,y,ν)), selected positive ν bins))`, in degrees.

Observed pairs also inherit the existing line-delay value. Their complex cross power is rotated by `exp(+2πi ν τ)` at each physical FFT frequency **before** complex band averaging. Simulations have zero line-delay correction. The same lower/higher order and correction sign are used by the native pipeline; no arbitrary observational formation heights are invented.

The real-input rFFT is restricted to exactly the bins that `fftfreq(nt,dt)>0` selects. DC and the even-length Nyquist bin are excluded. This is a subset optimization of the notebook's FFT, numerically tested for even and odd lengths. No padding, synthetic frequency interpolation, extra window, detrending or phase-angle average is added. A cumulative complex sum permits exact-bin band reductions without repeating FFTs. Bounds outside the measured positive-frequency domain and intervals containing no bins produce explicit errors. Inclusive bin boundaries tolerate only 16 floating-point epsilons times the frequency scale, so equivalent JavaScript slider and NumPy FFT values do not accidentally exclude a boundary bin. This is roundoff handling, not frequency interpolation or a fraction-bin tolerance.

The dual-ended slider displays mHz. Initial bounds are 0.7–3.1 mHz clipped to the available grid; if that interval has no bin, the available positive band is used. Status and saved metadata report requested bounds, actual included first/last frequencies and bin count. Both plots now use the same **CMasher fusion palette and fixed −80° to +80° display limits as the k–ω dataset diagrams**, with shared Times New Roman typography, inward ticks, white background, black frame and matching degree colorbars. This replaces the initial twilight display. Wrapped phase values remain unchanged, including values outside the display limits; hover and numerical exports retain them. Native coordinates, linked pan/zoom ranges and physical data-frame aspect ratio are preserved.

## Magnetic contours

`Bh = hypot(Bx,By)`, in gauss. The native pipeline's inclination from +z is folded by `min(theta,180°−theta)` to a polarity-free 0°–90° angle, equivalent to `atan2(Bh,abs(Bz))` wherever the field is nonzero. Zero field has undefined inclination and is excluded.

The selection is the logical intersection of finite `Bh >= threshold_G` and `theta >= threshold_deg`, initially **10 G** and **45°**. The current default contours show broader regional trends: Gaussian smoothing of that unchanged Boolean selection with **σ = 0.8 Mm**, followed by the **15% neighborhood-coverage contour**. The Gaussian widths are converted independently using the native x/y pixel scales. The new **Contour smoothing σ [Mm]** control changes only the displayed outlines; setting it to zero restores the original 0.5 boundary of the raw selection. A compact note explains that regional outlines can enclose neighboring pixels outside the original pointwise selection. A thin black contour over a white stroke is shared by both plots, clipped to the native image domain. No field component, threshold criterion, Dopplergram, phase array or wave-filter setting is changed by contour smoothing.

Vector components are read from the **same simulation file**, first temporal snapshot, at the **lower member of the selected height pair**. Native axis inference selects and orients only that plane; explicit G/gauss or T units are validated and converted. Native x/y coordinates and registration are checked without resampling. The height index, physical height, frame and interpretation are displayed and exported. This is an instantaneous diagnostic overlay on a time-series phase map, not a temporal average of magnetic geometry.

Observed source pairs currently provide LOS magnetograms rather than registered vector components. Their phase maps work, but horizontal-field/inclination controls are disabled with an explicit explanation. Missing/invalid component units never silently acquire gauss units. A simulation is treated as known zero field only when its existing source metadata identifies it as such.

## Callbacks, caching and outputs

- Dataset changes rebuild the raw temporal cache and magnetic snapshot; previous pending work is invalidated.
- Frequency changes reduce the filtered temporal cache and refresh only the filtered phase image.
- Either magnetic threshold or the contour smoothing scale changes only the common contour source.
- Gaussian changes reuse the combined application's reconstructed cubes and rebuild only the filtered temporal cache; the raw reference stays unchanged.
- Native reconstruction, source restoration and cache construction run outside the Bokeh document thread. Per-stage generations and cancellation reject obsolete work.
- **Save Plot** reuses the existing paired Bokeh HTML/text export and the parent export directory. Metadata includes the source/height runtime, source versions, raw-reference definition, full and selected bands, current Gaussian state, original processing chain, magnetic snapshot and thresholds.

There is one cached raw and one current filtered cumulative cross-spectrum per spatial view. At 482×240×240 samples each is approximately 223 MB; the tool avoids storing redundant spatial-filter cubes or rebuilding the Gaussian transfer. First-time input preparation remains dependent on source availability. Frequency reductions of the tested full-size datasets took about **0.76–0.85 ms**, excluding browser transport/rendering. Constructing a filtered temporal cache took about **3.0 s**.

## Validation

The original integration regression suite passed **163 tests** in **156.02 s** across spatial functions/UI, filtering/recalculation, integrated and observation explorers, atmospheric profiles, HTML contexts, runtime, Magnetogram and Gaussian components. Its 14 dedicated spatial checks execute the existing notebook cell against independent fixtures and test phase sign, complex averaging, FFT-bin parity, unsupported intervals, inclusive boundary roundoff, magnetic polarity/units/registration, logical intersection, contour edges, stable raw reference, live Gaussian inheritance, disabled-filter state, dataset switching, exports and stale callbacks. The style/contour cleanup adds direct native k–ω sign comparisons for normal and reversed height ordering, shared mapper/font/tick/colorbar assertions, anisotropic physical smoothing and regional-contour checks; its results are recorded below.

Full-size validation used the horizontal-10 G simulation at two distinct original HTML contexts:

| Height pair [km] | Shape per cube | Raw vs notebook max phase error | Gaussian vs notebook max phase error |
| --- | --- | --- | --- |
| 0–220.000116 | 482×240×240 | 5.33e-14° | 7.82e-14° |
| 440–660.000116 | 482×240×240 | 2.66e-14° | 7.82e-14° |

Both tests used current native Gaussian settings `central_k=1.5`, `width_k=4`, `central_f=3`, `width_f=3.1`. Independent native component reads agreed with the horizontal-field calculation within **7.11e-15 G** and inclination within **4.90e-13°**. The initially selected contour area differed between heights, approximately **3.78%** and **1.77%**, verifying that the overlay does not reuse an unrelated height.

Live browser tests followed the existing HTML gallery → individual k–ω subplot → single **Open in Bokeh** → embedded spatial-view button at both height pairs. The second pair inherited an unsaved Gaussian frequency FWHM of **3.1 mHz**, with native heights **440 and 660.000116 km** and magnetic height index **2**. Both frequency-slider ends and both magnetic thresholds were exercised, including rapid changes. A source-backed diagram exceeded the former 30-second image-load deadline during testing; such products now receive the same 120-second deadline as native raw-cube loads, with a regression check and successful repeat launch.

Five ordinary **Save Plot** exports were decoded at the ColumnDataSource level. The raw full-band image was **exactly unchanged across all five**. The contour-only edit preserved **both phase arrays exactly**, while contour count changed from **173 to 0** and restored to **173**. The final frequency interval included exactly **28 measured bins**, 0.8990318119–2.7662517289 mHz. Independent execution of the notebook FFT/cross-spectrum/band-average calculation on the actual source cubes matched the final exported raw reference within **2.49e-14°** and the exported Gaussian-filtered selected-band image within **9.24e-14°**. Gaussian settings and magnetic thresholds were read from the exported metadata, not inferred visually.

The real 25 April observed Fe7090/K7699 Magnetogram processing result also opened spatial analysis successfully. Its raw full-band reference was restored from the original pair, its right image used the supplied masked/Gaussian-filtered pair, and its vector-contour controls displayed the explicit LOS-only limitation. Both successful sessions recorded **no browser console errors**. At the 1920-pixel desktop test viewport, square native grids retain square physical data frames, shared cyclic scales, registered contours, and separated controls. At 600 pixels, the sections stack with controls first and both `clientWidth` and `scrollWidth` equal **600**, confirming no horizontal overflow. Parent export-directory settings were restored after scratch exports. The permanent loopback Bokeh service remains running and passed its health check; the temporary HTML preview service was stopped after validation.

Numerical evidence: [full-size height-pair comparisons](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-phase-validation.json) and [actual browser-export comparisons](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-phase-browser-validation.json). Captures: [finished simulation view](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-phase-final-desktop.png) and [observed view](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-phase-observed-desktop.png). Final test log: [/tmp/morales-spatial-verified-regression.log](/tmp/morales-spatial-verified-regression.log).

## Files changed in this addition

- `Code/Time-Distance/spatial_phase_analysis.py` — reusable temporal cross-spectrum, exact-bin averaging, source restoration, magnetic geometry/snapshot and contour functions.
- `Code/Time-Distance/spatial_phase_explorer.py` — embedded responsive view, controls, current-state synchronization, background generation checks and export.
- `Code/Time-Distance/bokeh_ui_helpers.py` — shared native phase mapper, axes typography and colorbar style used by both k–ω and spatial plots.
- `Code/Time-Distance/integrated_komega_explorer.py` — inline layout and primary-session state binding.
- `Code/Time-Distance/observation_komega_explorer.py` — saved products with source companions receive the existing 120-second raw-cube load deadline rather than the old 30-second phase-image deadline.
- `Code/Time-Distance/requirements-observation-komega.txt` — explicit contourpy dependency, already available through Matplotlib in the scientific environment.
- `Code/Tests/test_spatial_phase_analysis.py` — independent scientific and interaction regression checks.
- `Code/Tests/test_observation_komega_explorer.py` — regression for source-backed load deadlines.
- `Code/Time-Distance/INTEGRATED_KOMEGA_BOKEH.md` and this report — navigation, mathematical definition, provenance and limitations.

## Limits

The named toy-box notebook and the actual spatial-map notebook contain different diagnostics; they are not claimed to be interchangeable. Magnetic contours use one explicitly identified snapshot and height. LOS-only observations cannot supply vector inclination. Mean-profile atmospheric defaults are not used to manufacture spatial magnetic maps. Native grids must be regular and pre-aligned; no unrequested coordinate interpolation is introduced. Phase in zero/negligible-power cells is not physically defined. Source files must be locally readable; cloud placeholders are not substituted with other datasets.

## 14 October 2026 style and contour cleanup

The phase convention was traced through `TimeDistance.resolve_phase_analysis_cube_order`, positive temporal FFTs, cross power and the native spatial reduction. The existing spatial convention already matched k–ω: `F_lower * conjugate(F_higher)`, with the native positive line-delay correction for observations. No phase-sign reversal or recalculation change was introduced. New known-wave tests populate the native nonzero spatial annuli and compare spatial phase directly with the native k–ω output; both normal and reversed atmospheric ordering agree within 1e-12 degrees.

Shared `phase_color_mapper`, `phase_color_bar` and `style_phase_plot` helpers now serve both dataset k–ω and spatial views. They retain the native k–ω palette, limits, missing-value color, fonts, tick lengths, border and colorbar formatting. Only the spatial view's formerly different display changes.

Regional contours are formed from the original Boolean magnetic intersection, not from altered magnetic-field values. At the tested horizontal-10 G simulation heights, the new default produces **342 → 19** outlines at 0–220 km and **173 → 10** at 440–660 km. The original pixel selections remain exactly unchanged. These outlines describe neighborhood coverage and may include adjacent unselected pixels; they are explicitly labeled as display smoothing. Setting **Contour smoothing σ [Mm]** to zero recovers the original pixel-level outlines. Changing that control triggers no temporal FFT, Dopplergram filtering or phase recomputation.

**85 relevant tests passed in 140.35 s**, covering spatial science/UI, the combined application, observational loading and Magnetogram workflows. This includes 18 spatial tests with native sign comparisons, shared styling assertions, physical smoothing on unequal x/y sampling, island merging, unchanged selection masks and domain-boundary checks. All four changed production Python modules passed compilation. Contour evidence is in [spatial-style-validation.json](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-style-validation.json); the regression log is [/tmp/morales-spatial-style-regression.log](/tmp/morales-spatial-style-regression.log).

The final 18-test spatial run passed again in **10.25 s** after allowing more space for the shared axis/colorbar fonts and clearing the contour note when vector data are unavailable. In the running Bokeh application, the 440–660 km simulation opened with the new fusion display and broader contours. Two ordinary Save Plot exports were decoded: both full-resolution phase arrays are **exactly equal** to the earlier integration export at the same height pair, frequency band and Gaussian settings (**maximum difference 0 degrees**). Changing contour smoothing from 0.8 Mm to zero changed **10 → 173** outlines, with both phase arrays exactly unchanged. The control was restored to 0.8 Mm, and the parent export directory was restored. Browser error logs were empty. At 1920×1080, the physical data frames are square and axes/colorbars fit without clipping; at 600 pixels, controls and plots stack and both document client width and scroll width are **600**.

Current browser evidence: [numerical export comparison](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-style-browser-validation.json), [desktop capture](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-style-final-desktop.png), [narrow capture](/Users/juliomorales/.codex/visualizations/2026/10/07/01a1146d-3adc-7011-ad1e-806c7c1b8a9c/spatial-style-narrow.png), and [final spatial test log](/tmp/morales-spatial-style-final-tests.log). The existing local service was reloaded with these source changes.

Files changed in this cleanup: `bokeh_ui_helpers.py`, `observation_komega_explorer.py`, `spatial_phase_analysis.py`, `spatial_phase_explorer.py`, `Code/Tests/test_spatial_phase_analysis.py`, and this report. Generated HTML, notebook calculations, native filtering/FFT routines and dispersion equations remain unchanged.
