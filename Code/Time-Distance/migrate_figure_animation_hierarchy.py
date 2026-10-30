'''
Purpose
-------
Retain historical figure/animation classification and move planning; script execution
delegates to recorded-provenance migration.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for migrate_figure_animation_hierarchy.py.
'''

from __future__ import annotations

# Import the libraries and shared helpers used by this module
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import sys
import re

import output_paths


FIGURE_ANIMATION_EXTENSIONS = {
    '.jpeg',
    '.jpg',
    '.png',
    '.gif',
    '.mp4',
    '.mov',
    '.m4v',
    '.webm',
}

GEOMETRIES = {'annulus', 'north', 'south', 'east', 'west'}
OBSERVABLES = {'v1', 'v2', 'v3', 'bb1', 'bb2', 'bb3', 'rho', 'temp', 'pressure'}
SOURCE_ROOTS = {'simulations', 'observations'}

# Parsing assumptions:
# - Gaussian filter parameters appear as gauss_ck_<k>_wk_<k-width>_cf_<f>_wf_<f-width>.
# - Magnetogram thresholds appear as b_<relation>_<threshold>g, where gt/ge are magnetic.
# - Simulation filenames usually start with hx|vx|z0_<field-strength>_<observable>.
# - Observation filenames or folders contain a compact date token such as 06may2019.
# Files that do not match these assumptions are logged to unclassified_files_*.log.
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
OBSERVATION_DATE_RE = re.compile(r'\d{1,2}[a-z]{3}\d{4}', flags = re.IGNORECASE)
SIMULATION_PREFIX_RE = re.compile(
    r'(?P<component>hx|vx|z0)_(?P<strength>\d+(?:_\d+)?g)_(?P<observable>v1|v2|v3|bb1|bb2|bb3|rho|temp|pressure)(?:_|$)',
    flags = re.IGNORECASE,
)


@dataclass(frozen = True)
class MigrationRecord:
    '''
    Purpose
    -------
    Hold one historical figure/animation migration decision.

    Inputs
    ------
    source: pathlib.Path
        Original artifact path.
    destination: pathlib.Path
        Planned output path.
    filter_folder: str
        Historical numbered filter-directory name.
    filter_parameters: str
        Recorded or inferred filter-setting text.
    product: str
        Registered diagnostic product kind.
    action: str
        Planned move or already-in-place skip action.

    Outputs
    -------
    record: MigrationRecord
        Frozen source/destination and filter/product/action metadata.
    '''

    source: Path
    destination: Path
    filter_folder: str
    filter_parameters: str
    product: str
    action: str


@dataclass(frozen = True)
class UnclassifiedRecord:
    '''
    Purpose
    -------
    Record an artifact whose historical identity could not be classified.

    Inputs
    ------
    source: pathlib.Path
        Unclassified original artifact.
    reason: str
        Missing or unsupported historical identity information.

    Outputs
    -------
    record: UnclassifiedRecord
        Frozen source path and explicit classification failure reason.
    '''

    source: Path
    reason: str


class FilterRegistry:
    '''
    Purpose
    -------
    Preserve existing historical filter-text mappings and allocate additional folder
    names.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    registry: FilterRegistry
        In-memory allocator for one historical figure/animation root.

    Notes
    -----
    Preserve existing filter_x mappings and allocate new generic filter folders.
    '''

    def __init__(self, root: Path):
        '''
        Purpose
        -------
        Initialize historical filter-folder mappings from an existing root.

        Inputs
        ------
        root: str or pathlib.Path
            Root directory for the paths managed by this helper.

        Outputs
        -------
        None
            Stores the resolved root, reads existing parameter files, and records the
            largest folder number.
        '''

        # Initialize historical filter-folder mappings from an existing root
        self.root = Path(root).expanduser().resolve()
        self.text_to_name: dict[str, str] = {}
        self.max_number = 0
        self._load_existing()

    def _load_existing(self) -> None:
        '''
        Purpose
        -------
        Inventory direct numbered filter folders and their recorded parameter text.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Updates text_to_name and max_number without creating directories.
        '''

        # Inventory direct numbered filter folders and their recorded parameter text
        if not self.root.exists():
            return

        for candidate in self.root.iterdir():
            match = re.fullmatch(r'filter_(\d+)', candidate.name)
            if match is None or not candidate.is_dir():
                continue

            self.max_number = max(self.max_number, int(match.group(1)))
            parameter_file = candidate / 'filter_parameters.txt'
            if parameter_file.exists():
                text = parameter_file.read_text(encoding = 'utf-8')
                self.text_to_name.setdefault(text, candidate.name)

    def resolve(self, config: dict) -> tuple[str, str]:
        '''
        Purpose
        -------
        Reuse or allocate a historical folder name for the supplied filter
        configuration.

        Inputs
        ------
        config: dict
            Resolved pipeline configuration, including data, sampling, filtering, and
            output settings.

        Outputs
        -------
        name, text: tuple of str
            In-memory folder mapping and serialized filter parameters.
        '''

        # Reuse or allocate a historical folder name for the supplied filter
        # configuration
        text = output_paths.filter_parameter_text(config)
        if text in self.text_to_name:
            return self.text_to_name[text], text

        self.max_number += 1
        filter_folder = f'filter_{self.max_number}'
        self.text_to_name[text] = filter_folder

        return filter_folder, text


