'''
Purpose
-------
Resolve explicitly stored optimized filter settings using verified original-input
provenance.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for optimized_filter_config.py.

Notes
-----
Resolve explicitly stored optimized settings, never infer optimization from plots.

The existing Store Parameters UI writes observation_filter_parameters.json.
Its processing_chain, not its derived FITS filename, identifies original cubes,
ordered height indices, and the magnetogram selection. Read/validate once per
filesystem version; missing or conflicting matches are errors in optimized mode.
'''
# Import the libraries and shared helpers used by this module
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar
import hashlib
import json

DEFAULT_FILE = Path(__file__).with_name('observation_filter_parameters.json')


class ConfigurationError(ValueError):
    '''
    Purpose
    -------
    Represent missing, ambiguous, or inconsistent optimized-filter configuration.

    Inputs
    ------
    None

    Outputs
    -------
    exception: ConfigurationError
        ValueError subclass carrying the configuration-validation explanation.
    '''

    pass


def _key(data):
    '''
    Purpose
    -------
    Construct an ordered original-input identity from a source configuration.

    Inputs
    ------
    data: dict
        Original-input configuration containing source_type and its mode-specific
        paths/heights.

    Outputs
    -------
    key: tuple
        Source mode with resolved file paths and, for simulations, observable and
        ordered height indices.
    '''

    # Construct an ordered original-input identity from a source configuration
    mode = data['source_type']
    if mode == 'single_cube':
        nested = data.get('single_cube', {})
        return (mode, str(Path(data.get('file', nested.get('file', ''))).expanduser().resolve()),
                str(data.get('observable', nested.get('observable', ''))),
                int(data.get('h1', nested.get('h1'))), int(data.get('h2', nested.get('h2'))))
    nested = data.get('paired_cubes', {})
    return (mode, *(str(Path(data.get(k, nested.get(k, ''))).expanduser().resolve()) for k in ('v1', 'v2')))


def _record_input(record):
    '''
    Purpose
    -------
    Recover original dataset inputs from a stored processing chain or explicit sidecar.

    Inputs
    ------
    record: dict
        Stored registry observation with dataset and optional processing_chain metadata.

    Outputs
    -------
    data: dict
        Original source configuration; insufficient input provenance raises
        ConfigurationError.
    '''

    # Recover original dataset inputs from a stored processing chain or explicit sidecar
    chain = record.get('processing_chain', {})
    source = chain.get('input', {})
    inputs = source.get('inputs', {})
    if inputs and source.get('source_type'):
        data = dict(inputs, source_type=source['source_type'])
        if 'file_path' in data:
            data['file'] = data['file_path']
        for old, new in [('v1_path', 'v1'), ('v2_path', 'v2')]:
            if old in data: data[new] = data[old]
        return data
    reference = record['dataset'].get('metadata', {}).get('analysis_input')
    if reference:
        return reference['data']
    files = record['dataset']['files']
    # Saved FITS products carry an explicit original-input sidecar.
    if len(files) == 1:
        sidecar = find_json_sidecar(files[0], '.inputs.json')
        if sidecar.is_file():
            return json.loads(sidecar.read_text())['data']
    raise ConfigurationError('Stored setting has no original dataset/height-pair provenance.')


@lru_cache(maxsize=16)
def _load(path, version):
    # Reuse the actual registry schema and its existing full validation.
    '''
    Purpose
    -------
    Validate and cache one complete optimized registry under an unchanged filesystem
    version.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    version: tuple
        Filesystem version included in the memoization key; the path supplies the
        contents.

    Outputs
    -------
    entries, digest: tuple
        Resolved input keys/filtering records and SHA-256 of the registry bytes;
        concurrent changes or unsupported repeated magnetogram stages raise
        ConfigurationError.
    '''

    from observation_filter_registry import read_registry
    before = Path(path).read_bytes()
    registry = read_registry(path)
    after = Path(path).read_bytes()
    st = Path(path).stat()
    if before != after or (st.st_size, st.st_mtime_ns, st.st_ctime_ns) != version:
        raise ConfigurationError('Optimized configuration changed during validation; load the current file again.')
    entries = []
    for identity, record in registry['observations'].items():
        data = _record_input(record)
        stages = record.get('processing_chain', {}).get('stages', [])
        magnetic = [s for s in stages if s['operation'] == 'magnetogram']
        if len(magnetic) > 1:
            raise ConfigurationError(f'{identity}: multiple magnetogram stages cannot be represented by this pipeline.')
        if magnetic:
            parameters = deepcopy(magnetic[0]['parameters'])
            parameters['enabled'] = True
        else:
            baseline = record['dataset'].get('metadata', {}).get('analysis_input', {}).get('filtering', {})
            parameters = deepcopy(baseline.get('magnetogram', {'enabled': False}))
            active = baseline.get('enabled') and 'magnetogram' in baseline.get('filter_sequence', [])
            parameters['enabled'] = bool(active and parameters.get('enabled'))
        filtering = dict(enabled=True, filter_sequence=(['magnetogram'] if parameters['enabled'] else []) + ['gaussian'],
                         gaussian=dict(enabled=True, **record['gaussian']['parameters']), magnetogram=parameters)
        entries.append(dict(key=_key(data), identity=identity, filtering=filtering))
    return entries, hashlib.sha256(before).hexdigest()


