'''
Purpose
-------
Build a relocatable HTML/Bokeh tools bundle while cataloguing the separate scientific
Data tree.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for package_komega_tools.py.

Notes
-----
Build a relocatable HTML/Bokeh tools ZIP; the large Data tree stays separate.
'''
# Import the libraries and shared helpers used by this module
import argparse
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import quote
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_locations import current_source_path, source_identity_path, relocations
from figure_locations import canonical_figure_root

PROJECT = Path(__file__).resolve().parents[2]
TD = Path(__file__).resolve().parent


def write_launchers(destination):
    '''
    Purpose
    -------
    Copy the shared platform launcher templates into a new or refreshed bundle.

    Inputs
    ------
    destination: pathlib.Path
        Existing extracted-bundle directory receiving launcher templates.

    Outputs
    -------
    None
        Writes macOS/shell/Windows launchers and sets executable permissions for shell
        entrypoints.

    Notes
    -----
    Use the same bootstrap templates for fresh builds and refreshed bundles.
    '''
    # Copy the shared platform launcher templates into a new or refreshed bundle
    for name in ('Start Tools.command', 'Start Tools.sh'):
        target = destination/name
        shutil.copy2(TD/'portable_start.sh', target)
        target.chmod(0o755)
    shutil.copy2(TD/'portable_start.bat', destination/'Start Tools.bat')
    target = destination/'Code/Time-Distance/portable_start.ps1'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TD/'portable_start.ps1', target)


def bootstrap_tags(relative_root, package_id):
    '''
    Purpose
    -------
    Construct escaped portable-connection and bootstrap script elements.

    Inputs
    ------
    relative_root: str
        Relative URL from the current HTML page to the bundle root.
    package_id: str
        UUID identifying this portable bundle.

    Outputs
    -------
    tags: str
        HTML script tags carrying the package identity and relative bundle root.
    '''

    # Construct escaped portable-connection and bootstrap script elements
    root = escape(relative_root.rstrip('/')+'/', quote=True)
    return (f'<script src="{root}portable-connection.js"></script>'
            f'<script src="{root}portable-bootstrap.js" data-root="{root}" '
            f'data-package="{package_id}"></script>')


def instrument_html(html, relative_root, package_id, *, bridge=False):
    '''
    Purpose
    -------
    Attach portable startup scripts or construct a Bokeh-launch bridge page.

    Inputs
    ------
    html: str
        Existing page text to instrument when bridge is False.
    relative_root: str
        Relative URL from this page to the bundle root.
    package_id: str
        Portable bundle UUID inserted into bootstrap data attributes.
    bridge: bool
        Replace the page with the existing portable Bokeh bridge template when True.

    Outputs
    -------
    html: str
        Original HTML with bootstrap tags before its first closing body, appended tags
        if absent, or a new bridge document.
    '''

    # Attach portable startup scripts or construct a Bokeh-launch bridge page
    tags = bootstrap_tags(relative_root, package_id)
    if bridge:
        return ('<!doctype html><html><head><meta charset="utf-8"><title>Opening Bokeh</title></head>'
                '<body><p id="status">Opening the combined Bokeh tool…</p>'+tags+'''
<script>(async () => {
  if (await window.MoralesPortable.ready) {
    try {
      const target = new URLSearchParams(location.hash.slice(1)).get('target');
      location.replace(window.MoralesPortable.rebase(target));
    } catch (error) { document.getElementById('status').textContent = error.message; }
  }
})();</script></body></html>''')
    if re.search(r'</body\s*>', html, re.I):
        return re.sub(r'</body\s*>', lambda _: tags+'</body>', html, count=1, flags=re.I)
    return html+tags


def walk_records(value):
    '''
    Purpose
    -------
    Traverse nested dictionaries and lists to yield every dictionary record.

    Inputs
    ------
    value: object
        Nested JSON-like dictionary/list value to traverse.

    Outputs
    -------
    records: iterator of dict
        Input dictionaries yielded before their nested records; noncontainer leaves
        produce no values.
    '''

    # Traverse nested dictionaries and lists to yield every dictionary record
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk_records(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_records(item)


def render_index(entries, package_id):
    '''
    Purpose
    -------
    Render the bundle's linked gallery index with portable startup support.

    Inputs
    ------
    entries: iterable of pathlib.Path
        Bundle-relative gallery pages listed in the index.
    package_id: str
        Portable bundle UUID supplied to the bootstrap.

    Outputs
    -------
    html: str
        Escaped gallery-link page instrumented with the bundle bootstrap scripts.
    '''

    # Render the bundle's linked gallery index with portable startup support
    links = ''.join(f'<li><a href="{quote(page.as_posix())}">{escape(page.stem.replace("_", " ").title())}</a></li>'
                    for page in entries)
    html = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Morales HTML and Bokeh tools</title></head><body style="font:17px/1.6 system-ui;margin:2rem;max-width:70rem">'
            '<p><a href="/setup">Change Data directory</a></p><ul>'+links+'</ul></body></html>')
    return instrument_html(html, '.', package_id)


