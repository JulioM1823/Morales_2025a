'''
Purpose
-------
Construct the combined filter/dispersion workspace from an optional figure-launch
context.

Inputs
------
None

Outputs
-------
None
    Adds the workspace to curdoc(), or displays an escaped launch-context error for
    supported input failures.

Notes
-----
Launch the combined filter/dispersion workspace with ``bokeh serve``.
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
from komega_bokeh_context import request_context
from bokeh.models import Div
from html import escape

# Build the selected session workspace and report explicit launch failures
try:
    build_document(curdoc(), launch_context=request_context(curdoc()))
except (ValueError, KeyError, OSError) as exc:
    curdoc().add_root(Div(text=f'<h2>Could not open the selected k–ω plot</h2><p>{escape(str(exc))}</p>'))
