'''
Purpose
-------
Scientific equivalence, synchronized state, durable saves and real exports.

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
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import json
import sys
from unittest.mock import patch

import numpy as np
import pytest
from astropy.io import fits
from bokeh.document import Document
from bokeh.events import ButtonClick
from bokeh.io.doc import patch_curdoc
from bokeh.models import ColumnDataSource

MODULE_DIR = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(MODULE_DIR))
import integrated_komega_explorer as integrated
import komega_explorer
from gaussian_filter_explorer import compute_diagram_filter
from observation_filter_registry import load_filter_parameters, read_registry
from test_dopplergram_recalculation import numerical_product
from dopplergram_recalculation import recalculate


def product(path, shape, offset, nt):
    '''
    Purpose
    -------
    Write a native numerical-product fixture for the integrated explorer.

    Inputs
    ------
    path: pathlib.Path
        Input or output path used by this fixture or its local substitute.

    shape: tuple of int
        Requested numerical-product or cube dimensions in the current fixture.

    offset: float
        Offset or seed adjustment distinguishing synthetic products.

    nt: int or None
        Number of temporal samples in the synthetic cube.

    Outputs
    -------
    None
        Delegate to numerical_product() to write the source and saved product.
    '''

    # Write a saved phase product with the axis and source metadata needed by discovery.
    numerical_product(path,shape,offset,nt)


@pytest.fixture
def app(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Construct the explorer fixture with synthetic inputs and small numerical grids.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    app: object
        Bokeh explorer document with initial scheduling disabled. Apply the
        temporary control/grid settings required by this module's tests.
    '''

    # Use a fresh document and small grids so the test controls the first calculation.
    root = tmp_path/'products'
    product(root/'observations/a_komega.fits', (8, 40), 0, 80)
    product(root/'simulations/b_komega.fits', (10, 30), 15, 59)
    config = komega_explorer._load_config(komega_explorer.CONFIG_FILE)
    vesa = komega_explorer.load_dispersion_explorer(config['komega_comparison']['vesa_2026_dir'])
    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'interactive', (8, 10))
    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'balanced', (10, 12))
    return integrated.build_document(Document(), product_roots=[root], raw_roots=[],
        registry_file=tmp_path/'registry.json', export_dir=tmp_path/'exports', schedule_initial=False)


def select(pair, identity):
    '''
    Purpose
    -------
    Select and synchronously load the requested explorer dataset.

    Inputs
    ------
    pair: object
        Explorer section containing a selected dataset, filter, and result sources.

    identity: str
        Dataset identifier selected in the explorer.

    Outputs
    -------
    None
        Update selector/load state and assert that the selected dataset is available.
    '''

    pair.selector.value = [identity]
    pair._perform_load(identity)
    assert pair.data is not None, pair.status.text


def calculate(app):
    '''
    Purpose
    -------
    Calculate the active integrated model synchronously and verify a result is stored.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Update app.model and assert that its last_result is available.
    '''

    app.model._perform_recompute()
    assert app.model.last_result is not None, app.model.status.text


def assert_model_grid(app):
    '''
    Purpose
    -------
    Check model axes, image extents, and hover geometry against the selected native
    product.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Report any coordinate, raster-extent, or hover-size mismatch by assertion.
    '''

    # Compare coordinates and raster extents for the original and filtered model panels.
    model, data = app.model, app.primary.data
    for result in (model.last_result, model.filtered_result):
        np.testing.assert_array_equal(result.kh_mm_inv, data.kh)
        np.testing.assert_array_equal(result.nu_mhz, data.nu)
        assert result.phase_deg.shape[:2] == data.values.T.shape
    for renderer in (model, model.filtered):
        for source in renderer.image_sources:
            for key in ('x', 'y', 'dw', 'dh'):
                np.testing.assert_array_equal(source.data[key], app.primary.image_source.data[key])
        for hover in renderer.hover_renderers:
            assert hover.glyph.width == np.median(np.diff(data.kh))
            assert hover.glyph.height == np.median(np.diff(data.nu))


def test_all_models_default_to_exact_primary_bins_and_follow_dataset_switch(app):
    '''
    Purpose
    -------
    Verify all models default to exact primary bins and follow dataset switch.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    for identity in (app.primary.observations[0].id, app.primary.observations[1].id):
        select(app.primary, identity)
        assert all(model.last_result is None for model in app.model_workspace.models)
        for model in app.model_workspace.models:
            app.model_select.value = model.definition.key
            assert model.resolution_select.value == 'dataset'
            calculate(app)
            assert_model_grid(app)


def test_custom_grid_and_restore_defaults_matches_dataset(app):
    '''
    Purpose
    -------
    Verify custom grid and restore defaults matches dataset.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    assert [key for key, _ in app.model.resolution_select.options] == ['dataset', 'custom']
    assert not app.model.custom_grid.visible
    app.model.custom_kh.value = '10'
    app.model.custom_nu.value = '12'
    app.model.resolution_select.value = 'custom'
    assert app.model.custom_grid.visible
    calculate(app)
    assert app.model.last_result.phase_deg.shape[:2] == (12, 10)
    app.model._restore_defaults()
    assert app.model.resolution_select.value == 'dataset'
    calculate(app)
    assert_model_grid(app)


