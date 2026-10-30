'''
Purpose
-------
Geometry, identity, optimized selection, and repeat-run regressions.

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
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0,str(TD))
import output_paths as manager
import optimized_filter_config as optimized
import pipeline
import config as config_module


def configuration(tmp_path, heights=(0.,220.), indices=(0,1), filename='simulation_hx_10G.nc'):
    '''
    Purpose
    -------
    Construct the synthetic single-cube configuration used by output-geometry tests.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    heights: sequence of float
        Physical heights of the synthetic cube levels (km).

    indices: tuple of int
        Indices selecting the two synthetic height levels.

    filename: str or pathlib.Path
        Source filename used by the current test case.

    Outputs
    -------
    config: dict
        Height-resolved runtime settings with temporary data and figure roots.
        Create the minimal source file when it is absent.
    '''

    # Create a source identity with resolved height values and isolated output roots.
    source=tmp_path/filename
    if not source.exists(): source.write_bytes(b'input')
    return dict(data=dict(source_type='single_cube',file=str(source),observable='v3',h1=indices[0],h2=indices[1],
        resolved_h1_index=indices[0],resolved_h2_index=indices[1],resolved_h1_km=heights[0],resolved_h2_km=heights[1],
        resolved_delta_z_km=abs(heights[1]-heights[0])),filtering=copy.deepcopy(config_module.default_filtering),
        magnetogram_mode={'single_cube':'bottom'},time_distance=dict(dt=30.,p_dx_Mm=.16,maxdist_Mm=.5,width=0,
        dx_pixels=1.,nworkers=1,xcorr_geometry='annulus'),paths=dict(data_output_dir=str(tmp_path/'Data'),figure_dir=str(tmp_path/'Figures')),
        optimized_filtering={'mode':'manual'})


def test_required_hierarchy_and_no_parameter_directories(tmp_path):
    '''
    Purpose
    -------
    Verify required hierarchy and no parameter directories.

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

    cfg=configuration(tmp_path)
    manager.configure_outputs(cfg)
    for root in (tmp_path/'Data',tmp_path/'Figures'):
        for name in manager.DIAGNOSTICS:
            assert (root/'simulations/v3/Annulus/hx/h10G/h0_vs_h1'/name).is_dir()
            assert (root/'simulations/v3/Annulus/hx/h10G/delta_z_220_km'/name).is_dir()
    assert not list(tmp_path.rglob('filter_*'))
    assert Path(cfg['data']['phase_outfile']).parent.name=='phase_differences'


def test_retired_orientation_plot_is_disabled_even_for_historical_configs(tmp_path):
    '''
    Purpose
    -------
    Verify retired orientation plot is disabled even for historical configs.

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

    cfg=configuration(tmp_path)
    manager.configure_outputs(cfg)
    assert cfg['data']['orientation_validation_outfile']==''
    identity=manager.output_identity(cfg)
    cfg['data']['orientation_validation_outfile']=str(tmp_path/'legacy_validation.png')
    assert pipeline.TimeDistance(cfg).orientation_validation_outfile is None
    assert manager.output_identity(cfg)==identity
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='Unsupported output product'):
        manager.build_output_file(tmp_path/'Figures',cfg,'orientation_validation','retired.png')


def test_gaussian_gallery_discovers_real_diagram_metadata_without_validation_images(tmp_path):
    '''
    Purpose
    -------
    Verify gaussian gallery discovers real diagram metadata without validation images.

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

    import comparison_gallery as gallery
    cfg=configuration(tmp_path)
    cfg['filtering'].update(enabled=True,filter_sequence=['gaussian'])
    cfg['filtering']['gaussian'].update(enabled=True,central_k=1.5,width_k=4.,central_f=3.,width_f=3.)
    manager.configure_outputs(cfg)
    image=manager.build_output_file(tmp_path/'Figures',cfg,'komega_diagram','hx_10g_v3_0km_220km_komega.png')
    image.write_bytes(b'diagram')
    manager.register_output(image,cfg,'komega_diagram')
    # A different pair has no bearing on this comparison's parameter discovery.
    other=configuration(tmp_path,heights=(220.,440.),indices=(1,2))
    other['filtering']=copy.deepcopy(cfg['filtering'])
    other['filtering']['gaussian']['central_k']=9.
    manager.configure_outputs(other)
    wrong=manager.build_output_file(tmp_path/'Figures',other,'komega_diagram','hx_10g_v3_220km_440km_komega.png')
    wrong.write_bytes(b'other diagram');manager.register_output(wrong,other,'komega_diagram')
    parts=gallery.ComparisonPlotNameParts('gaussian_filter_comparison','v3','0','220','filters_1')
    assert gallery._discover_gaussian_processing_slugs(tmp_path/'Figures','hx_10g',parts,1)==[
        'gaussian_filtered_gauss_ck_1_5_wk_4_cf_3_wf_3']


