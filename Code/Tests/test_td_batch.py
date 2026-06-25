from pathlib import Path
from types import ModuleType
import importlib.util
import sys

import nbformat
import numpy as np
import pytest
from astropy.io import fits


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "Code" / "Tests"
TIME_DISTANCE_DIR = ROOT / "Code" / "Time-Distance"
CONFIG_PATH = TIME_DISTANCE_DIR / "config.py"
BATCH_NOTEBOOK_PATH = TIME_DISTANCE_DIR / "batch.ipynb"
PLOTS_NOTEBOOK_PATH = TIME_DISTANCE_DIR / "plots.ipynb"
PERFORMANCE_AUDIT_PATH = TESTS_DIR / "performance_audit.py"


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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
        if "def write_default_comparison_viewers(" in source:
            helper_cell = source

    if helper_cell is None:
        raise RuntimeError(f"Could not find the helper-definition cell in {notebook_path}.")

    exec(compile(helper_cell, str(notebook_path), "exec"), namespace)

    return module


def _load_td_analysis_notebook_helpers(notebook_path: Path):
    notebook = nbformat.read(notebook_path, as_version = 4)
    module = ModuleType("td_analysis_notebook_under_test")
    namespace = module.__dict__

    helper_cell = None
    comparison_helper_cell = None
    for cell in notebook.cells:
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", "")
        if "def parse_spectral_identifier(" in source and "def prepare_runtime_config(" in source:
            helper_cell = source
        if (
            "def parse_single_cube_field_strength_case(" in source
            and "def build_field_strength_comparison_column_cases(" in source
        ):
            comparison_helper_cell = source

    if helper_cell is None:
        raise RuntimeError(f"Could not find the helper-definition cell in {notebook_path}.")
    if comparison_helper_cell is None:
        raise RuntimeError(f"Could not find the comparison helper-definition cell in {notebook_path}.")

    exec(compile(helper_cell, str(notebook_path), "exec"), namespace)
    exec(compile(comparison_helper_cell, str(notebook_path), "exec"), namespace)

    return module


