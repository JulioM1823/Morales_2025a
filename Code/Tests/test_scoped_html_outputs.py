'''
Purpose
-------
Regression checks for scoped galleries, shared assets, and exact launches.

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
import json
import sys
from urllib.parse import unquote
from html.parser import HTMLParser

import pytest
from PIL import Image

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import output_paths as paths
import html_output_paths as html
import comparison_gallery as gallery
from test_geometry_outputs import configuration


class References(HTMLParser):
    '''
    Purpose
    -------
    Collect HTML source and hyperlink references for output-scope tests.

    Inputs
    ------
    None
        Constructed by the test framework or its enclosing fixture.

    Outputs
    -------
    instance: References
        Fixture or test-suite object providing the documented methods.
    '''

    def __init__(self):
        '''
        Purpose
        -------
        Initialize the synthetic object state required by the enclosing test.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Store fixture values, metadata, or mutable call-recording containers on
            self.
        '''

        super().__init__(); self.paths=[]
    def handle_starttag(self, tag, attrs):
        '''
        Purpose
        -------
        Collect relevant resource paths from one HTML start tag.

        Inputs
        ------
        tag: str
            HTML start-tag name received by HTMLParser.

        attrs: list of tuple
            HTML attribute-name/value pairs received by HTMLParser.

        Outputs
        -------
        None
            Append matching src/href attribute values to the parser's reference list.
        '''

        self.paths.extend(value for key,value in attrs if key in {'src','href'} and value)


def comparison(root, tmp_path, observable, direction, indices=(0,1), categories=('hx','vx'), source_type='single_cube'):
    '''
    Purpose
    -------
    Build a scoped synthetic comparison image and its recorded per-panel sidecar.

    Inputs
    ------
    root: pathlib.Path
        Root directory containing the inputs, outputs, or cache under test.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    observable: str
        Numerical observable selected from the source cube.

    direction: str
        Directional or annulus correlation/output scope selected by the test.

    indices: tuple of int
        Indices selecting the two synthetic height levels.

    categories: sequence of str
        Model categories represented in the synthetic comparison.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    Outputs
    -------
    fixture: tuple
        Output identity records and the written comparison image path. Save
        the JSON sidecar beneath the configured shared support directory.
    '''

    # Save the shared comparison image and its exact recorded subplot context.
    cfg = configuration(tmp_path, indices=indices)
    cfg['data']['observable'] = observable
    if source_type == 'paired_cubes':
        cfg['data'].update(source_type=source_type, v1=str(tmp_path/'fe5434.fits'),
            v2=str(tmp_path/'fe7090.fits'), height_labels=['fe5434','fe7090'])
    cfg['time_distance']['xcorr_geometry'] = direction
    identity = paths.output_identity(cfg)
    identities=[]
    for category in categories:
        value=json.loads(json.dumps(identity))
        value['category']='.' if category=='.' else category+'/'+category[0]+'10G'
        identities.append(value)
    shared=html.shared_support_directory(root,identity)
    image=shared/'megaplots'/f'field_strength_comparison_{observable}_{indices[0]}_example.jpeg'
    image.parent.mkdir(parents=True,exist_ok=True)
    Image.new('RGB',(100,100),'white').save(image)
    record=dict(schema_version=1,all_axes=True,comparison_type='field_strength_comparison',height_pair_km=[0.,220.],
        html_scope=dict(identities=identities,geometry=direction),targets=[dict(id='exact-panel',label='Recorded panel',
        panelKind='figure',sourceFile=str(image),sourcePath=str(image),src='',missing=False,crop=None,
        bounds=dict(left=0,top=0,width=100,height=100),pixelBounds=dict(left=0,top=0,width=100,height=100))])
    paths.atomic_json(paths.json_sidecar_path(image,'.subplots.json'),record)
    return identities,image


def test_galleries_isolate_observable_direction_and_ordered_pair(tmp_path):
    '''
    Purpose
    -------
    Verify galleries isolate observable direction and ordered pair.

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
    first,image=comparison(root,tmp_path,'v3','east')
    comparison(root,tmp_path,'bb3','east')
    comparison(root,tmp_path,'v3','west')
    comparison(root,tmp_path,'v3','east',indices=(1,0))
    groups=html.scoped_comparison_groups(root)
    target=html.html_directory(root,first[0])
    assert len(groups)==8
    assert [p.path for p in groups[target]]==[image]
    assert '/v3/East/hx/h10G/h0_vs_h1/HTML' in str(target)


