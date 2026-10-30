'''
Purpose
-------
Bunte boundary consistency, finite sampling, and analytic solution sheets.

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
import importlib
from pathlib import Path
import sys
import warnings

import numpy as np
import pytest
from bokeh.document import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Time-Distance'))
from komega_explorer import CONFIG_FILE, _load_config, build_document, load_dispersion_explorer

vesa = load_dispersion_explorer(_load_config(CONFIG_FILE)['komega_comparison']['vesa_2026_dir'])
adapter = importlib.import_module(vesa.__package__ + '.interactive_models')


@pytest.mark.parametrize('speed', [0., 1e-8, 3., 40.])
def test_bunte_has_complete_stable_roots_and_verified_boundaries(speed):
    '''
    Purpose
    -------
    Verify bunte has complete stable roots and verified boundaries.

    Inputs
    ------
    speed: float
        Alfven-speed case in km/s.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    result = adapter.compute_diagram('bunte1993', {'a': speed}, (48, 56), use_cache=False)
    assert result.warnings == ()
    assert np.isfinite(result.phase_deg).all()
    assert np.isfinite(result.kz_real).all() and np.isfinite(result.kz_imag).all()
    assert result.summary['unmatched_boundary_points'] == 0
    assert result.summary['kz_solve_failed_cells'] == 0
    assert result.summary['max_kz_root_residual'] < 1e-12
    assert 0. < result.nu_mhz[0] < result.nu_mhz[-1] < 11.
    roots = result.kz_real + 1j * result.kz_imag
    np.testing.assert_allclose(roots[:, :, 0], -roots[:, :, 1])
    params = adapter.build_model_parameters('bunte1993', {'a': speed})
    diagram = adapter.DiagnosticDiagram(*np.meshgrid(result.kh_mm_inv*1e-3,
        result.nu_mhz * 2*np.pi*1e-3), params)
    # Run the actual solver outside the adapter's existing errstate/warning context.
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        actual, diagnostics = diagram.kz_quadratic_roots_grid(return_diagnostics=True)
    np.testing.assert_allclose(actual, roots)
    assert not diagnostics['uncertain_mask'].any()


def test_bunte_zero_field_is_continuous_with_the_nonzero_field_limit():
    '''
    Purpose
    -------
    Verify bunte zero field is continuous with the nonzero field limit.

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

    zero = adapter.compute_diagram('bunte1993', {'a': 0.}, (16, 18), use_cache=False)
    small = adapter.compute_diagram('bunte1993', {'a': 1e-8}, (16, 18), use_cache=False)
    np.testing.assert_allclose(zero.phase_deg, small.phase_deg, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(zero.kz_real, small.kz_real, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(zero.kz_imag, small.kz_imag, rtol=1e-12, atol=1e-12)


def test_bunte_height_update_matches_fresh_solve_on_the_corrected_coordinates():
    '''
    Purpose
    -------
    Verify bunte height update matches fresh solve on the corrected coordinates.

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

    result = adapter.compute_diagram('bunte1993', resolution=(16, 18), use_cache=False)
    values = dict(result.parameter_values, dz=300.)
    updated = adapter.update_diagram_postprocessing(result, values)
    fresh = adapter.compute_diagram('bunte1993', values, (16, 18), use_cache=False)
    np.testing.assert_allclose(updated.phase_deg, fresh.phase_deg)
    np.testing.assert_array_equal(updated.nu_mhz, result.nu_mhz)


def test_bunte_ui_runs_cleanly_with_filter_and_remove(monkeypatch):
    '''
    Purpose
    -------
    Verify bunte ui runs cleanly with filter and remove.

    Inputs
    ------
    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'interactive', (16, 18))
    app = build_document(Document(), schedule_initial=False)
    index = next(i for i, model in enumerate(app.models) if model.definition.key == "bunte1993")
    app.tabs.active = index
    model = app.models[index]
    model._perform_recompute()
    assert model.last_result.warnings == ()
    assert model.status.text == '' and not model.status.visible
    original = model.image_sources[0].data['image'][0].copy()
    app.apply_filter.active = True
    np.testing.assert_allclose(model.image_sources[0].data['image'][0], original * model.transmission)
    app.apply_filter.active = False
    np.testing.assert_allclose(model.image_sources[0].data['image'][0], original)
