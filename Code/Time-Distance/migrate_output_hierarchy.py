'''
Purpose
-------
Retain historical output-migration helpers; script execution delegates to
recorded-provenance geometry migration.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for migrate_output_hierarchy.py.
'''

from __future__ import annotations

# Import the libraries and shared helpers used by this module
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
    '''
    Purpose
    -------
    Retain existing filter-text mappings while allocating new historical numbered
    folders.

    Inputs
    ------
    roots: list of pathlib.Path
        Historical roots containing direct filter_N directories.

    Outputs
    -------
    registry: FilterRegistry
        In-memory text-to-folder registry spanning the supplied roots.
    '''

    def __init__(self, roots: list[Path]):
        '''
        Purpose
        -------
        Initialize the historical filter registry from the supplied roots.

        Inputs
        ------
        roots: list of pathlib.Path
            Historical roots containing numbered filter folders.

        Outputs
        -------
        None
            Expands roots and inventories existing folder numbers and parameter text.
        '''

        # Initialize the historical filter registry from the supplied roots
        self.roots = [Path(root).expanduser() for root in roots]
        self.text_to_name = {}
        self.max_number = 0
        self._load_existing()

    def _load_existing(self):
        '''
        Purpose
        -------
        Read existing direct filter folders and their optional parameter text.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Updates text_to_name and the maximum known folder number; absent roots are
            skipped.
        '''

        # Read existing direct filter folders and their optional parameter text
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
        '''
        Purpose
        -------
        Reuse or allocate a numbered folder for the configuration's filter text.

        Inputs
        ------
        config: dict
            Resolved pipeline configuration, including data, sampling, filtering, and
            output settings.

        Outputs
        -------
        name, text: tuple of str
            Existing or newly allocated in-memory folder mapping; no directories are
            written here.
        '''

        # Reuse or allocate a numbered folder for the configuration's filter text
        text = output_paths.filter_parameter_text(config)
        if text in self.text_to_name:
            return self.text_to_name[text], text

        self.max_number += 1
        name = f'filter_{self.max_number}'
        self.text_to_name[text] = name

        return name, text


def _number_token_to_float(token: str) -> float:
    '''
    Purpose
    -------
    Decode a legacy underscore decimal token into a float.

    Inputs
    ------
    token: str
        Historical numeric filename token.

    Outputs
    -------
    value: float
        Parsed number after replacing underscores with decimal points.
    '''

    # Decode a legacy underscore decimal token into a float
    return float(str(token).replace('_', '.'))


def _default_filtering():
    '''
    Purpose
    -------
    Construct the inactive historical filtering template.

    Inputs
    ------
    None

    Outputs
    -------
    filtering: dict
        New disabled Gaussian/magnetogram settings with blank unspecified parameters.
    '''

    # Construct the inactive historical filtering template
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
    '''
    Purpose
    -------
    Read available Gaussian/magnetogram settings from historical filename tokens.

    Inputs
    ------
    name: str
        Historical artifact filename.

    Outputs
    -------
    filtering: dict
        Inferred filter settings with unknown markers where active-stage values were not
        encoded.
    '''

    # Read available Gaussian/magnetogram settings from historical filename tokens
    stem = Path(name).stem.lower()
    filtering = _default_filtering()
    sequence = []

    # Recover Gaussian settings only from available historical filename tokens
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

    # Recover magnetic-selection metadata and mark unrecorded thresholds explicitly
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
    '''
    Purpose
    -------
    Resolve an explicit directional filename token or use the historical annulus
    default.

    Inputs
    ------
    name: str
        Historical artifact filename whose underscore tokens are inspected.

    Outputs
    -------
    geometry: str
        east, west, north, south, or annulus.
    '''

    # Resolve an explicit directional filename token or use the historical annulus
    # default
    stem = Path(name).stem.lower()
    tokens = set(stem.split('_'))
    for geometry in ['east', 'west', 'north', 'south']:
        if geometry in tokens:
            return geometry

    return 'annulus'


def infer_data_product(path: Path):
    '''
    Purpose
    -------
    Match a historical FITS stem to a known numerical product suffix.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    product: str or None
        Registered time-distance, phase, komega, or coherence product kind.
    '''

    # Match a historical FITS stem to a known numerical product suffix
    stem = path.stem.lower()
    for suffix, product in DATA_PRODUCTS.items():
        if stem.endswith(f'_{suffix}'):
            return product

    return None


