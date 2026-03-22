from pathlib import Path
from types import ModuleType

import nbformat
import pytest


ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_DIR = ROOT / "Code" / "Time-Distance"
CONFIG_PATH = TIME_DISTANCE_DIR / "config.py"
BATCH_NOTEBOOK_PATH = TIME_DISTANCE_DIR / "td_batch.ipynb"


def _load_td_batch_notebook_helpers(notebook_path: Path):
    notebook = nbformat.read(notebook_path, as_version = 4)
    module = ModuleType("td_batch_notebook_under_test")
    namespace = module.__dict__

    helper_cell = None
    for cell in notebook.cells:
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", "")
        if "def load_mode_base_config(" in source and "def execute_batch_runs(" in source:
            helper_cell = source
            break

    if helper_cell is None:
        raise RuntimeError(f"Could not find the helper-definition cell in {notebook_path}.")

    exec(compile(helper_cell, str(notebook_path), "exec"), namespace)

    return module


helpers = _load_td_batch_notebook_helpers(BATCH_NOTEBOOK_PATH)


def test_generate_unique_unordered_pairs_deduplicates_repeated_paths(tmp_path: Path):
    cube_a = tmp_path / "cube_a.fits"
    cube_b = tmp_path / "cube_b.fits"
    cube_c = tmp_path / "cube_c.fits"

    pairs = helpers.generate_unique_unordered_pairs([cube_a, cube_b, cube_a, cube_c])

    assert pairs == [
        (str(cube_a.resolve()), str(cube_b.resolve())),
        (str(cube_a.resolve()), str(cube_c.resolve())),
        (str(cube_b.resolve()), str(cube_c.resolve())),
    ]


def test_parse_single_cube_field_strength_case_extracts_geometry_and_strength(tmp_path: Path):
    cube_path = tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc"

    case = helpers.parse_single_cube_field_strength_case(cube_path)

    assert case["cube_path"] == str(cube_path.resolve())
    assert case["component"] == "hx"
    assert case["geometry"] == "horizontal"
    assert case["field_strength_G"] == pytest.approx(10.0)
    assert case["field_strength_token"] == "10g"
    assert case["field_strength_label"] == "10 G"


def test_organize_single_cube_field_strength_cases_groups_and_sorts(tmp_path: Path):
    cube_paths = [
        tmp_path / "co5bold" / "vx" / "50G" / "simulation_vx_50G.nc",
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
        tmp_path / "co5bold" / "hx" / "50G" / "simulation_hx_50G.nc",
    ]

    organized = helpers.organize_single_cube_field_strength_cases(cube_paths)

    assert [case["field_strength_label"] for case in organized["cases_by_geometry"]["horizontal"]] == [
        "10 G",
        "50 G",
    ]
    assert [case["field_strength_label"] for case in organized["cases_by_geometry"]["vertical"]] == [
        "10 G",
        "50 G",
    ]


def test_organize_single_cube_field_strength_cases_rejects_duplicate_case(tmp_path: Path):
    cube_paths = [
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G_a.nc",
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G_b.nc",
    ]

    with pytest.raises(ValueError, match = "Duplicate field-strength comparison case"):
        helpers.organize_single_cube_field_strength_cases(cube_paths)


def test_parse_single_cube_gaussian_filter_comparison_case_supports_zero_field(tmp_path: Path):
    cube_path = tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc"

    case = helpers.parse_single_cube_gaussian_filter_comparison_case(cube_path)

    assert case["cube_path"] == str(cube_path.resolve())
    assert case["component"] == "z0"
    assert case["field_strength_G"] == pytest.approx(0.0)
    assert case["case_key"] == "0g"
    assert case["comparison_label"] == "0G"