def target_dir_default() -> Path:
    '''
    Purpose
    -------
    Resolve the project's default figure-animation target tree.

    Inputs
    ------
    None

    Outputs
    -------
    directory: pathlib.Path
        Resolved Figures directory joined to Animations.
    '''

    # Resolve the project's default figure-animation target tree
    project_root = Path(__file__).resolve().parents[2]
    return (project_root / 'Figures').resolve() / 'Animations'


def number_token_to_float(token: str) -> float:
    '''
    Purpose
    -------
    Decode the underscore decimal notation in historical filename parameters.

    Inputs
    ------
    token: str
        Legacy numeric token whose underscores represent decimal points.

    Outputs
    -------
    value: float
        Parsed numeric value; malformed tokens raise ValueError.
    '''

    # Decode the underscore decimal notation in historical filename parameters
    return float(str(token).replace('_', '.'))


def default_filtering() -> dict:
    '''
    Purpose
    -------
    Construct an inactive historical filtering metadata template.

    Inputs
    ------
    None

    Outputs
    -------
    filtering: dict
        New disabled Gaussian and magnetogram sections with blank unspecified values.
    '''

    # Construct an inactive historical filtering metadata template
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


def filter_folder_from_path(path: Path) -> str | None:
    '''
    Purpose
    -------
    Locate a numbered filter directory component in a historical path.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    name: str or None
        First exact filter_N path component, or None when absent.
    '''

    # Locate a numbered filter directory component in a historical path
    for part in path.parts:
        if re.fullmatch(r'filter_\d+', part):
            return part

    return None


def read_filter_parameters_for_folder(root: Path, filter_folder: str) -> str | None:
    '''
    Purpose
    -------
    Read parameter text from one historical numbered folder.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.
    filter_folder: str
        Historical filter_N folder relative to root.

    Outputs
    -------
    text: str or None
        UTF-8 filter_parameters.txt contents, or None when missing.
    '''

    # Read parameter text from one historical numbered folder
    parameter_file = root / filter_folder / 'filter_parameters.txt'
    if parameter_file.exists():
        return parameter_file.read_text(encoding = 'utf-8')

    return None


