'''
Purpose
-------
Direct filtering, restoration, and shared controls for all model diagrams.

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
from __future__ import annotations

# Import the test dependencies and implementation modules used by these checks.
import importlib
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pytest
from bokeh.document import Document
from bokeh.events import ButtonClick
from bokeh.models import Div, WheelZoomTool

MODULE_DIR = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(MODULE_DIR))
import komega_explorer as explorer
from gaussian_filter_explorer import (PreviewGeometry, compute_diagram_filter,
    compute_filter_result)


@pytest.fixture
def app(monkeypatch):
    '''
    Purpose
    -------
    Construct the explorer fixture with synthetic inputs and small numerical grids.

    Inputs
    ------
    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    app: object
        Bokeh explorer document with initial scheduling disabled. Apply the
        temporary control/grid settings required by this module's tests.
    '''

    # Use a fresh document and small grids so the test controls the first calculation.
    config = explorer._load_config(explorer.CONFIG_FILE)
    vesa = explorer.load_dispersion_explorer(config['komega_comparison']['vesa_2026_dir'])
    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'interactive', (8, 10))
    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'balanced', (10, 12))
    return explorer.build_document(Document(), schedule_initial=False)


def calculate(app, index):
    '''
    Purpose
    -------
    Activate the requested model tab and calculate its result synchronously.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    index: int
        Zero-based model/tab index to calculate.

    Outputs
    -------
    model: object
        Updated model section; assert that its last_result is available.
    '''

    app.tabs.active = index
    model = app.models[index]
    model._perform_recompute()
    assert model.last_result is not None, model.status.text
    return model


def test_solver_accepts_native_axes_beyond_preset_limit_and_caches_coordinates(app):
    '''
    Purpose
    -------
    Verify solver accepts native axes beyond preset limit and caches coordinates.

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

    kh, nu = np.linspace(.1, 3.5, 5), np.linspace(0., 16., 241)
    first = app.vesa.compute_diagram('mt1982', kh_mm_inv=kh, nu_mhz=nu)
    assert first.phase_deg.shape[:2] == (241, 5)
    np.testing.assert_array_equal(first.kh_mm_inv, kh)
    np.testing.assert_array_equal(first.nu_mhz, nu)
    assert app.vesa.compute_diagram('mt1982', kh_mm_inv=kh, nu_mhz=nu) is first
    second = app.vesa.compute_diagram('mt1982', kh_mm_inv=kh*.8, nu_mhz=nu*.9)
    assert second is not first
    assert not np.allclose(first.kz_real, second.kz_real, equal_nan=True)


@pytest.mark.parametrize('kh,nu', [([0., 1.], None), (None, [0., 1.]),
    ([0.], [0., 1.]), ([0., 0.], [0., 1.]), ([0., 1.], [0., np.nan]),
    ([-1., 0.], [0., 1.]), ([[0., 1.]], [0., 1.])])
def test_solver_rejects_invalid_comparison_axes(app, kh, nu):
    '''
    Purpose
    -------
    Verify solver rejects invalid comparison axes.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    kh: float or array-like
        Horizontal-wavenumber sample or test axis, in the units of the tested API.

    nu: array-like
        Frequency axis supplied to the tested comparison API (mHz).

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='axis|axes'):
        app.vesa.compute_diagram('mt1982', kh_mm_inv=kh, nu_mhz=nu)


@pytest.mark.parametrize('nt', [79, 80])
def test_diagram_construction_matches_native_filter_when_axes_match(nt):
    '''
    Purpose
    -------
    Verify diagram construction matches native filter when axes match.

    Inputs
    ------
    nt: int or None
        Number of temporal samples in the synthetic cube.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    geometry = PreviewGeometry(16, nt, 11.88, .43, 'test')
    params = dict(central_k=1.5, width_k=4., central_f=3., width_f=3.)
    native = compute_filter_result(geometry, **params)
    actual = compute_diagram_filter(native.kh, native.nu, geometry, **params)
    assert actual.shape == native.transmission.shape
    np.testing.assert_allclose(actual, native.transmission, atol=1e-14)


