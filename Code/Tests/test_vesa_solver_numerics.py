'''
Purpose
-------
Numerical regression checks for the Vesa_2026 solver used by this project.

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
import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
VESA_DIR = ROOT.parent / "Vesa_2026" / "Code" / "diagnostic_diagram"


def _load(name: str):
    '''
    Purpose
    -------
    Import the selected on-disk module under the isolated name used by the test.

    Inputs
    ------
    name: str
        Module, callback, variable, or context label selected by the caller.

    Outputs
    -------
    module: types.ModuleType
        Executed module exposing the implementation under test. Where present,
        register it in sys.modules before loader execution.
    '''

    # Create and execute an isolated import of the on-disk implementation module.
    path = VESA_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"vesa_solver_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


functions = _load("functions")
config = _load("config")


def _diagram(model: str, *, omega=0.01, kh=0.003, **changes):
    '''
    Purpose
    -------
    Construct a one-point Vesa diagnostic with optional model-parameter overrides.

    Inputs
    ------
    model: str
        Dispersion model identifier selected for the parameterized case.

    omega: float
        Angular-frequency sample (rad/s).

    kh: float or array-like
        Horizontal-wavenumber sample or test axis, in the units of the tested API.

    **changes: dict
        Overrides applied to the baseline parameter or processing configuration.

    Outputs
    -------
    diagram: DiagnosticDiagram
        Model initialized on the supplied kh and omega samples.
    '''

    params = dict(config.params[model])
    params.update(changes)
    kh_grid, omega_grid = np.meshgrid([kh], [omega])
    return functions.DiagnosticDiagram(kh_grid, omega_grid, params)


@pytest.mark.parametrize(
    ("coefficients", "expected"),
    [
        ([1.0, 0.0, -1e12], 1e6),
        ([1.0, 0.0, -1e-12], 1e-6),
        ([1e-24, 0.0, -1.0], 1e12),
    ],
)
def test_kz_variable_scaling_keeps_all_roots_across_scales(coefficients, expected):
    '''
    Purpose
    -------
    Verify k_z variable scaling keeps all roots across scales.

    Inputs
    ------
    coefficients: sequence
        Polynomial coefficients used by the root-scaling test.

    expected: object
        Reference value supplied by the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    diagram = _diagram("mt1981")
    diagram.kz_coefficients = lambda omega, kh: np.array(coefficients)

    roots, info = diagram._solve_kz_roots_at_point(0.01, 0.003, return_info=True)

    np.testing.assert_allclose(np.sort(roots.real), [-expected, expected], rtol=1e-12)
    assert info["effective_degree"] == 2
    assert not info["degree_reduced"]
    assert not info["solver_failed"]


def test_horizontal_alfven_field_reports_no_isolated_kz_roots():
    '''
    Purpose
    -------
    Verify horizontal alfven field reports no isolated k_z roots.

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

    diagram = _diagram("alfven_mode", a=3.0, theta=np.pi / 2, phi=0.0)

    roots, info = diagram._solve_kz_roots_at_point(0.01, 0.003, return_info=True)
    assert np.isnan(roots).all()
    assert info["effective_degree"] == 0
    assert info["degree_reduced"]
    assert not info["solver_failed"]

    _, resonant_info = diagram._solve_kz_roots_at_point(3.0 * 0.003, 0.003, return_info=True)
    assert resonant_info["zero_polynomial"]
    assert resonant_info["solver_failed"]


def test_zero_field_slow_fast_degree_reduction_preserves_acoustic_roots():
    '''
    Purpose
    -------
    Verify zero field slow fast degree reduction preserves acoustic roots.

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

    diagram = _diagram("slow_fast_mode", a=0.0)
    roots, info = diagram._solve_kz_roots_at_point(0.01, 0.003, return_info=True)

    assert info["effective_degree"] == 2
    assert info["degree_reduced"]
    assert not info["solver_failed"]
    assert np.count_nonzero(np.isfinite(roots)) == 2


