from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[2]
TIME_DISTANCE_DIR = ROOT / "Code" / "Time-Distance"
SCRIPT_PATH = TIME_DISTANCE_DIR / "migrate_figure_animation_hierarchy.py"

if str(TIME_DISTANCE_DIR) not in sys.path:
    sys.path.insert(0, str(TIME_DISTANCE_DIR))


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("figure_animation_migration_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load_migration_module()


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents = True, exist_ok = True)
    path.touch()
    return path


def test_build_migration_plan_routes_legacy_simulation_figure(tmp_path: Path):
    source = _touch(
        tmp_path
        / "legacy"
        / "hx_10g_v3_0km_220km_gaussian_filtered_gauss_ck_2_wk_2_cf_1_5_wf_1_5_phase_diff.jpeg"
    )

    records, unclassified = migration.build_migration_plan(tmp_path)

    assert unclassified == []
    assert len(records) == 1
    record = records[0]
    assert record.source == source.resolve()
    assert record.action == "move"
    assert record.filter_folder == "filter_1"
    assert record.product == "phase_difference"
    assert record.destination == (
        tmp_path
        / "filter_1"
        / "simulations"
        / "nonmagneto"
        / "horizontal"
        / "10G"
        / "phase"
        / "annulus"
        / "v3"
        / "hx_10g_v3_0km_220km_phase_diff.jpeg"
    ).resolve()
    assert "filtering.gaussian.central_f: 1.5" in record.filter_parameters
    assert "filtering.gaussian.central_k: 2.0" in record.filter_parameters
    assert "filtering.gaussian.width_f: 1.5" in record.filter_parameters
    assert "filtering.gaussian.width_k: 2.0" in record.filter_parameters


def test_build_migration_plan_routes_legacy_observation_figure(tmp_path: Path):
    source = _touch(
        tmp_path
        / "legacy"
        / "06may2019_v2_north_b_gt_50g_phase_diff.png"
    )

    records, unclassified = migration.build_migration_plan(tmp_path)

    assert unclassified == []
    assert len(records) == 1
    record = records[0]
    assert record.source == source.resolve()
    assert record.destination == (
        tmp_path
        / "filter_1"
        / "observations"
        / "magneto"
        / "06may2019"
        / "phase"
        / "north"
        / "v2"
        / "06may2019_v2_north_phase_diff.png"
    ).resolve()
    assert "filtering.magnetogram.selection: magnetic" in record.filter_parameters
    assert "filtering.magnetogram.threshold_G: 50.0" in record.filter_parameters


def test_build_migration_plan_appends_duplicate_suffix(tmp_path: Path):
    filename = "hx_10g_v3_0km_220km_gaussian_filtered_gauss_ck_2_wk_2_cf_1_5_wf_1_5_phase_diff.jpeg"
    _touch(tmp_path / "legacy_a" / filename)
    _touch(tmp_path / "legacy_b" / filename)

    records, unclassified = migration.build_migration_plan(tmp_path)

    assert unclassified == []
    assert len(records) == 2
    destination_names = {record.destination.name for record in records}
    assert destination_names == {
        "hx_10g_v3_0km_220km_phase_diff.jpeg",
        "hx_10g_v3_0km_220km_phase_diff_duplicate_1.jpeg",
    }


def test_build_migration_plan_marks_unclassified_files(tmp_path: Path):
    source = _touch(tmp_path / "mystery_animation.mp4")

    records, unclassified = migration.build_migration_plan(tmp_path)

    assert records == []
    assert len(unclassified) == 1
    assert unclassified[0].source == source.resolve()
    assert unclassified[0].reason == "missing product token"


def test_build_migration_plan_skips_already_organized_file(tmp_path: Path):
    filter_dir = tmp_path / "filter_1"
    filter_dir.mkdir()
    (filter_dir / "filter_parameters.txt").write_text("filtering.enabled: false\n", encoding = "utf-8")
    source = _touch(
        filter_dir
        / "simulations"
        / "nonmagneto"
        / "horizontal"
        / "10G"
        / "phase"
        / "annulus"
        / "v3"
        / "hx_10g_v3_0km_220km_phase_diff.jpeg"
    )

    records, unclassified = migration.build_migration_plan(tmp_path)

    assert unclassified == []
    assert len(records) == 1
    assert records[0].source == source.resolve()
    assert records[0].destination == source.resolve()
    assert records[0].action == "skip"


def test_apply_migration_moves_file_and_writes_filter_parameters(tmp_path: Path):
    source = _touch(
        tmp_path
        / "legacy"
        / "hx_10g_v3_0km_220km_gaussian_filtered_gauss_ck_2_wk_2_cf_1_5_wf_1_5_phase_diff.jpeg"
    )
    records, unclassified = migration.build_migration_plan(tmp_path)

    summary = migration.apply_migration(tmp_path, records, dry_run = False)

    assert unclassified == []
    assert summary["moved"] == 1
    assert not source.exists()
    assert records[0].destination.exists()
    assert (tmp_path / "filter_1" / "filter_parameters.txt").exists()
