'''
Purpose
-------
Organize diagnostic outputs by source, observable, geometry, height pair, and
reproducible run identity.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for output_paths.py.
'''

# Import the libraries and shared helpers used by this module
from pathlib import Path
import re
from data_locations import current_source_path, source_identity_path


XCORR_GEOMETRY_DEFAULT = 'annulus'
XCORR_GEOMETRIES = ('annulus', 'east', 'west', 'north', 'south')
OBSERVABLES = ('v1', 'v2', 'v3', 'bb1', 'bb2', 'bb3', 'rho', 'temp', 'pressure', 'plasma_beta')

PRODUCT_DIRECTORY = {
    'time_distance': 'xcorr',
    'phase_difference': 'phase',
    'komega_diagram': 'komega',
    'coherence_diagram': 'komega',
    'gaussian_filter': 'komega',
    'filtered_dopplergram': 'komega',
    'composite_diagnostics': 'komega',
}


def slugify(value):
    '''
    Purpose
    -------
    Normalize a value into a lowercase filename-safe token.

    Inputs
    ------
    value: object
        Value converted to text before filename normalization.

    Outputs
    -------
    slug: str
        ASCII alphanumeric token with collapsed underscore separators and normalized
        Angstrom spelling.
    '''

    # Normalize a value into a lowercase filename-safe token
    value = str(value).strip().lower()
    value = value.replace('å', 'a')
    value = re.sub(r'angstrom', 'a', value, flags = re.IGNORECASE)
    value = re.sub(r'[^0-9a-z]+', '_', value)
    value = re.sub(r'_+', '_', value)

    return value.strip('_')


def join_slug(parts):
    '''
    Purpose
    -------
    Join nonempty normalized path-label tokens with underscores.

    Inputs
    ------
    parts: iterable
        Values to normalize individually and join in order.

    Outputs
    -------
    slug: str
        Combined token with empty normalized parts omitted.
    '''

    # Join nonempty normalized path-label tokens with underscores
    normalized = [slugify(part) for part in parts if str(part).strip() != '']
    normalized = [part for part in normalized if part != '']

    return '_'.join(normalized).strip('_')


def normalize_xcorr_geometry(geometry):
    '''
    Purpose
    -------
    Validate and normalize a supported cross-correlation geometry.

    Inputs
    ------
    geometry: str or None
        Requested spatial averaging geometry.

    Outputs
    -------
    geometry: str
        annulus, east, west, north, or south; blank input uses annulus and unsupported
        values raise ValueError.
    '''

    # Validate and normalize a supported cross-correlation geometry
    if geometry in ['', None]:
        geometry = XCORR_GEOMETRY_DEFAULT

    normalized = str(geometry).strip().lower()
    if normalized not in XCORR_GEOMETRIES:
        raise ValueError(
            "time_distance['xcorr_geometry'] must be one of "
            "'annulus', 'east', 'west', 'north', or 'south'.")

    return normalized


def normalize_observable_slug(observable):
    '''
    Purpose
    -------
    Normalize simulation observable aliases into stable output-directory tokens.

    Inputs
    ------
    observable: str
        Input field name or alias, such as bx, density, or temperature.

    Outputs
    -------
    observable: str
        Canonical supported field token or a filename-safe normalized fallback.
    '''

    # Normalize simulation observable aliases into stable output-directory tokens
    from simulation_observables import normalize
    alias_lookup = {
        'bx': 'bb1',
        'by': 'bb2',
        'bz': 'bb3',
        'b1': 'bb1',
        'b2': 'bb2',
        'b3': 'bb3',
        'temperature': 'temp',
        'density': 'rho',
    }

    normalized = normalize(observable)
    normalized = alias_lookup.get(normalized, normalized)

    return normalized if normalized in OBSERVABLES else slugify(normalized or 'v1')


def resolve_output_observable(config):
    '''
    Purpose
    -------
    Resolve the active observable from the configured source type.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    observable: str
        Normalized observable token for the simulation or paired-cube configuration.
    '''

    # Resolve the active observable from the configured source type
    data = config.get('data', {})
    source_type = str(data.get('source_type', '')).strip().lower()

    if source_type == 'single_cube':
        return normalize_observable_slug(data.get('observable', data.get('single_cube', {}).get('observable', '')))

    return normalize_observable_slug(data.get('observable', 'v1'))


def resolve_output_geometry(config):
    '''
    Purpose
    -------
    Resolve the configured cross-correlation geometry with its default.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    geometry: str
        Validated lowercase cross-correlation geometry.
    '''

    # Resolve the configured cross-correlation geometry with its default
    return normalize_xcorr_geometry(
        config.get('time_distance', {}).get('xcorr_geometry', XCORR_GEOMETRY_DEFAULT)
    )


def resolve_magnetogram_folder(config):
    '''
    Purpose
    -------
    Describe whether the effective filtering sequence selects magnetic pixels.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    folder: str
        magneto only for enabled magnetic selection in an active magnetogram stage;
        otherwise nonmagneto.
    '''

    # Describe whether the effective filtering sequence selects magnetic pixels
    filtering = config.get('filtering', {})
    magnetogram = filtering.get('magnetogram', {})
    filter_sequence = [str(value).strip().lower() for value in filtering.get('filter_sequence', [])]

    if (
        filtering.get('enabled', False)
        and magnetogram.get('enabled', False)
        and 'magnetogram' in filter_sequence
    ):
        selection = str(magnetogram.get('selection', 'nonmagnetic')).strip().lower()
        if selection == 'magnetic':
            return 'magneto'

    return 'nonmagneto'