@pytest.mark.parametrize('value', ['', '7', '221', '12.5', 'nan'])
def test_invalid_custom_grid_does_not_replace_valid_solution(app, value):
    '''
    Purpose
    -------
    Verify invalid custom grid does not replace valid solution.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    value: float
        Control, coherence, or validation value used by the current case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.model.resolution_select.value = 'custom'
    calculate(app)
    original = app.model.last_result
    app.model.custom_kh.value = value
    assert app.model.grid_error.visible
    assert app.model.last_result is original
    app.model.custom_kh.value = '11'
    assert not app.model.grid_error.visible
    calculate(app)
    assert len(app.model.last_result.kh_mm_inv) == 11


def test_compact_controls_retain_exact_inputs_and_remove_requested_text(app):
    '''
    Purpose
    -------
    Verify compact controls retain exact inputs and remove requested text.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from bokeh.models import Div
    for model in app.model_workspace.models:
        app.model_select.value = model.definition.key
        assert not model.mask_warnings.visible
        assert model.mask_warnings.active == [0]
        layouts = [child[0] for grid in model.parameter_grids for child in grid.children]
        assert layouts == [model.numeric_controls[item.key].layout
                           for role in ('dispersion', 'diagram')
                           for item in model.definition.parameters if item.role == role]
        for item in model.definition.parameters:
            control = model.numeric_controls[item.key]
            assert control.slider.sizing_mode == 'stretch_width'
            assert control.input.width == 72
        text = ' '.join(div.text for div in model.controls.select({'type': Div}))
        assert 'Wheel Zoom' not in text and 'inspect every solution' not in text


def test_native_axes_survive_postprocessing_without_repeating_roots(app):
    '''
    Purpose
    -------
    Verify native axes survive postprocessing without repeating roots.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.model_select.value = 'mt1982'
    calculate(app)
    original = app.model.last_result
    with patch.object(app.model_workspace.vesa, 'compute_diagram', side_effect=AssertionError('Repeated solve')):
        app.model.widgets['dz'].value += 15
    assert_model_grid(app)
    fresh = app.model_workspace.vesa.compute_diagram(app.model.definition.key,
        app.model._current_values(), kh_mm_inv=app.primary.data.kh, nu_mhz=app.primary.data.nu)
    np.testing.assert_allclose(app.model.last_result.phase_deg, fresh.phase_deg, equal_nan=True)
    np.testing.assert_array_equal(app.model.last_result.kz_real, original.kz_real)


def test_same_size_different_axes_do_not_restore_stale_panel_cache(app):
    '''
    Purpose
    -------
    Verify same size different axes do not restore stale panel cache.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    original = app.model.last_result
    # A different cadence/pixel scale changes coordinates without changing counts.
    data = replace(app.primary.data, kh=app.primary.data.kh * .8, nu=app.primary.data.nu * .7)
    app.model_workspace.set_comparison_grid(data)
    assert app.model.last_result is None and app.model.filtered_result is None
    run_scheduled(app.doc, app.model._pending_callback)
    result = app.model.last_result
    np.testing.assert_array_equal(result.kh_mm_inv, data.kh)
    np.testing.assert_array_equal(result.nu_mhz, data.nu)
    assert result is not original
    assert not np.allclose(result.kz_real, original.kz_real, equal_nan=True)


def run_scheduled(doc, callback):
    '''
    Purpose
    -------
    Run the callback actually registered by a widget change, as Bokeh does.

    Inputs
    ------
    doc: bokeh.document.Document
        Document whose pending callbacks are executed synchronously.

    callback: object
        Scheduled callback or worker callable exercised by the helper.

    Outputs
    -------
    None
        Assert registration and execute the actual pending callback chain.
    '''
    # Exercise the callback registered by Bokeh, including its immediate next-tick
    # stage.
    assert callback in doc.session_callbacks
    before = set(doc.session_callbacks)
    callback.callback()
    # The native model callback yields once to paint its busy state, then solves
    # on a registered next-tick callback. Exercise that actual second stage too.
    for next_tick in set(doc.session_callbacks) - before:
        next_tick.callback()


