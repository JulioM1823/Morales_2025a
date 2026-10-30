'''
Purpose
-------
Map packaged files and separate data directories while preserving original identity
labels.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for portable_paths.py.

Notes
-----
Opt-in path translation for a distributed tools bundle.

Saved scientific records remain unchanged. Only paths used for I/O are mapped.
Ordinary research checkouts do not enable this module's translations.
'''
# Import the libraries and shared helpers used by this module
from functools import lru_cache
import json
import os
from pathlib import Path, PurePosixPath


def bundle_root():
    '''
    Purpose
    -------
    Resolve the optional portable-bundle root from the environment.

    Inputs
    ------
    None

    Outputs
    -------
    root: pathlib.Path or None
        Resolved MORALES_PORTABLE_ROOT directory, or None outside portable operation.
    '''

    # Resolve the optional portable-bundle root from the environment
    value = os.environ.get('MORALES_PORTABLE_ROOT')
    return Path(value).resolve() if value else None


@lru_cache(maxsize=4)
def _manifest(root):
    '''
    Purpose
    -------
    Read and cache the portable manifest for a bundle root.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    record: dict
        Decoded portable-manifest.json contents.
    '''

    # Read and cache the portable manifest for a bundle root
    return json.loads((Path(root)/'portable-manifest.json').read_text(encoding='utf-8'))


def manifest():
    '''
    Purpose
    -------
    Return the current portable manifest or an empty nonportable record.

    Inputs
    ------
    None

    Outputs
    -------
    record: dict
        Cached bundle manifest, or an empty dictionary outside portable operation.
    '''

    # Return the current portable manifest or an empty nonportable record
    root = bundle_root()
    return _manifest(str(root)) if root else {}


def settings():
    '''
    Purpose
    -------
    Read the bundle-local Data-directory settings when available.

    Inputs
    ------
    None

    Outputs
    -------
    record: dict
        Saved .local/settings.json settings, or an empty dictionary when absent.
    '''

    # Read the bundle-local Data-directory settings when available
    root = bundle_root()
    path = root/'.local/settings.json' if root else None
    return json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else {}


def data_directory():
    '''
    Purpose
    -------
    Resolve the configured external Data directory.

    Inputs
    ------
    None

    Outputs
    -------
    directory: pathlib.Path or None
        Expanded absolute MORALES_DATA_DIR or saved Data directory, or None when neither
        is set.
    '''

    # Resolve the configured external Data directory
    value = os.environ.get('MORALES_DATA_DIR') or settings().get('data_directory')
    return Path(value).expanduser().resolve() if value else None


def co5bold_directory():
    '''
    Purpose
    -------
    Resolve the external or packaged CO5BOLD directory.

    Inputs
    ------
    None

    Outputs
    -------
    directory: pathlib.Path or None
        Configured Data/co5bold, fallback packaged Data/co5bold, or None outside a
        bundle.
    '''

    # Resolve the external or packaged CO5BOLD directory
    data = data_directory()
    if data is None:
        root = bundle_root()
        return root/'Data/co5bold' if root else None
    return data/'co5bold'


