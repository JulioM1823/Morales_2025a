'''
Purpose
-------
Relocation, setup, and packaging contracts without changing scientific inputs.

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
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import portable_paths as paths
import portable_runtime as runtime
import package_komega_tools as packaging
import portable_launcher as launcher


def test_environment_refusal_creates_nothing(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify environment refusal creates nothing.

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

    (tmp_path/'requirements-portable.txt').write_text('example==1\n')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    with patch.object(launcher.venv, 'EnvBuilder') as builder:
        with pytest.raises(RuntimeError, match='Setup cancelled'):
            launcher.provision(tmp_path)
        builder.assert_not_called()
    assert not (tmp_path/'.local').exists()


def test_environment_install_failure_does_not_mark_setup_complete(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify environment install failure does not mark setup complete.

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

    (tmp_path/'requirements-portable.txt').write_text('example==1\n')
    (tmp_path/'.local').mkdir()
    (tmp_path/'.local/requirements-installed.txt').write_text('example==1\n')
    monkeypatch.setattr('builtins.input', lambda _: 'yes')
    def create(environment):
        '''
        Purpose
        -------
        Simulate private-environment creation for the setup-failure test.

        Inputs
        ------
        environment: pathlib.Path
            Private Python-environment path passed to the installation substitute.

        Outputs
        -------
        None
            Create the fixture path/state used before the intentionally failed install.
        '''

        target = environment/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        target.parent.mkdir(parents=True)
        target.write_text('test interpreter')
    with patch.object(launcher.venv, 'EnvBuilder') as builder:
        builder.return_value.create.side_effect = create
        with patch.object(launcher.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pip')):
            with pytest.raises(subprocess.CalledProcessError):
                launcher.provision(tmp_path)
    assert not (tmp_path/'.local/requirements-installed.txt').exists()


def test_complete_private_environment_is_reused_without_prompt(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify complete private environment is reused without prompt.

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

    requirements = b'# fixture requirements\n'
    (tmp_path/'requirements-portable.txt').write_bytes(requirements)
    python = tmp_path/'.local/venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    (tmp_path/'.local/requirements-installed.txt').write_bytes(requirements)
    def unexpected(*args, **kwargs):
        '''
        Purpose
        -------
        Fail if the private-environment reuse path attempts an unnecessary setup
        operation.

        Inputs
        ------
        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        None
            Always raise the assertion in this test substitute.
        '''

        raise AssertionError('Completed setup must not prompt or reinstall')
    monkeypatch.setattr('builtins.input', unexpected)
    monkeypatch.setattr(launcher.venv, 'EnvBuilder', unexpected)
    assert launcher.provision(tmp_path) == python
    (tmp_path/'requirements-portable.txt').write_text('changed==2\n')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    # Require the expected RuntimeError from this failure case.
    with pytest.raises(RuntimeError, match='Setup cancelled'):
        launcher.provision(tmp_path)
    assert (tmp_path/'.local/requirements-installed.txt').read_bytes() == requirements


@pytest.mark.skipif(os.name == 'nt', reason='POSIX launcher')
def test_native_launcher_decline_without_any_python(tmp_path):
    '''
    Purpose
    -------
    Verify native launcher decline without any python.

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

    bundle, commands = tmp_path/'Tools with spaces', tmp_path/'commands'
    bundle.mkdir()
    commands.mkdir()
    shutil.copy2(TD/'portable_start.sh', bundle/'Start Tools.sh')
    (commands/'dirname').symlink_to(shutil.which('dirname'))
    # Restrict discovery to a PATH with no Python, curl, wget, or uv.
    result = subprocess.run(['/bin/sh', str(bundle/'Start Tools.sh'), '--setup-only'],
        input='n\n', text=True, capture_output=True, env=dict(os.environ, PATH=str(commands)))
    assert result.returncode == 1
    assert 'download Python 3.11' in result.stdout
    assert 'Setup cancelled' in result.stdout
    assert not (bundle/'.local').exists()