def test_one_document_keeps_all_models_controls_and_linked_axes(app):
    '''
    Purpose
    -------
    Verify one document keeps all models controls and linked axes.

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

    assert app.doc.validate() is None
    assert len(app.doc.roots) == 1
    assert [model.definition.key for model in app.models] == [
        'nc2009', 'alfven_mode', 'slow_mode', 'fast_mode', 'bunte1993', 'mt1982', 'mt1981']
    assert [model.branch_count for model in app.models] == [6, 2, 2, 2, 2, 2, 2]
    assert not app.apply_filter.active
    assert app.remove_filter.label == 'Remove Filter'
    assert app.filter.status not in app.doc.models
    for section in app.models:
        assert set(section.widgets) == {item.key for item in section.definition.parameters}
        assert section.plot.x_range is app.filter.plot.x_range
        assert section.plot.y_range is app.filter.plot.y_range
        assert section.plot.toolbar.active_scroll is None
        assert any(isinstance(tool, WheelZoomTool) for tool in section.plot.tools)
    adapter = importlib.import_module(app.vesa.__package__ + '.interactive_models')
    assert Path(adapter.config.__file__).resolve().parent == Path(app.vesa.__file__).resolve().parent
    assert adapter.DiagnosticDiagram.__module__.startswith(app.vesa.__package__)


@pytest.mark.parametrize("model_key", ["alfven_mode", "slow_mode"])
def test_zero_field_models_report_no_isolated_roots(app, model_key):
    '''
    Purpose
    -------
    Verify zero field models report no isolated roots.

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

    result = app.vesa.compute_diagram(
        model_key,
        {"a": 0.0},
        (8, 10),
        use_cache=False,
    )

    assert not (np.isfinite(result.kz_real) & np.isfinite(result.kz_imag)).any()
    assert result.warnings
    assert result.all_kz_roots is not None


def test_all_seven_models_multiply_all_fields_without_mutating_cached_results(app):
    '''
    Purpose
    -------
    Verify all seven models multiply all fields without mutating cached results.

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

    app.apply_filter.active = True
    for index in range(7):
        model = calculate(app, index)
        expected = app.vesa.compute_diagram(model.definition.key, model._current_values(), (8, 10))
        if model.definition.key in {'alfven_mode', 'slow_mode', 'fast_mode'}:
            assert expected.all_kz_roots is not None
            assert expected.propagating_mask.shape == expected.kz_real.shape
            assert expected.vertical_group_velocity_km_s.shape == expected.kz_real.shape
            assert expected.normalized_dispersion_residual.shape == expected.kz_real.shape
            assert expected.mode_ambiguous_mask.shape == expected.kz_real.shape[:2]
            if model.definition.key in {'slow_mode', 'fast_mode'}:
                assert expected.all_kz_roots.shape == (*expected.kz_real.shape[:2], 4)
                assert expected.mode_classification.shape == expected.all_kz_roots.shape
                assert expected.selected_root_indices.shape == expected.kz_real.shape
        for field, key in [('phase', 'phase_deg'), ('kz_real', 'kz_real'), ('kz_imag', 'kz_imag')]:
            model.field_select.value = field
            raw = getattr(expected, key)
            np.testing.assert_allclose(getattr(model.last_result, key), raw, equal_nan=True)
            multiplied = raw * model.transmission[..., None]
            for branch, source in enumerate(model.image_sources):
                values = multiplied[:, :, branch].copy()
                display_mask = expected.numerical_warning_mask.copy()
                if expected.mode_ambiguous_mask is not None:
                    display_mask |= expected.mode_ambiguous_mask
                values[display_mask] = np.nan
                np.testing.assert_allclose(source.data['image'][0], values, equal_nan=True)
                np.testing.assert_allclose(model.hover_source.data[f'field_{branch}'], values.ravel(), equal_nan=True)
            # Filtering delegates scaling to the ordinary plotting routine.
            limits = (-80., 80.) if field == 'phase' else model._pipeline_kz_limits(multiplied)
            assert (model.mapper.low, model.mapper.high) == limits
        np.testing.assert_array_equal(model.hover_source.data['transmission'], model.transmission.ravel())


def test_remove_button_and_filter_sliders_use_cached_tabs_without_solving(app):
    '''
    Purpose
    -------
    Verify remove button and filter sliders use cached tabs without solving.

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

    first = calculate(app, 0)
    second = calculate(app, 5)
    baseline = first.image_sources[0].data['image'][0].copy()
    source_ids = [source.id for source in first.image_sources]
    with patch.object(app.vesa, 'compute_diagram', side_effect=AssertionError('Filter edit ran root solver')):
        app.apply_filter.active = True
        previous = first.transmission.copy()
        for key in app.filter.sliders:
            app.filter.sliders[key].value += .5
            app.filter._perform_recompute()
            assert not np.array_equal(first.transmission, previous)
            previous = first.transmission.copy()
            np.testing.assert_array_equal(second.transmission,
                compute_diagram_filter(second.last_result.kh_mm_inv, second.last_result.nu_mhz,
                    app.filter.geometry, **app.filter._current_parameters()))
        app.remove_filter._trigger_event(ButtonClick(model=app.remove_filter))
        assert not app.apply_filter.active
        app.remove_filter._trigger_event(ButtonClick(model=app.remove_filter))
    np.testing.assert_allclose(first.image_sources[0].data['image'][0], baseline, equal_nan=True)
    assert [source.id for source in first.image_sources] == source_ids
    assert 'cache' not in first.status.text.lower()
    assert "Updated in" not in first.status.text


