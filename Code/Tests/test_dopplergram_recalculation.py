'''
Purpose
-------
Independent Fourier reconstruction and native-pipeline numerical checks.

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
from concurrent.futures import Future

import numpy as np
import pytest
from astropy.io import fits
from bokeh.document import Document

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0,str(TD))
import pipeline,config
import dopplergram_recalculation as workflow
import observation_komega_explorer as ui
from observation_datasets import Observation,load_observation
from test_magnetogram_workflow import observational,simulation,process

PARAMETERS = dict(central_k=1.5,width_k=4.,central_f=1.5,width_f=3.)


def numerical_product(path,shape,offset=0,nt=None,source_type='paired_cubes',dt=11.88,dx=.43):
    '''
    Purpose
    -------
    A real source pair and its saved native phase, rather than arbitrary degrees.

    Inputs
    ------
    path: pathlib.Path
        Input or output path used by this fixture or its local substitute.

    shape: tuple of int
        Requested numerical-product or cube dimensions in the current fixture.

    offset: float
        Offset or seed adjustment distinguishing synthetic products.

    nt: int or None
        Number of temporal samples in the synthetic cube.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    dt: float
        Temporal cadence in seconds.

    dx: float
        Spatial sampling in Mm per pixel.

    Outputs
    -------
    fixture: tuple
        Prepared runtime configuration, generated source cubes, and native
        phase reference values. Write FITS/netCDF sources and recorded metadata.
    '''
    # Generate reproducible source cubes and record the native product inputs.
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    nt=nt or shape[1]*2
    rng=np.random.default_rng(13+int(offset))
    cubes=[rng.normal(size=(nt,shape[0]*2,shape[0]*2)) for _ in range(2)]
    root=path.parent/'source_cubes';root.mkdir(exist_ok=True)
    sources=[root/(path.stem.replace('_komega','')+f'_v{i}.fits') for i in (1,2)]
    for source,cube in zip(sources,cubes):fits.writeto(source,cube,overwrite=True)
    if source_type=='single_cube':
        import netCDF4
        source=root/('simulation_hx_10G_'+path.stem.replace('_komega','')+'.nc')
        with netCDF4.Dataset(source,'w') as f:
            for name,count,step,unit in [('time',nt,dt,'s'),('xc3',2,200.,'km'),('xc2',shape[0]*2,dx,'Mm'),('xc1',shape[0]*2,dx,'Mm')]:
                f.createDimension(name,count);v=f.createVariable(name,'f8',(name,));v.units=unit;v[:]=np.arange(count)*step
            v=f.createVariable('v3','f8',('time','xc3','xc2','xc1'));v.units='cm/s';v[:]=np.stack(cubes,axis=1)
        cfg=config.get_config(optimized_filtering={'mode':'manual'}, source_type='single_cube',file_path=str(source),observable='v3',h1=0,h2=1)
    else:
        cfg=config.get_config(optimized_filtering={'mode':'manual'}, source_type='paired_cubes',v1_path=str(sources[0]),v2_path=str(sources[1]),
            dt=dt,p_dx_Mm=dx,delta_z_km=100.)
    cfg['_module_dir']=str(TD);cfg['filtering']['enabled']=False
    cfg['atmospheric_profiles']['enabled']=False
    cfg=pipeline.prepare_runtime_config(cfg)
    values,kh,nu,_=pipeline.TimeDistance(cfg).compute_komega_diagram(*cubes)
    header=fits.Header(dict(SRCMODE=source_type,BUNIT='deg',CTYPE1='KH',CTYPE2='NU',
        CUNIT1='1/Mm',CUNIT2='mHz',CRVAL1=kh[0],CDELT1=kh[1]-kh[0],CRVAL2=nu[0],CDELT2=nu[1]-nu[0],
        DT_S=dt,DX_MM=dx,NX_ORIG=cubes[0].shape[2],NY_ORIG=cubes[0].shape[1],NT_ORIG=nt))
    fits.writeto(path,values,header,overwrite=True)
    workflow.write_input_reference(path,cfg)
    return cfg,cubes,values


@pytest.mark.parametrize('shape',[(24,8,8),(25,9,9),(37,12,10)])
def test_identity_filter_and_independent_inverse_fft(shape,tmp_path):
    '''
    Purpose
    -------
    Verify identity filter and independent inverse FFT.

    Inputs
    ------
    shape: tuple of int
        Requested numerical-product or cube dimensions in the current fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    F=pipeline.load_agw_filter_class(TD/'config.py')
    helpers=F.build_gaussian_filter.__globals__
    rng=np.random.default_rng(8);cube=rng.normal(size=shape);xyt=cube.transpose(2,1,0)
    identity=helpers['filter_data'](np.ones(xyt.shape),xyt)
    np.testing.assert_array_equal(identity.real,xyt)
    assert not np.any(identity.imag)
    _,kx,ky,nu=helpers['make_fourier_grid'](30.,.16,xyt,True)
    transfer=helpers['create_filter'](xyt,nu,kx,ky,1.5,3.,1.5,4.)
    actual=helpers['filter_data'](transfer,xyt)
    unshifted=np.fft.ifftshift(transfer)
    opposite=np.ix_(*[(-np.arange(n))%n for n in xyt.shape])
    np.testing.assert_array_equal(unshifted,unshifted[opposite])
    independent=np.fft.ifftn(np.fft.fftn(xyt)*unshifted)
    np.testing.assert_allclose(actual,independent,rtol=1e-12,atol=1e-14)
    assert np.max(abs(actual.imag))<1e-13
    assert actual.shape==xyt.shape


