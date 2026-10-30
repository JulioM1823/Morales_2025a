'''
Purpose
-------
Spectral statistics, physical grids, caching, and all native Bokeh models.

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
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pytest
from bokeh.document import Document

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import coherence_bokeh as ui
import spectral_coherence as spectral
from test_integrated_komega_explorer import app, calculate, select
from test_komega_explorer import app as legacy_app, calculate as calculate_legacy
from test_dopplergram_recalculation import numerical_product
from observation_datasets import Observation, load_observation


def waves(shape=(128, 32, 40), dt=30., dx=.16):
    '''
    Purpose
    -------
    Generate reproducible noisy plane waves with a known phase difference and Fourier
    bin.

    Inputs
    ------
    shape: tuple of int
        Requested numerical-product or cube dimensions in the current fixture.

    dt: float
        Temporal cadence in seconds.

    dx: float
        Spatial sampling in Mm per pixel.

    Outputs
    -------
    waves: tuple
        Two velocity-unit cubes with the requested shape, horizontal angular
        wavenumber (Mm^-1), and frequency (mHz). Use a fixed random seed.
    '''

    # Use an exact Fourier-bin plane wave and a fixed random seed for reproducibility.
    nt, ny, nx = shape
    t, y, x = np.indices(shape)
    angle = 2*np.pi*(3*x/nx + 2*y/ny - 12*t/nt)
    rng = np.random.default_rng(713)
    return (3*np.cos(angle) + .4*rng.normal(size=shape),
            3*np.cos(angle+.7) + .4*rng.normal(size=shape),
            np.hypot(2*np.pi*3/(nx*dx), 2*np.pi*2/(ny*dx)), 12000/(nt*dt))


@pytest.mark.parametrize('shape,dt,dx', [((128,32,40),30.,.16), ((129,33,41),11.88,.43)])
def test_known_wave_bounds_reproducibility_and_exact_fourier_units(shape,dt,dx):
    '''
    Purpose
    -------
    Verify known wave bounds reproducibility and exact fourier units.

    Inputs
    ------
    shape: tuple of int
        Requested numerical-product or cube dimensions in the current fixture.

    dt: float
        Temporal cadence in seconds.

    dx: float
        Spatial sampling in Mm per pixel.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    first, second, kh, nu = waves(shape,dt,dx)
    result = spectral.estimate_coherence(first,second,dt,dx)
    repeated = spectral.estimate_coherence(first,second,dt,dx)
    np.testing.assert_array_equal(result.values,repeated.values)
    finite = result.values[np.isfinite(result.values)]
    assert finite.min() >= 0 and finite.max() <= 1
    ki, fi = np.argmin(abs(result.kh-kh)), np.argmin(abs(result.nu-nu))
    assert result.values[ki,fi] > .98
    np.testing.assert_allclose(np.diff(result.nu),1000/(shape[0]*dt))
    np.testing.assert_allclose(np.diff(result.kh),max(2*np.pi/(shape[2]*dx),2*np.pi/(shape[1]*dx)))
    # Reconstruct the ratio from the averaged complex and auto-spectra.
    valid = np.isfinite(result.values)
    reference = abs(result.cross[valid])**2/result.auto_lower[valid]/result.auto_higher[valid]
    np.testing.assert_allclose(result.values[valid],reference,atol=2e-15)


def test_independent_noise_is_low_and_not_trivial_unity():
    '''
    Purpose
    -------
    Verify independent noise is low and not trivial unity.

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

    rng = np.random.default_rng(919)
    cubes = [rng.normal(size=(128,48,48)) for _ in range(2)]
    result = spectral.estimate_coherence(*cubes,20.,.2)
    interior = result.values[2:,3:-3]
    assert np.nanmean(interior) < .02
    assert np.nanquantile(interior,.99) < .1
    assert np.nanmax(interior) < .3


def test_observational_time_delay_is_corrected_before_frequency_pooling():
    '''
    Purpose
    -------
    Verify observational time delay is corrected before frequency pooling.

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

    rng=np.random.default_rng(89)
    first=rng.normal(size=(64,16,16))
    second=np.roll(first,5,axis=0)
    uncorrected=spectral.estimate_coherence(first,second,10.,.3)
    corrected=spectral.estimate_coherence(first,second,10.,.3,phase_delay_seconds=-50.)
    assert np.nanmean(uncorrected.values) < .8
    np.testing.assert_allclose(corrected.values[np.isfinite(corrected.values)],1.,atol=2e-15)


