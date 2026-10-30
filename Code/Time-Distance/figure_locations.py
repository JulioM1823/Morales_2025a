'''
Purpose
-------
Resolve active figure trees and verified legacy archives without conflating their
identities.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for figure_locations.py.

Notes
-----
Canonical figure writes and the distinct, recorded legacy figure archive.
'''
# Import the libraries and shared helpers used by this module
from functools import lru_cache
from pathlib import Path
import json

PROJECT_ROOT=Path(__file__).resolve().parents[2]


def canonical_figure_root(root=None):
    '''
    Purpose
    -------
    Resolve the active figure root, including the manuscript-contained tree.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    directory: pathlib.Path
        Resolved active root; an eligible real manuscript Figures directory replaces the
        outer Figures path.
    '''

    # Resolve the active figure root, including the manuscript-contained tree
    root=Path(root if root is not None else PROJECT_ROOT/'Figures').expanduser().absolute()
    # The managed tree can be moved into the manuscript in place of its former
    # forwarding link. Explicit custom roots retain their own destinations.
    if root.name=='Figures':
        replacement=root.parent/'Morales_2025a et al/Figures'
        if (replacement.is_dir() and not replacement.is_symlink()
                and any((replacement/name).is_dir() for name in ('simulations','observations'))):
            return replacement.resolve()
    return root.resolve()


def figure_project_root(root):
    '''
    Purpose
    -------
    Identify the project owning an outer or manuscript-contained figure tree.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    project: pathlib.Path
        Project directory above the managed figure root.

    Notes
    -----
    Project owning an outer or manuscript-contained managed figure tree.
    '''
    # Identify the project owning an outer or manuscript-contained figure tree
    root=canonical_figure_root(root)
    if root.name=='Figures' and root.parent.name in {'Morales_2025a et al','Morales 2025a et al'}:
        return root.parent.parent
    return root.parent


@lru_cache(maxsize=4)
def _replacement(path, version):
    '''
    Purpose
    -------
    Read a figure-replacement manifest under a filesystem-version cache key.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    version: tuple
        Manifest modification time and size, used to invalidate the cache.

    Outputs
    -------
    record: dict
        Decoded JSON replacement record.
    '''

    # Read a figure-replacement manifest under a filesystem-version cache key
    return json.loads(Path(path).read_text())


def _recorded_replacement(project):
    '''
    Purpose
    -------
    Find the latest verified replacement record matching the active figure root.

    Inputs
    ------
    project: str or pathlib.Path or None
        Project root; None uses the module default when supported.

    Outputs
    -------
    record: dict or None
        Matching replacement metadata, or None if no verified record exists.
    '''

    # Find the latest verified replacement record matching the active figure root
    canonical=canonical_figure_root(project/'Figures')
    manifests=sorted((project/'Data/json_files').glob('manuscript_figures_replacement_*.json'),reverse=True)
    for manifest in manifests:
        stat=manifest.stat()
        record=_replacement(str(manifest),(stat.st_mtime_ns,stat.st_size))
        if (record.get('status')=='verified'
                and canonical_figure_root(record['canonical_figures'])==canonical):return record
    return None


def legacy_figure_root(project=None, *, required=False):
    '''
    Purpose
    -------
    Locate a distinct legacy figure archive without returning the active-tree alias.

    Inputs
    ------
    project: str or pathlib.Path or None
        Project root; None uses the module default when supported.
    required: bool
        Require a distinct existing legacy directory instead of returning None.

    Outputs
    -------
    directory: pathlib.Path or None
        Recorded archive or distinct legacy manuscript tree. Missing required archives
        raise FileNotFoundError.

    Notes
    -----
    Never return the manuscript alias to the active output tree as legacy input.
    '''
    # Locate a distinct legacy figure archive without returning the active-tree alias
    project=Path(project or PROJECT_ROOT).expanduser().resolve()
    canonical=canonical_figure_root(project/'Figures')
    record=_recorded_replacement(project)
    if record:
        archive=Path(record['previous_figures_backup']).expanduser().resolve()
        if archive.is_dir() and archive!=canonical:return archive
        if required:raise FileNotFoundError(f'Recorded legacy figure archive is unavailable: {archive}')
        return None
    for name in ('Morales_2025a et al','Morales 2025a et al'):
        candidate=project/name/'Figures'
        if candidate.is_dir() and candidate.resolve()!=canonical:return candidate.resolve()
    if required:raise FileNotFoundError('No distinct legacy figure archive exists; the manuscript Figures alias is the active output tree.')
    return None


def legacy_figure_identity_path(path, project=None):
    '''
    Purpose
    -------
    Retain original labels for assets now stored in a verified figure archive.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    project: str or pathlib.Path or None
        Project root; None uses the module default when supported.

    Outputs
    -------
    identity: pathlib.Path
        Original manuscript figure path for archived assets, otherwise the resolved
        input path.

    Notes
    -----
    Retain IDs of original assets now held in the verified archive.
    '''
    # Retain original labels for assets now stored in a verified figure archive
    project=Path(project or PROJECT_ROOT).expanduser().resolve()
    path=Path(path).expanduser().absolute()
    if not path.is_relative_to(project):return path.resolve()
    record=_recorded_replacement(project)
    if record:
        archive=Path(record['previous_figures_backup']).resolve()
        if path.is_relative_to(archive):
            return Path(record['manuscript_figures'])/path.relative_to(archive)
    return path.resolve()


def resolve_legacy_figure_source(path, project=None):
    '''
    Purpose
    -------
    Resolve historical figure-source metadata to the active tree or legacy archive.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    project: str or pathlib.Path or None
        Project root; None uses the module default when supported.

    Outputs
    -------
    current: pathlib.Path
        Current source location with historical labels translated using verified archive
        metadata.

    Notes
    -----
    Resolve historical migration-source metadata without changing its identity.
    '''
    # Resolve historical figure-source metadata to the active tree or legacy archive
    project=Path(project or PROJECT_ROOT).expanduser().resolve()
    path=Path(path).expanduser().absolute()
    original_root=project/'Figures'
    current_root=canonical_figure_root(original_root)
    if path.is_relative_to(original_root) and current_root!=original_root:
        current=current_root/path.relative_to(original_root)
        if current.is_file():return current.resolve()
    for name in ('Morales_2025a et al','Morales 2025a et al'):
        original=project/name/'Figures'
        if path.is_relative_to(original):
            archive=legacy_figure_root(project)
            if archive is not None:return (archive/path.relative_to(original)).resolve()
    return path.resolve()
