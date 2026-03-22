import importlib.util
from pathlib import Path
from types import SimpleNamespace

from astropy.io import fits
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_PATH = ROOT / "Code" / "Time-Distance" / "time_distance.py"
CONFIG_PATH = ROOT / "Code" / "Time-Distance" / "config.py"


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


td = _load_module("time_distance_under_test", TIME_DISTANCE_PATH)
config_module = _load_module("time_distance_config_under_test", CONFIG_PATH)


class _FakeNetCDFVariable:
    def __init__(self, values, *, units=""):
        self.values = np.asarray(values, dtype=np.float64)
        self.units = units

    def __getitem__(self, key):
        return self.values


class _FakeNetCDFDataset:
    def __init__(self, variables):
        self.variables = variables

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _write_synthetic_single_cube(file_path: Path, z_values_km=None):
    netcdf4 = pytest.importorskip("netCDF4")

    if z_values_km is None:
        z_values_km = np.array([0.0, 300.0], dtype=np.float64)
    else:
        z_values_km = np.asarray(z_values_km, dtype=np.float64)

    with netcdf4.Dataset(file_path, "w") as dataset:
        dataset.createDimension("t", 4)
        dataset.createDimension("xc3", z_values_km.size)
        dataset.createDimension("xc2", 3)
        dataset.createDimension("xc1", 3)

        time_coord = dataset.createVariable("t", "f8", ("t",))
        time_coord.units = "s"
        time_coord[:] = np.arange(4, dtype=np.float64) * 30.0

        x_coord = dataset.createVariable("xc1", "f8", ("xc1",))
        x_coord.units = "Mm"
        x_coord[:] = np.arange(3, dtype=np.float64) * 0.5

        y_coord = dataset.createVariable("xc2", "f8", ("xc2",))
        y_coord.units = "Mm"
        y_coord[:] = np.arange(3, dtype=np.float64) * 0.5

        z_coord = dataset.createVariable("xc3", "f8", ("xc3",))
        z_coord.units = "km"
        z_coord[:] = z_values_km

        cube_shape = (4, z_values_km.size, 3, 3)
        dataset.createVariable("v3", "f8", ("t", "xc3", "xc2", "xc1"))[:] = np.arange(
            np.prod(cube_shape), dtype=np.float64
        ).reshape(cube_shape)

        bx = np.zeros(cube_shape, dtype=np.float64)
        by = np.zeros(cube_shape, dtype=np.float64)
        bz = np.zeros(cube_shape, dtype=np.float64)

        bx[:, 0, :, :] = 1.0
        by[:, 0, :, :] = 1.0
        bz[:, 0, :, :] = np.sqrt(2.0)

        bx[:, 1, :, :] = -1.0
        by[:, 1, :, :] = 1.0
        bz[:, 1, :, :] = 0.0

        # One undefined vector per height should be ignored by the averages.
        bx[0, 0, 0, 0] = 0.0
        by[0, 0, 0, 0] = 0.0
        bz[0, 0, 0, 0] = 0.0
        bx[1, 1, 1, 1] = 0.0
        by[1, 1, 1, 1] = 0.0
        bz[1, 1, 1, 1] = 0.0

        dataset.createVariable("bb1", "f8", ("t", "xc3", "xc2", "xc1"))[:] = bx
        dataset.createVariable("bb2", "f8", ("t", "xc3", "xc2", "xc1"))[:] = by
        dataset.createVariable("bb3", "f8", ("t", "xc3", "xc2", "xc1"))[:] = bz


def _write_synthetic_model_atmosphere(file_path: Path):
    np.savetxt(
        file_path,
        np.array(
            [
                [0.0, 0.0, 0.0, 1.0e-7, 0.0, 2.0e6],
                [0.3, 0.0, 0.0, 4.0e-8, 0.0, 1.8e6],
            ],
            dtype=np.float64,
        ),
    )


def test_single_cube_physical_heights_are_relative_to_photosphere(tmp_path: Path, monkeypatch):
    cube_file = tmp_path / "synthetic_single_cube_offset_heights.nc"
    cube_file.touch()
    fake_dataset = _FakeNetCDFDataset(
        {
            "t": _FakeNetCDFVariable([0.0, 30.0, 60.0, 90.0], units="s"),
            "xc1": _FakeNetCDFVariable([0.0, 0.5, 1.0], units="Mm"),
            "xc2": _FakeNetCDFVariable([0.0, 0.5, 1.0], units="Mm"),
            "xc3": _FakeNetCDFVariable([150.0, 450.0], units="km"),
        }
    )
    monkeypatch.setattr(td, "nc", SimpleNamespace(Dataset=lambda path: fake_dataset))

    resolved_heights = td.infer_netcdf_height_pair_km(cube_file, 0, 1)
    assert resolved_heights["h1_km"] == pytest.approx(0.0)
    assert resolved_heights["h2_km"] == pytest.approx(300.0)

    config = config_module.get_config(
        source_type="single_cube",
        file_path=str(cube_file),
        observable="v3",
        h1=0,
        h2=1,
        data_output_dir=str(tmp_path / "data"),
        figure_dir=str(tmp_path / "figures"),
        animation_dir=str(tmp_path / "animations"),
    )

    _, runtime_config, pipeline = td.build_pipeline(config_file=CONFIG_PATH, config_override=config)

    assert runtime_config["data"]["resolved_h1_km"] == pytest.approx(0.0)
    assert runtime_config["data"]["resolved_h2_km"] == pytest.approx(300.0)
    assert runtime_config["data"]["resolved_delta_z_km"] == pytest.approx(300.0)
    assert Path(pipeline.komega_outfile).name.startswith("synthetic_single_cube_offset_heights_v3_0km_300km_")