def infer_filtering_from_filename(path: Path) -> dict:
    '''
    Purpose
    -------
    Read only the filter metadata explicitly encoded in a historical filename.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    filtering: dict
        Inferred stage flags/values with unknown markers for omitted active-stage
        parameters.

    Notes
    -----
    Infer filtering metadata from legacy filename fragments only.
    '''

    # Read only the filter metadata explicitly encoded in a historical filename
    stem = path.stem.lower()
    filtering = default_filtering()
    sequence: list[str] = []

    gaussian_match = FILTER_PARAM_RE.search(stem)
    if 'gaussian_filtered' in stem or 'gaussian_filter' in stem or gaussian_match is not None:
        filtering['enabled'] = True
        filtering['gaussian']['enabled'] = True
        sequence.append('gaussian')
        if gaussian_match is not None:
            for key, token in gaussian_match.groupdict().items():
                filtering['gaussian'][key] = number_token_to_float(token)
        else:
            # Some old filenames only record that a Gaussian filter was applied.
            filtering['gaussian']['central_k'] = 'unknown'
            filtering['gaussian']['width_k'] = 'unknown'
            filtering['gaussian']['central_f'] = 'unknown'
            filtering['gaussian']['width_f'] = 'unknown'

    # Resolve separately encoded magnetic-stage settings and selection polarity
    magnetogram_match = MAGNETOGRAM_RE.search(stem)
    if 'magnetogram' in stem or magnetogram_match is not None:
        filtering['enabled'] = True
        filtering['magnetogram']['enabled'] = True
        sequence.insert(0, 'magnetogram')
        if magnetogram_match is not None:
            relation = magnetogram_match.group('relation').lower()
            filtering['magnetogram']['selection'] = 'magnetic' if relation in {'gt', 'ge'} else 'nonmagnetic'
            filtering['magnetogram']['threshold_G'] = number_token_to_float(magnetogram_match.group('threshold'))
        else:
            filtering['magnetogram']['selection'] = 'unknown'
            filtering['magnetogram']['threshold_G'] = 'unknown'

    if len(sequence) > 0:
        filtering['filter_sequence'] = sequence

    return filtering


def infer_geometry(path: Path) -> str:
    '''
    Purpose
    -------
    Resolve averaging geometry from path components or historical filename tokens.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    geometry: str
        Recognized annulus/directional geometry, defaulting to annulus when no token
        exists.
    '''

    # Resolve averaging geometry from path components or historical filename tokens
    for part in reversed(path.parts):
        lower_part = part.lower()
        if lower_part in GEOMETRIES:
            return lower_part

    tokens = set(path.stem.lower().split('_'))
    for geometry in ['north', 'south', 'east', 'west', 'annulus']:
        if geometry in tokens:
            return geometry

    return 'annulus'


def infer_observable(path: Path, source_type: str) -> str:
    '''
    Purpose
    -------
    Resolve a supported observable from directories or a simulation filename prefix.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    source_type: str
        single_cube or paired_cubes, selecting the historical fallback rule.

    Outputs
    -------
    observable: str
        Matched field, paired-cube v1 fallback, or empty text for an unresolved
        simulation field.
    '''

    # Resolve a supported observable from directories or a simulation filename prefix
    for part in reversed(path.parts):
        lower_part = part.lower()
        if lower_part in OBSERVABLES:
            return lower_part

    match = SIMULATION_PREFIX_RE.match(path.stem.lower())
    if match is not None:
        return match.group('observable').lower()

    tokens = path.stem.lower().split('_')
    for token in tokens:
        if token in OBSERVABLES:
            return token

    return 'v1' if source_type == 'paired_cubes' else ''


def infer_product(path: Path) -> str | None:
    '''
    Purpose
    -------
    Classify a historical image/animation into a diagnostic product family.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    product: str or None
        Time-distance, phase, or komega product kind; retired orientation-validation and
        unmatched artifacts return None.
    '''

    # Classify a historical image/animation into a diagnostic product family
    if 'magnetic_orientation_validation' in path.stem.lower():
        return None
    for part in reversed(path.parts):
        lower_part = part.lower()
        if lower_part == 'xcorr':
            return 'time_distance'
        if lower_part == 'phase':
            return 'phase_difference'
        if lower_part == 'komega':
            return 'komega_diagram'

    stem = path.stem.lower()
    if 'phase_diff' in stem or 'frequency_animation' in stem:
        return 'phase_difference'
    if (
        re.search(r'(^|_)xc($|_)', stem)
        or 'xcorr' in stem
        or 'time_lag_animation' in stem
        or ('radius_animation' in stem and 'phase_diff' not in stem)
    ):
        return 'time_distance'
    if any(token in stem for token in ['komega', 'gaussian_filter', 'dopplergram', 'composite']):
        return 'komega_diagram'

    return None


def infer_source_type(path: Path) -> str | None:
    '''
    Purpose
    -------
    Classify simulation versus observation provenance from historical paths/names.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    source_type: str or None
        single_cube, paired_cubes, or None when neither convention is present.
    '''

    # Classify simulation versus observation provenance from historical paths/names
    lower_parts = [part.lower() for part in path.parts]
    if 'simulations' in lower_parts:
        return 'single_cube'
    if 'observations' in lower_parts:
        return 'paired_cubes'
    if SIMULATION_PREFIX_RE.match(path.stem.lower()) is not None:
        return 'single_cube'
    if OBSERVATION_DATE_RE.search(path.stem.lower()) is not None:
        return 'paired_cubes'

    return None