def test_migration_does_not_reintroduce_retired_orientation_images(tmp_path):
    '''
    Purpose
    -------
    Verify migration does not reintroduce retired orientation images.

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

    from migrate_geometry_outputs import migrate, migration_product
    legacy=tmp_path/'legacy';legacy.mkdir()
    figures=tmp_path/'legacy_figures';figures.mkdir()
    image=figures/'hx_10g_v3_0km_220km_unfiltered_komega_magnetic_orientation_validation.png'
    image.write_bytes(b'historical optional plot')
    assert migration_product(image) is None
    report=migrate(legacy,figures,tmp_path/'Data',figure_root=tmp_path/'Figures',apply=True)
    assert report['counts']=={'skipped':1}
    assert image.read_bytes()==b'historical optional plot'
    assert not list((tmp_path/'Figures').rglob('*.png'))


@pytest.mark.parametrize('filename,category',[('simulation_hx_50G.nc','hx/h50G'),('simulation_hx_100G.nc','hx/h100G'),('simulation_vx_10G.nc','vx/v10G'),('simulation_vx_50G.nc','vx/v50G'),('simulation_vx_100G.nc','vx/v100G'),('simulation_z0_0G.nc','z0')])
def test_categories_are_model_fields_not_mask_threshold(tmp_path,filename,category):
    '''
    Purpose
    -------
    Verify categories are model fields not mask threshold.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    filename: str or pathlib.Path
        Source filename used by the current test case.

    category: str
        Synthetic magnetic-model category used to identify output paths.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg=configuration(tmp_path,filename=filename)
    cfg['filtering']['magnetogram'].update(enabled=True,threshold_G=3.)
    assert manager.resolve_category(cfg).as_posix()==category


def test_order_is_stable_nonuniform_negative_and_reversed_heights(tmp_path):
    '''
    Purpose
    -------
    Verify order is stable nonuniform negative and reversed heights.

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

    samples=[(-500.,-279.6),(440.2,660.3),(220.1,440.4),(0.,220.49),(880.7,660.4)]
    for product in manager.DIAGNOSTICS:
        names=[manager.grouped_filename(f'{i}.fits',{'heights_km':h}) for i,h in enumerate(samples)]
        order=sorted(range(len(names)),key=lambda i:names[i])
        assert order==[4,1,2,3,0]
        import re
        natural=lambda value:[int(part) if part.isdigit() else part for part in re.split(r'(\d+)',value)]
        assert sorted(range(len(names)),key=lambda i:natural(names[i]))==order
        # A newly added highest pair cannot change any existing name/rank.
        new=manager.grouped_filename('new.fits',{'heights_km':[1100.3,1320.4]})
        assert sorted(names+[new])[0]==new
    cfg=configuration(tmp_path,heights=(10.2,230.69))
    assert manager.height_geometry(cfg)['delta_z_rounded_km']==220
    cfg['data'].update(resolved_h2_km=230.71,resolved_delta_z_km=220.51)
    assert manager.height_geometry(cfg)['delta_z_rounded_km']==221


def test_effective_configuration_and_datasets_never_collide(tmp_path):
    '''
    Purpose
    -------
    Verify effective configuration and datasets never collide.

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

    cfg=configuration(tmp_path);manager.configure_outputs(cfg)
    original=cfg['data']['komega_outfile']
    changed=copy.deepcopy(cfg);changed['filtering']['gaussian']['width_f']=4.3
    manager.configure_outputs(changed)
    assert changed['data']['komega_outfile']!=original
    assert Path(changed['data']['komega_outfile']).parent==Path(original).parent
    other=configuration(tmp_path,filename='second_simulation_hx_10G.nc');manager.configure_outputs(other)
    assert other['data']['komega_outfile']!=original
    reversed_pair=configuration(tmp_path,heights=(220.,0.),indices=(1,0));manager.configure_outputs(reversed_pair)
    assert Path(reversed_pair['data']['komega_outfile']).parent.parent.name=='h1_vs_h0'


