'''
Purpose
-------
Provide portable-bundle setup, status, and static-file routes while retaining loopback
service state.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for portable_runtime.py.

Notes
-----
Loopback-only setup and static-file routes for a portable tools package.
'''
# Import the libraries and shared helpers used by this module
from html import escape
import json
import os
from pathlib import Path
import secrets
import tempfile
from urllib.parse import urlsplit

from tornado.web import HTTPError, RequestHandler, StaticFileHandler
from portable_paths import bundle_root, data_directory, manifest, resolve_path


def validate_directory(value):
    '''
    Purpose
    -------
    Validate a Data root and list required files that are absent or have a different
    size.

    Inputs
    ------
    value: str
        Absolute Data-directory path containing a co5bold subdirectory.

    Outputs
    -------
    directory, missing: tuple
        Resolved Data path and relative missing/mismatched-file names; invalid roots
        raise ValueError.
    '''

    # Validate a Data root and list required files that are absent or have a different
    # size
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('Enter the full path to an existing Data directory.')
    path = path.resolve()
    if not (path/'co5bold').is_dir():
        raise ValueError('Select the Data directory containing co5bold, rather than co5bold itself.')
    # Check explicitly listed input files by size, without reading hundreds of GB.
    missing = []
    for item in manifest().get('required_data', []):
        candidate = path.joinpath(*item['relative'].split('/'))
        if not candidate.is_file() or (item['size_bytes'] is not None and candidate.stat().st_size != item['size_bytes']):
            missing.append(item['relative'])
    return path, missing


def configured():
    '''
    Purpose
    -------
    Check whether the configured Data directory and its co5bold subdirectory exist.

    Inputs
    ------
    None

    Outputs
    -------
    available: bool
        True when both required directories are present.
    '''

    # Check whether the configured Data directory and its co5bold subdirectory exist
    path = data_directory()
    return path is not None and path.is_dir() and (path/'co5bold').is_dir()


def save_directory(value):
    '''
    Purpose
    -------
    Persist a validated Data root atomically and clear loaded configuration caches.

    Inputs
    ------
    value: str
        Absolute Data-directory path validated before settings are written.

    Outputs
    -------
    missing: list of str
        Required files absent or size-mismatched after saving bundle-local settings.
        Existing documents retain their loaded inputs.
    '''

    # Persist a validated Data root atomically and clear loaded configuration caches
    path, missing = validate_directory(value)
    destination = bundle_root()/'.local/settings.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                     prefix='.settings-', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump({'schema_version': 1, 'data_directory': str(path)}, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    # New sessions read the chosen path. Existing documents retain their inputs.
    import sys
    for name in ('observation_datasets', 'dopplergram_recalculation'):
        module = sys.modules.get(name)
        cache = getattr(module, 'configuration', None)
        if cache is not None and hasattr(cache, 'cache_clear'):
            cache.cache_clear()
    return missing


class PackageHandler(RequestHandler):
    '''
    Purpose
    -------
    Supply noncached responses for portable setup and service endpoints.

    Inputs
    ------
    None

    Outputs
    -------
    handler: PackageHandler
        Tornado request handler whose default headers disable response caching.
    '''

    def set_default_headers(self):
        '''
        Purpose
        -------
        Disable HTTP caching for this portable-service response.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Sets the Cache-Control response header to no-store.
        '''

        # Disable HTTP caching for this portable-service response
        self.set_header('Cache-Control', 'no-store')


class StatusHandler(PackageHandler):
    '''
    Purpose
    -------
    Report portable package identity and Data-directory configuration status.

    Inputs
    ------
    None

    Outputs
    -------
    handler: StatusHandler
        JSON status endpoint; null-origin requests receive the matching CORS origin
        header.
    '''

    def get(self):
        '''
        Purpose
        -------
        Return package identity and local Data-directory readiness as JSON.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Writes the status response and conditionally permits a null Origin header.
        '''

        # Return package identity and local Data-directory readiness as JSON
        origin = self.request.headers.get('Origin')
        if origin == 'null':
            self.set_header('Access-Control-Allow-Origin', 'null')
        self.write({'service': 'morales-komega', 'package_id': manifest()['package_id'],
                    'configured': configured()})


