'''
Purpose
-------
Publish and validate immutable processing-result arrays with source and implementation
provenance.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for processing_results.py.

Notes
-----
Content-addressed, immutable processing products shared by Bokeh applications.
'''
from __future__ import annotations
# Import the libraries and shared helpers used by this module
from output_paths import json_output_path

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from contextlib import contextmanager
import file_lock as fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile

import numpy as np

from observation_datasets import file_fingerprint

DEFAULT_RESULT_CACHE = Path(__file__).resolve().parents[2] / 'Data/Filters/processing_results'


class ResultError(ValueError):
    '''
    Purpose
    -------
    Represent an unavailable, inconsistent, or damaged processing-result cache entry.

    Inputs
    ------
    None

    Outputs
    -------
    exception: ResultError
        ValueError subclass carrying the cache-validation explanation.
    '''

    pass


def canonical_json(value):
    '''
    Purpose
    -------
    Serialize a value into stable compact JSON without nonfinite numeric literals.

    Inputs
    ------
    value: JSON-serializable object
        Identity or metadata value to serialize; nonfinite floats raise ValueError.

    Outputs
    -------
    text: str
        Sorted-key JSON suitable for identity hashing.
    '''

    # Serialize a value into stable compact JSON without nonfinite numeric literals
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def result_key(identity):
    '''
    Purpose
    -------
    Calculate the full SHA-256 key of a processing identity or metadata object.

    Inputs
    ------
    identity: JSON-serializable object
        Processing identity or metadata to hash.

    Outputs
    -------
    key: str
        64-character lowercase hexadecimal digest of canonical JSON.
    '''

    # Calculate the full SHA-256 key of a processing identity or metadata object
    return hashlib.sha256(canonical_json(identity).encode('utf-8')).hexdigest()


@lru_cache(maxsize=256)
def _fingerprint_version(path, version):
    '''
    Purpose
    -------
    Cache a file fingerprint under its explicit filesystem version.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    version: tuple
        Filesystem version included in the memoization key; the path supplies the
        contents.

    Outputs
    -------
    fingerprint: dict
        File path, size, and SHA-256 metadata from file_fingerprint.
    '''

    # Cache a file fingerprint under its explicit filesystem version
    return file_fingerprint(path)


def fingerprint(path):
    '''
    Purpose
    -------
    Hash file contents while reusing cached hashes only for an unchanged filesystem
    version.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    fingerprint: dict
        Source fingerprint; a detected change during reading raises ResultError after
        confirmation.

    Notes
    -----
    Hash file contents; reuse the hash only while the filesystem version matches.
    '''
    # Hash file contents while reusing cached hashes only for an unchanged filesystem
    # version
    path = Path(path).expanduser().resolve()
    stat = path.stat()
    value = _fingerprint_version(str(path), (stat.st_size, stat.st_mtime_ns,
                                            stat.st_ctime_ns, stat.st_ino))
    after = path.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino):
        # Sync providers may update metadata/xattrs while immutable products are
        # hashed. A second content hash distinguishes that from changing bytes.
        confirmed = file_fingerprint(path)
        if confirmed != value:
            raise ResultError(f'Source changed while reading: {path}. Please retry.')
        return confirmed
    return dict(value)


@dataclass
class ProcessingResult:
    '''
    Purpose
    -------
    Hold one validated processing result and its memory-mapped arrays.

    Inputs
    ------
    id: str
        Full SHA-256 processing-result identifier.
    manifest: dict
        Validated result manifest and provenance.
    arrays: dict
        Named read-only NumPy arrays loaded from the result directory.

    Outputs
    -------
    result: ProcessingResult
        Container retaining the immutable identity, manifest, and named arrays.
    '''

    id: str
    manifest: dict
    arrays: dict


