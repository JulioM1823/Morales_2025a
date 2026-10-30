#!/usr/bin/env python3
'''
Purpose
-------
Benchmark and validate the time-distance xcorrj skip-distance engines.

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

# Import the test dependencies and implementation modules used by these checks.
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
    '''
    Purpose
    -------
    Import the selected on-disk module under the isolated name used by the test.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    module: types.ModuleType
        Executed module exposing the implementation under test. Where present,
        register it in sys.modules before loader execution.
    '''

    # Create and execute an isolated import of the on-disk implementation module.
    spec = importlib.util.spec_from_file_location('time_distance_benchmark_runtime', TIME_DISTANCE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_base_config(time_distance_module, config_file, source_type):
    '''
    Purpose
    -------
    Load source-type-specific settings and preserve configured dispersion inputs for a
    benchmark.

    Inputs
    ------
    time_distance_module: types.ModuleType
        Dynamically loaded time-distance pipeline module.

    config_file: str or pathlib.Path
        Python configuration file used to build the runtime settings.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    Outputs
    -------
    config: dict
        Configuration for the requested dataset mode. Unsupported source modes
        raise ValueError; source overrides require a get_config() interface.
    '''

    # Load only the requested source-mode defaults before applying benchmark changes.
    if source_type in ['', None]:
        return time_distance_module.load_time_distance_config(config_file)

    config_module = time_distance_module.load_config_module(config_file)
    source_type = time_distance_module._normalize_source_type(source_type)
    dispersion_curves = copy.deepcopy(getattr(config_module, 'dispersion_curve_inputs', None))

    if not hasattr(config_module, 'get_config'):
        raise ValueError('Source-type overrides require config.py to expose get_config(...).')

    if source_type == 'paired_cubes':
        return config_module.get_config(optimized_filtering={'mode':'manual'},
            source_type = source_type,
            dispersion_curves = dispersion_curves,
            **copy.deepcopy(getattr(config_module, 'paired_cubes_inputs', {})))

    if source_type == 'single_cube':
        return config_module.get_config(optimized_filtering={'mode':'manual'},
            source_type = source_type,
            dispersion_curves = dispersion_curves,
            **copy.deepcopy(getattr(config_module, 'single_cube_inputs', {})))

    raise ValueError("source_type must be 'paired_cubes' or 'single_cube'.")


class MemorySampler:
    '''
    Purpose
    -------
    Sample process resident memory on a daemon thread during measured operations.

    Inputs
    ------
    interval_seconds: float
        Delay in seconds between process-memory samples.

    Outputs
    -------
    instance: MemorySampler
        Fixture or test-suite object providing the documented methods.
    '''

    def __init__(self, interval_seconds = 0.1):
        '''
        Purpose
        -------
        Initialize the memory sampling interval, stop event, and optional process
        handle.

        Inputs
        ------
        interval_seconds: float
            Delay in seconds between process-memory samples.

        Outputs
        -------
        None
            Store sampler state; do not start the background thread yet.
        '''

        self.interval_seconds = float(interval_seconds)
        self.peak_rss = 0
        self._stop = threading.Event()
        self._thread = None
        self._process = psutil.Process() if psutil is not None else None

    def start(self):
        '''
        Purpose
        -------
        Start a daemon thread and initialize the peak resident-memory sample.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Store and start the sampler thread; the performance-audit variant
            also clears its stop event before starting.
        '''

        self.peak_rss = self.current_rss()
        self._thread = threading.Thread(target = self._sample, daemon = True)
        self._thread.start()

    def stop(self):
        '''
        Purpose
        -------
        Signal and join the sampler thread, then retain the final peak-memory
        observation.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Stop periodic sampling and update peak_rss in place.
        '''

        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.peak_rss = max(self.peak_rss, self.current_rss())

    def current_rss(self):
        '''
        Purpose
        -------
        Read process resident memory through psutil or the resource fallback.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        rss: int
            Bytes when psutil is available; otherwise the platform-native
            ru_maxrss value, which this benchmark does not normalize.
        '''

        if self._process is not None:
            return int(self._process.memory_info().rss)
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    def _sample(self):
        '''
        Purpose
        -------
        Update the recorded peak resident memory until the stop event is set.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Mutate peak_rss on the daemon thread at interval_seconds spacing.
        '''

        while not self._stop.is_set():
            self.peak_rss = max(self.peak_rss, self.current_rss())
            time.sleep(self.interval_seconds)


def wrap_pipeline_stages(pipeline):
    '''
    Purpose
    -------
    Instrument pipeline methods with elapsed-time and call-count accumulators.

    Inputs
    ------
    pipeline: object
        Pipeline instance whose methods are wrapped with timing counters.

    Outputs
    -------
    stage_times, stage_call_counts: tuple of dict
        Mutable timing totals in seconds and invocation counts. Replace
        selected pipeline methods in place with delegating wrappers.
    '''

    # Keep timing/count dictionaries in closures while replacing only selected methods.
    stage_times = {}
    stage_call_counts = {}

    def wrap(stage_name):
        '''
        Purpose
        -------
        Wrap the selected pipeline method with the enclosing timing/counting closure.

        Inputs
        ------
        stage_name: str
            Pipeline method name captured by the timing wrapper.

        Outputs
        -------
        None
            Replace the named method on the enclosing pipeline instance.
        '''

        original = getattr(pipeline, stage_name)

        def timed_stage(*args, **kwargs):
            '''
            Purpose
            -------
            Call the original pipeline method and record elapsed time even when it
            raises.

            Inputs
            ------
            *args: tuple
                Positional arguments accepted by the wrapper, or parsed benchmark
                options.

            **kwargs: dict
                Keyword arguments accepted by the substituted or wrapped callable.

            Outputs
            -------
            result: object
                Unchanged original method result. Update timing/count dictionaries
                in finally and propagate the original exception.
            '''

            start_time = time.perf_counter()
            # Delegate unchanged results/errors while collecting stage timing in
            # finally.
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
    '''
    Purpose
    -------
    Hash the complete file in one-megabyte blocks.

    Inputs
    ------
    file_path: str or pathlib.Path
        Path of the source, module, or numerical product being inspected.

    Outputs
    -------
    digest: str
        Hexadecimal SHA-256 digest of the input bytes.
    '''

    # Hash incrementally so the input file is not loaded into one large byte string.
    digest = hashlib.sha256()
    with open(file_path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def summarize_fits(file_path):
    '''
    Purpose
    -------
    Read a FITS product and report its shape, numerical statistics, and byte digest.

    Inputs
    ------
    file_path: str or pathlib.Path
        Path of the source, module, or numerical product being inspected.

    Outputs
    -------
    summary: dict
        Path/existence metadata and, for an existing product, shape, dtype,
        finite-aware statistics, sum, and SHA-256 digest.
    '''

    # Read the actual FITS array and hash the saved bytes independently of its
    # statistics.
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
    '''
    Purpose
    -------
    Find the matching reference FITS product by basename in the optional reference tree.

    Inputs
    ------
    reference_dir: str or pathlib.Path or None
        Optional directory searched for a matching reference product.

    candidate_name: str
        Product basename used for reference-file lookup.

    Outputs
    -------
    path: pathlib.Path or None
        Matching reference file, or None when no reference directory/match is available.
    '''

    # Prefer the direct reference path before searching the reference directory tree.
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
    '''
    Purpose
    -------
    Compare candidate and reference FITS arrays using shape, exact, and tolerance
    checks.

    Inputs
    ------
    reference_file: str, pathlib.Path, or None
        Optional reference FITS product; None disables this comparison.

    candidate_file: str or pathlib.Path
        New FITS product being checked against the reference.

    Outputs
    -------
    comparison: dict or None
        Shape agreement and numerical difference statistics, or None only when
        reference_file is None. Unreadable supplied paths propagate errors.
        Tolerance checks use atol=rtol=1e-6.
    '''

    # Require matching array shapes before computing exact and tolerance-based
    # differences.
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
    '''
    Purpose
    -------
    Copy benchmark defaults and apply engine, worker, output, and command-line
    overrides.

    Inputs
    ------
    base_config: dict
        Base configuration copied before applying benchmark-specific settings.

    run_dir: pathlib.Path
        Directory assigned to this benchmark run.

    engine: str
        Cross-correlation implementation selected for the benchmark.

    workers: int
        Number of workers configured for the benchmark run.

    args: tuple or argparse.Namespace
        Positional arguments accepted by the wrapper, or parsed benchmark options.

    Outputs
    -------
    config: dict
        Runtime configuration for one measured pipeline run.
    '''

    # Copy the base configuration so benchmark engine and output overrides stay local.
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
    '''
    Purpose
    -------
    Execute and time one configured correlation engine while recording memory and
    product comparisons.

    Inputs
    ------
    time_distance_module: types.ModuleType
        Dynamically loaded time-distance pipeline module.

    config_file: str or pathlib.Path
        Python configuration file used to build the runtime settings.

    base_config: dict
        Base configuration copied before applying benchmark-specific settings.

    output_root: pathlib.Path
        Root beneath which benchmark runs are written.

    engine: str
        Cross-correlation implementation selected for the benchmark.

    workers: int
        Number of workers configured for the benchmark run.

    args: tuple or argparse.Namespace
        Positional arguments accepted by the wrapper, or parsed benchmark options.

    Outputs
    -------
    summary: dict
        Run settings, elapsed/stage timings, memory sample, product metadata,
        and reference comparisons; write the run summary beneath output_root.
    '''

    # Collect elapsed time, memory samples, and product/reference checks for one engine.
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
    '''
    Purpose
    -------
    Parse the benchmark or performance-audit command-line options.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    arguments: argparse.Namespace
        Parsed options; argparse reports malformed or unsupported arguments.
    '''

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
    '''
    Purpose
    -------
    Execute the configured benchmark and publish its measured timing/results summary.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    None
        Run the benchmark workload and print or write its configured summaries.
    '''

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