def test_live_filter_and_model_callbacks_use_latest_parameters(app):
    '''
    Purpose
    -------
    Verify live filter and model callbacks use latest parameters.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    select(app.secondary, app.primary.observations[1].id)
    original = app.primary.result_source.data['image'][0].copy()
    for value in (1.1, 2.2, 3.3):
        app.primary.filter.sliders['central_k'].value = value
    callback = app.primary.filter._scheduled_callback
    run_scheduled(app.doc, callback)
    assert_dataset_filter(app, app.primary)
    assert_dataset_filter(app, app.secondary)
    assert not np.allclose(original, app.primary.result_source.data['image'][0], equal_nan=True)
    np.testing.assert_allclose(app.model.filtered_result.phase_deg,
        app.model.last_result.phase_deg * app.model.transmission[..., None], equal_nan=True)
    app.model.widgets['cs'].value += .2
    assert app.model.filtered_result is None  # A stale result is never shown during a solve.
    app.primary.filter.sliders['width_f'].value = 2.5
    run_scheduled(app.doc, app.primary.filter._scheduled_callback)
    assert app.model.filtered_result is None
    run_scheduled(app.doc, app.model._pending_callback)
    assert dict(app.model.last_result.parameter_values)['cs'] == app.model.widgets['cs'].value
    np.testing.assert_allclose(app.model.filtered_result.phase_deg,
        app.model.last_result.phase_deg * app.model.transmission[..., None], equal_nan=True)
    app.model.widgets['dz'].value += 10
    np.testing.assert_allclose(app.model.filtered_result.phase_deg,
        app.model.last_result.phase_deg * app.model.transmission[..., None], equal_nan=True)


def test_curve_sources_independent_visibility_sampling_and_legends(app):
    '''
    Purpose
    -------
    Verify curve sources independent visibility sampling and legends.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from bokeh.models import Legend
    calculate(app)
    assert '<details' in app.sampling_info.text and '<details open' not in app.sampling_info.text
    for widget in app.primary.sampling.values():
        assert widget.id not in app.doc.models
        assert widget.title in app.sampling_info.text
    model = app.model
    for renderers in app.curves.overlays.values():
        assert renderers[0].data_source is model.fmode_source
        assert [r.data_source for r in renderers[1:]] == model.boundary_sources_by_branch[0]
    toggle = app.curves.toggles[(model.definition.key, 0)]
    toggle.active = False
    for renderers in app.curves.overlays.values():
        assert not renderers[1].visible
        assert renderers[0].visible
        assert renderers[2].visible
    app.curves.fmode.active = False
    assert all(not renderers[0].visible for renderers in app.curves.overlays.values())
    assert all(not list(plot.select(type=Legend)) for plot in app.all_plots())


def test_path_display_and_search_preserve_dataset_identity(app):
    '''
    Purpose
    -------
    Verify path display and search preserve dataset identity.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    pair = app.primary
    identity, data = pair.selected_id, pair.data
    assert all('/' not in label for _, label in pair.selector.options)
    pair.full_path.active = True
    assert all(label.startswith('/') for _, label in pair.selector.options)
    pair.search.value_input = 'does not match any file'
    assert pair.selector.options[0][0] == identity
    pair.full_path.active = False
    assert pair.selected_id == identity and pair.data is data


def assert_dataset_filter(app, pair):
    '''
    Purpose
    -------
    Check that native filter geometry and recalculated phase match the displayed
    dataset.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    pair: object
        Explorer section containing a selected dataset, filter, and result sources.

    Outputs
    -------
    None
        Compare the result image with an independent recalculation.
    '''

    # Calculate the native filtered reference independently of the displayed image
    # source.
    expected = compute_diagram_filter(pair.data.kh, pair.data.nu, pair.filter.geometry,
                                     **app.primary.filter._current_parameters())
    assert expected.shape == pair.data.values.T.shape
    native = recalculate(pair.data.dopplergrams,pair.data.analysis_config,
                         app.primary.filter._current_parameters())
    np.testing.assert_array_equal(pair.result_source.data['image'][0],native[0].T)


def test_one_horizontal_workspace_reuses_all_models_and_selectors(app):
    '''
    Purpose
    -------
    Verify one horizontal workspace reuses all models and selectors.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    assert len(app.doc.roots) == 1
    assert app.doc.validate() is None
    workspace = app.doc.get_model_by_name('integrated:workspace')
    assert [item[0] for item in workspace.children] == [app.left_section, app.middle_section, app.right_section]
    assert app.middle_section.width >= 440
    assert [item.definition.key for item in app.model_workspace.models] == [
        'nc2009', 'alfven_mode', 'slow_mode', 'fast_mode', 'bunte1993', 'mt1982', 'mt1981']
    assert [item.branch_count for item in app.model_workspace.models] == [6, 2, 2, 2, 2, 2, 2]
    assert app.primary.filter is app.model_workspace.filter
    assert type(app.primary.selector).__name__ == 'MultiChoice'
    assert app.primary.selector.height is None
    assert not app.primary.full_path.active
    app.primary.search.value_input = 'simulations'
    assert len(app.primary.selector.options) == 2  # Active selection remains available.
    assert app.primary.selector.options[-1][0].startswith('simulation_fits:')
    app.primary.search.value_input = ''
    assert len(app.primary.selector.options) == 2
    assert app.primary.filter.status not in app.doc.models


