'''
Purpose
-------
CLI coverage and dispatch tests; no scientific pipeline is executed.

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
import ast
import re
import sys
from pathlib import Path

import netCDF4
import numpy as np
import pytest

TD = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(TD))
import pipeline as td
import output_paths


def cube(path, fields, heights):
    '''
    Purpose
    -------
    Write a tiny netCDF cube containing selected observables and explicit height
    coordinates.

    Inputs
    ------
    path: pathlib.Path
        Input or output path used by this fixture or its local substitute.

    fields: sequence of str
        Observable names to include in the synthetic cube.

    heights: sequence of float
        Physical heights of the synthetic cube levels (km).

    Outputs
    -------
    path: pathlib.Path
        Written source cube; include a one-dimensional unsupported profile
        variable to exercise observable validation.
    '''

    # Include supported cube observables and an unsupported one-dimensional profile.
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, 'w') as dataset:
        for name, size in [('time', 2), ('xc3', len(heights)), ('xc2', 2), ('xc1', 2)]:
            dataset.createDimension(name, size)
        z = dataset.createVariable('xc3', 'f8', ('xc3',))
        z.units = 'km'
        z[:] = heights
        for name in fields:
            field = dataset.createVariable(name, 'f4', ('time', 'xc3', 'xc2', 'xc1'))
            if name in ('pressure', 'pgas'):
                field.units = 'dyn/cm^2'
        # A profile is not a supported time-dependent observable.
        dataset.createVariable('temperature_profile', 'f4', ('xc3',))
    return path


@pytest.fixture
def workspace(tmp_path):
    '''
    Purpose
    -------
    Create a CLI workspace with magnetic/reference cubes, duplicate links, and a hidden
    input.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    fixture: tuple
        Config file, source root, magnetic cube, reference cube, and hidden cube.
    '''

    # Construct visible, hidden, and duplicate source paths for the CLI discovery
    # checks.
    root = tmp_path / 'cubes'
    magnetic = cube(root / 'hx/10G/magnetic.nc', ['v1', 'bb1', 'ei'], [0., 220., 660.])
    reference = cube(root / 'z0/0G/reference.nc', ['v1', 'ei'], [0., 220.])
    (root / 'duplicate.nc').symlink_to(magnetic)
    hidden = cube(root / '.cache/ignored.nc', ['v1'], [0., 220.])
    config_file = tmp_path / 'config.py'
    source = (TD / 'config.py').read_text()
    source = re.sub(r'^project_dir = .*$', lambda _: f'project_dir = {str(tmp_path)!r}', source, flags=re.M)
    source += (f'\nco5bold_batch_root = {str(root)!r}\n'
               f'single_cube_inputs.update(file_path={str(magnetic)!r}, h1=0, h2=1)\n')
    config_file.write_text(source)
    return config_file, root, magnetic, reference, hidden


SWEEP = ['--all-simulations', '--all-observables', '--all-height-pairs',
         '--all-geometries', '--default-gaussian', '--no-magnetogram', '--skip-existing']


def test_complete_sweep_has_no_duplicates_or_missing_field_substitutes(workspace):
    '''
    Purpose
    -------
    Verify complete sweep has no duplicates or missing field substitutes.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, root, magnetic, reference, hidden = workspace
    plan = td.build_cli_run_configs(config_file, td.parse_cli_args(SWEEP))
    keys = set()
    for config in plan:
        data = config['data']['single_cube']
        key = (data['file'], data['observable'], data['h1'], data['h2'], config['time_distance']['xcorr_geometry'])
        assert key not in keys
        keys.add(key)
        assert data['h1'] < data['h2']
        assert data['file'] != str(hidden)
        if data['file'] == str(reference):
            assert data['observable'] in ('v1', 'ei')
        assert config['optimized_filtering'] == {'mode': 'manual'}
        assert config['filtering']['filter_sequence'] == ['gaussian']
        assert config['filtering']['gaussian'] == dict(enabled=True, central_k=1.5, width_k=4., central_f=3., width_f=3.)
        assert config['filtering']['magnetogram']['enabled'] is False
        assert config['output']['reuse'] is True
        assert Path(config['paths']['data_output_dir']) == config_file.parent / 'Data'
        assert Path(config['paths']['figure_dir']) == config_file.parent / 'Figures'
    assert len(plan) == len(keys) == 55  # (3 fields x 3 pairs + 2 fields x 1 pair) x 5 geometries
    assert td.discover_simulation_files(root) == sorted([str(magnetic), str(reference)])


