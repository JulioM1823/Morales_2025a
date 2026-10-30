# Comparison HTML → combined Bokeh tool

Every subplot hotspot opens its own individual figure HTML file. Native image
exports are preserved; a missing historical image is recovered as the exact
megaplot crop. Every k–ω figure has one **Open in Bokeh** button.

The installed macOS launchd service (`com.juliomorales.morales2025a.komega`)
automatically starts and supervises the loopback-only server on port 5013. The
local `bokeh-launch.html` bridge polls `/health` and forwards the unchanged,
encoded context to `/integrated_komega_bokeh_app` when ready. File URLs are
supported through the health endpoint's restricted `Origin: null` CORS response.
The server does not expose the application outside the local computer. On another
checkout, install the service once using the scientific Python environment:

```sh
../Vesa_2026/.venv/bin/python Code/Time-Distance/manage_komega_service.py install
```

`komega_bokeh_context.py` validates schema-1 legacy and schema-2 atmospheric
contexts, dataset IDs and numerical paths. The combined document selects the
exact FITS and initially displays `nc2009` (3D MAG). New simulation contexts embed
height-integrated snapshot inputs and provenance for all seven models; switching
models or resetting retains that height pair's defaults. Observations supply no
simulation overrides. Legacy schema-1 records retain their previous layer-mean
behavior. Missing inputs have explicit fallback provenance; inconsistent height
metadata cannot produce an enabled atmospheric launch.

Original cube and physical preprocessing references are published alongside
numerical products as `.inputs.json`. Existing HTML links keep their dataset IDs;
the loader restores the appropriate unfiltered/post-Magnetogram cube baseline
and recalculates Gaussian results through the native pipeline. Existing HTML
templates therefore need no per-file patch or changed launch URL for this fix.
See `FILTER_RECALCULATION_REPORT.md` for numerical validation.

Notebook save hooks publish standalone `.bokeh.json` and megaplot
`.subplots.json` records for field-strength, field-orientation, simulation Gaussian
and observational Gaussian comparisons. Navigation records now cover every
individual Matplotlib data axis. `comparison_gallery.py` owns the shared
individual-page template and bridge used by all three galleries. Existing image
zoom, labels, hover and drag behavior remain.

`regenerate_html_figures.py` restores the existing historical records and calls
the same gallery generator. It verifies shortened Gaussian filenames against
their original SHA-1 digest using saved filter metadata; it does not guess column
order. Gaussian panels use their exact saved filtered FITS. Unfiltered numerical
products absent from disk are recovered using the existing native raw-Dopplergram
loader and FFT, persisted under `komega_contexts/bokeh_datasets`. Gaussian-only
products can supply the same cube's saved atmosphere metadata independently of
that FFT. Original images and scientific products are never overwritten.

```sh
../Vesa_2026/.venv/bin/python Code/Time-Distance/regenerate_html_figures.py --check-only
../Vesa_2026/.venv/bin/python Code/Time-Distance/regenerate_html_figures.py
../Vesa_2026/.venv/bin/python Code/Time-Distance/regenerate_html_figures.py --refresh-atmosphere
```

The atmospheric refresh updates all current simulation contexts without
repeating FFTs, regenerates the requested HTML Figures output and any existing
figure-root galleries, and writes matching FITS `.atmosphere.json` sidecars.
It also refreshes saved simulation catalog products omitted from the galleries.
For legacy FITS lacking height metadata, canonical filename heights are accepted
only when they identify one unambiguous layer pair in the original cube; this
fallback and the matched coordinate convention are recorded explicitly.
The unit checks, averaging and physical approximations are documented in
`Code/Time-Distance/ATMOSPHERIC_PROFILES_INTEGRATION.md`.

Legacy exports without recoverable numerical context retain an explicitly
disabled button instead of opening an unrelated dataset. All 60 current
simulation megaplots have verified numerical sources; their raw cubes are in
`/Users/juliomorales/Library/CloudStorage/GoogleDrive-juliomorales1823@gmail.com/My Drive/Graduate School/Research/Projects/Helioseismology/Morales_2025a/Data/co5bold`.

Tests cover the source notebook hooks, all three gallery types, individual file
links, exact data/context handoff, observations, multiple simulation averages,
zero magnetic field, original sampling, invalid contexts and native numerical
callbacks. Browser checks exercise navigation and launches through a loopback
HTTP preview, responsive layout, dropdown closing, path labels, sampling
disclosure, and curve controls. Relative file targets and the `Origin: null`
health response are audited separately. The browser automation tool blocks
`file://` navigation; the user confirmed that direct Finder opening of the
field-strength gallery and its Open in Bokeh button automatically opens the
correct dataset.
