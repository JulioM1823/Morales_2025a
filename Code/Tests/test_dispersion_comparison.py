'''
Purpose
-------
Regression checks for dispersion comparison.

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
import json
from pathlib import Path
import re
import sys

from astropy.io import fits
import nbformat
import numpy as np
from PIL import Image as PILImage
import pytest


ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_DIR = ROOT / "Code" / "Time-Distance"
if str(TIME_DISTANCE_DIR) not in sys.path:
    sys.path.insert(0, str(TIME_DISTANCE_DIR))
VESA_2026_DIR = ROOT.parent / "Vesa_2026"
DEMO_NOTEBOOK = TIME_DISTANCE_DIR / "komega_single_model_demo.ipynb"

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _load_module(name: str, path: Path):
    '''
    Purpose
    -------
    Import the selected on-disk module under the isolated name used by the test.

    Inputs
    ------
    name: str
        Module, callback, variable, or context label selected by the caller.

    path: Path
        Input or output path used by this fixture or its local substitute.

    Outputs
    -------
    module: types.ModuleType
        Executed module exposing the implementation under test. Where present,
        register it in sys.modules before loader execution.
    '''

    # Create and execute an isolated import of the on-disk implementation module.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dispersion = _load_module(
    "dispersion_comparison_under_test",
    TIME_DISTANCE_DIR / "dispersion_comparison.py",
)
config_module = _load_module(
    "time_distance_config_for_dispersion_test",
    TIME_DISTANCE_DIR / "config.py",
)
gallery = _load_module(
    "comparison_gallery_for_dispersion_test",
    TIME_DISTANCE_DIR / "comparison_gallery.py",
)


def _comparison_config(sample_count: int = 8) -> dict:
    '''
    Purpose
    -------
    Copy comparison defaults and restrict both numerical axes to the requested sample
    count.

    Inputs
    ------
    sample_count: int
        Maximum samples retained on each comparison axis.

    Outputs
    -------
    config: dict
        Configuration containing empty data settings and bounded comparison axes.
    '''

    # Copy defaults before restricting comparison grid sizes for this test.
    settings = json.loads(json.dumps(config_module.default_komega_comparison))
    settings["vesa_2026_dir"] = str(VESA_2026_DIR)
    settings["max_k_samples"] = sample_count
    settings["max_frequency_samples"] = sample_count
    return {"data": {}, "komega_comparison": settings}


def _pair_metadata() -> dict:
    '''
    Purpose
    -------
    Construct fixed height-pair magnetic parameters for comparison tests.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    metadata: dict
        Two-height metadata using km, km/s, and degree units.
    '''

    return {
        "dispersion_height_pair": {
            "height_values_km": [0.0, 220.0],
            "a_by_height_km_s": [2.0, 4.0],
            "a_km_s": 3.0,
            "theta_by_height_deg": [20.0, 40.0],
            "theta_deg": 30.0,
            "phi_by_height_deg": [179.0, -179.0],
            "phi_deg": 180.0,
            "dz_km": 220.0,
        }
    }


def _write_tiny_png(path: Path) -> Path:
    '''
    Purpose
    -------
    Write the fixed tiny PNG fixture, creating its parent directories.

    Inputs
    ------
    path: Path
        Input or output path used by this fixture or its local substitute.

    Outputs
    -------
    path: pathlib.Path
        Destination of the written image.
    '''

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(TINY_PNG)
    return path


def test_height_pair_context_uses_layer_means_and_physical_separation():
    '''
    Purpose
    -------
    Verify height pair context uses layer means and physical separation.

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

    context = dispersion.resolve_height_pair_context(_comparison_config(), _pair_metadata())

    assert context["a_km_s"] == pytest.approx(3.0)
    theta = np.deg2rad([20.,40.]); phi = np.deg2rad([179.,-179.])
    bx = np.mean(np.sin(theta)*np.cos(phi)); by = np.mean(np.sin(theta)*np.sin(phi)); bz = np.mean(np.cos(theta))
    assert context["theta_deg"] == pytest.approx(np.degrees(np.arctan2(np.hypot(bx,by),bz)))
    assert context["phi_deg"] == pytest.approx(np.degrees(np.arctan2(by,bx)))
    assert context["dz_km"] == pytest.approx(220.0)
    assert context["theta_convention"] == "inclination from +z"
    assert context["phi_convention"] == "azimuth atan2(By, Bx), +x toward +y"
    assert context["dz_convention"] == "absolute physical layer separation"