def test_residual_uses_actual_polynomial_terms():
    '''
    Purpose
    -------
    Verify residual uses actual polynomial terms.

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

    diagram = _diagram("mt1981")
    diagram.kz_coefficients = lambda omega, kh: np.array([1.0, 0.0, -1e-6])
    roots = np.array([[[0.0 + 0.0j, np.nan + 0.0j]]])

    residuals, _ = diagram.kz_root_quality(roots)

    assert residuals[0, 0, 0] == pytest.approx(1.0)


@pytest.mark.parametrize("model", list(config.params))
def test_representative_grid_has_complete_roots_and_small_term_residual(model):
    '''
    Purpose
    -------
    Verify representative grid has complete roots and small term residual.

    Inputs
    ------
    model: str
        Dispersion model identifier selected for the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    params = dict(config.params[model])
    if model in {"nc2009", "alfven_mode", "slow_fast_mode", "slow_mode", "fast_mode", "bunte1993"}:
        params["a"] = 3.0
        if "theta" in params:
            params["theta"] = np.deg2rad(30.0)
        if "phi" in params:
            params["phi"] = np.deg2rad(20.0)
        if model == "nc2009":
            params["ax"] = params["a"] * np.sin(params["theta"]) * np.cos(params["phi"])
            params["ay"] = params["a"] * np.sin(params["theta"]) * np.sin(params["phi"])
            params["az"] = params["a"] * np.cos(params["theta"])
    kh_grid, omega_grid = np.meshgrid(
        np.linspace(0.0, 0.007, 6),
        np.linspace(0.5, 10.0, 6) * 2 * np.pi * 1e-3,
    )
    diagram = functions.DiagnosticDiagram(kh_grid, omega_grid, params)

    roots, diagnostics = diagram.kz_solve_grid(return_diagnostics=True)

    assert np.isfinite(roots).all()
    assert not diagnostics["solve_failed_mask"].any()
    assert not diagnostics["degree_reduced_mask"].any()
    assert np.nanmax(diagnostics["max_root_residual"]) < 1e-10


def test_high_precision_cross_check_on_selected_point():
    '''
    Purpose
    -------
    Verify high precision cross check on selected point.

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

    pytest.importorskip("mpmath")
    diagram = _diagram("mt1981")
    roots = diagram._kz_solve_raw_grid()

    result = diagram.kz_validate_high_precision(
        roots, np.ones((1, 1), dtype=bool), digits=50
    )

    assert result["checked_mask"][0, 0]
    assert not result["failed_mask"][0, 0]
    assert result["max_relative_difference"][0, 0] < 1e-10


@pytest.mark.parametrize(
    ("theta", "phi"),
    [(0.0, 0.0), (np.deg2rad(35.0), 0.0), (np.deg2rad(70.0), np.deg2rad(43.0))],
)
def test_alfven_closed_form_branches_satisfy_original_relation(theta, phi):
    '''
    Purpose
    -------
    Verify alfven closed form branches satisfy original relation.

    Inputs
    ------
    theta: float
        Field inclination in the angular convention used by the tested API.

    phi: float
        Field azimuth in the angular convention used by the tested API.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    diagram = _diagram("alfven_mode", a=4.2, theta=theta, phi=phi)
    kh, omega = 0.006, 0.021

    roots = diagram._solve_kz_roots_at_point(omega, kh)
    mu, nu = np.sin(theta)*np.cos(phi), np.cos(theta)
    expected = -kh*mu/nu + np.array([-1.0, 1.0])*omega/(diagram.a*nu)

    np.testing.assert_allclose(np.sort(roots.real), np.sort(expected), rtol=1e-13)
    k_parallel = kh*mu + roots.real*nu
    residual = np.abs(omega**2 - diagram.a**2*k_parallel**2) / (
        omega**2 + diagram.a**2*k_parallel**2
    )
    assert np.max(residual) < 1e-13


