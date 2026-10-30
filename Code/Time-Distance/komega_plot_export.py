'''
Purpose
-------
Export cloned Bokeh plot pairs with readable provenance and optional managed-output
registration.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for komega_plot_export.py.

Notes
-----
Export the actual Bokeh plot pair and readable, structured provenance.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

import numpy as np
from bokeh.core.serialization import Deserializer, Serializer
from bokeh.document import Document
from bokeh.embed import file_html
from bokeh.layouts import row
from bokeh.resources import INLINE

DEFAULT_EXPORT_DIR = Path(__file__).with_name('komega_exports')


def json_value(value):
    '''
    Purpose
    -------
    Convert nested numerical provenance into portable JSON-compatible values.

    Inputs
    ------
    value: object
        Numerical metadata containing dictionaries, sequences, NumPy values, or paths.

    Outputs
    -------
    value: object
        Converted dictionaries/lists/scalars/path strings with nonfinite floats replaced
        by None.

    Notes
    -----
    Convert numerical provenance to portable JSON values, never Python repr.
    '''
    # Convert nested numerical provenance into portable JSON-compatible values
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_value(item) for item in value]
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def metadata_text(metadata):
    '''
    Purpose
    -------
    Render structured provenance under readable named text headings.

    Inputs
    ------
    metadata: dict
        Export provenance sections to serialize.

    Outputs
    -------
    text: str
        Human-readable export metadata with indented valid JSON beneath each heading.
    '''

    # Render structured provenance under readable named text headings
    lines = ['K-OMEGA PLOT EXPORT', '==================', '']
    for title, content in json_value(metadata).items():
        heading = title.replace('_', ' ').title()
        lines.extend([heading, '-' * len(heading)])
        # Pretty JSON under named headings is both readable and unambiguous.
        lines.extend([json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False), ''])
    return '\n'.join(lines)


def save_plot_pair(plots, metadata, directory=DEFAULT_EXPORT_DIR, *, config=None, product="komega_diagram"):
    '''
    Purpose
    -------
    Clone two live plots and publish self-contained HTML plus matching provenance text.

    Inputs
    ------
    plots: sequence of two bokeh.models.Plot
        Selected plot pair cloned through Bokeh serialization without mutating its live
        document.
    metadata: dict
        Source identifiers, export_type, and provenance included in text/managed
        metadata.
    directory: str or pathlib.Path
        Export destination or managed figure root.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    product: str
        Managed product kind used when config is supplied.

    Outputs
    -------
    paths: tuple of pathlib.Path
        Published HTML and text files. Temporary/published files are cleaned on write
        failure; managed HTML metadata is registered when config is supplied.

    Notes
    -----
    Clone plots without touching their live document; stage both files safely.
    '''
    # Clone two live plots and publish self-contained HTML plus matching provenance text
    if len(plots) != 2:
        raise ValueError('Select two valid plots before saving.')
    metadata = dict(metadata, timestamp_utc=datetime.now(timezone.utc).isoformat())
    identity = metadata['source_1']['id']
    short_id = sha256(identity.encode()).hexdigest()[:8]
    source_2 = metadata['source_2']
    label = source_2.get('model_key', 'comparison')
    label = re.sub(r'[^a-zA-Z0-9_-]', '_', label)[:24]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    stem = f"komega_{metadata['export_type']}_{short_id}_{label}_{stamp}"
    # Serialization retains glyphs, hover, legends, ranges and mapper behavior.
    # Python/server callbacks are not needed by these frozen interactive plots.
    pair = Deserializer().decode(Serializer().encode(row(*plots)))
    for plot in pair.children:
        plot.width = plot.width or 430
        plot.height = plot.height or 470
    pair.width = sum(plot.width for plot in pair.children) + pair.spacing
    pair.height = max(plot.height for plot in pair.children)
    pair.sizing_mode = 'fixed'
    # file_html() creates a temporary document for unattached roots, inheriting
    # curdoc()'s DocumentReady callbacks in Bokeh 3.2. Those callbacks reference
    # the entire live application. Give the clone its own explicit document.
    export_document = Document()
    if plots[0].document is not None:
        export_document.theme = plots[0].document.theme
    export_document.add_root(pair)
    html = file_html(export_document, INLINE, title='K–ω plot pair')
    outputs = {'.html': html, '.txt': metadata_text(metadata)}
    directory = Path(directory).expanduser().resolve()
    export_root = directory
    if config is not None:
        import output_paths as manager
        if directory == DEFAULT_EXPORT_DIR.resolve():
            directory = Path(config['paths']['figure_dir']).resolve()
        export_root = directory
        directory = manager.build_output_directory(directory, config, product)
    directory.mkdir(parents=True, exist_ok=True)
    staged, published = [], []
    try:
        for suffix, content in outputs.items():
            target = directory / (stem + suffix)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                    prefix='.' + stem, suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                staged.append((temporary, target))
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
            published.append(target)
    except Exception:
        for target in published:
            target.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    if config is not None:
        for target in published:
            # HTML and text share a stem, but a single metadata record describes
            # their identical processing configuration; register the HTML last.
            if target.suffix=='.html':
                manager.register_output(target, config, product, root=export_root, extra={'export':json_value(metadata)})
    return tuple(published)
