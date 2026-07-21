from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re

import output_paths


DATA_PRODUCTS = {
    'xc': 'time_distance',
    'phase_diff': 'phase_difference',
    'komega': 'komega_diagram',
    'coherence': 'coherence_diagram',
}

ANIMATION_SUFFIX_PRODUCTS = {
    'xc_radius_animation': 'time_distance',
    'xc_time_lag_animation': 'time_distance',
    'phase_diff_radius_animation': 'phase_difference',
    'phase_diff_frequency_animation': 'phase_difference',
}

FILTER_PARAM_RE = re.compile(
    r'gauss_ck_(?P<central_k>\d+(?:_\d+)?)_'
    r'wk_(?P<width_k>\d+(?:_\d+)?)_'
    r'cf_(?P<central_f>\d+(?:_\d+)?)_'
    r'wf_(?P<width_f>\d+(?:_\d+)?)',
    flags = re.IGNORECASE,
)
MAGNETOGRAM_RE = re.compile(
    r'b_(?P<relation>le|lt|ge|gt|eq)_(?P<threshold>\d+(?:_\d+)?)g',
    flags = re.IGNORECASE,
)


class FilterRegistry:
    def __init__(self, roots: list[Path]):
        self.roots = [Path(root).expanduser() for root in roots]
        self.text_to_name = {}
        self.max_number = 0
        self._load_existing()

    def _load_existing(self):
        for root in self.roots:
            if not root.exists():
                continue
            for candidate in root.iterdir():
                match = re.fullmatch(r'filter_(\d+)', candidate.name)
                if match is None or not candidate.is_dir():
                    continue
                number = int(match.group(1))
                self.max_number = max(self.max_number, number)
                parameter_file = candidate / 'filter_parameters.txt'
                if parameter_file.exists():
                    text = parameter_file.read_text(encoding = 'utf-8')
                    self.text_to_name.setdefault(text, candidate.name)

    def resolve(self, config):
        text = output_paths.filter_parameter_text(config)
        if text in self.text_to_name:
            return self.text_to_name[text], text

        self.max_number += 1
        name = f'filter_{self.max_number}'
        self.text_to_name[text] = name

        return name, text


def _number_token_to_float(token: str) -> float:
    return float(str(token).replace('_', '.'))


def _default_filtering():
    return {
        'enabled': False,
        'filter_sequence': [],
        'gaussian': {
            'enabled': False,
            'central_k': '',
            'width_k': '',
            'central_f': '',
            'width_f': '',
        },
        'magnetogram': {
            'enabled': False,
            'selection': 'nonmagnetic',
            'threshold_G': '',
            'fill_value': 0.0,
        },
    }


def infer_filtering_from_name(name: str):
    stem = Path(name).stem.lower()
    filtering = _default_filtering()
    sequence = []

    if 'gaussian_filtered' in stem or 'gaussian_filter' in stem or FILTER_PARAM_RE.search(stem):
        filtering['enabled'] = True
        filtering['gaussian']['enabled'] = True
        sequence.append('gaussian')
        match = FILTER_PARAM_RE.search(stem)
        if match is not None:
            for key, token in match.groupdict().items():
                filtering['gaussian'][key] = _number_token_to_float(token)
        else:
            filtering['gaussian']['central_k'] = 'unknown'
            filtering['gaussian']['width_k'] = 'unknown'
            filtering['gaussian']['central_f'] = 'unknown'
            filtering['gaussian']['width_f'] = 'unknown'

    if 'magnetogram' in stem or MAGNETOGRAM_RE.search(stem):
        filtering['enabled'] = True
        filtering['magnetogram']['enabled'] = True
        sequence.insert(0, 'magnetogram')
        match = MAGNETOGRAM_RE.search(stem)
        if match is not None:
            relation = match.group('relation').lower()
            filtering['magnetogram']['selection'] = 'magnetic' if relation in ['gt', 'ge'] else 'nonmagnetic'
            filtering['magnetogram']['threshold_G'] = _number_token_to_float(match.group('threshold'))
        else:
            filtering['magnetogram']['selection'] = 'nonmagnetic'
            filtering['magnetogram']['threshold_G'] = 'unknown'

    if filtering['enabled']:
        filtering['filter_sequence'] = sequence

    return filtering


def infer_geometry_from_name(name: str) -> str:
    stem = Path(name).stem.lower()
    tokens = set(stem.split('_'))
    for geometry in ['east', 'west', 'north', 'south']:
        if geometry in tokens:
            return geometry

    return 'annulus'


def infer_data_product(path: Path):
    stem = path.stem.lower()
    for suffix, product in DATA_PRODUCTS.items():
        if stem.endswith(f'_{suffix}'):
            return product

    return None


def infer_animation_product(path: Path):
    stem = path.stem.lower()
    for suffix, product in ANIMATION_SUFFIX_PRODUCTS.items():
        if stem.endswith(f'_{suffix}'):
            return product

    return None