def test_linking_repeat_reuse_and_invalidation(tmp_path):
    '''
    Purpose
    -------
    Verify linking repeat reuse and invalidation.

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

    cfg=configuration(tmp_path);manager.configure_outputs(cfg)
    path=Path(cfg['data']['komega_outfile']);path.write_bytes(b'scientific bytes')
    record=manager.register_output(path,cfg,'komega_diagram')
    group=manager.associate_output(path,record,tmp_path/'Data')
    assert group.is_symlink() and group.read_bytes()==path.read_bytes()
    assert manager.metadata_path(group).is_file()
    manager.register_output(path,cfg,'komega_diagram')
    assert len(list(group.parent.glob('*.fits')))==1
    assert manager.can_reuse(path,cfg)
    path.write_bytes(b'changed bytes')
    assert not manager.can_reuse(path,cfg)
    path.write_bytes(b'scientific bytes')
    Path(cfg['data']['file']).write_bytes(b'changed source')
    assert not manager.can_reuse(path,cfg)


def test_collision_refuses_unrelated_alias(tmp_path):
    '''
    Purpose
    -------
    Verify collision refuses unrelated alias.

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

    cfg=configuration(tmp_path);manager.configure_outputs(cfg)
    path=Path(cfg['data']['komega_outfile']);path.write_bytes(b'data')
    group=tmp_path/'Data/simulations/v3/Annulus/hx/h10G/delta_z_220_km/k_omega'/manager.grouped_filename(path,manager.height_geometry(cfg))
    group.write_bytes(b'unrelated')
    # Require the expected FileExistsError from this failure case.
    with pytest.raises(FileExistsError):manager.register_output(path,cfg,'komega_diagram')
    assert group.read_bytes()==b'unrelated'


def test_observations_never_get_fabricated_heights_or_field_category(tmp_path):
    '''
    Purpose
    -------
    Verify observations never get fabricated heights or field category.

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

    cfg=configuration(tmp_path)
    cfg['data']=dict(source_type='paired_cubes',v1=str(tmp_path/'25Apr2019.fe5434.fits'),
        v2=str(tmp_path/'25Apr2019.fe7090.fits'),resolved_delta_z_km=168.)
    assert manager.resolve_category(cfg).as_posix()=='.'
    assert manager.organization_prefix(cfg).as_posix()=='observations/doppler_velocity/Annulus'
    assert manager.height_geometry(cfg)['heights_km'] is None
    assert manager.height_geometry(cfg)['delta_z_rounded_km'] is None
    cfg['output']=dict(category='vx',field_strength_G=10.,height_values_km=[250.,418.])
    assert manager.resolve_category(cfg).as_posix()=='vx/v10G'
    assert manager.height_geometry(cfg)['heights_km']==[250.,418.]


def test_actual_saved_optimized_configuration_and_manual_override(tmp_path):
    '''
    Purpose
    -------
    Verify actual saved optimized configuration and manual override.

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

    cfg=configuration(tmp_path,indices=(2,4),heights=(440.,880.))
    from data_locations import CO5BOLD_ROOT
    cfg['data']['file']=str(CO5BOLD_ROOT/'hx/100G/simulation_hx_100G_33570s_48000s.nc')
    cfg['optimized_filtering']={'mode':'optimized','file':str(optimized.DEFAULT_FILE)}
    optimized.apply_optimized_filters(cfg)
    assert cfg['filtering']['gaussian']['central_f']==6.
    assert cfg['filtering']['magnetogram']['threshold_G']==0.
    assert cfg['filtering']['filter_sequence']==['magnetogram','gaussian']
    cfg['optimized_filtering']['overrides']={'gaussian':{'width_k':2.}}
    optimized.apply_optimized_filters(cfg)
    assert cfg['filtering']['gaussian']['width_k']==2.
    assert cfg['filter_configuration']['overrides']['gaussian']['width_k']==2.
    cfg['data']['h2']=3
    # Require the expected optimized.ConfigurationError from this failure case.
    with pytest.raises(optimized.ConfigurationError,match='found 0'):optimized.apply_optimized_filters(cfg)


