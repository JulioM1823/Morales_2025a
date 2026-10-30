'''
Purpose
-------
Scientific paths, persistent products, Bokeh state and Gaussian handoff.

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
from pathlib import Path
import copy
import sys
import os
from unittest.mock import patch
from concurrent.futures import Future

import numpy as np
import pytest
from astropy.io import fits
from bokeh.document import Document

MODULE_DIR = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(MODULE_DIR))
import magnetogram_workflow as workflow
import magnetogram_explorer as ui
import integrated_komega_explorer as integrated
import komega_explorer
from observation_datasets import load_observation, reproducibility_metadata
from observation_filter_registry import read_registry, store_parameters, load_filter_parameters, RegistryError
from processing_results import ResultError, ResultStore, result_key, result_observation, fingerprint
import processing_results


@pytest.fixture
def observational(tmp_path):
    '''
    Purpose
    -------
    Create paired observational velocity FITS cubes and an aligned synthetic
    magnetogram.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    fixture: tuple
        DopplerDataset, velocity cube, and magnetic reference values. Write
        source FITS files beneath tmp_path.
    '''

    # Write reproducible velocity pairs and an aligned field with a nonfinite pixel.
    folder = tmp_path/'06May2019'
    folder.mkdir()
    rng = np.random.default_rng(52)
    cube = rng.normal(size=(24, 8, 8))
    v1 = folder/'06May2019.ibis.to.hmi.vel.fe5434.fits'
    v2 = folder/'06May2019.ibis.to.hmi.vel.fe7090.fits'
    mag = folder/'06May2019.HMImag.aligned.fits'
    magnetic = np.broadcast_to(np.arange(8.)[None, None, :], cube.shape).copy()
    magnetic[:, 0, 0] = np.nan
    fits.writeto(v1, cube)
    fits.writeto(v2, np.roll(cube, 1, axis=0) + rng.normal(0, .1, cube.shape))
    fits.writeto(mag, magnetic * 10.)
    return workflow.DopplerDataset('fixture-observation', 'Observation fixture', 'paired_cubes',
        (v1, v2), dict(dt=11.88, p_dx_Mm=.43, delta_z_km=100.)), cube, magnetic


@pytest.fixture
def simulation(tmp_path):
    '''
    Purpose
    -------
    Create a height-dependent simulation cube and magnetic field with explicit native
    metadata.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    fixture: tuple
        DopplerDataset, velocity cube, and magnetic reference array; write the
        netCDF fixture beneath tmp_path.
    '''

    # Encode height-dependent magnetic structure in a time-dependent netCDF fixture.
    nc = pytest.importorskip('netCDF4')
    path = tmp_path/'simulation_hx_10G.nc'
    rng = np.random.default_rng(81)
    cube = rng.normal(size=(24, 3, 8, 8))
    magnetic = np.zeros_like(cube)
    magnetic[:, 0] = np.arange(8.)[None, None, :]
    magnetic[:, 1] = 9.
    magnetic[:, 2] = np.arange(8.)[::-1][None, None, :]
    with nc.Dataset(path, 'w') as f:
        for name, count, step, units in [('time', 24, 30., 's'), ('xc3', 3, 100., 'km'),
                                         ('xc2', 8, .16, 'Mm'), ('xc1', 8, .16, 'Mm')]:
            f.createDimension(name, count)
            variable = f.createVariable(name, 'f8', (name,))
            variable[:] = np.arange(count)*step
            variable.units = units
        for name, array in [('v3', cube), ('bb3', magnetic)]:
            variable = f.createVariable(name, 'f8', ('xc2', 'time', 'xc1', 'xc3'))
            variable[:] = array.transpose(2, 0, 3, 1)
    return workflow.DopplerDataset('fixture-simulation', 'Simulation fixture', 'single_cube', (path,),
        dict(observable='v3', h1=0, h2=2)), cube, magnetic


def parameters(source_type, **changes):
    '''
    Purpose
    -------
    Copy default workflow parameters and apply the supplied test overrides.

    Inputs
    ------
    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    **changes: dict
        Overrides applied to the baseline parameter or processing configuration.

    Outputs
    -------
    parameters: dict
        Per-case processing settings for the selected source type.
    '''

    # Copy source-mode defaults before applying per-case overrides.
    values = dict(selection='magnetic', threshold_G=3., fill_value=0.,
                  observable='', mode='dataset' if source_type == 'paired_cubes' else 'bottom')
    values.update(changes)
    return values


def process(dataset, root, **changes):
    '''
    Purpose
    -------
    Prepare a synthetic Doppler dataset and calculate the requested masked/filter
    result.

    Inputs
    ------
    dataset: object
        Synthetic DopplerDataset passed to the processing workflow.

    root: pathlib.Path
        Root directory containing the inputs, outputs, or cache under test.

    **changes: dict
        Overrides applied to the baseline parameter or processing configuration.

    Outputs
    -------
    result: tuple
        Prepared dataset, runtime configuration, and computed workflow result.
        Use root for the workflow cache.
    '''

    # Prepare the selected dataset before requesting its cache-backed calculation.
    values = parameters(dataset.source_type, **changes)
    prepared, config = workflow.prepare_dataset(dataset, values, cache_root=root)
    return prepared, config, workflow.compute_result(prepared, config, values, cache_root=root)


def test_observation_conversion_shared_mask_and_native_phase(observational, tmp_path):
    '''
    Purpose
    -------
    Verify observation conversion shared mask and native phase.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, cube, magnetic = observational
    prepared, config, result = process(dataset, tmp_path/'cache')
    np.testing.assert_allclose(prepared.arrays['original_v1'], cube)
    np.testing.assert_allclose(prepared.arrays['magnetogram_v1'], magnetic)
    np.testing.assert_allclose(prepared.arrays['magnetogram_v2'], magnetic)
    expected_mask = np.abs(magnetic) <= 3.
    expected = cube.copy()
    expected[expected_mask] = 0.
    np.testing.assert_array_equal(result.arrays['dopplergram_v1'], expected)
    np.testing.assert_array_equal(result.arrays['removed_mask_v1'], expected_mask)
    # NaN magnetic pixels retain the pipeline's comparison behavior (not an invented mask).
    assert not result.arrays['removed_mask_v1'][0, 0, 0]
    expected_phase, kh, nu, metadata = workflow.pipeline.TimeDistance(config).compute_komega_diagram(
        result.arrays['dopplergram_v1'], result.arrays['dopplergram_v2'])
    np.testing.assert_allclose(result.arrays['komega'], expected_phase)
    np.testing.assert_array_equal(result.arrays['kh'], kh)
    np.testing.assert_array_equal(result.arrays['nu'], nu)
    assert result.manifest['metadata']['komega']['phase_delay_seconds'] == metadata['phase_delay_seconds']
    assert metadata['phase_delay_seconds'] != 0.


