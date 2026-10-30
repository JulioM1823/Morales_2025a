'''
Purpose
-------
Resolve verified dataset relocations while retaining historical source identities.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for data_locations.py.

Notes
-----
Current source locations and stable identities for verified relocated data.
'''
# Import the libraries and shared helpers used by this module
from functools import lru_cache
from pathlib import Path
import json

PROJECT_ROOT=Path(__file__).resolve().parents[2]
CO5BOLD_ROOT=PROJECT_ROOT/'Data/co5bold'
CO5BOLD_PROFILES=CO5BOLD_ROOT/'co5bold_1d_profiles'
RELOCATION_MANIFEST=PROJECT_ROOT/'Data/json_files/co5bold_relocation.json'
ADDITIONAL_RELOCATION_MANIFESTS = tuple(PROJECT_ROOT/'Data/json_files'/name for name in (
    'observations_raw_relocation.json', 'phase_coherence_relocation.json'))


@lru_cache(maxsize=4)
def _relocation(path, version):
    '''
    Purpose
    -------
    Read one verified relocation manifest using its filesystem-version cache key.

    Inputs
    ------
    path: str or pathlib.Path
        JSON relocation-manifest path.
    version: tuple
        Manifest modification time and size, used only to invalidate the cache.

    Outputs
    -------
    mapping: tuple or None
        Original root, current root, and recorded relative-file set; None for an
        unverified schema/status.
    '''

    # Read one verified relocation manifest using its filesystem-version cache key
    record=json.loads(Path(path).read_text())
    if record.get('schema_version')!=1 or record.get('status')!='verified':return None
    return (Path(record['source']),Path(record['destination']),
            frozenset(row['relative_path'] for row in record['files']))


def relocation():
    '''
    Purpose
    -------
    Return the primary verified source relocation if its manifest exists.

    Inputs
    ------
    None

    Outputs
    -------
    mapping: tuple or None
        Original root, destination root, and recorded file set; None when absent or
        unverified.
    '''

    # Return the primary verified source relocation if its manifest exists
    if not RELOCATION_MANIFEST.is_file():return None
    stat=RELOCATION_MANIFEST.stat()
    return _relocation(str(RELOCATION_MANIFEST),(stat.st_mtime_ns,stat.st_size))


def relocations():
    '''
    Purpose
    -------
    Collect the verified primary and additional relocation mappings.

    Inputs
    ------
    None

    Outputs
    -------
    mappings: list of tuple
        Available relocation roots and their recorded relative files.
    '''

    # Collect the verified primary and additional relocation mappings
    mappings = [relocation()]
    for manifest in ADDITIONAL_RELOCATION_MANIFESTS:
        if manifest.is_file():
            stat = manifest.stat()
            mappings.append(_relocation(str(manifest), (stat.st_mtime_ns, stat.st_size)))
    return [mapping for mapping in mappings if mapping]


def current_source_path(path):
    '''
    Purpose
    -------
    Resolve historical source references to their verified current location.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    current: pathlib.Path
        Absolute current location, using portable remapping or verified relocation
        records before resolving legacy figures.
    '''
    # Resolve historical source references to their verified current location
    from portable_paths import bundle_root, resolve_path
    if bundle_root():
        return resolve_path(path).absolute()
    path=Path(path).expanduser().absolute()
    for mapping in relocations():
        source,destination,files=mapping
        if path.is_relative_to(source):
            relative=path.relative_to(source)
            if relative.as_posix() in files:return destination/relative
    if not path.exists():
        from figure_locations import resolve_legacy_figure_source
        relocated=resolve_legacy_figure_source(path)
        if relocated.exists():return relocated
    return path.resolve()


def source_identity_path(path):
    '''
    Purpose
    -------
    Retain the original source label used by dataset and cache identities.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    identity: pathlib.Path
        Historical label for verified relocated sources, or the resolved current path
        for unrelated inputs.

    Notes
    -----
    Keep original dataset/cache IDs; this label is never a new I/O default.

    Files in the checksum-verified CO5BOLD move and the verified figure archive
    retain their original labels. File versions and checksums still distinguish
    changed inputs, and unrelated datasets keep their own identities.
    '''
    # Retain the original source label used by dataset and cache identities
    from portable_paths import bundle_root, identity_path
    if bundle_root():
        return identity_path(path) or Path(path).expanduser().absolute()
    path=current_source_path(path)
    for mapping in relocations():
        source,destination,files=mapping
        if path.is_relative_to(destination):
            relative=path.relative_to(destination)
            if relative.as_posix() in files:return source/relative
    from figure_locations import legacy_figure_identity_path
    return legacy_figure_identity_path(path)
