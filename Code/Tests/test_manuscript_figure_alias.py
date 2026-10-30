'''
Purpose
-------
Plot production and historical-source recovery after sharing manuscript Figures.

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

import pytest

TD=Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0,str(TD))
import figure_locations as locations
import html_output_paths as html
import output_paths as paths


@pytest.fixture
def shared(tmp_path):
    '''
    Purpose
    -------
    Create current, manuscript-alias, and archived fixture output locations.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    fixture: tuple
        Primary root, alias path, and archive root for the alias-migration case.
    '''

    # Keep current output, manuscript alias, and historical archive locations distinct.
    primary=tmp_path/'Figures';primary.mkdir()
    manuscript=tmp_path/'Morales_2025a et al';manuscript.mkdir()
    alias=manuscript/'Figures';alias.symlink_to('../Figures',target_is_directory=True)
    archive=manuscript/'Figures_backup_test';archive.mkdir()
    report=tmp_path/'Data/json_files/manuscript_figures_replacement_test.json'
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps(dict(status='verified',canonical_figures=str(primary),
        manuscript_figures=str(alias),previous_figures_backup=str(archive))))
    return primary,alias,archive


def test_current_and_legacy_roots_remain_distinct(shared,tmp_path):
    '''
    Purpose
    -------
    Verify current and legacy roots remain distinct.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    primary,alias,archive=shared
    assert locations.canonical_figure_root(alias)==primary
    assert locations.legacy_figure_root(tmp_path)==archive
    archived=archive/'Simulations/original.jpeg';archived.parent.mkdir();archived.write_bytes(b'image')
    assert locations.resolve_legacy_figure_source(alias/'Simulations/original.jpeg',tmp_path)==archived


def test_replacement_tree_in_manuscript_is_current_without_backup(shared,tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify replacement tree in manuscript is current without backup.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

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

    primary,alias,archive=shared
    alias.unlink();alias.mkdir();(alias/'simulations').mkdir()
    archive.rmdir()
    current=alias/'simulations/current.png';current.write_bytes(b'current plot')
    monkeypatch.setattr(locations,'PROJECT_ROOT',tmp_path)
    assert locations.canonical_figure_root()==alias
    assert locations.canonical_figure_root(primary)==alias
    assert locations.canonical_figure_root(alias)==alias
    assert locations.figure_project_root(alias)==tmp_path
    assert locations.legacy_figure_root(tmp_path) is None
    assert locations.resolve_legacy_figure_source(primary/'simulations/current.png',tmp_path)==current
    paths.atomic_json(paths.metadata_path(current),dict(extra={'migration_source':str(primary/'simulations/current.png')}))
    assert html._canonical_index(alias)[str(current)]==current
    # Stable historical IDs do not depend on the continued existence of a backup.
    assert locations.legacy_figure_identity_path(archive/'saved.fits',tmp_path)==alias/'saved.fits'
    custom=tmp_path/'custom/Figures';custom.mkdir(parents=True)
    assert locations.canonical_figure_root(custom)==custom


def test_alias_is_never_inferred_as_legacy_when_no_archive_is_recorded(shared,tmp_path):
    '''
    Purpose
    -------
    Verify alias is never inferred as legacy when no archive is recorded.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    primary,alias,archive=shared
    next((tmp_path/'Data/json_files').glob('*.json')).unlink()
    assert locations.legacy_figure_root(tmp_path) is None
    # Require the expected FileNotFoundError from this failure case.
    with pytest.raises(FileNotFoundError,match='No distinct legacy'):
        locations.legacy_figure_root(tmp_path,required=True)


def test_legacy_migration_and_import_refuse_to_reimport_active_outputs(shared,tmp_path):
    '''
    Purpose
    -------
    Verify legacy migration and import refuse to reimport active outputs.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from migrate_geometry_outputs import migrate
    primary,alias,archive=shared
    (primary/'simulations').mkdir()
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='active managed Figures'):
        migrate(tmp_path/'legacy_data',alias,tmp_path/'Data',figure_root=primary,apply=True)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='active Figures'):
        html.import_legacy_comparisons(alias,primary,tmp_path/'Data',TD/'config.py')


