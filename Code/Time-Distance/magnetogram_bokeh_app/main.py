'''
Purpose
-------
Parse session options and construct the separate magnetogram preprocessing workspace.

Inputs
------
None

Outputs
-------
None
    Validates portable Data settings and adds the magnetogram tool to curdoc();
    construction errors become escaped error roots.

Notes
-----
Server entry point for the separate magnetogram preprocessing workspace.
'''
# Import the libraries and shared helpers used by this module
import argparse
from html import escape
from pathlib import Path
import sys

from bokeh.io import curdoc
from bokeh.models import Div

# Resolve sibling modules before importing the application builder
MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from gaussian_filter_explorer import CONFIG_FILE
from magnetogram_explorer import build_document
from processing_results import DEFAULT_RESULT_CACHE

# Parse the Bokeh script options for this session
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, default=CONFIG_FILE)
parser.add_argument('--result-cache', type=Path, default=DEFAULT_RESULT_CACHE)
parser.add_argument('--raw-root', type=Path, action='append')
parser.add_argument('--simulation-root', type=Path, action='append')
# The shared launcher passes these existing Gaussian workspace options too.
parser.add_argument('--registry', type=Path)
parser.add_argument('--export-dir', type=Path)
parser.add_argument('--data-root', type=Path, action='append')
args = parser.parse_args()
# Build the selected session workspace and report explicit launch failures
try:
    from portable_paths import require_data_directory
    require_data_directory()
    build_document(curdoc(), config_file=args.config, cache_root=args.result_cache,
                   raw_roots=args.raw_root, simulation_roots=args.simulation_root)
except Exception as exc:
    curdoc().add_root(Div(text='<h2>Could not open the magnetogram workspace</h2><p>' + escape(str(exc)) + '</p>'))
