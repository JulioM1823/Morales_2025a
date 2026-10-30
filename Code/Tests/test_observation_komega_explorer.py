'''
Purpose
-------
Observation/simulation loading, filter reuse, registry durability, and UI.

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sys
from unittest.mock import patch

import numpy as np
import pytest
from astropy.io import fits
from bokeh.document import Document
from bokeh.events import ButtonClick

MODULE_DIR = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(MODULE_DIR))
import observation_datasets as datasets
import observation_filter_registry as registry
import observation_komega_explorer as explorer
from gaussian_filter_explorer import CONFIG_FILE, compute_filter_result, compute_diagram_filter
from test_dopplergram_recalculation import numerical_product
from dopplergram_recalculation import recalculate


def product(path, offset=0., nt=80):
    '''
    Purpose
    -------
    Write a small k-omega FITS fixture with the recorded native axes and sampling
    metadata.

    Inputs
    ------
    path: pathlib.Path
        Input or output path used by this fixture or its local substitute.

    offset: float
        Offset or seed adjustment distinguishing synthetic products.

    nt: int or None
        Number of temporal samples in the synthetic cube.

    Outputs
    -------
    values: np.array
        Numerical phase values saved to the fixture FITS file.
    '''

    # Write a saved phase product with the axis and source metadata needed by discovery.
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.arange(8 * 40, dtype=float).reshape(8, 40) / 10. + offset
    values[2, 5] = np.nan
    header = fits.Header(dict(SRCMODE='paired_cubes', BUNIT='deg', CTYPE1='KH', CTYPE2='NU',
        CUNIT1='1/Mm', CUNIT2='mHz', CRVAL1=0., CDELT1=.8, CRVAL2=0., CDELT2=.5,
        DX_MM=.43, DT_S=11.88, NX_ORIG=16, NY_ORIG=16, NT_ORIG=nt))
    fits.writeto(path, values, header, overwrite=True)
    return values


@pytest.fixture
def products(tmp_path):
    '''
    Purpose
    -------
    Write the small observational product set used by discovery and selector tests.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    fixture: tuple
        Product root, written product paths, and numerical reference values.
    '''

    # Write distinct fixture products so discovery and revisit behavior can be checked.
    root = tmp_path / 'products'
    first = root / 'filter_1/observations/25apr2019/komega/25apr2019_fe7090_k7699_komega.fits'
    second = root / 'filter_2/observations/25apr2019/komega/25apr2019_fe7090_k7699_komega.fits'
    third = root / 'filter_1/observations/06may2019/komega/06may2019_ca8542_fe5434_komega.fits'
    values = [product(first), product(second, 10.), product(third, -15., 79)]
    product(root / 'filter_1/observations/25apr2019/coherence.fits')
    return root, [first, second, third], values


@pytest.fixture
def app(products, tmp_path):
    '''
    Purpose
    -------
    Construct the explorer fixture with synthetic inputs and small numerical grids.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    app: object
        Bokeh explorer document with initial scheduling disabled. Apply the
        temporary control/grid settings required by this module's tests.
    '''

    # Use a fresh document and small grids so the test controls the first calculation.
    for i,path in enumerate(products[1]):
        products[2][i]=numerical_product(path,(8,40),i*5,nt=80 if i<2 else 79)[2]
    return explorer.build_document(Document(), product_roots=[products[0]], raw_roots=[],
                                   registry_file=tmp_path/'registry.json', schedule_initial=False)


def select(app, identity):
    '''
    Purpose
    -------
    Select and synchronously load the requested explorer dataset.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    identity: str
        Dataset identifier selected in the explorer.

    Outputs
    -------
    None
        Update selector/load state and assert that the selected dataset is available.
    '''

    app.selector.value = [identity]
    app._perform_load(identity)
    assert app.data is not None, app.status.text


def test_discovery_retains_all_runs_excludes_simulations_and_non_komega(products):
    '''
    Purpose
    -------
    Verify discovery retains all runs excludes simulations and non k-omega.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    simulation_product(products[0] / 'filter_1/simulations/hx_test_komega.fits')
    observations = datasets.discover_observations(product_roots=[products[0]], raw_roots=[])
    assert len(observations) == 3
    assert len({o.id for o in observations}) == 3
    assert {o.files[0] for o in observations} == set(products[1])