def test_sections_preserve_edited_values_data_models_and_callbacks(app):
    '''
    Purpose
    -------
    Verify sections preserve edited values data models and callbacks.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.primary.filter.numeric_controls['central_k'].input.value = '2.234567'
    app.primary.filter._perform_recompute()
    app.model.widgets['cs'].value += .2
    calculate(app)
    sections = (app.gaussian_section, app.dispersion_section)
    sources = list(app.doc.select(dict(type=ColumnDataSource)))
    data = {source.id: deepcopy(source.data) for source in sources}
    models = set(app.doc.models)
    callbacks = set(app.doc.session_callbacks)
    state = {key: deepcopy(value) for key, value in vars(app.state).items()
             if key not in ('unfiltered', 'filtered')}
    results = {key: dict(getattr(app.state, key)) for key in ('unfiltered', 'filtered')}
    result, filtered = app.model.last_result, app.model.filtered_result
    display_key = app.model._filtered_display_key
    children = [list(section.body.children) for section in sections]
    with ExitStack() as stack:
        expensive = [stack.enter_context(patch.object(owner, method)) for owner, method in (
            (app.primary.filter, '_perform_recompute'), (app.primary, '_refresh_preview'),
            (app.model, '_perform_recompute'), (app.model, 'refresh_filter'))]
        for _ in range(4):
            for gaussian, dispersion in ((False, True), (True, False), (False, False), (True, True)):
                for section, expanded in zip(sections, (gaussian, dispersion)):
                    section.toggle.active = expanded
                    assert section.body.visible is expanded
                    assert section.toggle.label == ('Hide ' if expanded else 'Show ') + 'Controls'
                    assert section.layout.visible
                    assert section.body.height is None and section.layout.height is None
                assert all(target.visible is gaussian for target in app.gaussian_section._targets)
                assert app.model_select.visible  # Models remain selectable while collapsed.
                assert app.model.plots[int(app.branch_select.value)] in [item[0] for item in app.left_plots.children]
                assert app.model.filtered.plots[int(app.branch_select.value)] in [item[0] for item in app.right_plots.children]
                assert all(plot.visible for plot in app.all_plots())
                assert set(app.doc.models) == models
                assert set(app.doc.session_callbacks) == callbacks
                assert {key: value for key, value in vars(app.state).items()
                        if key not in results} == state
                for key, values in results.items():
                    assert all(getattr(app.state, key)[name] is value for name, value in values.items())
                assert app.model.last_result is result and app.model.filtered_result is filtered
                assert app.model._filtered_display_key == display_key
        assert all(mock.call_count == 0 for mock in expensive)
    assert [section.body.children for section in sections] == children
    assert app.primary.filter.sliders['central_k'].value == 2.234567
    for source in sources:
        assert app.doc.get_model_by_id(source.id) is source
        for key, values in data[source.id].items():
            np.testing.assert_equal(source.data[key], values)


@pytest.mark.parametrize('expanded', [False, True])
def test_section_state_survives_all_models_shared_parameters_and_comparison(app, expanded):
    '''
    Purpose
    -------
    Verify section state survives all models shared parameters and comparison.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    expanded: bool
        Requested expanded/collapsed state of the tested section.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.model.widgets['cs'].value += .25
    shared_cs = app.model.widgets['cs'].value
    cached = {}
    for model in app.model_workspace.models:
        app.model_select.value = model.definition.key
        calculate(app)
        cached[model.definition.key] = model.last_result
    app.model_select.value = 'nc2009'
    app.branch_select.value = '5'
    app.gaussian_section.toggle.active = False
    app.dispersion_section.toggle.active = expanded
    params = {model.definition.key: model._current_values() for model in app.model_workspace.models}
    callbacks = set(app.doc.session_callbacks)
    with patch.object(app.model_workspace.vesa, 'compute_diagram') as solve:
        for _ in range(2):
            for model in app.model_workspace.models:
                app.model_select.value = model.definition.key
                assert app.dispersion_section.body.visible is expanded
                assert app.dispersion_section.layout.visible
                assert not app.gaussian_section.body.visible
                assert app.model_controls.children == app._control_panels[model.definition.key]
                assert model._current_values() == params[model.definition.key]
                if 'cs' in model.widgets:
                    assert model.widgets['cs'].value == shared_cs
                assert model.last_result is cached[model.definition.key]
                assert app.left_plots.children[1][0] is model.plots[int(app.branch_select.value)]
                assert app.right_plots.children[1][0] is model.filtered.plots[int(app.branch_select.value)]
        solve.assert_not_called()
    assert set(app.doc.session_callbacks) == callbacks
    app.model_select.value = 'nc2009'
    assert app.branch_select.value == '5'
    app.left_toggle.active = True
    assert not app.dispersion_section.layout.visible
    app.right_toggle.active = False
    assert app.dispersion_section.layout.visible
    assert app.dispersion_section.body.visible is expanded
    assert not app.gaussian_section.body.visible