def test_independent_direct_annular_frequency_spectral_pooling():
    '''
    Purpose
    -------
    Verify independent direct annular frequency spectral pooling.

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

    rng = np.random.default_rng(14)
    first,second = [rng.normal(size=(32,12,16)) for _ in range(2)]
    result = spectral.estimate_coherence(first,second,12.,.3)
    transforms=[]
    for cube in (first,second):
        cube=cube/np.max(abs(cube))
        transforms.append(np.fft.fftshift(np.fft.fftn((cube-cube.mean()).transpose(1,2,0))))
    kx=2*np.pi*np.fft.fftshift(np.fft.fftfreq(16,.3))
    ky=2*np.pi*np.fft.fftshift(np.fft.fftfreq(12,.3))
    radius=np.hypot(ky[:,None],kx[None,:])
    dk=result.kh[1]-result.kh[0]
    for ki,fi in ((2,4),(3,8),(4,14)):
        mask=(np.floor(radius/dk+.5)==ki)&(radius<=min(abs(kx).max(),abs(ky).max())+dk*1e-10)
        indices=slice(16+max(0,fi-2),16+min(16,fi+3))
        a,b=[value[mask,indices] for value in transforms]
        expected=abs(np.mean(a*np.conj(b)))**2/np.mean(abs(a)**2)/np.mean(abs(b)**2)
        assert result.values[ki,fi] == pytest.approx(expected,abs=2e-15)


def test_zero_power_missing_samples_small_scales_and_threshold():
    '''
    Purpose
    -------
    Verify zero power missing samples small scales and threshold.

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

    first,second,_,_=waves()
    zeros=spectral.estimate_coherence(np.zeros_like(first),np.zeros_like(second),30.,.16)
    assert np.isnan(zeros.values).all()
    first[:,0,0]=np.nan
    result=spectral.estimate_coherence(first,second,30.,.16)
    assert result.metadata['complete_spatial_fraction'] == pytest.approx(1-1/(32*40))
    tiny=spectral.estimate_coherence(first*1e-190,second*1e-190,30.,.16)
    np.testing.assert_allclose(result.values,tiny.values,atol=1e-14)
    np.testing.assert_array_equal(spectral.coherence_weights([np.nan,0.,.4,.5,1.],.5),[0.,0.,0.,.5,1.])
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError): spectral.coherence_weights([.5],1.01)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='jointly finite'):
        spectral.estimate_coherence(np.full_like(first,np.nan),second,30.,.16)


def test_alignment_preserves_coordinates_and_never_extrapolates_or_bridges_missing_bins():
    '''
    Purpose
    -------
    Verify alignment preserves coordinates and never extrapolates or bridges missing
    bins.

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

    first,second,_,_=waves()
    result=spectral.estimate_coherence(first,second,30.,.16)
    np.testing.assert_allclose(spectral.align_coherence(result,result.kh,result.nu),result.values.T,equal_nan=True)
    aligned=spectral.align_coherence(result,[-1.,result.kh[3],result.kh[-1]+1.],[-1.,result.nu[8],result.nu[-1]+1.])
    assert np.isnan(aligned[[0,2],:]).all() and np.isnan(aligned[:,[0,2]]).all()
    assert aligned[1,1] == result.values[3,8]
    values=result.values.copy();values[3,8]=np.nan
    missing=replace(result,values=values)
    assert np.isnan(spectral.align_coherence(missing,[(result.kh[3]+result.kh[4])/2],[result.nu[8]])).all()


def test_integrated_all_models_fields_and_backward_compatibility_without_repeated_fft(app):
    '''
    Purpose
    -------
    Verify integrated all models fields and backward compatibility without repeated FFT.

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

    controls=app.model_workspace.coherence
    assert controls.threshold.value == 0 and not controls.apply.active
    with patch.object(ui,'coherence_for_data',wraps=ui.coherence_for_data) as estimator:
        controls.show.active=True
        assert controls.result is not None, controls.status.text
        assert controls.mapper.low == 0 and controls.mapper.high == 1
        assert estimator.call_count == 1
        for model in app.model_workspace.models:
            app.model_select.value=model.definition.key
            calculate(app)
            cached=model.last_result
            legacy=[source.data['image'][0].copy() for source in model.filtered.image_sources]
            controls.apply.active=True
            np.testing.assert_array_equal(model.filtered_result.phase_deg,cached.phase_deg*model.transmission[...,None])
            with patch.object(app.model_workspace.vesa,'compute_diagram',side_effect=AssertionError('Repeated root solve')):
                controls.numeric.input.value='.43'
                assert controls.threshold.value == .43
                for field,attribute in [('phase','phase_deg'),('kz_real','kz_real'),('kz_imag','kz_imag')]:
                    model.field_select.value=field
                    np.testing.assert_array_equal(getattr(model.filtered_result,attribute),getattr(cached,attribute)*model.transmission[...,None])
                    expected=spectral.coherence_weights(controls.aligned(cached),.43)*model.transmission
                    np.testing.assert_array_equal(model.filtered.spectral_weight,expected)
                    np.testing.assert_array_equal(model.filtered.coherence_weight,spectral.coherence_weights(controls.aligned(cached),.43))
                model.field_select.value='phase'
                controls.apply.active=False
            for before,source in zip(legacy,model.filtered.image_sources):
                np.testing.assert_array_equal(before,source.data['image'][0])
            assert all(overlay.visible for overlay in model.filtered._coherence_overlays)
            assert all(not renderer.visible for renderer in model.filtered.image_renderers)
            assert model.last_result is cached
        assert estimator.call_count == 1
    controls.numeric.input.value='1.1'
    assert controls.threshold.value == .43 and controls.numeric.message.visible
    assert app.doc.validate() is None