def infer_source_config(path: Path, product: str):
    stem = path.stem.lower()
    filtering = infer_filtering_from_name(path.name)
    geometry = infer_geometry_from_name(path.name)
    config = {
        'data': {},
        'filtering': filtering,
        'time_distance': {'xcorr_geometry': geometry},
    }

    simulation_match = re.match(
        r'(?P<component>hx|vx|z0)_(?P<strength>\d+(?:_\d+)?g)_(?P<observable>v1|v2|v3|bb1|bb2|bb3|rho|temp|pressure)(?:_|$)',
        stem,
        flags = re.IGNORECASE,
    )
    if simulation_match is not None:
        component = simulation_match.group('component')
        strength = simulation_match.group('strength')
        observable = simulation_match.group('observable')
        config['data'] = {
            'source_type': 'single_cube',
            'file': f'{component}/{strength}/migration_source.nc',
            'observable': observable,
        }
        return config

    if re.match(r'\d{1,2}[a-z]{3}\d{4}', stem, flags = re.IGNORECASE):
        config['data'] = {
            'source_type': 'paired_cubes',
            'v1': path.name,
            'observable': 'v1',
        }
        return config

    return None


def destination_for(path: Path, root: Path, registry: FilterRegistry, product: str):
    config = infer_source_config(path, product)
    if config is None:
        return None, 'unclassified'

    filter_folder_name, text = registry.resolve(config)
    destination = output_paths.build_output_file(
        root,
        config,
        product,
        path.name,
        filter_folder_name,
        create = False,
    )

    return {
        'source': path,
        'destination': destination,
        'filter_folder': filter_folder_name,
        'filter_parameters': text,
        'config': config,
        'product': product,
        'root': root,
    }, ''


def iter_data_files(root: Path):
    if not root.exists():
        return

    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in ['.fits', '.fit', '.fts']:
            continue
        if any(re.fullmatch(r'filter_\d+', part) for part in path.relative_to(root).parts):
            continue
        product = infer_data_product(path)
        if product is not None:
            yield path, product


def iter_animation_files(root: Path):
    if not root.exists():
        return

    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() != '.mp4':
            continue
        if any(re.fullmatch(r'filter_\d+', part) for part in path.relative_to(root).parts):
            continue
        product = infer_animation_product(path)
        if product is not None:
            yield path, product


def collect_moves(project_root: Path):
    data_root = project_root / 'Data' / 'Time-Distance'
    animation_root = project_root / 'Morales 2025a et al' / 'Figures' / 'Animations'
    all_roots = [data_root, animation_root]
    registry = FilterRegistry(all_roots)
    moves = []
    skipped = Counter()

    for root, iterator in [(data_root, iter_data_files), (animation_root, iter_animation_files)]:
        for path, product in iterator(root):
            record, reason = destination_for(path, root, registry, product)
            if record is None:
                skipped[reason] += 1
                continue
            if record['source'].resolve() == record['destination'].resolve():
                skipped['already_in_place'] += 1
                continue
            moves.append(record)

    destination_counts = Counter(record['destination'] for record in moves)
    collisions = [destination for destination, count in destination_counts.items() if count > 1]
    if len(collisions) > 0:
        collision_set = set(collisions)
        safe_moves = []
        for record in moves:
            if record['destination'] in collision_set:
                skipped['destination_collision'] += 1
            else:
                safe_moves.append(record)
        moves = safe_moves

    return moves, skipped


def apply_moves(moves, dry_run: bool):
    moved = 0
    skipped = Counter()

    for record in moves:
        source = record['source']
        destination = record['destination']
        if destination.exists():
            skipped['destination_exists'] += 1
            continue

        if dry_run:
            continue

        output_paths.ensure_filter_parameters_file(
            record['root'],
            record['filter_folder'],
            record['filter_parameters'],
        )
        destination.parent.mkdir(parents = True, exist_ok = True)
        source.rename(destination)
        moved += 1

    return moved, skipped


def main():
    parser = argparse.ArgumentParser(description = 'Migrate time-distance outputs into the filter/product hierarchy.')
    parser.add_argument('--project-root', default = Path(__file__).resolve().parents[2], type = Path)
    parser.add_argument('--dry-run', action = 'store_true')
    args = parser.parse_args()

    project_root = args.project_root.expanduser().resolve()
    moves, skipped = collect_moves(project_root)
    moved, apply_skipped = apply_moves(moves, dry_run = args.dry_run)

    print(f'project_root={project_root}')
    print(f'planned_moves={len(moves)}')
    print(f'moved={moved}')
    if skipped:
        print('classification_skips=' + ','.join(f'{key}:{value}' for key, value in sorted(skipped.items())))
    if apply_skipped:
        print('apply_skips=' + ','.join(f'{key}:{value}' for key, value in sorted(apply_skipped.items())))
    for record in moves[:10]:
        print(f"{record['source']} -> {record['destination']}")


if __name__ == '__main__':
    main()
