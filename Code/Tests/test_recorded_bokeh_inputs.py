'''
Purpose
-------
Exact source-backed launches after an intermediate phase export is removed.

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
import copy
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Event

import numpy as np
import pytest
from bokeh.document import Document

TD = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(TD))
import komega_bokeh_context as context
import observation_datasets as datasets
import observation_komega_explorer as ui
from dopplergram_recalculation import input_reference
from test_dopplergram_recalculation import numerical_product


@pytest.mark.parametrize('source_type', ['paired_cubes', 'single_cube'])
def test_removed_export_uses_exact_recorded_cubes_and_keeps_identity(tmp_path, source_type):
    '''
    Purpose
    -------
    Verify removed export uses exact recorded cubes and keeps identity.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path = tmp_path / 'observations/selected_komega.fits'
    cfg, _, _ = numerical_product(path, (6, 12), nt=24, source_type=source_type)
    original = datasets.dataset_from_fits(path, source_type, context.PROJECT_DIR)
    before = datasets.load_observation(original)
    assert before.analysis_config['atmospheric_profiles']['make_figure'] is False
    reference = input_reference(cfg)
    launch = dict(schema_version=1,
        dataset=dict(id=original.id, file=str(path), source_type=source_type),
        model=dict(key='nc2009', parameters={} if source_type == 'paired_cubes' else
                   dict(a=1., dz=200., theta_deg=45., phi_deg=0.)),
        processing=dict(input_reference=reference, xcorr_geometry='annulus'))
    path.unlink()
    selected = context.validate_context(launch)
    assert selected.id == original.id and selected.kind == 'recorded_input'
    assert selected.files == original.files
    after = datasets.load_observation(selected)
    from_sidecar = datasets.load_observation(original)
    for loaded in (after, from_sidecar):
        assert all(p.is_file() for p in loaded.observation.files)
        for name in ('values', 'kh', 'nu'):
            np.testing.assert_array_equal(getattr(loaded, name), getattr(before, name))
        for first, second in zip(loaded.dopplergrams, before.dopplergrams):
            np.testing.assert_array_equal(first, second)
        assert loaded.metadata['analysis_input'] == before.metadata['analysis_input']
        assert loaded.metadata['source_fingerprints']
        assert 'recalculation_error' not in loaded.metadata
    # Discovery may already contain a phase-only alias with the same ID.
    app = ui.build_document(Document(), launch_context=launch, observations=[original],
        product_roots=[], raw_roots=[], registry_file=tmp_path/'registry.json', schedule_initial=False)
    assert app.catalog[original.id].kind == 'recorded_input'
    assert app.data is not None, app.status.text
    app._store()
    assert 'Parameters stored' in app.status.text, app.status.text
    changed = copy.deepcopy(launch)
    changed['processing']['input_reference']['filtering']['enabled'] = True
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='no longer matches'):
        context.validate_context(changed)
    changed = copy.deepcopy(launch)
    changed['dataset']['id'] = 'different dataset'
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='disagree'):
        context.validate_context(changed)


def test_missing_export_without_recorded_inputs_fails_explicitly(tmp_path):
    '''
    Purpose
    -------
    Verify missing export without recorded inputs fails explicitly.

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

    missing = datasets.dataset_from_fits(tmp_path/'missing_komega.fits', 'paired_cubes', tmp_path)
    # Require the expected (ValueError, FileNotFoundError) from this failure case.
    with pytest.raises((ValueError, FileNotFoundError)):
        datasets.load_observation(missing)


def test_simultaneous_panels_share_one_baseline_calculation(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify simultaneous panels share one baseline calculation.

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

    import dopplergram_recalculation as workflow
    path=tmp_path/'original.nc';path.write_bytes(b'source version')
    reference=dict(data=dict(source_type='single_cube',file=str(path)),filtering=dict(enabled=False))
    started,release,second=Event(),Event(),Event()
    calls=[];expected=object()
    @lru_cache(maxsize=2)
    def calculate(*key):
        '''
        Purpose
        -------
        Return the fixed baseline while recording calls to the shared calculation cache.

        Inputs
        ------
        *key: tuple
            Parameter name, array index, or cache-key arguments used by the local
            substitute.

        Outputs
        -------
        baseline: object
            Enclosing expected baseline fixture.
        '''

        calls.append(key);started.set()
        assert release.wait(5.)
        return expected
    monkeypatch.setattr(workflow,'_load_baseline_cached',calculate)
    def request_second():
        '''
        Purpose
        -------
        Request the same recorded-input baseline through the normal workflow cache.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        baseline: object
            Cached baseline result for the enclosing input reference and config path.
        '''

        second.set()
        return workflow.load_baseline(reference,TD/'config.py')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(workflow.load_baseline,reference,TD/'config.py')
        assert started.wait(5.)
        other=pool.submit(request_second)
        assert second.wait(5.)
        release.set()
        assert first.result(5.) is other.result(5.) is expected
    assert len(calls)==1

