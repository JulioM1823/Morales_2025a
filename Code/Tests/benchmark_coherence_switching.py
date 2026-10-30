'''
Purpose
-------
Measure complete Python model-switch callbacks at the native interactive grid.

Run with the Vesa Python environment from the repository root. Optional
--baseline-dir loads a saved pre-change copy of the affected modules. Separate
processes keep solver caches independent. Dataset I/O, WebSocket transport and
browser paint are excluded; first-use times include the exact native solve.

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
import cProfile
import json
from pathlib import Path
import pstats
import sys
import time
from types import SimpleNamespace

import numpy as np
from bokeh.document import Document


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

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('/tmp/morales-switch-benchmark'))
    parser.add_argument('--cycles', type=int, default=3)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Time-Distance'))
    if args.baseline_dir is not None:
        sys.path.insert(0, str(args.baseline_dir.resolve()))
    import integrated_komega_explorer as integrated
    from gaussian_filter_explorer import PreviewGeometry, compute_filter_result
    from spectral_coherence import estimate_coherence, data_key

    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = integrated.build_document(Document(), product_roots=[], raw_roots=[],
        schedule_initial=False, registry_file=args.output_dir / 'registry.json')
    geometry = PreviewGeometry(32, 64, 30., .16, 'benchmark')
    cube = np.random.default_rng(921).normal(size=(64, 32, 32))
    cube.setflags(write=False)
    data = SimpleNamespace(observation=SimpleNamespace(id='benchmark', label='benchmark'),
        values=np.zeros((16, 32)), geometry=geometry, ny=32, metadata={},
        dopplergrams=(cube, cube), analysis_config=dict(
            data=dict(source_type='single_cube', h1=0, h2=1),
            time_distance=dict(dt=30., p_dx_Mm=.16), filtering={}))
    app.primary.data = data
    app.primary.selected_id = 'benchmark'
    app.primary.catalog['benchmark'] = data.observation
    app.primary.filter_result = compute_filter_result(app.primary.filter.geometry,
        **app.primary.filter._current_parameters())
    controls = app.model_workspace.coherence
    coherence = estimate_coherence(cube, cube, 30., .16)
    coherence.metadata['dataset_id'] = 'benchmark'
    controls.key = data_key(data)
    controls._cache[controls.key] = coherence

    cold, solver, arrays = {}, {}, {}
    for model in app.model_workspace.models:
        model.resolution_select.value = 'interactive'
        start = time.perf_counter()
        app.model_select.value = model.definition.key
        model._perform_recompute()
        cold[model.definition.key] = (time.perf_counter() - start) * 1000
        assert model.last_result is not None, model.status.text
        assert (len(model.last_result.kh_mm_inv), len(model.last_result.nu_mhz)) == tuple(
            app.model_workspace.vesa.RESOLUTION_OPTIONS['interactive'])
        solver[model.definition.key] = model.last_result.elapsed_seconds * 1000
        for field in ('phase_deg', 'kz_real', 'kz_imag'):
            arrays[model.definition.key + '_' + field] = getattr(model.last_result, field)

    modes = {}
    for weighted in (False, True):
        controls.apply.active = weighted
        times = []
        profiler = cProfile.Profile()
        if args.profile:
            profiler.enable()
        for _ in range(args.cycles):
            for model in app.model_workspace.models:
                start = time.perf_counter()
                app.model_select.value = model.definition.key
                times.append((time.perf_counter() - start) * 1000)
        profiler.disable()
        modes['weighted' if weighted else 'unweighted'] = dict(
            median_ms=float(np.median(times)), p95_ms=float(np.percentile(times, 95)),
            max_ms=max(times), switches=len(times))
        if args.profile:
            pstats.Stats(profiler).sort_stats('cumtime').print_stats(16)

    label = 'before' if args.baseline_dir is not None else 'after'
    np.savez(args.output_dir / f'arrays-{label}.npz', **arrays)
    output = dict(cold_ms=cold, solver_ms=solver, warm=modes,
        resolution=app.model_workspace.vesa.RESOLUTION_OPTIONS['interactive'])
    (args.output_dir / f'{label}.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
