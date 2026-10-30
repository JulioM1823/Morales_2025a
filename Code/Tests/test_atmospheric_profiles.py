'''
Purpose
-------
Height integration, source identity/units, nonlinear inputs and Bokeh defaults.

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
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np
from astropy.io import fits
from bokeh.document import Document
import pytest
from scipy.integrate import simpson

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import atmospheric_profiles as ap
import config
import komega_bokeh_context as context
import komega_explorer
import integrated_komega_explorer as integrated
import observation_datasets


@pytest.mark.parametrize('bounds,expected', [((.5, 5.), 10.25), ((5., .5), 10.25), ((2., 2.), 8.)])
def test_exact_linear_integrals_nonuniform_grid_interpolated_reversed_and_zero(bounds, expected):
    '''
    Purpose
    -------
    Verify exact linear integrals nonuniform grid interpolated reversed and zero.

    Inputs
    ------
    bounds: tuple
        Integration endpoints used by the profile-averaging case.

    expected: object
        Reference value supplied by the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    z = np.array([0., .8, 2.1, 4., 7.])
    q = 3*z+2
    assert ap.interval_average(z, q, *bounds) == pytest.approx(expected)
    assert ap.interval_average(z[::-1], q[::-1], *bounds) == pytest.approx(expected)


def test_invalid_regions_are_not_bridged_or_extrapolated():
    '''
    Purpose
    -------
    Verify invalid regions are not bridged or extrapolated.

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

    for z, q, bounds in [([0, 1, 1], [1, 2, 3], (0, 1)),
                         ([0, 1, 2], [1, np.nan, 3], (.1, 1.8)),
                         ([0, 1, 2], [1, 2, 3], (-.1, 1))]:
        with pytest.raises(ap.ProfileError):
            ap.interval_average(z, q, *bounds)
    assert ap.interval_average([0, 1, 2, 3], [np.nan, 2, 3, 4], 2, 3) == 3.5


def test_alfven_units_components_and_independent_known_case():
    # 3–4–5 gauss, rho=1e-10 g/cm^3 -> B=5e-4 T, rho=1e-7 kg/m^3.
    '''
    Purpose
    -------
    Verify alfven units components and independent known case.

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

    expected = .0005/np.sqrt(4*np.pi*1e-7*1e-7)/1000
    assert ap.alfven_speed(3., 4., 0., 1e-10) == pytest.approx(expected)
    assert ap.alfven_speed(.0003, .0004, 0., 1e-7, magnetic_unit='T', density_unit='kg/m^3') == pytest.approx(expected)
    # Require the expected ap.ProfileError from this failure case.
    with pytest.raises(ap.ProfileError): ap.alfven_speed(3, 4, 0, 0)
    # Require the expected ap.ProfileError from this failure case.
    with pytest.raises(ap.ProfileError): ap.alfven_speed(3, 4, 0, 1, magnetic_unit='unknown')