def test_simulation_bottom_and_per_height_pair_are_distinct(simulation, tmp_path):
    '''
    Purpose
    -------
    Verify simulation bottom and per height pair are distinct.

    Inputs
    ------
    simulation: tuple
        Synthetic simulation dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, cube, magnetic = simulation
    prepared, config, bottom = process(dataset, tmp_path/'cache')
    np.testing.assert_array_equal(prepared.arrays['original_v1'], cube[:, 0])
    np.testing.assert_array_equal(prepared.arrays['original_v2'], cube[:, 2])
    np.testing.assert_array_equal(prepared.arrays['magnetogram_v1'], magnetic[:, 0])
    np.testing.assert_array_equal(prepared.arrays['magnetogram_v2'], magnetic[:, 0])
    assert bottom.manifest['metadata']['komega']['phase_delay_seconds'] == 0.
    pair_prepared, _, pair = process(dataset, tmp_path/'cache', mode='per_height_pair')
    np.testing.assert_array_equal(pair_prepared.arrays['magnetogram_v2'], magnetic[:, 2])
    assert not np.array_equal(pair.arrays['removed_mask_v1'], pair.arrays['removed_mask_v2'])
    assert pair.id != bottom.id
    assert not np.array_equal(pair.arrays['komega'], bottom.arrays['komega'])
    assert config['time_distance']['dt'] == 30.
    assert config['time_distance']['p_dx_Mm'] == .16


def test_cache_hits_misses_and_parameter_invalidation(observational, tmp_path):
    '''
    Purpose
    -------
    Verify cache hits misses and parameter invalidation.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    root = tmp_path/'cache'
    prepared, config, first = process(dataset, root)
    with (patch.object(workflow.filter_class(), 'load_dopplergrams', side_effect=AssertionError('Reload')),
          patch.object(workflow.pipeline.TimeDistance, 'compute_komega_diagram', side_effect=AssertionError('FFT'))):
        same_prepared, _, second = process(dataset, root)
    assert first.id == second.id and prepared.id == same_prepared.id
    np.testing.assert_array_equal(first.arrays['komega'], second.arrays['komega'])
    for key, value in [('threshold_G', 4.), ('fill_value', .25), ('selection', 'nonmagnetic')]:
        revised = workflow.compute_result(prepared, config, parameters(dataset.source_type, **{key:value}), cache_root=root)
        assert revised.id != first.id
    scientific = copy.deepcopy(prepared.manifest['identity'])
    scientific['scientific']['sampling']['dt'] = 30.
    assert result_key(scientific) != prepared.id
    assert result_key({'b':2, 'a':1}) == result_key({'a':1, 'b':2})
    revised_config = copy.deepcopy(config)
    revised_config['time_distance']['dt'] = 30.
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='Sampling or phase metadata changed'):
        workflow.compute_result(prepared, revised_config, parameters(dataset.source_type), cache_root=root)


