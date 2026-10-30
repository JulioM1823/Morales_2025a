'''
Purpose
-------
Source relocation, checksum integrity, and existing-cache compatibility.

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
import importlib.util
import json
import sys

import pytest

PROJECT=Path(__file__).resolve().parents[2]
TD=PROJECT/'Code/Time-Distance'
sys.path.insert(0,str(TD))
import data_locations as locations
import output_paths as paths

spec=importlib.util.spec_from_file_location('co5bold_move',PROJECT/'Code/Scripts/move_co5bold_data.py')
move=importlib.util.module_from_spec(spec);spec.loader.exec_module(move)


def source_tree(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Create a synthetic CO5BOLD source tree, destination, and relocation-manifest
    setting.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    fixture: tuple
        Source root, destination root, synthetic cube, profile, and manifest
        paths. Clear the relocation cache after patching the manifest location.
    '''

    # Create real fixture files so relocation checks can verify byte preservation.
    source=tmp_path/'original/co5bold';source.mkdir(parents=True)
    destination=tmp_path/'project/Data/co5bold';destination.parent.mkdir(parents=True)
    cube=source/'hx/10G/simulation_hx_10G.nc';cube.parent.mkdir(parents=True)
    cube.write_bytes(b'immutable synthetic cube')
    profile=source/'co5bold_1d_profiles/profile.h5';profile.parent.mkdir()
    profile.write_bytes(b'immutable synthetic profile')
    manifest=destination.parent/'json_files/co5bold_relocation.json'
    monkeypatch.setattr(locations,'RELOCATION_MANIFEST',manifest)
    locations._relocation.cache_clear()
    return source,destination,cube,profile,manifest