def test_organize_single_cube_gaussian_filter_comparison_cases_orders_required_cases(tmp_path: Path):
    cube_paths = [
        tmp_path / "co5bold" / "vx" / "50G" / "simulation_vx_50G.nc",
        tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc",
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "vx" / "100G" / "simulation_vx_100G.nc",
        tmp_path / "co5bold" / "hx" / "100G" / "simulation_hx_100G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
        tmp_path / "co5bold" / "hx" / "50G" / "simulation_hx_50G.nc",
    ]

    organized = helpers.organize_single_cube_gaussian_filter_comparison_cases(cube_paths)

    assert organized["ordered_labels"] == [
        "0G",
        "h10G",
        "h50G",
        "h100G",
        "v10G",
        "v50G",
        "v100G",
    ]


def test_generate_shared_single_cube_height_index_pairs_validates_shared_grid(tmp_path: Path):
    cube_1 = tmp_path / "cube_1.nc"
    cube_2 = tmp_path / "cube_2.nc"

    class _FakeTimeDistanceModule:
        @staticmethod
        def infer_netcdf_height_coordinates_km(file_path):
            file_path = str(Path(file_path).resolve())
            if file_path == str(cube_1.resolve()):
                return [0.0, 200.0, 500.0]
            if file_path == str(cube_2.resolve()):
                return [0.0, 200.0, 500.0]
            raise AssertionError(f"Unexpected file path: {file_path}")

    comparison = helpers.generate_shared_single_cube_height_index_pairs(
        _FakeTimeDistanceModule(),
        [cube_1, cube_2],
    )

    assert comparison["height_values_km"] == pytest.approx([0.0, 200.0, 500.0])
    assert comparison["height_pairs"] == [(0, 1), (0, 2), (1, 2)]


def test_generate_shared_single_cube_height_index_pairs_rejects_mismatched_grids(tmp_path: Path):
    cube_1 = tmp_path / "cube_1.nc"
    cube_2 = tmp_path / "cube_2.nc"

    class _FakeTimeDistanceModule:
        @staticmethod
        def infer_netcdf_height_coordinates_km(file_path):
            file_path = str(Path(file_path).resolve())
            if file_path == str(cube_1.resolve()):
                return [0.0, 200.0, 500.0]
            if file_path == str(cube_2.resolve()):
                return [0.0, 300.0, 500.0]
            raise AssertionError(f"Unexpected file path: {file_path}")

    with pytest.raises(ValueError, match = "must share the same height coordinate grid"):
        helpers.generate_shared_single_cube_height_index_pairs(
            _FakeTimeDistanceModule(),
            [cube_1, cube_2],
        )


def test_build_paired_cubes_batch_plan_returns_v_lists_and_configs(tmp_path: Path):
    config_file, td, base_config = helpers.load_mode_base_config(
        "paired_cubes",
        config_file = CONFIG_PATH,
    )
    cube_paths = [
        tmp_path / "cube_1.fits",
        tmp_path / "cube_2.fits",
        tmp_path / "cube_3.fits",
    ]

    plan = helpers.build_paired_cubes_batch_plan(
        base_config,
        td,
        cube_paths,
        delta_z_km = 250.0,
        p_dx_Mm = 0.5,
        dt = 12.0,
    )

    assert config_file == CONFIG_PATH.resolve()
    assert plan["v1_list"] == [
        str(cube_paths[0].resolve()),
        str(cube_paths[0].resolve()),
        str(cube_paths[1].resolve()),
    ]
    assert plan["v2_list"] == [
        str(cube_paths[1].resolve()),
        str(cube_paths[2].resolve()),
        str(cube_paths[2].resolve()),
    ]
    assert len(plan["run_configs"]) == 3

    first_config = plan["run_configs"][0]
    assert first_config["data"]["source_type"] == "paired_cubes"
    assert first_config["data"]["paired_cubes"]["v1"] == str(cube_paths[0].resolve())
    assert first_config["data"]["paired_cubes"]["v2"] == str(cube_paths[1].resolve())
    assert first_config["data"]["paired_cubes"]["delta_z_km"] == pytest.approx(250.0)
    assert first_config["data"]["paired_cubes"]["p_dx_Mm"] == pytest.approx(0.5)
    assert first_config["data"]["paired_cubes"]["dt"] == pytest.approx(12.0)