def make_bundle(root, data):
    '''
    Purpose
    -------
    Write the minimal portable-bundle configuration and dataset record for HTTP setup
    tests.

    Inputs
    ------
    root: pathlib.Path
        Root directory containing the inputs, outputs, or cache under test.

    data: object
        Synthetic variable data, registry record, or external data root for the current
        helper.

    Outputs
    -------
    record: dict
        Saved dataset/context record associated with the fixture bundle.
    '''

    # Create a minimal portable installation with recorded numerical input metadata.
    data.mkdir(parents=True, exist_ok=True)
    (data/'co5bold').mkdir(exist_ok=True)
    record = dict(package_id='test-package', original_project='/original/Morales_2025a',
        files={'/old/phase.fits': 'Data/recorded_products/phase.fits'},
        identities={'Data/recorded_products/phase.fits': '/original/Morales_2025a/Data/phase.fits'},
        data_files={}, data_identities={'co5bold/cube.nc': '/original/raw/cube.nc'},
        external_roots=[{'source':'/original/Morales_2025a/Data','kind':'data'}],
        required_data=[{'relative':'co5bold/cube.nc','size_bytes':4}])
    root.mkdir(parents=True, exist_ok=True)
    (root/'portable-manifest.json').write_text(json.dumps(record))
    return record