def infer_simulation_path_metadata(file_path):
    '''
    Purpose
    -------
    Read simulation orientation and field-strength labels from path components.

    Inputs
    ------
    file_path: str or pathlib.Path
        Simulation path carrying historical hx/vx/z0 and gauss labels.

    Outputs
    -------
    metadata: dict
        orientation and strength tokens; unmatched strength is unknownG.
    '''

    # Read simulation orientation and field-strength labels from path components
    path = Path(str(file_path))
    orientation = ''
    strength = ''

    # Read explicit orientation and gauss labels from native path components
    for part in path.parts:
        lower_part = part.lower()
        if lower_part in ['hx', 'horizontal', 'h']:
            orientation = 'horizontal'
        elif lower_part in ['vx', 'vertical', 'v']:
            orientation = 'vertical'
        elif lower_part in ['z0', 'zero', 'zero_field']:
            orientation = ''

        if re.fullmatch(r'\d+(?:_\d+)?g', lower_part):
            strength = lower_part.replace('_', '.')[:-1] + 'G'

    # Check the historical combined case token when a component is still unresolved
    if orientation == '' or strength == '':
        match = re.search(r'(hx|vx|z0)[_\-/](\d+(?:_\d+)?g)', str(path), flags = re.IGNORECASE)
        if match is not None:
            component = match.group(1).lower()
            if component == 'hx':
                orientation = 'horizontal'
            elif component == 'vx':
                orientation = 'vertical'
            else:
                orientation = ''
            strength = match.group(2).replace('_', '.')
            strength = strength[:-1] + 'G'

    if strength == '':
        strength = 'unknownG'

    return {
        'orientation': orientation,
        'strength': strength,
    }


def _format_filter_value(value):
    '''
    Purpose
    -------
    Render a scalar or sequence into stable human-readable filter text.

    Inputs
    ------
    value: object
        Filter-setting value to format.

    Outputs
    -------
    text: str
        Lowercase Boolean/null literals, float representations, or recursively formatted
        sequences.
    '''

    # Render a scalar or sequence into stable human-readable filter text
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, int):
        return str(value)
    if value is None:
        return 'null'
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_format_filter_value(item) for item in value) + ']'

    return str(value)


def _flatten_filter_parameters(prefix, value, rows):
    '''
    Purpose
    -------
    Append sorted dotted filter-setting keys and formatted leaf values.

    Inputs
    ------
    prefix: str
        Current dotted parameter-key prefix.
    value: object
        Nested filter-setting dictionary or leaf value.
    rows: list
        Destination list of (key, formatted value) pairs.

    Outputs
    -------
    None
        Mutates rows in place while descending nested dictionaries.
    '''

    # Append sorted dotted filter-setting keys and formatted leaf values
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten_filter_parameters(f'{prefix}.{key}' if prefix else str(key), value[key], rows)
        return

    rows.append((prefix, _format_filter_value(value)))


def filter_parameter_text(config):
    '''
    Purpose
    -------
    Serialize the effective filtering dictionary into ordered parameter lines.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    text: str
        Newline-terminated dotted key/value description, with a disabled fallback for
        empty settings.
    '''

    # Serialize the effective filtering dictionary into ordered parameter lines
    filtering = config.get('filtering', {})
    rows = []
    _flatten_filter_parameters('filtering', filtering, rows)
    if len(rows) == 0:
        rows.append(('filtering.enabled', 'false'))

    return '\n'.join(f'{key}: {value}' for key, value in rows) + '\n'


def _filter_folder_number(path):
    '''
    Purpose
    -------
    Parse the number of a historical filter_N directory.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    number: int or None
        Numeric suffix for an exact filter_N name, otherwise None.
    '''

    # Parse the number of a historical filter_N directory
    match = re.fullmatch(r'filter_(\d+)', path.name)
    return int(match.group(1)) if match is not None else None


def _scan_filter_folders(roots):
    '''
    Purpose
    -------
    Inventory historical filter directories and their recorded parameter text.

    Inputs
    ------
    roots: iterable of path-like
        Roots whose direct filter_N subdirectories are scanned.

    Outputs
    -------
    entries: list of dict
        Directory names, numeric indices, and optional filter_parameters.txt contents.
    '''

    # Inventory historical filter directories and their recorded parameter text
    entries = []
    for root in roots:
        root = Path(root).expanduser()
        if not root.exists():
            continue
        for candidate in root.iterdir():
            number = _filter_folder_number(candidate)
            if number is None or not candidate.is_dir():
                continue
            parameter_file = candidate / 'filter_parameters.txt'
            text = parameter_file.read_text(encoding = 'utf-8') if parameter_file.exists() else ''
            entries.append({
                'name': candidate.name,
                'number': number,
                'text': text,
            })

    return entries


def resolve_filter_folder_name(config, roots):
    '''
    Purpose
    -------
    Reuse the lowest matching historical filter folder or allocate the next number.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    roots: iterable of path-like
        Candidate roots containing historical numbered filter folders.

    Outputs
    -------
    name, text: tuple of str
        Selected filter_N name and the current filter-parameter description.
    '''

    # Reuse the lowest matching historical filter folder or allocate the next number
    roots = [Path(root).expanduser() for root in roots if root not in ['', None]]
    text = filter_parameter_text(config)
    entries = _scan_filter_folders(roots)
    matching_entries = [entry for entry in entries if entry['text'] == text]

    if len(matching_entries) > 0:
        number = min(entry['number'] for entry in matching_entries)
        return f'filter_{number}', text

    max_number = max([entry['number'] for entry in entries], default = 0)
    return f'filter_{max_number + 1}', text


def ensure_filter_parameters_file(root, filter_folder_name, text):
    '''
    Purpose
    -------
    Create a historical filter folder and synchronize its parameter text.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    filter_folder_name: str
        Numbered filter-directory name relative to root.
    text: str
        Exact parameter text to persist.

    Outputs
    -------
    folder: pathlib.Path
        Created/reused folder after writing filter_parameters.txt when needed.
    '''

    # Create a historical filter folder and synchronize its parameter text
    folder = Path(root).expanduser() / filter_folder_name
    folder.mkdir(parents = True, exist_ok = True)
    parameter_file = folder / 'filter_parameters.txt'

    if not parameter_file.exists() or parameter_file.read_text(encoding = 'utf-8') != text:
        parameter_file.write_text(text, encoding = 'utf-8')

    return folder