@pytest.mark.parametrize('key,value', [('central_k', 2.2), ('width_k', 3.2),
                                      ('central_f', 2.5), ('width_f', 2.2)])
def test_filter_changes_update_both_right_plots_without_touching_left_or_solving(app, key, value):
    '''
    Purpose
    -------
    Verify filter changes update both right plots without touching left or solving.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    key: object
        Parameter name, array index, or cache-key arguments used by the local
        substitute.

    value: float
        Control, coherence, or validation value used by the current case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    select(app.secondary, app.primary.observations[1].id)
    original_data = app.primary.image_source.data['image'][0]
    original_secondary = app.secondary.image_source.data['image'][0]
    original_model = [source.data['image'][0] for source in app.model.image_sources]
    cached = app.model.last_result
    with patch.object(app.model_workspace.vesa, 'compute_diagram', side_effect=AssertionError('Repeated solve')):
        app.primary.filter.sliders[key].value = value
        app.primary.filter._perform_recompute()
    assert app.primary.image_source.data['image'][0] is original_data
    assert app.secondary.image_source.data['image'][0] is original_secondary
    assert app.model.last_result is cached
    for source, before in zip(app.model.image_sources, original_model):
        assert source.data['image'][0] is before
    assert_dataset_filter(app, app.primary)
    assert_dataset_filter(app, app.secondary)
    np.testing.assert_allclose(app.model.filtered_result.phase_deg,
        cached.phase_deg * app.model.transmission[..., None], equal_nan=True)
    assert 'Unsaved' not in app.primary.status.text
    assert app.primary._gaussian_unsaved


def test_all_models_fields_branches_masks_and_natural_scaling_preserved(app):
    '''
    Purpose
    -------
    Verify all models fields branches masks and natural scaling preserved.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    for item in app.model_workspace.models:
        app.model_select.value = item.definition.key
        calculate(app)
        assert len(app.branch_select.options) == item.branch_count
        for field, attr in [('phase', 'phase_deg'), ('kz_real', 'kz_real'), ('kz_imag', 'kz_imag')]:
            item.field_select.value = field
            raw = getattr(item.last_result, attr)
            filtered = raw * item.transmission[..., None]
            np.testing.assert_allclose(getattr(item.filtered_result, attr), filtered, equal_nan=True)
            for branch in range(item.branch_count):
                app.branch_select.value = str(branch)
                assert app.left_plots.children[1][0] is item.plots[branch]
                assert app.right_plots.children[1][0] is item.filtered.plots[branch]
                displayed = filtered[:, :, branch].copy()
                displayed[item.last_result.numerical_warning_mask] = np.nan
                np.testing.assert_allclose(item.filtered.image_sources[branch].data['image'][0], displayed, equal_nan=True)
            expected_limits = (-80., 80.) if field == 'phase' else item._pipeline_kz_limits(filtered)
            assert (item.filtered.mapper.low, item.filtered.mapper.high) == expected_limits
        item.mask_warnings.active = []
        assert item.filtered.mask_warnings.active == []
        item.show_fmode.active = [0]
        assert item.filtered.show_fmode.active == [0]


@pytest.mark.parametrize('model_key', ['slow_mode', 'fast_mode'])
def test_separate_mhd_models_render_with_warning_mask_enabled(app, model_key):
    '''
    Purpose
    -------
    Verify separate MHD models render with warning mask enabled.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    model_key: str
        Model identifier selected in the explorer or solver fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.model_select.value = model_key
    model = app.model
    values = dict(a=14.6, cs=7.05246440457191, theta_deg=-87.0,
                  phi_deg=0.26121180203181327, dz=100.0)
    for key, value in values.items():
        model.widgets[key].value = value
    model.mask_warnings.active = [0]
    calculate(app)

    result = model.last_result
    assert not result.numerical_warning_mask.all()
    for renderer, expected in ((model, result), (model.filtered, model.filtered_result)):
        assert expected is not None
        for branch in range(model.branch_count):
            pixels = renderer.image_sources[branch].data['image'][0]
            assert np.isfinite(pixels).any()
            assert not renderer.message_labels[branch].visible
            masked = expected.phase_deg[:, :, branch].copy()
            masked[result.numerical_warning_mask] = np.nan
            np.testing.assert_array_equal(pixels, masked)
    np.testing.assert_array_equal(result.kh_mm_inv, app.primary.data.kh)
    np.testing.assert_array_equal(result.nu_mhz, app.primary.data.nu)


@pytest.mark.parametrize('model_key', ['slow_mode', 'fast_mode'])
def test_first_model_raster_is_populated_when_attached_to_document(app, model_key):
    '''
    Purpose
    -------
    Verify first model raster is populated when attached to document.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    model_key: str
        Model identifier selected in the explorer or solver fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''
    app.model_select.value = model_key
    model = app.model
    for key, value in dict(a=14.6, cs=7.05246440457191,
                           theta_deg=-87.0, dz=100.0).items():
        model.widgets[key].value = value
    attached_images = []

    def attached(attr, old, new):
        '''
        Purpose
        -------
        Capture newly attached coherence-overlay rasters during a renderer-list update.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: object
            Previous Bokeh property value.

        new: object
            Updated Bokeh property value.

        Outputs
        -------
        None
            Append copies of the newly attached image arrays to the enclosing log.
        '''

        for renderer in new:
            if renderer not in old and renderer.name and ':coherence_overlay:' in renderer.name:
                images = renderer.data_source.data.get('image', [])
                attached_images.append([image.copy() for image in images])

    for panel in (model, model.filtered):
        for plot in panel.plots:
            plot.on_change('renderers', attached)
    calculate(app)

    assert len(attached_images) == 2*model.branch_count
    for images in attached_images:
        assert len(images) == 1
        assert images[0].shape == model.last_result.phase_deg.shape[:2]
        assert np.any(images[0] >> 24)  # The first browser payload has visible pixels.


