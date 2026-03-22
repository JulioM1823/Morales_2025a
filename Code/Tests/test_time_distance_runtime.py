import copy
import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_PATH = ROOT / "Code" / "Time-Distance" / "time_distance.py"
CONFIG_PATH = ROOT / "Code" / "Time-Distance" / "config.py"
AGW_FILTER_PATH = ROOT / "Code" / "Time-Distance" / "agw_filter.py"


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


td = _load_module("time_distance_runtime_under_test", TIME_DISTANCE_PATH)
config_module = _load_module("time_distance_config_runtime_under_test", CONFIG_PATH)
agw_filter_module = _load_module("agw_filter_runtime_under_test", AGW_FILTER_PATH)


def _legacy_xcorrj_reference(v1, v2, *, width, dx_pixels, dx_Mm, dt, maxdist_Mm):
    nt, ny0, nx0 = v1.shape
    lower = np.transpose(v1, (1, 2, 0))
    higher = np.transpose(v2, (1, 2, 0))
    fft_lower = np.fft.fft(lower, axis = 2)
    fft_higher = np.fft.fft(higher, axis = 2)

    requested_maxpix = int(np.floor(maxdist_Mm/dx_Mm))
    maxpix_geom = int(np.floor((min(nx0, ny0) - 4*width - 3)/2))
    maxpix = min(requested_maxpix, maxpix_geom)
    extent = np.arange(-width, width + 1, dtype = int)
    deltas = np.arange(0, maxpix + 1, dtype = int)

    results = []
    x0 = nx0 // 2
    y0 = ny0 // 2
    xgrid, ygrid = np.meshgrid(np.arange(-nx0 // 2, nx0 // 2), np.arange(-ny0 // 2, ny0 // 2))
    fullgrid = np.hypot(xgrid, ygrid)
    center = fullgrid.shape[0] // 2

    for delta in deltas:
        bsize = int(np.floor((min(nx0, ny0) - 2*delta - 1)/2) - (2*width + 1))
        ntarg = 2*bsize + 1
        bigbox = np.zeros((ny0, nx0), dtype = bool)
        bigbox[y0 - bsize:y0 + bsize + 1, x0 - bsize:x0 + bsize + 1] = True
        box = np.flatnonzero(bigbox.flatten(order = "F"))
        xcorr_ann = np.zeros((box.size, nt), dtype = np.complex128)
        phase_diff_ann = np.zeros((box.size, nt), dtype = np.float64)

        annulus_offsets = []
        for offset in extent:
            yy, xx = np.nonzero(
                ((delta + offset - dx_pixels/2.0) < fullgrid)
                & (fullgrid <= (delta + offset + dx_pixels/2.0))
            )
            annulus_offsets.append((yy - center, xx - center))

        for i, box_index in enumerate(box):
            indy, indx = np.unravel_index(int(box_index), bigbox.shape, order = "F")
            phi1 = fft_lower[indy, indx, :]
            phiann = np.zeros((extent.size, nt), dtype = np.complex128)

            for irad, (yy_shift, xx_shift) in enumerate(annulus_offsets):
                yy = yy_shift + indy
                xx = xx_shift + indx
                phiann[irad, :] = fft_higher[yy, xx, :].mean(axis = 0)

            phi2 = phiann.mean(axis = 0)
            xcorr_ann[i, :] = np.fft.ifft(np.conj(phi1)*phi2)
            phi1_phase = phi1 - phi1.mean()
            phi2_phase = phi2 - phi2.mean()
            phase_diff_ann[i, :] = np.rad2deg(np.angle(np.fft.fftshift(phi1_phase*np.conj(phi2_phase))))

        xcorr_ann = np.fft.fftshift(xcorr_ann, axes = 1)
        xcorr_ann = np.reshape(xcorr_ann, (ntarg, ntarg, nt), order = "F")
        phase_diff_ann = np.reshape(phase_diff_ann, (ntarg, ntarg, nt), order = "F")
        xc = xcorr_ann.mean(axis = 1).mean(axis = 0).real
        phase_diff = phase_diff_ann.mean(axis = 1).mean(axis = 0)
        results.append((delta, xc, phase_diff))

    radii_pixels = np.array([item[0] for item in results], dtype = np.float64)
    xc = np.array([item[1] for item in results], dtype = np.float64)
    phase_diff = np.array([item[2] for item in results], dtype = np.float64)
    time_lags = ((np.arange(xc.shape[1]) - xc.shape[1]//2)*dt).astype(np.float64)
    frequencies = np.fft.fftshift(np.fft.fftfreq(xc.shape[1], d = dt))*1.0e3

    return xc, phase_diff, radii_pixels, time_lags, frequencies


def _legacy_azimuthal_average_fft_complex_oana(mid_time, end_time, array, mid_space, radial_meshgrid):
    if end_time % 2 == 0:
        azim = np.zeros([mid_space, mid_time], dtype = np.complex128)
    else:
        azim = np.zeros([mid_space, mid_time + 1], dtype = np.complex128)

    copied_array = np.array(array, copy = True)
    annulus_half_width = 0.5

    for j in range(mid_time, end_time):
        arr_product = copied_array[:, :, j]

        for k in range(1, int(mid_space) + 1):
            desired_condition = np.logical_and(
                radial_meshgrid >= k - annulus_half_width,
                radial_meshgrid < k + annulus_half_width)
            indices = np.nonzero(np.ravel(desired_condition == True, order = "C"))[0]
            flat_array = arr_product.flatten(order = "C")
            azim[k - 1, j - int(mid_time)] = np.mean(flat_array[indices])

    return azim


def test_xcorrj_matches_legacy_reference_small_cube():
    rng = np.random.default_rng(21)
    v1 = rng.standard_normal((24, 20, 20))
    v2 = rng.standard_normal((24, 20, 20))

    config = copy.deepcopy(td.load_time_distance_config(CONFIG_PATH))
    config["data"]["paired_cubes"]["p_dx_Mm"] = 0.5
    config["data"]["paired_cubes"]["dt"] = 1.0
    config["data"]["paired_cubes"]["delta_z_km"] = 100.0
    config["time_distance"]["width"] = 0
    config["time_distance"]["maxdist_Mm"] = 2.0
    config["time_distance"]["nworkers"] = 1

    pipeline = td.TimeDistance(td.prepare_runtime_config(config))
    result = pipeline.xcorrj(v1, v2)
    reference = _legacy_xcorrj_reference(
        v1,
        v2,
        width = 0,
        dx_pixels = 1.0,
        dx_Mm = 0.5,
        dt = 1.0,
        maxdist_Mm = 2.0,
    )

    for result_array, reference_array in zip(result, reference):
        np.testing.assert_allclose(result_array, reference_array, rtol = 1.0e-12, atol = 1.0e-12)


def test_azimuthal_average_fft_complex_oana_matches_legacy_reference():
    rng = np.random.default_rng(8)
    array = rng.standard_normal((24, 24, 15)) + 1j*rng.standard_normal((24, 24, 15))
    mid_time = array.shape[2] // 2
    mid_space = min(array.shape[:2]) // 2
    x = np.linspace(-mid_space, mid_space - 1, min(array.shape[:2]), dtype = np.float64)
    y = np.linspace(-mid_space, mid_space - 1, min(array.shape[:2]), dtype = np.float64)
    x_grid, y_grid = np.meshgrid(x, y)
    radial_meshgrid = np.hypot(x_grid, y_grid)

    result = td.azimuthal_average_fft_complex_oana(
        mid_time,
        array.shape[2],
        array,
        mid_space,
        radial_meshgrid,
    )
    reference = _legacy_azimuthal_average_fft_complex_oana(
        mid_time,
        array.shape[2],
        array,
        mid_space,
        radial_meshgrid,
    )

    np.testing.assert_allclose(result, reference, rtol = 1.0e-12, atol = 1.0e-12)


def test_load_magnetograms_reuses_shared_cube(tmp_path):
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "cube_v1.fits"),
        v2_path = str(tmp_path / "cube_v2.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
        magnetogram_v1 = str(tmp_path / "shared_hmimag.fits"),
        magnetogram_v2 = str(tmp_path / "shared_hmimag.fits"),
    )

    runtime_config = td.prepare_runtime_config(config)
    agw_filter = agw_filter_module.AGWFilter(runtime_config)
    load_calls = []

    def _fake_load_cube(file_path):
        load_calls.append(str(Path(file_path).resolve()))
        return np.ones((2, 2, 2), dtype = np.float64)

    agw_filter.load_cube = _fake_load_cube
    magnetogram_v1, magnetogram_v2 = agw_filter.load_magnetograms()

    assert load_calls == [str((tmp_path / "shared_hmimag.fits").resolve())]
    np.testing.assert_allclose(magnetogram_v1, magnetogram_v2, rtol = 0.0, atol = 0.0)