def test_model_adapter_preserves_authoritative_structure_and_model_specific_inputs():
    '''
    Purpose
    -------
    Verify model adapter preserves authoritative structure and model specific inputs.

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

    config = _comparison_config()
    context = dispersion.resolve_height_pair_context(config, _pair_metadata())
    modules = dispersion.load_vesa_2026_modules(config)

    assert Path(modules["functions_file"]).resolve() == (
        VESA_2026_DIR / "Code" / "diagnostic_diagram" / "functions.py"
    ).resolve()
    assert Path(modules["config_file"]).resolve() == (
        VESA_2026_DIR / "Code" / "diagnostic_diagram" / "config.py"
    ).resolve()
    assert "sf1966" not in dispersion.MODEL_BY_NAME

    for model_spec in dispersion.MODEL_SPECS:
        params = dispersion.resolve_model_parameters(
            config,
            model_spec["model"],
            context,
            modules,
        )
        authoritative = modules["config_module"].params[model_spec["model"]]
        assert params["model"] == model_spec["model"]
        assert params["kz_order"] == authoritative["kz_order"]
        assert params["omega_order"] == authoritative["omega_order"]
        assert params["dz"] == pytest.approx(220.0)
        if "a" in model_spec["uses"]:
            assert params["a"] == pytest.approx(3.0)
        if "theta" in model_spec["uses"]:
            assert params["theta"] == pytest.approx(np.deg2rad(context["theta_deg"]))
        if "phi" in model_spec["uses"]:
            assert params["phi"] == pytest.approx(np.deg2rad(context["phi_deg"]))
        if model_spec["model"] in {"mt1982", "mt1981"}:
            assert "a" not in params
            assert "theta" not in params
            assert "phi" not in params


def test_end_to_end_assets_and_click_destination_have_exact_eight_rows(tmp_path: Path):
    '''
    Purpose
    -------
    Verify end to end assets and click destination have exact eight rows.

    Inputs
    ------
    tmp_path: Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    figure_dir = tmp_path / "figures"
    simulation_dir = figure_dir / "Simulations"
    observed = _write_tiny_png(
        simulation_dir / "hx_10g_v3_0km_220km_unfiltered_komega.png"
    )
    observed_bytes = observed.read_bytes()
    config = _comparison_config(sample_count=8)

    manifest = dispersion.generate_komega_comparison_assets(
        observed,
        np.linspace(0.0, 5.0, 8),
        np.linspace(0.5, 10.0, 8),
        config,
        pair_metadata=_pair_metadata(),
    )

    assert observed.read_bytes() == observed_bytes
    assert tuple(row["label"] for row in manifest["rows"]) == dispersion.COMPARISON_ROW_LABELS
    assert len(manifest["rows"]) == 8
    assert manifest["souffrin_included"] is False
    assert "sf1966" not in {record["model"] for record in manifest["models"]}
    assert all((observed.parent / row["path"]).exists() for row in manifest["rows"])
    assert manifest["solver_domain"]["k_h_Mm_inverse"] == pytest.approx([0.0, 5.0])
    assert manifest["solver_domain"]["nu_mHz"] == pytest.approx([0.5, 10.0])

    expected_branch_counts = {
        "nc2009": 6,
        "alfven_mode": 2,
        "slow_mode": 2,
        "fast_mode": 2,
        "bunte1993": 2,
        "mt1982": 2,
        "mt1981": 2,
    }
    for record in manifest["models"]:
        assert record["kz_branches_rendered"] == expected_branch_counts[record["model"]]
        assert record["colorbars_rendered"] == max(1, expected_branch_counts[record["model"]])
        assert record["kz_branches_rendered"] == record["authoritative_kz_order"]
        assert record["omega_solver_failures"] == 0
        if record["model"] in {"alfven_mode", "slow_mode", "fast_mode"}:
            assert len(record["kz_branch_labels"]) == expected_branch_counts[record["model"]]
            assert all("energy" in label for label in record["kz_branch_labels"])
    assert manifest["authoritative_source"]["methods"] == list(
        dispersion.AUTHORITATIVE_METHODS
    )
    first_theory_file = observed.parent / manifest["rows"][1]["path"]
    with PILImage.open(first_theory_file) as theory_image:
        assert theory_image.info["dpi"] == pytest.approx((300.0, 300.0), abs=0.1)
    assert all("$k$--$\\omega$" in spec["plot_title_tex"] for spec in dispersion.MODEL_SPECS)
    assert "$\\theta=" in dispersion._format_parameter("theta", np.deg2rad(30.0))

    _write_tiny_png(
        simulation_dir / "field_strength_comparison_v3_0km_220km_hx_10g.png"
    )
    _write_tiny_png(simulation_dir / "hx_10g_v3_0km_220km_xc.png")
    _write_tiny_png(simulation_dir / "hx_10g_v3_0km_220km_phase_diff.png")
    html_dir = figure_dir / "HTML Figures"
    gallery.write_default_comparison_viewers(figure_dir, html_dir=html_dir)

    detail_html = (
        html_dir
        / "comparison_view"
        / "field_strength_comparison_v3_0km_220km_hx_10g.html"
    ).read_text(encoding="utf-8")
    assert f'data-source-path="Simulations/{observed.name}"' in detail_html
    gallery_html = (html_dir / "field_strength_comparison.html").read_text(encoding="utf-8")
    assert 'src="../Simulations/field_strength_comparison_v3_0km_220km_hx_10g.png"' in gallery_html
    targets_match = re.search(r"const targets = (.*?);\n", detail_html)
    assert targets_match is not None
    targets = json.loads(targets_match.group(1))
    komega_target = next(target for target in targets if target["id"].endswith("-komega"))
    assert tuple(row["label"] for row in komega_target["comparisonRows"]) == (
        dispersion.COMPARISON_ROW_LABELS
    )
    assert 'section.dataset.komegaComparisonRow' in detail_html
    assert "souffrin" not in detail_html.lower()