def test_project_fits_axes_are_not_swapped_by_standard_naxis_order(products):
    '''
    Purpose
    -------
    Verify project FITS axes are not swapped by standard NAXIS order.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    observation = datasets.discover_observations(product_roots=[products[0]], raw_roots=[])[0]
    data = datasets.load_observation(observation)
    assert data.values.shape == (8, 40)
    np.testing.assert_allclose(data.kh, np.arange(8)*.8)
    np.testing.assert_allclose(data.nu, np.arange(40)*.5)
    assert data.geometry.nx == 16
    assert not data.metadata['sampling_inferred']
    assert data.metadata['source_fingerprints'][0]['sha256']


def test_legacy_inference_and_wrong_units_handled_explicitly(products):
    '''
    Purpose
    -------
    Verify legacy inference and wrong units handled explicitly.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path = products[1][0]
    with fits.open(path, mode='update') as hdus:
        for key in ['NX_ORIG', 'NT_ORIG', 'NY_ORIG']:
            del hdus[0].header[key]
    observation = datasets.Observation('fits:test', 'test', 'fits', (path,))
    data = datasets.load_observation(observation)
    assert data.geometry.nt == 80 and data.geometry.nx == 16
    assert data.metadata['sampling_inferred']
    with fits.open(path, mode='update') as hdus:
        hdus[0].header['CUNIT2'] = 'Hz'
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='frequency units'):
        datasets.load_observation(observation)


def test_raw_observation_pairs_use_pipeline_phase_computation(tmp_path):
    '''
    Purpose
    -------
    Verify raw observation pairs use pipeline phase computation.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    root = tmp_path / '25apr2019'
    root.mkdir()
    rng = np.random.default_rng(42)
    first = root/'25Apr2019_000001_velocity_k7699.fits'
    second = root/'25Apr2019_000001_velocity_fe7090.fits'
    cubes = [rng.normal(size=(25, 8, 8)), rng.normal(size=(25, 8, 8))]
    for path, cube in zip([first, second], cubes):
        fits.writeto(path, cube)
    observations = datasets.discover_observations(product_roots=[], raw_roots=[root])
    assert len(observations) == 1 and observations[0].kind == 'raw_pair'
    data = datasets.load_observation(observations[0])
    assert data.geometry.nt == 25 and data.geometry.nx == 8
    assert data.values.shape == (4, 13)
    assert not data.metadata['sampling_inferred']
    assert data.metadata['source_processing']['gaussian_preprocessed'] is False
    # The loader is the existing pipeline, with no filter/output run.
    config = datasets.configuration(str(CONFIG_FILE)).config.copy()
    config = __import__('copy').deepcopy(config)
    config['data'].update(source_type='paired_cubes', v1=str(observations[0].files[0]),
                          v2=str(observations[0].files[1]), h1=0, h2=1)
    config['data'].setdefault('coherence_outfile', '')
    config['_module_dir'] = str(CONFIG_FILE.parent)
    defaults = datasets.configuration(str(CONFIG_FILE)).paired_cubes_inputs
    config['time_distance'].update(dt=defaults['dt'], p_dx_Mm=defaults['p_dx_Mm'])
    # Pair ordering is deterministic lexicographic, as in batch.ipynb.
    expected, kh, nu, _ = datasets.pipeline.TimeDistance(config).compute_komega_diagram(
        cubes[0] if observations[0].files[0] == first else cubes[1],
        cubes[1] if observations[0].files[1] == second else cubes[0])
    np.testing.assert_allclose(data.values, expected, equal_nan=True)
    np.testing.assert_array_equal(data.kh, kh)
    np.testing.assert_array_equal(data.nu, nu)


def test_ui_has_one_root_searchable_scrollable_selector_and_linked_plots(app):
    '''
    Purpose
    -------
    Verify ui has one root searchable scrollable selector and linked plots.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.doc.validate()
    assert len(app.doc.roots) == 1
    assert type(app.selector).__name__ == 'MultiChoice'
    assert app.selector.height is None
    assert not app.full_path.active
    assert app.remove_filter.label == 'Remove Filter'
    assert app.filter.status not in app.doc.models
    assert app.doc.get_model_by_name('observations:provenance') is None
    assert app.doc.get_model_by_name('observations:preview_status') is None
    assert app.observed_plot.x_range is app.filter.plot.x_range is app.result_plot.x_range
    assert app.mapper.low == -80. and app.mapper.high == 80.
    selected = app.selected_id
    app.search.value_input = '06may2019'
    assert len(app.selector.options) == 1
    assert '06may2019' in app.selector.options[0][1]
    assert app.selected_id == selected  # Searching does not switch/save another dataset.
    app.search.value_input = ''
    assert len(app.selector.options) == 3
    assert app.selector.value == [selected]


