'''
Purpose
-------
Provision and launch an extracted portable tools bundle using its private environment
and loopback service.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for portable_launcher.py.

Notes
-----
Start an extracted portable bundle, provisioning its own environment once.
'''
# Import the libraries and shared helpers used by this module
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import venv
import webbrowser


def provision(root, *, approved=False):
    '''
    Purpose
    -------
    Reuse or provision the bundle-local supported Python environment after setup
    consent.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    approved: bool
        Existing explicit setup consent; otherwise this operation prompts on standard
        input before installing.

    Outputs
    -------
    python: pathlib.Path
        Private Python executable after installing and checking requirements. Missing
        consent or unsupported bootstrap interpreters raise RuntimeError; installation
        failures propagate.

    Notes
    -----
    Install only inside the extracted bundle, after explicit setup consent.
    '''
    # Reuse or provision the bundle-local supported Python environment after setup
    # consent
    local = root/'.local'
    environment = local/'venv'
    python = environment/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    requirements = root/'requirements-portable.txt'
    marker = local/'requirements-installed.txt'
    usable = python.is_file() and subprocess.run(
        [str(python), '-I', '-c', 'import sys; sys.exit(sys.version_info[:2] not in {(3,10),(3,11)})'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if usable and marker.is_file() and marker.read_bytes() == requirements.read_bytes():
        return python
    if not approved:
        print('Morales Tools needs a private Python 3.10/3.11 environment and its scientific libraries.\n'
              'Setup downloads the libraries from PyPI into this tools folder (.local).\n'
              'Your other Python environments and system settings will stay unchanged.\n'
              'Internet access is required for downloads.', flush=True)
        try:
            approved = input('Allow environment setup? [y/N] ').strip().lower() in {'y', 'yes'}
        except EOFError:
            approved = False
    if not approved:
        raise RuntimeError('Setup cancelled. No environment or libraries were installed.')
    # A failed rebuild must never reuse an earlier environment's success marker.
    marker.unlink(missing_ok=True)
    if not usable:
        if sys.version_info[:2] not in {(3, 10), (3, 11)}:
            raise RuntimeError('Run the platform Start Tools launcher to obtain Python 3.11 automatically.')
        print('Creating the private Python environment…', flush=True)
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    print('Installing the required scientific libraries…', flush=True)
    # Ignore global pip configuration and never install into the invoking interpreter.
    subprocess.run([str(python), '-I', '-m', 'pip', '--isolated', 'install',
                    '--disable-pip-version-check', '--only-binary=:all:',
                    '--cache-dir', str(local/'pip-cache'),
                    '--index-url', 'https://pypi.org/simple', '-r', str(requirements)], check=True)
    subprocess.run([str(python), '-I', '-m', 'pip', '--isolated', 'check'], check=True)
    marker.write_bytes(requirements.read_bytes())
    return python


def status(origin, package_id):
    '''
    Purpose
    -------
    Check whether a local portable service belongs to the expected package.

    Inputs
    ------
    origin: str
        Local service HTTP origin without a trailing path.
    package_id: str
        Expected portable bundle UUID.

    Outputs
    -------
    matches: bool
        True for a matching package_id status response; network/JSON failures return
        False.
    '''

    # Check whether a local portable service belongs to the expected package
    try:
        with urlopen(origin+'/portable/status', timeout=1) as response:
            return json.load(response).get('package_id') == package_id
    except (OSError, ValueError):
        return False


def main():
    '''
    Purpose
    -------
    Parse launcher options, reuse or start the package service, and supervise its
    process.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv, may provision the private environment, writes bundle-local
        connection/registry state, starts the loopback server, and opens a browser
        unless disabled. Cleanup terminates the spawned server when necessary.
    '''

    # Parse launcher options, reuse or start the package service, and supervise its
    # process
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--use-current-python', action='store_true', help='Use an already provisioned scientific environment.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int)
    parser.add_argument('--setup-only', action='store_true', help='Prepare the environment without starting the tools.')
    parser.add_argument('--setup-approved', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    record = json.loads((root/'portable-manifest.json').read_text(encoding='utf-8'))
    local = root/'.local'
    connection_file = local/'connection.json'
    # Reuse an already-running service only when its package identity matches
    if not args.setup_only and connection_file.is_file():
        origin = json.loads(connection_file.read_text())['origin']
        if status(origin, record['package_id']):
            if not args.no_browser:
                webbrowser.open(origin+'/files/index.html')
            print('Tools already running at '+origin, flush=True)
            return
    # Select the explicitly supplied environment or provision the private bundle
    # environment
    if args.use_current_python:
        python = Path(sys.executable)
    else:
        python = provision(root, approved=args.setup_approved)
    if args.setup_only:
        print('Environment ready: '+str(python), flush=True)
        return
    local.mkdir(exist_ok=True)
    # Choose a loopback port and publish this package's current connection state
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port or 0))
        port = probe.getsockname()[1]
    origin = 'http://127.0.0.1:'+str(port)
    connection = {'origin': origin, 'package_id': record['package_id']}
    connection_file.write_text(json.dumps(connection), encoding='utf-8')
    (root/'portable-connection.js').write_text('window.MoralesConnection = '+json.dumps(connection)+';\n', encoding='utf-8')
    registry = local/'observation_filter_parameters.json'
    original_registry = root/'Code/Time-Distance/observation_filter_parameters.json'
    if not registry.exists() and original_registry.is_file():
        shutil.copy2(original_registry, registry)
    # Isolate portable runtime paths and backend settings for the server process
    env = dict(os.environ, MORALES_PORTABLE_ROOT=str(root), MPLCONFIGDIR=str(local/'matplotlib'),
               MPLBACKEND='Agg', PYTHONUNBUFFERED='1')
    env.pop('MORALES_DATA_DIR', None)
    command = [str(python), str(root/'Code/Time-Distance/serve_komega_tools.py'), '--port', str(port),
               '--registry', str(registry), '--export-dir', str(local/'exports'),
               '--result-cache', str(local/'processing_results')]
    process = subprocess.Popen(command, cwd=root, env=env)
    try:
        # Wait for matching package readiness while detecting early process failure
        deadline = time.monotonic()+90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('The local tools server stopped. See the error above.')
            if status(origin, record['package_id']):
                print('Tools ready: '+origin+'/files/index.html\nKeep this window open. Press Ctrl+C to stop.', flush=True)
                if not args.no_browser:
                    webbrowser.open(origin+'/files/index.html')
                break
            time.sleep(.25)
        else:
            raise RuntimeError('The tools server did not become ready within 90 seconds.')
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        # Stop the spawned server when supervision exits, escalating only after its
        # timeout
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