def build(destination, *, project=PROJECT, figure_root=None, data_root=None, archive=True):
    '''
    Purpose
    -------
    Create a new portable tools bundle and optionally archive it as a ZIP.

    Inputs
    ------
    destination: str or pathlib.Path
        New extracted-bundle directory; an optional sibling .zip is created.
    project: str or pathlib.Path or None
        Project root; None uses the module default when supported.
    figure_root: str or pathlib.Path or None
        Managed figure source root; defaults to the project's canonical Figures tree.
    data_root: str or pathlib.Path or None
        Full Data tree containing co5bold, catalogued without copying large scientific
        arrays.
    archive: bool
        Create a new ZIP archive after assembling the extracted bundle.

    Outputs
    -------
    summary: dict
        Package UUID and asset/source counts after copying tools/figures, cataloguing
        external data, instrumenting HTML, and writing manifests/launchers. Existing
        destinations raise FileExistsError; unavailable source trees raise ValueError.
    '''

    # Create a new portable tools bundle and optionally archive it as a ZIP
    project = Path(project).resolve()
    figure_root = Path(figure_root or canonical_figure_root(project/'Figures')).resolve()
    data_root = Path(data_root or project/'Data').resolve()
    destination = Path(destination).absolute()
    if destination.exists() or destination.with_suffix('.zip').exists():
        raise FileExistsError('Choose a new output name; existing bundles are never overwritten.')
    if not figure_root.is_dir() or not (data_root/'co5bold').is_dir():
        raise ValueError('Source Figures and the full Data directory (containing co5bold) are required.')
    destination.mkdir(parents=True)
    package_id = str(uuid.uuid4())
    record = dict(schema_version=1, package_id=package_id, original_project=str(project),
                  files={}, identities={}, data_files={}, data_identities={}, external_roots=[],
                  required_data=[], additional_data=[], missing_source_assets=[])
    # Both the current full Data path and historical Research path occur in HTML.
    roots = {str(data_root), str(project/'Data'), '/Users/juliomorales/Research/Projects/Morales_2025a/Data'}
    record['external_roots'] = [{'source': root, 'kind': 'data'} for root in sorted(roots, key=len, reverse=True)]
    for source, relocated, _ in relocations():
        if relocated.is_relative_to(data_root):
            record['external_roots'].append(dict(source=str(source), kind='data',
                subdirectory=relocated.relative_to(data_root).as_posix()))
    record['external_roots'].sort(key=lambda item: len(item['source']), reverse=True)
    extra_roots = {}
    required = {}

    def data_relative(label, current):
        '''
        Purpose
        -------
        Resolve a source label to its external Data-relative bundle mapping.

        Inputs
        ------
        label: str
            Original or historical source-path label.
        current: pathlib.Path
            Current verified physical source location.

        Outputs
        -------
        relative: str or None
            Relative Data path, including observations_raw mappings when needed; updates
            extra_roots for discovered external observational data.
        '''

        # Resolve a source label to its external Data-relative bundle mapping
        for path in (Path(label), current):
            if path.is_relative_to(data_root):
                return path.relative_to(data_root).as_posix()
        for root in roots:
            if str(label).startswith(root+'/'):
                return str(label)[len(root)+1:]
        # Raw observing cubes are an existing dependency outside the project Data tree.
        parts = Path(label).parts
        if 'Data' in parts:
            index = len(parts)-1-parts[::-1].index('Data')
            source = str(Path(*parts[:index+1]))
            extra_roots[source] = dict(source=source, kind='data', subdirectory='observations_raw')
            return 'observations_raw/'+Path(*parts[index+1:]).as_posix()
        return None

    def add_data(label, *, identity=None, needed=False):
        '''
        Purpose
        -------
        Register original/current Data labels and optional required-source inventory
        entries.

        Inputs
        ------
        label: str
            Original source-path label to map.
        identity: str or None
            Explicit original identity label, otherwise derived from
            source_identity_path.
        needed: bool
            Include file size and availability in the required-source inventory when
            True.

        Outputs
        -------
        relative: str or None
            Resolved Data-relative mapping, or None for unmappable sources; mutates the
            enclosing manifest and required-data inventories.
        '''

        # Register original/current Data labels and optional required-source inventory
        # entries
        current = current_source_path(label)
        relative = data_relative(label, current)
        if relative is None:
            return None
        record['data_files'][str(label)] = relative
        record['data_files'][str(current)] = relative
        record['data_identities'].setdefault(relative, identity or str(source_identity_path(current)))
        if needed:
            size = current.stat().st_size if current.is_file() else None
            required[relative] = dict(relative=relative, size_bytes=size)
            if not current.is_relative_to(data_root):
                item = dict(source=str(current), relative=relative, size_bytes=size)
                if item not in record['additional_data']:
                    record['additional_data'].append(item)
        return relative

    # A metadata catalogue is sufficient: scientific arrays remain in the selected Data tree.
    print('Cataloguing Data paths…', flush=True)
    for path in sorted(data_root.rglob('*')):
        if path.is_file() and path.suffix.lower() in {'.fits', '.fit', '.fts', '.nc', '.h5', '.dat', '.npz'}:
            add_data(str(path), needed=path.is_relative_to(data_root/'co5bold') or
                     path.is_relative_to(data_root/'observations_raw'))

    print('Copying HTML and figure assets…', flush=True)
    html_pages = []
    assets = []
    for path in sorted(figure_root.rglob('*')):
        if not path.is_file():
            if path.is_symlink():
                record['missing_source_assets'].append(str(path))
            continue
        if any(part.startswith('.') for part in path.relative_to(figure_root).parts) or path.suffix in {'.log', '.lock', '.json'}:
            continue
        assets.append(path)
    def copy_asset(path):
        '''
        Purpose
        -------
        Copy one figure asset into the bundle's matching Figures-relative location.

        Inputs
        ------
        path: str or pathlib.Path
            Filesystem path operated on by this helper.

        Outputs
        -------
        None
            Creates the destination parent and copies file bytes/metadata while
            following source symlinks.
        '''

        # Copy one figure asset into the bundle's matching Figures-relative location
        target = destination/'Figures'/path.relative_to(figure_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target, follow_symlinks=True)
    # Independent file reads may hydrate cloud assets; keep their latency from
    # serializing the entire transfer. Each task streams directly to its file.
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(copy_asset, path) for path in assets]
        for count, future in enumerate(as_completed(futures), 1):
            future.result()
            if count % 2000 == 0:
                print(f'Copied {count}/{len(assets)} figure assets', flush=True)
    for path in assets:
        relative = Path('Figures')/path.relative_to(figure_root)
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        record['files'][str(path)] = relative.as_posix()
        record['files'][str(path.resolve())] = relative.as_posix()
        record['identities'][relative.as_posix()] = str(source_identity_path(path))
        if path.suffix == '.html':
            relative_root = os.path.relpath(destination, target.parent).replace(os.sep, '/')
            html = instrument_html(target.read_text(encoding='utf-8'), relative_root, package_id,
                                   bridge=path.name == 'bokeh-launch.html')
            target.write_text(html, encoding='utf-8')
            html_pages.append(relative)
        if path.suffix == '.html':
            # Full-resolution HTML embeds the exact launch contexts already.
            # Do not require unrelated research metadata to view a shared page.
            match = re.search(r'const targets = (.*);', html)
            for item in walk_records(json.loads(match[1]) if match else []):
                dataset = item.get('dataset')
                if isinstance(dataset, dict) and isinstance(dataset.get('file'), str):
                    label = dataset['file']
                    source = current_source_path(label)
                    identity = dataset.get('id', '').partition(':')[2]
                    if identity and not identity.startswith('/'):
                        identity = str(project/identity)
                    relative_data = add_data(label, identity=identity or None)
                    if relative_data is None:
                        # Missing historical phase exports are reconstructed only from their recorded raw inputs.
                        virtual = 'Data/recorded_products/'+sha256(label.encode()).hexdigest()[:24]+'.fits'
                        record['files'][label] = virtual
                        record['identities'][virtual] = identity or str(source_identity_path(source))
                reference = item.get('input_reference')
                if isinstance(reference, dict):
                    for key in ('file', 'v1', 'v2'):
                        label = reference.get('data', {}).get(key)
                        if label:
                            add_data(label, needed=True)

    record['external_roots'].extend(extra_roots.values())
    record['required_data'] = sorted(required.values(), key=lambda item: item['relative'])
    # Only the tools' source and existing solver are needed, not notebooks or research archives.
    module_destination = destination/'Code/Time-Distance'
    module_destination.mkdir(parents=True)
    for path in TD.glob('*'):
        if path.is_file() and (path.suffix in {'.py', '.js'} or
                path.name in {'portable_start.sh', 'portable_start.ps1', 'portable_start.bat', 'portable_README.md'}):
            shutil.copy2(path, module_destination/path.name)
    for name in ('integrated_komega_bokeh_app', 'magnetogram_bokeh_app'):
        shutil.copytree(TD/name, module_destination/name, ignore=shutil.ignore_patterns('__pycache__'))
    for path in sorted((TD/'komega_exports').glob('*')):
        if path.suffix not in {'.html', '.txt'}:
            continue
        relative = Path('Code/Time-Distance/komega_exports')/path.name
        target = destination/relative
        target.parent.mkdir(exist_ok=True)
        if path.suffix == '.html':
            relative_root = os.path.relpath(destination, target.parent).replace(os.sep, '/')
            target.write_text(instrument_html(path.read_text(), relative_root, package_id), encoding='utf-8')
            html_pages.append(relative)
        else:
            shutil.copy2(path, target)
    registry = TD/'observation_filter_parameters.json'
    if registry.is_file():
        shutil.copy2(registry, module_destination/registry.name)
    for path in (TD/'Oana_codes').glob('*.dat'):
        target = module_destination/'Oana_codes'/path.name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(path, target)
    support = data_root/'Time-Distance/model_atmosphere.dat'
    if support.is_file():
        target = destination/'Data/Time-Distance/model_atmosphere.dat'
        target.parent.mkdir(parents=True)
        shutil.copy2(support, target)
    solver = project.parent/'Vesa_2026/Code/diagnostic_diagram'
    solver_destination = destination/'vendor/Vesa_2026/Code/diagnostic_diagram'
    solver_destination.mkdir(parents=True)
    for name in ('config.py', 'functions.py', 'interactive_models.py', 'interactive_bokeh.py',
                 'numeric_controls.py', 'magnetic_geometry.py'):
        shutil.copy2(solver/name, solver_destination/name)
    (destination/'portable-bootstrap.js').write_text((TD/'portable_bootstrap.js').read_text(), encoding='utf-8')
    (destination/'portable-connection.js').write_text('window.MoralesConnection = {origin:"http://127.0.0.1:5013"};\n')
    shutil.copy2(TD/'requirements-portable.txt', destination/'requirements-portable.txt')
    (destination/'portable-manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    write_launchers(destination)
    entries = [page for page in html_pages if page.name in {'field_strength_comparison.html',
                'field_orientation_comparison.html', 'gaussian_filter_comparison.html'} and
               page.parent.name == 'HTML' and not any(re.fullmatch(r'h\d+_vs_h\d+', part) for part in page.parts)]
    (destination/'index.html').write_text(render_index(entries, package_id), encoding='utf-8')
    shutil.copy2(TD/'portable_README.md', destination/'README.md')
    summary = dict(package_id=package_id, html_pages=len(html_pages)+1,
                   required_sources=len(required), additional_data=len(record['additional_data']),
                   missing_source_assets=len(record['missing_source_assets']))
    (destination/'build-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    if archive:
        print('Writing ZIP…', flush=True)
        with zipfile.ZipFile(destination.with_suffix('.zip'), 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as output:
            for path in sorted(destination.rglob('*')):
                if path.is_file():
                    output.write(path, destination.name+'/'+path.relative_to(destination).as_posix())
    return summary


def main():
    '''
    Purpose
    -------
    Parse bundle-building arguments and report the completed package summary as JSON.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv and creates the requested new extracted bundle and optional ZIP
        archive.
    '''

    # Parse bundle-building arguments and report the completed package summary as JSON
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New extracted bundle directory; a sibling ZIP is also created.')
    parser.add_argument('--data-root', type=Path, default=PROJECT/'Data')
    parser.add_argument('--figure-root', type=Path)
    parser.add_argument('--no-zip', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.output, data_root=args.data_root, figure_root=args.figure_root,
                           archive=not args.no_zip), indent=2))


if __name__ == '__main__':
    main()