def infer_magnetogram_selection(path: Path, filtering: dict) -> str:
    '''
    Purpose
    -------
    Resolve the historical magnetic-selection folder label.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    filtering: dict
        Historical filter metadata used when no folder label exists.

    Outputs
    -------
    folder: str
        magneto/nonmagneto from explicit path components or inferred filter selection.
    '''

    # Resolve the historical magnetic-selection folder label
    lower_parts = [part.lower() for part in path.parts]
    if 'magneto' in lower_parts:
        return 'magneto'
    if 'nonmagneto' in lower_parts:
        return 'nonmagneto'

    magnetogram = filtering.get('magnetogram', {})
    if magnetogram.get('enabled', False):
        return 'magneto' if str(magnetogram.get('selection', '')).lower() == 'magnetic' else 'nonmagneto'

    return 'nonmagneto'


def infer_simulation_file_token(path: Path) -> str:
    '''
    Purpose
    -------
    Reconstruct a historical simulation label from orientation and field-strength
    tokens.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    label: str
        orientation/strength/migration_source.nc placeholder, retaining unknown markers
        where needed.
    '''

    # Reconstruct a historical simulation label from orientation and field-strength
    # tokens
    lower_parts = [part.lower() for part in path.parts]
    orientation = ''
    strength = ''

    if 'horizontal' in lower_parts:
        orientation = 'hx'
    elif 'vertical' in lower_parts:
        orientation = 'vx'

    for part in path.parts:
        if re.fullmatch(r'\d+(?:_\d+)?g', part.lower(), flags = re.IGNORECASE):
            strength = part.lower()
            break

    match = SIMULATION_PREFIX_RE.match(path.stem.lower())
    if match is not None:
        component = match.group('component').lower()
        strength = match.group('strength').lower()
        if component in {'hx', 'vx'}:
            orientation = component
        else:
            orientation = 'z0'

    if orientation == '':
        orientation = 'z0' if strength in {'0g', '0G'} else 'unknown'
    if strength == '':
        strength = 'unknownG'

    return f'{orientation}/{strength}/migration_source.nc'


def infer_observation_date_token(path: Path) -> str | None:
    '''
    Purpose
    -------
    Locate a compact observational date in path components or the filename.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    date: str or None
        Lowercase compact date token, or None when absent.
    '''

    # Locate a compact observational date in path components or the filename
    for part in reversed(path.parts):
        if OBSERVATION_DATE_RE.fullmatch(part):
            return part.lower()

    match = OBSERVATION_DATE_RE.search(path.stem.lower())
    if match is not None:
        return match.group(0).lower()

    return None


def build_inferred_config(path: Path) -> tuple[dict | None, str | None]:
    '''
    Purpose
    -------
    Construct limited source/filter metadata from a historical artifact path.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    config, reason: tuple
        Inferred dictionary and None, or (None, explicit missing-token reason). This
        does not establish complete modern source/height provenance.
    '''

    # Construct limited source/filter metadata from a historical artifact path
    product = infer_product(path)
    if product is None:
        return None, 'missing product token'

    # Require source and observable labels before constructing a historical placeholder
    # configuration
    source_type = infer_source_type(path)
    if source_type is None:
        return None, 'missing source type token'

    filtering = infer_filtering_from_filename(path)
    geometry = infer_geometry(path)
    observable = infer_observable(path, source_type)
    if observable == '':
        return None, 'missing observable token'

    # Preserve an explicitly magnetic path's recorded selection semantics
    magnetogram_folder = infer_magnetogram_selection(path, filtering)
    if magnetogram_folder == 'magneto':
        filtering['enabled'] = True
        filtering['magnetogram']['enabled'] = True
        if 'magnetogram' not in filtering['filter_sequence']:
            filtering['filter_sequence'].insert(0, 'magnetogram')
        if filtering['magnetogram'].get('selection', '') in ['', 'unknown', None]:
            filtering['magnetogram']['selection'] = 'magnetic'

    config = {
        'filtering': filtering,
        'time_distance': {'xcorr_geometry': geometry},
        'data': {'observable': observable},
    }

    # Construct mode-specific historical source labels without asserting missing modern
    # provenance
    if source_type == 'single_cube':
        config['data'].update({
            'source_type': 'single_cube',
            'file': infer_simulation_file_token(path),
            'observable': observable,
        })
    else:
        date_token = infer_observation_date_token(path)
        if date_token is None:
            return None, 'missing observation date token'
        config['data'].update({
            'source_type': 'paired_cubes',
            'v1': f'{date_token}_migration_source.fits',
            'observable': observable,
        })

    return config, None


