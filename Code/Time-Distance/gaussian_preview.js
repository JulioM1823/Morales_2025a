// Purpose
// -------
// Preview the Gaussian filter in one browser animation frame without a Python solve.
//
// Inputs
// ------
// Bokeh CustomJS arguments: grid, sliders, image, hover, mapper, and error models.
// The grid supplies kh in Mm^-1, frequency in mHz, passbands, reflected-bin indices,
// and positive-frequency row indices; centers and FWHM widths use matching units.
//
// Outputs
// -------
// Coalesce repeated edits, replace the image/hover sources, and update color limits.
// Display validation errors while retaining the previous successful image.

// One animation frame uses the latest slider values, independently of Python.
if (image._gaussian_frame != null) return;
// Reuse the newest slider values when the single queued frame begins
image._gaussian_frame = requestAnimationFrame(() => {
    image._gaussian_frame = null;
    const started = performance.now();
    try {
        // Read the current filter grid and return when no grid has been supplied
        const data = grid.data;
        if (!data.kh.length) return;
        const kh = data.kh[0], frequency = data.frequency[0];
        const passband = data.passband[0], suppressor = data.suppressor[0];
        const reflected = data.reflected[0], positive = data.positive[0];
        const nk = kh.length, nt = frequency.length, ny = positive.length;
        const ck = sliders.central_k.value, wk = sliders.width_k.value;
        const cf = sliders.central_f.value, wf = sliders.width_f.value;
        // Reject nonfinite centers or nonpositive widths before changing the preview
        if (![ck, wk, cf, wf].every(Number.isFinite) || ck < 0 || cf < 0 || wk <= 0 || wf <= 0)
            throw new Error('Gaussian centers must be nonnegative and widths positive and finite.');
        // Convert FWHM to Gaussian sigma and include both frequency signs
        const fsig = wf / 2.355, ksig = wk / 2.355;
        const envelope = Float64Array.from(frequency, f =>
            Math.exp(-((f - cf) ** 2) / (2 * fsig ** 2)) +
            Math.exp(-((f + cf) ** 2) / (2 * fsig ** 2)));
        const values = new Float64Array(nk * ny), profile = new Float64Array(nt);
        let maximum = 0;
        // Apply radial weights and the existing passband/suppressor at each kh
        for (let k = 0; k < nk; k++) {
            const weight = Math.exp(-((kh[k] - ck) ** 2) / (2 * ksig ** 2));
            let peak = 0;
            for (let f = 0; f < nt; f++) {
                profile[f] = passband[k * nt + f] * (suppressor[f] * envelope[f] * weight);
                peak = Math.max(peak, profile[f]);
            }
            // Normalize only profiles whose peak transmission exceeds unity
            if (peak > 1) for (let f = 0; f < nt; f++) profile[f] /= peak;
            // Average reflected frequency bins into the positive-frequency image
            for (let y = 0; y < ny; y++) {
                const f = positive[y];
                const value = .5 * (profile[f] + profile[reflected[f]]);
                values[y * nk + k] = value;
                maximum = Math.max(maximum, value);
            }
        }
        // Purpose: map uniformly sampled centers to image-edge bounds.
        // Inputs: one nonempty numeric axis; Outputs: [lower edge, upper edge].
        const limits = axis => {
            const step = axis.length > 1 ? axis[1] - axis[0] : 1;
            return [axis[0] - .5 * step, axis[axis.length - 1] + .5 * step];
        };
        const nu = Float64Array.from(positive, f => frequency[f]);
        const [x0, x1] = limits(kh), [y0, y1] = limits(nu);
        // Publish the raster with its physical image bounds and two-dimensional shape
        const {ndarray} = Bokeh.require('core/util/ndarray');
        image.data = {image: [ndarray(values, {shape: [ny, nk]})],
            x: [x0], y: [y0], dw: [x1 - x0], dh: [y1 - y0]};
        // Rebuild flattened hover coordinates only when the grid object changes
        if (image._gaussian_grid !== data) {
            image._gaussian_grid = data;
            image._gaussian_kh = Float64Array.from(values, (_, i) => kh[i % nk]);
            image._gaussian_nu = Float64Array.from(values, (_, i) => nu[Math.floor(i / nk)]);
        }
        // Publish matching hover values, color limits, and elapsed browser time
        hover.data = {kh: image._gaussian_kh, nu: image._gaussian_nu, transmission: values};
        mapper.low = 0;
        mapper.high = Math.max(maximum, 1e-12);
        error.visible = false;
        image._gaussian_elapsed_ms = performance.now() - started;
    // Report failed edits without replacing the last successful raster
    } catch (exc) {
        error.text = String(exc.message || exc);
        error.visible = true;
    }
});
