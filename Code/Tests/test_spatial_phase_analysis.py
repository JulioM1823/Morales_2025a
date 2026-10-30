'''
Purpose
-------
Notebook equivalence, magnetic registration and the embedded live workflow.

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
from concurrent.futures import Future
import copy
import json
import sys

import numpy as np
import pytest
from bokeh.document import Document
from bokeh.models import ColorBar, Legend

TD=Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0,str(TD))
import spatial_phase_analysis as science
import spatial_phase_explorer as spatial_ui
import pipeline
from test_integrated_komega_explorer import app,run_scheduled,select
from test_magnetogram_workflow import simulation,process
from observation_datasets import load_observation,Observation
from processing_results import load_processing_observation,result_observation


@pytest.mark.parametrize('nt',[256,257])
def test_exact_existing_notebook_calculation(nt):
    '''
    Purpose
    -------
    Verify exact existing notebook calculation.

    Inputs
    ------
    nt: int or None
        Number of temporal samples in the synthetic cube.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    rng=np.random.default_rng(51)
    vz=rng.normal(size=(nt,3,7,9))
    cells=json.loads((TD/'vorticity.ipynb').read_text())['cells']
    source=''.join(cells[5]['source']).split('# Band-averaged magnitude-squared coherence')[0]
    namespace=dict(vz=vz)
    exec(compile(source,'vorticity.ipynb cell 5','exec'),namespace)
    spectrum=science.TemporalCrossSpectrum((vz[:,1],vz[:,2]),30.)
    actual,metadata=spectrum.band((.7,3.1))
    np.testing.assert_allclose(actual,namespace['phase_diff_map'],rtol=1e-12,atol=2e-12)
    np.testing.assert_array_equal(spectrum.frequency_mhz,namespace['freq_mHz'])
    assert metadata['bin_count']==np.count_nonzero(namespace['band'])
    # Full-band reference uses every strictly positive bin, not the selected band.
    full,_=spectrum.band(spectrum.full_band)
    expected=np.angle(namespace['cross_power'].mean(axis=0),deg=True)
    np.testing.assert_allclose(full,expected,atol=2e-12)


def test_known_phase_sign_complex_average_and_delay():
    '''
    Purpose
    -------
    Verify known phase sign complex average and delay.

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

    nt=256;dt=30.;n=12;t=np.arange(nt)
    phase=np.array([[-170.,-40.,30.],[100.,170.,-90.]])
    first=np.broadcast_to(np.cos(2*np.pi*n*t/nt)[:,None,None],(nt,2,3))
    second=np.cos(2*np.pi*n*t[:,None,None]/nt+np.deg2rad(phase)[None,:,:])
    frequency=1000*n/(nt*dt)
    spectrum=science.TemporalCrossSpectrum((first,second),dt)
    actual,_=spectrum.band((frequency,frequency))
    np.testing.assert_allclose(actual,-phase,atol=1e-12)
    delay=3.26
    corrected=science.TemporalCrossSpectrum((first,second),dt,phase_delay_seconds=delay)
    actual,_=corrected.band((frequency,frequency))
    expected=np.angle(np.exp(1j*np.deg2rad(-phase))*np.exp(2j*np.pi*frequency*1e-3*delay),deg=True)
    np.testing.assert_allclose(actual,expected,atol=1e-12)
    # These operations cannot be exchanged: the mean vector has phase 180°.
    assert abs(np.angle(np.mean(np.exp(1j*np.deg2rad([170.,-170.]))),deg=True))==180.
    assert np.mean([170.,-170.])==0.


def test_band_updates_reuse_fft_and_reject_unsupported_bins(monkeypatch):
    '''
    Purpose
    -------
    Verify band updates reuse FFT and reject unsupported bins.

    Inputs
    ------
    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    rng=np.random.default_rng(4)
    cubes=tuple(rng.normal(size=(256,6,8)) for _ in range(2))
    cache=science.TemporalCrossSpectrum(cubes,30.)
    monkeypatch.setattr(np.fft,'rfft',lambda *a,**k:pytest.fail('Repeated FFT'))
    a,_=cache.band((.7,3.1));b,_=cache.band((1.,2.))
    assert not np.allclose(a,b)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='no temporal FFT bins'):cache.band((.701,.702))
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='inside'):cache.band((-1.,2.))
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='inside'):cache.band((2.,1.))
    assert len(cache.frequency_mhz)==127  # even-N Nyquist is negative in fftfreq