def is_candidate_file(path: Path, target_dir: Path) -> bool:
    '''
    Purpose
    -------
    Recognize supported nonhidden figure/animation artifacts outside migration logs.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    target_dir: pathlib.Path
        Containing tree used to exclude migration_logs subdirectories.

    Outputs
    -------
    accepted: bool
        True for existing recognized media suffixes that are eligible for
        classification.
    '''

    # Recognize supported nonhidden figure/animation artifacts outside migration logs
    if not path.is_file():
        return False
    if path.name == 'filter_parameters.txt':
        return False
    if path.name.startswith('.'):
        return False
    if 'migration_logs' in path.relative_to(target_dir).parts:
        return False

    return path.suffix.lower() in FIGURE_ANIMATION_EXTENSIONS


def iter_candidate_files(target_dir: Path):
    '''
    Purpose
    -------
    Yield eligible figure/animation paths in stable relative-path order.

    Inputs
    ------
    target_dir: pathlib.Path
        Historical figure/animation tree to search recursively.

    Outputs
    -------
    paths: iterator of pathlib.Path
        Candidate artifacts under target_dir.
    '''

    # Yield eligible figure/animation paths in stable relative-path order
    for path in sorted(target_dir.rglob('*'), key = lambda candidate: candidate.relative_to(target_dir).as_posix()):
        if is_candidate_file(path, target_dir):
            yield path


def resolve_filter_folder(path: Path, target_dir: Path, config: dict, registry: FilterRegistry) -> tuple[str, str]:
    '''
    Purpose
    -------
    Preserve a recorded numbered folder or allocate a filter-text mapping.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    target_dir: pathlib.Path
        Historical root containing numbered filter folders.
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    registry: FilterRegistry
        Shared in-memory allocator used when no recorded folder exists.

    Outputs
    -------
    name, text: tuple of str
        Existing folder/parameter text or registry-allocated values.
    '''

    # Preserve a recorded numbered folder or allocate a filter-text mapping
    current_filter_folder = filter_folder_from_path(path.relative_to(target_dir))
    if current_filter_folder is not None:
        existing_text = read_filter_parameters_for_folder(target_dir, current_filter_folder)
        if existing_text is not None:
            return current_filter_folder, existing_text
        return current_filter_folder, output_paths.filter_parameter_text(config)

    return registry.resolve(config)


def resolve_collision(destination: Path, source: Path, reserved: set[Path]) -> Path:
    '''
    Purpose
    -------
    Choose a destination without overwriting existing or reserved artifacts.

    Inputs
    ------
    destination: pathlib.Path
        Initially requested output path.
    source: pathlib.Path
        Original artifact whose in-place destination is allowed.
    reserved: set of pathlib.Path
        Destinations already assigned by this plan; not mutated here.

    Outputs
    -------
    destination: pathlib.Path
        Original destination for an in-place artifact, otherwise the first available
        _duplicate_N variant.
    '''

    # Choose a destination without overwriting existing or reserved artifacts
    if destination.resolve() == source.resolve():
        return destination

    candidate = destination
    counter = 1
    while candidate.exists() or candidate in reserved:
        candidate = destination.with_name(f'{destination.stem}_duplicate_{counter}{destination.suffix}')
        counter += 1

    return candidate


