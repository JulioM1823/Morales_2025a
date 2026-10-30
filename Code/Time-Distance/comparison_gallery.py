'''
Purpose
-------
Discover comparison figures and publish linked HTML galleries and individual subplot
pages.

Navigation records retain source identities, pixel crops, and percentage hit
bounds. Embedded HTML and JavaScript implement the browser views generated
by the Python publishing functions.

Static HTML galleries for comparison-plot outputs.

The plotting pipeline records explicit numerical sources and launch context
alongside new megaplots; older image-only galleries retain their navigation.

Inputs
------
None

Outputs
-------
exports: functions and classes
    Numerical helpers or publication interfaces defined below; importing the
    module does not execute the command-line pipeline.
'''


# Import the relevant libraries and shared project helpers.
from __future__ import annotations
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar

from dataclasses import dataclass
from html import escape
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
from typing import Any, Iterable
from urllib.parse import quote
from hashlib import sha256, sha1
from itertools import permutations


def relative_href(path, directory):
    '''
    Purpose
    -------
    Encode a filesystem-relative path for use in an HTML link.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    directory: str or Path
        Directory containing the generated HTML/link target.

    Outputs
    -------
    href: str
        URL-quoted relative path with POSIX separators; parent-directory
        components are retained.
    '''

    # Encode a relative filesystem path while preserving browser path separators.
    return quote(os.path.relpath(Path(path).absolute(), Path(directory).absolute()).replace(os.sep, '/'), safe='/')


def write_launch_bridge(directory):
    '''
    Purpose
    -------
    Write the local HTML bridge used to open a Bokeh destination.

    Inputs
    ------
    directory: str or Path
        Directory containing the generated HTML/link target.

    Outputs
    -------
    target: Path
        Path of bokeh-launch.html written in directory; the directory must
        exist.
    '''

    # Write the browser-side Bokeh launch bridge beside the generated figure views.
    target = Path(directory) / 'bokeh-launch.html'
    target.write_text('''<!doctype html><html><head><meta charset="utf-8"><title>Opening Bokeh</title></head>
<body><p id="status">Opening the combined Bokeh tool…</p><script>
(async () => {
  const target = new URLSearchParams(location.hash.slice(1)).get('target');
  let url;
  try {
    url = new URL(target);
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:' ||
        url.pathname !== '/integrated_komega_bokeh_app') throw Error('Invalid local launch URL');
  } catch (error) { document.getElementById('status').textContent = error.message; return; }
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url.origin + '/health', {cache:'no-store', signal:AbortSignal.timeout(2000)});
      const state = await response.json();
      if (state.service === 'morales-komega') { location.replace(url.href); return; }
    } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  document.getElementById('status').textContent = 'The local Bokeh service is unavailable. No dataset was substituted.';
})();
</script></body></html>''', encoding='utf-8')
    return target


def launch_href(url, directory):
    '''
    Purpose
    -------
    Write a launch bridge and encode a Bokeh URL into its fragment.

    Inputs
    ------
    url: str
        Bokeh destination URL encoded into the launch-bridge fragment.

    directory: str or Path
        Directory containing the generated HTML/link target.

    Outputs
    -------
    href: str
        Relative bridge filename with a percent-encoded target URL; writes the
        bridge as a side effect.
    '''

    # Ensure the bridge exists before encoding the destination URL into its fragment.
    bridge = write_launch_bridge(directory)
    return bridge.name + '#target=' + quote(url, safe='')


def write_figure_page(image_path, *, output_path=None, label=None, workspace=None, komega=False):
    '''
    Purpose
    -------
    Publish an individual image page with optional Bokeh launch context.

    Inputs
    ------
    image_path: str or Path
        Source PNG/JPEG figure file.

    output_path: str or Path or None
        HTML destination; None uses the source image basename with an .html
        suffix.

    label: str or None
        Page title/alt label; None or empty text uses the image stem.

    workspace: dict or None
        Optional launch context whose url identifies the Bokeh workspace.

    komega: bool
        Include the unavailable-launch explanation when no workspace is
        supplied.

    Outputs
    -------
    output_path: Path
        Resolved HTML path written after creating parent directories; the source
        image is linked without modification.
    '''

    # Resolve source/destination paths and create the page directory.
    image_path = Path(image_path).absolute()
    output_path = Path(output_path or image_path.with_suffix('.html')).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    label = label or image_path.stem
    nav = ''
    # Use exact numerical launch context when a Bokeh workspace is available.
    if workspace:
        href = launch_href(workspace['url'], output_path.parent)
        nav = f'<nav><a href="{escape(href, quote=True)}">Open in Bokeh</a></nav>'
    # Disclose unavailable numerical context for historical image-only komega figures.
    elif komega:
        nav = ('<nav><a aria-disabled="true">Open in Bokeh</a>'
               '<span>This historical figure has no exact numerical launch context.</span></nav>')
    # Publish the escaped image/title markup and optional launch navigation.
    output_path.write_text(f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(label)}</title>