def test_historical_index_recognizes_preserved_assets(shared,tmp_path):
    '''
    Purpose
    -------
    Verify historical index recognizes preserved assets.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    primary,alias,archive=shared
    original=archive/'legacy.jpeg';original.write_bytes(b'original')
    canonical=primary/'canonical.jpeg';canonical.symlink_to(original)
    paths.atomic_json(paths.metadata_path(canonical),dict(extra={'migration_source':str(alias/'legacy.jpeg')}))
    assert html._canonical_index(primary)[str(original)]==canonical


def test_archived_assets_keep_ids_and_link_names(shared,tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify archived assets keep ids and link names.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

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
    from data_locations import current_source_path, source_identity_path
    primary,alias,archive=shared
    monkeypatch.setattr(locations,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(context,'PROJECT_DIR',tmp_path)
    archived=archive/'saved_numerical.fits';archived.write_bytes(b'saved numerical data')
    original=alias/archived.name
    managed=tmp_path/'Data/simulations/managed.fits';managed.parent.mkdir(parents=True)
    managed.symlink_to(archived)
    expected='simulation_fits:Morales_2025a et al/Figures/saved_numerical.fits'
    assert current_source_path(original)==archived
    assert source_identity_path(archived)==original
    record=dict(schema_version=1,dataset=dict(id=expected,file=str(managed),source_type='single_cube'),
        model=dict(key='nc2009',parameters=dict(a=1.,dz=220.,theta_deg=45.,phi_deg=0.)))
    assert context.validate_context(record).id==expected
    assert observation_datasets.dataset_from_fits(original,'single_cube',tmp_path).files==(archived,)
    linked=html.link_asset(archived,primary/'assets',project=tmp_path)
    assert linked.name==paths.digest(str(original))[:24]+'_'+archived.name
    assert linked.samefile(archived)


def test_fallback_navigation_does_not_scan_manuscript_alias_twice(shared,monkeypatch):
    '''
    Purpose
    -------
    Verify fallback navigation does not scan manuscript alias twice.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import comparison_gallery
    import dopplergram_recalculation as replay
    primary,alias,archive=shared
    scanned=[]
    monkeypatch.setattr(comparison_gallery,'discover_comparison_plots',lambda root:scanned.append(root) or [])
    replay._navigation_observables.cache_clear()
    assert replay._navigation_observables(str(alias))=={}
    assert scanned==[primary,archive]


def test_gallery_generation_through_alias_publishes_one_shared_set(shared,tmp_path):
    '''
    Purpose
    -------
    Verify gallery generation through alias publishes one shared set.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from test_scoped_html_outputs import comparison
    primary,alias,archive=shared
    comparison(primary,tmp_path,'v3','annulus')
    outputs=html.write_scoped_comparison_viewers(alias)
    directory=primary/'simulations/v3/Annulus/HTML'
    assert list(outputs)==[str(directory)]
    for kind in ('field_strength_comparison','field_orientation_comparison','gaussian_filter_comparison'):
        page=directory/(kind+'.html')
        assert page.is_file() and (alias/page.relative_to(primary)).samefile(page)
    assert not (primary/'HTML Figures').exists()


def test_saved_navigation_rebases_after_tree_moves_into_manuscript(shared,tmp_path):
    '''
    Purpose
    -------
    Verify saved navigation rebases after tree moves into manuscript.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from test_scoped_html_outputs import comparison,References
    from urllib.parse import unquote
    primary,alias,archive=shared
    comparison(primary,tmp_path,'v3','annulus')
    alias.unlink();primary.rename(alias);archive.rmdir()
    outputs=html.write_scoped_comparison_viewers(primary)
    assert list(outputs)==[str(alias/'simulations/v3/Annulus/HTML')]
    for page in alias.rglob('*.html'):
        parser=References();parser.feed(page.read_text())
        for reference in parser.paths:
            if '://' not in reference and not reference.startswith('#'):
                assert (page.parent/unquote(reference.split('#',1)[0])).is_file(),(page,reference)


@pytest.mark.parametrize('product,directory',[
    ('phase_difference','phase_differences'),('komega_diagram','k_omega'),
    ('time_distance','xcorr'),('spatial_phase','spatial')])
def test_notebook_plot_writer_saves_all_diagnostics_to_shared_tree(shared,tmp_path,monkeypatch,product,directory):
    '''
    Purpose
    -------
    Verify notebook plot writer saves all diagnostics to shared tree.

    Inputs
    ------
    shared: tuple
        Current, manuscript-alias, and archived output roots from the fixture.

    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    product: str
        Diagnostic product type selected by the parameterized plotting case.

    directory: pathlib.Path
        Directory against which individual-figure links are resolved.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    # Notebook saves reload their local gallery module. Restore the importing
    # test modules' instance afterward so later monkeypatches target one module.
    import comparison_gallery
    monkeypatch.setitem(sys.modules,'comparison_gallery',comparison_gallery)
    from test_td_batch import analysis_helpers
    from test_geometry_outputs import configuration
    primary,alias,archive=shared
    cfg=configuration(tmp_path);cfg['paths']['figure_dir']=str(alias)
    figure=Figure(figsize=(2,2),dpi=40);FigureCanvasAgg(figure)
    figure.subplots().plot([0.,1.],[1.,0.])
    monkeypatch.setattr(analysis_helpers,'plt',SimpleNamespace(rcParams=matplotlib.rcParams),raising=False)
    output=analysis_helpers.save_gaussian_filter_comparison_figure(figure,'synthetic_path_check.jpeg',
        figure_dir=alias,config=cfg,product=product)
    assert output.is_relative_to(primary) and output.parent.name==directory
    assert (alias/output.relative_to(primary)).samefile(output)
    record=paths.read_metadata(output)
    assert record['product']==product
    grouped=primary/paths.terminal_directory(record['identity'])/'delta_z_220_km'/directory
    images=list(grouped.glob('*.jpeg'))
    assert len(images)==1 and images[0].samefile(output)
    assert not list(archive.rglob('*.jpeg'))
