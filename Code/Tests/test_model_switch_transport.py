'''
Purpose
-------
Verify the live model/solution messages with an independent receiving document.

Inputs
------
None
    Test cases use local fixtures, parameterized inputs, and the imported
    implementation modules.

Outputs
-------
Tests and audit helpers: callable
    Expose the regression cases or measured audit entrypoints defined here.
'''
# Import the test dependencies and implementation modules used by these checks.
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import warnings

import numpy as np
from bokeh.document import Document
from bokeh.document.events import DocumentPatchedEvent
from bokeh.layouts import column
from bokeh.models import ColumnDataSource
from bokeh.plotting import figure
from bokeh.protocol import Protocol
from bokeh.util.warnings import BokehUserWarning
import pytest

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import integrated_komega_explorer as integrated
import bokeh_ui_helpers as ui
from gaussian_filter_explorer import PreviewGeometry, compute_filter_result


def test_live_attachment_publishes_the_completed_image():
    '''
    Purpose
    -------
    Verify live attachment publishes the completed image.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''
    server = Document()
    root = column()
    server.add_root(root)
    client = Document.from_json(server.to_json(deferred=False))
    source = ColumnDataSource(dict(image=[np.zeros((3, 4), dtype=np.uint32)]))
    plot = figure()
    plot.image_rgba(image='image', x=0, y=0, dw=1, dh=1, source=source)
    expected = np.arange(12, dtype=np.uint32).reshape(3, 4) | np.uint32(0xff000000)

    def publish(event):
        '''
        Purpose
        -------
        Record a document-change event for subsequent Bokeh transport replay.

        Inputs
        ------
        event: object
            Document-change event captured for transport assertions.

        Outputs
        -------
        None
            Append the serialized/captured event to the enclosing transport log.
        '''

        if isinstance(event, DocumentPatchedEvent):
            Protocol().create('PATCH-DOC', [event]).apply_to_document(client)

    server.on_change(publish)
    with patch.object(Document, 'session_context', property(lambda self: object())):
        with ui.model_graph_update(server):
            root.children = [plot]
            source.data = dict(image=[expected])
    np.testing.assert_array_equal(client.get_model_by_id(source.id).data['image'][0], expected)


@pytest.fixture
def transport_app(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Build an integrated explorer fixture for document-patch replay tests.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    app: object
        Initialized integrated explorer on the synthetic product roots.
    '''

    # Build the isolated integrated application used by patch replay assertions.
    app = integrated.build_document(Document(), product_roots=[], raw_roots=[],
        schedule_initial=False, registry_file=tmp_path/'registry.json')
    # Only the model transport is under test; no external cubes or FITS products.
    geometry = PreviewGeometry(32, 64, 30., .16, 'transport regression')
    cube = np.random.default_rng(921).normal(size=(64, 32, 32))
    cube.setflags(write=False)
    data = SimpleNamespace(observation=SimpleNamespace(id='transport', label='transport'),
        values=np.zeros((16, 32)), geometry=geometry, ny=32, metadata={},
        dopplergrams=(cube, cube), analysis_config=dict(
            data=dict(source_type='single_cube', h1=0, h2=1),
            time_distance=dict(dt=30., p_dx_Mm=.16), filtering={}))
    app.primary.data = data
    app.primary.selected_id = 'transport'
    app.primary.catalog['transport'] = data.observation
    app.primary.filter_result = compute_filter_result(app.primary.filter.geometry,
        **app.primary.filter._current_parameters())
    monkeypatch.setitem(app.model_workspace.vesa.RESOLUTION_OPTIONS, 'interactive', (8, 10))
    app.model._perform_recompute()
    assert app.model.last_result is not None, app.model.status.text
    return app


def test_live_model_and_solution_switches_replay_without_stale_definitions(transport_app):
    '''
    Purpose
    -------
    Verify live model and solution switches replay without stale definitions.

    Inputs
    ------
    transport_app: object
        Explorer fixture used to capture and replay document transport events.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app = transport_app
    client = Document.from_json(app.doc.to_json(deferred=False))
    messages = []

    def publish(event):
        '''
        Purpose
        -------
        Record a document-change event for subsequent Bokeh transport replay.

        Inputs
        ------
        event: object
            Document-change event captured for transport assertions.

        Outputs
        -------
        None
            Append the serialized/captured event to the enclosing transport log.
        '''

        if isinstance(event, DocumentPatchedEvent):
            message = Protocol().create('PATCH-DOC', [event])
            message.apply_to_document(client)
            messages.append(message)

    app.doc.on_change(publish)
    originals = {}
    # Exercise the server branch while keeping solver execution deterministic.
    with patch.object(Document, 'session_context', property(lambda self: object())), \
         warnings.catch_warnings():
        warnings.filterwarnings('error', message='reference already known', category=BokehUserWarning)
        for cycle in range(2):
            for model in app.model_workspace.models:
                app.model_select.value = model.definition.key
                if model.last_result is None:
                    model._perform_recompute()
                assert model.last_result is not None, model.status.text
                original = originals.setdefault(model.definition.key, model.last_result)
                assert model.last_result is original
                for branch in range(model.branch_count):
                    app.branch_select.value = str(branch)
                    for side in (model, model.filtered):
                        raster = side._coherence_overlays[branch]
                        restored = client.get_model_by_id(raster.id)
                        assert restored is not None
                        assert restored.visible == raster.visible
                        np.testing.assert_array_equal(restored.data_source.data['image'][0],
                                                      raster.data_source.data['image'][0])
    assert messages