def test_source_and_corrupt_cache_invalidation(observational, tmp_path):
    '''
    Purpose
    -------
    Verify source and corrupt cache invalidation.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    root = tmp_path/'cache'
    prepared, config, result = process(dataset, root)
    path = root/result.id/'dopplergram_v1.npy'
    path.write_bytes(b'interrupted product')
    # Require the expected ResultError from this failure case.
    with pytest.raises(ResultError, match='damaged'):
        ResultStore(root).load(result.id)
    repaired = workflow.compute_result(prepared, config, parameters(dataset.source_type), cache_root=root)
    assert repaired.id == result.id
    with fits.open(dataset.files[0], mode='update') as f:
        f[0].data[0, 0, 0] += 1.
    # Require the expected ResultError from this failure case.
    with pytest.raises(ResultError, match='Source changed'):
        workflow.compute_result(prepared, config, parameters(dataset.source_type), cache_root=root)
    changed_prepared, _, changed = process(dataset, root)
    assert changed.id != result.id and changed_prepared.id != prepared.id


def test_validation_missing_alignment_and_values(observational, tmp_path):
    '''
    Purpose
    -------
    Verify validation missing alignment and values.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    mag = dataset.files[0].parent/'06May2019.HMImag.aligned.fits'
    fits.writeto(mag, np.ones((23, 8, 8)), overwrite=True)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='alignment mismatch'):
        process(dataset, tmp_path/'cache')
    mag.unlink()
    # Require the expected FileNotFoundError from this failure case.
    with pytest.raises(FileNotFoundError, match='No paired_cubes magnetogram'):
        process(dataset, tmp_path/'cache')
    for changes in ({'threshold_G':-1.}, {'threshold_G':float('nan')}, {'fill_value':float('inf')}, {'mode':'unknown'}):
        with pytest.raises(ValueError):
            workflow.validate_parameters(parameters('paired_cubes', **changes))
    assert workflow.validate_parameters(parameters('paired_cubes', fill_value='NaN'))['fill_value'] == 'NaN'