@pytest.fixture
def atmosphere(tmp_path):
    '''
    Purpose
    -------
    Create synthetic cube and native atmospheric profiles on distinct height grids.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    fixture: tuple
        Runtime configuration and loaded profile object. Write the fixture files
        into tmp_path, with explicit native units and provenance.
    '''

    # Create separate cube and native-profile grids with explicit coordinate and field
    # units.
    cube_path, profile_path = tmp_path/'renamed.nc', tmp_path/'TEST_t00000020s_atmos_param.h5'
    z = np.array([0., 100., 300., 700.])
    with netCDF4.Dataset(cube_path, 'w') as f:
        f.Model = 'TEST'
        for name, length in [('time', 2), ('xc3', 4), ('xc2', 2), ('xc1', 2)]:
            f.createDimension(name, length)
        f.createVariable('time', 'f8', ('time',))[:] = [10, 20]
        v = f.createVariable('xc3', 'f8', ('xc3',)); v.units='cm'; v[:] = z*1e5
        v = f.createVariable('rho', 'f8', ('time', 'xc3')); v.units='gm/cm^3'
        v.cell_methods = 'xc1, xc2: mean'; v[:] = 1e-10*np.exp(-z/200.)
        for name, values in [('bb1', 3+z/100), ('bb2', z*0), ('bb3', z*0+4)]:
            v = f.createVariable(name, 'f8', ('time', 'xc3', 'xc2', 'xc1')); v.units='G'
            v[:] = np.broadcast_to(values[None, :, None, None], v.shape)
    fine = np.array([0., 50., 200., 400., 700.])
    with netCDF4.Dataset(profile_path, 'w') as f:
        f.createDimension('z', len(fine))
        v=f.createVariable('z', 'f8', ('z',)); v.units='cm'; v[:]=fine*1e5
        for name, values, units in [('sound_speed', (6+fine/1000)*1e5, 'cm/s'),
            ('brunt_vaisala_freq', .02+fine*1e-5, 'rad/s'),
            ('acoustic_cutoff_freq_isothermal', .025+fine*1e-5, 'rad/s'),
            ('acoustic_cutoff_freq_non_isothermal', .03+fine*1e-5, 'rad/s'),
            ('adiabatic_index', fine*0+1.4, 'dimensionless'),
            ('temperature', fine*0+6000, 'K')]:
            v=f.createVariable(name, 'f8', ('z',));v.units=units;v[:]=values
    cfg=copy.deepcopy(config.config)
    cfg['data'].update(file=str(cube_path), source_type='single_cube', h1=0, h2=2,
        resolved_h1_index=0, resolved_h2_index=2, resolved_h1_km=0., resolved_h2_km=300.)
    cfg['atmospheric_profiles'].update(directory=str(tmp_path), legacy_units={})
    cfg['paths']['figure_dir']=str(tmp_path/'figures')
    return cfg, ap.load_profiles(cfg)


def test_snapshot_identity_units_scale_height_and_nonlinear_averaging(atmosphere):
    '''
    Purpose
    -------
    Verify snapshot identity units scale height and nonlinear averaging.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, profiles = atmosphere
    result = profiles.parameters(50., 250.)
    assert profiles.provenance['cube_frame'] == 1
    assert result['parameters']['cs'] == pytest.approx(6.15)
    assert result['parameters']['H'] == pytest.approx(200.)
    fine = np.linspace(50., 250., 100001)
    z = profiles.cube_height_km
    bx, by, bz = [np.interp(fine, z, q) for q in profiles.components_G]
    rho = np.interp(fine, z, profiles.density_cgs)
    independent = np.sqrt((bx*1e-4)**2+(by*1e-4)**2+(bz*1e-4)**2)/np.sqrt(4*np.pi*1e-7*rho*1000.)/1000
    assert result['parameters']['a'] == pytest.approx(simpson(independent, x=fine)/200, rel=1e-9)
    separate_means = ap.alfven_speed(*[ap.interval_average(z, q, 50, 250) for q in
        (*profiles.components_G, profiles.density_cgs)])
    assert result['parameters']['a'] != pytest.approx(separate_means, rel=1e-3)
    assert profiles.parameters(250, 50)['parameters'] == result['parameters']
    assert profiles.parameters(100, 100)['parameters']['dz'] == 0
    assert set(result['unavailable']) == {'gamma', 'tau', 'g'}


def test_profile_figure_is_automatic_and_not_duplicated(atmosphere):
    '''
    Purpose
    -------
    Verify profile figure is automatic and not duplicated.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, profiles=atmosphere
    result=ap.resolve_parameters(cfg)
    assert result['status']=='available', result
    outputs=list(map(Path,result['diagnostic_figures']))
    assert {p.suffix for p in outputs}=={'.pdf','.png'}
    versions=[p.stat().st_mtime_ns for p in outputs]
    assert all(p.is_file() and p.stat().st_size>1000 for p in outputs)
    ap.resolve_parameters(cfg)
    assert [p.stat().st_mtime_ns for p in outputs]==versions


