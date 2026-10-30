'''
Purpose
-------
Serve the integrated and magnetogram Bokeh applications with compatible legacy URL
aliases.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for serve_komega_tools.py.

Notes
-----
Serve the integrated workspace, including existing figure-link URL aliases.
'''
# Import the libraries and shared helpers used by this module
from pathlib import Path
import argparse
from urllib.parse import urlsplit

from bokeh.application import Application
from bokeh.application.handlers.script import ScriptHandler
from bokeh.server.server import Server
from tornado.web import RequestHandler


class HealthHandler(RequestHandler):
    '''
    Purpose
    -------
    Report local Bokeh-service readiness to supported figure-page origins.

    Inputs
    ------
    None

    Outputs
    -------
    handler: HealthHandler
        Noncached JSON endpoint allowing null or loopback HTTP origins.
    '''

    def get(self):
        # Local file:// figure pages use the readiness bridge before navigating.
        '''
        Purpose
        -------
        Return service readiness and permit supported local figure-page origins.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Writes the morales-komega service identifier with no-store and optional
            matching CORS headers.
        '''

        origin = self.request.headers.get('Origin')
        parsed = urlsplit(origin or '')
        if origin == 'null' or (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'}):
            self.set_header('Access-Control-Allow-Origin', origin)
        self.set_header('Cache-Control', 'no-store')
        self.write({'service': 'morales-komega'})


def build_applications(directory, app_args):
    # These apps are standalone scripts: there are no directory hooks, themes,
    # templates or static assets. DirectoryHandler additionally reads __init__.py
    # for every alias, which can fail with EDEADLK on cloud-backed files and stop
    # the entire service before its readiness endpoint is available.
    '''
    Purpose
    -------
    Construct script-backed Bokeh applications and compatible workspace URL aliases.

    Inputs
    ------
    directory: str or pathlib.Path
        Time-Distance source directory containing the Bokeh application scripts.
    app_args: list of str
        Command-line arguments forwarded to each Bokeh ScriptHandler.

    Outputs
    -------
    applications: dict
        URL paths mapped to shared integrated or separate magnetogram Application
        objects.
    '''

    directory = Path(directory)
    workspace = Application(ScriptHandler(
        filename=str(directory/'integrated_komega_bokeh_app'/'main.py'), argv=app_args))
    applications = {f'/{name}': workspace for name in (
        'integrated_komega_bokeh_app', 'observation_komega_bokeh_app',
        'komega_bokeh_app', 'gaussian_filter_bokeh_app')}
    applications['/magnetogram_bokeh_app'] = Application(ScriptHandler(
        filename=str(directory/'magnetogram_bokeh_app'/'main.py'), argv=app_args))
    return applications


def main():
    '''
    Purpose
    -------
    Parse server options and run the local Bokeh service event loop.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv, builds application and health/setup routes, starts the server,
        and optionally opens the integrated workspace. Portable packages require a
        127.0.0.1 bind address.
    '''

    # Parse server options and run the local Bokeh service event loop
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5013)
    parser.add_argument('--address', default='127.0.0.1')
    parser.add_argument('--show', action='store_true')
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--export-dir', type=Path)
    parser.add_argument('--data-root', type=Path, action='append')
    parser.add_argument('--raw-root', type=Path, action='append')
    parser.add_argument('--simulation-root', type=Path, action='append')
    parser.add_argument('--result-cache', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    # Forward the selected source, registry, export, and cache options to each
    # application script
    app_args = []
    for option in ('registry', 'export_dir', 'data_root', 'raw_root', 'simulation_root', 'result_cache', 'config'):
        value = getattr(args, option)
        for item in (value if isinstance(value, list) else [value]):
            if item is not None:
                app_args.extend(['--' + option.replace('_', '-'), str(item)])
    applications = build_applications(directory, app_args)
    from portable_paths import bundle_root
    patterns = [('/health', HealthHandler)]
    # Add portable setup/static routes and enforce the package loopback bind address
    if bundle_root():
        if args.address != '127.0.0.1':
            parser.error('Portable packages bind only to 127.0.0.1.')
        from portable_runtime import routes
        patterns.extend(routes())
    # Start the configured Bokeh service and enter its event loop
    server = Server(applications, address=args.address, port=args.port,
                    allow_websocket_origin=[f'{args.address}:{args.port}', f'localhost:{args.port}'],
                    extra_patterns=patterns)
    server.start()
    print(f'Integrated k–ω workspace: http://{args.address}:{args.port}/integrated_komega_bokeh_app', flush=True)
    print(f'Magnetogram workspace: http://{args.address}:{args.port}/magnetogram_bokeh_app', flush=True)
    if args.show:
        server.io_loop.add_callback(server.show, '/integrated_komega_bokeh_app')
    server.io_loop.start()


if __name__ == '__main__':
    main()