def test_invalid_cubes_and_zero_field():
    '''
    Purpose
    -------
    Verify invalid cubes and zero field.

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

    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='matching'):science.TemporalCrossSpectrum((np.zeros((4,3,3)),np.zeros((5,3,3))),30.)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='finite real'):science.TemporalCrossSpectrum((np.full((4,3,3),np.nan),)*2,30.)
    bh,theta=science.magnetic_geometry(np.zeros((2,2)),np.zeros((2,2)),np.zeros((2,2)))
    assert np.isnan(theta).all()
    assert not science.magnetic_selection(bh,theta,0.,0.).any()


def test_vector_geometry_polarity_and_logical_intersection():
    '''
    Purpose
    -------
    Verify vector geometry polarity and logical intersection.

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

    bx=np.array([[6.,6.,12.],[0.,20.,np.nan]])
    by=np.array([[8.,8.,0.],[0.,0.,0.]])
    bz=np.array([[10.,-10.,30.],[100.,0.,0.]])
    bh,theta=science.magnetic_geometry(bx,by,bz)
    np.testing.assert_allclose(bh[0],[10.,10.,12.])
    np.testing.assert_allclose(theta[0],np.degrees(np.arctan2(bh[0],abs(bz[0]))))
    mask=science.magnetic_selection(bh,theta,10.,45.)
    np.testing.assert_array_equal(mask,[[True,True,False],[False,True,False]])
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError):science.magnetic_selection(bh,theta,-1.,45.)


def test_contours_close_on_native_pixel_edges():
    '''
    Purpose
    -------
    Verify contours close on native pixel edges.

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

    x=np.arange(5.)*.2;y=np.arange(3.)*.4
    paths=science.contour_lines(np.ones((3,5),bool),x,y)
    assert len(paths['xs'])==1
    np.testing.assert_allclose([min(paths['xs'][0]),max(paths['xs'][0]),min(paths['ys'][0]),max(paths['ys'][0])],[-.1,.9,-.2,1.])
    assert science.contour_lines(np.zeros((3,5),bool),x,y)==dict(xs=[],ys=[])


def test_regional_contours_merge_small_islands_without_changing_selection():
    '''
    Purpose
    -------
    Verify regional contours merge small islands without changing selection.

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

    x=np.arange(90)*.16;y=x.copy()
    mask=np.zeros((90,90),bool)
    mask[15:32,15:32]=True;mask[32:49,34:51]=True;mask[75,75]=True
    original=mask.copy()
    raw=science.contour_lines(mask,x,y)
    regional=science.contour_lines(mask,x,y,sigma_mm=.8)
    assert len(raw['xs'])==3
    assert len(regional['xs'])==1
    np.testing.assert_array_equal(mask,original)
    for xs,ys in zip(regional['xs'],regional['ys']):
        assert min(xs)>=x[0]-.08 and max(xs)<=x[-1]+.08
        assert min(ys)>=y[0]-.08 and max(ys)<=y[-1]+.08


def test_regional_contour_smoothing_uses_both_native_spatial_scales():
    '''
    Purpose
    -------
    Verify regional contour smoothing uses both native spatial scales.

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

    from scipy.ndimage import gaussian_filter
    x=np.arange(60)*.2;y=np.arange(30)*.4
    mask=np.zeros((30,60),bool);mask[10:20,20:40]=True
    actual=science.regional_magnetic_coverage(mask,x,y,.8)
    np.testing.assert_array_equal(actual,gaussian_filter(mask.astype(float),sigma=(2.,4.),mode='nearest'))
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='nonnegative'):
        science.regional_magnetic_coverage(mask,x,y,-.1)


@pytest.mark.parametrize('reversed_heights',[False,True])
def test_spatial_phase_sign_matches_native_komega(simulation,tmp_path,reversed_heights):
    '''
    Purpose
    -------
    Verify spatial phase sign matches native k-omega.

    Inputs
    ------
    simulation: tuple
        Synthetic simulation dataset, velocity cube, and magnetic-field fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    reversed_heights: bool
        Whether the test reverses the input height order.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset,_,_=simulation
    _,cfg,_=process(dataset,tmp_path/'cache')
    cfg=copy.deepcopy(cfg)
    if reversed_heights:
        cfg['data']['resolved_h1_km'],cfg['data']['resolved_h2_km']=200.,0.
    nt=256;j=12;phase=37.
    # Populate the nonzero spatial annuli retained by the native diagnostic.
    amplitude=1.+np.random.default_rng(17).uniform(size=(8,8))
    first=np.cos(2*np.pi*j*np.arange(nt)/nt)[:,None,None]*amplitude
    second=np.cos(2*np.pi*j*np.arange(nt)/nt+np.deg2rad(phase))[:,None,None]*amplitude
    native,_,_,_=pipeline.TimeDistance(cfg).compute_komega_diagram(first,second)
    frequency=1000*j/(nt*cfg['time_distance']['dt'])
    spatial,_=science.ordered_spectrum((first,second),cfg).band((frequency,frequency))
    expected=phase if reversed_heights else -phase
    np.testing.assert_allclose(spatial,expected,atol=1e-12)
    np.testing.assert_allclose(spatial,native[0,j],atol=1e-12)