def build_destination(path: Path, target_dir: Path, registry: FilterRegistry, reserved: set[Path]) -> tuple[MigrationRecord | None, UnclassifiedRecord | None]:
    '''
    Purpose
    -------
    Classify one artifact and reserve its resolved historical migration destination.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    target_dir: pathlib.Path
        Root used for the historical destination hierarchy.
    registry: FilterRegistry
        Shared numbered filter-folder mapping.
    reserved: set of pathlib.Path
        Already planned destinations, updated after successful classification.

    Outputs
    -------
    record, unclassified: tuple
        MigrationRecord and None, or None and UnclassifiedRecord; adds successful
        destinations to reserved.
    '''

    # Classify one artifact and reserve its resolved historical migration destination
    config, reason = build_inferred_config(path)
    if config is None:
        return None, UnclassifiedRecord(source = path, reason = reason or 'unclassified')

    product = infer_product(path)
    assert product is not None
    filter_folder, filter_parameters = resolve_filter_folder(path, target_dir, config, registry)
    destination = output_paths.build_output_file(
        target_dir,
        config,
        product,
        path.name,
        filter_folder,
        create = False,
    )
    destination = resolve_collision(destination, path, reserved)
    reserved.add(destination)
    action = 'skip' if destination.resolve() == path.resolve() else 'move'

    return MigrationRecord(
        source = path,
        destination = destination,
        filter_folder = filter_folder,
        filter_parameters = filter_parameters,
        product = product,
        action = action,
    ), None


def build_migration_plan(target_dir: Path) -> tuple[list[MigrationRecord], list[UnclassifiedRecord]]:
    '''
    Purpose
    -------
    Collect classified and unclassified historical figure/animation records.

    Inputs
    ------
    target_dir: pathlib.Path
        Historical artifact tree to inspect.

    Outputs
    -------
    records, unclassified: tuple of list
        Collision-resolved plan and explicit missing-identity records; no media files
        are moved.
    '''

    # Collect classified and unclassified historical figure/animation records
    target_dir = Path(target_dir).expanduser().resolve()
    registry = FilterRegistry(target_dir)
    reserved: set[Path] = set()
    records: list[MigrationRecord] = []
    unclassified: list[UnclassifiedRecord] = []

    for path in iter_candidate_files(target_dir):
        record, skipped = build_destination(path, target_dir, registry, reserved)
        if skipped is not None:
            unclassified.append(skipped)
        elif record is not None:
            records.append(record)

    return records, unclassified