def test_selection_updates_observed_pixels_and_native_gaussian_geometry(app, products):
    '''
    Purpose
    -------
    Verify selection updates observed pixels and native gaussian geometry.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    for observation in app.observations:
        select(app, observation.id)
        expected = products[2][products[1].index(observation.files[0])]
        np.testing.assert_allclose(app.image_source.data['image'][0], expected.T, equal_nan=True)
        np.testing.assert_array_equal(app.boundary_source.data['kh'], app.data.kh)
        direct = compute_filter_result(app.filter.geometry, **app.filter._current_parameters())
        np.testing.assert_array_equal(app.filter_result.transmission, direct.transmission)
        np.testing.assert_array_equal(app.transmission, compute_diagram_filter(app.data.kh, app.data.nu, app.filter.geometry, **app.filter._current_parameters()))
    assert app.selector.value == [app.selected_id]


def test_every_gaussian_control_recalculates_cubes_and_remove_restores_without_reloading(app):
    '''
    Purpose
    -------
    Verify every gaussian control recalculates cubes and remove restores without
    reloading.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    original = app.image_source.data['image'][0].copy()
    app.apply_filter.active = True
    assert app.transmission.shape == original.shape
    for slider in app.filter.sliders.values():
        prior = app.transmission.copy()
        slider.value += .5
        app.filter._perform_recompute()
        assert not np.array_equal(prior, app.transmission)
        np.testing.assert_array_equal(app.hover_source.data['power'], (app.transmission**2).ravel())
        np.testing.assert_allclose(app.image_source.data['image'][0], original, equal_nan=True)
        native = recalculate(app.data.dopplergrams,app.data.analysis_config,app.filter._current_parameters())[0].T
        np.testing.assert_array_equal(app.result_source.data['image'][0],native)
        np.testing.assert_array_equal(app.hover_source.data['result'],native.ravel())
        assert (app.mapper.low, app.mapper.high) == (-80., 80.)
    with patch.object(explorer, 'load_observation', side_effect=AssertionError('Remove reloaded data')):
        app.remove_filter._trigger_event(ButtonClick(model=app.remove_filter))
        app.remove_filter._trigger_event(ButtonClick(model=app.remove_filter))
    assert not app.apply_filter.active
    np.testing.assert_allclose(app.result_source.data['image'][0], original, equal_nan=True)
    np.testing.assert_allclose(app.image_source.data['image'][0], original, equal_nan=True)


def test_save_update_preserve_other_records_and_restore_on_revisit(app):
    '''
    Purpose
    -------
    Verify save update preserve other records and restore on revisit.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    first, second = app.observations[:2]
    select(app, first.id)
    app.filter.sliders['central_k'].value = 2.45
    original_nt = app.data.geometry.nt
    app.sampling['nt'].value = original_nt+1
    app._store()
    assert 'Sampling must match' in app.status.text
    app.sampling['nt'].value = app.data.geometry.nt
    app._store()
    assert 'Parameters stored for' in app.status.text
    select(app, second.id)
    assert app.filter.sliders['central_k'].value == app.filter.defaults['central_k']
    assert app.sampling['nt'].value == 80
    app.filter.sliders['width_f'].value = 4.25
    app._store()
    saved_second = registry.read_registry(app.registry_file)['observations'][second.id]
    select(app, first.id)
    assert app.filter.sliders['central_k'].value == 2.45
    assert app.sampling['nt'].value == original_nt
    assert 'Loaded stored parameters for' in app.status.text
    app.filter.sliders['central_k'].value = 2.85
    app._store()
    records = registry.read_registry(app.registry_file)['observations']
    assert len(records) == 2
    assert records[first.id]['gaussian']['parameters']['central_k'] == 2.85
    assert records[second.id] == saved_second
    assert records[first.id]['dataset']['axes']['nu_mHz'] == app.data.nu.tolist()
    # A fresh server session restores from disk, without browser local storage.
    other = explorer.build_document(Document(), product_roots=[first.files[0].parents[4]], raw_roots=[],
        registry_file=app.registry_file, schedule_initial=False)
    select(other, first.id)
    assert other.filter.sliders['central_k'].value == 2.85
    assert other.sampling['nt'].value == original_nt


def test_source_changes_do_not_silently_load_or_store_old_parameters(app):
    '''
    Purpose
    -------
    Verify source changes do not silently load or store old parameters.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app._store()
    path = app.data.observation.files[0]
    product(path, offset=19.)
    app._store()
    assert 'Source changed while open' in app.status.text
    select(app, app.selected_id)
    assert 'Source data or axes changed' in app.status.text
    app._store()
    assert 'Parameters stored' in app.status.text


