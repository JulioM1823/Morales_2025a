'''
Purpose
-------
Install or remove the supervised macOS launchd service for the local Bokeh tools.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for manage_komega_service.py.

Notes
-----
Install the loopback-only Bokeh server as a supervised macOS login service.
'''
# Import the libraries and shared helpers used by this module
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys

LABEL = 'com.juliomorales.morales2025a.komega'


def service_configuration(python=None):
    '''
    Purpose
    -------
    Build the launchd property-list settings for this checkout's Bokeh service.

    Inputs
    ------
    python: str or pathlib.Path or None
        Python executable for the service; defaults to the current interpreter.

    Outputs
    -------
    configuration: dict
        Program arguments, working directory, restart policy, environment, and combined
        log path.
    '''

    # Build the launchd property-list settings for this checkout's Bokeh service
    directory = Path(__file__).absolute().parent
    logs = directory / '.komega_service'
    return dict(Label=LABEL, ProgramArguments=[str(python or sys.executable),
        str(directory/'serve_komega_tools.py')], WorkingDirectory=str(directory.parents[1]),
        RunAtLoad=True, KeepAlive=True, ThrottleInterval=5,
        EnvironmentVariables={'MPLCONFIGDIR': str(logs/'matplotlib'), 'PYTHONUNBUFFERED': '1'},
        StandardOutPath=str(logs/'server.log'), StandardErrorPath=str(logs/'server.log'))


def install():
    '''
    Purpose
    -------
    Install and start the macOS per-user Bokeh launch agent.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Creates the service log directory and LaunchAgents plist, reloads changed
        settings, and starts the agent; unsupported platforms raise RuntimeError.
    '''

    # Install and start the macOS per-user Bokeh launch agent
    if sys.platform != 'darwin':
        raise RuntimeError('Automatic login startup currently uses macOS launchd.')
    configuration = service_configuration()
    logs = Path(configuration['StandardOutPath']).parent
    logs.mkdir(parents=True, exist_ok=True)
    target = Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    target.parent.mkdir(parents=True, exist_ok=True)
    contents = plistlib.dumps(configuration)
    domain = f'gui/{os.getuid()}'
    if target.exists() and target.read_bytes() != contents:
        subprocess.run(['launchctl', 'bootout', domain, str(target)], check=False)
    target.write_bytes(contents)
    loaded = subprocess.run(['launchctl', 'print', domain+'/'+LABEL], capture_output=True).returncode == 0
    if not loaded:
        subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
    subprocess.run(['launchctl', 'kickstart', domain+'/'+LABEL], check=True)
    print(target)


def main():
    '''
    Purpose
    -------
    Parse install/uninstall arguments and apply the requested launchd service action.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv, invokes launchctl, and writes or removes the per-user service
        plist.
    '''

    # Parse install/uninstall arguments and apply the requested launchd service action
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    args = parser.parse_args()
    if args.action == 'install':
        install()
    else:
        target = Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}', str(target)], check=False)
        target.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
