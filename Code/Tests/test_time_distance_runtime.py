import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_PATH = ROOT / "Code" / "Time-Distance" / "pipeline.py"
CONFIG_PATH = ROOT / "Code" / "Time-Distance" / "config.py"
AGW_FILTER_PATH = ROOT / "Code" / "Time-Distance" / "filter.py"


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


td = _load_module("time_distance_runtime_under_test", TIME_DISTANCE_PATH)
config_module = _load_module("time_distance_config_runtime_under_test", CONFIG_PATH)
agw_filter_module = _load_module("agw_filter_runtime_under_test", AGW_FILTER_PATH)


class _FakeNetCDFVariable:
    def __init__(self, name, data, dimensions):
        self.name = name
        self._data = np.asarray(data, dtype = np.float64)
        self.dimensions = tuple(dimensions)
        self.shape = self._data.shape
        self.ndim = self._data.ndim

    def __getitem__(self, item):
        return self._data[item]


class _FakeNetCDFDataset:
    def __init__(self, file_path):
        cube = np.arange(72, dtype = np.float64).reshape((4, 2, 3, 3))
        self._file_path = str(file_path)
        self.variables = {
            "v3": _FakeNetCDFVariable("v3", cube, ("t", "xc3", "xc2", "xc1")),
            "xc3": _FakeNetCDFVariable("xc3", np.array([0.0, 300.0], dtype = np.float64), ("xc3",)),
        }

    def filepath(self):
        return self._file_path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_config_does_not_define_magnetogram_paths():
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/dataset/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/dataset/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )

    assert not hasattr(config_module, "vesa_2025_magnetogram")
    assert "magnetogram_v1" not in config["filtering"]["magnetogram"]
    assert "magnetogram_v2" not in config["filtering"]["magnetogram"]
    assert config["filtering"]["magnetogram"]["enabled"] is False
    assert config["filtering"]["filter_sequence"] == ["gaussian"]
    assert "magnetogram" not in td.build_processing_slug(config)
    assert config["magnetogram_mode"] == {"single_cube": "bottom"}


def test_config_keeps_enabled_magnetogram_in_filter_sequence():
    filtering = copy.deepcopy(config_module.default_filtering)
    filtering["magnetogram"]["enabled"] = True
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/dataset/cube_v1.fits",
        v2_path = "/tmp/dataset/cube_v2.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
        filtering = filtering,
    )

    assert config["filtering"]["filter_sequence"] == ["magnetogram", "gaussian"]
    assert "magnetogram" in td.build_processing_slug(config)


def test_config_accepts_single_cube_per_height_pair_magnetogram_mode():
    config = config_module.get_config(
        source_type = "single_cube",
        file_path = "/tmp/simulation.nc",
        observable = "v3",
        h1 = 1,
        h2 = 2,
        magnetogram_mode = {"single_cube": "per_height_pair"},
    )

    assert config["magnetogram_mode"] == {"single_cube": "per_height_pair"}


def test_config_rejects_invalid_magnetogram_mode():
    with pytest.raises(ValueError, match = r"magnetogram_mode\['single_cube'\]"):
        config_module.get_config(
            source_type = "single_cube",
            file_path = "/tmp/simulation.nc",
            observable = "v3",
            h1 = 1,
            h2 = 2,
            magnetogram_mode = {"single_cube": "top"},
        )


def test_config_rejects_paired_cubes_magnetogram_mode():
    with pytest.raises(ValueError, match = "only supports the 'single_cube' key"):
        config_module.get_config(
            source_type = "paired_cubes",
            v1_path = "/tmp/dataset/cube_v1.fits",
            v2_path = "/tmp/dataset/cube_v2.fits",
            delta_z_km = 100.0,
            p_dx_Mm = 0.5,
            dt = 1.0,
            magnetogram_mode = {"paired_cubes": "dataset"},
        )


def test_config_accepts_directional_xcorr_geometry():
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/dataset/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/dataset/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["xcorr_geometry"] = "east"
    runtime_config = td.prepare_runtime_config(config)
    outfile_path = Path(runtime_config["data"]["outfile"])
    phase_path = Path(runtime_config["data"]["phase_outfile"])

    assert runtime_config["time_distance"]["xcorr_geometry"] == "east"
    assert outfile_path.parts[-4:-1] == ("xcorr", "east", "v1")
    assert phase_path.parts[-4:-1] == ("phase", "east", "v1")
    assert "_east_xc.fits" in outfile_path.name
    assert "_east_phase_diff.fits" in phase_path.name
    assert "filter_1" in outfile_path.parts
    assert Path(runtime_config["data"]["filter_parameters_file"]).exists()