def test_dataset_switch_invalidation_and_cache_reuse(app):
    '''
    Purpose
    -------
    Verify dataset switch invalidation and cache reuse.

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

    controls=app.model_workspace.coherence
    with patch.object(ui,'coherence_for_data',wraps=ui.coherence_for_data) as estimator:
        controls.apply.active=True
        original=controls.result
        original_data=app.primary.data
        select(app.primary,app.primary.observations[1].id)
        assert controls.result is not original
        assert controls.result.metadata['dataset_id'] == app.primary.selected_id
        # Model/threshold/Gaussian edits never change the measured baseline.
        second=controls.result
        app.primary.filter.sliders['width_f'].value=2.
        app.primary.filter._perform_recompute()
        controls.threshold.value=.2
        assert controls.result is second and estimator.call_count == 2
        app.primary.data=original_data
        controls.sync()
        assert controls.result is original and estimator.call_count == 2


@pytest.mark.parametrize('source_type,dt,dx',[('paired_cubes',11.88,.43),('single_cube',30.,.16)])
def test_correct_native_pair_sampling_and_source_version_invalidation(tmp_path,source_type,dt,dx):
    '''
    Purpose
    -------
    Verify correct native pair sampling and source version invalidation.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    dt: float
        Temporal cadence in seconds.

    dx: float
        Spatial sampling in Mm per pixel.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path=tmp_path/'pair_komega.fits'
    cfg,cubes,_=numerical_product(path,(8,20),nt=40,source_type=source_type,dt=dt,dx=dx)
    data=load_observation(Observation('test','test','fits',(path,)))
    result=spectral.coherence_for_data(data)
    assert result.metadata['sampling']['dt_seconds'] == dt
    assert result.metadata['sampling']['dx_Mm'] == dx
    assert result.metadata['height_pair']['h1'] == cfg['data']['h1']
    assert result.metadata['height_pair']['h2'] == cfg['data']['h2']
    source=Path(data.analysis_config['_dopplergram_source_versions'][0][0])
    source.touch()
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='changed'): spectral.data_key(data)


def test_async_stale_results_are_discarded_and_session_closes(app,monkeypatch):
    '''
    Purpose
    -------
    Verify async stale results are discarded and session closes.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    controls=app.model_workspace.coherence
    futures=[]
    def submit(work):
        '''
        Purpose
        -------
        Record deferred worker work and return the controlled Future used by the test.

        Inputs
        ------
        work: callable
            Worker calculation retained by the controlled executor.

        Outputs
        -------
        future: concurrent.futures.Future
            Future retained by the enclosing fixture; the test decides when the
            recorded callable runs or when the Future is completed.
        '''

        future=Future();future.set_running_or_notify_cancel();futures.append((future,work));return future
    monkeypatch.setattr(ui.COHERENCE_POOL,'submit',submit)
    controls._async=True
    controls.apply.active=True
    assert controls.result is None and len(futures)==1
    controls.threshold.value=.4
    assert len(futures)==1
    first=futures[0]
    select(app.primary,app.primary.observations[1].id)
    first[0].set_result(first[1]())
    for callback in list(app.doc.session_callbacks):
        if type(callback).__name__=='NextTickCallback': callback.callback()
    assert controls.result is None
    controls.close()
    assert not controls._cache and controls._closed


def test_legacy_controls_use_same_estimator_and_keep_solutions(legacy_app,app):
    '''
    Purpose
    -------
    Verify legacy controls use same estimator and keep solutions.

    Inputs
    ------
    legacy_app: object
        Legacy explorer fixture used for estimator and solution comparisons.

    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    controls=legacy_app.coherence
    controls.loader=lambda: app.primary.data
    model=calculate_legacy(legacy_app,0)
    model.mask_warnings.active=[]
    original=model.last_result
    controls.apply.active=True
    assert controls.result is not None,controls.status.text
    legacy_app.apply_filter.active=True
    assert model.last_result is original
    np.testing.assert_array_equal(model.image_source.data['image'][0],original.phase_deg[:,:,0]*model.transmission)
    controls.apply.active=False
    np.testing.assert_array_equal(model.image_source.data['image'][0],original.phase_deg[:,:,0]*model.transmission)