<style>body{{margin:0;background:white;font-family:system-ui}}nav{{padding:12px;display:flex;gap:12px;align-items:center}}
nav a{{padding:8px 14px;border:1px solid #777;border-radius:4px;color:#111;text-decoration:none}}
nav a[aria-disabled]{{color:#777}}img{{display:block}}</style></head><body>{nav}
<img src="{relative_href(image_path, output_path.parent)}" alt="{escape(label, quote=True)}"></body></html>''', encoding='utf-8')
    return output_path


IMAGE_EXTENSIONS = (".jpeg", ".jpg", ".png")

COMPARISON_VIEWERS = {
    "field_strength_comparison": {
        "title": "Field Strength Comparison",
        "output_name": "field_strength_comparison.html",
    },
    "field_orientation_comparison": {
        "title": "Field Orientation Comparison",
        "output_name": "field_orientation_comparison.html",
    },
    "gaussian_filter_comparison": {
        "title": "Gaussian Filter Comparison",
        "output_name": "gaussian_filter_comparison.html",
    },
}

FULL_RESOLUTION_VIEW_DIRNAME = "comparison_view"
DEFAULT_BOKEH_SERVER_URL = "http://127.0.0.1:5013"

KOMEGA_COMPARISON_ROW_LABELS = (
    "Observed/Simulation k–ω Diagram",
    "3D MAG Wave k–ω Diagram",
    "Alfvén Mode k–ω Diagram",
    "Slow Magnetoacoustic Mode k–ω Diagram",
    "Fast Magnetoacoustic Mode k–ω Diagram",
    "Bunte 1993 k–ω Diagram",
    "MT1982 k–ω Diagram",
    "MT1981 k–ω Diagram",
)

PANEL_ROWS = (
    ("komega", "k-omega diagram"),
    ("xc", "cross-correlation"),
    ("phase_diff", "phase difference"),
)

FIELD_STRENGTH_CASE_RE = re.compile(r"(z0|hx|vx)_((?:\d+(?:_\d+)?g)(?:_\d+(?:_\d+)?g)*)")
FIELD_ORIENTATION_CASE_RE = re.compile(r"([hv])(\d+(?:_\d+)?g)")
PROCESSING_MARKERS = (
    "_magnetogram_gaussian_filtered_",
    "_gaussian_magnetogram_filtered_",
    "_gaussian_filtered_",
    "_unfiltered",
)
XCORR_DIRECTIONAL_GEOMETRIES = {
    "east": "East Wedge",
    "west": "West Wedge",
    "north": "North Wedge",
    "south": "South Wedge",
}
_OUTPUT_PATHS_MODULE = None


def _load_output_paths_module():
    '''
    Purpose
    -------
    Load the shared output-path helper without relying on sys.path state.

    Inputs
    ------
    None

    Outputs
    -------
    module: module or None
        Cached output_paths module loaded from a discovered sibling/project
        path, or None when no loadable candidate exists.
    '''

    # Reuse an already loaded helper before probing sibling/project locations.
    global _OUTPUT_PATHS_MODULE
    if _OUTPUT_PATHS_MODULE is not None:
        return _OUTPUT_PATHS_MODULE

    # Search known filesystem locations without relying on the caller's sys.path.
    candidates = []
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().with_name("output_paths.py"))
    candidates.extend([
        Path("output_paths.py"),
        Path("Code/Time-Distance/output_paths.py"),
    ])
    module_path = next((candidate.expanduser().resolve() for candidate in candidates if candidate.expanduser().exists()), None)
    if module_path is None:
        return None

    # Execute the discovered helper once and cache the module object.
    spec = importlib.util.spec_from_file_location("comparison_gallery_output_paths", module_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _OUTPUT_PATHS_MODULE = module
    return module


@dataclass(frozen=True)
class ComparisonPlot:
    '''
    Purpose
    -------
    Metadata for one discovered comparison plot.

    Inputs
    ------
    comparison_type: str
        Supported comparison kind.

    path: Path
        Source comparison image path.

    relative_src: str
        Encoded source path relative to its figure discovery root.

    h1_km: float or None
        First physical height in km, or None for observational data.

    h2_km: float or None
        Second physical height in km, or None for observational data.

    width: int or None
        Source image width in pixels when readable.

    height: int or None
        Source image height in pixels when readable.

    xcorr_geometry: str
        Annulus or directional wedge identifier; defaults to annulus.

    Outputs
    -------
    instance: ComparisonPlot
        Frozen metadata record for one discovered comparison image.
    '''

    # Retain source identity, physical heights, pixel dimensions, and geometry together.
    comparison_type: str
    path: Path
    relative_src: str
    h1_km: float | None
    h2_km: float | None
    width: int | None
    height: int | None
    xcorr_geometry: str = "annulus"

    @property
    def height_pair(self) -> tuple[float, float]:
        '''
        Purpose
        -------
        Return the stored physical heights of this comparison.

        Inputs
        ------
        None

        Outputs
        -------
        pair: tuple
            h1_km and h2_km, retaining None values for observational datasets.
        '''

        # Retain unavailable height sentinels when exposing the pair.
        return (self.h1_km, self.h2_km)

    @property
    def geometry_label(self) -> str:
        '''
        Purpose
        -------
        Return the human-readable directional-wedge label.

        Inputs
        ------
        None

        Outputs
        -------
        label: str
            Configured wedge title, or an empty string for annular/unrecognized
            geometry.
        '''

        # Annular geometry has no extra wedge label.
        return XCORR_DIRECTIONAL_GEOMETRIES.get(self.xcorr_geometry, "")


@dataclass(frozen=True)
class ComparisonPlotNameParts:
    '''
    Purpose
    -------
    Parsed fields encoded in a comparison plot filename.

    Inputs
    ------
    comparison_type: str
        Encoded comparison kind.

    observable: str
        Observable filename token.

    h1_token: str
        First underscore-decimal height token in km.

    h2_token: str
        Second underscore-decimal height token in km.

    tail: str
        Remaining field-case and processing filename suffix.

    Outputs
    -------
    instance: ComparisonPlotNameParts
        Frozen parsed filename fields used to locate corresponding source
        products.
    '''

    # Keep the original height tokens for deterministic source-basename reconstruction.
    comparison_type: str
    observable: str
    h1_token: str
    h2_token: str
    tail: str


def format_height_km(value: float) -> str:
    '''
    Purpose
    -------
    Format a height value for compact, deterministic labels.

    Inputs
    ------
    value: float
        Finite height in km, formatted without unnecessary decimal places.

    Outputs
    -------
    text: str
        Integer text when within 1e-9 of an integer; otherwise compact
        general-format numeric text.
    '''

    # Avoid decimal suffixes for heights numerically equal to integers.
    if abs(value - round(value)) < 1.0e-9:
        return str(int(round(value)))

    return f"{value:g}"


def format_height_pair(height_pair: tuple[float, float]) -> str:
    '''
    Purpose
    -------
    Return a human-readable height-pair label.

    Inputs
    ------
    height_pair: tuple
        First and second heights in km; None entries represent observational
        data.

    Outputs
    -------
    label: str
        Ordered height-pair label in km, or Observational datasets when either
        height is None.
    '''

    # Use a dataset label when physical height values are not encoded.
    if any(value is None for value in height_pair):
        return 'Observational datasets'

    return f"{format_height_km(height_pair[0])}-{format_height_km(height_pair[1])} km"


def _parse_height_token(token: str) -> float:
    '''
    Purpose
    -------
    Decode an underscore-decimal height filename token.

    Inputs
    ------
    token: str
        Height filename token using an underscore as the decimal separator.

    Outputs
    -------
    height: float
        Decoded height in km; malformed tokens raise ValueError.
    '''

    # Restore the decimal separator from the filename-safe height token.
    return float(token.replace("_", "."))


def _height_sort_key(height_pair: tuple[float, float]) -> tuple[float, float]:
    '''
    Purpose
    -------
    Sort physical height pairs before unavailable observational heights.

    Inputs
    ------
    height_pair: tuple
        First and second heights in km; None entries represent observational
        data.

    Outputs
    -------
    key: tuple
        Floating-point heights with None replaced by positive infinity.
    '''

    # Place missing observational heights after finite simulation heights.
    return tuple(float('inf') if value is None else float(value) for value in height_pair)


def _comparison_filename_pattern(comparison_type: str) -> re.Pattern[str]:
    '''
    Purpose
    -------
    Compile the observable and height-prefix pattern for one comparison kind.

    Inputs
    ------
    comparison_type: str
        field_strength_comparison, field_orientation_comparison, or
        gaussian_filter_comparison.

    Outputs
    -------
    pattern: re.Pattern
        Anchored named-group pattern for observable, h1, and h2 filename fields.
    '''

    # Match only the requested comparison prefix and its encoded observable/heights.
    return re.compile(
        rf"^{re.escape(comparison_type)}_"
        r"(?P<observable>[a-zA-Z0-9]+)_"
        r"(?P<h1>\d+(?:_\d+)?)km_"
        r"(?P<h2>\d+(?:_\d+)?)km_"
    )


def read_image_size(image_path: Path) -> tuple[int, int] | tuple[None, None]:
    '''
    Purpose
    -------
    Read PNG or JPEG dimensions without importing image-processing packages.

    Inputs
    ------
    image_path: str or Path
        Source PNG/JPEG figure file.

    Outputs
    -------
    width, height: tuple
        Image dimensions in pixels; (None, None) for unsupported or unreadable headers.
        Malformed binary structures can raise struct.error.
    '''

    # Read only enough binary structure to recover PNG/JPEG dimensions.
    image_path = Path(image_path)
    try:
        with image_path.open("rb") as handle:
            header = handle.read(24)
            # Decode PNG IHDR dimensions directly from the fixed header.
            if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR":
                width, height = struct.unpack(">II", header[16:24])
                return int(width), int(height)

            if header[:2] != b"\xff\xd8":
                return None, None

            # Scan JPEG markers until a supported start-of-frame segment supplies
            # dimensions.
            handle.seek(2)
            while True:
                marker_prefix = handle.read(1)
                if marker_prefix == b"":
                    return None, None
                if marker_prefix != b"\xff":
                    continue

                marker = handle.read(1)
                while marker == b"\xff":
                    marker = handle.read(1)
                if marker == b"":
                    return None, None

                marker_code = marker[0]
                if marker_code in (0xD8, 0xD9):
                    continue

                segment_length_bytes = handle.read(2)
                if len(segment_length_bytes) != 2:
                    return None, None
                segment_length = struct.unpack(">H", segment_length_bytes)[0]
                if segment_length < 2:
                    return None, None

                # Recognize the JPEG frame-header variants carrying image height and
                # width.
                if marker_code in {
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                }:
                    segment = handle.read(segment_length - 2)
                    if len(segment) < 5:
                        return None, None
                    height, width = struct.unpack(">HH", segment[1:5])
                    return int(width), int(height)

                handle.seek(segment_length - 2, 1)
    # Report unreadable files through the same missing-dimensions sentinel.
    except OSError:
        return None, None


def _parse_comparison_plot_name(plot: ComparisonPlot) -> ComparisonPlotNameParts | None:
    '''
    Purpose
    -------
    Decode comparison kind, observable, height tokens, and processing tail.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    Outputs
    -------
    parts: ComparisonPlotNameParts or None
        Parsed supported filename, or None when it does not match the encoded
        comparison convention.
    '''

    # Require a supported comparison kind followed by observable, heights, and a tail.
    match = re.match(
        rf"^(?P<comparison_type>{'|'.join(re.escape(name) for name in COMPARISON_VIEWERS)})_"
        r"(?P<observable>[a-zA-Z0-9]+)_"
        r"(?P<h1>\d+(?:_\d+)?)km_"
        r"(?P<h2>\d+(?:_\d+)?)km_"
        r"(?P<tail>.+)$",
        plot.path.stem,
    )
    if match is None:
        return None

    return ComparisonPlotNameParts(
        comparison_type=match.group("comparison_type"),
        observable=match.group("observable"),
        h1_token=match.group("h1"),
        h2_token=match.group("h2"),
        tail=match.group("tail"),
    )


def _extract_xcorr_geometry_from_tail(tail: str) -> str:
    '''
    Purpose
    -------
    Resolve a directional geometry from the final filename token.

    Inputs
    ------
    tail: str
        Case/processing suffix of a comparison image basename.

    Outputs
    -------
    geometry: str
        east, west, north, south, or annulus when no directional suffix is
        recognized.
    '''

    # Interpret only the final suffix as a directional-wedge selection.
    tail = str(tail).strip("_").lower()
    if tail == "":
        return "annulus"

    last_token = tail.rsplit("_", 1)[-1]
    if last_token in XCORR_DIRECTIONAL_GEOMETRIES:
        return last_token

    return "annulus"


def _strip_xcorr_geometry_suffix(value: str) -> str:
    '''
    Purpose
    -------
    Remove a recognized directional-wedge suffix from a filename token.

    Inputs
    ------
    value: str
        Filename/processing token whose directional suffix may be removed.

    Outputs
    -------
    stem: str
        Underscore-trimmed input with the final directional geometry removed
        when present.
    '''

    # Strip a recognized directional suffix without altering the processing token.
    value = str(value).strip("_")
    geometry = _extract_xcorr_geometry_from_tail(value)
    if geometry == "annulus":
        return value

    suffix = f"_{geometry}"
    return value[: -len(suffix)] if value.lower().endswith(suffix) else value


def _format_plot_height_label(plot: ComparisonPlot) -> str:
    '''
    Purpose
    -------
    Combine a height-pair label with an optional directional-wedge title.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    Outputs
    -------
    label: str
        Height label, followed by the wedge label when one exists.
    '''

    # Append the directional geometry only when the plot has a wedge label.
    height_label = format_height_pair(plot.height_pair)
    if plot.geometry_label == "":
        return height_label

    return f"{height_label} - {plot.geometry_label}"


def _split_case_and_processing_tail(tail: str) -> tuple[str, str]:
    '''
    Purpose
    -------
    Split a filename tail at its earliest recognized processing marker.

    Inputs
    ------
    tail: str
        Case/processing suffix of a comparison image basename.

    Outputs
    -------
    case_part, processing_slug: tuple of str
        Case portion and processing portion without the separator underscore;
        absent markers yield an empty processing slug.
    '''

    # Find the earliest filter marker so case tokens remain intact.
    marker_positions = [
        (tail.find(marker), marker)
        for marker in PROCESSING_MARKERS
        if tail.find(marker) >= 0
    ]
    if len(marker_positions) == 0:
        return tail, ""

    marker_index, marker = min(marker_positions, key=lambda item: item[0])
    return tail[:marker_index], tail[marker_index + 1 :]


def _parse_field_strength_cases(case_part: str) -> list[str]:
    '''
    Purpose
    -------
    Expand grouped field-strength filename tokens into individual cases.

    Inputs
    ------
    case_part: str
        Filename portion encoding field strengths or orientations.

    Outputs
    -------
    cases: list of str
        Ordered case tokens such as hx_10g, preserving decimal underscores.
    '''

    # Expand each encoded field component into its listed strength cases.
    cases: list[str] = []
    for match in FIELD_STRENGTH_CASE_RE.finditer(case_part):
        component = match.group(1)
        strength_tokens = re.findall(r"\d+(?:_\d+)?g", match.group(2))
        cases.extend(f"{component}_{strength_token}" for strength_token in strength_tokens)

    return cases


def _parse_field_orientation_cases(case_part: str) -> list[str]:
    '''
    Purpose
    -------
    Expand horizontal/vertical filename tokens into simulation cases.

    Inputs
    ------
    case_part: str
        Filename portion encoding field strengths or orientations.

    Outputs
    -------
    cases: list of str
        Ordered hx_*g and vx_*g case identifiers.
    '''

    # Translate horizontal/vertical shorthand into the source case prefixes.
    component_by_orientation = {"h": "hx", "v": "vx"}
    return [
        f"{component_by_orientation[match.group(1)]}_{match.group(2)}"
        for match in FIELD_ORIENTATION_CASE_RE.finditer(case_part)
    ]


def _comparison_cases_and_processing(plot: ComparisonPlot) -> tuple[ComparisonPlotNameParts | None, list[str], str]:
    '''
    Purpose
    -------
    Decode field-comparison cases and their shared processing suffix.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    Outputs
    -------
    parts, cases, processing_slug: tuple
        Parsed fields and ordered cases; an unmatched filename yields (None, [],
        ""). Gaussian comparisons have no cases from this helper.
    '''

    # Decode the filename before selecting the comparison-specific case parser.
    parts = _parse_comparison_plot_name(plot)
    if parts is None:
        return None, [], ""

    if parts.comparison_type == "field_strength_comparison":
        case_part, processing_slug = _split_case_and_processing_tail(parts.tail)
        return parts, _parse_field_strength_cases(case_part), processing_slug

    if parts.comparison_type == "field_orientation_comparison":
        case_part, processing_slug = _split_case_and_processing_tail(parts.tail)
        return parts, _parse_field_orientation_cases(case_part), processing_slug

    return parts, [], ""


def _quoted_parent_image_src(path: Path, figure_dir: Path | None = None) -> str:
    '''
    Purpose
    -------
    Build an encoded image URL relative to a sibling support directory.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    figure_dir: Path or None
        Source-image root; None uses only the image basename in a
        parent-relative URL.

    Outputs
    -------
    src: str
        Parent-relative source URL; outside-root paths fall back to the image
        filename.
    '''

    # Prefer source-root-relative identity while retaining the sibling support-page
    # layout.
    path = Path(path).expanduser().absolute()
    if figure_dir is None:
        return f"../{quote(path.name)}"

    figure_dir = Path(figure_dir).expanduser().resolve()
    try:
        relative_path = path.relative_to(figure_dir)
    except ValueError:
        relative_path = Path(path.name)

    return quote(f"../{relative_path.as_posix()}")


def _relative_image_src(path: Path, document_dir: Path) -> str:
    '''
    Purpose
    -------
    Build an encoded source URL relative to the generated document directory.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    document_dir: str or Path or None
        Directory against which browser-relative source and view URLs are
        calculated.

    Outputs
    -------
    src: str
        URL-quoted POSIX relative image path.
    '''

    # Calculate a browser URL from the actual document directory.
    relative_path = Path(os.path.relpath(
        Path(path).expanduser().absolute(),
        start=Path(document_dir).expanduser().resolve(),
    ))
    return quote(relative_path.as_posix())


def _build_image_stem_index(figure_dir: Path) -> dict[str, list[Path]]:
    '''
    Purpose
    -------
    Index source images under current and retained historical basenames.

    Inputs
    ------
    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    index: dict
        Stem-to-Path lists from deterministic recursive discovery, excluding
        generated view and delta_z trees; nonexistent roots yield {}.
    '''

    # Build a deterministic source index while excluding generated view trees.
    figure_dir = Path(figure_dir).expanduser().resolve()
    index: dict[str, list[Path]] = {}
    if not figure_dir.exists():
        return index

    # Register current, run-suffix-free, and retained migration basenames for each
    # asset.
    for path in sorted(figure_dir.rglob("*"), key=lambda candidate: candidate.relative_to(figure_dir).as_posix()):
        if (
            path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and FULL_RESOLUTION_VIEW_DIRNAME not in path.relative_to(figure_dir).parts
        ):
            if any(part.startswith('delta_z_') for part in path.relative_to(figure_dir).parts):
                continue
            manager = _load_output_paths_module()
            stems = {path.stem, manager.strip_run_suffix(path.stem)}
            metadata = manager.read_metadata(path)
            if metadata and metadata.get('extra', {}).get('migration_source'):
                original = Path(metadata['extra']['migration_source']).stem
                stems.update((original, _clean_source_image_stem(original)))
            for stem in stems:
                index.setdefault(stem, []).append(path)

    return index


def _clean_source_image_stem(stem: str) -> str:
    '''
    Purpose
    -------
    Normalize a historical image stem using the shared output-name cleaner.

    Inputs
    ------
    stem: str
        Image basename without its extension.

    Outputs
    -------
    stem: str
        Cleaned stem, or the original when no cleaner is available.
    '''

    # Use the shared migration-aware filename cleaner when it is available.
    output_paths = _load_output_paths_module()
    if output_paths is None or not hasattr(output_paths, "clean_output_filename"):
        return stem

    return Path(output_paths.clean_output_filename(f"{stem}.jpeg")).stem


def _product_directory_for_panel(panel_kind: str) -> str:
    '''
    Purpose
    -------
    Map a panel kind to the shared product-output directory.

    Inputs
    ------
    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    Outputs
    -------
    directory: str
        Canonical/fallback product directory name, or empty text for unknown
        kinds.
    '''

    # Map subplot kinds through canonical output products with legacy folder fallbacks.
    product_by_kind = {
        "komega": "komega_diagram",
        "xc": "time_distance",
        "phase_diff": "phase_difference",
    }
    product = product_by_kind.get(panel_kind, "")
    output_paths = _load_output_paths_module()
    if product == "" or output_paths is None or not hasattr(output_paths, "product_directory"):
        return {"komega": "komega", "xc": "xcorr", "phase_diff": "phase"}.get(panel_kind, "")

    return output_paths.product_directory(product)


def _candidate_source_image_stems(source_stems: str | Iterable[str], panel_kind: str) -> list[str]:
    '''
    Purpose
    -------
    Build distinct legacy and cleaned basenames for a requested panel.

    Inputs
    ------
    source_stems: str or iterable of str
        Candidate source basenames before the product suffix is appended.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    Outputs
    -------
    candidates: list of str
        Ordered raw/cleaned stems with the panel-specific product suffix.
    '''

    # Normalize a single stem into the ordered candidate collection.
    if isinstance(source_stems, str):
        source_stems = [source_stems]

    suffixes_by_kind = {
        "komega": ("_komega",),
        "xc": ("_xc",),
        "phase_diff": ("_phase_diff",),
    }

    # Append product suffixes and retain distinct raw/cleaned source names.
    candidates: list[str] = []
    for source_stem in source_stems:
        for suffix in suffixes_by_kind.get(panel_kind, ()):
            raw_stem = f"{source_stem}{suffix}"
            for candidate in (raw_stem, _clean_source_image_stem(raw_stem)):
                if candidate not in candidates:
                    candidates.append(candidate)

    return candidates


def _find_image_by_stem(
    figure_dir: Path,
    stem: str,
    source_index: dict[str, list[Path]] | None = None,
    panel_kind: str = "",
) -> Path | None:
    '''
    Purpose
    -------
    Resolve an indexed or directly named image matching the requested product.

    Inputs
    ------
    figure_dir: Path
        Root for direct fallback basename lookup.

    stem: str
        Image basename without its extension.

    source_index: dict or None
        Optional mapping from image stems to candidate source Paths.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    Outputs
    -------
    path: Path or None
        Best ranked indexed candidate, first matching direct extension, or None
        when absent.
    '''

    # Rank indexed candidates only after filtering by the requested product.
    if source_index is not None and stem in source_index:
        candidates = [
            candidate
            for candidate in source_index[stem]
            if _candidate_matches_panel(candidate, panel_kind)
        ]
        if len(candidates) == 0:
            return None
        return sorted(candidates, key=lambda candidate: _candidate_rank(candidate, panel_kind, stem))[0]

    # Fall back to supported direct file extensions when no indexed stem resolves.
    for extension in IMAGE_EXTENSIONS:
        candidate = Path(figure_dir) / f"{stem}{extension}"
        if candidate.exists() and _candidate_matches_panel(candidate, panel_kind):
            return candidate
    return None


def _candidate_matches_panel(path: Path, panel_kind: str) -> bool:
    '''
    Purpose
    -------
    Exclude comparison/validation images and check the expected product suffix.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    Outputs
    -------
    matches: bool
        Whether the candidate is eligible for the requested panel kind.
    '''

    # Exclude comparison and orientation-validation images before checking product
    # suffixes.
    stem = _load_output_paths_module().strip_run_suffix(path.stem.lower())
    if "comparison_" in stem or stem.endswith("_comparison"):
        return False
    if "magnetic_orientation_validation" in stem or "orientation_validation" in stem:
        return False
    if panel_kind == "":
        return True
    if panel_kind == "komega":
        return stem.endswith("_komega")
    if panel_kind == "xc":
        return stem.endswith("_xc")
    if panel_kind == "phase_diff":
        return stem.endswith("_phase_diff")

    return True


def _candidate_rank(path: Path, panel_kind: str, requested_stem: str) -> tuple[int, str]:
    '''
    Purpose
    -------
    Rank source candidates by product folder, exact basename, and extension.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    requested_stem: str
        Exact requested source basename used for candidate ranking.

    Outputs
    -------
    rank: tuple
        Numeric preference score and POSIX path for deterministic sorting;
        smaller values rank first.
    '''

    # Prefer canonical product folders, exact stems, then JPEG assets deterministically.
    parts = [part.lower() for part in path.parts]
    product_dir = _product_directory_for_panel(panel_kind)
    score = 0
    if product_dir != "" and product_dir in parts:
        score -= 20
    if path.stem == requested_stem:
        score -= 10
    if path.suffix.lower() == ".jpeg":
        score -= 1

    return score, path.as_posix()


def _find_source_panel_image(
    figure_dir: Path,
    source_stems: str | Iterable[str],
    panel_kind: str,
    source_index: dict[str, list[Path]] | None = None,
) -> Path | None:
    '''
    Purpose
    -------
    Resolve a source panel using filename candidates and processing evidence.

    Inputs
    ------
    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    source_stems: str or iterable of str
        Candidate source basenames before the product suffix is appended.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    source_index: dict or None
        Optional mapping from image stems to candidate source Paths.

    Outputs
    -------
    path: Path or None
        Source image whose metadata matches when available; unresolved ambiguity
        returns None so publication can use the exact comparison crop.
    '''

    # Reuse the source index and extract requested Gaussian parameters for provenance
    # checks.
    source_stems = [source_stems] if isinstance(source_stems, str) else list(source_stems)
    if source_index is None:
        source_index = _build_image_stem_index(figure_dir)
    # A cleaned basename can occur in many processing directories. Its lexical
    # first match is not evidence that it belongs to this subplot's filter.
    request = source_stems[0] if source_stems else ''
    gaussian = re.search(r'gauss_ck_(\d+(?:_\d+)?)_wk_(\d+(?:_\d+)?)_cf_(\d+(?:_\d+)?)_wf_(\d+(?:_\d+)?)', request)
    wanted = ([float(value.replace('_', '.')) for value in gaussian.groups()]
              if gaussian else None)
    def compatible(candidate):
        '''
        Purpose
        -------
        Check candidate filter identity against the enclosing subplot request.

        Inputs
        ------
        candidate: Path
            Candidate source image checked against the requested processing
            metadata.

        Outputs
        -------
        matches: bool or None
            True/False when metadata or a parameter file resolves compatibility, or
            None when evidence is unavailable/inapplicable.
        '''

        # Check structured provenance first, then retained filter_parameters metadata.
        manager = _load_output_paths_module()
        record = manager.read_metadata(candidate)
        if record:
            filtering = record['identity']['filtering']
            sequence = filtering.get('filter_sequence', []) if filtering.get('enabled') else []
            if request.endswith('_unfiltered'): return not sequence
            if wanted is not None:
                found=[filtering.get('gaussian', {}).get(key) for key in ('central_k','width_k','central_f','width_f')]
                return found==wanted and ('magnetogram' in sequence)==('magnetogram' in request)
            return None
        # Use the nearest retained parameter record only when structured metadata is
        # absent.
        parameter_file = next((parent / 'filter_parameters.txt' for parent in candidate.parents
                               if (parent / 'filter_parameters.txt').is_file()), None)
        if parameter_file is None:
            return None
        fields = dict(line.split(': ', 1) for line in parameter_file.read_text().splitlines()
                      if ': ' in line)
        sequence = fields.get('filtering.filter_sequence', '')
        if request.endswith('_unfiltered'):
            return sequence == '[]'
        if wanted is not None:
            try:
                found = [float(fields['filtering.gaussian.' + key])
                         for key in ('central_k', 'width_k', 'central_f', 'width_f')]
            except (ValueError, KeyError):
                return False
            return found == wanted and ('magnetogram' in sequence) == ('magnetogram' in request)
        return None
    # Prefer verified processing matches and reject ambiguous or explicitly incompatible
    # candidates.
    for source_stem in _candidate_source_image_stems(source_stems, panel_kind):
        if source_index is not None:
            candidates = [path for path in source_index.get(source_stem, [])
                          if _candidate_matches_panel(path, panel_kind)]
            verified = [path for path in candidates if compatible(path) is True]
            if verified:
                return min(verified, key=lambda path: _candidate_rank(path, panel_kind, source_stem))
            if len(candidates) > 1 or (candidates and compatible(candidates[0]) is False):
                continue  # The writer will use the exact megaplot crop.
        source = _find_image_by_stem(
            figure_dir,
            source_stem,
            source_index=source_index,
            panel_kind=panel_kind,
        )
        if source is not None:
            return source

    return None


def _filter_slug_from_processing(processing_slug: str) -> str:
    '''
    Purpose
    -------
    Remove the filter-sequence prefix and directional suffix.

    Inputs
    ------
    processing_slug: str
        Filter/processing token, optionally ending with a directional geometry.

    Outputs
    -------
    slug: str
        Bare filter-parameter token or the unfiltered token.
    '''

    # Remove directional geometry before separating the filter-sequence prefix.
    processing_slug = _strip_xcorr_geometry_suffix(processing_slug)
    for prefix in (
        "magnetogram_gaussian_filtered_",
        "gaussian_magnetogram_filtered_",
        "gaussian_filtered_",
    ):
        if processing_slug.startswith(prefix):
            return processing_slug[len(prefix) :]
    return processing_slug


def _find_gaussian_filter_image(
    figure_dir: Path,
    case_prefix: str,
    parts: ComparisonPlotNameParts,
    processing_slug: str,
) -> Path | None:
    '''
    Purpose
    -------
    Locate a Gaussian transfer image matching a case and parameter slug.

    Inputs
    ------
    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    case_prefix: str
        Simulation case token such as z0_0g or hx_10g.

    parts: ComparisonPlotNameParts
        Parsed comparison filename fields.

    processing_slug: str
        Filter/processing token, optionally ending with a directional geometry.

    Outputs
    -------
    path: Path or None
        First sorted matching image, or None for unfiltered/absent assets.
    '''

    # Skip unfiltered requests before searching case/observable/height-specific assets.
    filter_slug = _filter_slug_from_processing(processing_slug)
    if filter_slug == "" or filter_slug == "unfiltered":
        return None

    xcorr_geometry = _extract_xcorr_geometry_from_tail(processing_slug)
    source_prefix = f"{case_prefix}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_"
    required_fragment = f"_gaussian_filter_{filter_slug}"
    # Require the same filter slug and any requested directional-wedge suffix.
    candidates = sorted(
        path
        for path in figure_dir.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and FULL_RESOLUTION_VIEW_DIRNAME not in path.relative_to(figure_dir).parts
            and path.stem.startswith(source_prefix)
            and required_fragment in path.stem
            and (
                xcorr_geometry == "annulus"
                or f"_{xcorr_geometry}_" in path.stem
                or path.stem.endswith(f"_{xcorr_geometry}")
            )
        )
    )

    return candidates[0] if len(candidates) > 0 else None


def _source_stem(case_prefix: str, parts: ComparisonPlotNameParts, processing_slug: str) -> str:
    '''
    Purpose
    -------
    Build one case/observable/height/processing source basename.

    Inputs
    ------
    case_prefix: str
        Simulation case token such as z0_0g or hx_10g.

    parts: ComparisonPlotNameParts
        Parsed comparison filename fields.

    processing_slug: str
        Filter/processing token, optionally ending with a directional geometry.

    Outputs
    -------
    stem: str
        Encoded source basename without the product suffix or extension.
    '''

    # Preserve encoded observable and height tokens when attaching the processing
    # suffix.
    base = f"{case_prefix}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km"
    return base if processing_slug == "" else f"{base}_{processing_slug}"


def _source_stems_for_panel(
    comparison_type: str,
    case_prefix: str,
    parts: ComparisonPlotNameParts,
    processing_slug: str,
    panel_kind: str,
) -> list[str]:
    '''
    Purpose
    -------
    Choose source basenames appropriate to the comparison and panel product.

    Inputs
    ------
    comparison_type: str
        field_strength_comparison, field_orientation_comparison, or
        gaussian_filter_comparison.

    case_prefix: str
        Simulation case token such as z0_0g or hx_10g.

    parts: ComparisonPlotNameParts
        Parsed comparison filename fields.

    processing_slug: str
        Filter/processing token, optionally ending with a directional geometry.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    Outputs
    -------
    stems: list of str
        Active processing stem for Gaussian/xcorr/phase panels; field-comparison
        komega panels prefer unfiltered basenames.
    '''

    # Use the active runtime stem for products whose processing must match the
    # comparison.
    active_stem = _source_stem(case_prefix, parts, processing_slug)
    if panel_kind != "komega":
        return [active_stem]
    if comparison_type == "gaussian_filter_comparison":
        return [active_stem]

    # Standard field comparison panels render the unfiltered k-omega product
    # while xcorr and phase panels render the active filtered runtime products.
    base_stem = _source_stem(case_prefix, parts, "")
    candidates = [f"{base_stem}_unfiltered", base_stem, active_stem]
    return list(dict.fromkeys(candidates))


def _relative_source_path(path: Path, figure_dir: Path) -> str:
    '''
    Purpose
    -------
    Represent source identity relative to the discovery root where possible.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    path_text: str
        POSIX root-relative path, or only the basename for an outside-root
        source.
    '''

    # Keep source identity relative to the discovery root when possible.
    path = Path(path).expanduser().absolute()
    figure_dir = Path(figure_dir).expanduser().resolve()
    try:
        return path.relative_to(figure_dir).as_posix()
    except ValueError:
        return path.name


def _source_target_for_path(
    path: Path | None,
    label: str,
    figure_dir: Path,
    expected: str = "",
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Package a source image with row-comparison and Bokeh sidecar context.

    Inputs
    ------
    path: str or Path
        Filesystem path converted to a relative browser link or inspected as a
        source asset.

    label: str
        Human-readable figure or navigation-target label.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    expected: str
        Expected source description retained for missing-link diagnostics.

    Outputs
    -------
    target: dict
        Link/source identity, alt text, missing status, expected description,
        and optional comparisonRows or bokeh launch links.
    '''

    # Represent an unresolved source explicitly rather than inventing a link.
    if path is None:
        return {
            "src": "",
            "sourcePath": "",
            "alt": label,
            "missing": True,
            "expected": expected,
        }

    # Package the source URL, absolute file identity, and accessible image label.
    target = {
        "src": _quoted_parent_image_src(path, figure_dir),
        "sourcePath": _relative_source_path(path, figure_dir),
        "sourceFile": str(path.expanduser().resolve()),
        "alt": label,
        "missing": False,
        "expected": expected,
    }
    # Attach validated comparison-row and Bokeh launch sidecars when present.
    comparison_rows = _load_komega_comparison_rows(path, figure_dir)
    if comparison_rows:
        target["comparisonRows"] = comparison_rows
    metadata_file = find_json_sidecar(path, '.bokeh.json')
    if metadata_file.is_file():
        target['bokeh'] = json.loads(metadata_file.read_text(encoding='utf-8'))['links']

    return target


def _komega_comparison_manifest_path(image_path: Path) -> Path:
    '''
    Purpose
    -------
    Locate the current or legacy comparison manifest beside a source image.

    Inputs
    ------
    image_path: str or Path
        Source PNG/JPEG figure file.

    Outputs
    -------
    path: Path
        First existing current/legacy manifest path, or the current destination
        when neither exists.
    '''

    # Prefer the managed JSON location while retaining legacy sibling-manifest
    # discovery.
    image_path = Path(image_path).expanduser().resolve()
    return next((p for p in (json_output_path(image_path.with_name(f"{image_path.stem}_dispersion_comparison.json")), image_path.with_name(f"{image_path.stem}_dispersion_comparison.json")) if p.is_file()), json_output_path(image_path.with_name(f"{image_path.stem}_dispersion_comparison.json")))


def _load_komega_comparison_rows(image_path: Path, figure_dir: Path) -> list[dict[str, Any]]:
    '''
    Purpose
    -------
    Load and validate the eight external image rows for one komega target.

    Inputs
    ------
    image_path: str or Path
        Source PNG/JPEG figure file.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    rows: list of dict
        Ordered observed-plus-seven-model row links and image dimensions.
        Missing/unreadable or wrong-order manifests and missing row assets yield an
        empty list.
    '''

    # Require a komega source and an existing comparison manifest.
    image_path = Path(image_path).expanduser().resolve()
    if not image_path.stem.lower().endswith("_komega"):
        return []
    manifest_path = _komega_comparison_manifest_path(image_path)
    if not manifest_path.exists():
        return []

    # Treat unreadable or malformed manifests as unavailable comparison rows.
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []

    # Require the exact observed-plus-seven-model order and excluded Souffrin row
    # policy.
    manifest_rows = manifest.get("rows", [])
    labels = tuple(str(row.get("label", "")) for row in manifest_rows)
    if labels != KOMEGA_COMPARISON_ROW_LABELS or bool(manifest.get("souffrin_included", False)):
        return []

    rows: list[dict[str, Any]] = []
    # Resolve every referenced image before publishing the complete row collection.
    for row_index, row in enumerate(manifest_rows):
        row_path = Path(str(row.get("path", "")))
        if not row_path.is_absolute():
            row_path = image_path.parent / row_path
        row_path = row_path.expanduser().resolve()
        if not row_path.exists() or row_path.suffix.lower() not in IMAGE_EXTENSIONS:
            return []
        width, height = read_image_size(row_path)
        rows.append(
            {
                "index": row_index + 1,
                "label": KOMEGA_COMPARISON_ROW_LABELS[row_index],
                "src": _quoted_parent_image_src(row_path, figure_dir),
                "sourcePath": _relative_source_path(row_path, figure_dir),
                "alt": KOMEGA_COMPARISON_ROW_LABELS[row_index],
                "width": width,
                "height": height,
            }
        )

    return rows


def _fallback_bands(size: int, expected_count: int) -> list[tuple[int, int]]:
    '''
    Purpose
    -------
    Divide an image axis into approximately equal inclusive panel bands.

    Inputs
    ------
    size: int
        Image-axis length in pixels.

    expected_count: int
        Requested number of panel bands or Gaussian-filter settings.

    Outputs
    -------
    bands: list of tuple
        Inclusive pixel-index intervals; invalid size/count yields [].
    '''

    # Reject empty dimensions before assigning evenly divided inclusive intervals.
    if size <= 0 or expected_count <= 0:
        return []

    bands: list[tuple[int, int]] = []
    for index in range(expected_count):
        start = int(round(size*index/expected_count))
        stop = int(round(size*(index + 1)/expected_count)) - 1
        bands.append((max(0, start), max(start, min(size - 1, stop))))
    return bands


def _expand_segments_to_count(
    segments: list[tuple[int, int]],
    expected_count: int,
) -> list[tuple[int, int]]:
    '''
    Purpose
    -------
    Subdivide the widest detected segments until the requested count is reached.

    Inputs
    ------
    segments: list of tuple
        Detected inclusive pixel-index intervals.

    expected_count: int
        Requested number of panel bands or Gaussian-filter settings.

    Outputs
    -------
    bands: list of tuple
        Ordered inclusive intervals, truncated to expected_count; empty segment
        input stays empty.
    '''

    # Preserve/truncate already sufficient intervals and leave empty detections empty.
    if expected_count <= 0 or len(segments) >= expected_count:
        return segments[:expected_count]
    if len(segments) == 0:
        return segments

    # Allocate all subdivisions before cutting. Recursive halving produced
    # uneven cells when seven abutting image columns formed one dark segment.
    widths = [stop-start+1 for start, stop in segments]
    counts = [1] * len(segments)
    while sum(counts) < expected_count:
        widest_index = max(range(len(segments)), key=lambda index: widths[index]/counts[index])
        counts[widest_index] += 1
    expanded = []
    for (widest_start, widest_stop), parts in zip(segments, counts):
        split_points = [
            int(round(widest_start + (widest_stop - widest_start + 1)*part/parts))
            for part in range(parts + 1)
        ]
        split_segments = [
            (split_points[part], max(split_points[part], split_points[part + 1] - 1))
            for part in range(parts)
        ]
        expanded.extend(split_segments)

    return expanded[:expected_count]


def _projection_segments(
    mask: Any,
    axis: int,
    expected_count: int,
    minimum_span: float,
    density_fraction: float = 0.02,
) -> list[tuple[int, int]]:
    '''
    Purpose
    -------
    Detect foreground panel intervals from a row or column projection.

    Inputs
    ------
    mask: np.ndarray
        Two-dimensional foreground-pixel mask.

    axis: int
        Zero detects column intervals by summing rows; any other value detects
        row intervals.

    expected_count: int
        Requested number of panel bands or Gaussian-filter settings.

    minimum_span: float
        Minimum accepted contiguous interval width, in pixels.

    density_fraction: float
        Minimum foreground density relative to the projection height/width.

    Outputs
    -------
    segments: list of tuple
        Inclusive pixel bands after density/span filtering and subdivision; gaps
        of up to two absent indices remain within one segment.
    '''

    # Project foreground density along the requested image direction.
    import numpy as np

    if axis == 0:
        projection = mask.sum(axis=0)
        threshold = mask.shape[0]*density_fraction
    else:
        projection = mask.sum(axis=1)
        threshold = mask.shape[1]*density_fraction

    # Keep positions above the density threshold before joining nearby occupied samples.
    indices = np.where(projection > threshold)[0]
    if indices.size == 0:
        return []

    # Split at wider gaps and reject segments shorter than the minimum panel span.
    segments: list[tuple[int, int]] = []
    start = int(indices[0])
    previous = int(indices[0])
    for index_value in indices[1:]:
        index_value = int(index_value)
        if index_value > previous + 3:
            if previous - start + 1 >= minimum_span:
                segments.append((start, previous))
            start = index_value
        previous = index_value

    if previous - start + 1 >= minimum_span:
        segments.append((start, previous))

    return _expand_segments_to_count(segments, expected_count)


def _load_image_mask(image_path: Path) -> tuple[Any | None, int, int]:
    '''
    Purpose
    -------
    Read a foreground mask while retaining a dimension-only fallback.

    Inputs
    ------
    image_path: str or Path
        Source PNG/JPEG figure file.

    Outputs
    -------
    mask, width, height: tuple
        Boolean pixels with any RGB channel below 245, plus dimensions in
        pixels. Missing Pillow/NumPy or unreadable images yield mask=None with
        header-derived dimensions.
    '''

    # Use Pillow/NumPy when available, retaining a header-only dimension fallback.
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        width, height = read_image_size(image_path)
        return None, int(width or 0), int(height or 0)

    try:
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            array = np.asarray(rgb)
    except OSError:
        width, height = read_image_size(image_path)
        return None, int(width or 0), int(height or 0)

    # Mark pixels whose RGB content differs sufficiently from the white background.
    mask = (array < 245).any(axis=2)
    height, width = mask.shape
    return mask, int(width), int(height)


def _detect_panel_bands(
    image_path: Path,
    expected_columns: int,
    expected_rows: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], int, int, Any | None]:
    '''
    Purpose
    -------
    Infer panel rows and columns from the foreground image mask.

    Inputs
    ------
    image_path: str or Path
        Source PNG/JPEG figure file.

    expected_columns: int
        Expected number of image panel columns.

    expected_rows: int
        Expected number of image panel rows.

    Outputs
    -------
    x_bands, y_bands, width, height, mask: tuple
        Inclusive panel intervals, image dimensions, and optional foreground
        mask; missing projections use equal-width fallback bands.
    '''

    # Read the image foreground and reject unavailable dimensions.
    mask, width, height = _load_image_mask(image_path)
    if width <= 0 or height <= 0:
        return [], [], width, height, mask

    # Fall back to equally divided panel geometry without image-analysis dependencies.
    if mask is None:
        return (
            _fallback_bands(width, expected_columns),
            _fallback_bands(height, expected_rows),
            width,
            height,
            mask,
        )

    # Detect row bands before estimating columns from the first detected row.
    minimum_y_span = max(2.0, height/max(1, expected_rows*4))
    y_bands = _projection_segments(mask, axis=1, expected_count=expected_rows, minimum_span=minimum_y_span)
    if len(y_bands) == 0:
        y_bands = _fallback_bands(height, expected_rows)

    minimum_x_span = max(2.0, width/max(1, expected_columns*4))
    x_source = mask
    if len(y_bands) > 0:
        first_y0, first_y1 = y_bands[0]
        x_source = mask[first_y0:first_y1 + 1, :]

    x_bands = _projection_segments(x_source, axis=0, expected_count=expected_columns, minimum_span=minimum_x_span)
    if len(x_bands) == 0:
        x_bands = _fallback_bands(width, expected_columns)

    return x_bands, y_bands, width, height, mask


def _row_x_bands(
    mask: Any | None,
    y_band: tuple[int, int],
    image_width: int,
    expected_columns: int,
) -> list[tuple[int, int]]:
    '''
    Purpose
    -------
    Detect panel columns within one selected image row.

    Inputs
    ------
    mask: np.ndarray or None
        Two-dimensional foreground-pixel mask, shape (image_height,
        image_width).

    y_band: tuple of int
        Inclusive first/last row indices in image pixels.

    image_width: int
        Full source image width in pixels.

    expected_columns: int
        Expected number of image panel columns.

    Outputs
    -------
    bands: list of tuple
        Inclusive column intervals, with equal-width fallback when image
        data/projections are unavailable.
    '''

    # Use equal-width columns when no foreground mask is available.
    if mask is None:
        return _fallback_bands(image_width, expected_columns)

    # Restrict column detection to the selected row, allowing narrower single-panel
    # spans.
    minimum_x_span = max(2.0, image_width/max(1, expected_columns*4))
    if expected_columns == 1:
        minimum_x_span = max(2.0, image_width/20)
    y0, y1 = y_band
    row_mask = mask[y0:y1 + 1, :]
    row_bands = _projection_segments(
        row_mask,
        axis=0,
        expected_count=expected_columns,
        minimum_span=minimum_x_span,
    )
    return row_bands if len(row_bands) > 0 else _fallback_bands(image_width, expected_columns)


def _bounds_percent(
    x_band: tuple[int, int],
    y_band: tuple[int, int],
    image_width: int,
    image_height: int,
) -> dict[str, float]:
    '''
    Purpose
    -------
    Convert inclusive pixel bands into percentage browser bounds.

    Inputs
    ------
    x_band: tuple of int
        Inclusive first/last column indices in image pixels.

    y_band: tuple of int
        Inclusive first/last row indices in image pixels.

    image_width: int
        Full source image width in pixels.

    image_height: int
        Full source image height in pixels.

    Outputs
    -------
    bounds: dict
        left/top/width/height in percent; nonpositive dimensions produce zero
        for that axis.
    '''

    # Include both endpoint pixels when converting crop size into browser percentages.
    x0, x1 = x_band
    y0, y1 = y_band
    return {
        "left": 100.0*x0/image_width if image_width > 0 else 0.0,
        "top": 100.0*y0/image_height if image_height > 0 else 0.0,
        "width": 100.0*(x1 - x0 + 1)/image_width if image_width > 0 else 0.0,
        "height": 100.0*(y1 - y0 + 1)/image_height if image_height > 0 else 0.0,
    }


def _bounds_pixels(x_band: tuple[int, int], y_band: tuple[int, int]) -> dict[str, int]:
    '''
    Purpose
    -------
    Convert inclusive pixel bands into a pixel crop rectangle.

    Inputs
    ------
    x_band: tuple of int
        Inclusive first/last column indices in image pixels.

    y_band: tuple of int
        Inclusive first/last row indices in image pixels.

    Outputs
    -------
    bounds: dict
        Integer left/top/width/height suitable for extracting the full inclusive
        band.
    '''

    # Convert inclusive band endpoints into the pixel rectangle used for extraction.
    x0, x1 = x_band
    y0, y1 = y_band
    return {
        "left": int(x0),
        "top": int(y0),
        "width": int(x1 - x0 + 1),
        "height": int(y1 - y0 + 1),
    }


def _target_id(*parts: object) -> str:
    '''
    Purpose
    -------
    Normalize identifier fragments into a stable browser subplot key.

    Inputs
    ------
    *parts: object
        Positional identifier fragments, converted to text and joined.

    Outputs
    -------
    target_id: str
        Lowercase hyphenated identifier, or subplot when all fragments normalize
        away.
    '''

    # Normalize joined fragments into a deterministic browser-safe subplot identifier.
    raw = "-".join(str(part) for part in parts if str(part) != "")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw.lower()).strip("-")
    return safe or "subplot"


def _build_target(
    target_id: str,
    label: str,
    source: dict[str, Any],
    x_band: tuple[int, int],
    y_band: tuple[int, int],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Combine source identity and panel geometry into a navigation record.

    Inputs
    ------
    target_id: str
        Stable browser identifier for this subplot.

    label: str
        Human-readable figure or navigation-target label.

    source: dict
        Source-link metadata, optional crop/launch context, and missing-source
        status.

    x_band: tuple of int
        Inclusive first/last column indices in image pixels.

    y_band: tuple of int
        Inclusive first/last row indices in image pixels.

    image_width: int
        Full source image width in pixels.

    image_height: int
        Full source image height in pixels.

    Outputs
    -------
    target: dict
        Source/launch metadata, percentage and pixel bounds, crop status, and
        stable id/label.
    '''

    # Copy source metadata before adding panel identity and pixel/percentage geometry.
    source = dict(source)
    crop_bounds = _bounds_pixels(x_band, y_band)

    target = {
        "id": target_id,
        "label": label,
        "src": source.get("src", ""),
        "sourcePath": source.get("sourcePath", ""),
        "sourceFile": source.get("sourceFile", ""),
        "alt": source.get("alt", label),
        "crop": source.get("crop", None),
        "bounds": _bounds_percent(x_band, y_band, image_width, image_height),
        "pixelBounds": crop_bounds,
        "missing": bool(source.get("missing", source.get("src", "") == "")),
        "expected": source.get("expected", ""),
    }
    # Retain comparison-row and launch context alongside the panel link.
    if source.get("comparisonRows"):
        target["comparisonRows"] = list(source["comparisonRows"])
    if source.get('bokeh'):
        target['bokeh'] = source['bokeh']
    return target


def _expected_panel_description(source_stems: str | Iterable[str], panel_kind: str) -> str:
    '''
    Purpose
    -------
    Describe the filename candidates expected for a subplot source.

    Inputs
    ------
    source_stems: str or iterable of str
        Candidate source basenames before the product suffix is appended.

    panel_kind: str
        Requested komega, xc, phase_diff, or gaussian_filter panel kind.

    Outputs
    -------
    description: str
        Comma-separated candidate product stems for diagnostics.
    '''

    # Expose all candidate stems in missing-source diagnostics.
    candidates = _candidate_source_image_stems(source_stems, panel_kind)
    return ", ".join(candidates)


def _build_field_comparison_targets(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
) -> list[dict[str, Any]]:
    '''
    Purpose
    -------
    Map field-comparison panels and their optional filter row to source records.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    title: str
        Human-readable comparison/gallery title.

    height_label: str
        Formatted height-pair and optional geometry label.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    targets: list of dict
        Navigation targets for each field case/product and optional shared
        Gaussian filter; unparseable geometry yields [].
    '''

    # Decode field cases and require enough detected bands for the three product rows.
    parts, cases, processing_slug = _comparison_cases_and_processing(plot)
    if parts is None or len(cases) == 0:
        return []

    expected_rows = 4
    expected_columns = len(cases)
    x_bands, y_bands, width, height, mask = _detect_panel_bands(plot.path, expected_columns, expected_rows)
    if len(x_bands) < expected_columns or len(y_bands) < 3 or width <= 0 or height <= 0:
        return []

    figure_dir = Path(plot.path.parent if figure_dir is None else figure_dir).expanduser().resolve()
    source_index = _build_image_stem_index(figure_dir)
    targets: list[dict[str, Any]] = []

    # Build the product rows for every field case using the shared processing identity.
    for column_index, case_prefix in enumerate(cases):
        for row_index, (panel_kind, panel_label) in enumerate(PANEL_ROWS):
            source_stems = _source_stems_for_panel(plot.comparison_type, case_prefix, parts, processing_slug, panel_kind)
            source = _source_target_for_path(
                _find_source_panel_image(
                    figure_dir,
                    source_stems,
                    panel_kind,
                    source_index=source_index,
                ),
                f"{case_prefix} {panel_label}",
                figure_dir,
                expected=_expected_panel_description(source_stems, panel_kind),
            )
            targets.append(
                _build_target(
                    _target_id(case_prefix, panel_kind),
                    f"{case_prefix} {panel_label}",
                    source,
                    x_bands[column_index],
                    y_bands[row_index],
                    width,
                    height,
                )
            )

    # Attach the optional shared Gaussian filter panel beneath the case/product rows.
    if len(y_bands) >= 4:
        filter_x_bands = _row_x_bands(mask, y_bands[3], width, 1)
        if len(filter_x_bands) > 0:
            reference_case = cases[0]
            source = _source_target_for_path(
                _find_gaussian_filter_image(figure_dir, reference_case, parts, processing_slug),
                f"{title}: {height_label} Gaussian filter",
                figure_dir,
                expected=f"{reference_case}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_*gaussian_filter_{_filter_slug_from_processing(processing_slug)}",
            )
            targets.append(
                _build_target(
                    _target_id("gaussian-filter", reference_case),
                    f"{title}: {height_label} Gaussian filter",
                    source,
                    filter_x_bands[0],
                    y_bands[3],
                    width,
                    height,
                )
            )

    return targets


def _extract_gaussian_filter_count(parts: ComparisonPlotNameParts) -> int:
    '''
    Purpose
    -------
    Read the declared number of Gaussian filters from the filename tail.

    Inputs
    ------
    parts: ComparisonPlotNameParts
        Parsed comparison filename fields.

    Outputs
    -------
    count: int
        Declared filters_N count, or zero when absent.
    '''

    # Read the explicit filters_N count rather than inferring columns from file order.
    match = re.search(r"(?:^|_)filters_(\d+)(?:_|$)", parts.tail)
    return int(match.group(1)) if match is not None else 0


def _parse_gaussian_processing_slugs_from_tail(parts: ComparisonPlotNameParts) -> list[str]:
    '''
    Purpose
    -------
    Decode explicitly indexed Gaussian filter settings in filename order.

    Inputs
    ------
    parts: ComparisonPlotNameParts
        Parsed comparison filename fields.

    Outputs
    -------
    slugs: list of str
        Gaussian processing slugs sorted by their encoded fN index.
    '''

    # Decode indexed Gaussian settings and preserve the encoded filter-column order.
    matches = []
    for match in re.finditer(
        r"(?:^|_)f(?P<index>\d+)_"
        r"(?P<slug>gauss_ck_\d+(?:_\d+)?_wk_\d+(?:_\d+)?_cf_\d+(?:_\d+)?_wf_\d+(?:_\d+)?)"
        r"(?=_f\d+_|_|$)",
        parts.tail,
        flags=re.IGNORECASE,
    ):
        matches.append((int(match.group("index")), f"gaussian_filtered_{match.group('slug').lower()}"))

    return [slug for _, slug in sorted(matches)]


def _discover_gaussian_processing_slugs(
    figure_dir: Path,
    reference_case: str,
    parts: ComparisonPlotNameParts,
    expected_count: int,
) -> list[str]:
    '''
    Purpose
    -------
    Recover filter-column order from encoded settings and retained provenance.

    Inputs
    ------
    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    reference_case: str
        Simulation case used to discover the ordered Gaussian configurations.

    parts: ComparisonPlotNameParts
        Parsed comparison filename fields.

    expected_count: int
        Requested number of panel bands or Gaussian-filter settings.

    Outputs
    -------
    slugs: list of str
        At most expected_count slugs. Historical truncated names require
        digest-verified ordering; unresolved positions use empty placeholders.
    '''

    # Prefer complete explicit filter-column settings in the comparison filename.
    parsed_slugs = _parse_gaussian_processing_slugs_from_tail(parts)
    if len(parsed_slugs) >= expected_count:
        return parsed_slugs[:expected_count]

    source_prefix = f"{reference_case}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_"
    komega_suffix = "_komega"
    processing_slugs = []

    # Hierarchy migration shortened product basenames, but preserved the original
    # scientific filter metadata in each filter directory.
    roots = [figure_dir, figure_dir.parents[1] / 'Data' / 'Time-Distance']
    for root in roots:
        for parameter_file in root.glob('filter_*/filter_parameters.txt'):
            fields = dict(line.split(': ', 1) for line in parameter_file.read_text().splitlines()
                          if ': ' in line)
            if fields.get('filtering.gaussian.enabled') != 'true':
                continue
            try:
                numbers = [f'{float(fields["filtering.gaussian." + key]):g}'.replace('.', '_')
                           for key in ('central_k', 'width_k', 'central_f', 'width_f')]
            except (ValueError, KeyError):
                continue
            processing_slugs.append('gaussian_filtered_gauss_ck_{}_wk_{}_cf_{}_wf_{}'.format(*numbers))

    # Match discovered komega assets against the case, observable, heights, and
    # geometry.
    for path in sorted(figure_dir.rglob("*"), key=lambda candidate: candidate.relative_to(figure_dir).as_posix()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if FULL_RESOLUTION_VIEW_DIRNAME in path.relative_to(figure_dir).parts:
            continue
        if not _candidate_matches_panel(path, 'komega'):
            continue
        manager = _load_output_paths_module()
        record = manager.read_metadata(path)
        if record:
            if record.get('product') != 'komega_diagram':
                continue
            identity = record['identity']
            category = identity['category'].split('/')
            case = 'z0_0g' if category == ['z0'] else f'{category[0]}_{category[-1][1:].lower()}'
            heights = [float(token.replace('_', '.')) for token in (parts.h1_token, parts.h2_token)]
            geometry = _extract_xcorr_geometry_from_tail(parts.tail)
            if (case != reference_case or identity['observable'] != parts.observable
                    or identity['geometry']['heights_km'] != heights
                    or identity['processing'].get('xcorr_geometry', 'annulus') != geometry):
                continue
            filtering = identity['filtering']
            gaussian = filtering.get('gaussian', {})
            if not (filtering.get('enabled') and gaussian.get('enabled')
                    and 'gaussian' in filtering.get('filter_sequence', [])):
                continue
            # The gallery compares Gaussian settings, independently of magnetic masks.
            numbers = [f'{float(gaussian[key]):g}'.replace('.', '_')
                       for key in ('central_k', 'width_k', 'central_f', 'width_f')]
            processing_slug = 'gaussian_filtered_gauss_ck_{}_wk_{}_cf_{}_wf_{}'.format(*numbers)
        else:
            stem = manager.strip_run_suffix(path.stem)
            if not stem.startswith(source_prefix) or not stem.endswith(komega_suffix):
                continue
            processing_slug = stem[len(source_prefix) : -len(komega_suffix)]
        if processing_slug == "unfiltered":
            continue
        if processing_slug not in processing_slugs:
            processing_slugs.append(processing_slug)

    # Rank discovered settings by their location in the original comparison tail.
    filter_tail = parts.tail
    ranked: list[tuple[int, str]] = []
    unranked: list[str] = []
    for processing_slug in processing_slugs:
        filter_slug = _filter_slug_from_processing(processing_slug)
        position = filter_tail.find(filter_slug)
        if position >= 0:
            ranked.append((position, processing_slug))
        else:
            unranked.append(processing_slug)

    if len(ranked) == 0:
        discovered_slugs = processing_slugs[:expected_count]
    else:
        discovered_slugs = ([slug for _, slug in sorted(ranked)] + sorted(unranked))[:expected_count]

    combined_slugs = parsed_slugs + [slug for slug in discovered_slugs if slug not in parsed_slugs]

    # Historical filenames were truncated with a SHA-1 suffix. Sorting the
    # remaining source names guessed their column order and linked wrong filters.
    # Recover the order only when the original full filename's digest verifies it.
    digest_match = re.search(r'_([a-f0-9]{12})$', parts.tail)
    if digest_match and expected_count > len(parsed_slugs):
        prefix = f'{parts.comparison_type}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_filters_{expected_count}'
        remaining = sorted(set(processing_slugs) - set(parsed_slugs))
        suffixes = ['', 'gaussian_filtered', *sorted(set(processing_slugs))]
        for rest in permutations(remaining, expected_count - len(parsed_slugs)):
            ordered = parsed_slugs + list(rest)
            full = prefix + ''.join(f'_f{i}_{_filter_slug_from_processing(slug)}'
                                    for i, slug in enumerate(ordered, 1))
            for suffix in suffixes:
                candidate = full + ('_' + suffix if suffix else '')
                if sha1(candidate.encode()).hexdigest()[:12] == digest_match[1]:
                    return ordered
        # Unverified columns retain exact image crops rather than guessed products.
        return parsed_slugs + [''] * (expected_count - len(parsed_slugs))

    return combined_slugs[:expected_count]


def _build_gaussian_comparison_targets(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
) -> list[dict[str, Any]]:
    '''
    Purpose
    -------
    Map Gaussian-filter columns and case/product rows to their source records.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    title: str
        Human-readable comparison/gallery title.

    height_label: str
        Formatted height-pair and optional geometry label.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    targets: list of dict
        Filter-row and seven-case product targets, or [] for absent
        filename/geometry requirements.
    '''

    # Validate the Gaussian comparison filename and declared filter-column count.
    parts = _parse_comparison_plot_name(plot)
    if parts is None:
        return []

    case_prefixes = ["z0_0g", "hx_10g", "hx_50g", "hx_100g", "vx_10g", "vx_50g", "vx_100g"]
    filter_count = _extract_gaussian_filter_count(parts)
    if filter_count <= 0:
        return []

    # Require the filter row plus three product rows for each of the seven cases.
    expected_rows = 1 + len(case_prefixes)*len(PANEL_ROWS)
    x_bands, y_bands, width, height, _ = _detect_panel_bands(plot.path, filter_count, expected_rows)
    if len(x_bands) < filter_count or len(y_bands) < expected_rows or width <= 0 or height <= 0:
        return []

    figure_dir = Path(plot.path.parent if figure_dir is None else figure_dir).expanduser().resolve()
    source_index = _build_image_stem_index(figure_dir)
    processing_slugs = _discover_gaussian_processing_slugs(
        figure_dir,
        case_prefixes[0],
        parts,
        filter_count,
    )
    if len(processing_slugs) < filter_count:
        processing_slugs.extend([""]*(filter_count - len(processing_slugs)))
    processing_slugs = processing_slugs[:filter_count]

    # Build one filter target per column before attaching all case/product targets.
    targets: list[dict[str, Any]] = []
    for filter_index, processing_slug in enumerate(processing_slugs):
        source = _source_target_for_path(
            _find_gaussian_filter_image(figure_dir, case_prefixes[0], parts, processing_slug),
            f"{title}: {height_label} filter {filter_index + 1}",
            figure_dir,
            expected=f"{case_prefixes[0]}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_*gaussian_filter_{_filter_slug_from_processing(processing_slug)}",
        )
        targets.append(
            _build_target(
                _target_id("filter", filter_index + 1),
                f"{title}: {height_label} filter {filter_index + 1}",
                source,
                x_bands[filter_index],
                y_bands[0],
                width,
                height,
            )
        )

    # Combine each case/product row with its corresponding filter-column processing.
    for case_index, case_prefix in enumerate(case_prefixes):
        for row_index, (panel_kind, panel_label) in enumerate(PANEL_ROWS):
            y_band = y_bands[1 + case_index*len(PANEL_ROWS) + row_index]
            for filter_index, processing_slug in enumerate(processing_slugs):
                source_stems = _source_stems_for_panel(plot.comparison_type, case_prefix, parts, processing_slug, panel_kind)
                source = _source_target_for_path(
                    _find_source_panel_image(
                        figure_dir,
                        source_stems,
                        panel_kind,
                        source_index=source_index,
                    ),
                    f"{case_prefix} filter {filter_index + 1} {panel_label}",
                    figure_dir,
                    expected=_expected_panel_description(source_stems, panel_kind),
                )
                targets.append(
                    _build_target(
                        _target_id(case_prefix, "filter", filter_index + 1, panel_kind),
                        f"{case_prefix} filter {filter_index + 1} {panel_label}",
                        source,
                        x_bands[filter_index],
                        y_band,
                        width,
                        height,
                    )
                )

    return targets


def build_subplot_navigation_targets(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
) -> list[dict[str, Any]]:
    '''
    Purpose
    -------
    Build clickable subplot targets for a comparison view page.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    title: str
        Human-readable comparison/gallery title.

    height_label: str
        Formatted height-pair and optional geometry label.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    targets: list of dict
        Clickable panel records, preferring exact generator metadata and
        resolving retained historical source paths. Unsupported metadata schema
        raises ValueError.
    '''
    # Load explicit subplot provenance and reject unsupported metadata versions.
    metadata_file = find_json_sidecar(plot.path, '.subplots.json')
    metadata = None
    if metadata_file.is_file():
        metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
        if metadata.get('schema_version') != 1:
            raise ValueError(f'Unsupported subplot metadata: {metadata_file}')
    # Complete generator records already contain the exact panel geometry and
    # source identities. Avoid re-detecting every image before discarding guesses.
    if metadata and metadata.get('all_axes'):
        targets = []
    elif plot.comparison_type in {"field_strength_comparison", "field_orientation_comparison"}:
        targets = _build_field_comparison_targets(plot, title, height_label, figure_dir=figure_dir)
    elif plot.comparison_type == "gaussian_filter_comparison":
        targets = _build_gaussian_comparison_targets(plot, title, height_label, figure_dir=figure_dir)
    else:
        targets = []
    # Resolve retained source locations and merge exact records with any detected
    # targets.
    if metadata:
        explicit = metadata['targets']
        root = Path(plot.path.parent if figure_dir is None else figure_dir).resolve()
        from figure_locations import figure_project_root, resolve_legacy_figure_source
        for target in explicit:
            source = resolve_legacy_figure_source(target['sourceFile'], figure_project_root(root))
            target['sourceFile'] = str(source)
            target['src'] = _quoted_parent_image_src(source, root)
            target['sourcePath'] = _relative_source_path(source, root)
        targets = (explicit if metadata.get('all_axes') else
                   [target for target in targets if _target_panel_kind(target) != 'komega'] + explicit)
    return targets


def publish_subplot_pages(plot, targets, view_dir):
    '''
    Purpose
    -------
    Create durable individual figure files without changing the megaplot image.

    Missing historical exports use the exact corresponding image crop, never a
    neighboring dataset or a differently filtered scientific product.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    targets: iterable of dict
        Subplot navigation records with source identities and image bounds.

    view_dir: str or Path
        Destination directory for individual figure pages and extracted crops.

    Outputs
    -------
    None
        Write durable crops and individual HTML pages, updating supplied targets
        in place with resolved sources and figureHref links.
    '''
    # Prepare durable extracted-image and individual-page directories.
    from PIL import Image
    assets = Path(view_dir) / 'subplot_assets'
    assets.mkdir(parents=True, exist_ok=True)
    pages = Path(view_dir) / 'individual_figures'
    pages.mkdir(parents=True, exist_ok=True)
    megaplot = None
    # Derive a stable per-panel asset/page identity from the source comparison and
    # target id.
    for target in targets:
        identity = sha256((str(plot.path) + ':' + str(target['id'])).encode()).hexdigest()[:24]
        source = target.get('sourceFile')
        crop = target.get('crop')
        # Extract the recorded exact megaplot crop when a standalone source is missing
        # or cropped.
        if target.get('missing') or crop:
            bounds = crop or target['pixelBounds']
            source = assets / (identity + '.png')
            if megaplot is None:
                megaplot = Image.open(plot.path)
            x, y = bounds['left'], bounds['top']
            megaplot.crop((x, y, x + bounds['width'], y + bounds['height'])).save(source)
            target['missing'] = False
            target['crop'] = None
            target['sourceFile'] = str(source)
            target['src'] = relative_href(source, view_dir)
            target['sourcePath'] = str(source)
            target['extractedFromMegaplot'] = True
        if not source:
            continue
        # Publish an individual image page with the target's precise Bokeh launch
        # context.
        workspace = (target.get('bokeh') or {}).get('workspace')
        page = write_figure_page(source, output_path=pages/(identity + '.html'),
            label=target['label'], workspace=workspace, komega=_target_panel_kind(target) == 'komega')
        target['figureHref'] = relative_href(page, view_dir)
    if megaplot is not None:
        megaplot.close()


def resolved_subplot_navigation_targets(targets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    '''
    Purpose
    -------
    Keep navigation records with an available nonempty source URL.

    Inputs
    ------
    targets: iterable of dict
        Subplot navigation records with source identities and image bounds.

    Outputs
    -------
    resolved: list of dict
        References to existing nonmissing targets; no deep copies are made.
    '''

    # Keep only targets with a usable source link and no missing flag.
    return [target for target in targets if not target.get("missing", False) and str(target.get("src", "")) != ""]


def _public_navigation_target(target: dict[str, Any]) -> dict[str, Any]:
    '''
    Purpose
    -------
    Remove private filesystem and missing-source diagnostics from a browser record.

    Inputs
    ------
    target: dict
        One subplot navigation record.

    Outputs
    -------
    public: dict
        Shallow copy excluding sourceFile, missing, and expected entries.
    '''

    # Remove private source paths and publication-only diagnostics from browser data.
    return {
        key: value
        for key, value in target.items()
        if key not in {"sourceFile", "missing", "expected"}
    }


def subplot_hit_bounds(targets):
    '''
    Purpose
    -------
    Include each subplot's surrounding labels/colorbar without crossing a neighbor.

    Data/crop bounds remain unchanged. Adjacent image frames define the midpoint
    between their plot cells, so a title or axis-label click follows the same link.

    Inputs
    ------
    targets: sequence of dict
        Subplot navigation records with source identities and image bounds.

    Outputs
    -------
    targets: sequence of dict
        Same target collection after in-place hitBounds expansion in percentage
        units. Horizontal and then vertical separators keep neighboring click
        areas distinct.
    '''
    # Expand horizontally toward neighboring panel separators before assigning click
    # bounds.
    for target in targets:
        b = target['bounds']
        left, top = b['left'], b['top']
        right, bottom = left+b['width'], top+b['height']
        horizontal = []
        for other in targets:
            if other is target:
                continue
            o = other['bounds']
            l, t, r, d = o['left'], o['top'], o['left']+o['width'], o['top']+o['height']
            if min(bottom, d) > max(top, t):
                horizontal.append((l, r))
        epsilon = 1e-7  # Percent conversions can differ at an abutting edge.
        before_x = [r for l, r in horizontal if r <= left+epsilon]
        after_x = [l for l, r in horizontal if l >= right-epsilon]
        x0 = (max(before_x)+left)/2 if before_x else max(0., left-b['width']*.25)
        x1 = (min(after_x)+right)/2 if after_x else min(100., right+b['width']*.25)
        target['hitBounds'] = dict(left=x0, top=top, width=x1-x0, height=b['height'])

    # A short row can expand into neighboring columns of the row above. Use
    # the completed horizontal footprints when finding vertical separators.
    for target in targets:
        b, hit = target['bounds'], target['hitBounds']
        left, right = hit['left'], hit['left']+hit['width']
        top, bottom = b['top'], b['top']+b['height']
        vertical = []
        for other in targets:
            if other is target:
                continue
            o, other_hit = other['bounds'], other['hitBounds']
            l, r = other_hit['left'], other_hit['left']+other_hit['width']
            if min(right, r) > max(left, l)+1e-7:
                vertical.append((o['top'], o['top']+o['height']))
        before_y = [d for t, d in vertical if d <= top+1e-7]
        after_y = [t for t, d in vertical if t >= bottom-1e-7]
        y0 = (max(before_y)+top)/2 if before_y else max(0., top-b['height']*.2)
        y1 = (min(after_y)+bottom)/2 if after_y else min(100., bottom+b['height']*.2)
        hit.update(top=y0, height=y1-y0)
    return targets


def _target_panel_kind(target: dict[str, Any]) -> str:
    '''
    Purpose
    -------
    Resolve the declared or identifier-derived subplot product kind.

    Inputs
    ------
    target: dict
        One subplot navigation record.

    Outputs
    -------
    kind: str
        Panel kind, or empty text when no recognized identifier is present.
    '''

    # Prefer explicit product metadata before decoding known target-id patterns.
    if target.get('panelKind'):
        return target['panelKind']
    target_id = str(target.get("id", ""))
    if target_id.endswith("-komega"):
        return "komega"
    if target_id.endswith("-xc"):
        return "xc"
    if target_id.endswith("-phase_diff"):
        return "phase_diff"
    if target_id.startswith("filter-") or "gaussian-filter" in target_id:
        return "gaussian_filter"

    return ""


def _target_matches_declared_kind(target: dict[str, Any]) -> bool:
    '''
    Purpose
    -------
    Validate a subplot source against recorded or filename-derived product identity.

    Inputs
    ------
    target: dict
        One subplot navigation record.

    Outputs
    -------
    matches: bool
        Whether source metadata/basename agrees with the declared kind; accepted
        crops and unspecified kinds pass through.
    '''

    # Accept exact extracted crops before validating standalone source-product identity.
    if target.get('extractedFromMegaplot'):
        return True
    if target.get('panelKind') == 'komega' and target.get('crop') and target.get('bokeh'):
        return True
    source_path = str(target.get("sourceFile") or target.get("sourcePath", ""))
    panel_kind = _target_panel_kind(target)
    if source_path == "" or panel_kind == "":
        return True
    if panel_kind not in {'komega', 'xc', 'phase_diff', 'gaussian_filter'}:
        return True
    # Use canonical product metadata when available, then inspect retained legacy
    # suffixes.
    metadata = _load_output_paths_module().read_metadata(source_path)
    if metadata is not None:
        expected = {'komega': {'komega_diagram'}, 'xc': {'time_distance'},
                    'phase_diff': {'phase_difference'}, 'gaussian_filter': {'gaussian_filter'}}
        if panel_kind in expected:
            return metadata.get('product') in expected[panel_kind]
    # Folder names such as comparison_views are organizational, not product
    # labels. Legacy images without metadata retain their original stem checks.
    stem = Path(source_path).stem.lower()
    if "comparison_" in stem or "orientation_validation" in stem:
        return False
    suffixes = {'komega': '_komega', 'xc': '_xc', 'phase_diff': '_phase_diff'}
    if panel_kind in suffixes:
        return stem.endswith(suffixes[panel_kind])
    if panel_kind == 'gaussian_filter':
        return '_gaussian_filter_' in stem
    return True


def validate_subplot_navigation_targets(
    plot: ComparisonPlot,
    targets: Iterable[dict[str, Any]],
    figure_dir: Path,
) -> list[str]:
    '''
    Purpose
    -------
    Collect missing-source, product-kind, and comparison-row warnings.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    targets: iterable of dict
        Subplot navigation records with source identities and image bounds.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    Outputs
    -------
    warnings: list of str
        Tab-separated diagnostic messages; no exception is raised solely for
        missing links.
    '''

    # Collect publication warnings while checking each declared source independently.
    figure_dir = Path(figure_dir).expanduser().resolve()
    warnings: list[str] = []
    for target in targets:
        if target.get("missing", False) or str(target.get("src", "")) == "":
            warnings.append(
                "missing target\t"
                f"comparison={plot.path.name}\t"
                f"target={target.get('id', '')}\t"
                f"label={target.get('label', '')}\t"
                f"expected={target.get('expected', '')}"
            )
            continue

        # Resolve missing absolute identities against the figure root before checking
        # file existence.
        source_file = str(target.get("sourceFile", ""))
        if source_file == "":
            source_path = Path(str(target.get("sourcePath", "")))
            source_file = str((figure_dir / source_path).resolve())
        if not Path(source_file).exists():
            warnings.append(
                "missing file\t"
                f"comparison={plot.path.name}\t"
                f"target={target.get('id', '')}\t"
                f"source={target.get('sourcePath', '')}"
            )
        if not _target_matches_declared_kind(target):
            warnings.append(
                "product mismatch\t"
                f"comparison={plot.path.name}\t"
                f"target={target.get('id', '')}\t"
                f"source={target.get('sourcePath', '')}\t"
                f"expected={target.get('expected', '')}"
            )

        # Require the complete comparison-row set when a komega target has no numerical
        # launch context.
        if _target_panel_kind(target) == "komega" and not target.get('bokeh'):
            comparison_rows = target.get("comparisonRows", [])
            row_labels = tuple(str(row.get("label", "")) for row in comparison_rows)
            if row_labels != KOMEGA_COMPARISON_ROW_LABELS:
                warnings.append(
                    "missing eight-row komega comparison\t"
                    f"comparison={plot.path.name}\t"
                    f"target={target.get('id', '')}\t"
                    f"source={target.get('sourcePath', '')}"
                )
            elif any("souffrin" in label.lower() for label in row_labels):
                warnings.append(
                    "forbidden Souffrin row\t"
                    f"comparison={plot.path.name}\t"
                    f"target={target.get('id', '')}"
                )

    return warnings


def _json_script_data(data: object) -> str:
    '''
    Purpose
    -------
    Serialize a browser payload with escaped closing-script sequences.

    Inputs
    ------
    data: JSON-serializable object
        Payload embedded in an HTML script element.

    Outputs
    -------
    json_text: str
        Compact ASCII JSON with closing-tag separators escaped for embedding.
    '''

    # Escape closing-tag separators so embedded JSON cannot terminate its script
    # element.
    return json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")


def discover_comparison_plots(
    figure_dir: str | Path,
    comparison_types: Iterable[str] | None = None,
) -> list[ComparisonPlot]:
    '''
    Purpose
    -------
    Discover comparison plot images in deterministic filename order.

    Inputs
    ------
    figure_dir: str or Path
        Root recursively searched for comparison PNG/JPEG files.

    comparison_types: iterable of str or None
        Comparison kinds to discover; None selects all configured gallery kinds.

    Outputs
    -------
    plots: list of ComparisonPlot
        Recognized current/legacy comparison figures ordered by comparison type,
        height pair, and filename; nonexistent roots yield [].
    '''

    # Prepare supported filename patterns before scanning the discovery root.
    figure_dir = Path(figure_dir).expanduser().resolve()
    selected_types = list(COMPARISON_VIEWERS if comparison_types is None else comparison_types)
    patterns = {
        comparison_type: _comparison_filename_pattern(comparison_type)
        for comparison_type in selected_types
    }

    if not figure_dir.exists():
        return []

    plots: list[ComparisonPlot] = []
    # Scan supported images deterministically, excluding generated and duplicate-height
    # trees.
    candidates = sorted(
        (
            path
            for path in figure_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and FULL_RESOLUTION_VIEW_DIRNAME not in path.relative_to(figure_dir).parts
            and not any(part.startswith('delta_z_') for part in path.relative_to(figure_dir).parts)
        ),
        key=lambda path: path.relative_to(figure_dir).as_posix(),
    )

    # Prefer exact subplot metadata before decoding legacy comparison filenames.
    for path in candidates:
        metadata_file = find_json_sidecar(path, '.subplots.json')
        if metadata_file.is_file():
            metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
            kind = metadata.get('comparison_type')
            if kind in selected_types:
                width, height = read_image_size(path)
                h1, h2 = metadata['height_pair_km']
                plots.append(ComparisonPlot(kind, path, quote(path.relative_to(figure_dir).as_posix()),
                                            h1, h2, width, height, metadata.get('html_scope', {}).get('geometry', _extract_xcorr_geometry_from_tail(path.stem))))
                continue
        for comparison_type, pattern in patterns.items():
            match = pattern.match(path.name)
            if match is None:
                continue

            width, height = read_image_size(path)
            tail = path.stem[match.end() :]
            plots.append(
                ComparisonPlot(
                    comparison_type=comparison_type,
                    path=path,
                    relative_src=quote(path.relative_to(figure_dir).as_posix()),
                    h1_km=_parse_height_token(match.group("h1")),
                    h2_km=_parse_height_token(match.group("h2")),
                    width=width,
                    height=height,
                    xcorr_geometry=_extract_xcorr_geometry_from_tail(tail),
                )
            )
            break

    # Return comparison-kind and height-pair order independent of filesystem traversal.
    return sorted(
        plots,
        key=lambda plot: (
            plot.comparison_type,
            _height_sort_key(plot.height_pair),
            plot.path.name,
        ),
    )


def comparison_height_pairs(plots: Iterable[ComparisonPlot]) -> list[tuple[float, float]]:
    '''
    Purpose
    -------
    Return the shared deterministic height-pair order for all galleries.

    Inputs
    ------
    plots: iterable of ComparisonPlot
        Discovered comparison images.

    Outputs
    -------
    height_pairs: list of tuple
        Unique height pairs ordered numerically, with None values sorted last.
    '''

    # Deduplicate physical height pairs and order unavailable heights last.
    height_pairs = {plot.height_pair for plot in plots}
    return sorted(height_pairs, key=_height_sort_key)


def _dimension_attributes(plot: ComparisonPlot) -> str:
    '''
    Purpose
    -------
    Render both image dimensions only when both are known.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    Outputs
    -------
    attributes: str
        HTML width/height attributes or empty text.
    '''

    # Emit intrinsic dimensions only when both are known.
    if plot.width is None or plot.height is None:
        return ""

    return f' width="{plot.width}" height="{plot.height}"'


def _full_resolution_view_name(plot: ComparisonPlot) -> str:
    '''
    Purpose
    -------
    Derive the inspection-page filename from a comparison image stem.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    Outputs
    -------
    filename: str
        Comparison basename with the .html extension.
    '''

    # Keep the source comparison stem as the durable inspection-page identity.
    return f"{plot.path.stem}.html"


def _full_resolution_view_href(plot: ComparisonPlot, document_dir=None, support_dir=None) -> str:
    '''
    Purpose
    -------
    Resolve a gallery link to the corresponding full-resolution inspection page.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    document_dir: str or Path or None
        Directory against which browser-relative source and view URLs are
        calculated.

    support_dir: str or Path or dict or None
        Full-resolution view directory or per-plot directory mapping used for
        links.

    Outputs
    -------
    href: str
        Encoded relative URL using the supplied support mapping/directory or
        default comparison_view folder.
    '''

    # Use actual per-plot support directories when constructing relocated gallery links.
    if document_dir is not None and support_dir is not None:
        directory = support_dir[plot.path] if isinstance(support_dir, dict) else support_dir
        return _relative_image_src(Path(directory) / _full_resolution_view_name(plot), Path(document_dir))
    return f"{FULL_RESOLUTION_VIEW_DIRNAME}/{quote(_full_resolution_view_name(plot))}"


def _render_plot_link(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    document_dir: Path | None,
    support_dir: Path | None = None,
) -> str:
    '''
    Purpose
    -------
    Render an escaped lazy-loading image link for one gallery entry.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    title: str
        Human-readable comparison/gallery title.

    height_label: str
        Formatted height-pair and optional geometry label.

    document_dir: str or Path or None
        Directory against which browser-relative source and view URLs are
        calculated.

    support_dir: str or Path or dict or None
        Full-resolution view directory or per-plot directory mapping used for
        links.

    Outputs
    -------
    html: str
        Anchor, height label, and image markup linking to the inspection page.
    '''

    # Escape image and inspection-page URLs before assembling a lazy-loading gallery
    # entry.
    src = escape(
        plot.relative_src if document_dir is None else _relative_image_src(plot.path, document_dir),
        quote=True,
    )
    view_href = escape(_full_resolution_view_href(plot, document_dir, support_dir), quote=True)
    image_title = escape(f"{title}: {height_label}", quote=True)
    dimension_attributes = _dimension_attributes(plot)

    return (
        f'<a class="figure-link" href="{view_href}" title="{image_title}" '
        f'data-source-path="{src}">\n'
        f'  <span class="height-label">{escape(height_label)}</span>\n'
        f'  <img src="{src}" alt="{image_title}"{dimension_attributes} '
        f'loading="lazy" decoding="async">\n'
        f"</a>"
    )


def _full_resolution_dimension_attributes(plot: ComparisonPlot) -> str:
    '''
    Purpose
    -------
    Render each independently available source-image dimension.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    Outputs
    -------
    attributes: str
        Joined HTML width and/or height attributes; unknown dimensions are
        omitted.
    '''

    # Emit each known intrinsic image dimension independently.
    attributes = []
    if plot.width is not None:
        attributes.append(f' width="{plot.width}"')
    if plot.height is not None:
        attributes.append(f' height="{plot.height}"')
    return "".join(attributes)


def _ordered_gallery_plots(
    selected_plots: Iterable[ComparisonPlot],
    height_pairs: Iterable[tuple[float, float]],
) -> list[ComparisonPlot]:
    '''
    Purpose
    -------
    Group comparison images by the requested height-pair order.

    Inputs
    ------
    selected_plots: iterable of ComparisonPlot
        Images selected for one gallery.

    height_pairs: iterable of tuple
        Requested height-pair ordering, in km; an empty order lets the helper
        derive it.

    Outputs
    -------
    ordered: list of ComparisonPlot
        Filename-sorted plots for each included height pair; an empty supplied
        order derives the shared numeric ordering.
    '''

    # Group all selected plots before applying the requested height-pair order.
    plots_by_height_pair: dict[tuple[float, float], list[ComparisonPlot]] = {}
    for plot in selected_plots:
        plots_by_height_pair.setdefault(plot.height_pair, []).append(plot)

    ordered_plots: list[ComparisonPlot] = []
    ordered_height_pairs = list(height_pairs)
    if len(ordered_height_pairs) == 0:
        ordered_height_pairs = comparison_height_pairs(selected_plots)

    # Sort filenames only within each requested height group.
    for height_pair in ordered_height_pairs:
        ordered_plots.extend(sorted(plots_by_height_pair.get(height_pair, []), key=lambda plot: plot.path.name))

    return ordered_plots


def render_full_resolution_view_html(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
    navigation_targets: Iterable[dict[str, Any]] | None = None,
    document_dir: Path | None = None,
) -> str:
    '''
    Purpose
    -------
    Render a minimal, borderless full-resolution inspection page.

    Inputs
    ------
    plot: ComparisonPlot
        Discovered comparison image and its height/geometry metadata.

    title: str
        Human-readable comparison/gallery title.

    height_label: str
        Formatted height-pair and optional geometry label.

    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    navigation_targets: iterable of dict or None
        Explicit subplot records; None discovers/builds targets from the
        comparison.

    document_dir: str or Path or None
        Directory against which browser-relative source and view URLs are
        calculated.

    Outputs
    -------
    html: str
        Inspection document containing source dimensions, subplot hit targets,
        encoded navigation data, and browser launch/selection behavior. No file
        is written.
    '''

    # Resolve source/document locations and preserve the image's intrinsic dimensions.
    figure_dir = Path(plot.path.parent if figure_dir is None else figure_dir).expanduser().resolve()
    document_dir = (
        Path(figure_dir / FULL_RESOLUTION_VIEW_DIRNAME)
        if document_dir is None
        else Path(document_dir).expanduser().resolve()
    )
    src = escape(_relative_image_src(plot.path, document_dir), quote=True)
    alt_text = escape(f"{title}: {height_label}", quote=True)
    dimension_attributes = _full_resolution_dimension_attributes(plot)
    frame_style = ""
    if plot.width is not None and plot.height is not None:
        frame_style = f' style="width: {plot.width}px; height: {plot.height}px;"'
    # Build navigation only when the caller has not supplied exact target records.
    if navigation_targets is None:
        navigation_targets = build_subplot_navigation_targets(plot, title, height_label, figure_dir=figure_dir)
    navigation_targets = resolved_subplot_navigation_targets(navigation_targets)
    navigation_targets = subplot_hit_bounds([_public_navigation_target(target) for target in navigation_targets])
    # Render source-preserving subplot hit areas and accessible navigation labels.
    rendered_hotspots = "\n".join(
        (
            f'    <a class="subplot-hotspot" href="{escape(str(target.get("figureHref", target["src"])), quote=True)}" '
            f'data-nav-target="{escape(str(target["id"]), quote=True)}" '
            f'data-source-path="{escape(str(target.get("sourcePath", "")), quote=True)}" '
            f'title="{escape(str(target["label"]), quote=True)}" '
            f'aria-label="{escape(str(target["label"]), quote=True)}" '
            f'style="left: {target["hitBounds"]["left"]:.6f}%; '
            f'top: {target["hitBounds"]["top"]:.6f}%; '
            f'width: {target["hitBounds"]["width"]:.6f}%; '
            f'height: {target["hitBounds"]["height"]:.6f}%;"></a>'
        )
        for target in navigation_targets
    )
    # Encode target/overview records separately from the unchanged browser
    # implementation.
    targets_json = _json_script_data(navigation_targets)
    overview_json = _json_script_data(
        {
            "id": "overview",
            "label": f"{title}: {height_label}",
            "src": _relative_image_src(plot.path, document_dir),
            "sourcePath": plot.path.name,
            "alt": f"{title}: {height_label}",
            "crop": None,
        }
    )

    # Assemble the inspection document from Python metadata and the embedded browser
    # template.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} {escape(height_label)}</title>
  <style>
    html,
    body {{
      margin: 0;
      padding: 0;
      background: #ffffff;
    }}

    body {{
      min-height: 100vh;
    }}

    .figure-frame {{
      position: relative;
      display: block;
      overflow: visible;
    }}

    .figure-frame.is-managed img {{
      position: absolute;
      left: 0;
      top: 0;
      max-width: none;
      max-height: none;
    }}

    .figure-frame.is-crop {{
      overflow: hidden;
    }}

    img {{
      display: block;
      width: auto;
      height: auto;
      max-width: none;
      max-height: none;
      image-rendering: auto;
    }}

    [hidden] {{
      display: none !important;
    }}

    .comparison-stack {{
      box-sizing: border-box;
      width: min(100%, 1800px);
      margin: 0 auto;
      padding: 16px;
      color: #111111;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    .comparison-row {{
      margin: 0;
      padding: 0 0 28px;
    }}

    .comparison-row + .comparison-row {{
      padding-top: 24px;
      border-top: 1px solid #d8d8d8;
    }}

    .comparison-row h2 {{
      margin: 0 0 10px;
      font-size: 19px;
      font-weight: 600;
    }}

    .comparison-row img {{
      width: auto;
      max-width: 100%;
      height: auto;
    }}

    .subplot-map {{
      position: absolute;
      inset: 0;
    }}

    .figure-frame:not(.is-overview) .subplot-map {{
      display: none;
    }}

    .subplot-hotspot {{
      position: absolute;
      display: block;
      cursor: pointer;
      background: rgba(0, 0, 0, 0);
      touch-action: pan-x pan-y;
    }}

    .subplot-hotspot:focus-visible {{
      outline: 2px solid #0b5cab;
      outline-offset: 2px;
    }}
    .bokeh-tools {{
      padding: 12px; display: flex; gap: 12px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .bokeh-tools a {{
      padding: 8px 14px; border: 1px solid #777; border-radius: 4px;
      color: #111; background: white; text-decoration: none;
    }}
    .bokeh-tools a[aria-disabled="true"] {{ color: #777; cursor: default; }}
  </style>
</head>
<body>
  <nav class="bokeh-tools" data-bokeh-tools hidden aria-label="Bokeh tools">
    <a data-bokeh-workspace>Open in Bokeh</a>
    <span data-bokeh-error hidden>This historical figure has no exact numerical launch context. No dataset will be substituted.</span>
  </nav>
  <div class="figure-frame is-overview"{frame_style} data-figure-frame>
    <img data-full-resolution-image src="{src}" alt="{alt_text}"{dimension_attributes}>
    <div class="subplot-map" aria-label="{escape(title)} subplot navigation">
{rendered_hotspots}
    </div>
  </div>
  <main class="comparison-stack" data-comparison-stack hidden aria-label="k-omega dispersion comparison"></main>
  <script>
    (() => {{
      const overview = {overview_json};
      const targets = {targets_json};
      const targetById = new Map(targets.map((target) => [target.id, target]));
      const frame = document.querySelector("[data-figure-frame]");
      const image = document.querySelector("[data-full-resolution-image]");
      const comparisonStack = document.querySelector("[data-comparison-stack]");
      const bokehTools = document.querySelector("[data-bokeh-tools]");
      const workspaceLink = document.querySelector("[data-bokeh-workspace]");
      const launchError = document.querySelector("[data-bokeh-error]");
      const defaultWorkspaceUrl = "{DEFAULT_BOKEH_SERVER_URL}/integrated_komega_bokeh_app";
      const minimumScale = 0.01;
      let baseWidth = Number(image.getAttribute("width")) || 0;
      let baseHeight = Number(image.getAttribute("height")) || 0;
      let scale = 1;
      let gestureStartScale = 1;
      let currentViewId = "overview";
      let pendingViewState = null;
      let pointerStart = null;

      const storageKey = () => `comparison-view:${{window.location.pathname}}:${{currentViewId}}`;

      const saveViewState = () => {{
        try {{
          window.sessionStorage.setItem(storageKey(), JSON.stringify({{
            scale,
            scrollX: window.scrollX,
            scrollY: window.scrollY,
          }}));
        }} catch (error) {{
          // Session storage can be unavailable for local files in some browsers.
        }}
      }};

      const loadViewState = (viewId) => {{
        try {{
          const value = window.sessionStorage.getItem(`comparison-view:${{window.location.pathname}}:${{viewId}}`);
          return value === null ? null : JSON.parse(value);
        }} catch (error) {{
          return null;
        }}
      }};

      const refreshBaseDimensions = () => {{
        baseWidth = image.naturalWidth || baseWidth || image.getBoundingClientRect().width;
        baseHeight = image.naturalHeight || baseHeight || image.getBoundingClientRect().height;
      }};

      const activeView = () => targetById.get(currentViewId) || overview;

      const renderComparisonRows = (view) => {{
        comparisonStack.replaceChildren();
        view.comparisonRows.forEach((row) => {{
          const section = document.createElement("section");
          section.className = "comparison-row";
          section.dataset.komegaComparisonRow = String(row.index);
          const heading = document.createElement("h2");
          heading.textContent = `${{row.index}}. ${{row.label}}`;
          const rowImage = document.createElement("img");
          rowImage.src = row.src;
          rowImage.alt = row.alt || row.label;
          rowImage.loading = row.index === 1 ? "eager" : "lazy";
          rowImage.decoding = "async";
          if (Number(row.width) > 0) {{
            rowImage.width = Number(row.width);
          }}
          if (Number(row.height) > 0) {{
            rowImage.height = Number(row.height);
          }}
          section.append(heading, rowImage);
          comparisonStack.append(section);
        }});
        frame.hidden = true;
        comparisonStack.hidden = false;
      }};

      const setFrameGeometry = () => {{
        const view = activeView();
        const crop = view.crop || null;
        const visibleWidth = crop === null ? baseWidth : crop.width;
        const visibleHeight = crop === null ? baseHeight : crop.height;
        const renderedWidth = visibleWidth * scale;
        const renderedHeight = visibleHeight * scale;

        frame.style.width = `${{renderedWidth}}px`;
        frame.style.height = `${{renderedHeight}}px`;
        image.style.width = `${{baseWidth * scale}}px`;
        image.style.height = `${{baseHeight * scale}}px`;
        image.style.left = crop === null ? "0px" : `${{-crop.left * scale}}px`;
        image.style.top = crop === null ? "0px" : `${{-crop.top * scale}}px`;
        frame.classList.toggle("is-overview", currentViewId === "overview");
        frame.classList.toggle("is-crop", crop !== null);
      }};

      const applyScale = (nextScale, anchorX, anchorY) => {{
        if (!Number.isFinite(nextScale) || nextScale <= 0) {{
          return;
        }}

        refreshBaseDimensions();
        if (baseWidth <= 0 || baseHeight <= 0) {{
          return;
        }}

        const before = frame.getBoundingClientRect();
        const viewportX = Number.isFinite(anchorX) ? anchorX : window.innerWidth / 2;
        const viewportY = Number.isFinite(anchorY) ? anchorY : window.innerHeight / 2;
        const imageX = before.width > 0 ? (viewportX - before.left) / before.width : 0.5;
        const imageY = before.height > 0 ? (viewportY - before.top) / before.height : 0.5;
        const boundedScale = Math.max(minimumScale, nextScale);
        const view = activeView();
        const crop = view.crop || null;
        const visibleWidth = crop === null ? baseWidth : crop.width;
        const renderedWidth = visibleWidth * boundedScale;

        if (!Number.isFinite(renderedWidth) || renderedWidth <= 0) {{
          return;
        }}

        scale = boundedScale;
        setFrameGeometry();

        const after = frame.getBoundingClientRect();
        const targetLeft = window.scrollX + after.left + imageX * after.width - viewportX;
        const targetTop = window.scrollY + after.top + imageY * after.height - viewportY;
        window.scrollTo(targetLeft, targetTop);
      }};

      const applyStoredState = () => {{
        if (pendingViewState !== null && Number.isFinite(pendingViewState.scale)) {{
          scale = Math.max(minimumScale, pendingViewState.scale);
        }}
        setFrameGeometry();

        if (pendingViewState !== null) {{
          window.scrollTo(
            Number(pendingViewState.scrollX) || 0,
            Number(pendingViewState.scrollY) || 0,
          );
        }}

        pendingViewState = null;
      }};

      const showView = (viewId, updateHistory) => {{
        const nextView = viewId === "overview" ? overview : targetById.get(viewId);
        if (nextView === undefined) {{
          return;
        }}

        saveViewState();
        currentViewId = viewId;
        pendingViewState = loadViewState(viewId);
        scale = pendingViewState === null || !Number.isFinite(pendingViewState.scale)
          ? 1
          : Math.max(minimumScale, pendingViewState.scale);

        if (updateHistory) {{
          const nextUrl = viewId === "overview"
            ? window.location.pathname + window.location.search
            : `#subplot=${{encodeURIComponent(viewId)}}`;
          window.history.pushState({{ viewId }}, "", nextUrl);
        }}

        document.title = nextView.label || overview.label;
        const isKomega = nextView.panelKind === "komega" || /-komega$/.test(nextView.id);
        bokehTools.hidden = !isKomega;
        launchError.hidden = !isKomega || Boolean(nextView.bokeh);
        const workspace = nextView.bokeh && nextView.bokeh.workspace;
        if (workspace && workspace.url) {{
          workspaceLink.href = "bokeh-launch.html#target=" + encodeURIComponent(workspace.url);
          workspaceLink.setAttribute("aria-disabled", "false");
        }} else {{
          workspaceLink.removeAttribute("href");
          workspaceLink.setAttribute("aria-disabled", "true");
        }}

        comparisonStack.hidden = true;
        comparisonStack.replaceChildren();
        frame.hidden = false;
        if (image.getAttribute("src") !== nextView.src) {{
          image.addEventListener("load", () => {{
            refreshBaseDimensions();
            applyStoredState();
          }}, {{ once: true }});
          image.src = nextView.src;
        }} else {{
          refreshBaseDimensions();
          applyStoredState();
        }}
      }};

      const viewIdFromLocation = () => {{
        const match = window.location.hash.match(/^#subplot=(.+)$/);
        if (match === null) {{
          return "overview";
        }}

        const viewId = decodeURIComponent(match[1]);
        return targetById.has(viewId) ? viewId : "overview";
      }};

      frame.classList.add("is-managed");
      image.addEventListener("load", () => {{
        refreshBaseDimensions();
        setFrameGeometry();
      }}, {{ once: true }});
      refreshBaseDimensions();
      setFrameGeometry();
      currentViewId = viewIdFromLocation();
      window.history.replaceState({{ viewId: currentViewId }}, "", window.location.href);
      if (currentViewId !== "overview") {{
        showView(currentViewId, false);
      }}

      document.addEventListener("pointerdown", (event) => {{
        const link = event.target.closest("[data-nav-target]");
        pointerStart = link === null ? null : {{
          x: event.clientX,
          y: event.clientY,
          id: link.getAttribute("data-nav-target"),
        }};
      }}, true);

      document.addEventListener("click", (event) => {{
        const link = event.target.closest("[data-nav-target]");
        if (link === null) {{
          return;
        }}

        const viewId = link.getAttribute("data-nav-target");
        if (pointerStart !== null && pointerStart.id === viewId) {{
          const dx = event.clientX - pointerStart.x;
          const dy = event.clientY - pointerStart.y;
          if (Math.hypot(dx, dy) > 6) {{
            event.preventDefault();
            pointerStart = null;
            return;
          }}
        }}

        pointerStart = null;
        // Follow the actual individual-figure file, including modified/new-tab clicks.
        // Existing hash URLs remain readable for older bookmarks.
        if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {{
          event.preventDefault();
          window.location.assign(link.href);
        }}
      }});

      window.addEventListener("popstate", (event) => {{
        const viewId = event.state && typeof event.state.viewId === "string"
          ? event.state.viewId
          : viewIdFromLocation();
        showView(viewId, false);
      }});

      window.addEventListener("pagehide", saveViewState);

      window.addEventListener("wheel", (event) => {{
        if (!event.ctrlKey && !event.metaKey) {{
          return;
        }}

        if (!comparisonStack.hidden) {{
          return;
        }}

        event.preventDefault();
        applyScale(scale * Math.exp(-event.deltaY * 0.002), event.clientX, event.clientY);
      }}, {{ passive: false }});

      window.addEventListener("gesturestart", (event) => {{
        if (!comparisonStack.hidden) {{
          return;
        }}
        event.preventDefault();
        gestureStartScale = scale;
      }}, {{ passive: false }});

      window.addEventListener("gesturechange", (event) => {{
        if (!comparisonStack.hidden) {{
          return;
        }}
        event.preventDefault();
        applyScale(gestureStartScale * event.scale, window.innerWidth / 2, window.innerHeight / 2);
      }}, {{ passive: false }});
    }})();
  </script>
</body>
</html>
"""


def render_comparison_view_html(
    comparison_type: str,
    plots: Iterable[ComparisonPlot],
    height_pairs: Iterable[tuple[float, float]],
    document_dir: Path | None = None,
    support_dir: Path | None = None,
) -> str:
    '''
    Purpose
    -------
    Render one standalone comparison gallery.

    Inputs
    ------
    comparison_type: str
        field_strength_comparison, field_orientation_comparison, or
        gaussian_filter_comparison.

    plots: iterable of ComparisonPlot
        Discovered comparison images.

    height_pairs: iterable of tuple
        Requested height-pair ordering, in km; an empty order lets the helper
        derive it.

    document_dir: str or Path or None
        Directory against which browser-relative source and view URLs are
        calculated.

    support_dir: str or Path or dict or None
        Full-resolution view directory or per-plot directory mapping used for
        links.

    Outputs
    -------
    html: str
        Gallery document for the selected kind and height ordering; no file is
        written. Unsupported kinds raise ValueError.
    '''

    # Reject unsupported gallery kinds before selecting source figures.
    if comparison_type not in COMPARISON_VIEWERS:
        raise ValueError(f"Unsupported comparison gallery type: {comparison_type}")

    viewer_config = COMPARISON_VIEWERS[comparison_type]
    title = viewer_config["title"]
    selected_plots = [plot for plot in plots if plot.comparison_type == comparison_type]
    if document_dir is not None:
        document_dir = Path(document_dir).expanduser().resolve()
    # Apply shared height ordering and render every selected image link.
    ordered_plots = _ordered_gallery_plots(selected_plots, height_pairs)
    rendered_figures = "\n".join(
        _render_plot_link(plot, title, _format_plot_height_label(plot), document_dir, support_dir)
        for plot in ordered_plots
    )
    if rendered_figures == "":
        rendered_figures = '<p>No comparison plots found.</p>'

    # Describe the gallery contents and select comparison-specific presentation rules.
    plot_count = len(ordered_plots)
    group_count = len({plot.height_pair for plot in ordered_plots})
    summary = f"{plot_count} plots across {group_count} height permutations"
    gaussian_sheet_tight_css = ""
    if comparison_type == "gaussian_filter_comparison":
        gaussian_sheet_tight_css = """
    .figure-sheet {
      padding-left: 8px;
      padding-right: 8px;
    }

    .figure-link {
      width: min(18vw, 220px);
      margin-right: 14px;
      overflow: hidden;
    }

    .figure-link img {
      margin-left: -12%;
      margin-right: -12%;
      max-width: 124%;
    }
"""

    # Assemble the gallery document with the pre-rendered links and browser
    # presentation.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} Gallery</title>
  <style>
    html,
    body {{
      margin: 0;
      padding: 0;
      background: #ffffff;
      color: #111111;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    header {{
      padding: 12px 16px 4px;
    }}

    h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0;
    }}

    .summary {{
      margin: 2px 0 0;
      color: #555555;
      font-size: 13px;
      letter-spacing: 0;
    }}

    .figure-sheet {{
      white-space: nowrap;
      padding: 12px 16px 24px;
    }}

    .figure-link {{
      display: inline-block;
      margin-right: 24px;
      vertical-align: top;
      color: inherit;
      text-decoration: none;
      width: min(30vw, 400px);
    }}

    .figure-link:focus-visible {{
      outline: 2px solid #0b5cab;
      outline-offset: 4px;
    }}

    .height-label {{
      display: block;
      margin: 0 0 6px;
      color: #444444;
      font-size: 13px;
      line-height: 1.2;
    }}

    img {{
      display: block;
      width: auto;
      max-width: 100%;
      height: auto;
      image-rendering: auto;
    }}
{gaussian_sheet_tight_css}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p class="summary">{escape(summary)}</p>
  </header>
  <main class="figure-sheet" aria-label="{escape(title)} height permutations">
{rendered_figures}
  </main>
  <script>
    (() => {{
      const storageKey = `comparison-gallery:${{window.location.pathname}}`;
      const saveScroll = () => {{
        try {{
          window.sessionStorage.setItem(storageKey, JSON.stringify({{
            scrollX: window.scrollX,
            scrollY: window.scrollY,
          }}));
        }} catch (error) {{
        }}
      }};
      const restoreScroll = () => {{
        try {{
          const stored = window.sessionStorage.getItem(storageKey);
          if (stored === null) {{
            return;
          }}
          const state = JSON.parse(stored);
          window.scrollTo(Number(state.scrollX) || 0, Number(state.scrollY) || 0);
        }} catch (error) {{
        }}
      }};

      document.addEventListener("click", (event) => {{
        const link = event.target.closest("a.figure-link");
        if (link === null) {{
          return;
        }}

        event.preventDefault();
        saveScroll();
        window.location.assign(link.href);
      }});

      window.addEventListener("pagehide", saveScroll);
      window.addEventListener("pageshow", restoreScroll);
    }})();
  </script>
</body>
</html>
"""


def write_comparison_viewer(
    figure_dir: str | Path,
    comparison_type: str,
    plots: Iterable[ComparisonPlot],
    height_pairs: Iterable[tuple[float, float]],
    html_dir: str | Path | None = None,
    support_dir: str | Path | None = None,
    published_views: dict | None = None,
    view_directories: dict | None = None,
) -> dict[str, object]:
    '''
    Purpose
    -------
    Write one comparison gallery HTML file.

    Inputs
    ------
    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    comparison_type: str
        field_strength_comparison, field_orientation_comparison, or
        gaussian_filter_comparison.

    plots: iterable of ComparisonPlot
        Discovered comparison images.

    height_pairs: iterable of tuple
        Requested height-pair ordering, in km; an empty order lets the helper
        derive it.

    html_dir: str or Path or None
        Gallery HTML destination; None selects the function's managed/default
        location.

    support_dir: str or Path or None
        Shared inspection-page destination; None uses html_dir/comparison_view.

    published_views: dict or None
        Shared cache mapping already-published view Paths to validation
        warnings; updated in place.

    view_directories: dict or None
        Optional mapping from plot Paths to full-resolution support directories.

    Outputs
    -------
    publication: dict
        Written gallery path, full-resolution view paths, plot count, warning
        count, and warning-log path. Writes source crops/pages/bridges and
        updates published_views when provided.
    '''

    # Create gallery/support destinations and resolve the selected comparison images.
    figure_dir = Path(figure_dir).expanduser().resolve()
    figure_dir.mkdir(parents=True, exist_ok=True)
    html_dir = figure_dir if html_dir is None else Path(html_dir).expanduser().resolve()
    html_dir.mkdir(parents=True, exist_ok=True)
    view_dir = (html_dir / FULL_RESOLUTION_VIEW_DIRNAME if support_dir is None else Path(support_dir).absolute())
    output_file = html_dir / COMPARISON_VIEWERS[comparison_type]["output_name"]
    selected_plots = [plot for plot in plots if plot.comparison_type == comparison_type]
    # Render the overview against the actual support directories before writing it.
    html = render_comparison_view_html(
        comparison_type,
        selected_plots,
        height_pairs,
        document_dir=html_dir,
        support_dir=view_directories or view_dir,
    )
    if support_dir is not None:
        links = ' '.join(f'<a href="{spec["output_name"]}">{escape(spec["title"])}</a>'
                         for spec in COMPARISON_VIEWERS.values())
        html = html.replace('<body>', '<body><nav aria-label="Comparison galleries">' + links + '</nav>', 1)
    output_file.write_text(html, encoding="utf-8")

    view_dir.mkdir(parents=True, exist_ok=True)
    base_view_dir = view_dir
    full_res_files: list[Path] = []
    validation_warnings: list[str] = []
    # Publish or reuse each full-resolution page and collect source-validation warnings.
    for plot in selected_plots:
        view_dir = Path((view_directories or {}).get(plot.path, base_view_dir))
        view_dir.mkdir(parents=True, exist_ok=True)
        height_label = _format_plot_height_label(plot)
        view_file = view_dir / _full_resolution_view_name(plot)
        full_res_files.append(view_file)
        if published_views is not None and view_file in published_views:
            validation_warnings.extend(published_views[view_file])
            continue
        navigation_targets = build_subplot_navigation_targets(
            plot,
            COMPARISON_VIEWERS[comparison_type]["title"],
            height_label,
            figure_dir=figure_dir,
        )
        # Create durable individual targets before validating and rendering browser
        # URLs.
        publish_subplot_pages(plot, navigation_targets, view_dir)
        validation_warnings.extend(validate_subplot_navigation_targets(plot, navigation_targets, figure_dir))
        for target in navigation_targets:
            source_file = target.get("sourceFile")
            if source_file and not target.get("missing", False):
                target["src"] = _relative_image_src(Path(source_file), view_dir)
            for row in target.get("comparisonRows", []):
                source_path = row.get("sourcePath")
                if source_path:
                    row["src"] = _relative_image_src(Path(row.get("sourceFile", figure_dir / source_path)), view_dir)
        write_launch_bridge(view_dir)
        view_html = render_full_resolution_view_html(
            plot,
            COMPARISON_VIEWERS[comparison_type]["title"],
            height_label,
            figure_dir=figure_dir,
            navigation_targets=navigation_targets,
            document_dir=view_dir,
        )
        view_file.write_text(view_html, encoding="utf-8")
        if published_views is not None:
            published_views[view_file] = validate_subplot_navigation_targets(plot, navigation_targets, figure_dir)

    # Write the complete warning log and limit console output for large galleries.
    warning_log = base_view_dir / f"{comparison_type}_subplot_link_warnings.log"
    if len(validation_warnings) == 0:
        warning_log.write_text("No subplot link warnings.\n", encoding="utf-8")
    else:
        warning_log.write_text("\n".join(validation_warnings) + "\n", encoding="utf-8")
        for warning in validation_warnings[:25]:
            print(f"Warning: {warning}")
        if len(validation_warnings) > 25:
            print(f"Warning: {len(validation_warnings) - 25} additional subplot link warning(s) written to {warning_log}")

    return {
        "comparison_type": comparison_type,
        "output_file": output_file,
        "plot_count": len(selected_plots),
        "full_resolution_output_files": full_res_files,
        "subplot_link_warning_count": len(validation_warnings),
        "subplot_link_warning_log": warning_log,
    }


def write_default_comparison_viewers(
    figure_dir: str | Path,
    html_dir: str | Path | None = None,
    *,
    scope: str | Path | None = None,
) -> dict[str, dict[str, object]]:
    '''
    Purpose
    -------
    Discover comparison plots and publish the configured default gallery set.

    Inputs
    ------
    figure_dir: str or Path or None
        Root of source figure discovery; builders default to the comparison
        image parent when None.

    html_dir: str or Path or None
        Gallery HTML destination; None selects the function's managed/default
        location.

    scope: str or Path or None
        Managed figure-output scope; cannot be combined with an explicit legacy
        html_dir.

    Outputs
    -------
    publications: dict
        Per-comparison publication records, or the managed scoped-publisher
        result when operating in a managed figure tree.
    '''

    # Route managed figure trees through the scoped publisher while retaining legacy
    # output support.
    from figure_locations import canonical_figure_root
    from html_output_paths import is_managed_figure_root, write_scoped_comparison_viewers
    figure_dir=canonical_figure_root(figure_dir)
    if scope is not None and html_dir is not None:
        raise ValueError('Managed scope and an explicit legacy HTML directory cannot be combined.')
    if html_dir is None and (scope is not None or is_managed_figure_root(figure_dir)):
        return write_scoped_comparison_viewers(figure_dir, scope=scope)
    # Discover the shared comparison/height ordering once for the legacy gallery set.
    plots = discover_comparison_plots(figure_dir)
    height_pairs = comparison_height_pairs(plots)

    return {
        comparison_type: write_comparison_viewer(
            figure_dir,
            comparison_type,
            plots,
            height_pairs,
            html_dir=html_dir,
        )
        for comparison_type in COMPARISON_VIEWERS
    }