def test_config_rejects_invalid_xcorr_geometry():
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/dataset/cube_v1.fits",
        v2_path = "/tmp/dataset/cube_v2.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["xcorr_geometry"] = "diagonal"

    with pytest.raises(ValueError, match = "xcorr_geometry"):
        td.prepare_runtime_config(config)


def test_directional_xcorr_geometry_masks_follow_quadrant_rules():
    yy_shift = np.array([-1, -1, 0, 1, 1, 1, 0, -1], dtype = np.int64)
    xx_shift = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype = np.int64)

    expected = {
        "east": {(0, 1), (1, 1), (-1, 1)},
        "west": {(0, -1), (1, -1), (-1, -1)},
        "north": {(1, 0), (1, 1), (1, -1)},
        "south": {(-1, 0), (-1, 1), (-1, -1)},
    }

    for geometry, expected_offsets in expected.items():
        selected_yy, selected_xx = td.select_xcorr_offsets_for_geometry(
            yy_shift,
            xx_shift,
            geometry,
        )
        selected_offsets = set(zip(selected_yy.tolist(), selected_xx.tolist()))
        assert selected_offsets == expected_offsets


def _legacy_xcorrj_reference(v1, v2, *, width, dx_pixels, dx_Mm, dt, maxdist_Mm, xcorr_geometry = "annulus"):
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
            yy_shift, xx_shift = td.select_xcorr_offsets_for_geometry(
                yy - center,
                xx - center,
                xcorr_geometry,
            )
            annulus_offsets.append((yy_shift, xx_shift))

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

    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["width"] = 0
    config["time_distance"]["maxdist_Mm"] = 2.0
    config["time_distance"]["nworkers"] = 1
    config["time_distance"]["xcorrj_engine"] = "chunked"
    config["time_distance"]["xcorrj_parallel"] = False
    config["time_distance"]["xcorrj_chunk_centers"] = 7

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


def test_xcorrj_legacy_engine_matches_legacy_reference_small_cube():
    rng = np.random.default_rng(22)
    v1 = rng.standard_normal((24, 20, 20))
    v2 = rng.standard_normal((24, 20, 20))

    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["width"] = 0
    config["time_distance"]["maxdist_Mm"] = 2.0
    config["time_distance"]["nworkers"] = 1
    config["time_distance"]["xcorrj_engine"] = "legacy"

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


@pytest.mark.parametrize("xcorr_geometry", ["east", "west", "north", "south"])
def test_xcorrj_directional_geometry_matches_reference_small_cube(xcorr_geometry):
    rng = np.random.default_rng(220 + len(xcorr_geometry))
    v1 = rng.standard_normal((20, 20, 20))
    v2 = rng.standard_normal((20, 20, 20))

    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["width"] = 0
    config["time_distance"]["maxdist_Mm"] = 2.0
    config["time_distance"]["nworkers"] = 1
    config["time_distance"]["xcorrj_engine"] = "chunked"
    config["time_distance"]["xcorrj_parallel"] = False
    config["time_distance"]["xcorrj_chunk_centers"] = 7
    config["time_distance"]["xcorr_geometry"] = xcorr_geometry

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
        xcorr_geometry = xcorr_geometry,
    )

    for result_array, reference_array in zip(result, reference):
        np.testing.assert_allclose(
            result_array,
            reference_array,
            rtol = 1.0e-12,
            atol = 1.0e-12,
            equal_nan = True)

    assert pipeline.xcorrj_diagnostics["xcorr_geometry"] == xcorr_geometry