def load_configurations(path=DEFAULT_FILE):
    '''
    Purpose
    -------
    Load a validated independent copy of optimized filter entries and registry checksum.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    entries, digest: tuple
        Deep-copied validated settings and file SHA-256; a missing file raises
        ConfigurationError.
    '''

    # Load a validated independent copy of optimized filter entries and registry
    # checksum
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f'Optimized configuration file is missing: {path}')
    st = path.stat()
    return deepcopy(_load(str(path), (st.st_size, st.st_mtime_ns, st.st_ctime_ns)))


def apply_optimized_filters(config):
    '''
    Purpose
    -------
    Apply one explicitly matched optimized filter or record the existing manual state.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    config: dict
        The same mutated configuration with effective filters and provenance; absent or
        ambiguous optimized matches raise ConfigurationError without silently choosing
        defaults.
    '''

    # Apply one explicitly matched optimized filter or record the existing manual state
    options = config.get('optimized_filtering', {})
    mode = options.get('mode', 'manual')
    if mode not in {'manual', 'optimized'}:
        raise ConfigurationError('optimized_filtering.mode must be manual or optimized.')
    if mode == 'manual':
        config['filter_configuration'] = {'mode': 'manual', 'effective': deepcopy(config['filtering'])}
        return config
    # Match optimized entries against exact original source and ordered-height identity
    entries, digest = load_configurations(options.get('file', DEFAULT_FILE))
    candidates = [e for e in entries if e['key'] == _key(config['data'])]
    selection = options.get('selection', config['filtering'].get('magnetogram', {}).get('selection'))
    if selection:
        candidates = [e for e in candidates if not e['filtering']['magnetogram'].get('enabled') or
                      e['filtering']['magnetogram'].get('selection') == selection]
    if options.get('entry_id'):
        candidates = [e for e in candidates if e['identity'] == options['entry_id']]
    # Reject missing or ambiguous settings before changing the effective filters
    if len(candidates) != 1:
        raise ConfigurationError(f'Expected exactly one optimized configuration for {_key(config["data"])}, '
                                 f'selection={selection!r}; found {len(candidates)}. No default was applied.')
    entry = candidates[0]
    effective = deepcopy(entry['filtering'])
    def merge(target, overrides):
        '''
        Purpose
        -------
        Deep-merge explicit filter overrides into the selected effective settings.

        Inputs
        ------
        target: dict
            Effective filter dictionary to update in place.
        overrides: dict
            Explicit nested filter overrides applied to target.

        Outputs
        -------
        None
            Mutates target, recursively retaining unoverridden values and copying
            replacement values.
        '''

        # Deep-merge explicit filter overrides into the selected effective settings
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(target.get(k), dict): merge(target[k], v)
            else: target[k] = deepcopy(v)
    # Apply explicit overrides and revalidate the resulting Gaussian and magnetic
    # parameters
    merge(effective, options.get('overrides', {}))
    from observation_filter_registry import validate_parameters
    validate_parameters({k: effective['gaussian'][k] for k in ('central_k','width_k','central_f','width_f')})
    if effective['magnetogram'].get('enabled'):
        from magnetogram_workflow import validate_parameters as validate_magnetic
        magnetic = {k:v for k,v in effective['magnetogram'].items() if k != 'enabled'}
        magnetic.setdefault('mode', 'dataset' if config['data']['source_type']=='paired_cubes' else config.get('magnetogram_mode', {}).get('single_cube','bottom'))
        validate_magnetic(magnetic)
    # Store the selected effective settings with registry checksum and override
    # provenance
    config['filtering'] = effective
    if effective['magnetogram'].get('mode'):
        config.setdefault('magnetogram_mode', {})['single_cube'] = effective['magnetogram']['mode']
    config['filter_configuration'] = dict(mode='optimized', file=str(Path(options.get('file', DEFAULT_FILE)).resolve()),
        file_sha256=digest, entry_id=entry['identity'], overrides=deepcopy(options.get('overrides', {})), effective=deepcopy(effective))
    return config