def test_inconsistent_sources_height_metadata_and_missing_units_are_disclosed(atmosphere):
    '''
    Purpose
    -------
    Verify inconsistent sources height metadata and missing units are disclosed.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, profiles=atmosphere
    cfg['data']['resolved_h2_km']=333.
    result=ap.resolve_parameters(cfg,make_figure=False)
    assert result['status']=='unavailable' and 'disagrees' in result['unavailable']['all']
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='Inconsistent atmospheric height'):
        context.with_atmosphere({},cfg,result)
    cfg['data']['resolved_h2_km']=300.
    with netCDF4.Dataset(cfg['data']['file'],'a') as f: f.Model='OTHER'
    result=ap.resolve_parameters(cfg,make_figure=False)
    assert result['status']=='unavailable' and 'OTHER' in result['unavailable']['all']


def _context(tmp_path, cfg, record, name):
    '''
    Purpose
    -------
    Write a synthetic k-omega FITS product and attach a validated atmospheric launch
    context.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    cfg: dict
        Synthetic runtime configuration associated with the atmospheric profiles.

    record: dict
        Atmospheric height-pair parameter record attached to the launch context.

    name: str
        Module, callback, variable, or context label selected by the caller.

    Outputs
    -------
    context: dict
        Launch context with atmospheric metadata; write its FITS product and
        profile sidecar beneath tmp_path.
    '''

    # Write the native phase axes, then attach and validate the recorded atmosphere.
    path=tmp_path/(name+'_komega.fits')
    header=fits.Header(dict(SRCMODE='single_cube',BUNIT='deg',DT_S=30.,DX_MM=.2,
        CTYPE1='KH',CTYPE2='NU',CUNIT1='1/Mm',CUNIT2='mHz',CRVAL1=0.,CDELT1=.5,
        CRVAL2=0.,CDELT2=.4,NX_ORIG=16,NY_ORIG=16,NT_ORIG=20))
    fits.writeto(path,np.zeros((8,10)),header)
    observation=observation_datasets.dataset_from_fits(path,'single_cube',context.PROJECT_DIR)
    value=dict(schema_version=1,dataset=dict(id=observation.id,file=str(path),source_type='single_cube'),
               model=dict(key='nc2009',parameters={},units={}))
    value=context.with_atmosphere(value,cfg,record)
    ap.write_sidecar(path,value['atmosphere'])
    context.validate_context(value)
    return value


def test_all_seven_models_initialize_reset_and_change_height_pair(tmp_path,atmosphere,monkeypatch):
    '''
    Purpose
    -------
    Verify all seven models initialize reset and change height pair.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, profiles=atmosphere
    first=_context(tmp_path,cfg,profiles.parameters(0,300),'first')
    second=_context(tmp_path,cfg,profiles.parameters(300,700),'second')
    def unavailable_raw_profiles(*args,**kwargs):
        '''
        Purpose
        -------
        Fail if a published launch context attempts to reload its raw atmospheric
        profiles.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        None
            Always raise AssertionError to expose the forbidden dependency.
        '''

        raise AssertionError('Published contexts must not require the raw profiles at launch.')
    monkeypatch.setattr(ap,'load_profiles',unavailable_raw_profiles)
    app=integrated.build_document(Document(),launch_context=first,product_roots=[tmp_path],raw_roots=[],
        registry_file=tmp_path/'registry.json',schedule_initial=False)
    assert len(app.model_workspace.models)==7
    for section in app.model_workspace.models:
        expected=first['atmosphere']['initializations'][section.definition.key]
        assert section._current_values()==expected
        assert dict(section.definition.defaults)==expected
    model=app.model
    monkeypatch.setitem(app.model_workspace.vesa.RESOLUTION_OPTIONS,'interactive',(8,10))
    model._perform_recompute()
    original=model.last_result.phase_deg.copy()
    model.widgets['cs'].value+=.3
    model._perform_recompute()
    assert not np.allclose(original,model.last_result.phase_deg,equal_nan=True)
    model._restore_defaults()
    assert model._current_values()==first['atmosphere']['initializations']['nc2009']
    identity=second['dataset']['id']
    app.primary.selector.value=[identity]
    app.primary._perform_load(identity)
    for section in app.model_workspace.models:
        assert section._current_values()==second['atmosphere']['initializations'][section.definition.key]
        section._restore_defaults()
        assert section._current_values()==second['atmosphere']['initializations'][section.definition.key]
    assert first['model']['parameters']['cs']!=second['model']['parameters']['cs']
    assert '300–700 km' in app.model_workspace.atmosphere_info.text
    assert 'gamma' in first['atmosphere']['fallbacks']['bunte1993']
    app.model._perform_recompute()
    assert 'atmospheric_initialization' in app.collect_metadata('unfiltered',[app.primary.observed_plot,app.model.plots[0]])


