import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_DIR = ROOT / "Code" / "Time-Distance"
if str(TIME_DISTANCE_DIR) not in sys.path:
    sys.path.insert(0, str(TIME_DISTANCE_DIR))

import time_distance as tdp  # noqa: E402


def test_fast_matches_baseline_xcorr_small_cube():
    rng = np.random.default_rng(7)
    v1 = rng.standard_normal((24, 24, 24), dtype=np.float32)
    v2 = rng.standard_normal((24, 24, 24), dtype=np.float32)
    skips = [4.0, 6.0]

    for width in (0, 1):
        base = tdp.time_distance_baseline(
            v1,
            v2,
            skip_distances=skips,
            width=width,
            n_jobs=1,
            normalize=False,
            legacy_axis_swap=True,
        )
        fast = tdp.time_distance_fast(
            v1,
            v2,
            skip_distances=skips,
            width=width,
            normalize=False,
            legacy_axis_swap=True,
            phase_average_mode="legacy",
            time_chunk=12,
        )

        np.testing.assert_allclose(base.xcorr, fast.xcorr, rtol=1e-5, atol=1e-5)


def test_lag_axis_matches_fftshift_convention():
    nt = 8
    dt = 30.0
    lag = tdp.lag_axis_minutes(nt, dt)
    expected = np.array([-4, -3, -2, -1, 0, 1, 2, 3], dtype=float) * dt / 60.0
    np.testing.assert_allclose(lag, expected, rtol=0.0, atol=0.0)


def test_synthetic_known_delay_peak():
    lag_samples = 3
    v1, v2 = tdp.synthetic_delay_cube(
        nt=64,
        ny=32,
        nx=32,
        lag_samples=lag_samples,
        noise_std=0.0,
        seed=1,
    )
    result = tdp.time_distance_fast(
        v1,
        v2,
        skip_distances=[0.0],
        width=0,
        normalize=False,
        legacy_axis_swap=True,
        phase_average_mode="cross_mean",
        time_chunk=32,
    )

    # Annulus A is index 4 in DIRECTION_ORDER.
    recovered = tdp.peak_lag_from_xcorr(result.xcorr[4, 0, :])
    assert recovered == lag_samples


def test_trim_spatial_zero_nan_borders_removes_invalid_edges():
    rng = np.random.default_rng(9)
    v1 = rng.standard_normal((8, 12, 12), dtype=np.float32)
    v2 = rng.standard_normal((8, 12, 12), dtype=np.float32)

    # Outer border is invalid by construction.
    v1[:, 0, :] = 0.0
    v1[:, -1, :] = np.nan
    v1[:, :, 0] = 0.0
    v1[:, :, -1] = np.nan

    v2[:, 0, :] = np.nan
    v2[:, -1, :] = 0.0
    v2[:, :, 0] = np.nan
    v2[:, :, -1] = 0.0

    trimmed_v1, trimmed_v2 = tdp.trim_spatial_zero_nan_borders(v1, v2)
    assert trimmed_v1.shape == (8, 10, 10)
    assert trimmed_v2.shape == (8, 10, 10)

    def _is_all_zero_or_nan(edge_cube: np.ndarray) -> bool:
        return bool(np.all(~np.isfinite(edge_cube) | (edge_cube == 0.0)))

    assert not _is_all_zero_or_nan(trimmed_v1[:, 0, :])
    assert not _is_all_zero_or_nan(trimmed_v1[:, -1, :])
    assert not _is_all_zero_or_nan(trimmed_v1[:, :, 0])
    assert not _is_all_zero_or_nan(trimmed_v1[:, :, -1])
    assert not _is_all_zero_or_nan(trimmed_v2[:, 0, :])
    assert not _is_all_zero_or_nan(trimmed_v2[:, -1, :])
    assert not _is_all_zero_or_nan(trimmed_v2[:, :, 0])
    assert not _is_all_zero_or_nan(trimmed_v2[:, :, -1])


def test_fast_auto_trim_matches_manual_trim():
    rng = np.random.default_rng(13)
    v1 = rng.standard_normal((24, 24, 24), dtype=np.float32)
    v2 = rng.standard_normal((24, 24, 24), dtype=np.float32)

    v1[:, 0, :] = 0.0
    v1[:, -1, :] = np.nan
    v1[:, :, 0] = 0.0
    v1[:, :, -1] = np.nan

    v2[:, 0, :] = np.nan
    v2[:, -1, :] = 0.0
    v2[:, :, 0] = np.nan
    v2[:, :, -1] = 0.0

    skips = [4.0, 6.0]
    auto = tdp.time_distance_fast(
        v1,
        v2,
        skip_distances=skips,
        width=0,
        normalize=False,
        legacy_axis_swap=True,
        phase_average_mode="legacy",
        time_chunk=12,
    )

    manual = tdp.time_distance_fast(
        v1[:, 1:-1, 1:-1],
        v2[:, 1:-1, 1:-1],
        skip_distances=skips,
        width=0,
        normalize=False,
        legacy_axis_swap=True,
        phase_average_mode="legacy",
        time_chunk=12,
        trim_zero_nan_borders=False,
    )

    np.testing.assert_allclose(auto.xcorr, manual.xcorr, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(auto.phase, manual.phase, rtol=1e-5, atol=1e-5)


def test_baseline_auto_trim_matches_manual_trim():
    rng = np.random.default_rng(17)
    v1 = rng.standard_normal((16, 20, 20), dtype=np.float32)
    v2 = rng.standard_normal((16, 20, 20), dtype=np.float32)

    v1[:, 0, :] = 0.0
    v1[:, -1, :] = np.nan
    v1[:, :, 0] = 0.0
    v1[:, :, -1] = np.nan

    v2[:, 0, :] = np.nan
    v2[:, -1, :] = 0.0
    v2[:, :, 0] = np.nan
    v2[:, :, -1] = 0.0

    skips = [3.0]
    auto = tdp.time_distance_baseline(
        v1,
        v2,
        skip_distances=skips,
        width=0,
        n_jobs=1,
        normalize=False,
    )

    manual = tdp.time_distance_baseline(
        v1[:, 1:-1, 1:-1],
        v2[:, 1:-1, 1:-1],
        skip_distances=skips,
        width=0,
        n_jobs=1,
        normalize=False,
        trim_zero_nan_borders=False,
    )

    np.testing.assert_allclose(auto.xcorr, manual.xcorr, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(auto.phase, manual.phase, rtol=1e-5, atol=1e-5)