def test_dry_run_uses_real_cli_without_preparation_or_execution(workspace, monkeypatch, capsys):
    '''
    Purpose
    -------
    Verify dry run uses real CLI without preparation or execution.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    capsys: pytest.CaptureFixture
        Fixture capturing standard output and error for assertions.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, _, _, _, _ = workspace
    def forbidden(*args, **kwargs):
        '''
        Purpose
        -------
        Fail if the CLI dry run attempts scientific preparation or execution.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        None
            Always fail the test through pytest.fail().
        '''

        pytest.fail('Dry run attempted to prepare or execute scientific outputs.')
    monkeypatch.setattr(td, 'prepare_runtime_config', forbidden)
    monkeypatch.setattr(td, 'run_time_distance', forbidden)
    assert td.main(['--config', str(config_file), *SWEEP, '--dry-run']) == 0
    assert 'Planned 55 unique time-distance runs.' in capsys.readouterr().out
    assert not (config_file.parent / 'Data').exists()
    assert not (config_file.parent / 'Figures').exists()


def test_sweep_dispatches_each_configuration_once(workspace, monkeypatch, capsys):
    '''
    Purpose
    -------
    Verify sweep dispatches each configuration once.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    capsys: pytest.CaptureFixture
        Fixture capturing standard output and error for assertions.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, _, _, _, _ = workspace
    dispatched = []
    def fake_run(*, config_file, config_override):
        '''
        Purpose
        -------
        Capture a dispatched CLI configuration and return minimal result metadata.

        Inputs
        ------
        config_file: str or pathlib.Path
            Python configuration file used to build the runtime settings.

        config_override: dict or None
            Configuration overrides accepted by the pipeline substitute.

        Outputs
        -------
        result: dict
            Fixed output names and empty one-element correlation/phase arrays.
        '''

        dispatched.append(config_override)
        return dict(outfile='xc.fits', phase_outfile='phase.fits', xc=np.empty((1,)), phase_diff=np.empty((1,)))
    monkeypatch.setattr(td, 'run_time_distance', fake_run)
    assert td.main(['--config', str(config_file), *SWEEP]) == 0
    assert len(dispatched) == 55
    capsys.readouterr()
    assert not (config_file.parent / 'Data').exists()


def test_single_run_defaults_and_batch_namespaces_remain_compatible(workspace):
    '''
    Purpose
    -------
    Verify single run defaults and batch namespaces remain compatible.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, _, magnetic, _, _ = workspace
    original = td.load_time_distance_config(config_file)
    plan = td.build_cli_run_configs(config_file, td.parse_cli_args([]))
    assert len(plan) == 1
    assert plan[0]['filtering'] == original['filtering']
    assert plan[0]['optimized_filtering'] == original['optimized_filtering']
    assert plan[0]['data']['single_cube']['file'] == str(magnetic)
    args = td.parse_cli_args([])
    for name in ('all_simulations', 'simulation_root', 'all_observables', 'all_height_pairs',
                 'geometry', 'all_geometries', 'default_gaussian', 'no_magnetogram', 'skip_existing', 'dry_run'):
        delattr(args, name)
    assert td.iter_run_configs(original, args) == plan


def test_repeated_explicit_inputs_are_deduplicated(workspace):
    '''
    Purpose
    -------
    Verify repeated explicit inputs are deduplicated.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, root, magnetic, _, _ = workspace
    args = td.parse_cli_args(['--file', str(magnetic), '--file', str(root / 'duplicate.nc'),
                              '--height-pair', '0', '1', '--height-pair', '0', '1',
                              '--geometry', 'East', '--geometry', 'east'])
    plan = td.build_cli_run_configs(config_file, args)
    assert len(plan) == 1
    assert plan[0]['time_distance']['xcorr_geometry'] == 'east'