def test_context_rejects_stale_height_or_parameter_metadata(tmp_path,atmosphere):
    '''
    Purpose
    -------
    Verify context rejects stale height or parameter metadata.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg,profiles=atmosphere
    value=_context(tmp_path,cfg,profiles.parameters(0,300),'test')
    value['atmosphere']['height_pair_km']=[0,400]
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='separation'): context.validate_context(value)


def test_static_comparison_receives_the_same_seven_model_inputs(atmosphere):
    '''
    Purpose
    -------
    Verify static comparison receives the same seven model inputs.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import dispersion_comparison as dispersion
    cfg, profiles=atmosphere
    record=profiles.parameters(0,300)
    pair=dispersion.resolve_height_pair_context(cfg,{'atmospheric_parameters':record})
    # Non-derived static settings retain their existing project override;
    # interactive fallback values retain the existing Vesa UI defaults.
    assert pair['atmospheric_parameters']['initializations']['bunte1993']['tau'] == cfg['komega_comparison']['models']['bunte1993']['params']['tau']
    for spec in dispersion.MODEL_SPECS:
        values=pair['atmospheric_parameters']['initializations'][spec['model']]
        params=dispersion.resolve_model_parameters(cfg,spec['model'],pair)
        for key,value in values.items():
            assert params[{'theta_deg':'theta','phi_deg':'phi'}.get(key,key)] == pytest.approx(
                np.deg2rad(value) if key.endswith('_deg') else value)


def test_unitless_legacy_z_is_verified_from_native_cell_boundaries(atmosphere):
    '''
    Purpose
    -------
    Verify unitless legacy z is verified from native cell boundaries.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, profiles=atmosphere
    profile=Path(profiles.provenance['profile']['path'])
    with netCDF4.Dataset(profile,'a') as f: f['z'].delncattr('units')
    with netCDF4.Dataset(cfg['data']['file'],'a') as f:
        f.createDimension('xb3',5)
        v=f.createVariable('xb3','f8',('xb3',));v.units='cm';v[:]=np.array([0,75,275,550,750])*1e5
        f['xc3'][:]=np.array([25,200,400,700])*1e5
    loaded=ap.load_profiles(cfg)
    assert loaded.height_km[0] == pytest.approx(-25)
    with netCDF4.Dataset(profile,'a') as f: f['z'][:]=f['z'][:]/1000
    # Require the expected ap.ProfileError from this failure case.
    with pytest.raises(ap.ProfileError,match='vertical bin'):ap.load_profiles(cfg)


def test_pipeline_fft_is_unchanged_when_profile_metadata_is_enabled(atmosphere,monkeypatch):
    '''
    Purpose
    -------
    Verify pipeline FFT is unchanged when profile metadata is enabled.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import pipeline
    cfg,profiles=atmosphere
    cfg['data'].update(outfile='',phase_outfile='',komega_outfile='',coherence_outfile='')
    cfg['time_distance'].update(dt=10.,p_dx_Mm=.2)
    rng=np.random.default_rng(13)
    cubes=[rng.normal(size=(12,6,6)) for _ in range(2)]
    monkeypatch.setattr(ap,'save_diagnostic',lambda p,d:[])
    enabled=pipeline.TimeDistance(cfg).compute_komega_diagram(*cubes)
    disabled=copy.deepcopy(cfg);disabled['atmospheric_profiles']['enabled']=False
    reference=pipeline.TimeDistance(disabled).compute_komega_diagram(*cubes)
    for first,second in zip(enabled[:3],reference[:3]):np.testing.assert_array_equal(first,second)
    assert enabled[3]['atmospheric_parameters']['status']=='available'
    assert 'atmospheric_parameters' not in reference[3]
    interactive=copy.deepcopy(cfg);interactive['atmospheric_profiles']['make_figure']=False
    def unexpected_publication(*args):
        '''
        Purpose
        -------
        Fail if the interactive calculation attempts to publish diagnostic files.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        Outputs
        -------
        None
            Always fail the test through pytest.fail().
        '''

        pytest.fail('Interactive calculation attempted to publish diagnostic files')
    monkeypatch.setattr(ap,'save_diagnostic',unexpected_publication)
    result=pipeline.TimeDistance(interactive).compute_komega_diagram(*cubes)
    for first,second in zip(result[:3],enabled[:3]):np.testing.assert_array_equal(first,second)
    assert result[3]['atmospheric_parameters']['parameters']==enabled[3]['atmospheric_parameters']['parameters']