def test_ambiguous_invalid_and_selection_specific_configurations(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify ambiguous invalid and selection specific configurations.

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

    cfg=configuration(tmp_path);cfg['optimized_filtering']={'mode':'optimized'}
    key=optimized._key(cfg['data'])
    entry=dict(key=key,identity='a',filtering=cfg['filtering'])
    # Require the expected optimized.ConfigurationError from this failure case.
    with pytest.raises(optimized.ConfigurationError,match='missing'):
        optimized.load_configurations(tmp_path/'missing.txt')
    monkeypatch.setattr(optimized,'load_configurations',lambda path:([entry,entry],'digest'))
    # Require the expected optimized.ConfigurationError from this failure case.
    with pytest.raises(optimized.ConfigurationError,match='found 2'):optimized.apply_optimized_filters(cfg)


def test_configuration_load_once_per_file_version():
    '''
    Purpose
    -------
    Verify configuration load once per file version.

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

    optimized._load.cache_clear()
    optimized.load_configurations();optimized.load_configurations()
    info=optimized._load.cache_info()
    assert info.misses==1 and info.hits==1


def test_small_pipeline_repeat_preserves_arrays_and_skips_recalculation(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify small pipeline repeat preserves arrays and skips recalculation.

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

    cfg=configuration(tmp_path);cfg['filtering']['enabled']=False
    manager.configure_outputs(cfg)
    worker=pipeline.TimeDistance(cfg)
    rng=np.random.default_rng(1234);cubes=(rng.normal(size=(32,24,24)),rng.normal(size=(32,24,24)))
    monkeypatch.setattr(worker,'load_dopplergrams',lambda:cubes)
    monkeypatch.setattr(worker,'compute_single_cube_magnetic_orientation_metadata',lambda:None)
    first=worker.run()
    second_worker=pipeline.TimeDistance(cfg)
    monkeypatch.setattr(second_worker,'load_dopplergrams',lambda:pytest.fail('recomputed completed run'))
    second=second_worker.run()
    assert second['reused']
    for key in ('xc','phase_diff','komega','coherence','radii','frequencies','time_lags'):
        np.testing.assert_array_equal(first[key],second[key])
    for key in ('outfile','phase_outfile','komega_outfile','coherence_outfile'):
        assert manager.can_reuse(cfg['data'][key],cfg)


@pytest.mark.parametrize('observable',['v1','v2','v3','bb1','bb2','bb3','rho','temp','pressure'])
@pytest.mark.parametrize('geometry',['east','west','north','south','annulus'])
def test_observable_and_geometry_prefixes(tmp_path,observable,geometry):
    '''
    Purpose
    -------
    Verify observable and geometry prefixes.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    observable: str
        Numerical observable selected from the source cube.

    geometry: str
        Correlation or Fourier-filter geometry selected for the case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg=configuration(tmp_path)
    cfg['data']['observable']=observable
    cfg['time_distance']['xcorr_geometry']=geometry
    manager.configure_outputs(cfg)
    identity=cfg['_output_context']['identity']
    assert identity['organization_prefix']==f'simulations/{observable}/{geometry.title()}'
    for root in (tmp_path/'Data',tmp_path/'Figures'):
        assert (root/'simulations'/observable/geometry.title()/'hx/h10G/h0_vs_h1/spatial').is_dir()
    cfg['data'].update(source_type='paired_cubes',v1=str(tmp_path/'25Apr2019.fe5434.fits'),
        v2=str(tmp_path/'25Apr2019.fe7090.fits'),height_labels=['fe5434','fe7090'])
    manager.configure_outputs(cfg)
    assert cfg['_output_context']['identity']['organization_prefix']==f'observations/doppler_velocity/{geometry.title()}'
    assert Path(cfg['data']['outfile']).parts[-5:-1]==('doppler_velocity',geometry.title(),'fe5434_vs_fe7090','xcorr')


def test_migration_is_non_destructive_and_idempotent(tmp_path):
    '''
    Purpose
    -------
    Verify migration is non destructive and idempotent.

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

    from migrate_geometry_outputs import migrate
    from astropy.io import fits
    cfg=configuration(tmp_path,heights=(30.,250.),indices=(0,1))
    legacy=tmp_path/'legacy';legacy.mkdir()
    numerical=legacy/'hx_10g_v3_30km_250km_unfiltered_komega.fits'
    array=np.arange(15,dtype=np.float32).reshape(3,5)
    fits.writeto(numerical,array)
    reference=dict(data=cfg['data'],sampling={'dt':30.,'p_dx_Mm':.16},
        filtering=dict(enabled=False,filter_sequence=[],gaussian={'enabled':False},magnetogram={'enabled':False}),
        magnetogram_mode={'single_cube':'bottom'})
    numerical.with_suffix('.inputs.json').write_text(json.dumps(reference))
    figures=tmp_path/'legacy_figures';figures.mkdir()
    first=migrate(legacy,figures,tmp_path/'Data',figure_root=tmp_path/'Figures',apply=True)
    second=migrate(legacy,figures,tmp_path/'Data',figure_root=tmp_path/'Figures',apply=True)
    assert first==second
    assert first['counts']=={'linked':1}
    destination=Path(first['records'][0]['destination'])
    assert destination.is_symlink() and destination.samefile(numerical)
    np.testing.assert_array_equal(fits.getdata(destination),array)
    assert 'simulations/v3/Annulus/hx/h10G/h0_vs_h1/k_omega' in str(destination)
    for name in manager.DIAGNOSTICS: assert (destination.parent.parent/name).is_dir()
    assert len(list((tmp_path/'Data/simulations/v3/Annulus/hx/h10G/delta_z_220_km/k_omega').glob('*.fits')))==1


def test_mutated_effective_config_cannot_reuse_old_context(tmp_path):
    '''
    Purpose
    -------
    Verify mutated effective config cannot reuse old context.

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

    cfg=configuration(tmp_path);manager.configure_outputs(cfg)
    product=Path(cfg['data']['komega_outfile']);product.write_bytes(b'saved')
    manager.register_output(product,cfg,'komega_diagram')
    cfg['filtering']['gaussian']['width_f']=7.
    assert not manager.can_reuse(product,cfg)


def test_invalid_optimized_file_and_filter_parameters_are_rejected(tmp_path):
    '''
    Purpose
    -------
    Verify invalid optimized file and filter parameters are rejected.

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

    path=tmp_path/'optimized.txt'
    path.write_text('{broken JSON')
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError): optimized.load_configurations(path)
    record=json.loads(optimized.DEFAULT_FILE.read_text())
    next(iter(record['observations'].values()))['gaussian']['parameters']['width_k']=-1.
    path.write_text(json.dumps(record))
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError): optimized.load_configurations(path)


def test_live_plot_export_uses_same_hierarchy_and_links(tmp_path):
    '''
    Purpose
    -------
    Verify live plot export uses same hierarchy and links.

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

    from bokeh.plotting import figure
    from komega_plot_export import save_plot_pair
    cfg=configuration(tmp_path)
    manager.build_runtime_output_paths(cfg,tmp_path/'Data',tmp_path/'Figures')
    plots=[figure(width=200,height=200),figure(width=200,height=200)]
    for plot in plots:plot.line([0,1],[1,0])
    files=save_plot_pair(plots,{'source_1':{'id':'simulation'},'source_2':{'model_key':'native'},
        'export_type':'spatial_phase'},tmp_path/'Figures',config=cfg,product='spatial_phase')
    assert files[0].is_relative_to(tmp_path/'Figures/simulations/v3/Annulus/hx/h10G/h0_vs_h1/spatial')
    assert manager.metadata_path(files[0]).is_file()
    groups=list((tmp_path/'Figures/simulations/v3/Annulus/hx/h10G/delta_z_220_km/spatial').glob('*.html'))
    assert len(groups)==1 and groups[0].samefile(files[0])
    assert groups[0].with_suffix('.txt').is_file()


def test_legacy_observations_inside_filter_folders_are_migrated(tmp_path):
    '''
    Purpose
    -------
    Verify legacy observations inside filter folders are migrated.

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

    from migrate_geometry_outputs import migrate
    from astropy.io import fits
    legacy=tmp_path/'legacy';folder=legacy/'filter_1/observations/nonmagneto/25apr2019/komega/annulus/v1'
    folder.mkdir(parents=True)
    product=folder/'25apr2019_fe5434_fe7090_komega.fits'
    fits.writeto(product,np.arange(6,dtype=np.float32).reshape(2,3))
    originals=[tmp_path/'25Apr2019.fe5434.fits',tmp_path/'25Apr2019.fe7090.fits']
    for source in originals:source.write_bytes(b'original')
    reference=dict(data=dict(source_type='paired_cubes',v1=str(originals[0]),v2=str(originals[1]),resolved_delta_z_km=168.),
        sampling={'dt':11.88,'p_dx_Mm':.43},filtering={'enabled':False,'filter_sequence':[]},magnetogram_mode={'single_cube':'bottom'})
    product.with_suffix('.inputs.json').write_text(json.dumps(reference))
    figures=tmp_path/'legacy_figures';figures.mkdir()
    report=migrate(legacy,figures,tmp_path/'Data',figure_root=tmp_path/'Figures',apply=True)
    assert report['counts']=={'linked':1}
    destination=Path(report['records'][0]['destination'])
    assert destination.is_relative_to(tmp_path/'Data/observations/doppler_velocity/Annulus/fe5434_vs_fe7090/k_omega')
    assert destination.samefile(product)
    assert 'unavailable' in report['records'][0]['grouping_status']


def test_production_and_programmatic_defaults_use_optimized_source():
    '''
    Purpose
    -------
    Verify production and programmatic defaults use optimized source.

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

    cfg=config_module.get_config(source_type='single_cube',file_path='hx/100G/simulation.nc',observable='v3',h1=2,h2=4)
    assert cfg['optimized_filtering']['mode']=='optimized'
    loaded=pipeline.load_time_distance_config(TD/'config.py')
    assert loaded['optimized_filtering']['mode']=='optimized'
    manual=config_module.get_config(source_type='single_cube',file_path='hx/100G/simulation.nc',observable='v3',h1=2,h2=4,
        filtering=config_module.default_filtering)
    assert manual['optimized_filtering']['mode']=='manual'


def test_json_companions_and_legacy_fallback(tmp_path):
    '''
    Purpose
    -------
    Verify JSON companions and legacy fallback.

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

    product = tmp_path/'k_omega'/'result.fits'
    product.parent.mkdir()
    product.write_bytes(b'scientific result')
    legacy = product.with_suffix('.metadata.json')
    legacy.write_text('{"legacy": true}')
    assert manager.read_metadata(product) == {'legacy': True}
    current = manager.metadata_path(product)
    assert current == product.parent/'json_files'/'result.metadata.json'
    manager.atomic_json(current, {'current': True})
    assert manager.read_metadata(product) == {'current': True}
    assert manager.product_from_json_sidecar(current, '.fits') == product


def test_json_relocation_preserves_relative_links_and_is_repeatable(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify JSON relocation preserves relative links and is repeatable.

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

    from organize_json_outputs import organize
    canonical = tmp_path/'pair'/'k_omega'/'result.metadata.json'
    canonical.parent.mkdir(parents=True)
    canonical.write_text('{"scientific_metadata": 1}')
    grouped = tmp_path/'delta_z_220_km'/'k_omega'/'001.metadata.json'
    manager._ensure_link(grouped, canonical)
    monkeypatch.chdir(tmp_path.parent)
    assert organize(Path(tmp_path.name)) == 2
    relocated = manager.json_output_path(canonical)
    alias = manager.json_output_path(grouped)
    assert alias.samefile(relocated)
    assert alias.read_text() == '{"scientific_metadata": 1}'
    assert organize(tmp_path) == 0
