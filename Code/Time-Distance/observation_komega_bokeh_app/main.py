'''
Purpose
-------
Parse session options and construct the observation/simulation filter-registry
workspace.

Inputs
------
None

Outputs
-------
None
    Reads script options and optional launch context, then populates curdoc(); supported
    launch errors become escaped document messages.

Notes
-----
Serve the observation/simulation filtering and parameter-registry page.
'''
# Import the libraries and shared helpers used by this module
import argparse
from pathlib import Path
import sys
from bokeh.io import curdoc

# Resolve sibling modules before importing the application builder
MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
from observation_komega_explorer import build_document
from gaussian_filter_explorer import CONFIG_FILE
from observation_filter_registry import DEFAULT_REGISTRY
from komega_bokeh_context import request_context
from bokeh.models import Div
from html import escape

# Parse the Bokeh script options for this session
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, default=CONFIG_FILE)
parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
parser.add_argument('--data-root', type=Path, action='append', help='Repeat to search several FITS product directories.')
parser.add_argument('--raw-root', type=Path, action='append', help='Repeat to discover original observation cube pairs.')
args = parser.parse_args()
# Build the selected session workspace and report explicit launch failures
try:
    build_document(curdoc(), config_file=args.config, registry_file=args.registry,
                   product_roots=args.data_root, raw_roots=args.raw_root,
                   launch_context=request_context(curdoc()))
except (ValueError, KeyError, OSError) as exc:
    curdoc().add_root(Div(text=f'<h2>Could not open the selected k–ω plot</h2><p>{escape(str(exc))}</p>'))