def test_significant_imaginary_and_nonfinite_inputs_are_rejected():
    '''
    Purpose
    -------
    Verify significant imaginary and nonfinite inputs are rejected.

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

    F=pipeline.load_agw_filter_class(TD/'config.py');helpers=F.build_gaussian_filter.__globals__
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='imaginary residual'):
        helpers['checked_real_cube'](np.ones((3,4,5))+1j*.01)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='finite Dopplergrams'):
        helpers['filter_data'](np.ones((3,4,5)),np.full((3,4,5),np.nan))


@pytest.mark.parametrize('fixture',['observational','simulation'])
def test_magnetic_gaussian_combination_matches_original_pipeline(request,fixture,tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify magnetic gaussian combination matches original pipeline.

    Inputs
    ------
    request: pytest.FixtureRequest or object
        Pytest request fixture or captured plotting request, as used by this test.

    fixture: object
        Parameterized fixture selected through pytest for the current case.

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

    dataset,_,_=request.getfixturevalue(fixture)
    prepared,cfg,magnetic=process(dataset,tmp_path/'cache')
    cfg=copy.deepcopy(cfg);cfg['paths']['project_dir']=str(tmp_path)
    cfg['atmospheric_profiles']['enabled']=False
    original=tuple(magnetic.arrays[key] for key in ('dopplergram_v1','dopplergram_v2'))
    reference=pipeline.TimeDistance(cfg).compute_komega_diagram(*original)
    none=workflow.recalculate(original,cfg)
    np.testing.assert_array_equal(none[0],reference[0])
    F=pipeline.load_agw_filter_class(TD/'config.py')
    expected_cfg=copy.deepcopy(cfg);expected_cfg['filtering']['gaussian'].update(PARAMETERS)
    expected_cubes=F(expected_cfg).apply_gaussian_filter(*original)
    expected=pipeline.TimeDistance(expected_cfg).compute_komega_diagram(*expected_cubes)
    actual=workflow.recalculate(original,cfg,PARAMETERS)
    for first,second in zip(actual[:3],expected[:3]):np.testing.assert_array_equal(first,second)
    for first,second in zip(actual[4],expected_cubes):np.testing.assert_array_equal(first,second)
    changed=workflow.recalculate(original,cfg,dict(PARAMETERS,width_f=2.))
    repeated=workflow.recalculate(original,cfg,PARAMETERS)
    np.testing.assert_array_equal(repeated[0],actual[0])
    assert not np.allclose(changed[4][0],actual[4][0])
    assert actual[3]['phase_delay_seconds']==reference[3]['phase_delay_seconds']
    assert original[0].shape==actual[4][0].shape
    # Explicit identity through the public pair filtering/recalculation API.
    monkeypatch.setattr(F,'build_gaussian_filter',lambda self,cube:np.ones(cube.transpose(2,1,0).shape))
    monkeypatch.setattr(pipeline,'load_agw_filter_class',lambda _:F)
    identity=workflow.recalculate(original,cfg,PARAMETERS)
    np.testing.assert_array_equal(identity[0],reference[0])


def test_bokeh_uses_cubes_and_never_weights_phase(tmp_path):
    '''
    Purpose
    -------
    Verify Bokeh uses cubes and never weights phase.

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

    path=tmp_path/'observations/test_komega.fits'
    cfg,cubes,values=numerical_product(path,(8,18),nt=36)
    app=ui.build_document(Document(),product_roots=[tmp_path],raw_roots=[],registry_file=tmp_path/'registry.json',schedule_initial=False)
    assert app.data.dopplergrams is not None,app.status.text
    app.apply_filter.active=True
    expected=workflow.recalculate(app.data.dopplergrams,app.data.analysis_config,app.filter._current_parameters())
    np.testing.assert_array_equal(app.result_source.data['image'][0],expected[0].T)
    assert not np.allclose(expected[0].T,values.T*app.transmission)
    app.apply_filter.active=False
    np.testing.assert_array_equal(app.result_source.data['image'][0],values.T)