def infer_animation_product(path: Path):
    '''
    Purpose
    -------
    Match a historical MP4 stem to a known animation suffix.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    product: str or None
        Time-distance or phase-difference product kind, or None when unmatched.
    '''

    # Match a historical MP4 stem to a known animation suffix
    stem = path.stem.lower()
    for suffix, product in ANIMATION_SUFFIX_PRODUCTS.items():
        if stem.endswith(f'_{suffix}'):
            return product

    return None


def infer_source_config(path: Path, product: str):
    '''
    Purpose
    -------
    Build the limited historical source configuration encoded in a filename.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    product: str
        Retained product-kind argument; not currently used during source inference.

    Outputs
    -------
    config: dict or None
        Inferred filtering/geometry/source fields, or None for unclassified names; this
        inference does not supply complete modern physical provenance.
    '''

    # Build the limited historical source configuration encoded in a filename
    stem = path.stem.lower()
    filtering = infer_filtering_from_name(path.name)
    geometry = infer_geometry_from_name(path.name)
    config = {
        'data': {},
        'filtering': filtering,
        'time_distance': {'xcorr_geometry': geometry},
    }

    # Classify explicit simulation case and observable tokens before observational dates
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

    # Retain only the limited source metadata actually encoded by the observational name
    if re.match(r'\d{1,2}[a-z]{3}\d{4}', stem, flags = re.IGNORECASE):
        config['data'] = {
            'source_type': 'paired_cubes',
            'v1': path.name,
            'observable': 'v1',
        }
        return config

    return None


def destination_for(path: Path, root: Path, registry: FilterRegistry, product: str):
    '''
    Purpose
    -------
    Resolve a historical migration destination through the output-path manager.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    registry: FilterRegistry
        Shared in-memory filter-folder allocator.
    product: str
        Registered numerical or animation product kind.

    Outputs
    -------
    record, reason: tuple
        Move record and empty reason, or (None, 'unclassified'); downstream
        path/provenance validation errors propagate.
    '''

    # Resolve a historical migration destination through the output-path manager
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
    '''
    Purpose
    -------
    Yield eligible ungrouped historical FITS products under a root.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    products: iterator of tuple
        (path, product kind) pairs excluding existing filter_N subtrees.
    '''

    # Yield eligible ungrouped historical FITS products under a root
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
    '''
    Purpose
    -------
    Yield eligible ungrouped historical MP4 products under a root.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    products: iterator of tuple
        (path, product kind) pairs excluding existing filter_N subtrees.
    '''

    # Yield eligible ungrouped historical MP4 products under a root
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
    '''
    Purpose
    -------
    Collect historical data/animation moves and remove conflicting destination
    assignments.

    Inputs
    ------
    project_root: pathlib.Path
        Project containing Data/Time-Distance and Figures/Animations.

    Outputs
    -------
    moves, skipped: tuple
        Move records and classification/collision counters; no products are moved.
    '''

    # Collect historical data/animation moves and remove conflicting destination
    # assignments
    data_root = project_root / 'Data' / 'Time-Distance'
    animation_root = (project_root / 'Figures').resolve() / 'Animations'
    all_roots = [data_root, animation_root]
    registry = FilterRegistry(all_roots)
    moves = []
    skipped = Counter()

    # Collect recognized data and animation records without moving source bytes
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

    # Remove all colliding destinations from the executable move plan
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
    '''
    Purpose
    -------
    Apply nonconflicting planned historical moves unless dry-run mode is active.

    Inputs
    ------
    moves: iterable of dict
        Planned source/destination/filter records.
    dry_run: bool
        Skip filesystem mutation when True.

    Outputs
    -------
    moved, skipped: tuple
        Moved-file count and existing-destination counters. Execution creates parameter
        files/directories and renames sources.
    '''

    # Apply nonconflicting planned historical moves unless dry-run mode is active
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
    '''
    Purpose
    -------
    Parse and execute the retained historical hierarchy-migration command.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Reads sys.argv and reports planned/applied moves. Direct script execution
        currently delegates to migrate_geometry_outputs.main instead.
    '''

    # Parse and execute the retained historical hierarchy-migration command
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
    from migrate_geometry_outputs import main as geometry_migration_main
    geometry_migration_main()