def test_missing_density_retains_independently_available_thermal_inputs(atmosphere):
    '''
    Purpose
    -------
    Verify missing density retains independently available thermal inputs.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg,profiles=atmosphere
    with netCDF4.Dataset(cfg['data']['file'],'a') as f:f.renameVariable('rho','missing_rho')
    record=ap.resolve_parameters(cfg,make_figure=False)
    assert record['status']=='available'
    assert record['parameters']['cs']==pytest.approx(6.15)
    assert 'a' not in record['parameters'] and 'H' not in record['parameters']
    assert 'Density profile unavailable' in record['unavailable']['a']


def test_invalid_scalar_samples_cannot_cancel_into_valid_averages(atmosphere):
    '''
    Purpose
    -------
    Verify invalid scalar samples cannot cancel into valid averages.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    _,profiles=atmosphere
    profiles.quantities['cs'][1]=-.1
    record=profiles.parameters(0,300)
    assert 'cs' not in record['parameters']
    assert 'Nonphysical cs' in record['unavailable']['cs']


def test_catalog_migration_uses_documented_verified_legacy_heights_and_refreshes_sources(tmp_path,atmosphere):
    '''
    Purpose
    -------
    Verify catalog migration uses documented verified legacy heights and refreshes
    sources.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import regenerate_html_figures as generator
    cfg,profiles=atmosphere
    value=_context(tmp_path,cfg,profiles.parameters(0,300),'hx_10g_v3_0km_300km')
    product=Path(value['dataset']['file']);ap.sidecar_path(product).unlink()
    cfg['paths']['data_output_dir']=str(tmp_path)
    cubes={'hx_10g':Path(cfg['data']['file'])}
    generator.refresh_catalog_atmospheres(cfg,cubes,Path(cfg['paths']['figure_dir']))
    first=ap.read_sidecar(product)
    assert first['parameters']['cs']==pytest.approx(6.15)
    assert 'legacy canonical pipeline filename' in first['height_identification']
    version=ap.sidecar_path(product).stat().st_mtime_ns
    generator.refresh_catalog_atmospheres(cfg,cubes,Path(cfg['paths']['figure_dir']))
    assert ap.sidecar_path(product).stat().st_mtime_ns==version
    with netCDF4.Dataset(profiles.provenance['profile']['path'],'a') as file:
        file['sound_speed'][:]=file['sound_speed'][:]+100
    generator.refresh_catalog_atmospheres(cfg,cubes,Path(cfg['paths']['figure_dir']))
    assert ap.read_sidecar(product)['parameters']['cs']==pytest.approx(6.151)


def test_legacy_native_height_names_resolve_to_the_actual_relative_cube_layers(tmp_path,atmosphere):
    '''
    Purpose
    -------
    Verify legacy native height names resolve to the actual relative cube layers.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import regenerate_html_figures as generator
    cfg,profiles=atmosphere
    value=_context(tmp_path,cfg,profiles.parameters(0,300),'hx_10g_v3_1589_92km_1889_92km')
    product=Path(value['dataset']['file']);ap.sidecar_path(product).unlink()
    with netCDF4.Dataset(cfg['data']['file'],'a') as file:
        file['xc3'][:]=file['xc3'][:]+1589.91546*1e5
    with netCDF4.Dataset(profiles.provenance['profile']['path'],'a') as file:
        file['z'][:]=file['z'][:]+1589.91546*1e5
    cfg['paths']['data_output_dir']=str(tmp_path)
    generator.refresh_catalog_atmospheres(cfg,{'hx_10g':Path(cfg['data']['file'])},Path(cfg['paths']['figure_dir']))
    record=ap.read_sidecar(product)
    assert record['height_pair_km']==pytest.approx([0.,300.])
    assert 'matched native coordinate convention' in record['height_identification']


