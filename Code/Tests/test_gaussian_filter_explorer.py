'''
Purpose
-------
Regression checks for gaussian filter explorer.

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
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
from bokeh.document import Document
from bokeh.models import Slider, WheelZoomTool


MODULE_DIR = Path(__file__).resolve().parents[1] / "Time-Distance"
sys.path.insert(0, str(MODULE_DIR))

import gaussian_filter_explorer as explorer  # noqa: E402


def test_explorer_has_no_runtime_scipy_dependency():
    '''
    Purpose
    -------
    Verify explorer has no runtime scipy dependency.

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

    source = (MODULE_DIR / "gaussian_filter_explorer.py").read_text(encoding="utf-8")
    assert "import scipy" not in source
    assert "from scipy" not in source


def _load_legacy_filter_module():
    '''
    Purpose
    -------
    Load filter.py with a no-op tqdm when the test environment lacks it.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    module: types.ModuleType
        Executed filter module; temporary sys.modules entries are restored
        after the import context exits.
    '''

    # Stub only unavailable optional dependencies during the legacy-module import.
    injected_modules = {}
    try:
        import tqdm  # noqa: F401
    except ModuleNotFoundError:
        fake_tqdm = types.ModuleType("tqdm")
        fake_tqdm.tqdm = lambda iterable=None, *args, **kwargs: iterable
        injected_modules["tqdm"] = fake_tqdm

    try:
        import h5py  # noqa: F401
    except ModuleNotFoundError:
        injected_modules["h5py"] = types.ModuleType("h5py")

    with patch.dict(sys.modules, injected_modules):
        spec = importlib.util.spec_from_file_location(
            "morales_legacy_filter_validation", MODULE_DIR / "filter.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def test_defaults_are_read_from_the_active_configuration():
    '''
    Purpose
    -------
    Verify defaults are read from the active configuration.

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

    defaults = explorer.load_gaussian_defaults()
    config = explorer._load_config(explorer.CONFIG_FILE)
    configured = config["filtering"]["gaussian"]
    assert defaults == {
        key: float(configured[key]) for key in explorer.PARAMETER_KEYS
    }


def test_radial_slice_matches_existing_filter_calculation_per_k():
    '''
    Purpose
    -------
    Verify radial slice matches existing filter calculation per k.

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

    legacy = _load_legacy_filter_module()
    frequency = np.linspace(-8.0, 8.0, 81)
    kh = np.array([0.0, 0.75, 1.5, 3.0, 6.0])
    parameters = dict(central_k=1.5, width_k=4.0, central_f=3.0, width_f=3.0)
    actual = explorer.compute_gaussian_filter_slice(
        kh, frequency, **parameters
    )

    expected_rows = []
    for kh_value in kh:
        expected = legacy.create_filter(
            np.empty((1, 1, frequency.size)),
            frequency,
            np.array([kh_value]),
            np.array([0.0]),
            parameters["central_f"],
            parameters["width_f"],
            parameters["central_k"],
            parameters["width_k"],
        )
        expected_rows.append(expected[0, 0])
    np.testing.assert_allclose(actual, np.vstack(expected_rows), rtol=0.0, atol=1e-15)


def test_filter_is_finite_bounded_and_responds_to_every_parameter():
    '''
    Purpose
    -------
    Verify filter is finite bounded and responds to every parameter.

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

    geometry = explorer.PreviewGeometry(40, 81, 30.0, 0.16, "test grid")
    defaults = explorer.load_gaussian_defaults()
    baseline = explorer.compute_filter_result(geometry, **defaults).transmission
    assert baseline.shape == (41, 20)
    assert np.all(np.isfinite(baseline))
    assert np.min(baseline) >= 0.0
    assert np.max(baseline) <= 1.0

    changes = {
        "central_k": defaults["central_k"] + 0.5,
        "width_k": defaults["width_k"] + 0.5,
        "central_f": defaults["central_f"] + 0.5,
        "width_f": defaults["width_f"] + 0.5,
    }
    for key, value in changes.items():
        parameters = dict(defaults)
        parameters[key] = value
        changed = explorer.compute_filter_result(geometry, **parameters).transmission
        assert not np.allclose(changed, baseline, rtol=0.0, atol=0.0)


def test_bokeh_document_uses_four_sliders_and_updates_sources_in_place():
    '''
    Purpose
    -------
    Verify Bokeh document uses four sliders and updates sources in place.

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

    doc = Document()
    app = explorer.build_document(doc, schedule_initial=False)
    assert doc.validate() is None
    assert tuple(app.sliders) == explorer.PARAMETER_KEYS
    assert all(isinstance(slider, Slider) for slider in app.sliders.values())
    assert app.plot.title.text == "Gaussian Filter k–ω Diagram"
    assert app.plot.xaxis[0].axis_label == "kₕ [Mm⁻¹]"
    assert app.plot.yaxis[0].axis_label == "ν / 2π [mHz]"
    assert (app.plot.width, app.plot.height) == (760, 980)
    assert app.plot.toolbar.active_scroll is None
    assert any(isinstance(tool, WheelZoomTool) for tool in app.plot.tools)

    source_id = id(app.image_source)
    app._perform_recompute()
    baseline = np.asarray(app.image_source.data["image"][0]).copy()
    with patch.object(app, "schedule_recompute") as schedule:
        app.sliders["central_k"].value += 0.5
    schedule.assert_called_once_with()
    app._perform_recompute()
    changed = np.asarray(app.image_source.data["image"][0])
    assert id(app.image_source) == source_id
    assert not np.allclose(changed, baseline, rtol=0.0, atol=0.0)


def test_invalid_width_is_rejected_without_nan_output():
    '''
    Purpose
    -------
    Verify invalid width is rejected without nan output.

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

    kh = np.linspace(0.0, 7.0, 20)
    frequency = np.linspace(-10.0, 10.0, 41)
    with np.testing.assert_raises_regex(ValueError, "widths must be positive"):
        explorer.compute_gaussian_filter_slice(
            kh,
            frequency,
            central_k=1.5,
            width_k=0.0,
            central_f=3.0,
            width_f=3.0,
        )
