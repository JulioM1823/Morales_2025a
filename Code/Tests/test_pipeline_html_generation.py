'''
Purpose
-------
Exercise the public HTML entry points and actual notebook figure writers.

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
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit
import json
import re
import sys

import pytest

TD=Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0,str(TD))
import comparison_gallery as gallery
import html_output_paths as html
import output_paths as paths
from test_geometry_outputs import configuration
from test_scoped_html_outputs import comparison, References


def check_local_links(root):
    '''
    Purpose
    -------
    Verify that each generated individual-figure link resolves beneath the expected
    output tree.

    Inputs
    ------
    root: pathlib.Path
        Root directory containing the inputs, outputs, or cache under test.

    Outputs
    -------
    None
        Fail the test if a required generated local page is absent.
    '''

    # Follow generated local figure references and require every target to exist.
    for page in root.rglob('*.html'):
        parser=References();parser.feed(page.read_text())
        for reference in parser.paths:
            url=urlsplit(reference)
            if not url.scheme and url.path:
                assert (page.parent/unquote(url.path)).is_file(),(page,reference)


@pytest.mark.parametrize('source_type,observable',
    [('single_cube',observable) for observable in paths.OBSERVABLES]+
    [('paired_cubes','doppler_velocity')])
@pytest.mark.parametrize('direction',paths.XCORR_GEOMETRIES)
def test_public_gallery_writer_handles_one_source_and_each_direction(tmp_path,source_type,observable,direction):
    '''
    Purpose
    -------
    Verify public gallery writer handles one source and each direction.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    observable: str
        Numerical observable selected from the source cube.

    direction: str
        Directional or annulus correlation/output scope selected by the test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    root=tmp_path/'Figures'
    identities,image=comparison(root,tmp_path,observable,direction,
        source_type=source_type,categories=('.',) if source_type=='paired_cubes' else ('hx','vx'))
    other='observations' if source_type=='single_cube' else 'simulations'
    assert not (root/other).exists()
    result=gallery.write_default_comparison_viewers(root)
    directory=root/identities[0]['organization_prefix']/'HTML'
    assert list(result)==[str(directory)]
    assert result[str(directory)]['field_strength_comparison']['plot_count']==1
    assert set(p.name for p in directory.glob('*.html'))=={
        value['output_name'] for value in gallery.COMPARISON_VIEWERS.values()}
    assert not list(root.glob('*.html')) and not (root/'HTML Figures').exists()
    check_local_links(root)


def test_public_writer_separates_every_recorded_configuration(tmp_path):
    '''
    Purpose
    -------
    Verify public writer separates every recorded configuration.

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

    root=tmp_path/'Figures'
    expected=set()
    for observable,direction,source_type in [
        ('v3','annulus','single_cube'),('v1','east','single_cube'),
        ('bb3','west','single_cube'),('doppler_velocity','north','paired_cubes')]:
        identities,_=comparison(root,tmp_path,observable,direction,source_type=source_type,
            categories=('.',) if source_type=='paired_cubes' else ('hx','vx'))
        expected.add(str(root/identities[0]['organization_prefix']/'HTML'))
    result=gallery.write_default_comparison_viewers(root)
    assert set(result)==expected
    assert all(records['field_strength_comparison']['plot_count']==1 for records in result.values())
    check_local_links(root)


@pytest.mark.parametrize('source_type,observable,direction',[
    ('single_cube','v3','annulus'),('paired_cubes','doppler_velocity','south')])
def test_standalone_regenerator_uses_manuscript_root_and_requested_scope(tmp_path,monkeypatch,source_type,observable,direction):
    '''
    Purpose
    -------
    Verify standalone regenerator uses manuscript root and requested scope.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    observable: str
        Numerical observable selected from the source cube.

    direction: str
        Directional or annulus correlation/output scope selected by the test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import regenerate_html_figures as regenerate
    root=tmp_path/'Morales_2025a et al/Figures'
    identities,_=comparison(root,tmp_path,observable,direction,source_type=source_type,
        categories=('.',) if source_type=='paired_cubes' else ('hx','vx'))
    _,unavailable=comparison(root,tmp_path,'v1','east')
    unavailable.unlink()
    monkeypatch.setattr(regenerate,'notebook_helpers',lambda:pytest.fail('Managed HTML regeneration entered native legacy recovery'))
    result=regenerate.restore(tmp_path/'Figures',tmp_path/'cubes',scope=identities[0]['organization_prefix'])
    assert list(result)==[str(root/identities[0]['organization_prefix']/'HTML')]
    assert not list((root/'simulations/v1/East').rglob('*.html'))
    check_local_links(root)


