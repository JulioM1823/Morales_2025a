#!/usr/bin/env python3
"""Profile time-distance pipeline and plotting notebook performance."""

from __future__ import annotations

import argparse
import contextlib
import copy
import cProfile
import csv
import importlib.util
import io
import json
import os
import pstats
import resource
import sys
import threading
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import nbformat
import numpy as np
from astropy.io import fits

try:
    import psutil
except ModuleNotFoundError:
    psutil = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = PROJECT_ROOT / "Code"
TESTS_DIR = CODE_DIR / "Tests"
TIME_DISTANCE_DIR = CODE_DIR / "Time-Distance"
DEFAULT_CONFIG = TIME_DISTANCE_DIR / "config.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "Data" / "Time-Distance" / "performance-audit"
TD_BATCH_NOTEBOOK = TIME_DISTANCE_DIR / "batch.ipynb"


class MemorySampler:
    """Sample process RSS during long pipeline and notebook operations."""

    def __init__(self, interval_seconds: float = 0.1):
        self.interval_seconds = float(interval_seconds)
        self.peak_rss = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = psutil.Process() if psutil is not None else None

    def __enter__(self) -> "MemorySampler":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        self.peak_rss = self.current_rss()
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.peak_rss = max(self.peak_rss, self.current_rss())

    def current_rss(self) -> int:
        if self._process is not None:
            return int(self._process.memory_info().rss)

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return int(usage)
        return int(usage * 1024)

    def _sample(self) -> None:
        while not self._stop.is_set():
            self.peak_rss = max(self.peak_rss, self.current_rss())
            time.sleep(self.interval_seconds)


