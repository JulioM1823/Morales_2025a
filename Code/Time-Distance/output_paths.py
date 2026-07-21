from pathlib import Path
from datetime import datetime
import re


XCORR_GEOMETRY_DEFAULT = 'annulus'
XCORR_GEOMETRIES = ('annulus', 'east', 'west', 'north', 'south')
OBSERVABLES = ('v1', 'v2', 'v3', 'bb1', 'bb2', 'bb3', 'rho', 'temp', 'pressure')

PRODUCT_DIRECTORY = {
    'time_distance': 'xcorr',
    'phase_difference': 'phase',
    'komega_diagram': 'komega',
    'coherence_diagram': 'komega',
    'orientation_validation': 'komega',
    'gaussian_filter': 'komega',
    'filtered_dopplergram': 'komega',
    'composite_diagnostics': 'komega',
}


def slugify(value):
    value = str(value).strip().lower()
    value = value.replace('å', 'a')
    value = re.sub(r'angstrom', 'a', value, flags = re.IGNORECASE)
    value = re.sub(r'[^0-9a-z]+', '_', value)
    value = re.sub(r'_+', '_', value)

    return value.strip('_')


def join_slug(parts):
    normalized = [slugify(part) for part in parts if str(part).strip() != '']
    normalized = [part for part in normalized if part != '']

    return '_'.join(normalized).strip('_')


def normalize_xcorr_geometry(geometry):
    if geometry in ['', None]:
        geometry = XCORR_GEOMETRY_DEFAULT

    normalized = str(geometry).strip().lower()
    if normalized not in XCORR_GEOMETRIES:
        raise ValueError(
            "time_distance['xcorr_geometry'] must be one of "
            "'annulus', 'east', 'west', 'north', or 'south'.")

    return normalized


def normalize_observable_slug(observable):
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

    normalized = str(observable or '').strip().lower()
    normalized = alias_lookup.get(normalized, normalized)

    return normalized if normalized in OBSERVABLES else slugify(normalized or 'v1')


def resolve_output_observable(config):
    data = config.get('data', {})
    source_type = str(data.get('source_type', '')).strip().lower()

    if source_type == 'single_cube':
        return normalize_observable_slug(data.get('observable', data.get('single_cube', {}).get('observable', '')))

    return normalize_observable_slug(data.get('observable', 'v1'))


def resolve_output_geometry(config):
    return normalize_xcorr_geometry(
        config.get('time_distance', {}).get('xcorr_geometry', XCORR_GEOMETRY_DEFAULT)
    )


def resolve_magnetogram_folder(config):
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


def _infer_observation_date_slug(file_path):
    text = str(file_path)
    match = re.search(r'(\d{1,2}[A-Za-z]{3}\d{4})', text)
    if match is not None:
        return datetime.strptime(match.group(1), '%d%b%Y').strftime('%d%b%Y').lower()

    parent_name = Path(text).expanduser().parent.name
    return slugify(parent_name or 'unknown_date')


def infer_simulation_path_metadata(file_path):
    path = Path(str(file_path))
    orientation = ''
    strength = ''

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
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten_filter_parameters(f'{prefix}.{key}' if prefix else str(key), value[key], rows)
        return

    rows.append((prefix, _format_filter_value(value)))


def filter_parameter_text(config):
    filtering = config.get('filtering', {})
    rows = []
    _flatten_filter_parameters('filtering', filtering, rows)
    if len(rows) == 0:
        rows.append(('filtering.enabled', 'false'))

    return '\n'.join(f'{key}: {value}' for key, value in rows) + '\n'


def _filter_folder_number(path):
    match = re.fullmatch(r'filter_(\d+)', path.name)
    return int(match.group(1)) if match is not None else None


def _scan_filter_folders(roots):
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
    folder = Path(root).expanduser() / filter_folder_name
    folder.mkdir(parents = True, exist_ok = True)
    parameter_file = folder / 'filter_parameters.txt'

    if not parameter_file.exists() or parameter_file.read_text(encoding = 'utf-8') != text:
        parameter_file.write_text(text, encoding = 'utf-8')

    return folder


def clean_output_filename(filename):
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
    if product not in PRODUCT_DIRECTORY:
        raise ValueError(f'Unsupported output product: {product}')

    return PRODUCT_DIRECTORY[product]


def build_output_directory(root, config, product, filter_folder_name):
    data = config.get('data', {})
    source_type = str(data.get('source_type', '')).strip().lower()
    output_dir = Path(root).expanduser() / filter_folder_name
    output_dir = output_dir / ('simulations' if source_type == 'single_cube' else 'observations')
    output_dir = output_dir / resolve_magnetogram_folder(config)

    if source_type == 'single_cube':
        simulation_meta = infer_simulation_path_metadata(data.get('file', data.get('single_cube', {}).get('file', '')))
        if simulation_meta['orientation'] != '':
            output_dir = output_dir / simulation_meta['orientation']
        output_dir = output_dir / simulation_meta['strength']
    else:
        paired = data.get('paired_cubes', {})
        date_source = data.get('v1', paired.get('v1', paired.get('file_1', '')))
        output_dir = output_dir / _infer_observation_date_slug(date_source)

    return (
        output_dir
        / product_directory(product)
        / resolve_output_geometry(config)
        / resolve_output_observable(config)
    )


def build_output_file(root, config, product, filename, filter_folder_name, create = True):
    output_dir = build_output_directory(root, config, product, filter_folder_name)
    if create:
        output_dir.mkdir(parents = True, exist_ok = True)

    return output_dir / clean_output_filename(filename)


def build_runtime_output_paths(config, data_output_dir, figure_output_dir = None, create = True):
    roots = [Path(data_output_dir).expanduser()]
    if figure_output_dir not in ['', None]:
        roots.append(Path(figure_output_dir).expanduser())

    filter_folder_name, text = resolve_filter_folder_name(config, roots)
    if create:
        for root in roots:
            ensure_filter_parameters_file(root, filter_folder_name, text)

    return {
        'filter_folder': filter_folder_name,
        'filter_parameters': text,
        'data_root': roots[0],
        'figure_root': roots[1] if len(roots) > 1 else None,
    }


def mirror_hierarchy_from_data_file(target_root, data_file, output_filename, create = True):
    target_root = Path(target_root).expanduser().resolve()
    data_file = Path(data_file).expanduser().resolve()
    output_filename = clean_output_filename(output_filename)
    parts = data_file.parts
    filter_index = None

    for index, part in enumerate(parts):
        if re.fullmatch(r'filter_\d+', part):
            filter_index = index
            break

    if filter_index is None:
        output_file = target_root / output_filename
        if create:
            output_file.parent.mkdir(parents = True, exist_ok = True)
        return output_file

    relative_parent = Path(*parts[filter_index:-1])
    output_file = target_root / relative_parent / output_filename

    source_parameter_file = Path(*parts[:filter_index + 1]) / 'filter_parameters.txt'
    target_parameter_file = target_root / parts[filter_index] / 'filter_parameters.txt'
    if create:
        output_file.parent.mkdir(parents = True, exist_ok = True)
        if source_parameter_file.exists():
            target_parameter_file.parent.mkdir(parents = True, exist_ok = True)
            source_text = source_parameter_file.read_text(encoding = 'utf-8')
            if not target_parameter_file.exists() or target_parameter_file.read_text(encoding = 'utf-8') != source_text:
                target_parameter_file.write_text(source_text, encoding = 'utf-8')

    return output_file