def test_build_single_cube_batch_plan_generates_per_cube_height_pairs(tmp_path: Path, monkeypatch):
    _, td, base_config = helpers.load_mode_base_config(
        "single_cube",
        config_file = CONFIG_PATH,
    )
    cube_1 = tmp_path / "cube_1.nc"
    cube_2 = tmp_path / "cube_2.nc"

    def _fake_heights(file_path):
        file_path = str(Path(file_path).resolve())
        if file_path == str(cube_1.resolve()):
            return [0.0, 200.0, 500.0]
        if file_path == str(cube_2.resolve()):
            return [0.0, 400.0]
        raise AssertionError(f"Unexpected file path: {file_path}")

    monkeypatch.setattr(td, "infer_netcdf_height_coordinates_km", _fake_heights)

    plan = helpers.build_single_cube_batch_plan(
        base_config,
        td,
        [cube_1, cube_2],
        observable = "v2",
        model_atmosphere_path = tmp_path / "model_atmosphere.dat",
    )

    assert plan["height_pairs_by_cube"][str(cube_1.resolve())] == [(0, 1), (0, 2), (1, 2)]
    assert plan["height_pairs_by_cube"][str(cube_2.resolve())] == [(0, 1)]
    assert len(plan["run_configs"]) == 4
    assert all(config["data"]["source_type"] == "single_cube" for config in plan["run_configs"])
    assert all(config["data"]["single_cube"]["observable"] == "v2" for config in plan["run_configs"])
    assert all(
        config["data"]["single_cube"]["model_atmosphere_path"] == str((tmp_path / "model_atmosphere.dat").resolve())
        for config in plan["run_configs"]
    )

    first_row = plan["height_pair_rows"][0]
    assert first_row["file"] == str(cube_1.resolve())
    assert first_row["h1_km"] == pytest.approx(0.0)
    assert first_row["h2_km"] == pytest.approx(200.0)


def test_build_single_cube_field_strength_comparison_plan_creates_one_request_per_height_pair(tmp_path: Path, monkeypatch):
    _, td, base_config = helpers.load_mode_base_config(
        "single_cube",
        config_file = CONFIG_PATH,
    )
    cube_paths = [
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
    ]

    def _fake_heights(_file_path):
        return [0.0, 200.0, 500.0]

    def _fake_prepare_runtime_config(runtime_config):
        prepared = {
            "data": {
                "single_cube": dict(runtime_config["data"]["single_cube"]),
                "outfile": "xc.fits",
                "phase_outfile": "phase.fits",
                "komega_outfile": "komega.fits",
            }
        }
        prepared["data"]["resolved_h1_km"] = float(_fake_heights(None)[prepared["data"]["single_cube"]["h1"]])
        prepared["data"]["resolved_h2_km"] = float(_fake_heights(None)[prepared["data"]["single_cube"]["h2"]])
        return prepared

    monkeypatch.setattr(td, "infer_netcdf_height_coordinates_km", _fake_heights)
    monkeypatch.setattr(td, "prepare_runtime_config", _fake_prepare_runtime_config)

    comparison_plan = helpers.build_single_cube_field_strength_comparison_plan(
        base_config,
        td,
        cube_paths,
        observable = "v3",
    )

    assert comparison_plan["height_pairs"] == [(0, 1), (0, 2), (1, 2)]
    assert len(comparison_plan["comparison_runs"]) == 3

    first_request = comparison_plan["comparison_runs"][0]["direct_plot_requests"][0]
    assert first_request["plot_type"] == "field_strength_comparison"
    assert first_request["cube_paths"] == [str(path.resolve()) for path in cube_paths]
    assert first_request["observable"] == "v3"
    assert first_request["h1"] == 0
    assert first_request["h2"] == 1