def test_paths_and_identifiers_survive_an_unrelated_location(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify paths and identifiers survive an unrelated location.

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

    root, data = tmp_path/'Tools space', tmp_path/'Somewhere else/Δ Data'
    make_bundle(root, data)
    (data/'co5bold/cube.nc').write_bytes(b'data')
    monkeypatch.setenv('MORALES_PORTABLE_ROOT', str(root))
    runtime.save_directory(str(data))
    assert paths.resolve_path('/original/Morales_2025a/Data/co5bold/cube.nc') == data/'co5bold/cube.nc'
    assert paths.resolve_path(root/'Data/co5bold/cube.nc') == data/'co5bold/cube.nc'
    assert paths.resolve_path('Data/co5bold/cube.nc') == data/'co5bold/cube.nc'
    assert paths.identifier('simulation_fits', [root/'Data/recorded_products/phase.fits']) == 'simulation_fits:Data/phase.fits'
    assert paths.identity_path(data/'co5bold/cube.nc') == Path('/original/raw/cube.nc')
    original = {'file':'/original/Morales_2025a/Data/co5bold/cube.nc','h1':0,'h2':2}
    saved = copy.deepcopy(original)
    assert paths.remap_data(original)['file'] == str(data/'co5bold/cube.nc')
    assert original == saved
    for invalid in ('../secrets', '/absolute'):
        with pytest.raises(ValueError):
            paths._safe_join(root, invalid)


def test_data_validation_and_saved_setting(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify data validation and saved setting.

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

    root, data = tmp_path/'Tools', tmp_path/'Data'
    make_bundle(root, data)
    monkeypatch.setenv('MORALES_PORTABLE_ROOT', str(root))
    assert runtime.save_directory(str(data)) == ['co5bold/cube.nc']
    assert paths.settings()['data_directory'] == str(data)
    (data/'co5bold/cube.nc').write_bytes(b'data')
    assert runtime.validate_directory(str(data))[1] == []
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='containing co5bold'):
        runtime.save_directory(str(data/'co5bold'))
    assert paths.data_directory() == data


def test_research_checkout_does_not_activate_portable_mode(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify research checkout does not activate portable mode.

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

    monkeypatch.delenv('MORALES_PORTABLE_ROOT', raising=False)
    value = {'file':'/untouched/input.nc'}
    assert paths.remap_data(value) is value
    assert paths.resolve_path('/untouched/input.nc') == Path('/untouched/input.nc')
    assert paths.identifier('fits', [tmp_path/'phase.fits']) is None


def test_every_packaged_html_gets_setup_and_bridge_uses_actual_port(tmp_path, monkeypatch):
    '''
    Purpose
    -------
    Verify every packaged HTML gets setup and bridge uses actual port.

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

    project = tmp_path/'project'
    figures, data = project/'Figures', project/'Data'
    figures.mkdir(parents=True)
    (data/'co5bold').mkdir(parents=True)
    (figures/'field_strength_comparison.html').write_text('<html><body><img src="plot.png"></body></html>')
    (figures/'bokeh-launch.html').write_text('old bridge')
    (figures/'plot.png').write_bytes(b'example-image')
    solver = tmp_path/'Vesa_2026/Code/diagnostic_diagram'
    solver.mkdir(parents=True)
    for name in ('config.py', 'functions.py', 'interactive_models.py', 'interactive_bokeh.py',
                 'numeric_controls.py', 'magnetic_geometry.py'):
        (solver/name).write_text('# Fixture solver source\n')
    # Keep the packaging contract independent of cloud-backed research exports.
    modules = tmp_path/'modules'
    modules.mkdir()
    for name in ('portable_bootstrap.js', 'requirements-portable.txt', 'portable_start.sh',
                 'portable_start.ps1', 'portable_start.bat', 'portable_README.md'):
        shutil.copy2(TD/name, modules/name)
    for name in ('integrated_komega_bokeh_app', 'magnetogram_bokeh_app', 'komega_exports'):
        (modules/name).mkdir()
    (modules/'komega_exports/saved.html').write_text('<html><body>Saved Bokeh export</body></html>')
    monkeypatch.setattr(packaging, 'TD', modules)
    result = packaging.build(tmp_path/'download', project=project, archive=False)
    assert result['html_pages'] >= 3
    for page in (tmp_path/'download').rglob('*.html'):
        text = page.read_text()
        assert 'portable-bootstrap.js' in text
        assert result['package_id'] in text
    bridge = (tmp_path/'download/Figures/bokeh-launch.html').read_text()
    assert 'MoralesPortable.rebase(target)' in bridge
    assert '5013' not in bridge
    assert (tmp_path/'download/Figures/plot.png').read_bytes() == b'example-image'
    assert not (tmp_path/'download/.local').exists()


class TestSetupHTTP(AsyncHTTPTestCase):
    '''
    Purpose
    -------
    Exercise portable setup routes through an isolated Tornado HTTP test application.

    Inputs
    ------
    None
        Constructed by the test framework or its enclosing fixture.

    Outputs
    -------
    instance: TestSetupHTTP
        Fixture or test-suite object providing the documented methods.
    '''

    def setUp(self):
        '''
        Purpose
        -------
        Prepare the temporary bundle and initialize the HTTP test server.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Store fixture state and start the inherited HTTP test application.
        '''

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/'Tools'
        self.data = Path(self.temporary.name)/'Data'
        make_bundle(self.root, self.data)
        self.env = patch.dict('os.environ', {'MORALES_PORTABLE_ROOT':str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        (self.root/'index.html').write_text('Test page')
        (self.root/'.secret').write_text('private')
        super().setUp()

    def tearDown(self):
        '''
        Purpose
        -------
        Stop the HTTP test server and release temporary fixture resources.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Invoke inherited cleanup and release the fixture temporary directory.
        '''

        super().tearDown()
        self.env.stop()
        self.temporary.cleanup()

    def get_app(self):
        '''
        Purpose
        -------
        Construct the Tornado application using the portable runtime setup routes.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        application: tornado.web.Application
            Application served by the HTTP test fixture.
        '''

        return Application(runtime.routes())

    def test_first_open_save_reopen_and_hostile_origin(self):
        '''
        Purpose
        -------
        Verify first open save reopen and hostile origin.

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

        state = self.fetch('/portable/status', headers={'Origin':'null'})
        assert state.headers['Access-Control-Allow-Origin'] == 'null'
        assert json.loads(state.body)['configured'] is False
        form = self.fetch('/setup')
        token = re.search(r'const token = "([^"]+)"', form.body.decode())[1]
        body = json.dumps({'data_directory':str(self.data)})
        hostile = self.fetch('/portable/configure', method='POST', body=body,
            headers={'Origin':'https://unrelated.invalid','X-Morales-Token':token})
        assert hostile.code == 403
        saved = self.fetch('/portable/configure', method='POST', body=body,
            headers={'Origin':self.get_url('').rstrip('/'),'X-Morales-Token':token})
        assert saved.code == 200
        assert json.loads(saved.body)['missing'] == ['co5bold/cube.nc']
        assert json.loads(self.fetch('/portable/status').body)['configured'] is True
        assert self.fetch('/files/index.html').body == b'Test page'
        assert self.fetch('/files/.secret').code == 403