def test_zero_field_height_pair_keeps_all_rows_and_marks_alfven_unavailable(tmp_path: Path):
    '''
    Purpose
    -------
    Verify zero field height pair keeps all rows and marks alfven unavailable.

    Inputs
    ------
    tmp_path: Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    observed = _write_tiny_png(tmp_path / "z0_0g_v3_0km_220km_unfiltered_komega.png")
    metadata = {
        "dispersion_height_pair": {
            "height_values_km": [0.0, 220.0],
            "a_by_height_km_s": [0.0, 0.0],
            "a_km_s": 0.0,
            "theta_by_height_deg": [np.nan, np.nan],
            "phi_by_height_deg": [np.nan, np.nan],
            "dz_km": 220.0,
        }
    }

    manifest = dispersion.generate_komega_comparison_assets(
        observed,
        np.linspace(0.0, 5.0, 8),
        np.linspace(0.5, 10.0, 8),
        _comparison_config(sample_count=8),
        pair_metadata=metadata,
    )

    assert len(manifest["rows"]) == 8
    assert all((observed.parent / row["path"]).exists() for row in manifest["rows"])
    alfven = next(record for record in manifest["models"] if record["model"] == "alfven_mode")
    assert alfven["kz_branches_rendered"] == 0
    assert alfven["colorbars_rendered"] == 1
    assert "No physical Alfvén branch" in alfven["unavailable_reason"]
    assert manifest["pair_context"]["angle_note"].startswith("magnetic direction undefined")


def test_single_model_demo_interface_uses_selected_dataset_and_config_parameters(tmp_path: Path):
    '''
    Purpose
    -------
    Verify single model demo interface uses selected dataset and config parameters.

    Inputs
    ------
    tmp_path: Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset_file = tmp_path / "selected_komega.fits"
    values = np.arange(8*9, dtype=np.float32).reshape(8, 9) - 20.0
    header = fits.Header()
    header["CRVAL1"] = 0.0
    header["CDELT1"] = 0.5
    header["CRVAL2"] = 0.5
    header["CDELT2"] = 0.75
    header["AKMSH1"] = 2.0
    header["AKMSH2"] = 4.0
    header["PAIRA"] = 3.0
    header["THAVG1"] = 20.0
    header["THAVG2"] = 40.0
    header["PAIRTHE"] = 30.0
    header["PHAVG1"] = 10.0
    header["PHAVG2"] = 20.0
    header["PAIRPHI"] = 15.0
    header["H1_KM"] = 0.0
    header["H2_KM"] = 220.0
    header["DZ_KM"] = 220.0
    fits.PrimaryHDU(values, header=header).writeto(dataset_file)

    config = _comparison_config(sample_count=8)
    config["time_distance"] = {"p_dx_Mm": 0.1, "dt": 30.0}
    dataset = dispersion.load_komega_fits_dataset(dataset_file, config)

    np.testing.assert_allclose(dataset["values"], values)
    np.testing.assert_allclose(dataset["k_axis_Mm_inverse"], np.arange(8)*0.5)
    np.testing.assert_allclose(dataset["nu_axis_mHz"], 0.5 + np.arange(9)*0.75)
    assert dataset["pair_metadata"]["a_h1_km_s"] == pytest.approx(2.0)
    assert dataset["pair_metadata"]["a_h2_km_s"] == pytest.approx(4.0)

    observed_file = tmp_path / "observed.png"
    figure, _ = dispersion.plot_observed_komega_dataset(dataset, observed_file)
    assert observed_file.exists()
    axis = figure.axes[0]
    style = dispersion.resolve_komega_plot_style(config)
    assert style["vmin_deg"] == pytest.approx(-80.0)
    assert style["vmax_deg"] == pytest.approx(80.0)
    np.testing.assert_allclose(figure.get_size_inches(), style["figsize"])
    np.testing.assert_allclose(axis.get_xlim(), style["xlim_Mm_inverse"])
    np.testing.assert_allclose(axis.get_ylim(), style["ylim_mHz"])
    assert axis.get_box_aspect() == pytest.approx(style["panel_box_aspect"])
    assert axis.images[0].get_cmap().name == "fusion"
    assert axis.images[0].norm.vmin == pytest.approx(-80.0)
    assert axis.images[0].norm.vmax == pytest.approx(80.0)
    assert r"$k$--$\omega$" in figure._suptitle.get_text()
    assert r"$\nu / 2\pi$" == axis.get_ylabel().split(" [")[0]
    dispersion.plt.close(figure)

    model_file = tmp_path / "mt1981.png"
    product = dispersion.generate_single_model_plot(dataset, "mt1981", config, model_file)
    assert model_file.exists()
    assert product["result"]["kz_branch_count"] == 2
    assert product["pair_context"]["dz_km"] == pytest.approx(220.0)
    configured = config["komega_comparison"]["models"]["mt1981"]["params"]
    for name in ("cs", "H", "N"):
        assert product["result"]["params"][name] == pytest.approx(configured[name])