def test_frequency_filter_and_threshold_updates_preserve_raw_reference(app,monkeypatch):
    '''
    Purpose
    -------
    Verify frequency filter and threshold updates preserve raw reference.

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

    app.spatial.sync();view=app.spatial
    assert view.inputs is not None,view.status.text
    assert view.filtered is not None,view.status.text
    assert app.spatial.layout.visible and app.komega_view.visible
    left=view.sources[0].data['image'][0].copy()
    right=view.sources[1].data['image'][0].copy()
    frequencies=view.filtered.frequency_mhz
    with monkeypatch.context() as m:
        m.setattr(np.fft,'rfft',lambda *a,**k:pytest.fail('Repeated temporal FFT'))
        view.frequency.value=(float(frequencies[2]),float(frequencies[4]))
        view.strength.value=20.;view.inclination.value=60.
    np.testing.assert_array_equal(view.sources[0].data['image'][0],left)
    assert not np.allclose(view.sources[1].data['image'][0],right)
    assert view.strength.disabled and 'LOS' in view.magnetic_info.text
    old_filtered=view.filtered
    view.section.plot_toggle.active=False;view.section.toggle.active=False
    app.primary.filter.sliders['width_f'].value=2.1
    run_scheduled(app.doc,app.primary.filter._scheduled_callback)
    app.spatial.sync()
    assert view.filtered is not old_filtered
    assert '2.1' in view.filter_info.text
    np.testing.assert_array_equal(view.sources[0].data['image'][0],left)
    expected=science.ordered_spectrum(app.primary.filtered_dopplergrams,app.primary.data.analysis_config)
    result,_=expected.band(view.frequency.value)
    np.testing.assert_array_equal(result,view.sources[1].data['image'][0])
    assert view.mapper.low==app.primary.mapper.low==-80.
    assert view.mapper.high==app.primary.mapper.high==80.
    assert view.mapper.palette==app.primary.mapper.palette
    for plot in view.plots:
        assert plot.title.text_font=='Times New Roman'
        for axis in (plot.xaxis[0],plot.yaxis[0]):
            assert axis.axis_label_text_font=='Times New Roman'
            assert axis.axis_label_text_font_size=='16pt'
            assert (axis.major_tick_in,axis.major_tick_out)==(8,0)
        bar=list(plot.select(type=ColorBar))[0]
        assert bar.title_text_font=='Times New Roman'
    assert view.plots[0].x_range is view.plots[1].x_range
    assert all(not list(p.select(type=Legend)) for p in view.plots)
    assert all(p.frame_width==p.frame_height for p in view.plots)
    saved=view.save_plots()
    assert saved is not None,view.export_status.text
    assert saved[-1].suffix=='.npz'
    with np.load(saved[-1],allow_pickle=False) as numerical:
        np.testing.assert_array_equal(numerical['phase'],result)
        np.testing.assert_array_equal(numerical['x_km'],view.inputs.x*1000.)
        np.testing.assert_array_equal(numerical['y_km'],view.inputs.y*1000.)
    assert 'observations/doppler_velocity/Annulus' in saved[-1].as_posix()


def test_source_switch_replaces_spatial_inputs(app):
    '''
    Purpose
    -------
    Verify source switch replaces spatial inputs.

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

    app.spatial.sync();view=app.spatial;original=view.inputs
    identity=app.primary.observations[1].id
    select(app.primary,identity)
    assert view.inputs is not original
    assert view.inputs.metadata['dataset_id']==identity
    assert view.filtered.shape==app.primary.data.dopplergrams[0].shape[1:]


def test_visible_gaussian_updates_and_disabled_filter_state(app):
    '''
    Purpose
    -------
    Verify visible gaussian updates and disabled filter state.

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

    app.spatial.sync();view=app.spatial
    left=view.sources[0].data['image'][0].copy()
    app.primary.filter.sliders['width_f'].value=2.3
    assert view.filtered is None
    run_scheduled(app.doc,app.primary.filter._scheduled_callback)
    assert view.filtered is not None
    np.testing.assert_array_equal(view.sources[0].data['image'][0],left)
    app.primary.apply_filter.active=False
    view.sync()
    assert 'disabled' in view.filter_info.text
    expected=science.ordered_spectrum(app.primary.data.dopplergrams,app.primary.data.analysis_config)
    np.testing.assert_array_equal(expected.band(view.frequency.value)[0],view.sources[1].data['image'][0])


def test_single_frequency_and_descending_native_axes():
    '''
    Purpose
    -------
    Verify single frequency and descending native axes.

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

    cache=science.TemporalCrossSpectrum((np.arange(12.).reshape(3,2,2),)*2,30.)
    assert cache.band(cache.full_band)[1]['bin_count']==1
    np.testing.assert_array_equal(science._regular_axis([.4,.2,0.]),[.4,.2,0.])
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='regular'):science._regular_axis([0.,.2,.5])