@pytest.mark.parametrize('malformed', ['{truncated', '{}', '{"schema_version":1,"observations":[],"schema_version":1}',
                                       '{"schema_version":1,"observations":{},"bad":NaN}'])
def test_bad_registry_displays_error_uses_defaults_and_never_overwrites(app, malformed):
    '''
    Purpose
    -------
    Verify bad registry displays error uses defaults and never overwrites.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    malformed: str
        Invalid registry contents supplied by the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.registry_file.write_text(malformed)
    select(app, app.selected_id)
    assert 'file was not changed' in app.status.text.lower()
    assert app.filter_result is not None
    app._store()
    assert 'not stored' in app.status.text
    assert app.registry_file.read_text() == malformed


def test_atomic_write_failure_leaves_prior_registry_intact(app):
    '''
    Purpose
    -------
    Verify atomic write failure leaves prior registry intact.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app._store()
    original = app.registry_file.read_bytes()
    app.filter.sliders['central_k'].value += .25
    with patch.object(registry.os, 'replace', side_effect=OSError('interrupted replacement')):
        app._store()
    assert 'interrupted replacement' in app.status.text
    assert app.registry_file.read_bytes() == original
    assert not list(app.registry_file.parent.glob('.registry.json.*.tmp'))


def test_locked_updates_from_independent_sessions_do_not_lose_other_records(app):
    '''
    Purpose
    -------
    Verify locked updates from independent sessions do not lose other records.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    prepared = [datasets.load_observation(o) for o in app.observations]
    def save(data):
        '''
        Purpose
        -------
        Save the supplied registry values through the normal concurrent-update path.

        Inputs
        ------
        data: object
            Synthetic variable data, registry record, or external data root for the
            current helper.

        Outputs
        -------
        None
            Execute the registry write used by the enclosing synchronization test.
        '''

        registry.store_parameters(data.observation.id,
            datasets.reproducibility_metadata(data, data.geometry), app.filter.defaults, app.registry_file)
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(save, prepared))
    assert len(registry.read_registry(app.registry_file)['observations']) == 3


def test_invalid_sampling_and_parameters_are_not_written(app):
    '''
    Purpose
    -------
    Verify invalid sampling and parameters are not written.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.sampling['nt'].value = 3.5
    app._store()
    assert 'integer sample count' in app.status.text
    assert not app.registry_file.exists()
    metadata = datasets.reproducibility_metadata(app.data, app.data.geometry)
    metadata['sampling']['dx_Mm'] = float('nan')
    # Require the expected registry.RegistryError from this failure case.
    with pytest.raises(registry.RegistryError, match='dx_Mm'):
        registry.store_parameters(app.selected_id, metadata, app.filter.defaults, app.registry_file)
    # Require the expected registry.RegistryError from this failure case.
    with pytest.raises(registry.RegistryError, match='finite'):
        registry.store_parameters(app.selected_id, metadata, dict(app.filter.defaults, central_k=float('inf')), app.registry_file)