def test_shared_pages_and_every_relative_reference_resolve(tmp_path,monkeypatch):
    # Notebook helper imports can reload the module during test collection.
    '''
    Purpose
    -------
    Verify shared pages and every relative reference resolve.

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

    import comparison_gallery as active_gallery
    root=tmp_path/'Figures'
    identities,image=comparison(root,tmp_path,'v3','south')
    calls=[]
    native=active_gallery.publish_subplot_pages
    def publish(*args,**kwargs):
        '''
        Purpose
        -------
        Record the published path before delegating to the native figure writer.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        result: object
            Unchanged result from the native publication function.
        '''

        calls.append(args[0].path);return native(*args,**kwargs)
    monkeypatch.setattr(active_gallery,'publish_subplot_pages',publish)
    outputs=html.write_scoped_comparison_viewers(root)
    assert len(outputs)==1
    assert calls==[image]  # Shared across two magnetic-category entry points.
    for records in outputs.values():
        assert set(records)==set(gallery.COMPARISON_VIEWERS)
    for page in root.rglob('*.html'):
        parser=References();parser.feed(page.read_text())
        for reference in parser.paths:
            if '://' not in reference and not reference.startswith('#'):
                assert (page.parent/unquote(reference.split('#',1)[0])).is_file(),(page,reference)
    assert len(list(root.rglob('individual_figures/*.html')))==1
    assert all('/HTML/misc_files/comparison_views/' in str(p) for p in root.rglob('bokeh-launch.html'))


def test_relative_urls_preserve_managed_symlinks(tmp_path):
    '''
    Purpose
    -------
    Verify relative urls preserve managed symlinks.

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

    legacy=tmp_path/'legacy'/'original.png';legacy.parent.mkdir();legacy.write_bytes(b'image')
    alias=html.link_asset(legacy,tmp_path/'Figures/assets')
    directory=tmp_path/'Figures/scoped/HTML';directory.mkdir(parents=True)
    from comparison_gallery import relative_href
    href=relative_href(alias,directory)
    assert href=='../../assets/'+alias.name
    assert 'legacy' not in href
    assert (directory/unquote(href)).samefile(legacy)