@pytest.mark.parametrize(("model", "family"), [("slow_mode", -1), ("fast_mode", 1)])
def test_exact_magnetoacoustic_roots_are_classified_and_residual_small(model, family):
    '''
    Purpose
    -------
    Verify exact magnetoacoustic roots are classified and residual small.

    Inputs
    ------
    model: str
        Dispersion model identifier selected for the parameterized case.

    family: str
        Requested fast or slow magnetoacoustic family.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    params = dict(config.params[model])
    params.update(a=3.2, cs=7.8, theta=np.deg2rad(34.0), phi=np.deg2rad(27.0))
    kh_grid, omega_grid = np.meshgrid(
        np.linspace(0.001, 0.007, 7),
        np.linspace(0.6, 9.0, 7)*2*np.pi*1e-3,
    )
    diagram = functions.DiagnosticDiagram(kh_grid, omega_grid, params)

    roots, diagnostics = diagram.kz_solve_grid(return_diagnostics=True)
    complete_roots = diagnostics["tracked_all_roots"]

    assert roots.shape == (*kh_grid.shape, 2)
    assert complete_roots.shape == (*kh_grid.shape, 4)
    assert np.nanmax(diagnostics["normalized_magnetoacoustic_residual"]) < 1e-10
    assert np.nanmax(diagnostics["selected_normalized_dispersion_residual"]) < 1e-10
    assert np.any(diagnostics["mode_classification"] == family)
    selected = diagnostics["selected_root_indices"]
    for i, j, branch in np.ndindex(selected.shape):
        source = selected[i, j, branch]
        if source >= 0:
            assert diagnostics["mode_classification"][i, j, source] == family


@pytest.mark.parametrize("model", ["slow_mode", "fast_mode"])
def test_mode_results_are_invariant_to_root_order_and_grid_traversal(model, monkeypatch):
    '''
    Purpose
    -------
    Verify mode results are invariant to root order and grid traversal.

    Inputs
    ------
    model: str
        Dispersion model identifier selected for the parameterized case.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    params = dict(config.params[model])
    params.update(a=3.2, cs=7.8, theta=np.deg2rad(34.0), phi=np.deg2rad(27.0))
    kh_values = np.linspace(0.001, 0.007, 8)
    omega_values = np.linspace(0.6, 9.0, 8)*2*np.pi*1e-3
    kh_grid, omega_grid = np.meshgrid(kh_values, omega_values)
    baseline_diagram = functions.DiagnosticDiagram(kh_grid, omega_grid, params)
    baseline = baseline_diagram.kz_solve_grid()

    shuffled_diagram = functions.DiagnosticDiagram(kh_grid, omega_grid, params)
    solve_point = shuffled_diagram._solve_kz_roots_at_point

    def reverse_solver_order(omega, kh, **kwargs):
        '''
        Purpose
        -------
        Reverse raw solver slots while preserving optional solve diagnostics.

        Inputs
        ------
        omega: float
            Angular-frequency sample (rad/s).

        kh: float or array-like
            Horizontal-wavenumber sample or test axis, in the units of the tested API.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        result: np.array or tuple
            Reversed root array, or reversed roots paired with the original info
            dictionary.
        '''

        result = solve_point(omega, kh, **kwargs)
        if kwargs.get("return_info", False):
            roots, info = result
            return roots[::-1], info
        return result[::-1]

    monkeypatch.setattr(shuffled_diagram, "_solve_kz_roots_at_point", reverse_solver_order)
    reordered = shuffled_diagram.kz_solve_grid()
    np.testing.assert_allclose(reordered, baseline, rtol=1e-10, atol=1e-12, equal_nan=True)

    reverse_grid_diagram = functions.DiagnosticDiagram(kh_grid[::-1, ::-1], omega_grid[::-1, ::-1], params)
    reverse_grid = reverse_grid_diagram.kz_solve_grid()[::-1, ::-1]
    np.testing.assert_allclose(reverse_grid, baseline, rtol=1e-8, atol=1e-10, equal_nan=True)


def test_magnetoacoustic_eigenfrequencies_recover_low_and_high_beta_limits():
    '''
    Purpose
    -------
    Verify magnetoacoustic eigenfrequencies recover low and high beta limits.

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

    kh, kz = 0.004, -0.006
    theta, phi = np.deg2rad(38.0), np.deg2rad(25.0)
    k2 = kh**2 + kz**2
    k_parallel = kh*np.sin(theta)*np.cos(phi) + kz*np.cos(theta)
    ratio = k_parallel**2/k2

    def eigenfrequencies_squared(a, cs):
        '''
        Purpose
        -------
        Evaluate the fast and slow homogeneous-MHD squared-frequency eigenvalues.

        Inputs
        ------
        a: float
            Alfven speed (km/s).

        cs: float
            Sound speed (km/s).

        Outputs
        -------
        omega2_fast, omega2_slow: tuple of float
            Eigenvalues in s^-2 for the enclosing squared wavenumber and direction
            ratio.
        '''

        discriminant = (a**2 + cs**2)**2 - 4*a**2*cs**2*ratio
        split = np.sqrt(discriminant)
        return (
            0.5*k2*(a**2 + cs**2 + split),
            0.5*k2*(a**2 + cs**2 - split),
        )

    fast_low, slow_low = eigenfrequencies_squared(1.0e3, 1.0)
    assert fast_low/(1.0e6*k2) == pytest.approx(1.0, rel=1e-6)
    assert slow_low/(k_parallel**2) == pytest.approx(1.0, rel=1e-6)

    fast_high, slow_high = eigenfrequencies_squared(1.0, 1.0e3)
    assert fast_high/(1.0e6*k2) == pytest.approx(1.0, rel=1e-6)
    assert slow_high/(k_parallel**2) == pytest.approx(1.0, rel=1e-6)


def test_equipartition_parallel_degeneracy_is_preserved_as_ambiguous():
    '''
    Purpose
    -------
    Verify equipartition parallel degeneracy is preserved as ambiguous.

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

    diagram = _diagram("fast_mode", a=3.0, cs=3.0, theta=0.0, phi=0.0, kh=0.0)
    roots, diagnostics = diagram.kz_solve_grid(return_diagnostics=True)

    assert diagnostics["branch_degenerate_mask"].all()
    assert diagnostics["mode_ambiguous_mask"].all()
    assert np.isfinite(diagnostics["tracked_all_roots"]).any()
    assert not np.isfinite(roots).any()