def test_xcorrj_chunked_parallel_matches_chunked_serial():
    rng = np.random.default_rng(23)
    v1 = rng.standard_normal((24, 22, 22))
    v2 = rng.standard_normal((24, 22, 22))

    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["width"] = 0
    config["time_distance"]["maxdist_Mm"] = 2.0
    config["time_distance"]["xcorrj_engine"] = "chunked"
    config["time_distance"]["xcorrj_chunk_centers"] = 5

    serial_config = copy.deepcopy(config)
    serial_config["time_distance"]["nworkers"] = 1
    serial_config["time_distance"]["xcorrj_parallel"] = False
    parallel_config = copy.deepcopy(config)
    parallel_config["time_distance"]["nworkers"] = 2
    parallel_config["time_distance"]["xcorrj_parallel"] = True

    serial_pipeline = td.TimeDistance(td.prepare_runtime_config(serial_config))
    parallel_pipeline = td.TimeDistance(td.prepare_runtime_config(parallel_config))
    serial_result = serial_pipeline.xcorrj(v1, v2)
    parallel_result = parallel_pipeline.xcorrj(v1, v2)

    for serial_array, parallel_array in zip(serial_result, parallel_result):
        np.testing.assert_allclose(parallel_array, serial_array, rtol = 1.0e-12, atol = 1.0e-12)

    assert parallel_pipeline.xcorrj_diagnostics["engine"] == "chunked"
    assert parallel_pipeline.xcorrj_diagnostics["effective_workers"] == 2
    assert parallel_pipeline.xcorrj_diagnostics["num_tasks"] > parallel_pipeline.xcorrj_diagnostics["num_radii"]


@pytest.mark.parametrize(
    ("nt", "width"),
    [
        (23, 0),
        (24, 1),
    ],
)
def test_xcorrj_chunked_handles_odd_even_width_and_clipped_maxdist(nt, width):
    rng = np.random.default_rng(24 + nt + width)
    v1 = rng.standard_normal((nt, 18, 18))
    v2 = rng.standard_normal((nt, 18, 18))

    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = "/tmp/06May2019.ibis.to.hmi.vel.fe5434.fits",
        v2_path = "/tmp/06May2019.ibis.to.hmi.vel.fe7090.fits",
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )
    config["time_distance"]["width"] = width
    config["time_distance"]["maxdist_Mm"] = 100.0
    config["time_distance"]["nworkers"] = 1
    config["time_distance"]["xcorrj_engine"] = "chunked"
    config["time_distance"]["xcorrj_parallel"] = False
    config["time_distance"]["xcorrj_chunk_centers"] = 4

    pipeline = td.TimeDistance(td.prepare_runtime_config(config))
    result = pipeline.xcorrj(v1, v2)
    reference = _legacy_xcorrj_reference(
        v1,
        v2,
        width = width,
        dx_pixels = 1.0,
        dx_Mm = 0.5,
        dt = 1.0,
        maxdist_Mm = 100.0,
    )

    for result_array, reference_array in zip(result, reference):
        np.testing.assert_allclose(
            result_array,
            reference_array,
            rtol = 1.0e-12,
            atol = 1.0e-12,
            equal_nan = True)


def test_xcorrj_runtime_controls_do_not_change_output_names(tmp_path):
    base_config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "06May2019.ibis.to.hmi.vel.fe5434.fits"),
        v2_path = str(tmp_path / "06May2019.ibis.to.hmi.vel.fe7090.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
        data_output_dir = str(tmp_path / "data"),
        figure_dir = str(tmp_path / "figures"),
    )
    controlled_config = copy.deepcopy(base_config)
    controlled_config["time_distance"].update({
        "nworkers": 2,
        "xcorrj_engine": "chunked",
        "xcorrj_parallel": True,
        "xcorrj_chunk_centers": 3,
        "xcorrj_chunk_memory_mb": 16.0,
    })

    base_runtime = td.prepare_runtime_config(base_config)
    controlled_runtime = td.prepare_runtime_config(controlled_config)

    for key in ["outfile", "phase_outfile", "komega_outfile", "coherence_outfile"]:
        assert Path(controlled_runtime["data"][key]).name == Path(base_runtime["data"][key]).name
        assert "_annulus" not in Path(base_runtime["data"][key]).name
        assert "annulus" in Path(base_runtime["data"][key]).parts


def test_directional_xcorr_geometry_changes_output_names(tmp_path):
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "06May2019.ibis.to.hmi.vel.fe5434.fits"),
        v2_path = str(tmp_path / "06May2019.ibis.to.hmi.vel.fe7090.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
        data_output_dir = str(tmp_path / "data"),
        figure_dir = str(tmp_path / "figures"),
    )
    config["time_distance"]["xcorr_geometry"] = "north"
    runtime_config = td.prepare_runtime_config(config)

    for key in ["outfile", "phase_outfile", "komega_outfile", "coherence_outfile"]:
        path = Path(runtime_config["data"][key])
        assert "north" in path.parts
        assert "_north_" in path.name


