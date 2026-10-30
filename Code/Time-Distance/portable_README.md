# Using the HTML and Bokeh tools

1. Extract this entire ZIP into a writable folder. Keep its files together.
2. Obtain a copy of the full project **Data** directory separately. The source
   Data tree is hundreds of GB and is not included in this tools ZIP.
3. Double-click **Start Tools.command** (macOS) or **Start Tools.bat** (Windows).
   On Linux run `sh 'Start Tools.sh'`.
4. At first launch, answer **y** to **Allow environment setup?**. Setup creates
   a private environment in this tools folder and installs the required libraries.
   If a usable Python 3.10 or 3.11 is not available, it first asks permission to
   download Python 3.11 and the uv setup utility from Astral. Libraries come from
   PyPI. Internet access is needed for these downloads. Answering **n** or pressing
   Enter cancels setup. Your other Python environments and system settings are
   unchanged; administrator access is unnecessary.
5. In the browser, enter the full path to your **Data** directory, containing
   `co5bold`, `simulations`, `observations`, etc. The choice is saved for all pages.
   Opening any bundled HTML page also checks this setup.
6. Keep the launcher window open while using Bokeh. Subsequent starts reuse the
   saved directory and environment. Press Ctrl+C in that window to stop the tools.

Static figures can be viewed without the launcher. Python-backed Bokeh controls
require it; browsers cannot start Python merely by opening an HTML file.
The server binds only to this computer and uses its own available port.
Use “Change Data directory” on the package index to update a moved Data folder.
Settings, exports, Python, libraries, and setup caches live inside `.local` in
this package. An existing compatible Python is reused as the environment's base;
it is never modified. New library requirements prompt for setup again.
The selected Data directory is used for original inputs and native data products.

Transfer Data as actual files, preserving relative folders. Project Data contains
symbolic links: a transfer that leaves links pointing back at the author's Mac
will not provide the linked data. `portable-manifest.json` lists required source
files and their byte sizes. Setup reports missing or differently sized sources;
this check does not establish checksum equality.

The observing cubes are kept in Data/observations_raw. If a build still finds
dependencies outside Data, `additional_data` in the manifest records their source
and expected relative paths. Those files must accompany the transferred Data tree.
Existing absent historical phase exports can be rebuilt from their exact recorded
inputs; another dataset is never silently substituted.

The ZIP contains the existing dispersion solver source, so a separate Vesa_2026
checkout is unnecessary. Python is downloaded on demand rather than bundled.
macOS, Linux, and Windows launchers are supplied; validation platforms are recorded
separately. If a download is interrupted, run Start Tools again to retry setup.