def test_phase_only_product_does_not_fake_coherence(app):
    '''
    Purpose
    -------
    Verify phase only product does not fake coherence.

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

    app.primary.data.dopplergrams=None
    controls=app.model_workspace.coherence
    controls.apply.active=True
    calculate(app)
    assert controls.result is None and 'unavailable' in controls.status.text
    assert not np.any(app.model.filtered.coherence_weight)
    assert app.save_plot('filtered') is None


def test_export_retains_physical_arrays_opacity_and_coherence_provenance(app):
    '''
    Purpose
    -------
    Verify export retains physical arrays opacity and coherence provenance.

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

    controls=app.model_workspace.coherence
    controls.apply.active=True
    controls.threshold.value=.35
    calculate(app)
    paths=app.save_plot('filtered')
    assert paths is not None,app.export_status.text
    html=next(path for path in paths if path.suffix=='.html').read_text()
    metadata=next(path for path in paths if path.suffix=='.txt').read_text()
    assert 'ImageRGBA' in html and 'coherence_overlay' in html
    assert 'annular_and_frequency_averaged_magnitude_squared_coherence' in metadata
    assert '"threshold": 0.35' in metadata
    np.testing.assert_array_equal(app.model.filtered_result.phase_deg,app.model.last_result.phase_deg*app.model.transmission[...,None])


def test_repeated_toggles_render_exactly_one_image_and_preserve_weighted_colors(app):
    '''
    Purpose
    -------
    Verify repeated toggles render exactly one image and preserve weighted colors.

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

    calculate(app)
    controls=app.model_workspace.coherence
    model=app.model.filtered
    with patch.object(ui,'coherence_for_data',wraps=ui.coherence_for_data) as estimator:
        for _ in range(12):
            controls.apply.active=True
            assert all(not renderer.visible for renderer in model.image_renderers)
            assert all(renderer.visible for renderer in model._coherence_overlays)
            for branch,(renderer,source) in enumerate(zip(model._coherence_overlays,model.image_sources)):
                rgba=renderer.data_source.data['image'][0]
                np.testing.assert_array_equal(rgba >> 24,
                    np.rint(model.coherence_visibility*255).astype(np.uint32))
                visible=(rgba >> 24)>0
                if visible.any():
                    # The weighted renderer contains model colors, not a white
                    # covering image whose draw order can expose the wrong field.
                    assert np.any((rgba[visible] & 0xffffff) != 0xffffff)
                values=source.data['image'][0]
                finite=np.isfinite(values)
                np.testing.assert_array_equal(values[finite],
                    (app.model.last_result.phase_deg[:,:,branch]*app.model.transmission)[finite])
            controls.apply.active=False
            assert all(not renderer.visible for renderer in model.image_renderers)
            assert all(renderer.visible for renderer in model._coherence_overlays)
        assert estimator.call_count == 1
    controls.apply.active=True
    app.model.widgets['cs'].value += .1
    assert app.model.filtered_result is None
    assert all(not renderer.visible for renderer in model._coherence_overlays)
    calculate(app)
    assert all(renderer.visible for renderer in model._coherence_overlays)
    assert all(not renderer.visible for renderer in model.image_renderers)


def test_pending_coherence_completion_obeys_latest_toggle_state(app,monkeypatch):
    '''
    Purpose
    -------
    Verify pending coherence completion obeys latest toggle state.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    controls=app.model_workspace.coherence
    calculate(app)
    pending=Future();pending.set_running_or_notify_cancel()
    work=[]
    def submit(callback):
        '''
        Purpose
        -------
        Record deferred worker work and return the controlled Future used by the test.

        Inputs
        ------
        callback: object
            Scheduled callback or worker callable exercised by the helper.

        Outputs
        -------
        future: concurrent.futures.Future
            Future retained by the enclosing fixture; the test decides when the
            recorded callable runs or when the Future is completed.
        '''

        work.append(callback)
        return pending
    monkeypatch.setattr(ui.COHERENCE_POOL,'submit',submit)
    controls._async=True
    for _ in range(8):
        controls.apply.active=True
        controls.apply.active=False
    assert len(work)==1
    pending.set_result(work[0]())
    # Run only the coherence completion callback, not unrelated model/load work.
    for callback in list(app.doc.session_callbacks):
        if type(callback).__name__=='NextTickCallback':
            callback.callback()
    assert controls.result is not None and not controls.apply.active
    assert all(not renderer.visible for renderer in app.model.filtered.image_renderers)
    assert all(renderer.visible for renderer in app.model.filtered._coherence_overlays)
    controls.apply.active=True
    assert len(work)==1
    assert all(renderer.visible for renderer in app.model.filtered._coherence_overlays)