def _safe_join(root, relative):
    '''
    Purpose
    -------
    Join a package-relative path after rejecting absolute or parent-traversal
    components.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    relative: str or pathlib.PurePath
        Relative package path whose components must stay within root.

    Outputs
    -------
    path: pathlib.Path
        Root-relative joined path; unsafe relative names raise ValueError.
    '''

    # Join a package-relative path after rejecting absolute or parent-traversal
    # components
    relative = PurePosixPath(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid bundle path.')
    return root.joinpath(*relative.parts)


def resolve_path(path):
    '''
    Purpose
    -------
    Resolve exact packaged files and recorded data roots without basename guessing.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    current: pathlib.Path
        Current file location from manifest mappings, external Data settings, or the
        expanded original path. Missing required Data configuration raises ValueError.

    Notes
    -----
    Map exact packaged files and recorded data roots, never just basenames.
    '''
    # Resolve exact packaged files and recorded data roots without basename guessing
    root = bundle_root()
    if root is None:
        return Path(path).expanduser()
    label = str(path).replace('\\', '/')
    record = manifest()
    if label in record.get('data_files', {}):
        destination = data_directory()
        if destination is None:
            raise ValueError('Define the Data directory in the local tools setup page first.')
        return _safe_join(destination, record['data_files'][label])
    if label in record.get('files', {}):
        return _safe_join(root, record['files'][label])
    for item in record.get('external_roots', []):
        source = item['source'].rstrip('/')
        if label == source or label.startswith(source+'/'):
            destination = data_directory()
            if destination is None:
                raise ValueError('Define the Data directory in the local tools setup page first.')
            if item.get('subdirectory'):
                destination = _safe_join(destination, item['subdirectory'])
            return _safe_join(destination, label[len(source):].lstrip('/'))
    # Relative URLs are made absolute against the extracted project by existing loaders.
    package_data = (root/'Data').as_posix()+'/'
    if label.startswith(package_data) and label not in record.get('identities', {}):
        relative = label[len(package_data):]
        if not relative.startswith('recorded_products/') and data_directory() is not None:
            return _safe_join(data_directory(), relative)
    # Paths relative to the original project are also published in launch URLs.
    if not PurePosixPath(label).is_absolute() and not (len(label) > 1 and label[1] == ':'):
        if label.startswith('Data/') and data_directory() is not None:
            return _safe_join(data_directory(), label[5:])
        return _safe_join(root, label)
    return Path(path).expanduser()


def identity_path(path):
    '''
    Purpose
    -------
    Recover the original identity label of a relocated packaged product.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    identity: pathlib.Path or None
        Recorded original label for a known bundle/Data file, otherwise None.

    Notes
    -----
    Return the original identity label for a relocated packaged product.
    '''
    # Recover the original identity label of a relocated packaged product
    root = bundle_root()
    if root is None:
        return None
    path = resolve_path(path).absolute()
    data = data_directory()
    if data is not None and path.is_relative_to(data):
        relative = path.relative_to(data).as_posix()
        label = manifest().get('data_identities', {}).get(relative)
        if label:
            return Path(label)
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    label = manifest().get('identities', {}).get(relative)
    return Path(label) if label else None


def identifier(kind, files):
    '''
    Purpose
    -------
    Construct a stable dataset identifier from original source labels in a bundle.

    Inputs
    ------
    kind: str
        Dataset-kind prefix.
    files: iterable of path-like
        Ordered dataset files whose original identity labels are retained.

    Outputs
    -------
    identifier: str or None
        Kind-prefixed original relative source labels, or None outside portable
        operation.
    '''

    # Construct a stable dataset identifier from original source labels in a bundle
    if bundle_root() is None:
        return None
    from data_locations import source_identity_path
    project = PurePosixPath(manifest()['original_project'])
    names = []
    for path in files:
        label = PurePosixPath(str(source_identity_path(path)).replace('\\', '/'))
        try:
            names.append(label.relative_to(project).as_posix())
        except ValueError:
            names.append(str(label))
    return kind+':'+'|'.join(names)


def remap_data(value):
    '''
    Purpose
    -------
    Translate absolute input paths in a working copy of nested reference data.

    Inputs
    ------
    value: object
        Reference data, including nested dictionaries, lists, and path values.

    Outputs
    -------
    remapped: object
        Recursively copied dictionaries/lists with mapped path strings, or the unchanged
        value outside a bundle.

    Notes
    -----
    Translate input paths in a working copy, preserving the saved reference.
    '''
    # Translate absolute input paths in a working copy of nested reference data
    if bundle_root() is None:
        return value
    if isinstance(value, dict):
        return {key: remap_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [remap_data(item) for item in value]
    if isinstance(value, (str, Path)) and (str(value).startswith('/') or ':\\' in str(value)):
        return str(resolve_path(value))
    return value


def require_data_directory():
    '''
    Purpose
    -------
    Reject opening a portable tool before a usable CO5BOLD Data directory is configured.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Raises ValueError when portable settings lack the required Data/co5bold
        directory.
    '''

    # Reject opening a portable tool before a usable CO5BOLD Data directory is
    # configured
    if bundle_root() and (data_directory() is None or not co5bold_directory().is_dir()):
        raise ValueError('Define the Data directory at /setup before opening a Bokeh tool.')