def test_prepare_runtime_config_strips_filter_and_magnetogram_metadata_from_filenames(tmp_path):
    filtering = copy.deepcopy(config_module.default_filtering)
    filtering["magnetogram"]["enabled"] = True
    filtering["magnetogram"]["selection"] = "magnetic"
    filtering["magnetogram"]["threshold_G"] = 10.0
    filtering["gaussian"]["central_k"] = 2.0
    filtering["gaussian"]["width_k"] = 2.0
    filtering["gaussian"]["central_f"] = 1.5
    filtering["gaussian"]["width_f"] = 1.5
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "06May2019.ibis.to.hmi.vel.fe5434.fits"),
        v2_path = str(tmp_path / "06May2019.ibis.to.hmi.vel.fe7090.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
        data_output_dir = str(tmp_path / "data"),
        figure_dir = str(tmp_path / "figures"),
        filtering = filtering,
    )
    runtime_config = td.prepare_runtime_config(config)
    outfile_path = Path(runtime_config["data"]["outfile"])
    parameter_text = Path(runtime_config["data"]["filter_parameters_file"]).read_text(encoding = "utf-8")

    assert outfile_path.parts[-7:-4] == ("observations", "magneto", "06may2019")
    assert outfile_path.parts[-4:-1] == ("xcorr", "annulus", "v1")
    assert "gaussian" not in outfile_path.name
    assert "gauss_ck" not in outfile_path.name
    assert "magnetogram" not in outfile_path.name
    assert "b_gt_10g" not in outfile_path.name
    assert "filtering.gaussian.central_k: 2.0" in parameter_text
    assert "filtering.magnetogram.threshold_G: 10.0" in parameter_text


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


