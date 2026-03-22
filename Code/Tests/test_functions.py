import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Code.Theory import config as cfg  # noqa: E402
from Code.Theory import functions as fn  # noqa: E402


KH_VALUES = np.array([0.05, 0.1, 0.2], dtype=float)
OMEGA_VALUES = np.array(
    [
        0.005,
        0.010000000000000002,
        0.015000000000000003,
        0.020000000000000004,
        0.025000000000000005,
        0.030000000000000006,
        0.035,
        0.04,
        0.045000000000000005,
        0.05,
    ],
    dtype=float,
)

OMEGA_SAMPLE = 0.02
KH_SAMPLE = 0.1
KZ_SAMPLE = 0.05

RTOL = 1e-9
ATOL = 1e-12


GOLDEN = {
    "sf1966": {
        "omega_poly": 5.576321893491126e-06,
        "kz_poly": -0.011440804733727815,
        "fmode": [0.11704699910719626, 0.1655294535724685, 0.23409399821439253],
        "omega_solve": [0.03095133064771714, 0.0, 0.0, 0.0],
        "kz_solve": [
            [-0.6108912282085672, 0.6108912282085673],
            [-0.2928934347208283, 0.2928934347208283],
            [-0.1804602036190207, 0.1804602036190207],
            [-0.11807118502720215, 0.11807118502720215],
            [-0.0729549183972074, 0.0729549183972074],
            [-0.025364140351091524, 0.025364140351091524],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
        ],
    },
    "mt1981": {
        "omega_poly": 5.576321893491126e-06,
        "kz_poly": -0.011440804733727815,
        "omega_solve": [0.03095133064771714, 0.0, 0.0, 0.0],
        "kz_solve": [
            [-0.6108912282085672, 0.6108912282085672],
            [-0.2928934347208283, 0.2928934347208283],
            [-0.1804602036190207, 0.1804602036190207],
            [-0.11807118502720217, 0.11807118502720217],
            [-0.07295491839720739, 0.07295491839720739],
            [-0.0253641403510915, 0.0253641403510915],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
        ],
    },
    "mt1982": {
        "omega_poly": 22.68911873030399,
        "kz_poly": -0.010636378452299821,
        "omega_solve": [0.0, 0.03082635120595743, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "kz_solve": [
            [-0.4719985337635251, 0.4719985337635251],
            [-0.2678497684473178, 0.2678497684473177],
            [-0.17228575015539943, 0.17228575015539943],
            [-0.11461404125321714, 0.11461404125321714],
            [-0.07179287345465254, 0.07179287345465254],
            [-0.03253308779272779, 0.03253308779272779],
            [-0.011033508840563682, 0.011033508840563682],
            [-0.005719018107000036, 0.005719018107000037],
            [-0.00354220117042983, 0.00354220117042983],
            [-0.0023946819756696263, 0.0023946819756696263],
        ],
    },
    "bunte1993": {
        "omega_poly": -462567.87168178504,
        "kz_poly": 0.012658861766494561,
        "omega_solve": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "kz_solve": [
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
        ],
    },
    "nc2009": {
        "omega_poly": -0.0008680423523165586,
        "kz_poly": -0.001669078577899235,
        "omega_solve": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "kz_solve": [
            [-0.44586922722515704, -0.4230208415311669, 0.0, 0.0, 0.0, 0.0],
            [-0.4573439184709108, -0.45150705572992295, -0.4184313308515504, -0.4115530084894448, 0.0, 0.0],
            [-0.4689323684516791, -0.46540277444402467, -0.40450087152319314, -0.40000548095802607, 0.0, 0.0],
            [-0.4806695350092517, -0.47767585866159606, -0.39214428921955574, -0.3883606477836665, 0.0, 0.0],
            [-0.4925107998241973, -0.4893859081716998, -0.3803321320069808, -0.3766331664653267, 0.0, 0.0],
            [-0.5043866553085495, -0.5008513286175963, -0.36878242313359294, -0.36485636544439454, 0.0, 0.0],
            [-0.5162609072471097, -0.5122035075679581, -0.35737203103630866, -0.3530585029089247, 0.0, 0.0],
            [-0.5281228410070608, -0.523498073799619, -0.3460403077876286, -0.34125571260710913, 0.0, 0.0],
            [-0.5399713539345945, -0.5347602356186122, -0.33475597515077304, -0.3294556595689179, 0.0, 0.0],
            [-0.5518080273882116, -0.5460025499126329, -0.3235021197543222, -0.3176617195737505, 0.0, 0.0],
        ],
    },
}


def _make_diag(model: str) -> fn.DiagnosticDiagram:
    kh_grid, omega_grid = np.meshgrid(KH_VALUES, OMEGA_VALUES)
    return fn.DiagnosticDiagram(kh_grid, omega_grid, cfg.params[model])


@pytest.mark.parametrize("model", ["sf1966", "mt1981", "mt1982", "bunte1993", "nc2009"])
def test_omega_poly_matches_golden(model: str):
    diag = _make_diag(model)
    result = diag.omega_poly(OMEGA_SAMPLE, KH_SAMPLE)
    np.testing.assert_allclose(result, GOLDEN[model]["omega_poly"], rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("model", ["sf1966", "mt1981", "mt1982", "bunte1993", "nc2009"])
def test_kz_poly_matches_golden(model: str):
    diag = _make_diag(model)
    result = diag.kz_poly(KZ_SAMPLE, OMEGA_SAMPLE, KH_SAMPLE)
    np.testing.assert_allclose(result, GOLDEN[model]["kz_poly"], rtol=RTOL, atol=ATOL)


def test_fmode_dispersion_matches_golden():
    diag = _make_diag("sf1966")
    np.testing.assert_allclose(diag.fmode_dispersion(), GOLDEN["sf1966"]["fmode"], rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("model", ["sf1966", "mt1981", "mt1982", "bunte1993", "nc2009"])
def test_omega_solve_matches_golden(model: str):
    diag = _make_diag(model)
    result = diag.omega_solve(KH_SAMPLE)
    np.testing.assert_allclose(result, GOLDEN[model]["omega_solve"], rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("model", ["sf1966", "mt1981", "mt1982", "bunte1993", "nc2009"])
def test_kz_solve_matches_golden(model: str):
    diag = _make_diag(model)
    result = diag.kz_solve(KH_SAMPLE)
    np.testing.assert_allclose(result, GOLDEN[model]["kz_solve"], rtol=RTOL, atol=ATOL)


def test_phase_speed_and_difference():
    omega = np.array([0.01, 0.02], dtype=float)
    kz = np.array([0.1, -0.2], dtype=float)
    diag = _make_diag("sf1966")
    v_phase = diag.phase_speed(omega, kz)
    np.testing.assert_allclose(v_phase, np.array([0.1, -0.1]), rtol=RTOL, atol=ATOL)

    delta_phi = diag.phase_difference(omega, v_phase, dz=150.0)
    np.testing.assert_allclose(delta_phi, np.array([15.0, -30.0]), rtol=RTOL, atol=ATOL)


def test_kz_poly_complex_branch_a0():
    kh_grid, omega_grid = np.meshgrid(KH_VALUES, OMEGA_VALUES)
    params = dict(cfg.params["bunte1993"])
    params["a"] = 0.0
    diag = fn.DiagnosticDiagram(kh_grid, omega_grid, params)
    result = diag.kz_poly(KZ_SAMPLE, OMEGA_SAMPLE, KH_SAMPLE)
    expected = -0.0393259691799348 + 0.011811340556245359j
    np.testing.assert_allclose(result, expected, rtol=RTOL, atol=ATOL)


def test_init_rejects_non_meshgrid():
    kh_grid = np.array([[0.05, 0.1], [0.2, 0.3]], dtype=float)
    omega_grid = np.array([[0.01, 0.01], [0.02, 0.02]], dtype=float)
    with pytest.raises(ValueError, match="kh_grid"):
        fn.DiagnosticDiagram(kh_grid, omega_grid, cfg.params["sf1966"])


def test_kz_poly_rejects_zero_omega():
    diag = _make_diag("sf1966")
    with pytest.raises(ValueError, match="omega must be non-zero"):
        diag.kz_poly(0.1, 0.0, 0.1)


def test_omega_solve_requires_scalar_kh():
    diag = _make_diag("sf1966")
    with pytest.raises(ValueError, match="kh must be a scalar"):
        diag.omega_solve(np.array([0.1, 0.2]))


def test_phase_difference_rejects_non_scalar_dz():
    diag = _make_diag("sf1966")
    with pytest.raises(ValueError, match="dz must be a scalar"):
        diag.phase_difference(0.01, 0.1, dz=np.array([150.0]))


def test_kz_solve_rejects_complex_polynomial():
    kh_grid, omega_grid = np.meshgrid(KH_VALUES, OMEGA_VALUES)
    params = dict(cfg.params["bunte1993"])
    params["a"] = 0.0
    diag = fn.DiagnosticDiagram(kh_grid, omega_grid, params)
    with pytest.raises(ValueError, match="complex values"):
        diag.kz_solve(KH_SAMPLE)