class ResultStore:
    '''
    Purpose
    -------
    Stage arrays and metadata before atomically publishing one complete result
    directory.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    store: ResultStore
        Cache store whose methods validate identities, manifests, checksums, source
        versions, and array shapes.

    Notes
    -----
    Stage every array and manifest, then atomically publish one complete directory.
    '''
    def __init__(self, root=DEFAULT_RESULT_CACHE):
        '''
        Purpose
        -------
        Store the expanded absolute root for processing-result directories.

        Inputs
        ------
        root: str or pathlib.Path
            Root directory for the paths managed by this helper.

        Outputs
        -------
        None
            Assigns the resolved cache root on this instance.
        '''

        # Store the expanded absolute root for processing-result directories
        self.root = Path(root).expanduser().resolve()

    def directory(self, identity):
        '''
        Purpose
        -------
        Resolve a result directory after validating its identifier syntax.

        Inputs
        ------
        identity: str
            64-character lowercase hexadecimal processing-result identifier.

        Outputs
        -------
        directory: pathlib.Path
            Cache root joined to the 64-character SHA-256 identifier; invalid syntax
            raises ResultError.
        '''

        # Resolve a result directory after validating its identifier syntax
        if not re.fullmatch(r'[0-9a-f]{64}', identity):
            raise ResultError('Invalid processing-result identifier.')
        return self.root / identity

    @contextmanager
    def lock(self, identity):
        '''
        Purpose
        -------
        Hold an exclusive filesystem lock for one processing-result identifier.

        Inputs
        ------
        identity: str
            Processing-result identifier whose writer/read-modify operation is
            serialized.

        Outputs
        -------
        context: context manager
            Yields while the result lock is held and releases it in a finally block;
            creates the cache root/lock file.
        '''

        # Hold an exclusive filesystem lock for one processing-result identifier
        self.directory(identity)
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / (identity + '.lock')).open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def manifest(self, identity):
        '''
        Purpose
        -------
        Read and validate the result manifest, identity, metadata hash, and array
        inventory.

        Inputs
        ------
        identity: str
            Processing-result identifier to load.

        Outputs
        -------
        manifest: dict
            Validated result record; malformed, missing, or incompatible records raise
            ResultError.
        '''

        # Read and validate the result manifest, identity, metadata hash, and array
        # inventory
        try:
            path = json_output_path(self.directory(identity) / 'manifest.json')
            if not path.is_file(): path = self.directory(identity) / 'manifest.json'
            manifest = json.loads(path.read_text())
            if (manifest['schema_version'] != 1 or manifest['id'] != identity
                    or result_key(manifest['identity']) != identity
                    or result_key(manifest['metadata']) != manifest['metadata_sha256']):
                raise ResultError('Processing-result identity or version is invalid.')
            if not isinstance(manifest['arrays'], dict) or not manifest['arrays']:
                raise ResultError('Missing processing-result array inventory.')
            for name, entry in manifest['arrays'].items():
                if (not re.fullmatch(r'[a-z][a-z0-9_]*', name) or not isinstance(entry, dict)
                        or not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256', ''))
                        or not isinstance(entry.get('shape'), list) or not entry['shape']
                        or not all(type(n) is int and n > 0 for n in entry['shape'])
                        or not isinstance(entry.get('dtype'), str)
                        or type(entry.get('size_bytes')) is not int or entry['size_bytes'] < 0):
                    raise ResultError('Invalid cached array inventory.')
            return manifest
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ResultError(f'Cannot open processing result {identity}: {exc}') from exc

    def load(self, identity, *, validate_sources=True):
        '''
        Purpose
        -------
        Verify source versions and cached array contents before loading read-only
        arrays.

        Inputs
        ------
        identity: str
            Processing-result identifier to load.
        validate_sources: bool
            Recheck recorded source fingerprints before reading arrays when True.

        Outputs
        -------
        result: ProcessingResult
            Validated manifest and memory-mapped arrays. Source changes,
            checksum/shape/dtype mismatches, and load errors raise ResultError.
        '''

        # Verify source versions and cached array contents before loading read-only
        # arrays
        manifest = self.manifest(identity)
        try:
            if validate_sources:
                for expected in manifest['identity']['sources']:
                    if fingerprint(expected['path']) != expected:
                        raise ResultError('Source data changed; recalculate this processing result.')
            arrays = {}
            for name, expected in manifest['arrays'].items():
                if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
                    raise ResultError('Invalid cached array name.')
                path = self.directory(identity) / (name + '.npy')
                actual = fingerprint(path)
                if (actual['sha256'], actual['size_bytes']) != (expected['sha256'], expected['size_bytes']):
                    raise ResultError(f'Cached {name} is damaged; recalculate the result.')
                array = np.load(path, mmap_mode='r', allow_pickle=False)
                if list(array.shape) != expected['shape'] or str(array.dtype) != expected['dtype']:
                    raise ResultError(f'Cached {name} has incompatible dimensions or data type.')
                arrays[name] = array
            return ProcessingResult(identity, manifest, arrays)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ResultError(f'Cannot load processing result {identity}: {exc}') from exc

    def publish(self, identity, metadata, arrays):
        '''
        Purpose
        -------
        Stage all result files before publishing the completed result directory.

        Inputs
        ------
        identity: dict
            Full processing identity used to derive the result key.
        metadata: dict
            Dataset, sampling, processing, and display provenance.
        arrays: mapping of str to np.ndarray
            Named arrays to save without pickle; names must match the supported
            identifier syntax.

        Outputs
        -------
        result: ProcessingResult
            Newly reloaded result after array/manifest writes, filesystem
            synchronization, and staging cleanup.
        '''

        # Write a complete staged result, then replace its published directory
        # atomically
        key = result_key(identity)
        target = self.directory(key)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.' + key + '-', dir=self.root))
        try:
            manifest = dict(schema_version=1, id=key, identity=identity, metadata=metadata,
                            metadata_sha256=result_key(metadata),
                            created_at_utc=datetime.now(timezone.utc).isoformat(), arrays={})
            # Write every named array and record its saved checksum, shape, and dtype
            for name, array in arrays.items():
                if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
                    raise ResultError('Invalid array name.')
                path = staging / (name + '.npy')
                with path.open('wb') as output:
                    np.save(output, np.asarray(array), allow_pickle=False)
                    output.flush()
                    os.fsync(output.fileno())
                saved = fingerprint(path)
                manifest['arrays'][name] = dict(sha256=saved['sha256'], size_bytes=saved['size_bytes'],
                                               shape=list(array.shape), dtype=str(array.dtype))
            # Synchronize the complete manifest before publishing the staged directory
            manifest_path = json_output_path(staging / 'manifest.json')
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with manifest_path.open('w') as output:
                output.write(canonical_json(manifest) + '\n')
                output.flush()
                os.fsync(output.fileno())
            # Callers hold the per-key lock; unreadable entries can be replaced safely.
            # Replace the published directory only after all staged files are complete
            if target.exists():
                shutil.rmtree(target)
            os.rename(staging, target)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return self.load(key)