def test_build_single_cube_field_orientation_comparison_plan_switches_plot_type(tmp_path: Path, monkeypatch):
    _, td, base_config = helpers.load_mode_base_config(
        "single_cube",
        config_file = CONFIG_PATH,
    )
    cube_paths = [
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
    ]

    def _fake_heights(_file_path):
        return [0.0, 200.0, 500.0]

    def _fake_prepare_runtime_config(runtime_config):
        prepared = {
            "data": {
                "single_cube": dict(runtime_config["data"]["single_cube"]),
                "outfile": "xc.fits",
                "phase_outfile": "phase.fits",
                "komega_outfile": "komega.fits",
            }
        }
        prepared["data"]["resolved_h1_km"] = float(_fake_heights(None)[prepared["data"]["single_cube"]["h1"]])
        prepared["data"]["resolved_h2_km"] = float(_fake_heights(None)[prepared["data"]["single_cube"]["h2"]])
        return prepared

    monkeypatch.setattr(td, "infer_netcdf_height_coordinates_km", _fake_heights)
    monkeypatch.setattr(td, "prepare_runtime_config", _fake_prepare_runtime_config)

    comparison_plan = helpers.build_single_cube_field_orientation_comparison_plan(
        base_config,
        td,
        cube_paths,
        observable = "v3",
    )

    assert comparison_plan["height_pairs"] == [(0, 1), (0, 2), (1, 2)]
    assert len(comparison_plan["comparison_runs"]) == 3

    first_request = comparison_plan["comparison_runs"][0]["direct_plot_requests"][0]
    assert first_request["plot_type"] == "field_orientation_comparison"
    assert first_request["cube_paths"] == [str(path.resolve()) for path in cube_paths]
    assert first_request["observable"] == "v3"
    assert first_request["h1"] == 0
    assert first_request["h2"] == 1


def test_build_single_cube_gaussian_filter_comparison_plan_expands_filters_cases_and_heights(tmp_path: Path, monkeypatch):
    _, td, base_config = helpers.load_mode_base_config(
        "single_cube",
        config_file = CONFIG_PATH,
    )
    cube_paths = [
        tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc",
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "hx" / "50G" / "simulation_hx_50G.nc",
        tmp_path / "co5bold" / "hx" / "100G" / "simulation_hx_100G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
        tmp_path / "co5bold" / "vx" / "50G" / "simulation_vx_50G.nc",
        tmp_path / "co5bold" / "vx" / "100G" / "simulation_vx_100G.nc",
    ]
    filter_params_list = [
        {"central_k": 2.0, "width_k": 2.0, "central_f": 1.5, "width_f": 1.5},
        {"central_k": 3.0, "width_k": 1.0, "central_f": 2.0, "width_f": 1.0},
    ]

    def _fake_heights(_file_path):
        return [0.0, 200.0, 500.0]

    def _fake_prepare_runtime_config(runtime_config):
        prepared = {
            "data": {
                "single_cube": dict(runtime_config["data"]["single_cube"]),
                "outfile": "xc.fits",
                "phase_outfile": "phase.fits",
                "komega_outfile": "komega.fits",
            },
            "filtering": dict(runtime_config["filtering"]),
        }
        prepared["data"]["resolved_h1_km"] = float(_fake_heights(None)[prepared["data"]["single_cube"]["h1"]])
        prepared["data"]["resolved_h2_km"] = float(_fake_heights(None)[prepared["data"]["single_cube"]["h2"]])
        return prepared

    monkeypatch.setattr(td, "infer_netcdf_height_coordinates_km", _fake_heights)
    monkeypatch.setattr(td, "prepare_runtime_config", _fake_prepare_runtime_config)

    comparison_plan = helpers.build_single_cube_gaussian_filter_comparison_plan(
        base_config,
        td,
        cube_paths,
        filter_params_list,
        observable = "v3",
    )

    assert comparison_plan["height_pairs"] == [(0, 1), (0, 2), (1, 2)]
    assert comparison_plan["organized_cases"]["ordered_labels"] == [
        "0G",
        "h10G",
        "h50G",
        "h100G",
        "v10G",
        "v50G",
        "v100G",
    ]
    assert len(comparison_plan["filter_params_list"]) == 2
    assert len(comparison_plan["run_configs"]) == 42
    assert len(comparison_plan["comparison_runs"]) == 3

    first_request = comparison_plan["comparison_runs"][0]["direct_plot_requests"][0]
    assert first_request["plot_type"] == "gaussian_filter_comparison"
    assert first_request["cube_paths"] == [str(path.resolve()) for path in cube_paths]
    assert len(first_request["filter_params_list"]) == 2
    assert first_request["observable"] == "v3"
    assert first_request["h1"] == 0
    assert first_request["h2"] == 1