def test_missing_source_and_empty_collection_report_errors(app, tmp_path):
    '''
    Purpose
    -------
    Verify recorded cubes recover removed exports and missing sources or empty
    collections report errors.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path = app.data.observation.files[0]
    expected = app.data.values.copy()
    path.unlink()
    select_id = app.selected_id
    app._perform_load(select_id)
    # Removing an intermediate export preserves recovery from its recorded cubes.
    assert app.data is not None, app.status.text
    assert app.data.observation.id == select_id
    np.testing.assert_array_equal(app.data.values, expected)
    for source in app.data.observation.files:
        assert source.is_relative_to(tmp_path)
        source.unlink()
    app._perform_load(select_id)
    assert app.data is None
    assert app.store_button.disabled
    assert 'Cannot load' in app.status.text
    empty = explorer.build_document(Document(), product_roots=[tmp_path/'missing'], raw_roots=[],
                                    registry_file=tmp_path/'missing.json', schedule_initial=False)
    assert 'No numerical datasets found' in empty.status.text
    assert empty.store_button.disabled


def callback(app, name):
    '''
    Purpose
    -------
    Retrieve the most recent document callback with the requested function name.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    name: str
        Module, callback, variable, or context label selected by the caller.

    Outputs
    -------
    callback: callable
        Registered callback function. A missing name raises StopIteration.
    '''

    return next(item.callback for item in reversed(app.doc.session_callbacks)
                if item.callback.__name__ == name)


def test_background_loader_updates_only_the_current_selection(app):
    '''
    Purpose
    -------
    Verify background loader updates only the current selection.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from concurrent.futures import Future
    future = Future()
    chosen = app.observations[-1]
    app.selector.value = [chosen.id]
    assert app.store_button.disabled and app.data is None
    with patch.object(explorer.LOAD_POOL, 'submit', return_value=future):
        app._start_load(chosen.id)
    future.set_result(datasets.load_observation(chosen))
    callback(app, 'accept')()
    assert app.data.observation.id == chosen.id
    assert not app.store_button.disabled
    assert 'Using default parameters' in app.status.text


def test_slow_old_selection_cannot_replace_a_new_observation(app):
    '''
    Purpose
    -------
    Verify slow old selection cannot replace a new observation.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from concurrent.futures import Future
    future = Future()
    old, new = app.observations[-2:]
    app.selector.value = [old.id]
    with patch.object(explorer.LOAD_POOL, 'submit', return_value=future):
        app._start_load(old.id)
    select(app, new.id)
    future.set_result(datasets.load_observation(old))
    callback(app, 'accept')()
    assert app.data.observation.id == new.id


def test_cloud_load_timeout_reports_error_without_freezing_selection(app):
    '''
    Purpose
    -------
    Verify cloud load timeout reports error without freezing selection.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from concurrent.futures import Future
    future = Future()
    chosen = app.observations[-1]
    app.selector.value = [chosen.id]
    with patch.object(explorer.LOAD_POOL, 'submit', return_value=future):
        app._start_load(chosen.id)
    callback(app, 'expired')()
    assert app.data is None
    assert app.store_button.disabled
    assert 'Loading timed out' in app.status.text
    select(app, app.observations[0].id)
    assert app.data is not None


def test_source_backed_saved_diagrams_use_the_raw_cube_load_deadline(app):
    '''
    Purpose
    -------
    Verify source backed saved diagrams use the raw cube load deadline.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from concurrent.futures import Future
    chosen = app.observations[-1]
    app.selector.value = [chosen.id]
    before = set(app.doc.session_callbacks)
    with patch.object(explorer.LOAD_POOL, 'submit', return_value=Future()):
        app._start_load(chosen.id)
    added = set(app.doc.session_callbacks) - before
    deadlines = [item.timeout for item in added if type(item).__name__ == 'TimeoutCallback']
    assert deadlines == [120000]


def test_incomplete_fingerprint_registry_is_rejected_without_losing_display(app):
    '''
    Purpose
    -------
    Verify incomplete fingerprint registry is rejected without losing display.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app._store()
    contents = json.loads(app.registry_file.read_text())
    contents['observations'][app.selected_id]['dataset']['metadata']['source_fingerprints'] = [{}]
    app.registry_file.write_text(json.dumps(contents))
    select(app, app.selected_id)
    assert 'Invalid dataset source fingerprint' in app.status.text
    assert app.data is not None and app.filter_result is not None