def write_logs(log_dir: Path, records: list[MigrationRecord], unclassified: list[UnclassifiedRecord], *, dry_run: bool) -> tuple[Path, Path]:
    '''
    Purpose
    -------
    Write timestamped migration and unclassified-artifact reports.

    Inputs
    ------
    log_dir: pathlib.Path
        Directory created for migration reports.
    records: list of MigrationRecord
        Classified migration decisions.
    unclassified: list of UnclassifiedRecord
        Artifacts and their classification failure reasons.
    dry_run: bool
        Label the log as a dry-run or execution report.

    Outputs
    -------
    migration_log, unclassified_log: tuple of pathlib.Path
        Newly written log files describing the plan and requested execution mode.
    '''

    # Write timestamped migration and unclassified-artifact reports
    log_dir.mkdir(parents = True, exist_ok = True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    migration_log = log_dir / f'figure_animation_migration_{timestamp}.log'
    unclassified_log = log_dir / f'unclassified_files_{timestamp}.log'
    mode = 'DRY_RUN' if dry_run else 'EXECUTE'

    with migration_log.open('w', encoding = 'utf-8') as handle:
        handle.write(f'mode\\t{mode}\\n')
        handle.write('action\\tsource\\tdestination\\tproduct\\tfilter_folder\\n')
        for record in records:
            handle.write(
                f'{record.action}\\t{record.source}\\t{record.destination}\\t'
                f'{record.product}\\t{record.filter_folder}\\n'
            )

    with unclassified_log.open('w', encoding = 'utf-8') as handle:
        handle.write('reason\\tsource\\n')
        for record in unclassified:
            handle.write(f'{record.reason}\\t{record.source}\\n')

    return migration_log, unclassified_log


def apply_migration(target_dir: Path, records: list[MigrationRecord], *, dry_run: bool) -> Counter:
    '''
    Purpose
    -------
    Apply a historical migration plan or summarize its dry-run actions.

    Inputs
    ------
    target_dir: pathlib.Path
        Historical root receiving parameter files and output directories.
    records: list of MigrationRecord
        Classified and collision-resolved plan.
    dry_run: bool
        Count actions without moving or writing when True.

    Outputs
    -------
    summary: collections.Counter
        Move/skip/failure counts. Execution writes filter metadata, creates directories,
        and moves files without overwriting newly occupied destinations.
    '''

    # Apply a historical migration plan or summarize its dry-run actions
    summary = Counter()
    if dry_run:
        summary['dry_run'] = sum(1 for record in records if record.action == 'move')
        summary['already_in_place'] = sum(1 for record in records if record.action == 'skip')
        return summary

    for record in records:
        if record.action == 'skip':
            summary['already_in_place'] += 1
            continue

        output_paths.ensure_filter_parameters_file(target_dir, record.filter_folder, record.filter_parameters)
        record.destination.parent.mkdir(parents = True, exist_ok = True)
        if record.destination.exists():
            summary['destination_exists_after_plan'] += 1
            continue

        try:
            shutil.move(str(record.source), str(record.destination))
        except Exception:
            summary['move_failed'] += 1
            raise
        else:
            summary['moved'] += 1

    return summary


def print_plan(records: list[MigrationRecord], unclassified: list[UnclassifiedRecord], summary: Counter, migration_log: Path, unclassified_log: Path, *, limit: int) -> None:
    '''
    Purpose
    -------
    Print migration counts, log locations, and a bounded move preview.

    Inputs
    ------
    records: list of MigrationRecord
        Classified migration decisions.
    unclassified: list of UnclassifiedRecord
        Unclassified artifact records.
    summary: collections.Counter
        Applied or dry-run action counters.
    migration_log: pathlib.Path
        Migration report filename to print.
    unclassified_log: pathlib.Path
        Unclassified report filename to print.
    limit: int
        Maximum number of move mappings shown in the preview.

    Outputs
    -------
    None
        Writes the human-readable plan summary to standard output.
    '''

    # Print migration counts, log locations, and a bounded move preview
    print(f'planned_records={len(records)}')
    print(f'unclassified={len(unclassified)}')
    for key, value in sorted(summary.items()):
        print(f'{key}={value}')
    print(f'migration_log={migration_log}')
    print(f'unclassified_log={unclassified_log}')

    printed = 0
    for record in records:
        if record.action != 'move':
            continue
        print(f'{record.source} -> {record.destination}')
        printed += 1
        if printed >= limit:
            break


def main() -> int:
    '''
    Purpose
    -------
    Parse and run the retained historical figure/animation migration command.

    Inputs
    ------
    None

    Outputs
    -------
    status: int
        Zero after planning/logging and optional moves. Direct script execution
        currently delegates to migrate_geometry_outputs.main instead.
    '''

    # Parse and run the retained historical figure/animation migration command
    parser = argparse.ArgumentParser(
        description = 'Safely migrate figure and animation files into the filter/product hierarchy.'
    )
    parser.add_argument('--target-dir', type = Path, default = target_dir_default())
    parser.add_argument('--log-dir', type = Path, default = None)
    parser.add_argument('--dry-run', action = 'store_true', help = 'Plan and log moves without moving files.')
    parser.add_argument('--execute', action = 'store_true', help = 'Perform the planned moves.')
    parser.add_argument('--preview-limit', type = int, default = 25)
    args = parser.parse_args()

    if args.dry_run and args.execute:
        parser.error('Use either --dry-run or --execute, not both.')

    dry_run = not args.execute
    target_dir = args.target_dir.expanduser().resolve()
    if not target_dir.exists():
        raise FileNotFoundError(f'Target directory does not exist: {target_dir}')

    log_dir = args.log_dir.expanduser().resolve() if args.log_dir is not None else target_dir / 'migration_logs'
    records, unclassified = build_migration_plan(target_dir)
    migration_log, unclassified_log = write_logs(log_dir, records, unclassified, dry_run = dry_run)
    summary = apply_migration(target_dir, records, dry_run = dry_run)
    print_plan(records, unclassified, summary, migration_log, unclassified_log, limit = max(0, args.preview_limit))

    if not args.execute:
        print('Dry run only. Re-run with --execute to move files.')

    return 0


if __name__ == '__main__':
    from migrate_geometry_outputs import main as geometry_migration_main
    geometry_migration_main()