def _load_performance_audit_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("performance_audit_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_comparison_view_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("comparison_view_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_config_module(module_path: Path = CONFIG_PATH):
    spec = importlib.util.spec_from_file_location("config_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = _load_td_batch_notebook_helpers(BATCH_NOTEBOOK_PATH)
analysis_helpers = _load_td_analysis_notebook_helpers(PLOTS_NOTEBOOK_PATH)
performance_audit = _load_performance_audit_module(PERFORMANCE_AUDIT_PATH)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents = True, exist_ok = True)
    path.touch()
    return path


def _write_tiny_png(path: Path) -> Path:
    path.parent.mkdir(parents = True, exist_ok = True)
    path.write_bytes(TINY_PNG)
    return path


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


def test_parse_single_cube_field_strength_case_supports_zero_field(tmp_path: Path):
    cube_path = tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc"

    batch_case = helpers.parse_single_cube_field_strength_case(cube_path)
    analysis_case = analysis_helpers.parse_single_cube_field_strength_case(cube_path)

    for case in [batch_case, analysis_case]:
        assert case["cube_path"] == str(cube_path.resolve())
        assert case["component"] == "z0"
        assert case["geometry"] == "zero"
        assert case["field_strength_G"] == pytest.approx(0.0)
        assert case["field_strength_token"] == "0g"
        assert case["field_strength_label"] == "0 G"


def test_organize_single_cube_field_strength_cases_groups_and_sorts(tmp_path: Path):
    cube_paths = [
        tmp_path / "co5bold" / "vx" / "50G" / "simulation_vx_50G.nc",
        tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc",
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
        tmp_path / "co5bold" / "hx" / "50G" / "simulation_hx_50G.nc",
    ]

    organized = helpers.organize_single_cube_field_strength_cases(cube_paths)

    assert [case["field_strength_label"] for case in organized["cases_by_geometry"]["zero"]] == [
        "0 G",
    ]
    assert [case["field_strength_label"] for case in organized["cases_by_geometry"]["horizontal"]] == [
        "10 G",
        "50 G",
    ]
    assert [case["field_strength_label"] for case in organized["cases_by_geometry"]["vertical"]] == [
        "10 G",
        "50 G",
    ]
    assert [case["geometry"] for case in organized["ordered_cases"]] == [
        "zero",
        "horizontal",
        "horizontal",
        "vertical",
        "vertical",
    ]


def test_td_analysis_field_strength_columns_include_zero_group(tmp_path: Path):
    cube_paths = [
        tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc",
        tmp_path / "co5bold" / "hx" / "10G" / "simulation_hx_10G.nc",
        tmp_path / "co5bold" / "vx" / "10G" / "simulation_vx_10G.nc",
    ]

    organized = analysis_helpers.organize_single_cube_field_strength_cases(cube_paths)
    column_cases = analysis_helpers.build_field_strength_comparison_column_cases(organized)

    assert [case["geometry"] if case is not None else None for case in column_cases] == [
        "zero",
        "horizontal",
        "vertical",
    ]


def test_td_analysis_comparison_height_validation_accepts_tiny_mismatch():
    case_config = {
        "data": {
            "resolved_h1_km": 0.000116,
            "resolved_h2_km": 220.000116,
        }
    }

    analysis_helpers.validate_single_cube_comparison_resolved_heights(
        case_config,
        0.0,
        220.0,
        "field-strength comparison",
    )


def test_td_analysis_comparison_height_validation_rejects_large_mismatch():
    case_config = {
        "data": {
            "resolved_h1_km": 0.0,
            "resolved_h2_km": 220.01,
        }
    }

    with pytest.raises(ValueError, match = "upper height"):
        analysis_helpers.validate_single_cube_comparison_resolved_heights(
            case_config,
            0.0,
            220.0,
            "field-strength comparison",
        )


def test_td_analysis_field_strength_defaults_do_not_emit_none_figsize():
    request = analysis_helpers.build_plot_request_defaults("field_strength_comparison", {})

    assert "figsize" not in request


def test_td_analysis_gaussian_comparison_filter_overlay_uses_defined_runtime_config():
    notebook = nbformat.read(PLOTS_NOTEBOOK_PATH, as_version = 4)
    source = next(
        cell.get("source", "")
        for cell in notebook.cells
        if cell.get("cell_type") == "code" and "def make_gaussian_filter_comparison_plot(" in cell.get("source", "")
    )

    assert "config = record['runtime_config'], modules = modules" not in source
    assert "config = case_filter_records[0][filter_index]['runtime_config'], modules = modules" in source


def test_td_analysis_gaussian_comparison_uses_filtered_komega_only_for_gaussian_classes():
    notebook = nbformat.read(PLOTS_NOTEBOOK_PATH, as_version = 4)
    source = next(
        cell.get("source", "")
        for cell in notebook.cells
        if cell.get("cell_type") == "code" and "def make_gaussian_filter_comparison_plot(" in cell.get("source", "")
    )

    def function_body(name: str) -> str:
        start = source.index(f"def {name}(")
        end = source.find("\ndef ", start + 1)
        return source[start:] if end == -1 else source[start:end]

    paired_gaussian_body = function_body("make_paired_cubes_gaussian_filter_comparison_plot")
    single_gaussian_body = function_body("make_gaussian_filter_comparison_plot")

    assert paired_gaussian_body.count("load_filtered_komega_plot_data") == 2
    assert single_gaussian_body.count("load_filtered_komega_plot_data") == 2
    assert "komega_mode = 'active'" in paired_gaussian_body
    assert "komega_mode = 'active'" in single_gaussian_body
    assert "load_filtered_komega_plot_data" not in function_body("make_field_strength_comparison_plot")
    assert "load_filtered_komega_plot_data" not in function_body("make_field_orientation_comparison_plot")


def test_td_analysis_filtered_komega_loader_uses_active_runtime_product(tmp_path: Path):
    active_komega = tmp_path / "active_filtered_komega.fits"
    values = np.array([[1.0, 2.0], [3.0, 4.0]], dtype = np.float32)
    fits.PrimaryHDU(values).writeto(active_komega)
    config = {
        "data": {"komega_outfile": str(active_komega)},
        "time_distance": {"dt": 10.0, "p_dx_Mm": 0.5},
    }
    plot_cache = {}

    loaded = analysis_helpers.load_filtered_komega_plot_data(config, plot_cache = plot_cache)

    assert loaded["data_file"] == active_komega.resolve()
    assert loaded["values"] == pytest.approx(values)
    assert loaded["data_source"] == "filtered_fits"
    assert loaded["visual_filtering_bypassed"] is False
    assert plot_cache[("filtered_komega_plot_data", str(active_komega.resolve()))] is loaded


def test_td_analysis_gaussian_comparison_requires_active_komega_product(tmp_path: Path):
    runtime_config = {
        "data": {
            "source_type": "single_cube",
            "outfile": str(_touch(tmp_path / "xc.fits")),
            "phase_outfile": str(_touch(tmp_path / "phase.fits")),
            "komega_outfile": str(tmp_path / "missing_filtered_komega.fits"),
        },
        "time_distance": {"dt": 10.0, "p_dx_Mm": 0.5},
    }

    output_paths = analysis_helpers.comparison_runtime_output_paths(runtime_config, komega_mode = "active")

    assert output_paths["komega_outfile"] == (tmp_path / "missing_filtered_komega.fits").resolve()
    with pytest.raises(FileNotFoundError, match = "missing_filtered_komega"):
        analysis_helpers.ensure_comparison_runtime_products(
            [runtime_config],
            {"execution_mode": "load", "missing_data_behavior": "error"},
            {},
            plot_label = "Gaussian-filter comparison",
            komega_mode = "active",
        )


def test_td_analysis_gaussian_comparison_legend_supports_current_matplotlib_api():
    notebook = nbformat.read(PLOTS_NOTEBOOK_PATH, as_version = 4)
    source = next(
        cell.get("source", "")
        for cell in notebook.cells
        if cell.get("cell_type") == "code" and "def add_gaussian_filter_comparison_legend(" in cell.get("source", "")
    )

    assert "legend.legendHandles" not in source
    assert "getattr(legend, 'legend_handles', None)" in source
    assert "getattr(legend, 'legendHandles', [])" in source


def test_td_analysis_gaussian_comparison_output_stems_are_filename_safe(tmp_path: Path):
    config = {
        "data": {
            "source_type": "paired_cubes",
            "paired_cubes": {"v1": str(tmp_path / "06May2019.AIA1600.ibis.aligned.final.fits")},
        },
        "filtering": {
            "enabled": True,
            "filter_sequence": ["gaussian"],
            "gaussian": {
                "enabled": True,
                "central_k": 2.0,
                "width_k": 1.5,
                "central_f": 2.0,
                "width_f": 2.0,
            },
            "magnetogram": {"enabled": False},
        },
    }
    filter_param_specs = [
        {"gaussian": {"central_k": 2.0, "width_k": 1.5, "central_f": 2.0, "width_f": 2.0}},
        {"gaussian": {"central_k": 0.5, "width_k": 1.5, "central_f": 2.0, "width_f": 2.0}},
        {"gaussian": {"central_k": 2.0, "width_k": 1.5, "central_f": 2.0, "width_f": 2.0}},
        {"gaussian": {"central_k": 1.0, "width_k": 1.0, "central_f": 3.0, "width_f": 3.0}},
        {"gaussian": {"central_k": 1.5, "width_k": 1.0, "central_f": 3.0, "width_f": 4.0}},
        {"gaussian": {"central_k": 1.5, "width_k": 4.0, "central_f": 3.0, "width_f": 3.0}},
    ]

    single_cube_stem = analysis_helpers.build_gaussian_filter_comparison_output_stem(
        config,
        filter_param_specs,
        0.0,
        220.0,
        "v3",
    )
    paired_cube_stem = analysis_helpers.build_paired_cubes_gaussian_filter_comparison_output_stem(
        config,
        filter_param_specs,
        paired_cases = [{"file_pair": ("a.fits", "b.fits")}],
    )

    for stem in [single_cube_stem, paired_cube_stem]:
        assert len(stem) <= 180
        assert len(f"{stem}.jpeg") < 255
        assert len(stem.rsplit("_", 1)[-1]) == 12


def test_comparison_view_discovers_and_writes_minimal_stable_sheets(tmp_path: Path):
    figure_dir = tmp_path / "figures"
    _write_tiny_png(
        figure_dir
        / "field_strength_comparison_v3_220km_440km_z0_0g_hx_10g_50g_100g.png"
    )
    _write_tiny_png(
        figure_dir
        / "field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_50g_100g.png"
    )
    _write_tiny_png(
        figure_dir
        / "field_orientation_comparison_v3_0km_220km_h10g_v10g_h50g_v50g.png"
    )
    _write_tiny_png(
        figure_dir
        / "gaussian_filter_comparison_v3_220km_440km_filters_2_f1_gauss.png"
    )
    _write_tiny_png(
        figure_dir
        / "paired_cubes_gaussian_filter_comparison_v3_0km_220km_filters_2_f1_gauss.png"
    )

    outputs = helpers.write_default_comparison_viewers(figure_dir)
    first_render = {
        name: (figure_dir / name).read_text(encoding = "utf-8")
        for name in [
            "field_strength_comparison.html",
            "field_orientation_comparison.html",
            "gaussian_filter_comparison.html",
        ]
    }
    first_view = (figure_dir / "comparison_view" / "field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_50g_100g.html").read_text(encoding = "utf-8")
    comparison_view.write_default_comparison_viewers(figure_dir)
    second_render = {
        name: (figure_dir / name).read_text(encoding = "utf-8")
        for name in first_render
    }

    field_strength_html = first_render["field_strength_comparison.html"]
    field_orientation_html = first_render["field_orientation_comparison.html"]

    assert outputs["field_strength_comparison"]["plot_count"] == 2
    assert "paired_cubes_gaussian_filter_comparison" not in field_strength_html
    assert field_strength_html.index("0-220 km") < field_strength_html.index("220-440 km")
    assert 'width="1" height="1"' in field_strength_html
    assert field_strength_html.count('class="figure-link"') == 2
    assert 'href="comparison_view/field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_50g_100g.html"' in field_strength_html
    assert 'target="_blank"' not in field_strength_html
    assert 'data-source-path="field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_50g_100g.png"' in field_strength_html
    assert 'window.location.assign(link.href)' in field_strength_html
    assert 'data-full-resolution-image src="../field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_50g_100g.png"' in first_view
    assert "max-width: none" in first_view
    assert "max-height: none" in first_view
    assert "width: max-content" not in first_view
    assert "transform" not in first_view
    assert 'class="subplot-hotspot"' in first_view
    assert 'data-nav-target="z0_0g-komega"' in first_view
    assert "const targets =" in first_view
    assert "window.history.pushState" in first_view
    assert "#subplot=" in first_view
    assert 'addEventListener("wheel"' in first_view
    assert 'addEventListener("gesturechange"' in first_view
    assert "image.style.width" in first_view
    assert "plot-card" not in field_strength_html
    assert "overflow" not in field_strength_html
    assert "Missing plot" not in field_orientation_html
    assert first_render == second_render


def test_comparison_view_labels_directional_geometry(tmp_path: Path):
    figure_dir = tmp_path / "figures"
    _write_tiny_png(
        figure_dir
        / "field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_gaussian_filtered_east.png"
    )

    outputs = helpers.write_default_comparison_viewers(figure_dir)
    field_strength_html = (figure_dir / "field_strength_comparison.html").read_text(encoding = "utf-8")
    full_view_html = (
        figure_dir
        / "comparison_view"
        / "field_strength_comparison_v3_0km_220km_z0_0g_hx_10g_gaussian_filtered_east.html"
    ).read_text(encoding = "utf-8")

    assert outputs["field_strength_comparison"]["plot_count"] == 1
    assert "0-220 km - East Wedge" in field_strength_html
    assert "0-220 km - East Wedge" in full_view_html


def test_plots_notebook_omits_gallery_export_block():
    notebook = nbformat.read(PLOTS_NOTEBOOK_PATH, as_version = 4)
    loader_source = next(
        cell.get("source", "")
        for cell in notebook.cells
        if cell.get("cell_type") == "code" and "def load_project_modules(" in cell.get("source", "")
    )
    execution_source = notebook.cells[3].get("source", "")

    assert "comparison_view" not in loader_source
    assert "write_default_comparison_viewers" in execution_source
    assert "comparison_view_error" in execution_source


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


def test_generate_shared_single_cube_height_index_pairs_accepts_tiny_grid_mismatch(tmp_path: Path):
    cube_1 = tmp_path / "cube_1.nc"
    cube_2 = tmp_path / "cube_2.nc"

    class _FakeTimeDistanceModule:
        @staticmethod
        def infer_netcdf_height_coordinates_km(file_path):
            file_path = str(Path(file_path).resolve())
            if file_path == str(cube_1.resolve()):
                return [0.0, 220.0, 440.0]
            if file_path == str(cube_2.resolve()):
                return [0.0, 220.000116, 440.000116]
            raise AssertionError(f"Unexpected file path: {file_path}")

    with pytest.warns(RuntimeWarning, match = "Height grids differ slightly"):
        comparison = helpers.generate_shared_single_cube_height_index_pairs(
            _FakeTimeDistanceModule(),
            [cube_1, cube_2],
        )

    assert comparison["height_values_km"] == pytest.approx([0.0, 220.0, 440.0])
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


def test_td_analysis_helpers_support_aia_bandpass_runtime_config(tmp_path: Path):
    runtime_config = {
        "paths": {
            "data_output_dir": str(tmp_path),
            "figure_dir": str(tmp_path),
            "animation_dir": str(tmp_path),
        },
        "data": {
            "source_type": "paired_cubes",
            "paired_cubes": {
                "data_dir": str(tmp_path),
                "v1": str(tmp_path / "06May2019.AIA1600.ibis.aligned.final.fits"),
                "v2": str(tmp_path / "06May2019.AIA1700.ibis.aligned.final.fits"),
                "delta_z_km": 100.0,
                "p_dx_Mm": 0.5,
                "dt": 10.0,
            },
        },
        "filtering": {
            "enabled": False,
            "filter_sequence": [],
            "magnetogram": {"enabled": False},
            "gaussian": {"enabled": False},
        },
        "time_distance": {},
        "plots": {"generate": {}},
    }

    assert analysis_helpers.parse_spectral_identifier(
        "06May2019.AIA1600.ibis.aligned.final.fits"
    ) == {"element": "AIA", "line": "1600"}

    prepared = analysis_helpers.prepare_runtime_config(runtime_config)

    assert "aia1600_aia1700" in Path(prepared["data"]["komega_outfile"]).name


def test_discover_paired_cube_groups_selects_canonical_diagnostics(tmp_path: Path):
    _, td, _ = helpers.load_mode_base_config(
        "paired_cubes",
        config_file = CONFIG_PATH,
    )
    directory = tmp_path / "06May2019"
    aia1600 = _touch(directory / "06May2019.AIA1600.ibis.aligned.fits")
    aia1600_final = _touch(directory / "06May2019.AIA1600.ibis.aligned.final.fits")
    aia1700_final = _touch(directory / "06May2019.AIA1700.ibis.aligned.final.fits")
    hmidop = _touch(directory / "06May2019.HMIdop.ibis.aligned.fits")
    fe7090 = _touch(directory / "06May2019.ibis.to.hmi.vel.fe7090.fits")
    _touch(directory / "06May2019.ibis.to.hmi.int.fe5434.fits")
    hmimag = _touch(directory / "06May2019.HMImag.ibis.aligned.fits")
    _touch(directory / "06May2019.HMIcont.ibis.aligned.fits")

    groups = helpers.discover_paired_cube_groups(tmp_path, time_distance_module = td)

    assert len(groups) == 1
    selected_names = {Path(path).name for path in groups[0]["diagnostic_files"]}
    assert selected_names == {
        aia1600_final.name,
        aia1700_final.name,
        hmidop.name,
        fe7090.name,
    }
    assert aia1600.name not in selected_names
    assert groups[0]["magnetogram"] == str(hmimag.resolve())
    assert len(groups[0]["file_pairs"]) == 6


def test_discover_paired_cube_groups_fails_ambiguous_top_priority(tmp_path: Path):
    _, td, _ = helpers.load_mode_base_config(
        "paired_cubes",
        config_file = CONFIG_PATH,
    )
    directory = tmp_path / "06May2019"
    _touch(directory / "06May2019.ibis.to.hmi.vel.fe7090.copy1.fits")
    _touch(directory / "06May2019.ibis.to.hmi.vel.fe7090.copy2.fits")
    _touch(directory / "06May2019.ibis.to.hmi.vel.fe5434.fits")

    with pytest.raises(ValueError, match = "Ambiguous paired_cubes candidates"):
        helpers.discover_paired_cube_groups(tmp_path, time_distance_module = td)


def test_discover_paired_cube_groups_warns_and_skips_single_diagnostic(tmp_path: Path):
    _, td, _ = helpers.load_mode_base_config(
        "paired_cubes",
        config_file = CONFIG_PATH,
    )
    directory = tmp_path / "06May2019"
    _touch(directory / "06May2019.ibis.to.hmi.vel.fe7090.fits")

    with pytest.warns(RuntimeWarning, match = "only one valid diagnostic cube"):
        groups = helpers.discover_paired_cube_groups(tmp_path, time_distance_module = td)

    assert groups == []


def test_config_discovers_only_non_aia_observational_batch_inputs(tmp_path: Path):
    config_module = _load_config_module()
    root = tmp_path / "Vesa_2025" / "Data"
    root_level = _touch(root / "06May2019.ibis.to.hmi.vel.rootonly.fits")
    fe5434 = _touch(root / "06May2019" / "06May2019.ibis.to.hmi.vel.fe5434.fits")
    fe7090 = _touch(root / "06May2019" / "06May2019.ibis.to.hmi.vel.fe7090.fits")
    nested_ca = _touch(root / "08May2019" / "nested" / "08May2019.ibis.to.hmi.vel.ca8542.fits")
    _touch(root / "06May2019" / "06May2019.AIA1600.ibis.aligned.final.fits")
    _touch(root / "06May2019" / "06May2019.ibis.to.hmi.int.fe5434.fits")
    _touch(root / "06May2019" / "06May2019.HMImag.ibis.aligned.fits")
    _touch(root / "06May2019" / ".hidden.vel.fe6173.fits")
    _touch(root / "06May2019" / "06May2019.cache.vel.fe6173.fits")

    discovered = config_module.discover_paired_cube_batch_input_paths(root)

    assert discovered == [
        str(fe5434.resolve()),
        str(fe7090.resolve()),
        str(nested_ca.resolve()),
    ]
    assert str(root_level.resolve()) not in discovered
    assert all("aia" not in Path(path).name.lower() for path in discovered)
    assert all(Path(path).is_file() for path in discovered)


def test_collect_paired_cube_batch_pair_records_groups_config_file_list_by_directory(tmp_path: Path):
    config_module = _load_config_module()
    _, td, _ = helpers.load_mode_base_config(
        "paired_cubes",
        config_file = CONFIG_PATH,
    )
    root = tmp_path / "Vesa_2025" / "Data"
    first_a = _touch(root / "06May2019" / "06May2019.ibis.to.hmi.vel.fe5434.fits")
    first_b = _touch(root / "06May2019" / "06May2019.ibis.to.hmi.vel.fe7090.fits")
    second_a = _touch(root / "08May2019" / "08May2019.ibis.to.hmi.vel.ca8542.fits")
    second_b = _touch(root / "08May2019" / "08May2019.ibis.to.hmi.vel.k7699.fits")
    _touch(root / "06May2019" / "06May2019.AIA1700.ibis.aligned.final.fits")

    discovered = config_module.discover_paired_cube_batch_input_paths(root)
    records = helpers.collect_paired_cube_batch_pair_records(
        {"input_paths": discovered, "file_pairs": []},
        td,
        default_delta_z_km = 168.0,
        default_p_dx_Mm = 0.43,
        default_dt = 11.88,
    )

    file_pairs = [record["file_pair"] for record in records]

    assert file_pairs == [
        (str(first_a.resolve()), str(first_b.resolve())),
        (str(second_a.resolve()), str(second_b.resolve())),
    ]
    assert all(Path(file_1).parent == Path(file_2).parent for file_1, file_2 in file_pairs)
    assert all("aia" not in (Path(file_1).name + Path(file_2).name).lower() for file_1, file_2 in file_pairs)


def test_build_recursive_paired_cubes_batch_plan_does_not_configure_magnetogram_paths(tmp_path: Path):
    _, td, base_config = helpers.load_mode_base_config(
        "paired_cubes",
        config_file = CONFIG_PATH,
    )
    directory = tmp_path / "06May2019"
    fe5434 = _touch(directory / "06May2019.ibis.to.hmi.vel.fe5434.fits")
    fe7090 = _touch(directory / "06May2019.ibis.to.hmi.vel.fe7090.fits")
    hmimag = _touch(directory / "06May2019.HMImag.ibis.aligned.fits")

    plan = helpers.build_recursive_paired_cubes_batch_plan(
        base_config,
        td,
        tmp_path,
        delta_z_km = 300.0,
        p_dx_Mm = 0.6,
        dt = 10.0,
    )

    assert len(plan["run_configs"]) == 1
    assert plan["file_pairs"] == [(str(fe5434.resolve()), str(fe7090.resolve()))]
    assert plan["v1_list"] == [str(fe5434.resolve())]
    assert plan["v2_list"] == [str(fe7090.resolve())]

    run_config = plan["run_configs"][0]
    assert run_config["data"]["source_type"] == "paired_cubes"
    assert run_config["data"]["paired_cubes"]["data_dir"] == str(directory.resolve())
    assert run_config["data"]["paired_cubes"]["v1"] == str(fe5434.resolve())
    assert run_config["data"]["paired_cubes"]["v2"] == str(fe7090.resolve())
    assert run_config["data"]["paired_cubes"]["delta_z_km"] == pytest.approx(300.0)
    assert run_config["data"]["paired_cubes"]["p_dx_Mm"] == pytest.approx(0.6)
    assert run_config["data"]["paired_cubes"]["dt"] == pytest.approx(10.0)
    assert "magnetogram_v1" not in run_config["filtering"]["magnetogram"]
    assert "magnetogram_v2" not in run_config["filtering"]["magnetogram"]
    assert plan["directory_records"][0]["magnetogram"] == str(hmimag.resolve())


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
        tmp_path / "co5bold" / "z0" / "0G" / "simulation_z0_0G.nc",
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
    assert all(run_config["filtering"]["filter_sequence"] == ["gaussian"] for run_config in comparison_plan["run_configs"])
    assert all(run_config["filtering"]["magnetogram"]["enabled"] is False for run_config in comparison_plan["run_configs"])

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
            "Executing plots.ipynb requires the 'nbformat' and 'nbclient' packages."
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


def test_td_analysis_load_time_distance_data_uses_plot_cache(monkeypatch, tmp_path: Path):
    data_file = tmp_path / "example_xc.fits"
    call_count = {"count": 0}

    def _fake_getdata(path):
        call_count["count"] += 1
        assert Path(path) == data_file.resolve()
        return np.arange(12, dtype = np.float64).reshape(3, 4)

    monkeypatch.setattr(analysis_helpers.fits, "getdata", _fake_getdata)

    plot_cache = {}
    first = analysis_helpers.load_time_distance_data(
        data_file,
        30.0,
        0.5,
        axis_type = "time_lag",
        plot_cache = plot_cache,
    )
    second = analysis_helpers.load_time_distance_data(
        data_file,
        30.0,
        0.5,
        axis_type = "time_lag",
        plot_cache = plot_cache,
    )
    frequency = analysis_helpers.load_time_distance_data(
        data_file,
        30.0,
        0.5,
        axis_type = "frequency",
        plot_cache = plot_cache,
    )

    assert first is second
    assert frequency is not first
    assert call_count["count"] == 2
    np.testing.assert_allclose(first["values"], np.arange(12, dtype = np.float64).reshape(3, 4))


def test_td_analysis_normalize_cross_correlation_display_vectorizes_rows():
    values = np.array(
        [
            [1.0, -2.0, np.nan],
            [0.0, 0.0, 0.0],
            [np.nan, np.nan, np.nan],
            [-4.0, 2.0, 0.0],
        ],
        dtype = np.float64,
    )

    normalized = analysis_helpers.normalize_cross_correlation_display(values)

    expected = np.array(
        [
            [0.5, -1.0, np.nan],
            [0.0, 0.0, 0.0],
            [np.nan, np.nan, np.nan],
            [-1.0, 0.5, 0.0],
        ],
        dtype = np.float64,
    )
    np.testing.assert_allclose(normalized, expected, equal_nan = True)
    assert np.shares_memory(normalized, values) is False


def test_td_analysis_regular_grid_plotter_prefers_imshow_and_falls_back_for_irregular_axes():
    pytest.importorskip("matplotlib")
    analysis_helpers.plt.switch_backend("Agg")

    fig, ax = analysis_helpers.plt.subplots()
    try:
        image = analysis_helpers.plot_regular_grid_image(
            ax,
            np.array([0.0, 1.0, 2.0]),
            np.array([10.0, 12.0]),
            np.ones((2, 3), dtype = np.float64),
        )
        assert image.__class__.__name__ == "AxesImage"
        assert image.get_extent() == [-0.5, 2.5, 9.0, 13.0]
    finally:
        analysis_helpers.plt.close(fig)

    fig, ax = analysis_helpers.plt.subplots()
    try:
        mesh = analysis_helpers.plot_regular_grid_image(
            ax,
            np.array([0.0, 1.0, 3.0]),
            np.array([0.0, 1.0]),
            np.ones((2, 3), dtype = np.float64),
        )
        assert mesh.__class__.__name__ == "QuadMesh"
    finally:
        analysis_helpers.plt.close(fig)


def test_td_batch_injected_notebook_defaults_to_noninteractive_batch_plotting():
    source = helpers.build_td_analysis_input_cell_source(
        {"data": {"source_type": "paired_cubes"}},
        use_config = True,
        direct_plot_requests = None,
    )

    assert "config['show_plots'] = bool(runtime_config.get('show_plots', False))" in source
    assert "config['close_figures_after_save'] = bool(runtime_config.get('close_figures_after_save', True))" in source


def test_execute_td_analysis_for_batch_in_process_records_profile_fields(monkeypatch, tmp_path: Path):
    runtime_config = {
        "data": {
            "source_type": "paired_cubes",
            "outfile": str(tmp_path / "example_xc.fits"),
            "komega_outfile": str(tmp_path / "example_komega.fits"),
        }
    }
    run_records = [
        {
            "label": "pair-a",
            "source_type": "paired_cubes",
            "runtime_config": runtime_config,
            "status": "completed",
        }
    ]

    monkeypatch.setattr(helpers, "import_td_analysis_notebook_dependencies", lambda: (object(), object()))
    monkeypatch.setattr(helpers, "load_td_analysis_in_process_runtime", lambda analysis_notebook = None: object())

    def _fake_in_process(analysis_runtime, runtime_config, **kwargs):
        assert runtime_config["show_plots"] is False
        assert runtime_config["close_figures_after_save"] is True
        return {
            "generated_products": [{"plot_type": "time_distance", "saved_file": "plot.jpeg"}],
            "component_times_seconds": {"setup": 0.01, "build_plot_requests": 0.02},
            "plot_times_seconds": {"time_distance": 0.03},
            "plot_call_counts": {"time_distance": 1},
        }

    monkeypatch.setattr(helpers, "execute_td_analysis_in_process", _fake_in_process)

    records = helpers.execute_td_analysis_for_batch(
        run_records,
        analysis_backend = "in_process",
        profile_enabled = True,
        profile_output_dir = tmp_path,
        verbose = False,
    )

    assert len(records) == 1
    record = records[0]
    assert record["status"] == "completed"
    assert record["analysis_backend"] == "in_process"
    assert record["wall_seconds"] >= 0.0
    assert record["peak_rss_bytes"] > 0
    assert record["component_times_seconds"]["setup"] == pytest.approx(0.01)
    assert record["plot_times_seconds"]["time_distance"] == pytest.approx(0.03)
    assert Path(record["profile_summary_file"]).exists()


def test_performance_audit_pipeline_profile_writes_summary_schema(tmp_path: Path):
    output_paths = {
        "outfile": tmp_path / "data" / "example_xc.fits",
        "phase_outfile": tmp_path / "data" / "example_phase.fits",
        "komega_outfile": tmp_path / "data" / "example_komega.fits",
        "coherence_outfile": tmp_path / "data" / "example_coherence.fits",
    }

    class _FakePipeline:
        def __init__(self):
            self.xcorrj_diagnostics = {"engine": "fake"}

        def load_dopplergrams(self):
            return None

        def compute_komega_diagram(self):
            return None

        def compute_coherence_diagram(self):
            return None

        def xcorrj(self):
            return None

        def save_time_distance(self):
            return None

        def run(self):
            self.load_dopplergrams()
            self.compute_komega_diagram()
            self.compute_coherence_diagram()
            self.xcorrj()
            self.save_time_distance()
            for path in output_paths.values():
                path.parent.mkdir(parents = True, exist_ok = True)
                fits.writeto(path, np.ones((2, 2), dtype = np.float32), overwrite = True)
            return {key: str(value) for key, value in output_paths.items()}

    class _FakeTimeDistanceModule:
        @staticmethod
        def build_pipeline(config_file, config_override):
            return None, {"runtime": "config"}, _FakePipeline()

    summary = performance_audit.run_pipeline_profile(
        _FakeTimeDistanceModule(),
        CONFIG_PATH,
        {"fake": "config"},
        tmp_path / "profile",
    )

    assert summary["status"] == "completed"
    assert summary["wall_seconds"] >= 0.0
    assert summary["peak_rss_bytes"] > 0
    assert "load_dopplergrams" in summary["component_times_seconds"]
    assert summary["outputs"]["outfile"]["shape"] == [2, 2]
    assert Path(summary["summary_file"]).exists()
    assert Path(summary["profile_file"]).exists()