def test_handoff_and_structured_registry_preserve_other_records(observational, tmp_path):
    '''
    Purpose
    -------
    Verify handoff and structured registry preserve other records.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    prepared, config, result = process(dataset, tmp_path/'cache')
    observation = result_observation(result.id, tmp_path/'cache')
    data = load_observation(observation)
    np.testing.assert_array_equal(data.values, result.arrays['komega'])
    np.testing.assert_array_equal(data.dopplergrams[0], result.arrays['dopplergram_v1'])
    registry = tmp_path/'registry.json'
    gaussian = dict(central_k=1.5, width_k=4., central_f=3., width_f=3.)
    metadata = reproducibility_metadata(data, data.geometry)
    saved = store_parameters(observation.id, metadata, gaussian, registry)
    assert [stage['operation'] for stage in saved['processing_chain']['stages']] == ['magnetogram', 'gaussian_komega']
    assert saved['processing_chain']['stages'][0]['parameters'] == parameters('paired_cubes')
    legacy_metadata = copy.deepcopy(metadata)
    legacy_metadata['id'] = 'legacy'
    legacy_metadata['metadata'].pop('processing_chain')
    legacy = store_parameters('legacy', legacy_metadata, gaussian, registry)
    assert 'processing_chain' not in legacy
    gaussian['central_k'] = 2.
    store_parameters(observation.id, metadata, gaussian, registry)
    assert len(read_registry(registry)['observations']) == 2
    assert read_registry(registry)['observations']['legacy'] == legacy
    assert load_filter_parameters(observation.id, registry) == gaussian
    registry.write_text('{broken')
    # Require the expected RegistryError from this failure case.
    with pytest.raises(RegistryError):
        store_parameters(observation.id, metadata, gaussian, registry)
    assert registry.read_text() == '{broken'


def test_bokeh_frames_display_only_and_invalidation(observational, tmp_path):
    '''
    Purpose
    -------
    Verify Bokeh frames display only and invalidation.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, cube, _ = observational
    root = tmp_path/'cache'
    prepared, _, result = process(dataset, root)
    app = ui.build_document(Document(), datasets=[dataset], cache_root=root, schedule_initial=False)
    app.selector.value = [dataset.id]
    app.accept_result(prepared.id, result.id)
    assert app.doc.validate() is None
    assert app.original_plot.x_range is app.filtered_plot.x_range
    assert app.original_plot.renderers[0].glyph.color_mapper is app.filtered_plot.renderers[0].glyph.color_mapper
    from bokeh.models import ColorBar, Legend
    for plot in (app.original_plot, app.filtered_plot):
        bars = list(plot.select(type=ColorBar))
        assert len(bars) == 1 and bars[0].color_mapper is app.velocity_mapper
    assert app.filtered_plot.title.text == 'Filtered dopplergram slice [cm/s]'
    assert '<b>Selected:</b> Observed Magnetogram' in app.status.text
    assert '<br>Open the Gaussian tool' in app.status.text
    assert app.layout.children.index(app.parameters) < len(app.layout.children) - 1
    assert all(not list(plot.select(type=Legend)) for plot in
               (app.original_plot, app.filtered_plot, app.magnetic_plot, app.komega_plot))
    app.full_path.active = True
    assert all(label.startswith('/') for _, label in app.selector.options)
    assert app.current.id == dataset.id
    app.full_path.active = False
    generation = app._generation
    with patch.object(ui.COMPUTE_POOL, 'submit', side_effect=AssertionError('Frame causes compute')):
        app.frame.value = 2
        app.channel.value = '2'
    assert app._generation == generation
    assert app.frame.title == '' and not app.frame.show_value
    assert app.frame_label.text == f'Frame 2:  t = {app.prepared_arrays["time_seconds"][2]:g} sec'
    np.testing.assert_array_equal(app.sources['filtered'].data['image'][0], result.arrays['dopplergram_v2'][2])
    # Display proportions follow physical extents, including rectangular cubes;
    # they must not rewrite either pixel geometry or shared scientific ranges.
    geometry = app.sources['original'].data
    ratio = geometry['dw'][0] / geometry['dh'][0]
    np.testing.assert_allclose(app.plot_aspects.data['ratio'], [ratio, ratio, ratio, 1.])
    assert app.original_plot.x_range.end - app.original_plot.x_range.start == pytest.approx(geometry['dw'][0])
    assert app.original_plot.y_range.end - app.original_plot.y_range.start == pytest.approx(geometry['dh'][0])
    assert '?result=' + result.id in app.launch_state.data['url'][0]
    app.threshold.value = 4.
    assert app.result is None and app.launch.disabled
    assert app.launch_state.data['url'] == ['']
    assert np.isnan(app.sources['komega'].data['image'][0]).all()
    app.threshold.value = -1.
    assert 'nonnegative' in app.status.text
    app.search.value_input = 'does not exist'
    assert app.selector.value == [dataset.id]


def test_gaussian_handoff_and_normal_defaults(observational, tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify gaussian handoff and normal defaults.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    root = tmp_path/'cache'
    _, _, result = process(dataset, root)
    observation = result_observation(result.id, root)
    config = komega_explorer._load_config(komega_explorer.CONFIG_FILE)
    vesa = komega_explorer.load_dispersion_explorer(config['komega_comparison']['vesa_2026_dir'])
    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'interactive', (8, 10))
    args = dict(product_roots=[], raw_roots=[], registry_file=tmp_path/'registry.json', schedule_initial=False)
    app = integrated.build_document(Document(), input_observation=observation, **args)
    assert app.primary.selected_id == observation.id
    assert app.primary.data.dopplergrams is not None
    np.testing.assert_array_equal(app.primary.data.values, result.arrays['komega'])
    app.primary._store()
    assert 'Parameters stored' in app.primary.status.text
    record = read_registry(args['registry_file'])['observations'][observation.id]
    assert record['model_context']['model'] == 'nc2009'
    assert len(record['processing_chain']['stages']) == 2
    app.primary.filter.sliders['central_k'].value = 2.
    app.primary.filter._perform_recompute()
    app.primary._store()
    reopened = integrated.build_document(Document(), input_observation=observation, **args)
    assert reopened.primary.filter.sliders['central_k'].value == 2.
    normal = integrated.build_document(Document(), **args)
    assert normal.primary.data is None
    assert normal.model_select.value == 'nc2009'
    assert normal.primary.filter._current_parameters() == normal.primary.filter.defaults