class SetupHandler(PackageHandler):
    '''
    Purpose
    -------
    Serve the bundle-local Data-directory setup form.

    Inputs
    ------
    None

    Outputs
    -------
    handler: SetupHandler
        Tornado handler retaining the configuration token supplied at route
        initialization.
    '''

    def initialize(self, token):
        '''
        Purpose
        -------
        Store the per-service token used by the setup form.

        Inputs
        ------
        token: str
            Random token shared by the setup page and configuration POST route.

        Outputs
        -------
        None
            Assigns token on this request handler.
        '''

        # Store the per-service token used by the setup form
        self.token = token

    def get(self):
        '''
        Purpose
        -------
        Render the setup page with the current directory and configuration token.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Writes escaped HTML containing the existing setup JavaScript; no settings
            are changed by this GET.
        '''

        # Render the setup page with the current directory and configuration token
        self.set_header('Content-Type', 'text/html; charset=utf-8')
        value = escape(str(data_directory() or ''), quote=True)
        token = json.dumps(self.token)
        # Render the existing setup form and browser submission script with escaped
        # state
        self.write('''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Data directory</title>
<style>body{font:17px/1.6 system-ui;max-width:46rem;margin:8vh auto;padding:24px}
input{box-sizing:border-box;width:100%;padding:12px;font:inherit}button,a{font:inherit;padding:10px}
[role=status]{white-space:pre-wrap}label{display:block;font-weight:600}</style></head><body>
<h1>Choose your Data directory</h1><p>Enter the full path to your local copy of <strong>Data</strong>.
It contains <code>co5bold</code>, <code>simulations</code>, <code>observations</code>, and other data folders.
The choice is saved for every HTML page and Bokeh tool in this package.</p>
<form id="setup"><label for="directory">Data directory</label><input id="directory" required value="''' + value + '''"
placeholder="/path/to/Morales_2025a/Data" autocomplete="off"><p><button>Save directory and continue</button></p></form>
<p id="status" role="status"></p><a id="continue" hidden>Continue with available data</a>
<script>
const token = ''' + token + ''';
const requested = new URLSearchParams(location.search).get('next');
let next = '/files/index.html';
if (requested) {
  const url = new URL(requested, location.origin);
  if (url.origin === location.origin && (url.pathname.startsWith('/files/') ||
      /^\\/(?:integrated_komega|observation_komega|komega|gaussian_filter|magnetogram)_bokeh_app/.test(url.pathname))) next = url.href;
}
document.getElementById('setup').addEventListener('submit', async event => {
  event.preventDefault();
  const status = document.getElementById('status');
  status.textContent = 'Checking directory…';
  try {
    const response = await fetch('/portable/configure', {method:'POST',
      headers:{'Content-Type':'application/json','X-Morales-Token':token},
      body:JSON.stringify({data_directory:document.getElementById('directory').value})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error);
    if (result.missing.length) {
      status.textContent = 'Directory saved. Some recorded source files are missing or have a different size. ' +
        'Tools using those files cannot reproduce the saved results.\\n' + result.missing.slice(0,20).join('\\n');
      const link = document.getElementById('continue'); link.href = next; link.hidden = false;
    } else location.replace(next);
  } catch (error) { status.textContent = error.message; }
});
</script></body></html>''')


class ConfigureHandler(PackageHandler):
    '''
    Purpose
    -------
    Validate token-protected same-origin Data-directory configuration requests.

    Inputs
    ------
    None

    Outputs
    -------
    handler: ConfigureHandler
        POST endpoint saving bundle-local settings after origin and token verification.
    '''

    def initialize(self, token):
        '''
        Purpose
        -------
        Store the expected token for configuration requests.

        Inputs
        ------
        token: str
            Random token required in the X-Morales-Token request header.

        Outputs
        -------
        None
            Assigns token on this request handler.
        '''

        # Store the expected token for configuration requests
        self.token = token

    def post(self):
        '''
        Purpose
        -------
        Verify request origin and token before saving a validated Data directory.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Writes saved/missing JSON, returns HTTP 400 for invalid settings, or raises
            HTTP 403 for failed origin/token checks.
        '''

        # Verify request origin and token before saving a validated Data directory
        if (self.request.headers.get('Origin') != self.request.protocol+'://'+self.request.host or
                not secrets.compare_digest(self.request.headers.get('X-Morales-Token', ''), self.token)):
            raise HTTPError(403)
        try:
            value = json.loads(self.request.body)['data_directory']
            if not isinstance(value, str):
                raise ValueError('Data directory must be a path string.')
            missing = save_directory(value)
        except (ValueError, KeyError, OSError) as exc:
            self.set_status(400)
            self.write({'error': str(exc)})
            return
        self.write({'saved': True, 'missing': missing})


class BundleFilesHandler(StaticFileHandler):
    '''
    Purpose
    -------
    Serve packaged static files while excluding hidden path components.

    Inputs
    ------
    None

    Outputs
    -------
    handler: BundleFilesHandler
        Static-file handler applying the additional hidden-component check.
    '''

    def validate_absolute_path(self, root, absolute_path):
        '''
        Purpose
        -------
        Apply standard static-root validation and reject hidden path components.

        Inputs
        ------
        root: str
            Configured absolute static-file root.
        absolute_path: str
            Requested absolute file path passed through Tornado validation.

        Outputs
        -------
        path: str or None
            Validated absolute filename from the parent handler; hidden components raise
            HTTPError(403).
        '''

        # Apply standard static-root validation and reject hidden path components
        path = super().validate_absolute_path(root, absolute_path)
        if path and any(part.startswith('.') for part in Path(path).relative_to(root).parts):
            raise HTTPError(403)
        return path


def routes():
    '''
    Purpose
    -------
    Build portable status, setup, configuration, and static-file routes.

    Inputs
    ------
    None

    Outputs
    -------
    routes: list of tuple
        Tornado route specifications sharing one new random configuration token.
    '''

    # Build portable status, setup, configuration, and static-file routes
    token = secrets.token_urlsafe(32)
    return [('/portable/status', StatusHandler), ('/setup', SetupHandler, {'token': token}),
            ('/portable/configure', ConfigureHandler, {'token': token}),
            (r'/files/(.*)', BundleFilesHandler, {'path': str(bundle_root()), 'default_filename': 'index.html'})]