def test_single_model_demo_uses_config_without_simulation_metadata(tmp_path: Path):
    '''
    Purpose
    -------
    Verify single model demo uses config without simulation metadata.

    Inputs
    ------
    tmp_path: Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset_file = tmp_path / "observed_only.fits"
    values = np.linspace(-30.0, 70.0, 8*9, dtype=np.float32).reshape(8, 9)
    fits.PrimaryHDU(values).writeto(dataset_file)

    config = _comparison_config(sample_count=8)
    dataset = dispersion.load_komega_fits_dataset(dataset_file, config)
    assert dataset["pair_metadata"] == {}
    sampling = config["komega_comparison"]["standalone_sampling"]
    np.testing.assert_allclose(
        dataset["k_axis_Mm_inverse"],
        np.linspace(0.0, np.pi/sampling["p_dx_Mm"], values.shape[0]),
    )
    np.testing.assert_allclose(
        dataset["nu_axis_mHz"],
        np.linspace(0.0, 0.5/sampling["dt_s"]*1.0e3, values.shape[1]),
    )

    # Require the expected ValueError from this failure case.
    with pytest.raises(
        ValueError,
        match="requires Alfven speeds calculated independently",
    ):
        dispersion.resolve_height_pair_context(config, dataset["pair_metadata"])

    output_file = tmp_path / "eight_rows.png"
    comparison = dispersion.generate_standalone_komega_comparison(
        dataset,
        config,
        output_file,
    )
    manifest = comparison["manifest"]
    context = manifest["pair_context"]
    standalone = config["komega_comparison"]["standalone_pair"]

    assert output_file.exists()
    with PILImage.open(output_file) as composite:
        assert composite.height > composite.width
    assert tuple(row["label"] for row in manifest["rows"]) == dispersion.COMPARISON_ROW_LABELS
    assert len(manifest["rows"]) == 8
    assert len(manifest["models"]) == 7
    assert manifest["souffrin_included"] is False
    assert all(
        (comparison["observed_file"].parent / row["path"]).exists()
        for row in manifest["rows"]
    )
    assert context["standalone_fallback_used"] is True
    assert context["a_km_s"] == pytest.approx(standalone["a_km_s"])
    assert context["theta_deg"] == pytest.approx(standalone["theta_deg"])
    assert context["phi_deg"] == pytest.approx(standalone["phi_deg"])
    assert context["dz_km"] == pytest.approx(standalone["dz_km"])
    assert context["a_by_height_km_s"] == []
    assert context["theta_by_height_deg"] == []
    assert context["phi_by_height_deg"] == []
    assert context["a_source"] == "config komega_comparison.standalone_pair"
    assert context["theta_source"] == "config komega_comparison.standalone_pair"
    assert context["phi_source"] == "config komega_comparison.standalone_pair"
    assert context["dz_source"] == "config komega_comparison.standalone_pair"


def test_all_models_demo_notebook_is_small_valid_and_user_editable():
    '''
    Purpose
    -------
    Verify all models demo notebook is small valid and user editable.

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

    notebook = nbformat.read(DEMO_NOTEBOOK, as_version=4)
    nbformat.validate(notebook)
    code = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")

    assert len(notebook.cells) == 3
    assert "DATASET_PATH =" in code
    assert "MODEL_NAME =" not in code
    assert "standalone_pair" in code
    assert "COMPARISON_ROW_LABELS" not in code
    assert "load_komega_fits_dataset" in code
    assert "generate_standalone_komega_comparison" in code
    assert "seven_row_comparison" in code
    for cell in notebook.cells:
        if cell.cell_type == "code":
            compile(cell.source, str(DEMO_NOTEBOOK), "exec")
            # Saved successful runs remain valid user-editable notebooks.
            assert all(output.output_type != "error" for output in cell.outputs)