@pytest.mark.parametrize('fixture',['observational','simulation'])
def test_explicit_reverse_filter_sequence_is_preserved(request,fixture,tmp_path):
    '''
    Purpose
    -------
    Verify explicit reverse filter sequence is preserved.

    Inputs
    ------
    request: pytest.FixtureRequest or object
        Pytest request fixture or captured plotting request, as used by this test.

    fixture: object
        Parameterized fixture selected through pytest for the current case.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    dataset,_,_=request.getfixturevalue(fixture)
    prepared,cfg,magnetic=process(dataset,tmp_path/'cache')
    cfg=copy.deepcopy(cfg);cfg['paths']['project_dir']=str(tmp_path)
    cfg['atmospheric_profiles']['enabled']=False
    cfg['filtering'].update(enabled=True,filter_sequence=['gaussian','magnetogram'])
    cfg['filtering']['gaussian'].update(PARAMETERS,enabled=True)
    cfg['filtering']['magnetogram'].update(magnetic.manifest['identity']['parameters'],enabled=True)
    raw=tuple(prepared.arrays[key] for key in ('original_v1','original_v2'))
    masked=tuple(magnetic.arrays[key] for key in ('dopplergram_v1','dopplergram_v2'))
    F=pipeline.load_agw_filter_class(TD/'config.py')
    expected_cubes=F(cfg).apply_filters(*raw)
    expected=pipeline.TimeDistance(cfg).compute_komega_diagram(*expected_cubes)
    actual=workflow.recalculate(masked,cfg,PARAMETERS,raw_cubes=raw)
    np.testing.assert_array_equal(actual[0],expected[0])
    for a,b in zip(actual[4],expected_cubes):np.testing.assert_array_equal(a,b)
    forward=workflow.recalculate(masked,cfg,PARAMETERS)
    assert not np.allclose(actual[4][0],forward[4][0])


def test_phase_only_product_remains_viewable_but_is_not_falsely_filtered(tmp_path):
    '''
    Purpose
    -------
    Verify phase only product remains viewable but is not falsely filtered.

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

    path=tmp_path/'example_komega.fits'
    header=fits.Header(dict(SRCMODE='paired_cubes',DT_S=30.,DX_MM=.16))
    fits.writeto(path,np.zeros((4,6)),header)
    app=ui.build_document(Document(),product_roots=[tmp_path],raw_roots=[],registry_file=tmp_path/'registry.json',schedule_initial=False)
    assert app.data is not None
    app.apply_filter.active=True
    assert app.filtered_dopplergrams is None
    assert 'Cannot recalculate' in app.status.text


def test_old_async_completion_cannot_replace_newer_controls(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify old async completion cannot replace newer controls.

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

    numerical_product(tmp_path/'test_komega.fits',(6,12),nt=24)
    app=ui.build_document(Document(),product_roots=[tmp_path],raw_roots=[],registry_file=tmp_path/'registry.json',schedule_initial=False)
    app._async_recalculation=True
    pending=[]
    def submit(function):
        '''
        Purpose
        -------
        Record deferred worker work and return the controlled Future used by the test.

        Inputs
        ------
        function: callable
            Deferred worker callable recorded by the test executor.

        Outputs
        -------
        future: concurrent.futures.Future
            Future retained by the enclosing fixture; the test decides when the
            recorded callable runs or when the Future is completed.
        '''

        future=Future();future.set_running_or_notify_cancel();pending.append((future,function));return future
    monkeypatch.setattr(ui.RECALCULATION_POOL,'submit',submit)
    app.apply_filter.active=True
    first=app._recalculation_generation
    app.filter.sliders['width_f'].value=2.
    app.filter._perform_recompute()
    assert app._recalculation_generation>first
    older,function=pending[0];older.set_result(function())
    for callback in list(app.doc.session_callbacks):
        if type(callback).__name__=='NextTickCallback':callback.callback()
    assert app.filtered_dopplergrams is None
    newer,function=pending[-1];newer.set_result(function())
    for callback in list(app.doc.session_callbacks):
        if type(callback).__name__=='NextTickCallback':callback.callback()
    assert app.recalculation_metadata['recalculation']['gaussian_parameters']['width_f']==2.