def test_filter_survives_model_parameter_field_and_resolution_changes(app):
    '''
    Purpose
    -------
    Verify filter survives model parameter field and resolution changes.

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

    app.apply_filter.active = True
    model = calculate(app, 5)
    model.widgets['cs'].value += .5
    model._perform_recompute()
    model.field_select.value = 'kz_real'
    model.custom_kh.value = '10'
    model.custom_nu.value = '12'
    model.resolution_select.value = 'custom'
    model._perform_recompute()
    assert model.transmission.shape == model.image_sources[0].data['image'][0].shape == (12, 10)
    assert len(model.hover_source.data['transmission']) == len(model.hover_source.data['kh']) == 120
    with patch.object(app.vesa, 'compute_diagram', side_effect=AssertionError('Δz ran root solver')):
        model.widgets['dz'].value += 5.
    assert model.last_result is not None
    raw = model.last_result.kz_real[:, :, 0] * model.transmission
    raw[model.last_result.numerical_warning_mask] = np.nan
    np.testing.assert_allclose(model.image_sources[0].data['image'][0], raw, equal_nan=True)


def test_failures_clear_diagrams_and_do_not_break_other_models(app):
    '''
    Purpose
    -------
    Verify failures clear diagrams and do not break other models.

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

    model = calculate(app, 5)
    app.apply_filter.active = True
    with patch.object(app.vesa, 'compute_diagram', side_effect=ValueError('bad model')):
        model._perform_recompute()
    assert model.last_result is None
    app.filter._perform_recompute()
    assert all(len(values) == 0 for values in model.hover_source.data.values())
    good = calculate(app, 0)
    with patch('gaussian_filter_explorer.compute_filter_result', side_effect=ValueError('bad filter')):
        app.filter._perform_recompute()
    assert app.filter_result is None and good.transmission is None
    assert app.filter.error_label.visible
    app.filter._perform_recompute()
    assert app.filter_result is not None and np.max(good.transmission) > 0.


def test_sessions_keep_filter_and_toggle_state_independent(app):
    '''
    Purpose
    -------
    Verify sessions keep filter and toggle state independent.

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

    other = explorer.build_document(Document(), schedule_initial=False)
    model = calculate(app, 5)
    other_model = calculate(other, 5)
    original = other_model.transmission.copy()
    app.apply_filter.active = True
    app.filter.sliders['central_k'].value += 1.
    app.filter._perform_recompute()
    assert not other.apply_filter.active
    np.testing.assert_array_equal(other_model.transmission, original)
    assert not np.array_equal(model.transmission, original)


def test_frequency_controls_display_mhz_and_preserve_native_state(app):
    '''
    Purpose
    -------
    Verify frequency controls display mhz and preserve native state.

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

    from bokeh_ui_helpers import to_mhz, from_mhz
    for section in app.models:
        for key in ('N2', 'wac'):
            if key not in section.widgets:
                continue
            native = section.widgets[key]
            control = section.numeric_controls[key]
            assert '[mHz]' in control.label.text
            assert control.slider.value == pytest.approx(to_mhz(key, native.value))
            control.input.value = '-3.5' if key == 'N2' else '5.2'
            expected = from_mhz(key, float(control.input.value))
            assert native.value == pytest.approx(expected)
            assert section._current_values()[key] == pytest.approx(expected)
            for other in app.models:
                if key in other.widgets:
                    assert other.widgets[key].value == pytest.approx(expected)
                    assert other.numeric_controls[key].slider.value == pytest.approx(to_mhz(key, expected))
            section._restore_defaults()
            assert control.slider.value == pytest.approx(to_mhz(key, native.value))