def test_inclusive_frequency_edges_tolerate_slider_roundoff():
    '''
    Purpose
    -------
    Verify inclusive frequency edges tolerate slider roundoff.

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

    rng=np.random.default_rng(12)
    cache=science.TemporalCrossSpectrum(tuple(rng.normal(size=(482,4,6)) for _ in range(2)),30.)
    lo,hi=cache.frequency_mhz[[12,39]]
    exact,metadata=cache.band((lo,hi))
    nudged,actual=cache.band((np.nextafter(lo,np.inf),np.nextafter(hi,-np.inf)))
    np.testing.assert_array_equal(exact,nudged)
    assert metadata['effective_mhz']==actual['effective_mhz']
    assert metadata['bin_count']==actual['bin_count']==28


def test_simulation_snapshot_units_axes_height_and_raw_reference(simulation,tmp_path):
    '''
    Purpose
    -------
    Verify simulation snapshot units axes height and raw reference.

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

    import netCDF4
    dataset,raw,magnetic=simulation
    with netCDF4.Dataset(dataset.files[0],'a') as f:
        f['bb3'].units='G'
        for name,value,unit in [('bb1',6.,'G'),('bb2',.0008,'T')]:
            v=f.createVariable(name,'f8',('xc1','xc3','time','xc2'));v.units=unit
            v[:]=value
    prepared,cfg,result=process(dataset,tmp_path/'cache')
    observation=result_observation(result.id,tmp_path/'cache')
    data=load_processing_observation(observation)
    inputs=science.prepare_inputs(data)
    bh,theta=inputs.magnetic
    np.testing.assert_allclose(bh,10.)
    np.testing.assert_allclose(theta,np.degrees(np.arctan2(10.,abs(magnetic[0,0]))))
    assert inputs.metadata['magnetic']['height_index']==0
    assert inputs.metadata['magnetic']['frame_index']==0
    np.testing.assert_array_equal(inputs.x,np.arange(8)*.16)
    expected=science.ordered_spectrum((raw[:,0],raw[:,2]),cfg)
    np.testing.assert_array_equal(inputs.reference.band(inputs.reference.full_band)[0],expected.band(expected.full_band)[0])
    # This is a genuinely raw reference, not the supplied spatially masked pair.
    masked=science.ordered_spectrum(data.dopplergrams,cfg)
    assert not np.allclose(inputs.reference.band(inputs.reference.full_band)[0],masked.band(masked.full_band)[0])


def test_stale_spatial_worker_completion_is_ignored(app,monkeypatch):
    '''
    Purpose
    -------
    Verify stale spatial worker completion is ignored.

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

    app.spatial.sync();view=app.spatial
    old=view.sources[1].data['image'][0].copy()
    pending=[]
    class Pool:
        '''
        Purpose
        -------
        Retain submitted work for manual completion in the stale-worker regression.

        Inputs
        ------
        None
            Constructed by the test framework or its enclosing fixture.

        Outputs
        -------
        instance: Pool
            Fixture or test-suite object providing the documented methods.
        '''

        def submit(self,fn):
            '''
            Purpose
            -------
            Record deferred worker work and return the controlled Future used by the
            test.

            Inputs
            ------
            fn: callable
                Deferred worker callable recorded by the test executor.

            Outputs
            -------
            future: concurrent.futures.Future
                Future retained by the enclosing fixture; the test decides when the
                recorded callable runs or when the Future is completed.
            '''

            future=Future();future.set_running_or_notify_cancel();pending.append((future,fn));return future
    monkeypatch.setattr(spatial_ui,'SPATIAL_POOL',Pool())
    monkeypatch.setattr(type(view.doc),'session_context',property(lambda self:object()))
    view._work('filter',lambda:'old',lambda result:view._message(result))
    view._work('filter',lambda:'current',lambda result:view._message(result))
    pending[1][0].set_result('current')
    for callback in list(view.doc.session_callbacks):
        if type(callback).__name__=='NextTickCallback':callback.callback()
    pending[0][0].set_result('old')
    for callback in list(view.doc.session_callbacks):
        if type(callback).__name__=='NextTickCallback':callback.callback()
    assert 'current' in view.status.text
    np.testing.assert_array_equal(view.sources[1].data['image'][0],old)