def test_selected_subplot_gaussian_wins_over_registry(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify selected subplot gaussian wins over registry.

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

    from observation_komega_explorer import ObservationKomegaExplorer
    import observation_komega_explorer as module
    parameters=dict(central_k=.75,width_k=2.25,central_f=3.,width_f=2.)
    pair=ObservationKomegaExplorer.__new__(ObservationKomegaExplorer)
    pair.filter=SimpleNamespace(defaults=dict(parameters,central_k=9.))
    pair.launch_context=dict(dataset={'id':'selected'},processing={'input_reference':{'filtering':
        dict(enabled=True,filter_sequence=['gaussian'],gaussian=dict(parameters,enabled=True))}})
    data=SimpleNamespace(observation=SimpleNamespace(id='selected',label='selected'),
        geometry=SimpleNamespace(nx=8,nt=24,dt_seconds=10.,dx_Mm=.2),ny=8)
    monkeypatch.setattr(module,'read_registry',lambda *a:pytest.fail('Selected subplot fell back to registry'))
    params,sampling,message,error=pair._load_settings(data)
    assert params==parameters and not error
    assert sampling['nt']==24 and 'selected subplot' in message


def test_missing_scope_is_an_explicit_error(tmp_path):
    '''
    Purpose
    -------
    Verify missing scope is an explicit error.

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

    root=tmp_path/'Figures';identities,image=comparison(root,tmp_path,'v2','north')
    sidecar=paths.json_sidecar_path(image,'.subplots.json');record=json.loads(sidecar.read_text())
    del record['html_scope'];paths.atomic_json(sidecar,record)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='explicit HTML scope'):
        html.write_scoped_comparison_viewers(root)


def test_launch_rejects_changed_filter_and_direction(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify launch rejects changed filter and direction.

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

    import observation_datasets
    import komega_bokeh_context as context
    product=tmp_path/'exact.fits';product.write_bytes(b'placeholder')
    observation=SimpleNamespace(id='exact',files=(product,))
    monkeypatch.setattr(observation_datasets,'dataset_from_fits',lambda *a:observation)
    reference=dict(schema_version=1,data={'source_type':'paired_cubes'},filtering={'enabled':False},
        time_distance={'xcorr_geometry':'west', 'dx_pixels':1.0})
    paths.atomic_json(paths.json_sidecar_path(product,'.inputs.json'),reference)
    value=dict(schema_version=1,dataset=dict(id='exact',file=str(product),source_type='paired_cubes'),
        model=dict(key='nc2009',parameters={}),processing=dict(input_reference=reference,xcorr_geometry='west'))
    assert context.validate_context(value) is observation
    reference['time_distance']['dx_pixels']=1
    assert context.validate_context(value) is observation  # JSON 1 and 1.0 represent the same processing value.
    changed=json.loads(json.dumps(value));changed['processing']['input_reference']['filtering']['enabled']=True
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='no longer matches'):
        context.validate_context(changed)
    changed=json.loads(json.dumps(value));changed['processing']['xcorr_geometry']='east'
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='direction disagrees'):
        context.validate_context(changed)


def test_observation_namespace_relocation_preserves_links(tmp_path):
    '''
    Purpose
    -------
    Verify observation namespace relocation preserves links.

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

    source=tmp_path/'legacy.fits';source.write_bytes(b'scientific content')
    old=tmp_path/'Data/observations/East/fe5434_vs_fe7090/k_omega/example.fits'
    paths._ensure_link(old,source)
    sidecar=paths.json_sidecar_path(old,'.metadata.json');paths.atomic_json(sidecar,{'original':True})
    grouped=tmp_path/'Data/observations/East/delta_z_220_km/k_omega/001.fits'
    paths._ensure_link(grouped,old)
    assert html.relocate_observation_directories(tmp_path/'Data')==3
    current=tmp_path/'Data/observations/doppler_velocity/East/fe5434_vs_fe7090/k_omega/example.fits'
    assert current.samefile(source)
    assert paths.read_metadata(current)=={'original':True}
    assert (tmp_path/'Data/observations/doppler_velocity/East/delta_z_220_km/k_omega/001.fits').samefile(source)
    assert html.relocate_observation_directories(tmp_path/'Data')==0


def test_product_validation_uses_metadata_and_ignores_support_folder_name(tmp_path):
    '''
    Purpose
    -------
    Verify product validation uses metadata and ignores support folder name.

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

    source=tmp_path/'HTML/misc_files/comparison_views/opaque__run_0123456789abcdef01234567.jpeg'
    source.parent.mkdir(parents=True);source.write_bytes(b'image')
    paths.atomic_json(paths.metadata_path(source),{'product':'phase_difference'})
    target=dict(sourceFile=str(source),panelKind='phase_diff')
    assert gallery._target_matches_declared_kind(target)
    target['panelKind']='komega'
    assert not gallery._target_matches_declared_kind(target)
    legacy=source.parent/'dataset_komega.jpeg';legacy.write_bytes(b'image')
    assert gallery._target_matches_declared_kind(dict(sourceFile=str(legacy),panelKind='komega'))


def test_observation_galleries_use_quantity_and_ordered_lines(tmp_path):
    '''
    Purpose
    -------
    Verify observation galleries use quantity and ordered lines.

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
    identities,image=comparison(root,tmp_path,'doppler_velocity','north',categories=('.',),source_type='paired_cubes')
    outputs=html.write_scoped_comparison_viewers(root)
    directory=html.megaplot_html_directory(root,identities[0])
    assert directory==root/'observations/doppler_velocity/North/HTML'
    assert str(directory) in outputs
    assert all(record['output_file'].is_file() for record in outputs[str(directory)].values())


def test_mixed_observable_scope_is_rejected(tmp_path):
    '''
    Purpose
    -------
    Verify mixed observable scope is rejected.

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

    root=tmp_path/'Figures';identities,image=comparison(root,tmp_path,'v2','north')
    sidecar=paths.json_sidecar_path(image,'.subplots.json');record=json.loads(sidecar.read_text())
    record['html_scope']['identities'][1]['observable']='bb3'
    paths.atomic_json(sidecar,record)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='mixes unrelated'):
        html.scoped_comparison_groups(root)


def test_observational_launch_uses_recorded_height_separation(tmp_path):
    '''
    Purpose
    -------
    Verify observational launch uses recorded height separation.

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

    from test_komega_bokeh_integration import sample
    from komega_bokeh_context import publish_context
    from komega_explorer import KomegaExplorer
    from bokeh.document import Document
    data,cfg=sample(tmp_path,'paired_cubes')
    cfg['data']['resolved_delta_z_km']=100.
    record=publish_context(tmp_path/'pair.jpeg',data,cfg)
    explorer=KomegaExplorer(Document(),launch_context=record['context'],schedule_initial=False)
    assert all(section.widgets['dz'].value==100. for section in explorer.models if 'dz' in section.widgets)


def test_mega_entry_pages_are_at_direction_html_and_include_all_pairs(tmp_path):
    '''
    Purpose
    -------
    Verify mega entry pages are at direction HTML and include all pairs.

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
    comparison(root,tmp_path,'v3','annulus')
    comparison(root,tmp_path,'v3','annulus',indices=(1,0))
    outputs=html.write_scoped_comparison_viewers(root)
    directory=root/'simulations/v3/Annulus/HTML'
    assert list(outputs)==[str(directory)]
    for kind in gallery.COMPARISON_VIEWERS:
        assert (directory/(kind+'.html')).is_file()
    records=outputs[str(directory)]['field_strength_comparison']
    assert records['plot_count']==2
    assert all('/misc_files/comparison_views/' in str(p) for p in records['full_resolution_output_files'])


def test_regeneration_can_target_one_observable_and_direction(tmp_path):
    '''
    Purpose
    -------
    Verify regeneration can target one observable and direction.

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
    comparison(root,tmp_path,'v3','annulus')
    comparison(root,tmp_path,'v3','east')
    comparison(root,tmp_path,'v1','annulus')
    untouched=root/'simulations/v3/East/HTML/field_strength_comparison.html'
    untouched.parent.mkdir(parents=True,exist_ok=True);untouched.write_text('existing east gallery')
    outputs=html.write_scoped_comparison_viewers(root,scope='simulations/v3/Annulus')
    assert list(outputs)==[str(root/'simulations/v3/Annulus/HTML')]
    assert untouched.read_text()=='existing east gallery'
    assert not list((root/'simulations/v1/Annulus').rglob('*.html'))


def test_missing_recorded_image_does_not_replace_existing_gallery(tmp_path):
    '''
    Purpose
    -------
    Verify missing recorded image does not replace existing gallery.

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
    _,image=comparison(root,tmp_path,'v3','annulus')
    image.unlink()
    page=root/'simulations/v3/Annulus/HTML/field_strength_comparison.html'
    page.parent.mkdir(parents=True,exist_ok=True);page.write_text('previous gallery')
    # Require the expected FileNotFoundError from this failure case.
    with pytest.raises(FileNotFoundError,match='HTML was not regenerated'):
        html.write_scoped_comparison_viewers(root,scope='simulations/v3/Annulus')
    assert page.read_text()=='previous gallery'


def test_html_scope_cannot_escape_its_figure_root(tmp_path):
    '''
    Purpose
    -------
    Verify HTML scope cannot escape its figure root.

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

    root=tmp_path/'Figures';root.mkdir()
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='inside the managed figure root'):
        html.write_scoped_comparison_viewers(root,scope='../unrelated')
