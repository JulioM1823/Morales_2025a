'''
Purpose
-------
Parse session launch options and construct the integrated dataset/model/filter
workspace.

Inputs
------
None

Outputs
-------
None
    Reads server script arguments and optional launch/result request context, validates
    portable Data settings, and populates curdoc(). Errors are logged and displayed in
    an escaped error root.

Notes
-----
One dataset/model/filter workspace, with server-side saves and exports.
'''
# Import the libraries and shared helpers used by this module
import argparse
from html import escape
import logging
from pathlib import Path
import sys

from bokeh.io import curdoc
from bokeh.models import Div

# Resolve sibling modules before importing the application builder
MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from gaussian_filter_explorer import CONFIG_FILE
from integrated_komega_explorer import build_document
from komega_bokeh_context import request_context
from komega_plot_export import DEFAULT_EXPORT_DIR
from observation_filter_registry import DEFAULT_REGISTRY
from processing_results import DEFAULT_RESULT_CACHE, request_result

# Parse the Bokeh script options for this session
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, default=CONFIG_FILE)
parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
parser.add_argument('--data-root', type=Path, action='append')
parser.add_argument('--raw-root', type=Path, action='append')
parser.add_argument('--export-dir', type=Path, default=DEFAULT_EXPORT_DIR)
parser.add_argument('--result-cache', type=Path, default=DEFAULT_RESULT_CACHE)
parser.add_argument('--simulation-root', type=Path, action='append')
args = parser.parse_args()
# Build the selected session workspace and report explicit launch failures
try:
    from portable_paths import require_data_directory
    require_data_directory()
    build_document(curdoc(), config_file=args.config, registry_file=args.registry,
        product_roots=args.data_root, raw_roots=args.raw_root, export_dir=args.export_dir,
        launch_context=request_context(curdoc()), input_observation=request_result(curdoc(), args.result_cache))
except Exception as exc:
    logging.getLogger(__name__).exception('Could not open the k–ω workspace')
    curdoc().add_root(Div(text=f'<h2>Could not open the k–ω workspace</h2><p>{escape(str(exc))}</p>'))
