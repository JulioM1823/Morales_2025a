'''
Purpose
-------
Validate and atomically update the shared dataset-specific Gaussian filter registry.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for observation_filter_registry.py.

Notes
-----
Validated JSON registry with locked read/modify/write and atomic replacement.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import file_lock as fcntl
import json
import math
from numbers import Real
import re
import os
import tempfile
import copy

from gaussian_filter_explorer import PARAMETER_KEYS, _validate_parameters

DEFAULT_REGISTRY = Path(__file__).with_name('observation_filter_parameters.json')
SCHEMA_VERSION = 1
ALGORITHM = 'agw_create_filter_bartlett_gaussian_hermitian_v2'


class RegistryError(ValueError):
    '''
    Purpose
    -------
    Represent invalid registry content or an unsuccessful registry update.

    Inputs
    ------
    None

    Outputs
    -------
    exception: RegistryError
        ValueError subclass carrying an explicit registry-validation explanation.
    '''

    pass


def validate_parameters(parameters):
    '''
    Purpose
    -------
    Validate the exact four Gaussian shape parameters and normalize their numeric
    values.

    Inputs
    ------
    parameters: dict
        Gaussian parameter mapping with exactly central_k, width_k, central_f, and
        width_f.

    Outputs
    -------
    parameters: dict
        Float central_k/width_k in Mm^-1 and central_f/width_f in mHz; widths are FWHM.
        Missing/extra/nonphysical inputs raise RegistryError.
    '''

    # Validate the exact four Gaussian shape parameters and normalize their numeric
    # values
    if not isinstance(parameters, dict) or set(parameters) != set(PARAMETER_KEYS):
        raise RegistryError('Gaussian parameters must contain exactly central_k, width_k, central_f, width_f.')
    if any(isinstance(v, bool) or not isinstance(v, Real) for v in parameters.values()):
        raise RegistryError('Gaussian parameters must be JSON numbers.')
    try:
        values = _validate_parameters(*(parameters[key] for key in PARAMETER_KEYS))
    except (TypeError, ValueError) as exc:
        raise RegistryError(str(exc)) from exc
    return dict(zip(PARAMETER_KEYS, values))


def _unique_keys(pairs):
    '''
    Purpose
    -------
    Build a JSON object while rejecting repeated key names.

    Inputs
    ------
    pairs: iterable of tuple
        Ordered JSON object key/value pairs passed by object_pairs_hook.

    Outputs
    -------
    record: dict
        Unique key/value mapping; duplicate JSON keys raise RegistryError.
    '''

    # Build a JSON object while rejecting repeated key names
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    '''
    Purpose
    -------
    Reject nonstandard nonfinite JSON constants.

    Inputs
    ------
    value: str
        NaN or infinity literal supplied by the JSON parser.

    Outputs
    -------
    None
        Always raises RegistryError for the supplied constant.
    '''

    # Reject nonstandard nonfinite JSON constants
    raise RegistryError(f'Invalid JSON constant: {value}')


def _validate_record(identity, record):
    '''
    Purpose
    -------
    Validate dataset identity, sampling, axes, fingerprints, and stored filter stages.

    Inputs
    ------
    identity: str
        Expected registry dataset identifier.
    record: dict
        Candidate observation/filter record to validate.

    Outputs
    -------
    None
        Raises RegistryError for malformed or inconsistent provenance without writing
        the registry.
    '''

    # Validate dataset identity, sampling, axes, fingerprints, and stored filter stages
    try:
        validate_parameters(record['gaussian']['parameters'])
        dataset = record['dataset']
        sampling = dataset['sampling']
        if dataset['id'] != identity:
            raise RegistryError('Dataset ID does not match its registry key.')
        if record['gaussian']['algorithm'] not in {ALGORITHM,'agw_create_filter_bartlett_gaussian_v1'}:
            raise RegistryError('Unsupported stored filter algorithm.')
        # Require physically usable original sample counts and finite positive sampling
        for key, minimum in (('nx', 2), ('ny', 2), ('nt', 3)):
            value = sampling[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise RegistryError(f'Invalid stored {key} sample count.')
        for key in ('dt_seconds', 'dx_Mm'):
            value = sampling[key]
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
                raise RegistryError(f'Invalid stored {key}.')
        # Validate exact nonnegative increasing stored coordinate axes
        for key in ('kh_Mm_inverse', 'nu_mHz'):
            axis = dataset['axes'][key]
            if not isinstance(axis, list) or len(axis) < 2 or not all(
                    isinstance(v, Real) and not isinstance(v, bool) and math.isfinite(v) for v in axis):
                raise RegistryError(f'Invalid stored {key} axis.')
            if axis[0] < 0 or any(a >= b for a, b in zip(axis, axis[1:])):
                raise RegistryError(f'Invalid stored {key} coordinate order.')
        # Require one explicit valid content fingerprint for every recorded source
        fingerprints = dataset['metadata']['source_fingerprints']
        if not isinstance(fingerprints, list) or not fingerprints or len(fingerprints) != len(dataset['files']):
            raise RegistryError('Missing dataset source fingerprints.')
        for source in fingerprints:
            if (not isinstance(source, dict) or not isinstance(source.get('path'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', source.get('sha256', ''))
                    or isinstance(source.get('size_bytes'), bool)
                    or not isinstance(source.get('size_bytes'), int) or source['size_bytes'] < 0):
                raise RegistryError('Invalid dataset source fingerprint.')
        # Check that the recorded native preprocessing chain ends with the saved
        # Gaussian filter
        if 'processing_chain' in record:
            chain = record['processing_chain']
            if not isinstance(chain, dict) or not isinstance(chain.get('input'), dict) or not isinstance(chain.get('stages'), list):
                raise RegistryError('Invalid processing chain.')
            stages = chain['stages']
            if not stages or not all(isinstance(stage, dict) for stage in stages) or stages[-1].get('operation') != 'gaussian_komega':
                raise RegistryError('Processing chain must end with the saved Gaussian diagram filter.')
            if stages[-1]['filter'] != record['gaussian']:
                raise RegistryError('Processing chain Gaussian inputs do not match the saved filter.')
            for stage in stages[:-1]:
                if stage.get('operation') == 'magnetogram':
                    from magnetogram_workflow import validate_parameters as validate_magnetic
                    validate_magnetic(stage['parameters'])
                    if stage['dataset_type'] not in {'paired_cubes', 'single_cube'} or not stage['sources']:
                        raise RegistryError('Invalid magnetogram stage provenance.')
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RegistryError(f'Invalid stored record for {identity}: {exc}. The file was not changed.') from exc


def read_registry(path=DEFAULT_REGISTRY):
    '''
    Purpose
    -------
    Read and validate a complete registry, or construct its empty initial schema.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    registry: dict
        Validated schema-version-1 observations mapping; missing files return an empty
        registry and malformed files raise RegistryError.
    '''

    # Read and validate a complete registry, or construct its empty initial schema
    path = Path(path)
    if not path.exists():
        return {'schema_version': SCHEMA_VERSION, 'observations': {}}
    try:
        registry = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys,
                              parse_constant=_invalid_constant)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RegistryError(f'Cannot read registry {path}: {exc}. The file was not changed.') from exc
    if not isinstance(registry, dict) or registry.get('schema_version') != SCHEMA_VERSION or not isinstance(registry.get('observations'), dict):
        raise RegistryError('Registry requires schema_version=1 and an observations object. The file was not changed.')
    for identity, record in registry['observations'].items():
        if not isinstance(identity, str) or not isinstance(record, dict):
            raise RegistryError('Invalid observation record in registry.')
        _validate_record(identity, record)
    return registry


@contextmanager
def _registry_lock(path):
    '''
    Purpose
    -------
    Hold an exclusive companion-file lock during a registry update.

    Inputs
    ------
    path: pathlib.Path
        Registry file whose companion lock serializes read/modify/write operations.

    Outputs
    -------
    context: context manager
        Yields while the registry lock is held, restoring the lock in a finally block;
        creates the parent and .lock file.
    '''

    # Hold an exclusive companion-file lock during a registry update
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def gaussian_metadata(parameters):
    '''
    Purpose
    -------
    Describe the canonical Gaussian transfer function and its physical-unit conventions.

    Inputs
    ------
    parameters: dict
        Four Gaussian shape parameters validated before metadata construction.

    Outputs
    -------
    metadata: dict
        Validated parameter values, algorithm identifier, fixed constants, units, and
        FFT/preview conventions.

    Notes
    -----
    The canonical filter definition shared by registry records and exports.
    '''
    # Describe the canonical Gaussian transfer function and its physical-unit
    # conventions
    parameters = validate_parameters(parameters)
    return {
        'algorithm': ALGORITHM, 'parameters': parameters,
        'units': {'central_k': 'Mm^-1', 'width_k': 'Mm^-1 FWHM', 'central_f': 'mHz', 'width_f': 'mHz FWHM'},
        'constants': {'fwhm_to_sigma': 2.355, 'sound_speed_km_s': 7., 'gravity_km_s2': .274,
                      'frequency_cap_mHz': 5., 'minimum_k_Mm_inverse': .1, 'low_frequency_suppressor_factor': 150.},
        'normalization': 'per-k profile divided by its maximum only if that maximum exceeds 1',
        'frequency_grid': 'signed linspace; endpoint=bool(nt % 2)',
        'preview_sampling': 'Gaussian constructed directly on stored diagram axes; signed frequency half reconstructed using nt parity',
        'preview_application': 'independent 3-D filtering of both Dopplergrams; checked inverse FFT; native TimeDistance phase recalculation',
        'hermitian_symmetry': 'explicit conjugate-index symmetric real transfer; imaginary inverse-FFT residual checked',
        'phase_color_limits_deg': [-80., 80.],
    }


def load_filter_parameters(identity, path=DEFAULT_REGISTRY):
    '''
    Purpose
    -------
    Retrieve a validated copy of Gaussian parameters for one dataset identifier.

    Inputs
    ------
    identity: str
        Canonical dataset identifier used as the observations mapping key.
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    parameters: dict or None
        Stored Gaussian inputs, or None if the registry has no matching dataset record.

    Notes
    -----
    Return validated Gaussian inputs for a canonical dataset ID, or None.

    Sampling, axes and source fingerprints remain available in read_registry().
    Callers must use them to reproduce and verify the original dataset/grid.
    '''
    # Retrieve a validated copy of Gaussian parameters for one dataset identifier
    record = read_registry(path)['observations'].get(identity)
    return None if record is None else dict(record['gaussian']['parameters'])


def store_parameters(identity, dataset, parameters, path=DEFAULT_REGISTRY, *, model_context=None):
    '''
    Purpose
    -------
    Replace one validated dataset record through locked atomic registry replacement.

    Inputs
    ------
    identity: str
        Canonical selected dataset identifier.
    dataset: dict
        Sampling, axes, files, source fingerprints, and processing metadata for that
        dataset.
    parameters: dict
        Four Gaussian shape inputs in Mm^-1 and mHz, with FWHM widths.
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    model_context: dict or None
        Optional model context retained when a processing chain is present.

    Outputs
    -------
    record: dict
        Stored dataset/filter record, including optional processing-chain/model
        provenance. Other observations and unknown registry-level fields are preserved;
        write/validation failures raise RegistryError.

    Notes
    -----
    Replace one record, preserving every other observation and unknown fields.
    '''
    # Replace one validated dataset record through locked atomic registry replacement
    parameters = validate_parameters(parameters)
    if dataset.get('id') != identity:
        raise RegistryError('Selected observation and saved dataset ID do not match.')
    path = Path(path).expanduser().resolve()
    record = {
        'dataset': dataset,
        'gaussian': gaussian_metadata(parameters),
        'stored_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    # Copy native preprocessing provenance before appending the saved Gaussian stage
    chain = dataset.get('metadata', {}).get('processing_chain')
    if chain is not None:
        record['processing_chain'] = copy.deepcopy(chain)
        record['processing_chain']['stages'].append(dict(operation='gaussian_komega',
            input_result=dataset['metadata'].get('processing_result'), filter=record['gaussian'],
            sampling=dataset['sampling'], axes=dataset['axes']))
        if model_context is not None:
            record['model_context'] = model_context
    _validate_record(identity, record)
    temporary = None
    try:
        # Serialize read-modify-write against other writers and preserve unrelated
        # observations
        with _registry_lock(path):
            registry = read_registry(path)
            registry['observations'][identity] = record
            # Validate the replacement before opening a temporary output file.
            serialized = json.dumps(registry, indent=2, sort_keys=True, allow_nan=False) + '\n'
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                    prefix=f'.{path.name}.', suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(serialized)
                output.flush()
                os.fsync(output.fileno())
            # Publish the fully synchronized registry with one atomic replacement
            os.replace(temporary, path)
            temporary = None
    except (OSError, TypeError, ValueError) as exc:
        raise RegistryError(f'Parameters were not stored: {exc}') from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return record