def test_single_cube_model_atmosphere_is_interpolated_per_layer(tmp_path: Path, monkeypatch):
    cube_file = tmp_path / "synthetic_single_cube_with_atmosphere.nc"
    cube_file.touch()
    fake_dataset = _FakeNetCDFDataset(
        {
            "t": _FakeNetCDFVariable([0.0, 30.0, 60.0, 90.0], units="s"),
            "xc1": _FakeNetCDFVariable([0.0, 0.5, 1.0], units="Mm"),
            "xc2": _FakeNetCDFVariable([0.0, 0.5, 1.0], units="Mm"),
            "xc3": _FakeNetCDFVariable([150.0, 250.0, 450.0], units="km"),
        }
    )
    monkeypatch.setattr(td, "nc", SimpleNamespace(Dataset=lambda path: fake_dataset))

    model_file = tmp_path / "model_atmosphere.dat"
    np.savetxt(
        model_file,
        np.array(
            [
                [0.0, 0.0, 0.0, 10.0, 0.0, 2.0e6],
                [0.1, 0.0, 0.0, 8.0, 0.0, 2.2e6],
                [0.2, 0.0, 0.0, 6.0, 0.0, 2.4e6],
                [0.3, 0.0, 0.0, 4.0, 0.0, 2.6e6],
            ],
            dtype=np.float64,
        ),
    )

    config = config_module.get_config(
        source_type="single_cube",
        file_path=str(cube_file),
        observable="v3",
        h1=0,
        h2=2,
        model_atmosphere_path=str(model_file),
        data_output_dir=str(tmp_path / "data"),
        figure_dir=str(tmp_path / "figures"),
        animation_dir=str(tmp_path / "animations"),
    )

    _, runtime_config, pipeline = td.build_pipeline(config_file=CONFIG_PATH, config_override=config)
    layer_model = runtime_config["data"]["single_cube_model_atmosphere"]

    assert layer_model["model_atmosphere_file"] == str(model_file.resolve())
    np.testing.assert_allclose(layer_model["height_km"], np.array([0.0, 100.0, 300.0]), atol=1.0e-12)
    np.testing.assert_allclose(layer_model["height_Mm"], np.array([0.0, 0.1, 0.3]), atol=1.0e-12)
    np.testing.assert_allclose(layer_model["density_cgs"], np.array([10.0, 8.0, 4.0]), atol=1.0e-12)
    np.testing.assert_allclose(layer_model["sound_speed_cgs"], np.array([2.0e6, 2.2e6, 2.6e6]), atol=1.0e-12)
    np.testing.assert_allclose(layer_model["sound_speed_km_s"], np.array([20.0, 22.0, 26.0]), atol=1.0e-12)
    assert pipeline.single_cube_model_atmosphere == layer_model