def test_diagnostic_curves_use_simulation_height_bounds(atmosphere, monkeypatch):
    '''
    Purpose
    -------
    Verify diagnostic curves use simulation height bounds.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from matplotlib.figure import Figure
    cfg, profiles = atmosphere
    captured = []
    original = Figure.savefig

    def inspect(figure, *args, **kwargs):
        '''
        Purpose
        -------
        Inspect the generated figure against the enclosing reference values before
        delegating.

        Inputs
        ------
        figure: matplotlib.figure.Figure
            Figure inspected before delegating to the original writer.

        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        result: object
            Original figure-writer result after the fixture-specific assertions.
        '''

        expected = profiles.cube_height_km[[0, -1]]/1000.
        assert len(figure.axes) == 7  # Four panels; centre panel has no twin.
        for axis in figure.axes:
            np.testing.assert_allclose(axis.get_xlim(), expected)
            for line in axis.lines:
                np.testing.assert_allclose(line.get_xdata()[[0, -1]], expected)
        captured.append(True)
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, 'savefig', inspect)
    ap.save_diagnostic(profiles, cfg['paths']['figure_dir'])
    assert captured


def test_diagnostic_rejects_profile_that_does_not_cover_simulation(atmosphere):
    '''
    Purpose
    -------
    Verify diagnostic rejects profile that does not cover simulation.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from dataclasses import replace
    cfg, profiles = atmosphere
    shortened = replace(profiles, cube_height_km=np.array([-10., 100., 300., 700.]))
    # Require the expected ap.ProfileError from this failure case.
    with pytest.raises(ap.ProfileError, match='Thermal profile does not cover'):
        ap.save_diagnostic(shortened, cfg['paths']['figure_dir'])