def result_observation(identity, root=DEFAULT_RESULT_CACHE):
    '''
    Purpose
    -------
    Build an observation reference to a complete saved processing result.

    Inputs
    ------
    identity: str
        Published processing-result identifier.
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    observation: Observation
        Generic processing_result dataset reference; intermediate-stage cache entries
        raise ResultError.

    Notes
    -----
    A generic dataset reference; arrays are loaded by the normal background loader.
    '''
    # Build an observation reference to a complete saved processing result
    from observation_datasets import Observation
    store = ResultStore(root)
    manifest = store.manifest(identity)
    dataset = manifest['metadata']['dataset']
    if manifest['identity']['stage'] != 'processing_result':
        raise ResultError('This cache entry is an intermediate, not a k–ω processing result.')
    return Observation('processing_result:' + identity, dataset['label'] + ' / processed input',
        'processing_result', tuple(Path(p['path']) for p in manifest['identity']['sources']),
        {'cache_root': str(store.root), 'result_id': identity})


def request_result(doc, root=DEFAULT_RESULT_CACHE):
    '''
    Purpose
    -------
    Resolve an optional processing result from Bokeh request arguments.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    observation: Observation or None
        Referenced processing-result observation, or None without a result argument;
        repeated arguments raise ResultError.
    '''

    # Resolve an optional processing result from Bokeh request arguments
    context = doc.session_context
    arguments = {} if context is None else context.request.arguments
    values = arguments.get('result', [])
    if not values:
        return None
    if len(values) != 1:
        raise ResultError('Specify exactly one processing result.')
    return result_observation(values[0].decode('utf-8'), root)