def test_horizontal_field_reduces_magnetoacoustic_quartic_without_clipping():
    '''
    Purpose
    -------
    Verify horizontal field reduces magnetoacoustic quartic without clipping.

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

    diagram = _diagram(
        "fast_mode", a=3.0, cs=7.8, theta=np.pi/2, phi=np.deg2rad(35.0)
    )
    roots, info = diagram._solve_kz_roots_at_point(0.01, 0.003, return_info=True)

    assert info["effective_degree"] == 2
    assert info["degree_reduced"]
    assert not info["solver_failed"]
    finite = roots[np.isfinite(roots)]
    assert finite.size == 2
    residuals = diagram.kz_root_residuals(finite.reshape(1, 1, -1))
    assert np.nanmax(residuals) < 1e-10


def test_vertical_energy_direction_is_not_inferred_from_kz_sign():
    '''
    Purpose
    -------
    Verify vertical energy direction is not inferred from k_z sign.

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

    diagram = _diagram(
        "alfven_mode", a=3.0, theta=np.deg2rad(60.0), phi=0.0,
        kh=0.01, omega=0.01,
    )
    roots, diagnostics = diagram.kz_solve_grid(return_diagnostics=True)
    velocities = diagnostics["vertical_group_velocity_km_s"][0, 0]

    assert np.all(roots[0, 0].real < 0.0)
    assert set(np.sign(velocities[np.isfinite(velocities)])) == {-1.0, 1.0}


@pytest.mark.parametrize("model", ["slow_mode", "fast_mode"])
def test_nearly_horizontal_mode_is_not_masked_by_other_root_families(model):
    '''
    Purpose
    -------
    Verify nearly horizontal mode is not masked by other root families.

    Inputs
    ------
    model: str
        Dispersion model identifier selected for the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''
    params = dict(config.params[model])
    params.update(a=14.6, cs=7.05246440457191,
                  theta=np.deg2rad(-87.0), phi=np.deg2rad(0.26121180203181327))
    kh, omega = np.meshgrid(np.linspace(0.0, 0.008, 16),
                            np.linspace(0.0, 11.0, 24)*2*np.pi*1e-3)
    diagram = functions.DiagnosticDiagram(kh, omega, params)
    roots, diagnostics = diagram.kz_solve_grid(return_diagnostics=True)

    # Local frequency eigenvalues identify the requested pair independently
    # of the majority family assigned to an entire tracked root sheet.
    selected = diagnostics["selected_root_indices"]
    real_pair = np.all((selected >= 0)
                       & diagnostics["selected_propagating_root_mask"], axis=2)
    assert real_pair.any()
    assert not diagnostics["mode_ambiguous_mask"][real_pair].any()
    assert np.nanmax(diagnostics["selected_normalized_dispersion_residual"]) < 1e-8
    assert np.isfinite(roots[~diagnostics["mode_ambiguous_mask"]]).any()


@pytest.mark.parametrize("model", ["slow_mode", "fast_mode"])
def test_unresolved_requested_mode_pair_remains_masked(model):
    '''
    Purpose
    -------
    Verify unresolved requested mode pair remains masked.

    Inputs
    ------
    model: str
        Dispersion model identifier selected for the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    diagram = _diagram(model, a=3.0, cs=3.0, theta=0.0, phi=0.0, kh=0.0)
    roots, diagnostics = diagram.kz_solve_grid(return_diagnostics=True)

    assert not np.isfinite(roots).any()
    assert diagnostics["mode_ambiguous_mask"].all()