def test_hdf5_observations_reuse_existing_dimension_scale_loader(tmp_path):
    '''
    Purpose
    -------
    Verify hdf5 observations reuse existing dimension scale loader.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import h5py
    root = tmp_path / '25apr2019'
    root.mkdir()
    rng = np.random.default_rng(51)
    for name in ('fe7090', 'k7699'):
        path = root / f'25Apr2019_000001_velocity_{name}.h5'
        with h5py.File(path, 'w') as hdf:
            cube = hdf.create_dataset('velocity', data=rng.normal(size=(25, 8, 8)))
            for index, (axis, count) in enumerate(zip(('t', 'y', 'x'), cube.shape)):
                scale = hdf.create_dataset(axis, data=np.arange(count))
                scale.make_scale(axis)
                cube.dims[index].attach_scale(scale)
    observations = datasets.discover_observations(product_roots=[], raw_roots=[root])
    assert len(observations) == 1
    data = datasets.load_observation(observations[0])
    assert data.values.shape == (4, 13)
    app = explorer.build_document(Document(), product_roots=[], raw_roots=[root],
        registry_file=tmp_path/'hdf5-registry.json', schedule_initial=False)
    app._store()
    assert 'Parameters stored' in app.status.text
    record = registry.read_registry(app.registry_file)['observations'][app.selected_id]
    assert record['dataset']['kind'] == 'raw_pair'
    assert record['dataset']['sampling']['nt'] == 25


def simulation_product(path, offset=0., legacy=False):
    '''
    Purpose
    -------
    Write a synthetic simulation k-omega FITS product with current or legacy metadata.

    Inputs
    ------
    path: pathlib.Path
        Input or output path used by this fixture or its local substitute.

    offset: float
        Offset or seed adjustment distinguishing synthetic products.

    legacy: bool
        Whether to write or load the legacy product metadata variant.

    Outputs
    -------
    values: np.array
        Saved phase array, with the fixture frequency/wavenumber axes and units.
    '''

    # Include the current or legacy sampling metadata required by this loader case.
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.arange(12 * 25, dtype=float).reshape(12, 25) / 10. + offset
    values[3, 8] = np.nan
    header = fits.Header(dict(SRCMODE='single_cube', BUNIT='deg', CTYPE1='KH', CTYPE2='NU',
        CUNIT1='1/Mm', CUNIT2='mHz', CRVAL1=0., CDELT1=np.pi/.16/11.,
        CRVAL2=0., CDELT2=(500./30.)/24., DX_MM=.16, DT_S=30.))
    if not legacy:
        header.update(NX_ORIG=24, NY_ORIG=24, NT_ORIG=49)
    fits.writeto(path, values, header, overwrite=True)
    return values


@pytest.fixture
def simulations(products):
    '''
    Purpose
    -------
    Extend the product fixture with synthetic simulation products.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    Outputs
    -------
    values_by_path: dict
        Written simulation paths mapped to their numerical phase arrays.
    '''

    # Extend the existing fixture root with independently identifiable simulation files.
    root = products[0]
    paths = [root/'filter_1/simulations/magneto/horizontal/hx_100g_komega.fits',
             root/'export/vx_10g_komega.fits', root/'export/z0_0g_komega.fits',
             root/'export/renamed_komega.fits']
    return dict(zip(paths, [simulation_product(path, i*5.) for i, path in enumerate(paths)]))


def test_mixed_discovery_includes_simulation_paths_prefixes_and_source_metadata(products, simulations):
    '''
    Purpose
    -------
    Verify mixed discovery includes simulation paths prefixes and source metadata.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    simulations: dict
        Synthetic simulation paths mapped to their reference arrays.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    observations = datasets.discover_observations(product_roots=[products[0]], raw_roots=[])
    mixed = datasets.discover_observations(product_roots=[products[0]], raw_roots=[], include_simulations=True)
    assert len(observations) == 3 and len(mixed) == 7
    assert {item.id for item in observations} == {item.id for item in mixed if item.kind == 'fits'}
    assert {item.files[0] for item in mixed if item.kind == 'simulation_fits'} == set(simulations)
    assert len({item.id for item in mixed}) == len(mixed)