def load_processing_observation(observation):
    '''
    Purpose
    -------
    Load validated processed cubes, their native spectrum, axes, and provenance.

    Inputs
    ------
    observation: Observation
        processing_result observation carrying cache_root and result_id in
        input_reference.

    Outputs
    -------
    data: ObservationData
        Supplied Dopplergram cubes, phase spectrum, sampling, and reconstructed runtime
        configuration. Changed implementation, absent runtime metadata, or incompatible
        arrays raise ResultError.

    Notes
    -----
    Shared input contract: two supplied cubes, phase spectrum, axes and provenance.
    '''
    # Load validated processed cubes, their native spectrum, axes, and provenance
    from gaussian_filter_explorer import PreviewGeometry
    from observation_datasets import ObservationData
    reference = observation.input_reference
    result = ResultStore(reference['cache_root']).load(reference['result_id'])
    algorithms = result.manifest['identity']['algorithms']
    if algorithms['numpy'] != np.__version__ or any(fingerprint(path)['sha256'] != expected
            for path, expected in algorithms['code_sha256'].items()):
        raise ResultError('Processing implementation changed; recalculate this result in the preprocessing tool.')
    # Validate recorded sampling and array axes before constructing the shared input
    # contract
    metadata, arrays = result.manifest['metadata'], result.arrays
    sampling = metadata['sampling']
    v1, v2 = arrays['dopplergram_v1'], arrays['dopplergram_v2']
    shape = (sampling['nt'], sampling['ny'], sampling['nx'])
    if v1.shape != shape or v2.shape != shape or arrays['komega'].shape != (len(arrays['kh']), len(arrays['nu'])):
        raise ResultError('Processing-result shapes are incompatible with the recorded sampling.')
    for key in ('kh', 'nu'):
        axis = arrays[key]
        if len(axis) < 2 or axis[0] < 0 or not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0):
            raise ResultError('Processing-result coordinates must be finite, increasing and nonnegative.')
    data_meta = dict(metadata['komega'], source_type=metadata['dataset']['source_type'],
        source_fingerprints=result.manifest['identity']['sources'],
        processing_chain=metadata['processing_chain'], processing_result=observation.input_reference,
        input_dataset=metadata['dataset'], coordinates=metadata['coordinates'],
        source_processing={'description': 'Supplied processed Dopplergrams; recalculated native k–ω',
                           'gaussian_preprocessed': False})
    from dopplergram_recalculation import runtime_config,input_reference
    # Reconstruct the original analysis runtime instead of inferring it from saved phase
    # values
    reference = metadata.get('analysis_input')
    if reference is None:
        raise ResultError('This processing result lacks its analysis runtime; recalculate it in the Magnetogram tool.')
    config = runtime_config(reference,Path(__file__).with_name('config.py'))
    # These supplied cubes already contain the spatial mask exactly once.
    config['filtering']['magnetogram']['enabled'] = False
    config['filtering']['filter_sequence'] = ['gaussian']
    data_meta['analysis_input'] = input_reference(config,provenance='immutable Magnetogram processing result supplied cubes')
    return ObservationData(observation, arrays['komega'], arrays['kh'], arrays['nu'],
        PreviewGeometry(sampling['nx'], sampling['nt'], sampling['dt_seconds'], sampling['dx_Mm'],
                        'Sampling of supplied Dopplergrams'), sampling['ny'], data_meta, (v1, v2),config)