def test_model_parameter_changes_and_comparison_toggles_preserve_state(app):
    '''
    Purpose
    -------
    Verify model parameter changes and comparison toggles preserve state.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    slider = app.model.widgets['theta_deg']
    slider.value = 60.
    calculate(app)
    cached = app.model.last_result
    values = app.model._current_values()
    for toggle in (app.left_toggle, app.right_toggle):
        toggle.active = True
        assert app.left_toggle.active and app.right_toggle.active
        assert app.state.left_comparison and app.state.right_comparison
        assert app.left_plots.children[1][0] is app.secondary.observed_plot
        assert app.right_plots.children[1][0] is app.secondary.result_plot
        assert app.model.last_result is cached
        toggle.active = False
        assert not app.left_toggle.active and not app.right_toggle.active
        assert app.model._current_values() == values
        assert app.model_select.value == 'nc2009'
    app.model_select.value = 'bunte1993'
    calculate(app)
    app.model_select.value = 'nc2009'
    assert app.model._current_values() == values


def test_saved_sampling_and_solution_selection_are_preserved_separately(app):
    '''
    Purpose
    -------
    Verify saved sampling and solution selection are preserved separately.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    app.branch_select.value = '5'
    app.model_select.value = 'bunte1993'
    assert app.branch_select.value == '0'
    app.model_select.value = 'nc2009'
    assert app.branch_select.value == '5'
    app.primary._store()
    assert 'matches' in app.filter_state.text
    app.primary.sampling['ny'].value = 18
    assert 'differs' in app.filter_state.text
    app.primary._store()
    assert 'Sampling must match' in app.primary.status.text
    app.primary.sampling['ny'].value = app.primary.data.ny
    app.primary._store()
    assert 'matches' in app.filter_state.text
    assert read_registry(app.primary.registry_file)['observations'][app.primary.selected_id]['dataset']['sampling']['ny'] == app.primary.data.ny


@pytest.mark.parametrize('source_type,strength', [('paired_cubes', 0.), ('single_cube', 2.), ('single_cube', 8.)])
def test_existing_figure_context_initializes_integrated_dataset_and_named_model_inputs(app, tmp_path, source_type, strength):
    '''
    Purpose
    -------
    Verify existing figure context initializes integrated dataset and named model
    inputs.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    strength: float
        Synthetic field/Alfven-speed parameter in the units declared by the fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from test_komega_bokeh_integration import sample
    from komega_bokeh_context import publish_context
    data, config = sample(tmp_path, source_type, strength)
    context = publish_context(tmp_path/'context.jpeg', data, config)['context']
    launched = integrated.build_document(Document(), product_roots=[], raw_roots=[],
        launch_context=context, registry_file=tmp_path/'context-registry.json', schedule_initial=False)
    assert launched.primary.data.observation.id == context['dataset']['id']
    assert launched.model_select.value == 'nc2009'
    if source_type == 'single_cube':
        for key, value in context['model']['parameters'].items():
            assert launched.model.widgets[key].value == value
    else:
        assert launched.model._current_values() == app.model._current_values()


def test_distinct_dataset_saves_replacement_reload_and_secondary_independence(app):
    '''
    Purpose
    -------
    Verify distinct dataset saves replacement reload and secondary independence.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    first, second = [item.id for item in app.primary.observations]
    app.primary.filter.sliders['central_k'].value = 2.1
    app.primary.store_button._trigger_event(ButtonClick(app.primary.store_button))
    assert 'Parameters stored for' in app.primary.status.text
    saved_first = load_filter_parameters(first, app.primary.registry_file)
    assert saved_first['central_k'] == 2.1
    select(app.primary, second)
    assert app.primary.filter._current_parameters() == app.primary.filter.defaults
    app.primary.filter.sliders['central_f'].value = 2.4
    app.primary._store()
    saved_second = load_filter_parameters(second, app.primary.registry_file)
    select(app.primary, first)
    assert app.primary.filter._current_parameters() == saved_first
    assert app.state.saved_parameters == saved_first
    select(app.secondary, second)
    assert app.primary.filter._current_parameters() == saved_first
    app.primary.filter.sliders['width_k'].value = 2.8
    assert app.state.saved_parameters == saved_first
    assert app.state.gaussian_parameters['width_k'] == 2.8
    app.primary._store()
    records = read_registry(app.primary.registry_file)['observations']
    assert len(records) == 2
    assert records[first]['gaussian']['parameters']['width_k'] == 2.8
    assert records[second]['gaussian']['parameters'] == saved_second
    assert records[first]['dataset']['id'] == first
    assert records[first]['dataset']['metadata']['source_fingerprints'][0]['sha256']
    assert set(records[first]['gaussian']['parameters']) == set(app.primary.filter.sliders)
    assert load_filter_parameters('missing:id', app.primary.registry_file) is None