def test_load_magnetograms_discovers_dataset_hmimag_cube(tmp_path):
    magnetogram_path = tmp_path / "06May2019.HMImag.ibis.aligned.fits"
    magnetogram_path.touch()

    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "cube_v1.fits"),
        v2_path = str(tmp_path / "cube_v2.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )

    runtime_config = td.prepare_runtime_config(config)
    agw_filter = agw_filter_module.AGWFilter(runtime_config)
    load_calls = []

    def _fake_load_cube(file_path):
        load_calls.append(str(Path(file_path).resolve()))
        return np.ones((2, 2, 2), dtype = np.float64)

    agw_filter.load_cube = _fake_load_cube
    magnetogram = agw_filter.load_magnetograms()

    assert load_calls == [str(magnetogram_path.resolve())]
    assert runtime_config["data"]["resolved_magnetogram_file"] == str(magnetogram_path.resolve())
    np.testing.assert_allclose(magnetogram, np.ones((2, 2, 2), dtype = np.float64)/10.0, rtol = 0.0, atol = 0.0)


def test_load_magnetograms_raises_when_dataset_hmimag_missing(tmp_path):
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "cube_v1.fits"),
        v2_path = str(tmp_path / "cube_v2.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )

    runtime_config = td.prepare_runtime_config(config)
    agw_filter = agw_filter_module.AGWFilter(runtime_config)

    with pytest.raises(FileNotFoundError, match = r"Expected pattern: \*HMImag\*\.fits"):
        agw_filter.load_magnetograms()


def test_load_magnetograms_raises_when_dataset_hmimag_ambiguous(tmp_path):
    (tmp_path / "a.HMImag.fits").touch()
    (tmp_path / "b.HMImag.fits").touch()
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "cube_v1.fits"),
        v2_path = str(tmp_path / "cube_v2.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )

    runtime_config = td.prepare_runtime_config(config)
    agw_filter = agw_filter_module.AGWFilter(runtime_config)

    with pytest.raises(ValueError, match = "Ambiguous paired_cubes magnetogram candidates"):
        agw_filter.load_magnetograms()


def test_paired_cubes_mask_loader_rejects_multiple_magnetograms():
    runtime_config = {
        "data": {
            "source_type": "paired_cubes",
            "v1": "/tmp/dataset/cube_v1.fits",
            "v2": "/tmp/dataset/cube_v2.fits",
            "data_dir": "/tmp/dataset",
        },
        "time_distance": {},
        "filtering": {
            "magnetogram": {
                "selection": "magnetic",
                "threshold_G": 0.5,
                "fill_value": 0.0,
            },
        },
    }
    agw_filter = agw_filter_module.AGWFilter(runtime_config)
    agw_filter.load_magnetograms = lambda: (
        np.zeros((2, 2, 2), dtype = np.float64),
        np.ones((2, 2, 2), dtype = np.float64),
    )

    with pytest.raises(ValueError, match = "paired_cubes magnetogram filtering requires exactly one"):
        agw_filter.load_magnetogram_filter_masks()


def test_gaussian_filter_cache_reuses_existing_filter(tmp_path: Path, monkeypatch):
    calls = {"create_filter": 0}

    def fake_create_filter(array, frequency_array, kx_array, ky_array, central_f, width_f, central_k, width_k):
        calls["create_filter"] += 1
        return np.full(array.shape, 0.125, dtype = np.float64)

    monkeypatch.setattr(agw_filter_module.spectral_analysis, "create_filter", fake_create_filter)
    runtime_config = {
        "paths": {"project_dir": str(tmp_path)},
        "data": {},
        "time_distance": {"dt": 1.0, "p_dx_Mm": 0.5},
        "filtering": {
            "gaussian": {
                "central_f": 1.5,
                "width_f": 1.5,
                "central_k": 2.0,
                "width_k": 2.0,
            },
        },
    }
    cube = np.ones((5, 4, 6), dtype = np.float64)

    first_filter = agw_filter_module.AGWFilter(copy.deepcopy(runtime_config)).build_gaussian_filter(cube)
    second_filter = agw_filter_module.AGWFilter(copy.deepcopy(runtime_config)).build_gaussian_filter(cube)

    assert calls["create_filter"] == 1
    np.testing.assert_array_equal(first_filter, second_filter)
    cache_files = sorted((tmp_path / "Data" / "Filters").glob("gaussian_filter_*.npy"))
    assert len(cache_files) == 1
    assert "gauss_ck_2_wk_2_cf_1_5_wf_1_5" in cache_files[0].name
    assert "shape_6x4x5" in cache_files[0].name


def test_gaussian_filter_cache_uses_shape_specific_keys(tmp_path: Path, monkeypatch):
    calls = {"create_filter": 0}

    def fake_create_filter(array, frequency_array, kx_array, ky_array, central_f, width_f, central_k, width_k):
        calls["create_filter"] += 1
        return np.full(array.shape, calls["create_filter"], dtype = np.float64)

    monkeypatch.setattr(agw_filter_module.spectral_analysis, "create_filter", fake_create_filter)
    runtime_config = {
        "paths": {"project_dir": str(tmp_path)},
        "data": {},
        "time_distance": {"dt": 1.0, "p_dx_Mm": 0.5},
        "filtering": {
            "gaussian": {
                "central_f": 1.5,
                "width_f": 1.5,
                "central_k": 2.0,
                "width_k": 2.0,
            },
        },
    }

    agw_filter_module.AGWFilter(copy.deepcopy(runtime_config)).build_gaussian_filter(np.ones((5, 4, 6), dtype = np.float64))
    agw_filter_module.AGWFilter(copy.deepcopy(runtime_config)).build_gaussian_filter(np.ones((5, 4, 7), dtype = np.float64))

    assert calls["create_filter"] == 2
    assert len(sorted((tmp_path / "Data" / "Filters").glob("gaussian_filter_*.npy"))) == 2


def test_magnetogram_filter_cache_reuses_existing_masks(tmp_path: Path, monkeypatch):
    calls = {"compute_masks": 0}
    original_compute_masks = agw_filter_module.AGWFilter.compute_magnetogram_filter_masks
    bottom_magnetogram = np.array(
        [
            [[0.0, 1.0], [2.0, 3.0]],
            [[-1.0, -2.0], [0.25, 0.75]],
        ],
        dtype = np.float64,
    )

    def fake_bottom_magnetogram(self, file_path):
        return bottom_magnetogram

    def counting_compute_masks(self, abs_magnetogram_for_v1, abs_magnetogram_for_v2, selection, threshold_G):
        calls["compute_masks"] += 1
        return original_compute_masks(self, abs_magnetogram_for_v1, abs_magnetogram_for_v2, selection, threshold_G)

    monkeypatch.setattr(agw_filter_module.AGWFilter, "load_netcdf_bottom_layer_magnetogram", fake_bottom_magnetogram)
    monkeypatch.setattr(agw_filter_module.AGWFilter, "compute_magnetogram_filter_masks", counting_compute_masks)
    runtime_config = {
        "paths": {"project_dir": str(tmp_path)},
        "data": {
            "source_type": "single_cube",
            "file": "/tmp/simulation.nc",
            "h1": 1,
            "h2": 2,
        },
        "time_distance": {},
        "magnetogram_mode": {"single_cube": "bottom"},
        "filtering": {
            "magnetogram": {
                "selection": "nonmagnetic",
                "threshold_G": 0.75,
                "fill_value": 0.0,
            },
        },
    }

    first_masks = agw_filter_module.AGWFilter(copy.deepcopy(runtime_config)).load_magnetogram_filter_masks()
    second_masks = agw_filter_module.AGWFilter(copy.deepcopy(runtime_config)).load_magnetogram_filter_masks()

    assert calls["compute_masks"] == 1
    np.testing.assert_array_equal(first_masks[0], second_masks[0])
    np.testing.assert_array_equal(first_masks[1], second_masks[1])
    cache_files = sorted((tmp_path / "Data" / "Filters").glob("magnetogram_filter_*.npz"))
    assert len(cache_files) == 1
    assert "b_le_0_75g" in cache_files[0].name


def test_single_cube_bottom_magnetogram_mode_uses_one_shared_map(tmp_path: Path):
    runtime_config = {
        "paths": {"project_dir": str(tmp_path)},
        "data": {
            "source_type": "single_cube",
            "file": "/tmp/simulation.nc",
            "h1": 1,
            "h2": 2,
        },
        "time_distance": {},
        "magnetogram_mode": {"single_cube": "bottom"},
        "filtering": {
            "magnetogram": {
                "selection": "magnetic",
                "threshold_G": 0.5,
                "fill_value": 0.0,
            },
        },
    }
    agw_filter = agw_filter_module.AGWFilter(runtime_config)
    bottom_magnetogram = np.ones((2, 2, 2), dtype = np.float64)
    agw_filter.load_netcdf_bottom_layer_magnetogram = lambda file_path: bottom_magnetogram

    loaded = agw_filter.load_magnetograms()
    removed_mask_v1, removed_mask_v2, metadata = agw_filter.load_magnetogram_filter_masks()

    assert loaded is bottom_magnetogram
    assert metadata["magnetogram_kind"] == "single"
    assert metadata["magnetogram_mode"] == "bottom"
    np.testing.assert_array_equal(removed_mask_v1, np.zeros((2, 2, 2), dtype = bool))
    np.testing.assert_array_equal(removed_mask_v2, np.zeros((2, 2, 2), dtype = bool))


def test_single_cube_per_height_pair_magnetogram_mode_uses_two_maps(tmp_path: Path):
    runtime_config = {
        "paths": {"project_dir": str(tmp_path)},
        "data": {
            "source_type": "single_cube",
            "file": "/tmp/simulation.nc",
            "h1": 1,
            "h2": 2,
        },
        "time_distance": {},
        "magnetogram_mode": {"single_cube": "per_height_pair"},
        "filtering": {
            "magnetogram": {
                "selection": "magnetic",
                "threshold_G": 0.5,
                "fill_value": 0.0,
            },
        },
    }
    agw_filter = agw_filter_module.AGWFilter(runtime_config)
    h1_magnetogram = np.zeros((2, 2, 2), dtype = np.float64)
    h2_magnetogram = np.ones((2, 2, 2), dtype = np.float64)
    agw_filter.load_netcdf_height_pair_magnetograms = lambda file_path: (h1_magnetogram, h2_magnetogram)

    loaded = agw_filter.load_magnetograms()
    removed_mask_v1, removed_mask_v2, metadata = agw_filter.load_magnetogram_filter_masks()

    assert loaded[0] is h1_magnetogram
    assert loaded[1] is h2_magnetogram
    assert metadata["magnetogram_kind"] == "pair"
    assert metadata["magnetogram_mode"] == "per_height_pair"
    np.testing.assert_array_equal(removed_mask_v1, np.ones((2, 2, 2), dtype = bool))
    np.testing.assert_array_equal(removed_mask_v2, np.zeros((2, 2, 2), dtype = bool))


def test_zero_field_single_cube_uses_synthetic_zero_magnetogram(tmp_path: Path, monkeypatch):
    cube_file = tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc"
    fake_dataset = _FakeNetCDFDataset(cube_file)
    monkeypatch.setattr(agw_filter_module, "nc", SimpleNamespace(Dataset = lambda _path: fake_dataset))
    runtime_config = {
        "paths": {"project_dir": str(tmp_path)},
        "data": {
            "source_type": "single_cube",
            "file": str(cube_file),
            "observable": "v3",
            "h1": 0,
            "h2": 1,
        },
        "time_distance": {},
        "magnetogram_mode": {"single_cube": "bottom"},
        "filtering": {
            "magnetogram": {
                "selection": "nonmagnetic",
                "threshold_G": 0.5,
                "fill_value": 0.0,
            },
        },
    }
    agw_filter = agw_filter_module.AGWFilter(runtime_config)

    magnetogram = agw_filter.load_magnetograms()
    removed_mask_v1, removed_mask_v2, metadata = agw_filter.load_magnetogram_filter_masks()

    np.testing.assert_array_equal(magnetogram, np.zeros((4, 3, 3), dtype = np.float64))
    assert agw_filter.data["magnetogram_cube_variable"] == "synthetic_zero_field"
    assert metadata["magnetogram_mode"] == "bottom"
    np.testing.assert_array_equal(removed_mask_v1, np.zeros((4, 3, 3), dtype = bool))
    np.testing.assert_array_equal(removed_mask_v2, np.zeros((4, 3, 3), dtype = bool))


def test_zero_field_single_cube_orientation_metadata_uses_synthetic_zero_components(tmp_path: Path, monkeypatch):
    cube_file = tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc"
    fake_dataset = _FakeNetCDFDataset(cube_file)
    monkeypatch.setattr(td, "nc", SimpleNamespace(Dataset = lambda _path: fake_dataset))
    monkeypatch.setattr(td, "AGWFilter", agw_filter_module.AGWFilter)
    runtime_config = {
        "data": {
            "source_type": "single_cube",
            "file": str(cube_file),
            "h1": 0,
            "h2": 1,
            "resolved_h1_km": 0.0,
            "resolved_h2_km": 300.0,
            "outfile": str(tmp_path / "xc.fits"),
            "phase_outfile": str(tmp_path / "phase.fits"),
            "komega_outfile": str(tmp_path / "komega.fits"),
            "coherence_outfile": str(tmp_path / "coherence.fits"),
            "orientation_validation_outfile": "",
            "single_cube_model_atmosphere": {
                "density_cgs": [1.0e-7, 4.0e-8],
                "sound_speed_cgs": [2.0e6, 1.8e6],
            },
        },
        "filtering": {},
        "time_distance": {},
        "magnetogram_mode": {"single_cube": "bottom"},
    }
    pipeline = td.TimeDistance(runtime_config)

    metadata = pipeline.compute_single_cube_magnetic_orientation_metadata()

    assert metadata["component_names"] == {
        "bx": "synthetic_zero_field_bx",
        "by": "synthetic_zero_field_by",
        "bz": "synthetic_zero_field_bz",
    }
    assert metadata["theta_valid_fraction"] == [0.0, 0.0]
    assert metadata["phi_valid_fraction"] == [0.0, 0.0]
    assert metadata["field_strength_G_between_heights"] == [0.0, 0.0]
    assert metadata["alfven_sound_ratio"]["mean_field_strength_G_between_heights"] == pytest.approx(0.0)
    assert metadata["alfven_sound_ratio"]["alfven_speed_cgs"] == pytest.approx(0.0)


def test_parse_spectral_identifier_supports_aia_bandpass_tokens():
    spectral_id = td.parse_spectral_identifier("06May2019.AIA1600.ibis.aligned.final.fits")

    assert spectral_id["element"] == "AIA"
    assert spectral_id["line"] == "1600"


def test_prepare_runtime_config_builds_slug_for_aia_bandpass_pairs(tmp_path):
    config = config_module.get_config(
        source_type = "paired_cubes",
        v1_path = str(tmp_path / "06May2019.AIA1600.ibis.aligned.final.fits"),
        v2_path = str(tmp_path / "06May2019.AIA1700.ibis.aligned.final.fits"),
        delta_z_km = 100.0,
        p_dx_Mm = 0.5,
        dt = 1.0,
    )

    runtime_config = td.prepare_runtime_config(config)
    outfile_name = Path(runtime_config["data"]["outfile"]).name

    assert "aia1600_aia1700" in outfile_name
