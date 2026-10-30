# Bokeh model and solution switching repair

Implemented 2026-10-25; final verification completed 2026-10-26.

Live reproduction emitted `Dropping a patch because it contains a previously known reference` for removed solution plots. Document-ready callback arguments were serialized to BokehJS but not included in the Python document's model registry. Switching plots could therefore detach sources or resend definitions for objects the browser already knew. The previous Python-only replay did not retain document-level callback arguments and missed this distinction.

The application root now retains the native model layouts and document-ready callback references through an inert CustomJS reference registry. It creates no hidden layout views. Selecting a cached solution republishes its complete owned RGBA raster after mounting that branch; raw and filtered views retain their native scalar arrays, coherence visibility and solver results. No solver equations, branch tracking, phase calculations or filtering definitions were changed.

Validation:

- Three new focused tests passed. The original source failed the callback-registration test, raster-republication test and retained-source test.
- The broader integrated, coherence, visibility, layout and responsiveness suite passed 83 tests, with one saved-megaplot discovery test deselected. See `regressions.log` and `focused.log`.
- All seven model selectors and their solution controls were exercised in a real browser. A final 64 x 96 native-grid deterministic Fourier fixture verified repeated solution returns visually. The corrected browser session and server log contained no dropped-reference or duplicate-reference errors. The two Choices deprecation notices are unrelated.
- The source, extracted portable folder and two corresponding ZIP entries are byte-identical. The ZIP retains 18,575 unique entries. All other compressed local records were preserved, and the published SHA-256 was verified. The previous archive is retained beside it as `Morales-Tools.before-model-switch-fix-20261025.zip`.
- The main service and portable status endpoint returned healthy responses. Reloading the main service exposed unreadable cloud-backed files in its previous Python environment; the service now uses the existing tested portable environment (Bokeh 3.2.2, NumPy 1.24.3). The original login-service plist was backed up in `Code/Time-Distance/.komega_service/service-before-model-switch-fix.plist`.

The separate saved `hx_100g_v3_440km_660km_komega.fits` check could not complete because the cloud-backed filesystem returned `Resource deadlock avoided`. The attached browser image uses controlled Fourier test data, not that simulation. No scientific input files were replaced to bypass this limitation.