def test_source_override_and_geometry_expansion(workspace):
    '''
    Purpose
    -------
    Verify source override and geometry expansion.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, _, _, _, _ = workspace
    plan = td.build_cli_run_configs(config_file, td.parse_cli_args(['--source-type', 'paired_cubes', '--all-geometries']))
    assert len(plan) == 5
    assert all(config['data']['source_type'] == 'paired_cubes' for config in plan)
    config_file.write_text(config_file.read_text().replace("source_type = 'single_cube'", "source_type = 'paired_cubes'"))
    plan = td.build_cli_run_configs(config_file, td.parse_cli_args(SWEEP))
    assert len(plan) == 55
    assert all(config['data']['source_type'] == 'single_cube' for config in plan)


@pytest.mark.parametrize('arguments', [
    ['--all-simulations', '--file', 'cube.nc'],
    ['--all-observables', '--observable', 'v3'],
    ['--all-geometries', '--geometry', 'north'],
    ['--all-height-pairs', '--height-pair', '0', '1'],
    ['--all-height-pairs', '--h1', '0'],
    ['--simulation-root', '/tmp'],
    ['--all-simulations', '--source-type', 'paired_cubes'],
])
def test_conflicting_cli_arguments_are_rejected(arguments):
    '''
    Purpose
    -------
    Verify conflicting CLI arguments are rejected.

    Inputs
    ------
    arguments: sequence of str
        Command-line tokens for the rejection case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    # Require the expected SystemExit from this failure case.
    with pytest.raises(SystemExit):
        td.parse_cli_args(arguments)


@pytest.mark.parametrize('flag', ['--all-observables', '--all-height-pairs'])
def test_simulation_coverage_cannot_be_applied_to_observations(workspace, flag):
    '''
    Purpose
    -------
    Verify simulation coverage cannot be applied to observations.

    Inputs
    ------
    workspace: tuple
        Synthetic CLI configuration, cube root, and visible/hidden input files.

    flag: str
        CLI option passed to the coverage-validation case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config_file, _, _, _, _ = workspace
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='single_cube-only'):
        td.build_cli_run_configs(config_file, td.parse_cli_args(['--source-type', 'paired_cubes', flag]))


def test_discovery_reports_missing_or_empty_sources(tmp_path):
    '''
    Purpose
    -------
    Verify discovery reports missing or empty sources.

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

    # Require the expected NotADirectoryError from this failure case.
    with pytest.raises(NotADirectoryError):
        td.discover_simulation_files(tmp_path / 'missing')
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='No simulation NetCDF'):
        td.discover_simulation_files(tmp_path)
    path = cube(tmp_path / 'empty.nc', [], [0., 220.])
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='No 4D observables'):
        td.infer_netcdf_observables(path)


def test_observable_aliases_do_not_repeat_the_same_selected_field(tmp_path):
    '''
    Purpose
    -------
    Verify observable aliases do not repeat the same selected field.

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

    path = cube(tmp_path / 'pressure.nc', ['pressure', 'pgas', 'ei'], [0., 220.])
    names = td.infer_netcdf_observables(path)
    assert len(names) == 2
    assert {td.normalize_observable_slug(name) for name in names} == {'pressure', 'ei'}


def test_cli_helpers_do_not_invalidate_scientific_cache_fingerprints(tmp_path):
    '''
    Purpose
    -------
    Verify CLI helpers do not invalidate scientific cache fingerprints.

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

    path = tmp_path / 'pipeline.py'
    original = (TD / 'pipeline.py').read_text()
    path.write_text(original)
    def fingerprint():
        '''
        Purpose
        -------
        Compute the current implementation fingerprint from the selected source-file
        signature.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        version: str
            Version returned by output_paths._implementation_version().
        '''

        stat = path.stat()
        return output_paths._implementation_version(((str(path), stat.st_size, stat.st_mtime_ns),))
    before = fingerprint()
    tree = ast.parse(original)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in (
            'discover_simulation_files', 'infer_netcdf_observables', 'build_cli_run_configs'
        ):
            node.body = [ast.Pass()]
    path.write_text(ast.unparse(tree))
    assert fingerprint() == before
    path.write_text(ast.unparse(tree) + '\ndef scientific_change():\n    return 1\n')
    assert fingerprint() != before