def test_dataset_discovery_search_and_scroll(observational, simulation, tmp_path):
    '''
    Purpose
    -------
    Verify dataset discovery search and scroll.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    simulation: tuple
        Synthetic simulation dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    observation, _, _ = observational
    simulated, _, _ = simulation
    records = workflow.discover_dopplergrams(raw_roots=[observation.files[0].parent],
                                            simulation_roots=[simulated.files[0].parent])
    assert {item.source_type for item in records} == {'paired_cubes', 'single_cube'}
    assert len(records) == 2
    app = ui.build_document(Document(), datasets=records, schedule_initial=False)
    assert type(app.selector).__name__ == 'MultiChoice'
    assert app.selector.height is None
    assert not app.full_path.active
    app.search.value_input = 'simulation_hx_10G.nc'
    assert len(app.selector.options) == 1
    assert app.selector.options[0][0] == records[1].id
    app.search.value_input = ''
    assert len(app.selector.options) == 2


def test_coalesces_pending_jobs_and_discards_stale_results(observational, tmp_path):
    '''
    Purpose
    -------
    Verify coalesces pending jobs and discards stale results.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    app = ui.build_document(Document(), datasets=[dataset], cache_root=tmp_path/'cache', schedule_initial=False)
    app.selector.value = [dataset.id]
    first, second = Future(), Future()
    first.set_running_or_notify_cancel()
    with patch.object(ui.COMPUTE_POOL, 'submit', side_effect=[first, second]) as submit:
        app._start(app._generation, dataset, app.current_parameters(), app.current_inputs())
        app.threshold.value = 4.
        app._start(app._generation, dataset, app.current_parameters(), app.current_inputs())
        app.threshold.value = 6.
        app._start(app._generation, dataset, app.current_parameters(), app.current_inputs())
        assert submit.call_count == 1
        first.set_result(('stale', 'stale'))
        callback = next(c for c in app.doc.session_callbacks if type(c).__name__ == 'NextTickCallback')
        app.doc.remove_next_tick_callback(callback)
        callback.callback()
        assert submit.call_count == 2
        assert submit.call_args.args[2]['threshold_G'] == 6.
        assert app.result is None and app.launch.disabled
        second.set_exception(ValueError('alignment fixture failure'))
        callback = next(c for c in app.doc.session_callbacks if type(c).__name__ == 'NextTickCallback')
        app.doc.remove_next_tick_callback(callback)
        callback.callback()
        assert 'alignment fixture failure' in app.status.text


def test_nan_fill_and_explicit_wcs_errors(observational, tmp_path):
    '''
    Purpose
    -------
    Verify nan fill and explicit wcs errors.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    _, _, result = process(dataset, tmp_path/'cache', fill_value='NaN', selection='nonmagnetic')
    assert not np.isfinite(result.arrays['komega']).any()
    for path, value in zip(dataset.files, (1., 2.)):
        with fits.open(path, mode='update') as source:
            source[0].header['CDELT1'] = value
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='spatial alignment mismatch'):
        process(dataset, tmp_path/'other-cache')


def test_registry_rejects_malformed_optional_chain(observational, tmp_path):
    '''
    Purpose
    -------
    Verify registry rejects malformed optional chain.

    Inputs
    ------
    observational: tuple
        Synthetic observational dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset, _, _ = observational
    _, _, result = process(dataset, tmp_path/'cache')
    data = load_observation(result_observation(result.id, tmp_path/'cache'))
    metadata = reproducibility_metadata(data, data.geometry)
    metadata['metadata']['processing_chain'] = {'input':{}, 'stages':[None]}
    # Require the expected RegistryError from this failure case.
    with pytest.raises(RegistryError, match='Processing chain'):
        store_parameters(data.observation.id, metadata,
                         dict(central_k=1.5, width_k=4., central_f=3., width_f=3.), tmp_path/'registry.json')
    assert not (tmp_path/'registry.json').exists()


def test_content_identity_survives_sync_metadata_changes(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify content identity survives sync metadata changes.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path = tmp_path/'immutable.npy'
    path.write_bytes(b'same scientific bytes')
    original = processing_results.file_fingerprint
    calls = []
    def metadata_update(source):
        '''
        Purpose
        -------
        Change sync-related source metadata while retaining the scientific content
        identity.

        Inputs
        ------
        source: str or dict
            Image source name or source metadata record used by the local helper.

        Outputs
        -------
        metadata: dict
            Updated source metadata used by the enclosing identity comparison.
        '''

        value = original(source)
        calls.append(value)
        os.utime(source, None)
        return value
    monkeypatch.setattr(processing_results, 'file_fingerprint', metadata_update)
    value = fingerprint(path)
    assert len(calls) == 2
    assert value['sha256'] == original(path)['sha256']