def clean_output_filename(filename):
    '''
    Purpose
    -------
    Remove historical filter-description tokens from an output filename.

    Inputs
    ------
    filename: str or pathlib.Path
        Original output filename containing optional filtering tokens.

    Outputs
    -------
    filename: str
        Cleaned stem with collapsed underscores and the original combined suffix string.
    '''

    # Remove historical filter-description tokens from an output filename
    path = Path(str(filename))
    stem = path.stem
    suffix = ''.join(path.suffixes)

    filter_patterns = [
        r'(?:(?<=_)|^)gauss_ck_\d+(?:_\d+)?_wk_\d+(?:_\d+)?_cf_\d+(?:_\d+)?_wf_\d+(?:_\d+)?(?=_|$)',
        r'(?:(?<=_)|^)b_(?:le|lt|ge|gt|eq)_\d+(?:_\d+)?g(?=_|$)',
        r'(?:(?<=_)|^)magnetogram(?=_|$)',
        r'(?:(?<=_)|^)gaussian_filtered(?=_|$)',
        r'(?:(?<=_)|^)gaussian_filter(?=_|$)',
        r'(?:(?<=_)|^)unfiltered(?=_|$)',
    ]

    for pattern in filter_patterns:
        stem = re.sub(pattern, '', stem, flags = re.IGNORECASE)

    stem = re.sub(r'_+', '_', stem).strip('_')

    return f'{stem}{suffix}'


def product_directory(product):
    '''
    Purpose
    -------
    Resolve the managed diagnostic directory for a product kind.

    Inputs
    ------
    product: str
        Logical product kind from PRODUCT_DIRECTORY.

    Outputs
    -------
    directory: str
        Registered product-directory token; unsupported kinds raise ValueError.
    '''

    # Resolve the managed diagnostic directory for a product kind
    if product not in PRODUCT_DIRECTORY:
        raise ValueError(f'Unsupported output product: {product}')

    return PRODUCT_DIRECTORY[product]


# Geometry-based output management. Legacy filter-folder readers above remain
# available for identifying historical products; no new writer uses them.
import copy
import hashlib
import json
import math
import os
import struct
import tempfile
from functools import lru_cache

DIAGNOSTICS = ('phase_differences', 'k_omega', 'xcorr', 'spatial')
PRODUCT_DIRECTORY.update({
    'phase_difference': 'phase_differences', 'komega_diagram': 'k_omega',
    'coherence_diagram': 'k_omega',
    'gaussian_filter': 'k_omega', 'filtered_dopplergram': 'k_omega',
    'composite_diagnostics': 'k_omega', 'spatial_phase': 'spatial',
    'filtered_dopplergrams': 'filtered_dopplergrams', 'run_state': '_run_state',
})