@pytest.mark.parametrize('kind', ['unfiltered', 'filter', 'filtered'])
@pytest.mark.parametrize('comparison', [False, True])
def test_each_export_saves_actual_pair_and_complete_readable_metadata(app, kind, comparison):
    '''
    Purpose
    -------
    Verify each export saves actual pair and complete readable metadata.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    kind: str
        Export variant selected by the parameterized case.

    comparison: object
        Comparison view or mode selected by the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    select(app.secondary, app.primary.observations[1].id)
    app.left_toggle.active = comparison
    app.primary.filter.sliders['width_f'].value = 2.3
    app.primary.filter._perform_recompute()
    grid = app.left_plots if kind == 'unfiltered' else app.right_plots
    original_plots = [item[0] for item in grid.children]
    # Match server callbacks: curdoc() is the live app, with its resize callback.
    with patch_curdoc(app.doc):
        paths = app.save_plot(kind)
    assert paths is not None, app.export_status.text
    html, text = [path.read_text() for path in paths]
    assert '<html' in html and 'Bokeh' in html and '"type":"object","name":"Row"' in html
    assert '"name":"Div"' not in html and '"name":"CustomJS"' not in html
    assert 'integrated:left_comparison' not in html
    assert 'K-OMEGA PLOT EXPORT' in text
    assert app.primary.selected_id in text and 'source_fingerprints' in text
    assert '2.3' in text and 'color_limits' in text and 'timestamp' in text.lower()
    if comparison:
        assert app.secondary.selected_id in text
    else:
        assert 'theta_deg' in text and 'solution_index' in text and 'solver_parameters' in text
    if kind == 'filter':
        assert text.index('Gaussian Filter') < text.index('Source 1')
    for plot in original_plots:
        assert plot.document is app.doc  # Export cloning leaves the session intact.
    assert not list(paths[0].parent.glob('*.tmp'))


def test_malformed_registry_missing_data_invalid_filter_and_export_failures_are_visible(app, tmp_path):
    '''
    Purpose
    -------
    Verify malformed registry missing data invalid filter and export failures are
    visible.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    registry = app.primary.registry_file
    registry.write_text('{broken')
    select(app.primary, app.primary.selected_id)
    assert 'Cannot read registry' in app.primary.status.text
    app.primary._store()
    assert 'Cannot read registry' in app.primary.status.text
    assert registry.read_text() == '{broken'
    registry.unlink()
    app.primary._store()
    assert load_filter_parameters(app.primary.selected_id, registry) is not None
    calculate(app)
    app.primary.filter.sliders['width_k'].value = 0.
    app.primary.filter._perform_recompute()
    assert app.primary.transmission is None and app.model.filtered_result is None
    assert app.save_plot('filtered') is None
    assert 'not saved' in app.export_status.text
    app.primary.filter.sliders['width_k'].value = 4.
    app.primary.filter._perform_recompute()
    blocked = tmp_path/'not-a-directory'
    blocked.write_text('preserve')
    app.export_directory.value = str(blocked)
    assert app.save_plot('filtered') is None
    assert blocked.read_text() == 'preserve'
    app.primary._perform_load(app.primary.selected_id, load_error=OSError('missing source'))
    assert app.primary.data is None
    assert app.model.filtered_result is None
    assert 'missing source' in app.primary.status.text
    assert app.save_plot('unfiltered') is None