def test_fourth_panel_loads_native_pressure_beta_and_invalidates_missing_cache(atmosphere, monkeypatch):
    '''
    Purpose
    -------
    Verify fourth panel loads native pressure beta and invalidates missing cache.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from matplotlib.figure import Figure
    cfg, profiles = atmosphere
    outputs = ap.save_diagnostic(profiles, cfg['paths']['figure_dir'])
    versions = [p.stat().st_mtime_ns for p in outputs]
    reference = Path(profiles.provenance['profile']['path'])
    with netCDF4.Dataset(reference) as source:
        z = np.asarray(source['z'][:])
    pressure, beta = np.array([100, 60, 30, 10, 1.]), np.array([90, 50, 20, 5, .1])
    for field, values, units in [('pressure', pressure, 'Pa'), ('plasma_beta', beta, '1')]:
        path = reference.with_name(reference.name.replace('_atmos_param', '_'+field+'_profile'))
        with netCDF4.Dataset(path, 'w') as d:
            d.Model = 'TEST'; d.snapshot_label_time_s = 20
            d.createDimension('z', len(z))
            coord = d.createVariable('z', 'f8', ('z',)); coord.units = 'cm'; coord[:] = z
            value = d.createVariable(field, 'f8', ('z',)); value.units = units; value[:] = values
    checked = []
    original = Figure.savefig

    def inspect(figure, *args, **kwargs):
        '''
        Purpose
        -------
        Inspect the generated figure against the enclosing reference values before
        delegating.

        Inputs
        ------
        figure: matplotlib.figure.Figure
            Figure inspected before delegating to the original writer.

        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        result: object
            Original figure-writer result after the fixture-specific assertions.
        '''

        assert len(figure.axes) == 7
        for axis, values in [(figure.axes[3], pressure*10.), (figure.axes[6], beta)]:
            assert axis.get_yscale() == 'log'
            line = axis.lines[0]
            np.testing.assert_allclose(line.get_ydata(), np.interp(line.get_xdata(), z/1e8, values))
        checked.append(True)
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, 'savefig', inspect)
    ap.save_diagnostic(profiles, cfg['paths']['figure_dir'])
    assert checked and [p.stat().st_mtime_ns for p in outputs] != versions


def write_native(cfg, profiles, field, values, units):
    '''
    Purpose
    -------
    Write one native one-dimensional profile using the loaded profile provenance.

    Inputs
    ------
    cfg: dict
        Synthetic runtime configuration associated with the atmospheric profiles.

    profiles: object
        Loaded atmospheric profiles carrying provenance and native-file information.

    field: str
        Observable or profile field selected by the current test.

    values: np.array
        Synthetic values or reference samples in the units declared by the fixture.

    units: str
        Unit metadata attached to the synthetic numerical variable.

    Outputs
    -------
    path: pathlib.Path
        Written profile file, with the supplied field values and units.
    '''

    # Resolve the provenance-selected reference before creating the companion native
    # profile.
    reference = Path(profiles.provenance['profile']['path'])
    suffix = 'density' if field == 'rho' else field
    path = reference.with_name(reference.name.replace('_atmos_param', '_'+suffix+'_profile'))
    with netCDF4.Dataset(reference) as d:
        z = d['z'][:]
    with netCDF4.Dataset(path, 'w') as d:
        d.Model = profiles.model
        d.snapshot_label_time_s = profiles.provenance['snapshot_time_s']
        d.createDimension('z', len(z))
        v = d.createVariable('z', 'f8', ('z',)); v.units = 'cm'; v[:] = z
        v = d.createVariable(field, 'f8', ('z',)); v.units = units; v[:] = values
    return path


def test_native_derivative_precedes_interpolation_and_preserves_instability(atmosphere):
    '''
    Purpose
    -------
    Verify native derivative precedes interpolation and preserves instability.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, old = atmosphere
    z = np.array([0., 50., 200., 400., 700.])
    rho = 1e-10*np.exp(-z/200.+4e-6*z*z)
    write_native(cfg, old, 'rho', rho, 'gm/cm^3')
    with netCDF4.Dataset(old.provenance['profile']['path'], 'a') as d:
        d['sound_speed'][:] = 1e6
    new = ap.load_profiles(cfg)
    # Log density is quadratic, so its three-point derivative is analytic.
    native_slope = -.005+8e-6*z
    slope = np.interp(new.height_km, z, native_slope)
    expected = -.274*slope-.274**2/100.
    np.testing.assert_allclose(new.quantities['N2'], expected, rtol=2e-12, atol=1e-16)
    np.testing.assert_allclose(new.quantities['wac'], -10.*slope/2., rtol=2e-12, atol=1e-16)
    assert np.any(expected < 0) and np.any(expected > 0)
    assert new.provenance['density_derivative_source'] == 'native unbinned density profile'
    assert new.parameters(700, 700)['parameters']['N2'] < 0
    assert 'H' not in new.parameters(700, 700)['parameters']


