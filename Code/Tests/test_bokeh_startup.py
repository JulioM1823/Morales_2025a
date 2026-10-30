'''
Purpose
-------
Launch aliases must work even when optional cloud package markers cannot read.

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
import builtins
import errno
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pytest

from bokeh.application.handlers.directory import DirectoryHandler
from bokeh.document import Document

TD = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(TD))
from serve_komega_tools import build_applications


class BokehStartupTests(unittest.TestCase):
    '''
    Purpose
    -------
    Check Bokeh startup when cloud-backed package markers are unavailable.

    Inputs
    ------
    None
        Constructed by the test framework or its enclosing fixture.

    Outputs
    -------
    instance: BokehStartupTests
        Fixture or test-suite object providing the documented methods.
    '''

    def test_launches_without_reading_unavailable_package_markers(self):
        '''
        Purpose
        -------
        Verify launches without reading unavailable package markers.

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

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('integrated_komega_bokeh_app', 'magnetogram_bokeh_app'):
                app = root / name
                app.mkdir()
                (app / '__init__.py').write_text('"""Package marker."""\n')
                (app / 'main.py').write_text(
                    'from pathlib import Path\n'
                    'import sys\n'
                    'from bokeh.io import curdoc\n'
                    'from bokeh.models import Div\n'
                    'curdoc().add_root(Div(text=Path(__file__).parent.name))\n'
                    'curdoc().title = " ".join(sys.argv[1:])\n')
            original_open = builtins.open

            def cloud_open(filename, *args, **kwargs):
                '''
                Purpose
                -------
                Simulate cloud-storage failure for the unavailable package marker and
                delegate other opens.

                Inputs
                ------
                filename: str or pathlib.Path
                    Source filename used by the current test case.

                *args: tuple
                    Positional arguments accepted by the wrapper, or parsed benchmark
                    options.

                **kwargs: dict
                    Keyword arguments accepted by the substituted or wrapped callable.

                Outputs
                -------
                handle: object
                    Original open() result, or an OSError for the selected __init__.py
                    path.
                '''

                if Path(filename).name == '__init__.py' and Path(filename).parent.parent == root:
                    raise OSError(errno.EDEADLK, 'Resource deadlock avoided', str(filename))
                return original_open(filename, *args, **kwargs)

            argv = ['--registry', 'registry with spaces.json']
            with patch('builtins.open', cloud_open):
                # Reproduce the production failure with the former loader.
                with self.assertRaises(OSError) as failed:
                    DirectoryHandler(filename=str(root / 'integrated_komega_bokeh_app'))
                self.assertEqual(failed.exception.errno, errno.EDEADLK)
                applications = build_applications(root, argv)
                self.assertEqual(len(applications), 5)
                workspace = applications['/integrated_komega_bokeh_app']
                for route, app in applications.items():
                    with self.subTest(route=route):
                        doc = Document()
                        app.initialize_document(doc)
                        expected = ('magnetogram_bokeh_app' if route == '/magnetogram_bokeh_app'
                                    else 'integrated_komega_bokeh_app')
                        self.assertEqual(doc.roots[0].text, expected)
                        self.assertEqual(doc.title, ' '.join(argv))
                        if expected == 'integrated_komega_bokeh_app':
                            self.assertIs(app, workspace)

    def test_required_entrypoint_errors_are_not_suppressed(self):
        '''
        Purpose
        -------
        Verify required entrypoint errors are not suppressed.

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

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                build_applications(Path(folder), [])


if __name__ == '__main__':
    unittest.main()


def test_live_initial_construction_resolves_graph_once():
    '''
    Purpose
    -------
    Verify live initial construction resolves graph once.

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
    import integrated_komega_explorer as integrated
    doc = Document()
    recompute = doc.models.recompute
    with patch.object(Document, 'session_context', property(lambda self: object())), \
         patch.object(doc.models, 'recompute', wraps=recompute) as rebuild, \
         patch('observation_komega_explorer.discover_observations', return_value=[]) as discover:
        app = integrated.build_document(doc, product_roots=[], raw_roots=[])
        assert discover.call_count == 0
        assert rebuild.call_count == 1
    assert doc.roots == [app.layout]
    assert len(doc.models) > 1000
    assert doc.models._freeze_count == 0
    for model in app.model_workspace.models:
        assert doc.get_model_by_id(model.layout.id) is model.layout


def test_construction_error_unwinds_graph_batch():
    '''
    Purpose
    -------
    Verify construction error unwinds graph batch.

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

    from bokeh_ui_helpers import model_graph_update
    doc = Document()
    with patch.object(Document, 'session_context', property(lambda self: object())):
        with pytest.raises(ValueError, match='construction failure'):
            with model_graph_update(doc, constructing=True):
                raise ValueError('construction failure')
    assert doc.models._freeze_count == 0


def test_direct_open_discovers_and_selects_after_document_ready():
    '''
    Purpose
    -------
    Verify direct open discovers and selects after document ready.

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

    from concurrent.futures import Future
    from bokeh.events import DocumentReady
    import observation_komega_explorer as ui
    from observation_datasets import Observation
    doc = Document()
    future = Future()
    record = Observation('fixture', 'Fixture', 'fits', (Path('/tmp/fixture_komega.fits'),))
    with patch.object(Document, 'session_context', property(lambda self: object())), \
         patch.object(ui, 'discover_observations', side_effect=AssertionError('Blocking discovery')), \
         patch.object(ui.LOAD_POOL, 'submit', return_value=future) as submit:
        app = ui.ObservationKomegaExplorer(doc, product_roots=[], raw_roots=[])
        assert app.selected_id is None
        assert 'Loading dataset catalog' in app.status.text
        doc.callbacks.trigger_event(DocumentReady())
        submit.assert_called_once()
        future.set_result([record])
        for callback in list(doc.session_callbacks):
            doc.remove_next_tick_callback(callback)
            callback.callback()
        assert app.selected_id == record.id
        assert app.selector.value == [record.id]
        assert app.file_selector.records == [record]


def test_live_hidden_comparison_waits_until_enabled():
    '''
    Purpose
    -------
    Verify live hidden comparison waits until enabled.

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

    import integrated_komega_explorer as integrated
    from observation_datasets import Observation
    record = Observation('fixture', 'Fixture', 'fits', (Path('/tmp/fixture_komega.fits'),))
    doc = Document()
    with patch.object(Document, 'session_context', property(lambda self: object())):
        app = integrated.build_document(doc, input_observation=record)
    assert app.primary.selected_id == record.id
    assert app.secondary.selected_id is None
    assert app.secondary._load_callback is None
    app.left_toggle.active = True
    assert app.secondary.selected_id == record.id
    assert app.secondary._load_callback in doc.session_callbacks
    assert app.right_toggle.active