@pytest.mark.parametrize('legacy', [False, True])
def test_simulation_loader_uses_own_sampling_axes_and_array_orientation(tmp_path, legacy):
    '''
    Purpose
    -------
    Verify simulation loader uses own sampling axes and array orientation.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    legacy: bool
        Whether to write or load the legacy product metadata variant.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path = tmp_path/'simulations/hx_test_komega.fits'
    values = simulation_product(path, legacy=legacy)
    simulation = datasets.discover_observations(product_roots=[tmp_path], raw_roots=[], include_simulations=True)[0]
    data = datasets.load_observation(simulation)
    np.testing.assert_allclose(data.values, values, equal_nan=True)
    np.testing.assert_allclose(data.kh, np.linspace(0., np.pi/.16, 12))
    np.testing.assert_allclose(data.nu, np.linspace(0., 500./30., 25))
    assert data.geometry.dt_seconds == 30. and data.geometry.dx_Mm == .16
    assert data.geometry.nx == 24 and data.ny == 24
    assert data.geometry.nt == (50 if legacy else 49)
    assert data.metadata['sampling_inferred'] == legacy
    assert data.metadata['source_type'] == 'single_cube'
    assert not data.metadata['sampling_defaults_used']
    with fits.open(path, mode='update') as hdus:
        del hdus[0].header['DT_S']
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='Simulation FITS products require DT_S and DX_MM'):
        datasets.load_observation(simulation)


def test_mixed_browser_filter_save_and_revisit_workflow(products, simulations, tmp_path):
    '''
    Purpose
    -------
    Verify mixed browser filter save and revisit workflow.

    Inputs
    ------
    products: tuple
        Saved numerical products, paths, and reference values supplied by the fixture.

    simulations: dict
        Synthetic simulation paths mapped to their reference arrays.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    for i,path in enumerate(products[1]):
        products[2][i]=numerical_product(path,(8,40),i*5,nt=80 if i<2 else 79)[2]
    for i,path in enumerate(simulations):
        simulations[path]=numerical_product(path,(12,25),i*5,nt=49,source_type='single_cube',dt=30.,dx=.16)[2]
    app = explorer.build_document(Document(), product_roots=[products[0]], raw_roots=[],
        registry_file=tmp_path/'mixed-registry.json', schedule_initial=False)
    observation = next(item for item in app.observations if item.kind == 'fits')
    select(app, observation.id)
    app.filter.sliders['central_k'].value = 2.45
    app._store()
    saved_observation = registry.read_registry(app.registry_file)['observations'][observation.id]

    app.search.value_input = 'HX_100G'
    assert len(app.selector.options) == 2  # Search retains the active observation.
    simulation_id = next(identity for identity, label in app.selector.options if 'hx_100g' in label)
    select(app, simulation_id)
    assert app.observed_plot.title.text == 'Simulated phase difference'
    assert app.filter.sliders['central_k'].value == app.filter.defaults['central_k']
    original = simulations[app.data.observation.files[0]].T
    np.testing.assert_allclose(app.image_source.data['image'][0], original, equal_nan=True)
    assert app.filter.geometry.dt_seconds == 30. and app.filter.geometry.dx_Mm == pytest.approx(.16)
    app.apply_filter.active = True
    for slider in app.filter.sliders.values():
        slider.value += .5
        app.filter._perform_recompute()
        assert app.transmission.shape == original.shape
        native=recalculate(app.data.dopplergrams,app.data.analysis_config,app.filter._current_parameters())[0].T
        np.testing.assert_array_equal(app.result_source.data['image'][0],native)
    with patch.object(explorer, 'load_observation', side_effect=AssertionError('Remove reloaded simulation')):
        app.remove_filter._trigger_event(ButtonClick(model=app.remove_filter))
    np.testing.assert_allclose(app.result_source.data['image'][0], original, equal_nan=True)
    app._store()
    assert 'Parameters stored for hx_100g' in app.status.text
    saved_parameters = app.filter._current_parameters()
    app.search.value_input = ''
    assert len(app.selector.options) == 7
    select(app, observation.id)
    assert app.observed_plot.title.text == 'Observed phase difference'
    assert app.filter.sliders['central_k'].value == 2.45
    select(app, simulation_id)
    assert app.filter._current_parameters() == saved_parameters
    assert 'Loaded stored parameters' in app.status.text
    app.filter.sliders['central_k'].value = 2.85
    app._store()
    records = registry.read_registry(app.registry_file)['observations']
    assert len(records) == 2
    assert records[observation.id] == saved_observation
    assert records[simulation_id]['gaussian']['parameters']['central_k'] == 2.85
    assert records[simulation_id]['dataset']['kind'] == 'simulation_fits'
    assert records[simulation_id]['dataset']['sampling']['nt'] == 49
    fresh = explorer.build_document(Document(), product_roots=[products[0]], raw_roots=[],
        registry_file=app.registry_file, schedule_initial=False)
    select(fresh, simulation_id)
    assert fresh.filter.sliders['central_k'].value == 2.85
