# Open in Bokeh repair — 2026-10-27

The local service repeatedly exited before serving `/health` because Bokeh's
`DirectoryHandler` could not read the cloud-backed application `__init__.py`:
`OSError: [Errno 11] Resource deadlock avoided`. The installed launchd service had
attempted 1,402 starts when inspected. The marker contains only a docstring.

`serve_komega_tools.py` now uses `ScriptHandler` for the two existing `main.py`
entrypoints. The four integrated-workspace URL aliases share one application;
the magnetogram URL retains its own application. There are no directory hooks,
templates, themes, or static assets in these application directories. Required
entrypoint failures still propagate. The integrated entrypoint also logs the
traceback when workspace construction fails.

The actual figure button subsequently exposed a separate Google Drive data-read
failure. Finder's Download Now restored the exact 50 G numerical product and its
60-file numerical/metadata folder; this changed local availability rather than
the saved scientific contents. The restored phase FITS array is 120 × 241, with
30 s cadence and 0.16000000000000014 Mm pixel scale. Its SHA-256 is
`875c386f2985fc80066303f8c50e6b5dc65963471a5e8c86cd410ae369a454e4`.

Validation:

- The new startup regression reproduces the former EDEADLK failure and verifies
  all five routes, script filenames, argument forwarding, and error propagation.
- The production Python environment passed 13 focused startup/HTML-context tests
  (3 gallery parametrizations deselected), in 12.91 s.
- Standalone loading from the original recorded cube completed in 21.91 s.
- The existing launchd service was restarted with the repaired source.
- Safari followed the unchanged original figure's Open in Bokeh button to port
  5013 and selected `hx_50g_v3_0km_440km_komega.fits`. A fresh session displayed
  populated simulated phase-difference and filtered-result plots and enabled
  Gaussian controls. No alternate dataset was substituted.

The tested figure is
`Morales_2025a et al/Figures/simulations/v3/Annulus/HTML/misc_files/comparison_views/h0_vs_h2/individual_figures/039b3dac5940e42c909b5f0e.html`.
Other cloud-only datasets were not exhaustively downloaded or browser-tested.
An unavailable derived Gaussian cache was rebuilt by the existing pipeline;
scientific calculation and filtering code were not changed. The portable ZIP
was not rebuilt as part of this local-service repair.