@pytest.mark.parametrize('writer,source_type,direction',[
    ('maybe_save_figure','single_cube','east'),
    ('save_gaussian_filter_comparison_figure','single_cube','annulus'),
    ('maybe_save_figure','paired_cubes','north'),
    ('save_gaussian_filter_comparison_figure','paired_cubes','south')])
def test_notebook_saves_new_megaplots_and_publishable_exact_launches(tmp_path,monkeypatch,writer,source_type,direction):
    '''
    Purpose
    -------
    Verify notebook saves new megaplots and publishable exact launches.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    writer: str
        Notebook writer selected for the output-scope case.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    direction: str
        Directional or annulus correlation/output scope selected by the test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import komega_bokeh_context as context
    import comparison_gallery as current_gallery
    monkeypatch.setitem(sys.modules,'comparison_gallery',current_gallery)
    from test_td_batch import analysis_helpers
    from test_komega_bokeh_integration import sample
    root=tmp_path/'Morales_2025a et al/Figures'
    (root/('simulations' if source_type=='single_cube' else 'observations')).mkdir(parents=True)
    data,cfg=sample(tmp_path,source_type)
    local=configuration(tmp_path,heights=(440.,660.),indices=(2,3))
    cfg['data'].update(local['data']);cfg['data']['source_type']=source_type
    cfg['paths']=local['paths'];cfg['time_distance']['xcorr_geometry']=direction
    if source_type=='paired_cubes':
        cfg['data'].update(v1=str(tmp_path/'fe5434.fits'),v2=str(tmp_path/'fe7090.fits'),
            height_labels=['fe5434','fe7090'])
    paths.build_runtime_output_paths(cfg,cfg['paths']['data_output_dir'],root)
    before=Path(data['data_file']).read_bytes()
    figure=Figure(figsize=(2,2),dpi=40);FigureCanvasAgg(figure)
    axis=figure.subplots();axis.imshow(data['values'].T,origin='lower')
    context.register_panel(axis,data,cfg)
    figure._komega_comparison_type='field_strength_comparison'
    monkeypatch.setattr(analysis_helpers,'plt',SimpleNamespace(rcParams=matplotlib.rcParams),raising=False)
    output=getattr(analysis_helpers,writer)(figure,'new_comparison.jpeg',
        figure_dir=tmp_path/'Figures',config=cfg,product='composite_diagnostics')
    identity=paths.output_identity(cfg)
    assert output.parent==html.shared_support_directory(root,identity)/'megaplots'
    assert not output.is_symlink()
    result=current_gallery.write_default_comparison_viewers(tmp_path/'Figures')
    record=result[str(root/identity['organization_prefix']/'HTML')]['field_strength_comparison']
    assert record['plot_count']==1  # delta_z aliases must not become duplicate megaplots.
    page=record['full_resolution_output_files'][0].read_text()
    targets=json.loads(re.search(r'const targets = (.*);',page).group(1))
    launches=[t['bokeh']['workspace']['context'] for t in targets if t.get('bokeh')]
    assert len(launches)==1
    selected=context.validate_context(launches[0])
    assert Path(selected.files[0]).samefile(data['data_file'])
    assert launches[0]['processing']['xcorr_geometry']==direction
    source=launches[0]['processing']['input_reference']['data']
    assert [source['resolved_h1_km'],source['resolved_h2_km']]==[440.,660.]
    if source_type=='single_cube':
        assert [source['resolved_h1_index'],source['resolved_h2_index']]==[2,3]
    else:
        assert source['height_labels']==['fe5434','fe7090']
    assert Path(data['data_file']).read_bytes()==before
    assert not list((tmp_path/'Figures').rglob('*.html'))
    check_local_links(root)


def test_in_process_batch_refreshes_html_after_saving_and_preserves_other_directions(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify in process batch refreshes HTML after saving and preserves other directions.

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

    from test_td_batch import helpers,analysis_helpers
    root=tmp_path/'Figures'
    comparison(root,tmp_path,'v3','east')
    _,other=comparison(root,tmp_path,'v1','west');other.unlink()
    cfg=configuration(tmp_path);cfg['time_distance']['xcorr_geometry']='east'
    monkeypatch.setattr(helpers,'resolve_td_batch_module_dir',lambda:TD)
    def save(request,config,modules,cache):
        '''
        Purpose
        -------
        Substitute a figure writer with fixed saved-product metadata for the publication
        test.

        Inputs
        ------
        request: pytest.FixtureRequest or object
            Pytest request fixture or captured plotting request, as used by this test.

        config: dict
            Runtime configuration passed to the substituted writer.

        modules: object
            Plotting-module namespace accepted by the substituted figure writer.

        cache: dict
            Plot-data cache accepted by the substituted figure writer.

        Outputs
        -------
        result: dict
            Metadata containing the enclosing saved image path.
        '''

        _,image=comparison(root,tmp_path,'v3','annulus')
        return {'saved_file':image}
    # The actual prepared run uses Annulus; a separate East scope stays intact.
    cfg['time_distance']['xcorr_geometry']='annulus'
    runtime=SimpleNamespace(_PLOT_DEFAULTS_TEMPLATE={'komega_diagram':{}},
        load_project_modules=lambda path:{},
        prepare_runtime_config=lambda value:value,
        build_plot_requests=lambda *args,**kwargs:[{'plot_type':'field_strength_comparison'}],
        run_plot_request=save,get_figure_dir=analysis_helpers.get_figure_dir)
    result=helpers.execute_td_analysis_in_process(runtime,cfg,config_file=TD/'config.py')
    directory=root/'simulations/v3/Annulus/HTML'
    assert result['html_directories']==[str(directory)]
    assert (directory/'field_strength_comparison.html').is_file()
    assert not list((root/'simulations/v3/East').rglob('*.html'))
    assert not list((root/'simulations/v1/West').rglob('*.html'))
    assert result['component_times_seconds']['comparison_html']>=0.
    check_local_links(root)


def test_plot_notebook_execution_cell_publishes_only_the_active_scope(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify plot notebook execution cell publishes only the active scope.

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

    from test_td_batch import analysis_helpers
    import comparison_gallery as active_gallery
    monkeypatch.setitem(sys.modules,'comparison_gallery',active_gallery)
    root=tmp_path/'Figures'
    _,other=comparison(root,tmp_path,'v1','west');other.unlink()
    cfg=configuration(tmp_path)
    paths.configure_outputs(cfg)
    def save(*args):
        '''
        Purpose
        -------
        Substitute a figure writer with fixed saved-product metadata for the publication
        test.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        Outputs
        -------
        result: dict
            Metadata containing the enclosing saved image path.
        '''

        _,image=comparison(root,tmp_path,'v3','annulus')
        return {'saved_file':image}
    namespace=dict(analysis_helpers.__dict__,config=cfg,modules={},
        config_file=TD/'config.py',use_config=False,direct_plot_requests=[],
        comparison_execution_mode='load',comparison_missing_data_behavior='error',
        build_plot_requests=lambda *args,**kwargs:[{'plot_type':'field_strength_comparison'}],
        run_plot_request=save,write_profile_summary=lambda *args:None)
    notebook=json.loads((TD/'plots.ipynb').read_text())
    exec(compile(''.join(notebook['cells'][3]['source']),'plots.ipynb execution','exec'),namespace)
    directory=root/'simulations/v3/Annulus/HTML'
    assert list(namespace['gallery_outputs'])==[str(directory)]
    assert (directory/'field_strength_comparison.html').is_file()
    assert not list((root/'simulations/v1/West').rglob('*.html'))
    check_local_links(root)
