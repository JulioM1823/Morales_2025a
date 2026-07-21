"""Static HTML galleries for comparison-plot outputs.

This notebook cell inlines the former standalone gallery module so batch plots
can generate their HTML viewers without importing a separate module.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import importlib.util
import json
from pathlib import Path
import re
import struct
from typing import Any, Iterable
from urllib.parse import quote


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
    """Load the shared output-path helper without relying on sys.path state."""

    global _OUTPUT_PATHS_MODULE
    if _OUTPUT_PATHS_MODULE is not None:
        return _OUTPUT_PATHS_MODULE

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

    spec = importlib.util.spec_from_file_location("comparison_gallery_output_paths", module_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _OUTPUT_PATHS_MODULE = module
    return module


@dataclass(frozen=True)
class ComparisonPlot:
    """Metadata for one discovered comparison plot."""

    comparison_type: str
    path: Path
    relative_src: str
    h1_km: float
    h2_km: float
    width: int | None
    height: int | None
    xcorr_geometry: str = "annulus"

    @property
    def height_pair(self) -> tuple[float, float]:
        return (self.h1_km, self.h2_km)

    @property
    def geometry_label(self) -> str:
        return XCORR_DIRECTIONAL_GEOMETRIES.get(self.xcorr_geometry, "")


@dataclass(frozen=True)
class ComparisonPlotNameParts:
    """Parsed fields encoded in a comparison plot filename."""

    comparison_type: str
    observable: str
    h1_token: str
    h2_token: str
    tail: str


def format_height_km(value: float) -> str:
    """Format a height value for compact, deterministic labels."""

    if abs(value - round(value)) < 1.0e-9:
        return str(int(round(value)))

    return f"{value:g}"


def format_height_pair(height_pair: tuple[float, float]) -> str:
    """Return a human-readable height-pair label."""

    return f"{format_height_km(height_pair[0])}-{format_height_km(height_pair[1])} km"


def _parse_height_token(token: str) -> float:
    return float(token.replace("_", "."))


def _height_sort_key(height_pair: tuple[float, float]) -> tuple[float, float]:
    return (float(height_pair[0]), float(height_pair[1]))


def _comparison_filename_pattern(comparison_type: str) -> re.Pattern[str]:
    return re.compile(
        rf"^{re.escape(comparison_type)}_"
        r"(?P<observable>[a-zA-Z0-9]+)_"
        r"(?P<h1>\d+(?:_\d+)?)km_"
        r"(?P<h2>\d+(?:_\d+)?)km_"
    )


def read_image_size(image_path: Path) -> tuple[int, int] | tuple[None, None]:
    """Read PNG or JPEG dimensions without importing image-processing packages."""

    image_path = Path(image_path)
    try:
        with image_path.open("rb") as handle:
            header = handle.read(24)
            if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR":
                width, height = struct.unpack(">II", header[16:24])
                return int(width), int(height)

            if header[:2] != b"\xff\xd8":
                return None, None

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
    except OSError:
        return None, None


def _parse_comparison_plot_name(plot: ComparisonPlot) -> ComparisonPlotNameParts | None:
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
    tail = str(tail).strip("_").lower()
    if tail == "":
        return "annulus"

    last_token = tail.rsplit("_", 1)[-1]
    if last_token in XCORR_DIRECTIONAL_GEOMETRIES:
        return last_token

    return "annulus"


def _strip_xcorr_geometry_suffix(value: str) -> str:
    value = str(value).strip("_")
    geometry = _extract_xcorr_geometry_from_tail(value)
    if geometry == "annulus":
        return value

    suffix = f"_{geometry}"
    return value[: -len(suffix)] if value.lower().endswith(suffix) else value


def _format_plot_height_label(plot: ComparisonPlot) -> str:
    height_label = format_height_pair(plot.height_pair)
    if plot.geometry_label == "":
        return height_label

    return f"{height_label} - {plot.geometry_label}"


def _split_case_and_processing_tail(tail: str) -> tuple[str, str]:
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
    cases: list[str] = []
    for match in FIELD_STRENGTH_CASE_RE.finditer(case_part):
        component = match.group(1)
        strength_tokens = re.findall(r"\d+(?:_\d+)?g", match.group(2))
        cases.extend(f"{component}_{strength_token}" for strength_token in strength_tokens)

    return cases


def _parse_field_orientation_cases(case_part: str) -> list[str]:
    component_by_orientation = {"h": "hx", "v": "vx"}
    return [
        f"{component_by_orientation[match.group(1)]}_{match.group(2)}"
        for match in FIELD_ORIENTATION_CASE_RE.finditer(case_part)
    ]


def _comparison_cases_and_processing(plot: ComparisonPlot) -> tuple[ComparisonPlotNameParts | None, list[str], str]:
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
    path = Path(path).expanduser().resolve()
    if figure_dir is None:
        return f"../{quote(path.name)}"

    figure_dir = Path(figure_dir).expanduser().resolve()
    try:
        relative_path = path.relative_to(figure_dir)
    except ValueError:
        relative_path = Path(path.name)

    return quote(f"../{relative_path.as_posix()}")


def _build_image_stem_index(figure_dir: Path) -> dict[str, list[Path]]:
    figure_dir = Path(figure_dir).expanduser().resolve()
    index: dict[str, list[Path]] = {}
    if not figure_dir.exists():
        return index

    for path in sorted(figure_dir.rglob("*"), key=lambda candidate: candidate.relative_to(figure_dir).as_posix()):
        if (
            path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and FULL_RESOLUTION_VIEW_DIRNAME not in path.relative_to(figure_dir).parts
        ):
            index.setdefault(path.stem, []).append(path)

    return index


def _clean_source_image_stem(stem: str) -> str:
    output_paths = _load_output_paths_module()
    if output_paths is None or not hasattr(output_paths, "clean_output_filename"):
        return stem

    return Path(output_paths.clean_output_filename(f"{stem}.jpeg")).stem


def _product_directory_for_panel(panel_kind: str) -> str:
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
    if isinstance(source_stems, str):
        source_stems = [source_stems]

    suffixes_by_kind = {
        "komega": ("_komega",),
        "xc": ("_xc",),
        "phase_diff": ("_phase_diff",),
    }

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
    if source_index is not None and stem in source_index:
        candidates = [
            candidate
            for candidate in source_index[stem]
            if _candidate_matches_panel(candidate, panel_kind)
        ]
        if len(candidates) == 0:
            return None
        return sorted(candidates, key=lambda candidate: _candidate_rank(candidate, panel_kind, stem))[0]

    for extension in IMAGE_EXTENSIONS:
        candidate = Path(figure_dir) / f"{stem}{extension}"
        if candidate.exists() and _candidate_matches_panel(candidate, panel_kind):
            return candidate
    return None


def _candidate_matches_panel(path: Path, panel_kind: str) -> bool:
    stem = path.stem.lower()
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
    for source_stem in _candidate_source_image_stems(source_stems, panel_kind):
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
    filter_slug = _filter_slug_from_processing(processing_slug)
    if filter_slug == "" or filter_slug == "unfiltered":
        return None

    xcorr_geometry = _extract_xcorr_geometry_from_tail(processing_slug)
    source_prefix = f"{case_prefix}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_"
    required_fragment = f"_gaussian_filter_{filter_slug}"
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
    base = f"{case_prefix}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km"
    return base if processing_slug == "" else f"{base}_{processing_slug}"


def _source_stems_for_panel(
    comparison_type: str,
    case_prefix: str,
    parts: ComparisonPlotNameParts,
    processing_slug: str,
    panel_kind: str,
) -> list[str]:
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
    path = Path(path).expanduser().resolve()
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
    if path is None:
        return {
            "src": "",
            "sourcePath": "",
            "alt": label,
            "missing": True,
            "expected": expected,
        }

    return {
        "src": _quoted_parent_image_src(path, figure_dir),
        "sourcePath": _relative_source_path(path, figure_dir),
        "sourceFile": str(path.expanduser().resolve()),
        "alt": label,
        "missing": False,
        "expected": expected,
    }


def _fallback_bands(size: int, expected_count: int) -> list[tuple[int, int]]:
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
    if expected_count <= 0 or len(segments) >= expected_count:
        return segments[:expected_count]
    if len(segments) == 0:
        return segments

    expanded = list(segments)
    while len(expanded) < expected_count:
        widths = [stop - start + 1 for start, stop in expanded]
        widest_index = max(range(len(expanded)), key=lambda index: widths[index])
        widest_start, widest_stop = expanded.pop(widest_index)
        parts = min(expected_count - len(expanded), max(2, round(widths[widest_index]/max(1.0, min(widths)))))
        split_points = [
            int(round(widest_start + (widest_stop - widest_start + 1)*part/parts))
            for part in range(parts + 1)
        ]
        split_segments = [
            (split_points[part], max(split_points[part], split_points[part + 1] - 1))
            for part in range(parts)
        ]
        expanded[widest_index:widest_index] = split_segments

    return expanded[:expected_count]


def _projection_segments(
    mask: Any,
    axis: int,
    expected_count: int,
    minimum_span: float,
    density_fraction: float = 0.02,
) -> list[tuple[int, int]]:
    import numpy as np

    if axis == 0:
        projection = mask.sum(axis=0)
        threshold = mask.shape[0]*density_fraction
    else:
        projection = mask.sum(axis=1)
        threshold = mask.shape[1]*density_fraction

    indices = np.where(projection > threshold)[0]
    if indices.size == 0:
        return []

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

    mask = (array < 245).any(axis=2)
    height, width = mask.shape
    return mask, int(width), int(height)


def _detect_panel_bands(
    image_path: Path,
    expected_columns: int,
    expected_rows: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], int, int, Any | None]:
    mask, width, height = _load_image_mask(image_path)
    if width <= 0 or height <= 0:
        return [], [], width, height, mask

    if mask is None:
        return (
            _fallback_bands(width, expected_columns),
            _fallback_bands(height, expected_rows),
            width,
            height,
            mask,
        )

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
    if mask is None:
        return _fallback_bands(image_width, expected_columns)

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
    x0, x1 = x_band
    y0, y1 = y_band
    return {
        "left": 100.0*x0/image_width if image_width > 0 else 0.0,
        "top": 100.0*y0/image_height if image_height > 0 else 0.0,
        "width": 100.0*(x1 - x0 + 1)/image_width if image_width > 0 else 0.0,
        "height": 100.0*(y1 - y0 + 1)/image_height if image_height > 0 else 0.0,
    }


def _bounds_pixels(x_band: tuple[int, int], y_band: tuple[int, int]) -> dict[str, int]:
    x0, x1 = x_band
    y0, y1 = y_band
    return {
        "left": int(x0),
        "top": int(y0),
        "width": int(x1 - x0 + 1),
        "height": int(y1 - y0 + 1),
    }


def _target_id(*parts: object) -> str:
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
    source = dict(source)
    crop_bounds = _bounds_pixels(x_band, y_band)

    return {
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


def _expected_panel_description(source_stems: str | Iterable[str], panel_kind: str) -> str:
    candidates = _candidate_source_image_stems(source_stems, panel_kind)
    return ", ".join(candidates)


def _build_field_comparison_targets(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
) -> list[dict[str, Any]]:
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
    match = re.search(r"(?:^|_)filters_(\d+)(?:_|$)", parts.tail)
    return int(match.group(1)) if match is not None else 0


def _parse_gaussian_processing_slugs_from_tail(parts: ComparisonPlotNameParts) -> list[str]:
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
    parsed_slugs = _parse_gaussian_processing_slugs_from_tail(parts)
    if len(parsed_slugs) >= expected_count:
        return parsed_slugs[:expected_count]

    source_prefix = f"{reference_case}_{parts.observable}_{parts.h1_token}km_{parts.h2_token}km_"
    komega_suffix = "_komega_magnetic_orientation_validation"
    processing_slugs = []

    for path in sorted(figure_dir.rglob("*"), key=lambda candidate: candidate.relative_to(figure_dir).as_posix()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if FULL_RESOLUTION_VIEW_DIRNAME in path.relative_to(figure_dir).parts:
            continue
        if not path.stem.startswith(source_prefix) or not path.stem.endswith(komega_suffix):
            continue

        processing_slug = path.stem[len(source_prefix) : -len(komega_suffix)]
        if processing_slug == "unfiltered":
            continue
        processing_slugs.append(processing_slug)

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

    return combined_slugs[:expected_count]


def _build_gaussian_comparison_targets(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
) -> list[dict[str, Any]]:
    parts = _parse_comparison_plot_name(plot)
    if parts is None:
        return []

    case_prefixes = ["z0_0g", "hx_10g", "hx_50g", "hx_100g", "vx_10g", "vx_50g", "vx_100g"]
    filter_count = _extract_gaussian_filter_count(parts)
    if filter_count <= 0:
        return []

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
    """Build clickable subplot targets for a comparison view page."""

    if plot.comparison_type in {"field_strength_comparison", "field_orientation_comparison"}:
        return _build_field_comparison_targets(plot, title, height_label, figure_dir=figure_dir)
    if plot.comparison_type == "gaussian_filter_comparison":
        return _build_gaussian_comparison_targets(plot, title, height_label, figure_dir=figure_dir)
    return []


def resolved_subplot_navigation_targets(targets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [target for target in targets if not target.get("missing", False) and str(target.get("src", "")) != ""]


def _public_navigation_target(target: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in target.items()
        if key not in {"sourceFile", "missing", "expected"}
    }


def _target_panel_kind(target: dict[str, Any]) -> str:
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
    source_path = str(target.get("sourcePath", "")).lower()
    panel_kind = _target_panel_kind(target)
    if source_path == "" or panel_kind == "":
        return True
    if "comparison_" in source_path:
        return False
    if "orientation_validation" in source_path or "magnetic_orientation_validation" in source_path:
        return False
    if panel_kind == "komega":
        return Path(source_path).stem.endswith("_komega")
    if panel_kind == "xc":
        return Path(source_path).stem.endswith("_xc")
    if panel_kind == "phase_diff":
        return Path(source_path).stem.endswith("_phase_diff")
    if panel_kind == "gaussian_filter":
        return "_gaussian_filter_" in Path(source_path).stem

    return True


def validate_subplot_navigation_targets(
    plot: ComparisonPlot,
    targets: Iterable[dict[str, Any]],
    figure_dir: Path,
) -> list[str]:
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

    return warnings


def _json_script_data(data: object) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")


def discover_comparison_plots(
    figure_dir: str | Path,
    comparison_types: Iterable[str] | None = None,
) -> list[ComparisonPlot]:
    """Discover comparison plot images in deterministic filename order."""

    figure_dir = Path(figure_dir).expanduser().resolve()
    selected_types = list(COMPARISON_VIEWERS if comparison_types is None else comparison_types)
    patterns = {
        comparison_type: _comparison_filename_pattern(comparison_type)
        for comparison_type in selected_types
    }

    if not figure_dir.exists():
        return []

    plots: list[ComparisonPlot] = []
    candidates = sorted(
        (
            path
            for path in figure_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and FULL_RESOLUTION_VIEW_DIRNAME not in path.relative_to(figure_dir).parts
        ),
        key=lambda path: path.relative_to(figure_dir).as_posix(),
    )

    for path in candidates:
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

    return sorted(
        plots,
        key=lambda plot: (
            plot.comparison_type,
            _height_sort_key(plot.height_pair),
            plot.path.name,
        ),
    )


def comparison_height_pairs(plots: Iterable[ComparisonPlot]) -> list[tuple[float, float]]:
    """Return the shared deterministic height-pair order for all galleries."""

    height_pairs = {plot.height_pair for plot in plots}
    return sorted(height_pairs, key=_height_sort_key)


def _dimension_attributes(plot: ComparisonPlot) -> str:
    if plot.width is None or plot.height is None:
        return ""

    return f' width="{plot.width}" height="{plot.height}"'


def _full_resolution_view_name(plot: ComparisonPlot) -> str:
    return f"{plot.path.stem}.html"


def _full_resolution_view_href(plot: ComparisonPlot) -> str:
    return f"{FULL_RESOLUTION_VIEW_DIRNAME}/{quote(_full_resolution_view_name(plot))}"


def _render_plot_link(plot: ComparisonPlot, title: str, height_label: str) -> str:
    src = escape(plot.relative_src, quote=True)
    view_href = escape(_full_resolution_view_href(plot), quote=True)
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
    plots_by_height_pair: dict[tuple[float, float], list[ComparisonPlot]] = {}
    for plot in selected_plots:
        plots_by_height_pair.setdefault(plot.height_pair, []).append(plot)

    ordered_plots: list[ComparisonPlot] = []
    ordered_height_pairs = list(height_pairs)
    if len(ordered_height_pairs) == 0:
        ordered_height_pairs = comparison_height_pairs(selected_plots)

    for height_pair in ordered_height_pairs:
        ordered_plots.extend(sorted(plots_by_height_pair.get(height_pair, []), key=lambda plot: plot.path.name))

    return ordered_plots


def render_full_resolution_view_html(
    plot: ComparisonPlot,
    title: str,
    height_label: str,
    figure_dir: Path | None = None,
    navigation_targets: Iterable[dict[str, Any]] | None = None,
) -> str:
    """Render a minimal, borderless full-resolution inspection page."""

    figure_dir = Path(plot.path.parent if figure_dir is None else figure_dir).expanduser().resolve()
    src = escape(_quoted_parent_image_src(plot.path, figure_dir), quote=True)
    alt_text = escape(f"{title}: {height_label}", quote=True)
    dimension_attributes = _full_resolution_dimension_attributes(plot)
    frame_style = ""
    if plot.width is not None and plot.height is not None:
        frame_style = f' style="width: {plot.width}px; height: {plot.height}px;"'
    if navigation_targets is None:
        navigation_targets = build_subplot_navigation_targets(plot, title, height_label, figure_dir=figure_dir)
    navigation_targets = resolved_subplot_navigation_targets(navigation_targets)
    navigation_targets = [_public_navigation_target(target) for target in navigation_targets]
    rendered_hotspots = "\n".join(
        (
            f'    <a class="subplot-hotspot" href="{escape(str(target["src"]), quote=True)}" '
            f'data-nav-target="{escape(str(target["id"]), quote=True)}" '
            f'data-source-path="{escape(str(target.get("sourcePath", "")), quote=True)}" '
            f'title="{escape(str(target["label"]), quote=True)}" '
            f'aria-label="{escape(str(target["label"]), quote=True)}" '
            f'style="left: {target["bounds"]["left"]:.6f}%; '
            f'top: {target["bounds"]["top"]:.6f}%; '
            f'width: {target["bounds"]["width"]:.6f}%; '
            f'height: {target["bounds"]["height"]:.6f}%;"></a>'
        )
        for target in navigation_targets
    )
    targets_json = _json_script_data(navigation_targets)
    overview_json = _json_script_data(
        {
            "id": "overview",
            "label": f"{title}: {height_label}",
            "src": _quoted_parent_image_src(plot.path, figure_dir),
            "sourcePath": plot.path.name,
            "alt": f"{title}: {height_label}",
            "crop": None,
        }
    )

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
  </style>
</head>
<body>
  <div class="figure-frame is-overview"{frame_style} data-figure-frame>
    <img data-full-resolution-image src="{src}" alt="{alt_text}"{dimension_attributes}>
    <div class="subplot-map" aria-label="{escape(title)} subplot navigation">
{rendered_hotspots}
    </div>
  </div>
  <script>
    (() => {{
      const overview = {overview_json};
      const targets = {targets_json};
      const targetById = new Map(targets.map((target) => [target.id, target]));
      const frame = document.querySelector("[data-figure-frame]");
      const image = document.querySelector("[data-full-resolution-image]");
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
        image.alt = nextView.alt || nextView.label || overview.alt;
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

        event.preventDefault();
        const viewId = link.getAttribute("data-nav-target");
        if (pointerStart !== null && pointerStart.id === viewId) {{
          const dx = event.clientX - pointerStart.x;
          const dy = event.clientY - pointerStart.y;
          if (Math.hypot(dx, dy) > 6) {{
            pointerStart = null;
            return;
          }}
        }}

        pointerStart = null;
        showView(viewId, true);
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

        event.preventDefault();
        applyScale(scale * Math.exp(-event.deltaY * 0.002), event.clientX, event.clientY);
      }}, {{ passive: false }});

      window.addEventListener("gesturestart", (event) => {{
        event.preventDefault();
        gestureStartScale = scale;
      }}, {{ passive: false }});

      window.addEventListener("gesturechange", (event) => {{
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
) -> str:
    """Render one standalone comparison gallery."""

    if comparison_type not in COMPARISON_VIEWERS:
        raise ValueError(f"Unsupported comparison gallery type: {comparison_type}")

    viewer_config = COMPARISON_VIEWERS[comparison_type]
    title = viewer_config["title"]
    selected_plots = [plot for plot in plots if plot.comparison_type == comparison_type]
    ordered_plots = _ordered_gallery_plots(selected_plots, height_pairs)
    rendered_figures = "\n".join(
        _render_plot_link(plot, title, _format_plot_height_label(plot))
        for plot in ordered_plots
    )
    if rendered_figures == "":
        rendered_figures = '<p>No comparison plots found.</p>'

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
) -> dict[str, object]:
    """Write one comparison gallery HTML file."""

    figure_dir = Path(figure_dir).expanduser().resolve()
    figure_dir.mkdir(parents=True, exist_ok=True)
    output_file = figure_dir / COMPARISON_VIEWERS[comparison_type]["output_name"]
    selected_plots = [plot for plot in plots if plot.comparison_type == comparison_type]
    html = render_comparison_view_html(comparison_type, selected_plots, height_pairs)
    output_file.write_text(html, encoding="utf-8")

    view_dir = figure_dir / FULL_RESOLUTION_VIEW_DIRNAME
    view_dir.mkdir(parents=True, exist_ok=True)
    full_res_files: list[Path] = []
    validation_warnings: list[str] = []
    for plot in selected_plots:
        height_label = _format_plot_height_label(plot)
        view_file = view_dir / _full_resolution_view_name(plot)
        full_res_files.append(view_file)
        navigation_targets = build_subplot_navigation_targets(
            plot,
            COMPARISON_VIEWERS[comparison_type]["title"],
            height_label,
            figure_dir=figure_dir,
        )
        validation_warnings.extend(validate_subplot_navigation_targets(plot, navigation_targets, figure_dir))
        view_html = render_full_resolution_view_html(
            plot,
            COMPARISON_VIEWERS[comparison_type]["title"],
            height_label,
            figure_dir=figure_dir,
            navigation_targets=navigation_targets,
        )
        view_file.write_text(view_html, encoding="utf-8")

    warning_log = view_dir / f"{comparison_type}_subplot_link_warnings.log"
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


def write_default_comparison_viewers(figure_dir: str | Path) -> dict[str, dict[str, object]]:
    """Discover all default comparison plots and write the three gallery viewers."""

    plots = discover_comparison_plots(figure_dir)
    height_pairs = comparison_height_pairs(plots)

    return {
        comparison_type: write_comparison_viewer(
            figure_dir,
            comparison_type,
            plots,
            height_pairs,
        )
        for comparison_type in COMPARISON_VIEWERS
    }