def load_local_module(module_name: str, file_path: str | Path) -> ModuleType:
    file_path = Path(file_path).expanduser().resolve()
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import {module_name} from {file_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_time_distance_module() -> ModuleType:
    return load_local_module("time_distance_performance_audit", TIME_DISTANCE_DIR / "pipeline.py")


def load_td_batch_helpers(notebook_path: str | Path = TD_BATCH_NOTEBOOK) -> ModuleType:
    notebook_path = Path(notebook_path).expanduser().resolve()
    notebook = nbformat.read(notebook_path, as_version=4)
    module = ModuleType("td_batch_performance_audit")
    namespace = module.__dict__

    helper_cells = []
    for cell in notebook.cells:
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if (
            "def load_mode_base_config(" in source and "def execute_batch_runs(" in source
        ) or "def infer_shared_single_cube_height_grid_km(" in source:
            helper_cells.append(source)

    if not helper_cells:
        raise RuntimeError(f"Could not find td_batch helper cells in {notebook_path}.")

    for source in helper_cells:
        exec(compile(source, str(notebook_path), "exec"), namespace)

    return module


def load_base_config(time_distance_module: ModuleType, config_file: str | Path, source_type: str) -> dict[str, Any]:
    config_file = Path(config_file).expanduser().resolve()
    config_module = time_distance_module.load_config_module(config_file)
    normalized_source_type = time_distance_module._normalize_source_type(source_type)
    dispersion_curves = copy.deepcopy(getattr(config_module, "dispersion_curve_inputs", None))

    if normalized_source_type == "paired_cubes":
        return config_module.get_config(
            source_type=normalized_source_type,
            dispersion_curves=dispersion_curves,
            **copy.deepcopy(getattr(config_module, "paired_cubes_inputs", {})),
        )

    if normalized_source_type == "single_cube":
        return config_module.get_config(
            source_type=normalized_source_type,
            dispersion_curves=dispersion_curves,
            **copy.deepcopy(getattr(config_module, "single_cube_inputs", {})),
        )

    raise ValueError("source_type must be 'paired_cubes' or 'single_cube'.")


def selected_source_types(source_type: str) -> list[str]:
    if source_type == "both":
        return ["single_cube", "paired_cubes"]
    return [source_type]


def audit_run_config(base_config: dict[str, Any], run_dir: Path, *, show_plots: bool = False) -> dict[str, Any]:
    run_config = copy.deepcopy(base_config)
    run_config.setdefault("paths", {})
    run_config["paths"]["data_output_dir"] = str(run_dir / "data")
    run_config["paths"]["figure_dir"] = str(run_dir / "figures")
    run_config["paths"]["animation_dir"] = str(run_dir / "figures" / "Animations")
    run_config["profile_enabled"] = True
    run_config["profile_output_dir"] = str(run_dir / "profiles")
    run_config["show_plots"] = bool(show_plots)
    run_config["close_figures_after_save"] = True
    return run_config


def build_scenario_run_configs(
    base_config: dict[str, Any],
    *,
    scenario: str,
    source_type: str,
    run_dir: Path,
    batch_helpers: ModuleType | None = None,
    time_distance_module: ModuleType | None = None,
    config_file: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic audit configs without mutating configured research outputs."""

    if scenario not in {"smoke", "representative", "full"}:
        raise ValueError("scenario must be 'smoke', 'representative', or 'full'.")

    if scenario == "smoke" or batch_helpers is None or time_distance_module is None:
        return [audit_run_config(base_config, run_dir / f"{scenario}_{source_type}" / "case_001")]

    if source_type == "single_cube":
        batch_settings = batch_helpers.get_batch_mode_settings(config_file, "single_netcdf_cube")
        batch_inputs = batch_helpers.resolve_single_cube_batch_inputs(base_config, batch_settings)
        plan = batch_helpers.build_single_cube_batch_plan(
            base_config,
            time_distance_module,
            batch_inputs["cube_paths"],
            observable=batch_inputs["observable"],
            model_atmosphere_path=batch_inputs["model_atmosphere_path"],
        )
    elif source_type == "paired_cubes":
        batch_settings = batch_helpers.get_batch_mode_settings(config_file, "paired_cubes")
        plan = batch_helpers.build_configured_paired_cubes_batch_plan(
            base_config,
            time_distance_module,
            batch_settings,
        )
    else:
        raise ValueError("source_type must be 'paired_cubes' or 'single_cube'.")

    run_configs = list(plan.get("run_configs", []))
    if len(run_configs) == 0:
        return [audit_run_config(base_config, run_dir / f"{scenario}_{source_type}" / "case_001")]

    if scenario == "representative":
        selected_indexes = sorted({0, min(2, len(run_configs) - 1), len(run_configs) - 1})
        run_configs = [run_configs[index] for index in selected_indexes]

    return [
        audit_run_config(run_config, run_dir / f"{scenario}_{source_type}" / f"case_{index:03d}")
        for index, run_config in enumerate(run_configs, start=1)
    ]


def wrap_pipeline_stages(pipeline: Any) -> tuple[dict[str, float], dict[str, int]]:
    stage_times: dict[str, float] = {}
    stage_call_counts: dict[str, int] = {}

    def wrap(stage_name: str) -> None:
        original = getattr(pipeline, stage_name)

        def timed_stage(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                stage_times[stage_name] = stage_times.get(stage_name, 0.0) + (
                    time.perf_counter() - start_time
                )
                stage_call_counts[stage_name] = stage_call_counts.get(stage_name, 0) + 1

        setattr(pipeline, stage_name, timed_stage)

    for stage_name in [
        "load_dopplergrams",
        "compute_single_cube_magnetic_orientation_metadata",
        "compute_komega_diagram",
        "compute_coherence_diagram",
        "xcorrj",
        "save_time_distance",
        "run",
    ]:
        if hasattr(pipeline, stage_name):
            wrap(stage_name)

    return stage_times, stage_call_counts


def summarize_cprofile(profile: cProfile.Profile, output_prefix: Path) -> dict[str, str]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    profile_file = output_prefix.with_suffix(".prof")
    text_file = output_prefix.with_suffix(".txt")
    profile.dump_stats(profile_file)

    buffer = io.StringIO()
    stats = pstats.Stats(profile, stream=buffer).strip_dirs().sort_stats("cumtime")
    stats.print_stats(80)
    text_file.write_text(buffer.getvalue(), encoding="utf-8")

    return {"profile_file": str(profile_file), "profile_text_file": str(text_file)}


def fits_summary(file_path: str | Path) -> dict[str, Any]:
    file_path = Path(file_path).expanduser().resolve()
    if not file_path.exists():
        return {"path": str(file_path), "exists": False}

    values = np.asarray(fits.getdata(file_path), dtype=np.float64)
    return {
        "path": str(file_path),
        "exists": True,
        "shape": [int(axis) for axis in values.shape],
        "min": float(np.nanmin(values)),
        "max": float(np.nanmax(values)),
        "mean": float(np.nanmean(values)),
        "std": float(np.nanstd(values)),
    }


def compare_fits(reference_file: str | Path, candidate_file: str | Path) -> dict[str, Any]:
    reference_file = Path(reference_file).expanduser().resolve()
    candidate_file = Path(candidate_file).expanduser().resolve()
    reference = np.asarray(fits.getdata(reference_file), dtype=np.float64)
    candidate = np.asarray(fits.getdata(candidate_file), dtype=np.float64)

    if reference.shape != candidate.shape:
        return {
            "reference_path": str(reference_file),
            "candidate_path": str(candidate_file),
            "shape_match": False,
            "reference_shape": [int(axis) for axis in reference.shape],
            "candidate_shape": [int(axis) for axis in candidate.shape],
        }

    difference = candidate - reference
    return {
        "reference_path": str(reference_file),
        "candidate_path": str(candidate_file),
        "shape_match": True,
        "exact_equal": bool(np.array_equal(reference, candidate)),
        "allclose_atol_1e_6_rtol_1e_6": bool(
            np.allclose(reference, candidate, atol=1.0e-6, rtol=1.0e-6, equal_nan=True)
        ),
        "max_abs_diff": float(np.nanmax(np.abs(difference))),
        "mean_abs_diff": float(np.nanmean(np.abs(difference))),
        "rms_diff": float(np.sqrt(np.nanmean(difference**2))),
    }


def run_pipeline_profile(
    time_distance_module: ModuleType,
    config_file: Path,
    run_config: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _, runtime_config, pipeline = time_distance_module.build_pipeline(
        config_file=config_file,
        config_override=copy.deepcopy(run_config),
    )
    stage_times, stage_call_counts = wrap_pipeline_stages(pipeline)

    profile = cProfile.Profile()
    tracemalloc.start()
    with MemorySampler() as memory_sampler:
        start_time = time.perf_counter()
        profile.enable()
        try:
            results = pipeline.run()
            status = "completed"
            error = ""
        except Exception as exc:
            results = {}
            status = "failed"
            error = f"{exc.__class__.__name__}: {exc}"
        finally:
            profile.disable()
            wall_seconds = time.perf_counter() - start_time
            current_bytes, peak_traced_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    profile_files = summarize_cprofile(profile, output_dir / "pipeline_cprofile")
    output_keys = ["outfile", "phase_outfile", "komega_outfile", "coherence_outfile"]
    outputs = {
        key: fits_summary(results[key])
        for key in output_keys
        if isinstance(results, dict) and key in results
    }

    summary = {
        "status": status,
        "error": error,
        "wall_seconds": float(wall_seconds),
        "peak_rss_bytes": int(memory_sampler.peak_rss),
        "tracemalloc_current_bytes": int(current_bytes),
        "tracemalloc_peak_bytes": int(peak_traced_bytes),
        "component_times_seconds": {key: float(value) for key, value in stage_times.items()},
        "component_call_counts": {key: int(value) for key, value in stage_call_counts.items()},
        "xcorrj_diagnostics": copy.deepcopy(getattr(pipeline, "xcorrj_diagnostics", None)),
        "runtime_config": runtime_config,
        "outputs": outputs,
        **profile_files,
    }

    summary_file = output_dir / "pipeline_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["summary_file"] = str(summary_file)
    return summary


def run_analysis_profile(
    batch_helpers: ModuleType,
    runtime_config: dict[str, Any],
    output_dir: Path,
    *,
    analysis_backend: str,
    config_file: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_index": 1,
        "total_runs": 1,
        "label": Path(runtime_config["data"]["outfile"]).stem,
        "source_type": runtime_config["data"]["source_type"],
        "runtime_config": runtime_config,
        "status": "completed",
    }

    profile = cProfile.Profile()
    tracemalloc.start()
    with MemorySampler() as memory_sampler:
        start_time = time.perf_counter()
        profile.enable()
        try:
            records = batch_helpers.execute_td_analysis_for_batch(
                [record],
                analysis_backend=analysis_backend,
                output_dir=output_dir / "executed_notebooks",
                profile_enabled=True,
                profile_output_dir=output_dir / "profiles",
                use_config=True,
                timeout=3600,
                continue_on_error=True,
                verbose=False,
            )
            status = "completed" if all(item.get("status") == "completed" for item in records) else "failed"
            error = ""
        except Exception as exc:
            records = []
            status = "failed"
            error = f"{exc.__class__.__name__}: {exc}"
        finally:
            profile.disable()
            wall_seconds = time.perf_counter() - start_time
            current_bytes, peak_traced_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    profile_files = summarize_cprofile(profile, output_dir / "analysis_cprofile")
    summary = {
        "status": status,
        "error": error,
        "analysis_backend": analysis_backend,
        "config_file": str(config_file),
        "wall_seconds": float(wall_seconds),
        "peak_rss_bytes": int(memory_sampler.peak_rss),
        "tracemalloc_current_bytes": int(current_bytes),
        "tracemalloc_peak_bytes": int(peak_traced_bytes),
        "analysis_records": records,
        **profile_files,
    }

    summary_file = output_dir / "analysis_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["summary_file"] = str(summary_file)
    return summary


def write_matrix_csv(records: Iterable[dict[str, Any]], output_file: Path) -> None:
    rows = []
    for record in records:
        pipeline = record.get("pipeline", {})
        analysis = record.get("analysis", {})
        rows.append(
            {
                "source_type": record.get("source_type", ""),
                "scenario": record.get("scenario", ""),
                "analysis_backend": analysis.get("analysis_backend", ""),
                "pipeline_status": pipeline.get("status", ""),
                "analysis_status": analysis.get("status", ""),
                "pipeline_wall_seconds": pipeline.get("wall_seconds", ""),
                "analysis_wall_seconds": analysis.get("wall_seconds", ""),
                "pipeline_peak_rss_bytes": pipeline.get("peak_rss_bytes", ""),
                "analysis_peak_rss_bytes": analysis.get("peak_rss_bytes", ""),
                "pipeline_summary_file": pipeline.get("summary_file", ""),
                "analysis_summary_file": analysis.get("summary_file", ""),
            }
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile time-distance notebooks and shared pipeline code.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--scenario", choices=["smoke", "representative", "full"], default="smoke")
    parser.add_argument("--source-type", choices=["paired_cubes", "single_cube", "both"], default="both")
    parser.add_argument("--label", default=None)
    parser.add_argument("--analysis-backend", choices=["notebook", "in_process"], default="in_process")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--show-plots", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    label = args.label or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = Path(args.output_root).expanduser().resolve() / label
    output_root.mkdir(parents=True, exist_ok=True)

    mpl_config_dir = output_root / "mplconfig"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))
    os.environ.setdefault("MPLBACKEND", "Agg")

    config_file = Path(args.config).expanduser().resolve()
    time_distance_module = load_time_distance_module()
    batch_helpers = load_td_batch_helpers()
    matrix_records = []

    for source_type in selected_source_types(args.source_type):
        base_config = load_base_config(time_distance_module, config_file, source_type)
        run_configs = build_scenario_run_configs(
            base_config,
            scenario=args.scenario,
            source_type=source_type,
            run_dir=output_root,
            batch_helpers=batch_helpers,
            time_distance_module=time_distance_module,
            config_file=config_file,
        )

        for run_index, run_config in enumerate(run_configs, start=1):
            run_dir = output_root / source_type / f"run_{run_index:03d}"
            pipeline_summary = run_pipeline_profile(
                time_distance_module,
                config_file,
                run_config,
                run_dir / "pipeline",
            )

            runtime_config = pipeline_summary.get("runtime_config", {})
            if pipeline_summary.get("status") == "completed":
                analysis_summary = run_analysis_profile(
                    batch_helpers,
                    runtime_config,
                    run_dir / "analysis",
                    analysis_backend=args.analysis_backend,
                    config_file=config_file,
                )
            else:
                analysis_summary = {
                    "status": "skipped_parent_failure",
                    "analysis_backend": args.analysis_backend,
                    "summary_file": "",
                }

            matrix_records.append(
                {
                    "source_type": source_type,
                    "scenario": args.scenario,
                    "run_index": int(run_index),
                    "pipeline": pipeline_summary,
                    "analysis": analysis_summary,
                }
            )

    matrix_summary = {
        "label": label,
        "config_file": str(config_file),
        "scenario": args.scenario,
        "source_type": args.source_type,
        "analysis_backend": args.analysis_backend,
        "output_root": str(output_root),
        "runs": matrix_records,
    }
    matrix_file = output_root / "performance_audit_summary.json"
    matrix_file.write_text(json.dumps(matrix_summary, indent=2, sort_keys=True), encoding="utf-8")
    write_matrix_csv(matrix_records, output_root / "performance_audit_summary.csv")
    print(matrix_file)

    failed = [
        record
        for record in matrix_records
        if record.get("pipeline", {}).get("status") != "completed"
        or record.get("analysis", {}).get("status") not in {"completed", "skipped_parent_failure"}
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