def test_build_td_analysis_input_cell_source_defines_comparison_execution_defaults():
    runtime_config = {
        "paths": {"data_output_dir": "/tmp"},
        "data": {
            "source_type": "single_cube",
            "single_cube": {
                "file": "/tmp/cube.nc",
                "observable": "v1",
                "h1": 0,
                "h2": 1,
            },
            "komega_outfile": "/tmp/example_komega.fits",
        },
        "time_distance": {"dt": 30.0, "p_dx_Mm": 0.024},
    }

    source = helpers.build_td_analysis_input_cell_source(
        runtime_config,
        use_config = False,
        direct_plot_requests = [{"plot_type": "field_strength_comparison"}],
    )

    assert "comparison_execution_mode = 'load'" in source
    assert "comparison_missing_data_behavior = 'error'" in source


def test_execute_batch_runs_skips_existing_outputs(tmp_path: Path):
    data_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_paths = {
        "outfile": data_dir / "test_xc.fits",
        "phase_outfile": data_dir / "test_phase.fits",
        "komega_outfile": data_dir / "test_komega.fits",
        "coherence_outfile": data_dir / "test_coherence.fits",
    }
    for path in output_paths.values():
        path.write_text("ready", encoding = "utf-8")

    class _FakeTimeDistanceModule:
        def __init__(self):
            self.run_calls = 0

        def prepare_runtime_config(self, run_config):
            return {
                "paths": {"data_output_dir": str(data_dir)},
                "data": {
                    "source_type": "paired_cubes",
                    "v1": "cube_1.fits",
                    "v2": "cube_2.fits",
                    **{key: str(value) for key, value in output_paths.items()},
                    "orientation_validation_outfile": "",
                },
            }

        def run_time_distance(self, config_file = None, config_override = None):
            self.run_calls += 1
            raise AssertionError("run_time_distance should not be called when outputs already exist")

    fake_td = _FakeTimeDistanceModule()
    run_records = helpers.execute_batch_runs(
        fake_td,
        CONFIG_PATH,
        run_configs = [{"name": "skip-me"}],
        skip_existing = True,
        continue_on_error = False,
        verbose = False,
    )

    assert len(run_records) == 1
    assert run_records[0]["status"] == "skipped_existing"
    assert fake_td.run_calls == 0


def test_execute_td_analysis_for_batch_skips_when_notebook_dependencies_are_missing(monkeypatch):
    run_records = [
        {
            "label": "pair-a",
            "source_type": "paired_cubes",
            "runtime_config": {"data": {"outfile": "a.fits"}},
            "status": "completed",
        },
        {
            "label": "pair-b",
            "source_type": "paired_cubes",
            "runtime_config": {"data": {"outfile": "b.fits"}},
            "status": "skipped_existing",
        },
    ]

    def _missing_dependencies():
        raise ModuleNotFoundError(
            "Executing td_analysis.ipynb requires the 'nbformat' and 'nbclient' packages."
        )

    monkeypatch.setattr(helpers, "import_td_analysis_notebook_dependencies", _missing_dependencies)

    analysis_records = helpers.execute_td_analysis_for_batch(run_records, verbose = False)

    assert [record["status"] for record in analysis_records] == [
        "skipped_missing_dependency",
        "skipped_missing_dependency",
    ]
    assert all("nbformat" in record["error"] for record in analysis_records)


def test_summarize_batch_records_counts_skipped_missing_dependency():
    summary = helpers.summarize_batch_records(
        [{"status": "completed"}],
        [{"status": "skipped_missing_dependency"}],
    )

    assert summary["runs"]["completed"] == 1
    assert summary["analysis"]["skipped_missing_dependency"] == 1