def test_move_preserves_every_byte_inode_timestamp_and_historical_access(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify move preserves every byte inode timestamp and historical access.

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

    source,destination,cube,profile,manifest=source_tree(tmp_path,monkeypatch)
    planned=move.plan(source,destination,manifest)
    result=move.apply(manifest)
    assert result['status']=='verified' and result['file_count']==2
    assert source.is_symlink() and source.resolve()==destination
    assert cube.read_bytes()==b'immutable synthetic cube'
    assert profile.read_bytes()==b'immutable synthetic profile'
    for row in planned['files']:
        target=destination/row['relative_path'];stat=target.stat()
        assert stat.st_ino==row['inode'] and stat.st_mtime_ns==row['mtime_ns']
        assert move.checksum(target)==row['sha256']
    original=manifest.read_bytes()
    assert move.apply(manifest)==result
    assert manifest.read_bytes()==original


def test_cloud_metadata_move_preserves_file_objects_without_reading_content(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify cloud metadata move preserves file objects without reading content.

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

    source,destination,_,_,manifest=source_tree(tmp_path,monkeypatch)
    monkeypatch.setattr(move,'checksum',lambda _:pytest.fail('Cloud content was read'))
    planned=move.plan(source,destination,manifest,metadata_only=True)
    verified=move.apply(manifest)
    assert 'content checksums not read' in verified['verification']
    for row in planned['files']:
        assert row['sha256'] is None
        assert (destination/row['relative_path']).stat().st_ino==row['inode']
    assert source.is_symlink() and source.resolve()==destination


def test_resolver_accepts_old_paths_without_alias_and_leaves_new_datasets_distinct(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify resolver accepts old paths without alias and leaves new datasets distinct.

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

    source,destination,cube,_,manifest=source_tree(tmp_path,monkeypatch)
    move.plan(source,destination,manifest);move.apply(manifest)
    current=destination/cube.relative_to(source)
    assert locations.current_source_path(cube)==current
    assert locations.source_identity_path(current)==cube
    source.unlink()  # Resolver compatibility also works without the forwarding link.
    assert locations.current_source_path(cube)==current
    assert locations.source_identity_path(current)==cube
    new=destination/'hx/10G/new_simulation.nc';new.write_bytes(b'new dataset')
    assert locations.source_identity_path(new)==new
    unrelated=tmp_path/'unrelated.nc';unrelated.write_bytes(b'unrelated')
    assert locations.source_identity_path(unrelated)==unrelated


def test_location_only_move_preserves_run_id_output_path_and_cache_reuse(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify location only move preserves run id output path and cache reuse.

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

    source,destination,cube,_,manifest=source_tree(tmp_path,monkeypatch)
    cfg=dict(data=dict(source_type='single_cube',file=str(cube),observable='v3',h1=0,h2=1,
            resolved_h1_km=0.,resolved_h2_km=220.,resolved_delta_z_km=220.),
        filtering=dict(enabled=False,filter_sequence=[],gaussian=dict(enabled=False),magnetogram=dict(enabled=False)),
        magnetogram_mode={'single_cube':'bottom'},time_distance=dict(dt=30.,p_dx_Mm=.16,xcorr_geometry='annulus'),
        paths=dict(data_output_dir=str(destination.parent),figure_dir=str(tmp_path/'Figures')))
    before=paths.build_runtime_output_paths(cfg,cfg['paths']['data_output_dir'],cfg['paths']['figure_dir'])
    run_id=before['run_id'];identity=copy.deepcopy(before['identity'])
    product=paths.build_output_file(destination.parent,cfg,'komega_diagram','diagram.fits')
    product.write_bytes(b'unchanged diagnostic data')
    paths.register_output(product,cfg,'komega_diagram')
    assert paths.can_reuse(product,cfg)
    move.plan(source,destination,manifest);move.apply(manifest)
    cfg['data']['file']=str(destination/cube.relative_to(source))
    after=paths.build_runtime_output_paths(cfg,cfg['paths']['data_output_dir'],cfg['paths']['figure_dir'])
    assert after['run_id']==run_id and after['identity']==identity
    assert paths.build_output_file(destination.parent,cfg,'komega_diagram','diagram.fits')==product
    assert paths.can_reuse(product,cfg)
    record=paths.register_output(product,cfg,'komega_diagram')
    assert record['source_locations']==[dict(identity_path=str(cube),current_path=cfg['data']['file'])]
    Path(cfg['data']['file']).write_bytes(b'changed scientific input')
    assert not paths.can_reuse(product,cfg)


def test_existing_destination_is_never_overwritten(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify existing destination is never overwritten.

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

    source,destination,cube,_,manifest=source_tree(tmp_path,monkeypatch)
    destination.mkdir();(destination/'existing.nc').write_bytes(b'existing result')
    # Require the expected FileExistsError from this failure case.
    with pytest.raises(FileExistsError):move.plan(source,destination,manifest)
    assert cube.is_file() and (destination/'existing.nc').read_bytes()==b'existing result'


def test_source_change_after_plan_prevents_move(tmp_path,monkeypatch):
    '''
    Purpose
    -------
    Verify source change after plan prevents move.

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

    source,destination,cube,_,manifest=source_tree(tmp_path,monkeypatch)
    move.plan(source,destination,manifest)
    cube.write_bytes(b'input changed after preflight inventory')
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError,match='Source changed'):move.apply(manifest)
    assert source.is_dir() and not source.is_symlink() and not destination.exists()


def test_defaults_use_the_project_data_directory():
    '''
    Purpose
    -------
    Verify defaults use the project data directory.

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

    spec=importlib.util.spec_from_file_location('relocated_configuration',TD/'config.py')
    configuration=importlib.util.module_from_spec(spec);spec.loader.exec_module(configuration)
    assert Path(configuration.co5bold_batch_root)==locations.CO5BOLD_ROOT
    assert Path(configuration.default_atmospheric_profiles['directory'])==locations.CO5BOLD_PROFILES
    for name in configuration.batch_config['single_netcdf_cube']['input_paths']:
        assert Path(name).is_relative_to(locations.CO5BOLD_ROOT)


def test_active_notebook_sources_have_no_original_co5bold_root():
    '''
    Purpose
    -------
    Verify active notebook sources have no original co5bold root.

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

    original=str(Path.home()/'Research/Projects/Morales_2025a/Data/co5bold')
    for notebook in PROJECT.joinpath('Code').rglob('*.ipynb'):
        document=json.loads(notebook.read_text())
        for cell in document['cells']:
            assert original not in ''.join(cell.get('source',[])),str(notebook)