def jsonable(value):
    '''
    Purpose
    -------
    Convert nested values to stable JSON-compatible containers and scalars.

    Inputs
    ------
    value: object
        Nested dictionary, sequence, path, array-like value, or scalar.

    Outputs
    -------
    value: object
        Converted paths/arrays and explicit strings for nonfinite floats; ordinary
        values are retained.
    '''

    # Convert nested values to stable JSON-compatible containers and scalars
    if isinstance(value, dict): return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [jsonable(v) for v in value]
    if isinstance(value, Path): return str(value)
    if hasattr(value, 'tolist'): return jsonable(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return 'NaN' if math.isnan(value) else ('Infinity' if value>0 else '-Infinity')
    return value


def canonical_json(value):
    '''
    Purpose
    -------
    Serialize normalized values into compact sorted JSON for identity hashing.

    Inputs
    ------
    value: object
        Identity or metadata value to normalize and serialize.

    Outputs
    -------
    text: str
        Stable JSON with nonfinite values represented by strings through jsonable().
    '''

    # Serialize normalized values into compact sorted JSON for identity hashing
    return json.dumps(jsonable(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    '''
    Purpose
    -------
    Calculate the SHA-256 digest of a canonical JSON value.

    Inputs
    ------
    value: object
        Identity or metadata value accepted by canonical_json().

    Outputs
    -------
    digest: str
        Full hexadecimal identity hash.
    '''

    # Calculate the SHA-256 digest of a canonical JSON value
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def atomic_json(path, value):
    '''
    Purpose
    -------
    Write normalized JSON through a synchronized temporary file and atomic replacement.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    value: object
        Metadata serialized with sorted keys and explicit nonfinite-value strings.

    Outputs
    -------
    None
        Creates parent directories, replaces path, and removes the temporary file in a
        finally block.
    '''

    # Write normalized JSON through a synchronized temporary file and atomic replacement
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                prefix='.' + path.name, suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(jsonable(value), indent=2, sort_keys=True, allow_nan=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def json_output_path(path):
    '''
    Purpose
    -------
    Place a machine-readable JSON companion in its json_files subdirectory.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    path: pathlib.Path
        Unchanged path if already under json_files, otherwise its sibling json_files
        location.

    Notes
    -----
    Keep machine-readable output companions out of the browsing directory.
    '''
    # Place a machine-readable JSON companion in its json_files subdirectory
    path = Path(path)
    return path if path.parent.name == 'json_files' else path.parent / 'json_files' / path.name


def json_sidecar_path(path, suffix):
    '''
    Purpose
    -------
    Construct a managed JSON sidecar path by replacing the product suffix.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    suffix: str
        Replacement suffix, such as .metadata.json or .inputs.json.

    Outputs
    -------
    sidecar: pathlib.Path
        Companion path inside json_files.
    '''

    # Construct a managed JSON sidecar path by replacing the product suffix
    return json_output_path(Path(path).with_suffix(suffix))


def find_json_sidecar(path, suffix):
    '''
    Purpose
    -------
    Resolve the managed sidecar with a historical adjacent-file fallback.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    suffix: str
        JSON sidecar suffix to locate.

    Outputs
    -------
    sidecar: pathlib.Path
        Current JSON path unless only the legacy adjacent sidecar exists.
    '''

    # Resolve the managed sidecar with a historical adjacent-file fallback
    current = json_sidecar_path(path, suffix)
    legacy = Path(path).with_suffix(suffix)
    return legacy if not current.is_file() and legacy.is_file() else current


def product_from_json_sidecar(path, product_suffix):
    '''
    Purpose
    -------
    Recover the adjacent product path represented by a JSON sidecar.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    product_suffix: str
        Output artifact suffix to reconstruct from the sidecar stem.

    Outputs
    -------
    product: pathlib.Path
        Product filename outside json_files with its requested suffix.
    '''

    # Recover the adjacent product path represented by a JSON sidecar
    path = Path(path)
    parent = path.parent.parent if path.parent.name == 'json_files' else path.parent
    return (parent / path.name).with_suffix('').with_suffix(product_suffix)


def metadata_path(path):
    '''
    Purpose
    -------
    Construct the managed metadata JSON path for an artifact.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    sidecar: pathlib.Path
        Product companion ending in .metadata.json under json_files.
    '''

    # Construct the managed metadata JSON path for an artifact
    return json_sidecar_path(path, '.metadata.json')


def read_metadata(path):
    '''
    Purpose
    -------
    Read current or legacy artifact metadata when its sidecar exists.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    record: dict or None
        Decoded JSON metadata, or None when no sidecar is present.
    '''

    # Read current or legacy artifact metadata when its sidecar exists
    sidecar = find_json_sidecar(path, '.metadata.json')
    return json.loads(sidecar.read_text()) if sidecar.is_file() else None


def file_sha256(path):
    '''
    Purpose
    -------
    Calculate an artifact checksum in bounded binary chunks.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    digest: str
        SHA-256 hexadecimal digest; filesystem read errors propagate.
    '''

    # Calculate an artifact checksum in bounded binary chunks
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def source_version(path):
    '''
    Purpose
    -------
    Record a current source version while retaining its verified historical identity
    label.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    record: dict
        Identity path plus file size/mtime, or an unavailable flag for missing inputs.
    '''

    # Record a current source version while retaining its verified historical identity
    # label
    path = current_source_path(path)
    # Retain checksum-verified source labels so a location-only move does not
    # change existing run IDs. Current physical locations are recorded separately.
    record = {'path': str(source_identity_path(path))}
    if path.is_file():
        st = path.stat()
        record.update(size_bytes=st.st_size, mtime_ns=st.st_mtime_ns)
    else:
        record['unavailable'] = True
    return record


@lru_cache(maxsize=16)
def _implementation_version(versions):
    # Keep numerical code changes distinct from path/layout changes.
    '''
    Purpose
    -------
    Hash the selected numerical implementation under explicit source-file versions.

    Inputs
    ------
    versions: tuple
        File paths and filesystem-version values included in the cache key.

    Outputs
    -------
    records: dict
        Source-name to SHA-256 mapping. Pipeline hashes use selected AST definitions;
        other files use complete text, so documentation edits can affect these hashes.
    '''

    import ast
    records = {}
    for path, _, _ in versions:
        source = Path(path).read_text()
        if Path(path).name == 'pipeline.py':
            tree = ast.parse(source)
            exclude = {'prepare_runtime_config', 'build_output_stem', 'build_pipeline', 'run_time_distance',
                       'parse_cli_args', 'iter_run_configs', 'main', '_load_output_paths_module',
                       'discover_simulation_files', 'infer_netcdf_observables', 'build_cli_run_configs'}
            nodes = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name not in exclude:
                    if node.name == 'TimeDistance':
                        node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and
                            (n.name.startswith('compute_') or n.name in {'xcorrj','resolve_phase_analysis_cube_order'})]
                    nodes.append(ast.dump(node, include_attributes=False))
            source = '\n'.join(nodes)
        records[Path(path).name] = hashlib.sha256(source.encode()).hexdigest()
    return records


def implementation_version():
    '''
    Purpose
    -------
    Collect the current pipeline, filter, and spatial-phase implementation hashes.

    Inputs
    ------
    None

    Outputs
    -------
    records: dict
        Version-cached numerical source hashes used in output identities.
    '''

    # Collect the current pipeline, filter, and spatial-phase implementation hashes
    paths = [Path(__file__).with_name(name) for name in ('pipeline.py','filter.py','spatial_phase_analysis.py')]
    return _implementation_version(tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths))


def resolve_category(config):
    '''
    Purpose
    -------
    Resolve a simulation field category independently of the spatial magnetic-mask
    threshold.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    category: pathlib.Path
        z0, hx/hNG, vx/vNG, or an empty observational category; conflicting/unsupported
        simulation identities raise ValueError.

    Notes
    -----
    Model field strength is independent of the spatial mask threshold.
    '''
    # Resolve a simulation field category independently of the spatial magnetic-mask
    # threshold
    data = config['data']
    options = config.get('output', {})
    category = options.get('category', data.get('category'))
    strength = options.get('field_strength_G', data.get('field_strength_G'))
    if data['source_type'] == 'single_cube':
        path = data.get('file', data.get('single_cube', {}).get('file', ''))
        match = re.search(r'(hx|vx|z0)[/_-](\d+(?:_\d+)?)[gG]', str(path), re.I)
        if match:
            inferred = match[1].lower()
            inferred_strength = float(match[2].replace('_', '.'))
            if category is not None and category != inferred:
                raise ValueError('Explicit output category disagrees with simulation identity.')
            if strength is not None and float(strength) != inferred_strength:
                raise ValueError('Explicit output field strength disagrees with simulation identity.')
            category, strength = inferred, inferred_strength
    if category == 'z0':
        if strength not in (None, 0, 0.): raise ValueError('z0 cannot have a nonzero model field strength.')
        return Path('z0')
    if category in {'hx', 'vx'} and strength is not None:
        if float(strength) not in (10., 50., 100.):
            raise ValueError('hx/vx model strength must be 10, 50, or 100 G.')
        return Path(category) / f'{category[0]}{float(strength):g}G'
    if data['source_type'] == 'paired_cubes' and category is None:
        # Observations do not carry a CO5BOLD model orientation/field strength.
        # Preserve their scientific meaning without manufacturing a category.
        return Path('.')
    raise ValueError('Cannot identify hx/vx/z0 category; supply output.category and field_strength_G.')


def organization_prefix(config):
    '''
    Purpose
    -------
    Build the source, observable, and averaging-geometry output prefix.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    prefix: pathlib.Path
        simulations/observable/Geometry or observations/quantity/Geometry.

    Notes
    -----
    Source, simulation observable, and averaging geometry precede categories.
    '''
    # Build the source, observable, and averaging-geometry output prefix
    geometry = resolve_output_geometry(config).title()
    if config['data']['source_type'] == 'single_cube':
        return Path('simulations') / resolve_output_observable(config) / geometry
    return Path('observations') / slugify(config['data'].get('observation_observable', 'doppler_velocity')) / geometry


def terminal_directory(identity):
    '''
    Purpose
    -------
    Combine an output identity's organization prefix and model category.

    Inputs
    ------
    identity: dict
        Recorded output identity containing organization_prefix and category.

    Outputs
    -------
    directory: pathlib.Path
        Relative terminal path, including the legacy observational quantity-layer
        fallback.
    '''

    # Combine an output identity's organization prefix and model category
    prefix = Path(identity['organization_prefix'])
    if len(prefix.parts) == 2 and prefix.parts[0] == 'observations':
        prefix = Path('observations') / 'doppler_velocity' / prefix.parts[1]
    return prefix / identity['category']


def height_geometry(config):
    '''
    Purpose
    -------
    Resolve the ordered height pair, physical separation, and optional separation
    grouping.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    geometry: dict
        Pair label, ordered heights in km, absolute separation in km, rounded
        separation, and grouping status. Missing/inconsistent simulation heights raise
        ValueError.
    '''

    # Resolve the ordered height pair, physical separation, and optional separation
    # grouping
    data = config['data']
    if data['source_type'] == 'single_cube':
        labels = [f'h{int(data.get("resolved_h1_index", data.get("h1")))}',
                  f'h{int(data.get("resolved_h2_index", data.get("h2")))}']
    else:
        labels = data.get('height_labels')
        if not labels:
            from pipeline import normalize_paired_line_token
            labels = [normalize_paired_line_token(data[k]) for k in ('v1','v2')]
        if not all(labels): raise ValueError('Cannot identify ordered observational height labels.')
    pair = '_vs_'.join(slugify(v) for v in labels)
    coordinates = config.get('output', {}).get('height_values_km')
    if coordinates is None:
        coordinates = [data.get('resolved_h1_km'), data.get('resolved_h2_km')]
    if None in coordinates:
        if data['source_type'] == 'single_cube': raise ValueError('Physical simulation heights are required.')
        separation = data.get('resolved_delta_z_km', data.get('paired_cubes', {}).get('delta_z_km'))
        return dict(pair=pair, labels=labels, heights_km=None, delta_z_km=separation,
                    delta_z_rounded_km=None, grouping_status='unavailable: absolute observational formation heights were not recorded')
    z1, z2 = map(float, coordinates)
    if not all(map(math.isfinite, (z1,z2))): raise ValueError('Physical heights must be finite kilometers.')
    separation = abs(z2-z1)
    recorded = data.get('resolved_delta_z_km')
    if recorded is not None and not math.isclose(separation, float(recorded), rel_tol=1e-8, abs_tol=1e-6):
        raise ValueError('Absolute coordinates disagree with the recorded height separation.')
    return dict(pair=pair, labels=labels, heights_km=[z1,z2], delta_z_km=separation,
                delta_z_rounded_km=int(round(separation)), grouping_status='available')


def output_identity(config):
    '''
    Purpose
    -------
    Assemble source versions, physical geometry, filtering, and numerical implementation
    provenance.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    identity: dict
        Complete schema-version-2 run identity; ambiguous magnetograms and inconsistent
        geometry/categories raise ValueError.
    '''

    # Assemble source versions, physical geometry, filtering, and numerical
    # implementation provenance
    data = config['data']
    geometry = height_geometry(config)
    files = [data['file']] if data['source_type']=='single_cube' else [data[k] for k in ('v1','v2')]
    sources = [source_version(p) for p in files]
    magnetic = config.get('filtering', {}).get('magnetogram', {})
    if data['source_type']=='paired_cubes' and config['filtering'].get('enabled') and magnetic.get('enabled') and 'magnetogram' in config['filtering'].get('filter_sequence', []):
        directories = {Path(p).expanduser().resolve().parent for p in files}
        if len(directories) != 1: raise ValueError('Paired Dopplergrams must share their magnetogram dataset directory.')
        directory = directories.pop()
        matches = sorted(p for p in directory.glob('*') if 'hmimag' in p.name.lower() and p.suffix.lower() in {'.fits','.fit','.fts'})
        if len(matches)>1: raise ValueError('Ambiguous paired-cube magnetogram identity.')
        sources.append(source_version(matches[0]) if matches else {'path':str(directory/'*HMImag*.fits'),'unavailable':True})
    dataset = data.get('dataset_id') or '|'.join(str(source_identity_path(p)) for p in files)
    processing = {k:v for k,v in config.get('time_distance', {}).items() if k not in
                  {'nworkers','xcorrj_parallel','xcorrj_chunk_centers','xcorrj_chunk_memory_mb'}}
    calibration = Path(__file__).with_name('Oana_codes')/'AGWs_config.ini'
    return dict(schema_version=2, dataset_id=dataset, source_type=data['source_type'], sources=sources,
                category=resolve_category(config).as_posix(), organization_prefix=organization_prefix(config).as_posix(), geometry=geometry,
                observable=resolve_output_observable(config), filtering=copy.deepcopy(config['filtering']),
                magnetogram_mode=copy.deepcopy(config.get('magnetogram_mode', {})), processing=processing,
                diagnostic_parameters=copy.deepcopy(config.get('diagnostic_parameters', {})),
                implementation=implementation_version(),
                phase_calibration_sha256=file_sha256(calibration) if calibration.is_file() else None)


def build_runtime_output_paths(config, data_output_dir, figure_output_dir=None, create=True):
    '''
    Purpose
    -------
    Attach a reproducible output context and optionally create its hierarchy.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    data_output_dir: str or pathlib.Path
        Root for numerical diagnostic products.
    figure_output_dir: str or pathlib.Path or None
        Optional root for figure products.
    create: bool
        Create required output directories when True.

    Outputs
    -------
    context: dict
        Identity, run hash, resolved output roots, and filter metadata stored as
        config['_output_context']. Optional creation makes diagnostic and
        separation-group directories.
    '''

    # Attach a reproducible output context and optionally create its hierarchy
    identity = output_identity(config)
    run_id = digest(identity)
    context = dict(identity=identity, run_id=run_id, data_root=Path(data_output_dir).expanduser().resolve(),
                   figure_root=Path(figure_output_dir).expanduser().resolve() if figure_output_dir else None,
                   filter_folder='', filter_parameters=filter_parameter_text(config))
    config['_output_context'] = context
    if create:
        for root in (context['data_root'], context['figure_root']):
            if root is None: continue
            ensure_organization_roots(root)
            pair = root / terminal_directory(identity) / identity['geometry']['pair']
            for diagnostic in DIAGNOSTICS: (pair / diagnostic).mkdir(parents=True, exist_ok=True)
            separation = identity['geometry']['delta_z_rounded_km']
            if separation is not None:
                for diagnostic in DIAGNOSTICS:
                    (root / terminal_directory(identity) / f'delta_z_{separation}_km' / diagnostic).mkdir(parents=True, exist_ok=True)
    return context


def _context(config):
    # Only prepare_runtime_config creates a context, after height/filter resolution.
    '''
    Purpose
    -------
    Reuse or reconstruct the runtime output context without creating directories.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    context: dict
        Existing context or a newly attached context derived from configured roots.
    '''

    return config.get('_output_context') or build_runtime_output_paths(config,
        config['paths']['data_output_dir'], config['paths'].get('figure_dir'), create=False)


def build_output_directory(root, config, product, filter_folder_name=None):
    '''
    Purpose
    -------
    Resolve a product's managed directory under the ordered physical height pair.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    product: str
        Registered logical product kind.
    filter_folder_name: str or None
        Retained compatibility argument; not used by the geometry-based writer.

    Outputs
    -------
    directory: pathlib.Path
        Root/organization/category/pair/diagnostic directory.
    '''

    # Resolve a product's managed directory under the ordered physical height pair
    identity = _context(config)['identity']
    return Path(root).expanduser() / terminal_directory(identity) / identity['geometry']['pair'] / product_directory(product)


def build_output_file(root, config, product, filename, filter_folder_name=None, create=True):
    '''
    Purpose
    -------
    Construct a run-tagged product path and reject an existing conflicting run identity.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    product: str
        Registered logical product kind.
    filename: str or pathlib.Path
        Desired stem and suffix before cleaning and appending the run tag.
    filter_folder_name: str or None
        Retained compatibility argument; not used by the geometry-based writer.
    create: bool
        Create required output directories when True.

    Outputs
    -------
    path: pathlib.Path
        Managed product path; optional parent creation and existing-metadata checks
        occur before return.
    '''

    # Construct a run-tagged product path and reject an existing conflicting run
    # identity
    output_dir = build_output_directory(root, config, product)
    filename = Path(filename)
    clean_stem = Path(clean_output_filename(filename.name)).stem
    # Preserve diagnostic/observable labels; a full identity in metadata guards
    # even the improbable truncated-digest collision before anything is written.
    clean_stem = strip_run_suffix(clean_stem)
    name = clean_stem[:110] + '__run_' + _context(config)['run_id'][:24] + filename.suffix
    path = output_dir / name
    if filename.suffix == '.json': path = json_output_path(path)
    if create: path.parent.mkdir(parents=True, exist_ok=True)
    old = read_metadata(path)
    if old and old['run_id'] != _context(config)['run_id']:
        raise FileExistsError(f'Output identity collision: {path}')
    return path


def strip_run_suffix(stem):
    '''
    Purpose
    -------
    Remove a trailing managed run-digest tag from a stem.

    Inputs
    ------
    stem: str
        Filename stem whose managed run tag is removed.

    Outputs
    -------
    stem: str
        Input text without a final __run_ plus 24 hexadecimal characters.
    '''

    # Remove a trailing managed run-digest tag from a stem
    return re.sub(r'__run_[0-9a-f]{24}$', '', str(stem))


def _descending_float(value):
    # IEEE-754 monotonic integer transform, then invert. Handles negative,
    # nonuniform, and sub-km coordinates without ranks that change on insertion.
    '''
    Purpose
    -------
    Encode a physical coordinate as a fixed-width descending IEEE-754 sort key.

    Inputs
    ------
    value: float
        Coordinate encoded without rank-dependent sorting.

    Outputs
    -------
    key: str
        Twenty-digit integer string whose lexical order reverses finite coordinate
        order.
    '''

    bits = struct.unpack('>Q', struct.pack('>d', 0. if value == 0 else float(value)))[0]
    ordered = (~bits & ((1<<64)-1)) if bits >> 63 else bits ^ (1<<63)
    return f'{((1<<64)-1)-ordered:020d}'


def grouped_filename(path, geometry):
    '''
    Purpose
    -------
    Prefix an artifact name with descending physical-height sort keys.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    geometry: dict
        Height geometry containing two physical heights_km values.

    Outputs
    -------
    filename: str
        Sortable upper/lower-height keys and explicit km labels followed by the artifact
        name.
    '''

    # Prefix an artifact name with descending physical-height sort keys
    lo, hi = sorted(geometry['heights_km'])
    prefix = f'{_descending_float(hi)}_{_descending_float(lo)}_z{lo:g}_to_z{hi:g}_km_'
    return prefix + Path(path).name


def _ensure_link(link, target):
    '''
    Purpose
    -------
    Create a relative symlink without replacing unrelated existing entries.

    Inputs
    ------
    link: str or pathlib.Path
        Symlink path to create or validate.
    target: str or pathlib.Path
        Existing artifact or companion target linked relative to link.parent.

    Outputs
    -------
    None
        Creates parent directories; reuses an identical link and raises FileExistsError
        for conflicts.
    '''

    # Create a relative symlink without replacing unrelated existing entries
    link, target = Path(link), Path(target)
    link.parent.mkdir(parents=True, exist_ok=True)
    relative = os.path.relpath(target, link.parent)
    if link.is_symlink() and os.readlink(link) == relative: return
    if link.exists() or link.is_symlink():
        raise FileExistsError(f'Refusing to replace an unrelated file/link: {link}')
    link.symlink_to(relative)


def associate_output(path, metadata, root):
    '''
    Purpose
    -------
    Link a product and its available sidecars into a separation-based browsing group.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    metadata: dict
        Registered artifact metadata containing identity and diagnostic_directory.
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    link: pathlib.Path or None
        Grouped artifact link, or None when physical separation or a supported
        diagnostic group is unavailable.
    '''

    # Link a product and its available sidecars into a separation-based browsing group
    geometry = metadata['identity']['geometry']
    if geometry['delta_z_rounded_km'] is None: return None
    diagnostic = metadata['diagnostic_directory']
    if diagnostic not in DIAGNOSTICS: return None
    group = Path(root) / terminal_directory(metadata['identity']) / f"delta_z_{geometry['delta_z_rounded_km']}_km" / diagnostic
    grouped = group / grouped_filename(path, geometry)
    _ensure_link(grouped, path)
    # Metadata and existing reproducibility sidecars resolve under either view.
    for suffix in ('.metadata.json', '.inputs.json', '.atmosphere.json', '.subplots.json', '.bokeh.json', '.txt', '.html'):
        sidecar = find_json_sidecar(path, suffix) if suffix.endswith('.json') else Path(path).with_suffix(suffix)
        target = json_sidecar_path(grouped, suffix) if suffix.endswith('.json') else grouped.with_suffix(suffix)
        if sidecar.is_file(): _ensure_link(target, sidecar)
    return grouped


def register_output(path, config, product, *, root=None, extra=None, checksum=True):
    '''
    Purpose
    -------
    Publish artifact provenance and optional separation-group links for one run.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    product: str
        Registered logical product kind.
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    extra: dict or None
        Additional artifact metadata retained under extra.
    checksum: bool
        Store the artifact SHA-256 checksum when True.

    Outputs
    -------
    record: dict
        Metadata written atomically beside the product; conflicting recorded run
        identities raise FileExistsError.
    '''

    # Publish artifact provenance and optional separation-group links for one run
    path = Path(path).absolute()
    context = _context(config)
    record = dict(schema_version=2, run_id=context['run_id'], identity=context['identity'], product=product,
                  diagnostic_directory=product_directory(product),
                  filter_configuration=copy.deepcopy(config.get('filter_configuration', {'mode':'manual'})),
                  artifact=dict(size_bytes=path.stat().st_size, sha256=file_sha256(path) if checksum else None), extra=extra or {})
    record['source_locations'] = [dict(identity_path=source['path'],
        current_path=str(current_source_path(source['path']))) for source in context['identity']['sources']]
    existing = read_metadata(path)
    if existing and existing['run_id'] != record['run_id']:
        raise FileExistsError(f'Refusing to overwrite another run: {path}')
    atomic_json(metadata_path(path), record)
    if root is None:
        for candidate in (context['data_root'], context['figure_root']):
            if candidate is not None and path.is_relative_to(candidate): root = candidate; break
    if root is not None:
        ensure_diagnostic_directories(root, record['identity'])
        associate_output(path, record, root)
    return record


def can_reuse(path, config, *, verify=True):
    '''
    Purpose
    -------
    Verify whether an existing artifact still matches its run, sources, size, and
    optional checksum.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    verify: bool
        Rehash the artifact contents in addition to checking identity and size.

    Outputs
    -------
    reusable: bool
        True only for a complete matching artifact with recorded checksum and unchanged
        live source versions.
    '''

    # Verify whether an existing artifact still matches its run, sources, size, and
    # optional checksum
    path = Path(path)
    if not path.is_file(): return False
    record = read_metadata(path)
    if not record or record['run_id'] != _context(config)['run_id'] or not record['artifact'].get('sha256'): return False
    if any(source.get('unavailable') for source in record['identity']['sources']): return False
    if digest(output_identity(config)) != record['run_id']: return False
    # Recheck live sources, even for a runtime object prepared before mutation.
    if any(source_version(s['path']) != s for s in record['identity']['sources']): return False
    return (path.stat().st_size == record['artifact']['size_bytes'] and
            (not verify or file_sha256(path) == record['artifact']['sha256']))


def mirror_hierarchy_from_data_file(target_root, data_file, output_filename, create=True):
    '''
    Purpose
    -------
    Mirror a recorded product hierarchy under another output root.

    Inputs
    ------
    target_root: str or pathlib.Path
        Destination figure/animation root.
    data_file: str or pathlib.Path
        Existing numerical product whose metadata or historical path supplies
        organization.
    output_filename: str or pathlib.Path
        Requested destination filename.
    create: bool
        Create required output directories when True.

    Outputs
    -------
    output: pathlib.Path
        Run-tagged target for managed metadata, or a cleaned historical filter-folder
        fallback; optionally creates directories.
    '''

    # Mirror a recorded product hierarchy under another output root
    data_file = Path(data_file).expanduser().absolute()
    metadata = read_metadata(data_file)
    if metadata:
        identity = metadata['identity']
        folder = Path(target_root) / terminal_directory(identity) / identity['geometry']['pair'] / metadata['diagnostic_directory']
        filename = Path(output_filename)
        stem = strip_run_suffix(filename.stem)
        output = folder / (stem + '__run_' + metadata['run_id'][:24] + filename.suffix)
        if create: output.parent.mkdir(parents=True, exist_ok=True)
        return output
    # Read-only compatibility with historical paths; new computations use the
    # geometry manager. Legacy animations can still be regenerated explicitly.
    parts = data_file.parts
    index = next((i for i, p in enumerate(parts) if re.fullmatch(r'filter_\d+', p)), None)
    folder = Path(target_root) / Path(*parts[index:-1]) if index is not None else Path(target_root)
    if create: folder.mkdir(parents=True, exist_ok=True)
    return folder / clean_output_filename(output_filename)


def atomic_fits(path, array, header):
    '''
    Purpose
    -------
    Write a FITS primary HDU through a temporary file and atomic replacement.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    array: np.ndarray
        Array stored in the primary HDU.
    header: astropy.io.fits.Header
        FITS header supplied to the primary HDU.

    Outputs
    -------
    None
        Creates parent directories, writes array/header, atomically replaces path, and
        cleans the temporary file.
    '''

    # Write a FITS primary HDU through a temporary file and atomic replacement
    from astropy.io import fits
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name, suffix='.tmp')
    os.close(fd)
    try:
        fits.PrimaryHDU(array, header=header).writeto(temporary, overwrite=True)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_npz(path, **arrays):
    '''
    Purpose
    -------
    Write named arrays to an NPZ archive using synchronized atomic replacement.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    arrays: mapping of str to array-like
        Keyword-named arrays passed to NumPy savez.

    Outputs
    -------
    None
        Creates parent directories and replaces path after writing/flushing the
        temporary archive.
    '''

    # Write named arrays to an NPZ archive using synchronized atomic replacement
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as handle:
            import numpy as np
            np.savez(handle, **arrays)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def configure_outputs(config, *, create=True):
    '''
    Purpose
    -------
    Populate all managed pipeline output filenames from the resolved runtime identity.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    create: bool
        Create required output directories when True.

    Outputs
    -------
    config: dict
        The same mutated configuration, including output context, product paths,
        optional persisted run state, and compatibility keys.

    Notes
    -----
    One entry point shared by the pipeline and plotting notebooks.
    '''
    # Populate all managed pipeline output filenames from the resolved runtime identity
    paths, data = config['paths'], config['data']
    context = build_runtime_output_paths(config, paths['data_output_dir'], paths.get('figure_dir'), create=create)
    from pipeline import build_output_stem
    products = {'outfile':'time_distance','phase_outfile':'phase_difference',
                'komega_outfile':'komega_diagram','coherence_outfile':'coherence_diagram'}
    for key, product in products.items():
        data[key] = str(build_output_file(context['data_root'], config, product,
                       build_output_stem(config, product)+'.fits', create=create))
    data['filter_folder'] = ''  # Historical callers may still read this key.
    data['filter_parameters_file'] = str(build_output_file(context['data_root'], config, 'run_state', 'processing_configuration.json', create=create))
    if create:
        atomic_json(data['filter_parameters_file'], dict(run_id=context['run_id'], identity=context['identity'],
            filter_configuration=config.get('filter_configuration', {'mode':'manual'})))
    data['run_state_file'] = str(build_output_file(context['data_root'], config, 'run_state', 'diagnostic_arrays.npz', create=create))
    data['filtered_dopplergrams_file'] = str(build_output_file(context['data_root'], config, 'filtered_dopplergrams', 'filtered_dopplergrams.npz', create=create))
    # Retired display-only plots: retain the key for older notebooks/configs.
    # Magnetic orientation metadata is still computed and cached independently.
    data['orientation_validation_outfile'] = ''
    return config


def export_configuration(config, gaussian_parameters=None, *, gaussian_enabled=False, diagnostic_parameters=None):
    '''
    Purpose
    -------
    Describe the effective live Gaussian and diagnostic state without recalculating
    input cubes.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    gaussian_parameters: dict or None
        Live Gaussian parameter overrides in their configured physical units.
    gaussian_enabled: bool
        Whether the effective exported sequence includes Gaussian filtering.
    diagnostic_parameters: dict or None
        Live diagnostic settings copied into the output identity.

    Outputs
    -------
    config: dict
        Deep-copied manual-export configuration with rebuilt noncreating output
        identity.

    Notes
    -----
    Describe the effective live filter state without reloading/recalculating cubes.
    '''
    # Describe the effective live Gaussian and diagnostic state without recalculating
    # input cubes
    cfg = copy.deepcopy(config)
    cfg['optimized_filtering'] = {'mode':'manual'}
    filters = cfg['filtering']
    sequence = list(filters.get('filter_sequence', []))
    filters.setdefault('gaussian', {})['enabled'] = bool(gaussian_enabled)
    if gaussian_parameters is not None: filters['gaussian'].update(gaussian_parameters)
    if gaussian_enabled and 'gaussian' not in sequence: sequence.append('gaussian')
    if not gaussian_enabled: sequence = [name for name in sequence if name!='gaussian']
    filters['filter_sequence'] = sequence
    filters['enabled'] = any(filters.get(name, {}).get('enabled') for name in sequence)
    cfg['diagnostic_parameters'] = copy.deepcopy(diagnostic_parameters or {})
    cfg['filter_configuration'] = {'mode':'manual export', 'effective':copy.deepcopy(filters)}
    build_runtime_output_paths(cfg, cfg['paths']['data_output_dir'], cfg['paths'].get('figure_dir'), create=False)
    return cfg


def ensure_diagnostic_directories(root, identity):
    '''
    Purpose
    -------
    Create ordered-pair and available separation-group diagnostic directories.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    identity: dict
        Output identity with organization prefix, category, and physical height
        geometry.

    Outputs
    -------
    None
        Creates managed organization roots and required diagnostic subdirectories.
    '''

    # Create ordered-pair and available separation-group diagnostic directories
    ensure_organization_roots(root)
    terminal = Path(root) / terminal_directory(identity)
    for diagnostic in DIAGNOSTICS:
        (terminal/identity['geometry']['pair']/diagnostic).mkdir(parents=True, exist_ok=True)
        separation=identity['geometry']['delta_z_rounded_km']
        if separation is not None:
            (terminal/f'delta_z_{separation}_km'/diagnostic).mkdir(parents=True, exist_ok=True)


def ensure_organization_roots(root):
    '''
    Purpose
    -------
    Create all registered observable and averaging-geometry root directories.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    None
        Creates observational Doppler-velocity and simulation observable folders under
        root.
    '''

    # Create all registered observable and averaging-geometry root directories
    root=Path(root)
    for geometry in XCORR_GEOMETRIES:
        (root/'observations'/'doppler_velocity'/geometry.title()).mkdir(parents=True,exist_ok=True)
        for observable in OBSERVABLES:
            (root/'simulations'/observable/geometry.title()).mkdir(parents=True,exist_ok=True)
