#!/usr/bin/env python3
"""Benchmark and validate the time-distance xcorrj skip-distance engines."""

import argparse
import copy
import hashlib
import importlib.util
import json
import resource
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from astropy.io import fits

try:
    import psutil
except ModuleNotFoundError:
    psutil = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = PROJECT_ROOT / 'Code'
TESTS_DIR = CODE_DIR / 'Tests'
TIME_DISTANCE_DIR = CODE_DIR / 'Time-Distance'
TIME_DISTANCE_FILE = TIME_DISTANCE_DIR / 'pipeline.py'


def load_time_distance_module():
    spec = importlib.util.spec_from_file_location('time_distance_benchmark_runtime', TIME_DISTANCE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_base_config(time_distance_module, config_file, source_type):
    if source_type in ['', None]:
        return time_distance_module.load_time_distance_config(config_file)

    config_module = time_distance_module.load_config_module(config_file)
    source_type = time_distance_module._normalize_source_type(source_type)
    dispersion_curves = copy.deepcopy(getattr(config_module, 'dispersion_curve_inputs', None))

    if not hasattr(config_module, 'get_config'):
        raise ValueError('Source-type overrides require config.py to expose get_config(...).')

    if source_type == 'paired_cubes':
        return config_module.get_config(
            source_type = source_type,
            dispersion_curves = dispersion_curves,
            **copy.deepcopy(getattr(config_module, 'paired_cubes_inputs', {})))

    if source_type == 'single_cube':
        return config_module.get_config(
            source_type = source_type,
            dispersion_curves = dispersion_curves,
            **copy.deepcopy(getattr(config_module, 'single_cube_inputs', {})))

    raise ValueError("source_type must be 'paired_cubes' or 'single_cube'.")


class MemorySampler:
    def __init__(self, interval_seconds = 0.1):
        self.interval_seconds = float(interval_seconds)
        self.peak_rss = 0
        self._stop = threading.Event()
        self._thread = None
        self._process = psutil.Process() if psutil is not None else None

    def start(self):
        self.peak_rss = self.current_rss()
        self._thread = threading.Thread(target = self._sample, daemon = True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.peak_rss = max(self.peak_rss, self.current_rss())

    def current_rss(self):
        if self._process is not None:
            return int(self._process.memory_info().rss)
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    def _sample(self):
        while not self._stop.is_set():
            self.peak_rss = max(self.peak_rss, self.current_rss())
            time.sleep(self.interval_seconds)


def wrap_pipeline_stages(pipeline):
    stage_times = {}
    stage_call_counts = {}

    def wrap(stage_name):
        original = getattr(pipeline, stage_name)

        def timed_stage(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                stage_times[stage_name] = stage_times.get(stage_name, 0.0) + (time.perf_counter() - start_time)
                stage_call_counts[stage_name] = stage_call_counts.get(stage_name, 0) + 1

        setattr(pipeline, stage_name, timed_stage)

    for stage_name in [
        'load_dopplergrams',
        'compute_komega_diagram',
        'compute_coherence_diagram',
        'xcorrj',
        'save_time_distance',
        'run',
    ]:
        wrap(stage_name)

    return stage_times, stage_call_counts


def sha256_file(file_path):
    digest = hashlib.sha256()
    with open(file_path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def summarize_fits(file_path):
    file_path = Path(file_path)
    if not file_path.exists():
        return {'path': str(file_path), 'exists': False}

    data = np.asarray(fits.getdata(file_path), dtype = np.float64)
    return {
        'path': str(file_path),
        'exists': True,
        'shape': [int(value) for value in data.shape],
        'dtype': str(data.dtype),
        'min': float(np.nanmin(data)),
        'max': float(np.nanmax(data)),
        'mean': float(np.nanmean(data)),
        'std': float(np.nanstd(data)),
        'sum': float(np.nansum(data)),
        'sha256': sha256_file(file_path)}


def locate_reference_file(reference_dir, candidate_name):
    if reference_dir in ['', None]:
        return None

    reference_dir = Path(reference_dir).expanduser().resolve()
    candidates = [
        reference_dir / candidate_name,
        reference_dir / 'data' / candidate_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches = sorted(reference_dir.rglob(candidate_name))
    if len(matches) > 0:
        return matches[0]

    return None


def compare_fits(reference_file, candidate_file):
    if reference_file is None:
        return None

    reference = np.asarray(fits.getdata(reference_file), dtype = np.float64)
    candidate = np.asarray(fits.getdata(candidate_file), dtype = np.float64)
    shape_match = reference.shape == candidate.shape
    if not shape_match:
        return {
            'reference_path': str(reference_file),
            'shape_match': False,
            'reference_shape': [int(value) for value in reference.shape],
            'candidate_shape': [int(value) for value in candidate.shape]}

    difference = candidate - reference
    return {
        'reference_path': str(reference_file),
        'shape_match': True,
        'exact_equal': bool(np.array_equal(candidate, reference)),
        'allclose_atol_1e_6_rtol_1e_6': bool(np.allclose(candidate, reference, atol = 1.0e-6, rtol = 1.0e-6, equal_nan = True)),
        'max_abs_diff': float(np.nanmax(np.abs(difference))),
        'mean_abs_diff': float(np.nanmean(np.abs(difference))),
        'rms_diff': float(np.sqrt(np.nanmean(difference**2)))}


def build_run_config(base_config, run_dir, engine, workers, args):
    run_config = copy.deepcopy(base_config)
    run_config.setdefault('paths', {})
    run_config['paths']['data_output_dir'] = str(run_dir / 'data')
    run_config['paths']['figure_dir'] = str(run_dir / 'figures')
    run_config.setdefault('time_distance', {})
    run_config['time_distance']['xcorrj_engine'] = engine
    run_config['time_distance']['nworkers'] = int(workers)
    run_config['time_distance']['xcorrj_parallel'] = not args.disable_parallel

    if args.chunk_centers not in ['', None]:
        run_config['time_distance']['xcorrj_chunk_centers'] = args.chunk_centers
    if args.chunk_memory_mb is not None:
        run_config['time_distance']['xcorrj_chunk_memory_mb'] = float(args.chunk_memory_mb)
    if args.maxdist_mm is not None:
        run_config['time_distance']['maxdist_Mm'] = float(args.maxdist_mm)

    return run_config


def run_one_benchmark(time_distance_module, config_file, base_config, output_root, engine, workers, args):
    source_type = base_config.get('data', {}).get('source_type', 'unknown')
    run_label = f'{source_type}_{engine}_workers_{workers}'
    run_dir = output_root / run_label
    run_dir.mkdir(parents = True, exist_ok = True)
    run_config = build_run_config(base_config, run_dir, engine, workers, args)

    _, runtime_config, pipeline = time_distance_module.build_pipeline(
        config_file = config_file,
        config_override = run_config)
    stage_times, stage_call_counts = wrap_pipeline_stages(pipeline)
    memory_sampler = MemorySampler()
    memory_sampler.start()
    start_time = time.perf_counter()
    results = pipeline.run()
    wall_seconds = time.perf_counter() - start_time
    memory_sampler.stop()

    output_keys = ['outfile', 'phase_outfile', 'komega_outfile', 'coherence_outfile']
    output_summaries = {}
    comparisons = {}
    for output_key in output_keys:
        candidate_path = Path(results[output_key])
        output_summaries[output_key] = summarize_fits(candidate_path)
        reference_file = locate_reference_file(args.reference_data_dir, candidate_path.name)
        if reference_file is not None:
            comparisons[output_key] = compare_fits(reference_file, candidate_path)

    summary = {
        'label': run_label,
        'config_file': str(config_file),
        'source_type': str(source_type),
        'engine': str(engine),
        'requested_workers': int(workers),
        'wall_seconds': float(wall_seconds),
        'max_rss': int(memory_sampler.peak_rss),
        'stage_times_seconds': {key: float(value) for key, value in stage_times.items()},
        'stage_call_counts': {key: int(value) for key, value in stage_call_counts.items()},
        'xcorrj_diagnostics': copy.deepcopy(pipeline.xcorrj_diagnostics),
        'outputs': output_summaries,
        'comparison_to_reference': comparisons,
        'runtime_time_distance': copy.deepcopy(runtime_config.get('time_distance', {}))}

    summary_file = run_dir / 'benchmark_summary.json'
    with open(summary_file, 'w', encoding = 'utf-8') as handle:
        json.dump(summary, handle, indent = 2, sort_keys = True)

    return summary


def parse_args():
    parser = argparse.ArgumentParser(description = 'Benchmark the pipeline.py xcorrj skip-distance engines.')
    parser.add_argument('--config', default = str(TIME_DISTANCE_FILE.with_name('config.py')))
    parser.add_argument('--source-type', choices = ['paired_cubes', 'single_cube', 'single_netcdf_cube'], default = None)
    parser.add_argument('--engine', choices = ['chunked', 'legacy'], default = 'chunked')
    parser.add_argument('--workers', nargs = '+', type = int, default = [1, 2, 4, 8, 12])
    parser.add_argument('--output-root', default = str(PROJECT_ROOT / 'Data' / 'Time-Distance' / 'performance-audit'))
    parser.add_argument('--label', default = None)
    parser.add_argument('--reference-data-dir', default = None)
    parser.add_argument('--chunk-centers', default = None)
    parser.add_argument('--chunk-memory-mb', type = float, default = None)
    parser.add_argument('--maxdist-mm', type = float, default = None)
    parser.add_argument('--disable-parallel', action = 'store_true')
    return parser.parse_args()


def main():
    args = parse_args()
    time_distance_module = load_time_distance_module()
    config_file = Path(args.config).expanduser().resolve()
    label = args.label or datetime.now().strftime('%Y%m%d_%H%M%S')
    output_root = Path(args.output_root).expanduser().resolve() / label
    output_root.mkdir(parents = True, exist_ok = True)
    base_config = load_base_config(time_distance_module, config_file, args.source_type)

    summaries = []
    for workers in args.workers:
        summaries.append(run_one_benchmark(
            time_distance_module,
            config_file,
            base_config,
            output_root,
            args.engine,
            int(workers),
            args))

    summary_file = output_root / 'benchmark_matrix_summary.json'
    with open(summary_file, 'w', encoding = 'utf-8') as handle:
        json.dump({'runs': summaries}, handle, indent = 2, sort_keys = True)

    print(summary_file)


if __name__ == '__main__':
    main()