def test_native_alfven_profile_is_used_before_averaging(atmosphere):
    '''
    Purpose
    -------
    Verify native alfven profile is used before averaging.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, old = atmosphere
    path = Path(old.provenance['profile']['path'])
    with netCDF4.Dataset(path, 'a') as d:
        a = d.createVariable('alfven_speed', 'f8', ('z',)); a.units='cm/s'
        a[:] = (2.+d['z'][:]/1e8)*1e5
    new = ap.load_profiles(cfg)
    values = new.parameters(50, 250)
    assert values['parameters']['a'] == pytest.approx(2.15)
    assert 'supplied horizontal mean' in values['parameter_sources']['a']
    assert values['parameters']['a'] != pytest.approx(old.parameters(50, 250)['parameters']['a'])
    initializations, _ = context.atmospheric_initializations(cfg, values)
    for inputs in initializations.values():
        if 'a' in inputs:
            assert inputs['a'] == pytest.approx(2.15)
        if 'cs' in inputs:
            assert inputs['cs'] == pytest.approx(values['parameters']['cs'])
        if 'N2' in inputs:
            assert inputs['N2'] == pytest.approx(values['parameters']['N2'])
        if 'H' in inputs:
            assert inputs['H'] == pytest.approx(values['parameters']['H'])


def test_pressure_check_reduces_to_paper_n2_under_hydrostatic_balance(atmosphere):
    '''
    Purpose
    -------
    Verify pressure check reduces to paper N2 under hydrostatic balance.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, old = atmosphere
    z_km = np.array([0., 50., 200., 400., 700.])
    rho = np.full(5, 1e-10)
    pressure = 500.-rho*27400.*z_km*1e5
    write_native(cfg, old, 'rho', rho, 'gm/cm^3')
    write_native(cfg, old, 'pressure', pressure, 'dyn/cm^2')
    with netCDF4.Dataset(old.provenance['profile']['path'], 'a') as d:
        d['sound_speed'][:] = np.sqrt((5./3.)*pressure/rho)
    new = ap.load_profiles(cfg)
    np.testing.assert_allclose(new.quantities['hydrostatic_gravity_km_s2'], .274, rtol=2e-13)
    # Pressure-gradient N2 uses the interpolated effective Gamma1, so compare
    # at native knots where the analytic thermodynamic state is exact.
    indices = np.searchsorted(new.height_km, z_km)
    np.testing.assert_allclose(new.quantities['Gamma1_effective'][indices], 5./3., rtol=1e-13)
    # d ln P from finite differences is not dP/P exactly on a coarse mesh;
    # the general buoyancy check must use the actual dP/dz expression.
    np.testing.assert_allclose(new.quantities['N2_pressure_gradient'][indices],
                               new.quantities['N2'][indices], rtol=1e-12, atol=1e-15)
    assert 'gamma' not in new.parameters(50, 250)['parameters']


def test_new_native_file_invalidates_cache_and_embedded_initializations(atmosphere):
    '''
    Purpose
    -------
    Verify new native file invalidates cache and embedded initializations.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, old = atmosphere
    record = old.parameters(50, 250)
    z = np.array([0., 50., 200., 400., 700.])
    write_native(cfg, old, 'rho', 1e-10*np.exp(-z/80.), 'gm/cm^3')
    new = ap.load_profiles(cfg)
    assert new is not old
    updated = ap.upgrade_atmosphere(record)
    assert updated['parameters']['H'] == pytest.approx(80.)
    assert updated['parameters']['N2'] != pytest.approx(record['parameters']['N2'])
    assert updated['provenance']['native_profiles']['rho']['path'].endswith('_density_profile.h5')
    record['provenance']['algorithm_version'] = 2
    record['initializations'] = {'nc2009': {'N2': 99.}}
    legacy = ap.upgrade_atmosphere(record)
    assert legacy['parameters']['H'] == pytest.approx(80.)
    assert legacy['provenance']['algorithm_version'] == ap.ALGORITHM_VERSION
    assert 'initializations' not in legacy


def test_co5bold_internal_field_normalization_is_explicit_and_overridable(atmosphere):
    '''
    Purpose
    -------
    Verify co5bold internal field normalization is explicit and overridable.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, old = atmosphere
    with netCDF4.Dataset(cfg['data']['file'], 'a') as d:
        d.SOLMETA_CREATOR = 'CO5BOLD'
    internal = ap.load_profiles(cfg)
    np.testing.assert_allclose(internal.components_G, np.asarray(old.components_G)*np.sqrt(4*np.pi))
    assert internal.parameters(100, 100)['parameters']['a'] == pytest.approx(
        old.parameters(100, 100)['parameters']['a']*np.sqrt(4*np.pi))
    with netCDF4.Dataset(cfg['data']['file'], 'a') as d:
        d.magnetic_field_convention = 'physical'
    physical = ap.load_profiles(cfg)
    np.testing.assert_allclose(physical.components_G, old.components_G)


def test_mismatched_native_profile_is_disclosed_instead_of_resampled(atmosphere):
    '''
    Purpose
    -------
    Verify mismatched native profile is disclosed instead of resampled.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, old = atmosphere
    path = write_native(cfg, old, 'rho', np.full(5, 1e-10), 'gm/cm^3')
    with netCDF4.Dataset(path, 'a') as d:
        d['z'][1] += 1e5
    record = ap.resolve_parameters(cfg, make_figure=False)
    assert record['status'] == 'unavailable'
    assert 'native heights differ' in record['unavailable']['all']