def test_invalid_sampling_or_pending_primary_selection_clears_only_filtered_outputs(app):
    '''
    Purpose
    -------
    Verify invalid sampling or pending primary selection clears only filtered outputs.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    original = app.model.last_result
    image = app.model.image_sources[0].data['image'][0]
    app.primary.sampling['nt'].value = 2
    assert app.primary.filter_result is None
    assert app.model.filtered_result is None
    assert app.secondary.transmission is None
    assert app.model.last_result is original
    assert app.model.image_sources[0].data['image'][0] is image
    app.primary.sampling['nt'].value = 80
    app.primary.filter._perform_recompute()
    assert app.model.filtered_result is not None
    app.primary.selector.value = [app.primary.observations[1].id]
    assert app.primary.data is None and app.model.filtered_result is None
    assert app.model.last_result is original


def test_all_nan_dataset_reports_unusable_values_and_refuses_blank_exports(app):
    '''
    Purpose
    -------
    Verify all nan dataset reports unusable values and refuses blank exports.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from dopplergram_recalculation import input_path
    input_path(app.primary.data.observation.files[0]).unlink()
    calculate(app)
    path = app.primary.data.observation.files[0]
    with fits.open(path, mode='update') as hdus:
        hdus[0].data[:] = np.nan
    select(app.primary, app.primary.selected_id)
    assert 'no finite phase values' in app.primary.status.text
    assert app.save_plot('unfiltered') is None
    assert 'no finite displayed values' in app.export_status.text
    assert app.save_plot('filtered') is None


def test_model_failure_clears_filtered_result_and_prevents_export(app):
    '''
    Purpose
    -------
    Verify model failure clears filtered result and prevents export.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    with patch.object(app.model_workspace.vesa, 'compute_diagram', side_effect=ValueError('solver failed')):
        app.model._perform_recompute()
    assert app.model.last_result is None and app.model.filtered_result is None
    assert 'solver failed' in app.model.status.text
    assert app.save_plot('filtered') is None


def test_export_stage_failure_leaves_no_partial_pair(app, monkeypatch):
    '''
    Purpose
    -------
    Verify export stage failure leaves no partial pair.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    import komega_plot_export
    original = komega_plot_export.os.replace
    count = 0
    def fail_second(*args):
        '''
        Purpose
        -------
        Simulate a publication failure on the second delegated write.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        Outputs
        -------
        result: object
            Original writer result for other calls; raise OSError on the second call.
        '''

        nonlocal count
        count += 1
        if count == 2:
            raise OSError('interrupted publication')
        return original(*args)
    monkeypatch.setattr(komega_plot_export.os, 'replace', fail_second)
    assert app.save_plot('filter') is None
    assert 'interrupted publication' in app.export_status.text
    assert not list(Path(app.export_directory.value).rglob("*.html"))
    assert not list(Path(app.export_directory.value).rglob("*.txt"))


def test_export_uses_the_directory_currently_typed_before_blur(app, tmp_path):
    '''
    Purpose
    -------
    Verify export uses the directory currently typed before blur.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    calculate(app)
    destination = tmp_path/'typed-directory'
    app.export_directory.value_input = str(destination)
    assert app.export_directory.value != str(destination)
    paths = app.save_plot('filtered')
    assert paths is not None, app.export_status.text
    assert all(path.is_relative_to(destination) for path in paths)
    assert 'observations/doppler_velocity/Annulus' in paths[0].relative_to(destination).as_posix()
    app.export_directory.value_input = ''
    assert app.save_plot('filtered') is None
    assert 'Choose a plot export directory' in app.export_status.text


def test_live_figure_launch_defers_full_catalog_until_document_ready(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify live figure launch defers full catalog until document ready.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from concurrent.futures import Future
    import weakref
    from bokeh.events import DocumentReady
    import observation_komega_explorer as observations
    from observation_datasets import dataset_from_fits
    path = tmp_path/'observations/launch_komega.fits'
    product(path, (8, 40), 0, 80)
    selected = dataset_from_fits(path, 'paired_cubes', tmp_path)
    monkeypatch.setattr('komega_bokeh_context.validate_context', lambda value: selected)
    calls = []
    future = Future()
    def submit(function, **kwargs):
        '''
        Purpose
        -------
        Record deferred worker work and return the controlled Future used by the test.

        Inputs
        ------
        function: callable
            Deferred worker callable recorded by the test executor.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        future: concurrent.futures.Future
            Future retained by the enclosing fixture; the test decides when the
            recorded callable runs or when the Future is completed.
        '''

        calls.append(function)
        return future
    monkeypatch.setattr(observations.LOAD_POOL, 'submit', submit)
    monkeypatch.setattr(observations, 'discover_observations', lambda **kwargs: (_ for _ in ()).throw(
        AssertionError('Catalog scan blocked initial rendering')))
    doc = Document()
    class Context:
        '''
        Purpose
        -------
        Provide the fixed context attribute consumed by the deferred catalog-launch
        test.

        Inputs
        ------
        None
            Constructed by the test framework or its enclosing fixture.

        Outputs
        -------
        instance: Context
            Fixture or test-suite object providing the documented methods.
        '''

        pass
    context = Context()
    doc._session_context = weakref.ref(context)
    app = observations.ObservationKomegaExplorer(doc, launch_context={}, registry_file=tmp_path/'registry.json')
    assert app.selected_id == selected.id
    assert list(app.catalog) == [selected.id]
    assert calls == []
    doc.callbacks.trigger_event(DocumentReady())
    assert calls == [observations.discover_observations]
