'''
Purpose
-------
Build the combined filter/dispersion document when this Bokeh server script executes.

Inputs
------
None

Outputs
-------
None
    Adds the komega_explorer layout and callbacks to curdoc(); the sibling source
    directory is added to sys.path when required.

Notes
-----
Launch entry point used by ``bokeh serve``.
'''

# Import the libraries and shared helpers used by this module
from pathlib import Path
import sys

from bokeh.io import curdoc


# Resolve sibling modules before importing the application builder
MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from komega_explorer import build_document  # noqa: E402


# Populate the current Bokeh document using the shared workspace builder
build_document(curdoc())