def test_single_cube_magnetic_orientation_metadata_includes_alfven_ratio(tmp_path: Path):
    pytest.importorskip("netCDF4")

    cube_file = tmp_path / "synthetic_single_cube_ratio.nc"
    model_file = tmp_path / "synthetic_model_atmosphere.dat"
    _write_synthetic_single_cube(cube_file)
    _write_synthetic_model_atmosphere(model_file)

    config = config_module.get_config(
        source_type="single_cube",
        file_path=str(cube_file),
        observable="v3",
        h1=0,
        h2=1,
        model_atmosphere_path=str(model_file),
        data_output_dir=str(tmp_path / "data"),
        figure_dir=str(tmp_path / "figures"),
        animation_dir=str(tmp_path / "animations"),
    )

    _, runtime_config, pipeline = td.build_pipeline(config_file=CONFIG_PATH, config_override=config)
    pipeline.orientation_validation_outfile = None
    metadata = pipeline.compute_single_cube_magnetic_orientation_metadata()
    alfven = metadata["alfven_sound_ratio"]

    expected_mean_field_h1 = 35.0 * 2.0 / 36.0
    expected_mean_field_h2 = 35.0 * np.sqrt(2.0) / 36.0
    expected_mean_field_between = np.mean([expected_mean_field_h1, expected_mean_field_h2])
    expected_density = np.mean([1.0e-7, 4.0e-8])
    expected_sound_speed_cgs = np.mean([2.0e6, 1.8e6])
    expected_alfven_speed_cgs = td.compute_alfven_speed_cgs(expected_mean_field_between, expected_density)

    np.testing.assert_allclose(
        metadata["field_strength_G_between_heights"],
        np.array([expected_mean_field_h1, expected_mean_field_h2]),
        atol=1.0e-12,
    )
    assert alfven["mean_field_strength_G_between_heights"] == pytest.approx(expected_mean_field_between)
    assert alfven["mean_density_cgs_between_heights"] == pytest.approx(expected_density)
    assert alfven["mean_sound_speed_cgs_between_heights"] == pytest.approx(expected_sound_speed_cgs)
    assert alfven["alfven_speed_cgs"] == pytest.approx(expected_alfven_speed_cgs)
    assert alfven["alfven_to_sound_speed_ratio"] == pytest.approx(expected_alfven_speed_cgs / expected_sound_speed_cgs)
    assert runtime_config["data"]["single_cube_model_atmosphere"]["density_cgs"] == pytest.approx([1.0e-7, 4.0e-8])


def test_compute_magnetic_orientation_angles_handles_zero_magnitude_and_quadrants():
    bx = np.array([1.0, 0.0, -1.0, 0.0, 0.0], dtype=np.float64)
    by = np.array([0.0, 1.0, 0.0, -1.0, 0.0], dtype=np.float64)
    bz = np.zeros_like(bx)

    orientation = td.compute_magnetic_orientation_angles(bx, by, bz, magnitude_epsilon=1.0e-12)

    np.testing.assert_allclose(orientation["theta_deg"][:4], np.array([90.0, 90.0, 90.0, 90.0]), atol=1.0e-12)
    np.testing.assert_allclose(orientation["phi_deg"][:4], np.array([0.0, 90.0, 180.0, -90.0]), atol=1.0e-12)
    assert np.isnan(orientation["theta_deg"][4])
    assert np.isnan(orientation["phi_deg"][4])


def test_circular_mean_degrees_handles_wraparound():
    mean_deg = td.circular_mean_degrees(np.array([179.0, -179.0], dtype=np.float64))

    assert np.isclose(abs(mean_deg), 180.0, atol=1.0e-12)


def test_single_cube_orientation_metadata_saved_to_komega_header(tmp_path: Path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("netCDF4")

    cube_file = tmp_path / "synthetic_single_cube.nc"
    model_file = tmp_path / "synthetic_model_atmosphere.dat"
    _write_synthetic_single_cube(cube_file)
    _write_synthetic_model_atmosphere(model_file)

    config = config_module.get_config(
        source_type="single_cube",
        file_path=str(cube_file),
        observable="v3",
        h1=0,
        h2=1,
        model_atmosphere_path=str(model_file),
        data_output_dir=str(tmp_path / "data"),
        figure_dir=str(tmp_path / "figures"),
        animation_dir=str(tmp_path / "animations"),
    )

    _, _, pipeline = td.build_pipeline(config_file=CONFIG_PATH, config_override=config)
    metadata = pipeline.compute_single_cube_magnetic_orientation_metadata()

    np.testing.assert_allclose(metadata["theta_means_deg"], np.array([45.0, 90.0]), atol=1.0e-10)
    np.testing.assert_allclose(metadata["phi_means_deg"], np.array([45.0, 135.0]), atol=1.0e-10)
    assert metadata["phi_mean_method"] == "circular"
    assert Path(metadata["validation_plot_file"]).exists()

    pipeline.save_time_distance(
        np.zeros((2, 2), dtype=np.float64),
        np.zeros((2, 2), dtype=np.float64),
        komega_spectrum=np.zeros((3, 4), dtype=np.float64),
        k_axis=np.array([0.0, 0.5, 1.0], dtype=np.float64),
        nu_axis=np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float64),
        komega_metadata={
            "phase_delay_seconds": 0.0,
            "phase_correction_applied": False,
            "magnetic_orientation": metadata,
        },
    )

    header = fits.getheader(pipeline.komega_outfile)
    assert header["THAVG1"] == pytest.approx(45.0)
    assert header["THAVG2"] == pytest.approx(90.0)
    assert header["PHAVG1"] == pytest.approx(45.0)
    assert header["PHAVG2"] == pytest.approx(135.0)
    assert bool(header["PHICIRC"]) is True
    assert header["CACSRAT"] == pytest.approx(
        metadata["alfven_sound_ratio"]["alfven_to_sound_speed_ratio"]
    )
