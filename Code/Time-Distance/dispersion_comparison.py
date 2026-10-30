'''
Purpose
-------
Evaluate authoritative Vesa_2026 wave models for a measured height pair and publish
observed/theory comparison assets.

Observed axes use Mm^-1 and mHz. Solver grids use km^-1 and angular frequency
in rad/s; displayed phase differences use degrees. The configured row order
contains the observed figure and seven model figures.

Authoritative Vesa_2026 dispersion diagrams for k-omega detail views.

This module is deliberately an interface layer.  It owns unit conversion,
height-pair parameter validation, plotting, and manifest generation, while all
dispersion polynomials and root/branch handling remain in Vesa_2026.

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

import copy
import importlib.util
import json
from math import ceil, pi
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.cm import ScalarMappable
from matplotlib.colors import TwoSlopeNorm
import cmasher as cmr
import numpy as np


COMPARISON_ROW_LABELS = (
    "Observed/Simulation k–ω Diagram",
    "3D MAG Wave k–ω Diagram",
    "Alfvén Mode k–ω Diagram",
    "Slow Magnetoacoustic Mode k–ω Diagram",
    "Fast Magnetoacoustic Mode k–ω Diagram",
    "Bunte 1993 k–ω Diagram",
    "MT1982 k–ω Diagram",
    "MT1981 k–ω Diagram",
)

MODEL_SPECS = (
    {
        "model": "nc2009",
        "label": COMPARISON_ROW_LABELS[1],
        "plot_title_tex": r"3D MAG Wave $k$--$\omega$ Diagram",
        "slug": "3d_mag_wave",
        "uses": ("a", "theta", "phi", "dz"),
        "display": ("a", "theta", "phi", "dz", "cs", "g", "N2", "wac"),
    },
    {
        "model": "alfven_mode",
        "label": COMPARISON_ROW_LABELS[2],
        "plot_title_tex": r"Alfv\'en Mode $k$--$\omega$ Diagram",
        "slug": "alfven_mode",
        "uses": ("a", "theta", "phi", "dz"),
        "display": ("a", "theta", "phi", "dz"),
    },
    {
        "model": "slow_mode",
        "label": COMPARISON_ROW_LABELS[3],
        "plot_title_tex": r"Slow Magnetoacoustic Mode $k$--$\omega$ Diagram",
        "slug": "slow_mode",
        "uses": ("a", "theta", "phi", "dz"),
        "display": ("a", "theta", "phi", "dz", "cs"),
    },
    {
        "model": "fast_mode",
        "label": COMPARISON_ROW_LABELS[4],
        "plot_title_tex": r"Fast Magnetoacoustic Mode $k$--$\omega$ Diagram",
        "slug": "fast_mode",
        "uses": ("a", "theta", "phi", "dz"),
        "display": ("a", "theta", "phi", "dz", "cs"),
    },
    {
        "model": "bunte1993",
        "label": COMPARISON_ROW_LABELS[5],
        "plot_title_tex": r"Bunte 1993 $k$--$\omega$ Diagram",
        "slug": "bunte1993",
        "uses": ("a", "dz"),
        "display": ("a", "dz", "cs", "g", "H", "gamma", "tau"),
    },
    {
        "model": "mt1982",
        "label": COMPARISON_ROW_LABELS[6],
        "plot_title_tex": r"MT1982 $k$--$\omega$ Diagram",
        "slug": "mt1982",
        "uses": ("dz",),
        "display": ("dz", "cs", "g", "H", "N2", "gamma", "tau"),
    },
    {
        "model": "mt1981",
        "label": COMPARISON_ROW_LABELS[7],
        "plot_title_tex": r"MT1981 $k$--$\omega$ Diagram",
        "slug": "mt1981",
        "uses": ("dz",),
        "display": ("dz", "cs", "H", "N2"),
    },
)

MODEL_BY_NAME = {spec["model"]: spec for spec in MODEL_SPECS}
FORBIDDEN_CONFIG_OVERRIDES = {
    "a",
    "a_over_cs",
    "ax",
    "ay",
    "az",
    "theta",
    "theta_deg",
    "phi",
    "phi_deg",
    "dz",
}
AUTHORITATIVE_METHODS = (
    "DiagnosticDiagram.omega_solve_grid",
    "DiagnosticDiagram.kz_solve_grid",
    "DiagnosticDiagram.associate_omega_boundaries_with_kz",
    "DiagnosticDiagram.plot_omega_boundaries_for_kz_branch",
    "DiagnosticDiagram.phase_speed",
    "DiagnosticDiagram.phase_difference",
)

_VESA_MODULE_CACHE: dict[str, dict[str, Any]] = {}

PIPELINE_KOMEGA_STYLE = {
    "figsize": (10.0, 6.0),
    "cmap": "cmr.fusion",
    "xlim_Mm_inverse": (0.0, 7.0),
    "ylim_mHz": (0.0, 10.0),
    "panel_box_aspect": 1.55,
    "dpi": 300,
    "use_tex": True,
    "font_family": "serif",
}


def _load_module(module_name: str, file_path: Path):
    '''
    Purpose
    -------
    Execute a Python source file under a supplied import name.

    Inputs
    ------
    module_name: str
        Import name assigned to the dynamically loaded Python module.

    file_path: Path
        Python source file to execute as a module.

    Outputs
    -------
    module: module
        Loaded module object; an unavailable specification/loader raises
        ImportError, and execution errors propagate.
    '''

    # Execute the exact source file instead of importing a same-named module from
    # sys.path.
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module specification for {file_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_vesa_2026_modules(config: dict) -> dict[str, Any]:
    '''
    Purpose
    -------
    Load the authoritative Vesa_2026 config and solver modules by path.

    Inputs
    ------
    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    Outputs
    -------
    modules: dict
        Cached config_module/functions_module and their source Paths. Missing
        project configuration or implementation files raise an error.
    '''

    # Require the configured authoritative Vesa project before resolving its
    # implementation files.
    settings = config.get("komega_comparison", {})
    project_dir = settings.get("vesa_2026_dir", "")
    if project_dir in ("", None):
        raise KeyError("komega_comparison['vesa_2026_dir'] is required.")

    project_dir = Path(project_dir).expanduser().resolve()
    module_dir = project_dir / "Code" / "diagnostic_diagram"
    config_file = module_dir / "config.py"
    functions_file = module_dir / "functions.py"
    for required_file in (config_file, functions_file):
        if not required_file.exists():
            raise FileNotFoundError(f"Required Vesa_2026 implementation not found: {required_file}")

    # Cache the loaded config/solver pair by its resolved module directory.
    cache_key = str(module_dir)
    if cache_key not in _VESA_MODULE_CACHE:
        suffix = len(_VESA_MODULE_CACHE)
        _VESA_MODULE_CACHE[cache_key] = {
            "config_module": _load_module(f"vesa_2026_config_{suffix}", config_file),
            "functions_module": _load_module(f"vesa_2026_functions_{suffix}", functions_file),
            "config_file": config_file,
            "functions_file": functions_file,
            "module_dir": module_dir,
        }

    return _VESA_MODULE_CACHE[cache_key]


def _finite_float(value, default=np.nan) -> float:
    '''
    Purpose
    -------
    Convert a value to a finite float or return the supplied fallback.

    Inputs
    ------
    value: object
        Value converted, formatted, or escaped by this helper.

    default: float
        Fallback returned when numeric conversion fails or the result is
        nonfinite.

    Outputs
    -------
    number: float
        Finite converted value, or default after TypeError/ValueError or nonfinite
        input; other conversion errors propagate.
    '''

    # Use the supplied fallback for failed conversions and nonfinite numeric values.
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(default)
    return value if np.isfinite(value) else float(default)


def resolve_komega_plot_style(config: dict | None = None) -> dict[str, Any]:
    '''
    Purpose
    -------
    Return the plotting conventions used by plots.ipynb k-omega figures.

    Inputs
    ------
    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    Outputs
    -------
    style: dict
        Copied, normalized defaults plus plot-style overrides and phase limits.
        Malformed limits or a non-centered phase scale raise ValueError.
    '''

    # Copy notebook-compatible defaults before applying local style overrides.
    config = {} if config is None else config
    settings = config.get("komega_comparison", {})
    style = copy.deepcopy(PIPELINE_KOMEGA_STYLE)
    style.update(copy.deepcopy(settings.get("plot_style", {})))
    # Normalize the centered phase-color range and figure/axis settings.
    phase_limits = settings.get("phase_limits_deg", [-80.0, 80.0])
    if not isinstance(phase_limits, (list, tuple, np.ndarray)) or len(phase_limits) != 2:
        raise ValueError("komega_comparison['phase_limits_deg'] must contain [vmin, vmax].")
    style["vmin_deg"] = float(phase_limits[0])
    style["vmax_deg"] = float(phase_limits[1])
    style["figsize"] = tuple(float(value) for value in style["figsize"])
    style["xlim_Mm_inverse"] = tuple(float(value) for value in style["xlim_Mm_inverse"])
    style["ylim_mHz"] = tuple(float(value) for value in style["ylim_mHz"])
    style["panel_box_aspect"] = float(style["panel_box_aspect"])
    style["dpi"] = int(style["dpi"])
    style["use_tex"] = bool(style["use_tex"])
    # Validate centered phase limits and finite increasing physical display intervals.
    if not style["vmin_deg"] < 0.0 < style["vmax_deg"]:
        raise ValueError("The k-omega phase limits must straddle zero.")
    for limits_name in ("xlim_Mm_inverse", "ylim_mHz"):
        limits = style[limits_name]
        if len(limits) != 2 or not np.all(np.isfinite(limits)) or limits[0] >= limits[1]:
            raise ValueError(f"Invalid k-omega plot limits: {limits_name}={limits!r}.")
    return style


def _resolve_komega_cmap(cmap_value=None):
    '''
    Purpose
    -------
    Resolve the pipeline's CMasher fusion map and optional overrides.

    Inputs
    ------
    cmap_value: str or Colormap or None
        Optional colormap override; None/empty/fusion aliases resolve to CMasher
        fusion.

    Outputs
    -------
    cmap: Colormap or object
        CMasher fusion for default aliases, registered Matplotlib colormap for a
        name, or the supplied nonstring object.
    '''

    # Resolve default fusion aliases before looking up named Matplotlib colormaps.
    if cmap_value in (None, "", "fusion", "cmr.fusion"):
        return cmr.fusion
    if isinstance(cmap_value, str):
        return matplotlib.colormaps.get_cmap(cmap_value)
    return cmap_value


def _komega_rc_settings(style: dict[str, Any]) -> dict[str, Any]:
    '''
    Purpose
    -------
    Select Matplotlib text and font settings for a local plotting context.

    Inputs
    ------
    style: dict
        Resolved figure dimensions, phase limits in degrees, axis limits, fonts,
        and render settings.

    Outputs
    -------
    settings: dict
        text.usetex and font.family entries derived from the resolved style.
    '''

    # Limit local rc overrides to the configured TeX and font settings.
    return {
        "text.usetex": bool(style["use_tex"]),
        "font.family": str(style["font_family"]),
    }


def _latex_escape_text(value: Any) -> str:
    '''
    Purpose
    -------
    Escape non-mathematical text embedded in a LaTeX-rendered title.

    Inputs
    ------
    value: object
        Value converted, formatted, or escaped by this helper.

    Outputs
    -------
    text: str
        Input text with LaTeX-reserved characters escaped for a non-math title.
    '''

    # Escape literal text character by character without treating it as a math
    # expression.
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def _two_values(metadata: dict, nested_key: str, first_key: str, second_key: str) -> list[float]:
    '''
    Purpose
    -------
    Read two finite layer values from grouped metadata or scalar fallback keys.

    Inputs
    ------
    metadata: dict
        Height-pair metadata containing optional grouped or scalar values.

    nested_key: str
        Key for a two-element list/tuple/array preferred over scalar fallback
        fields.

    first_key: str
        Fallback key for the first layer value.

    second_key: str
        Fallback key for the second layer value.

    Outputs
    -------
    pair: list of float
        First two grouped entries when available, otherwise converted scalar
        fallback entries; invalid values become NaN.
    '''

    # Prefer grouped layer values when at least two entries are available.
    values = metadata.get(nested_key, [])
    if isinstance(values, (list, tuple, np.ndarray)) and len(values) >= 2:
        return [_finite_float(values[0]), _finite_float(values[1])]
    return [_finite_float(metadata.get(first_key)), _finite_float(metadata.get(second_key))]


def circular_mean_degrees(values) -> float:
    '''
    Purpose
    -------
    Compute a finite-sample circular mean of signed angles.

    Inputs
    ------
    values: array-like
        Angle samples in degrees; nonfinite entries are ignored.

    Outputs
    -------
    mean_deg: float
        atan2(mean sine, mean cosine) in degrees; NaN for no finite data or
        resultant magnitude <= 1e-12.
    '''

    # Discard nonfinite samples before averaging their unit-circle components.
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan
    radians = np.deg2rad(values)
    mean_sin = float(np.mean(np.sin(radians)))
    mean_cos = float(np.mean(np.cos(radians)))
    # Leave the mean undefined when the angular resultant cancels.
    if np.hypot(mean_sin, mean_cos) <= 1.0e-12:
        return np.nan
    return float(np.rad2deg(np.arctan2(mean_sin, mean_cos)))


def resolve_height_pair_context(
    config: dict,
    pair_metadata: dict | None = None,
    *,
    allow_standalone_fallback: bool = False,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Resolve and validate representative physical inputs for a dataset height pair.

    Inputs
    ------
    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    pair_metadata: dict or None
        Dataset-specific layer heights (km), Alfvén speeds (km/s), orientations
        (deg), or atmospheric initialization metadata.

    allow_standalone_fallback: bool
        Permit notebook-only configured pair values when direct layer metadata
        is unavailable.

    Outputs
    -------
    context: dict
        Layer/pair Alfvén speeds (km/s), magnetic orientations (deg), physical
        separation/heights (km), source descriptions, and fallback/zero-field
        flags. Atmospheric initialization records take precedence;
        invalid/missing required physical inputs raise ValueError.
    '''

    # Copy dataset metadata and inspect any source-matched atmospheric initialization.
    data = config.get("data", {})
    standalone = config.get("komega_comparison", {}).get("standalone_pair", {})
    pair_metadata = {} if pair_metadata is None else copy.deepcopy(pair_metadata)
    from atmospheric_profiles import resolve_parameters
    atmosphere = pair_metadata.get('atmospheric_parameters') or resolve_parameters(config)
    # Use the resolved atmospheric initialization and disclose any model fallbacks.
    if atmosphere is not None:
        from atmospheric_profiles import upgrade_atmosphere
        atmosphere = upgrade_atmosphere(atmosphere)
        from komega_bokeh_context import atmospheric_initializations
        initializations, fallbacks = atmospheric_initializations(config, atmosphere, use_project_fallbacks=True)
        atmosphere = copy.deepcopy(atmosphere)
        atmosphere.update(initializations=initializations, fallbacks=fallbacks)
        values = initializations['nc2009']
        heights = atmosphere.get('height_pair_km', [])
        return dict(height_values_km=heights, a_by_height_km_s=[],
            a_km_s=values['a'], a_source=atmosphere.get('parameter_sources', {}).get('a', 'disclosed model fallback'),
            theta_by_height_deg=[], theta_deg=values['theta_deg'], theta_source='height-integrated unit-vector direction or disclosed fallback',
            phi_by_height_deg=[], phi_deg=values['phi_deg'], phi_source='height-integrated unit-vector direction or disclosed fallback',
            dz_km=values['dz'], dz_source='selected physical cube-layer separation',
            standalone_fallback_used=False, angles_available=True,
            zero_field=bool(values['a'] <= 1e-14), angle_note='',
            theta_convention='inclination from +z', phi_convention='atan2(By,Bx), +x toward +y',
            dz_convention='absolute physical layer separation', atmospheric_parameters=atmosphere)
    # Merge explicit pair metadata before reading per-layer physical inputs.
    nested = pair_metadata.get("dispersion_height_pair", {})
    if isinstance(nested, dict) and nested:
        merged_metadata = copy.deepcopy(pair_metadata)
        merged_metadata.update(copy.deepcopy(nested))
        pair_metadata = merged_metadata

    # Resolve two layer values for Alfvén speed, direction, and physical height.
    a_by_height = _two_values(
        pair_metadata,
        "a_by_height_km_s",
        "a_h1_km_s",
        "a_h2_km_s",
    )
    theta_by_height = _two_values(
        pair_metadata,
        "theta_by_height_deg",
        "theta_mean_h1_deg",
        "theta_mean_h2_deg",
    )
    phi_by_height = _two_values(
        pair_metadata,
        "phi_by_height_deg",
        "phi_mean_h1_deg",
        "phi_mean_h2_deg",
    )
    height_values_km = _two_values(
        pair_metadata,
        "height_values_km",
        "h1_km",
        "h2_km",
    )
    if not np.all(np.isfinite(height_values_km)):
        height_values_km = [
            _finite_float(data.get("resolved_h1_km")),
            _finite_float(data.get("resolved_h2_km")),
        ]

    # Prefer independently calculated layer speeds over standalone representative
    # values.
    layer_a_available = bool(np.all(np.isfinite(a_by_height)))
    fallback_used = False
    if layer_a_available:
        if np.any(np.asarray(a_by_height) < 0.0):
            raise ValueError("Layer Alfven speeds must be nonnegative.")
        a_km_s = float(np.mean(a_by_height))
        configured_a = _finite_float(pair_metadata.get("a_km_s"))
        if np.isfinite(configured_a) and not np.isclose(
            configured_a,
            a_km_s,
            rtol=1.0e-10,
            atol=1.0e-12,
        ):
            raise ValueError("Stored pair a does not equal the arithmetic mean of the two layer values.")
        a_source = "arithmetic mean of the two dataset layer values"
    # Permit configured representative values only through the explicit standalone path.
    elif allow_standalone_fallback:
        a_km_s = _finite_float(pair_metadata.get("a_km_s"))
        a_source = "dataset pair metadata"
        if not np.isfinite(a_km_s):
            a_km_s = _finite_float(standalone.get("a_km_s"))
            a_source = "config komega_comparison.standalone_pair"
            fallback_used = True
        if not np.isfinite(a_km_s) or a_km_s < 0.0:
            raise ValueError(
                "Set komega_comparison['standalone_pair']['a_km_s'] to a finite "
                "nonnegative value for standalone notebook plots."
            )
    else:
        raise ValueError(
            "The detailed k-omega comparison requires Alfven speeds calculated "
            "independently at both atmospheric layers."
        )

    # Separate zero-field direction conventions from finite-field angle requirements.
    zero_field = bool(np.isclose(a_km_s, 0.0, rtol=0.0, atol=1.0e-14))
    layer_angles_available = bool(
        np.all(np.isfinite(theta_by_height)) and np.all(np.isfinite(phi_by_height))
    )
    # Average layer unit vectors so angular wraparound is handled geometrically.
    if layer_angles_available:
        from vesa_support import support_module
        geometry = support_module('magnetic_geometry')
        direction = np.mean(geometry.components(1., theta_by_height, phi_by_height), axis=1)
        if np.linalg.norm(direction) <= 1e-12 and not zero_field:
            raise ValueError('Layer magnetic directions cancel; no unique representative orientation.')
        _, theta, phi = geometry.orientation(*direction) if not zero_field else (0., 0., 0.)
        theta_deg, phi_deg = float(theta), float(phi)
        theta_source = "direction of the mean of the two layer unit vectors"
        phi_source = "atan2 of the mean layer unit vector, relative to +x"
        angle_note = ""
    elif allow_standalone_fallback:
        theta_deg = _finite_float(pair_metadata.get("theta_deg"))
        phi_deg = _finite_float(pair_metadata.get("phi_deg"))
        theta_source = "dataset pair metadata"
        phi_source = "dataset pair metadata"
        if not np.isfinite(theta_deg):
            theta_deg = _finite_float(standalone.get("theta_deg"))
            theta_source = "config komega_comparison.standalone_pair"
            fallback_used = True
        if not np.isfinite(phi_deg):
            phi_deg = _finite_float(standalone.get("phi_deg"))
            phi_source = "config komega_comparison.standalone_pair"
            fallback_used = True
        if (not np.isfinite(theta_deg) or not np.isfinite(phi_deg)) and not zero_field:
            raise ValueError(
                "Set finite theta_deg and phi_deg values in "
                "komega_comparison['standalone_pair'] for standalone notebook plots."
            )
        if not np.isfinite(theta_deg) or not np.isfinite(phi_deg):
            theta_deg = 0.0
            phi_deg = 0.0
            theta_source = "solver-neutral zero-field value"
            phi_source = "solver-neutral zero-field value"
            angle_note = (
                r"magnetic direction undefined at $a=0$; "
                r"solver-neutral $0\,\mathrm{rad}$ representative"
            )
        else:
            angle_note = ""
    else:
        if not zero_field:
            raise ValueError(
                "Nonzero-field dispersion models require theta and phi at both atmospheric layers."
            )
        theta_deg = 0.0
        phi_deg = 0.0
        theta_source = "solver-neutral zero-field value"
        phi_source = "solver-neutral zero-field value"
        angle_note = (
            r"magnetic direction undefined at $a=0$; "
            r"solver-neutral $0\,\mathrm{rad}$ representative"
        )
    # Record direction availability before resolving the absolute physical layer
    # separation.
    angles_available = bool(np.isfinite(theta_deg) and np.isfinite(phi_deg))

    # Prefer verified physical heights and reject contradictory stored separations.
    dz_km = _finite_float(pair_metadata.get("dz_km"))
    dz_source = "dataset pair metadata"
    if np.all(np.isfinite(height_values_km)):
        height_dz_km = abs(float(height_values_km[1]) - float(height_values_km[0]))
        if np.isfinite(dz_km) and not np.isclose(dz_km, height_dz_km, rtol=1.0e-10, atol=1.0e-9):
            raise ValueError("Stored dz does not match the physical separation of the two layers.")
        dz_km = height_dz_km
        dz_source = "absolute separation of the two dataset heights"
    elif not np.isfinite(dz_km):
        dz_km = _finite_float(data.get("resolved_delta_z_km"))
        dz_source = "runtime resolved_delta_z_km"
    if not np.isfinite(dz_km) and allow_standalone_fallback:
        dz_km = _finite_float(data.get("paired_cubes", {}).get("delta_z_km"))
        dz_source = "dataset configuration delta_z_km"
    if not np.isfinite(dz_km) and allow_standalone_fallback:
        dz_km = _finite_float(standalone.get("dz_km"))
        dz_source = "config komega_comparison.standalone_pair"
        fallback_used = True
    if not np.isfinite(dz_km) or dz_km < 0.0:
        message = "A finite nonnegative physical layer separation dz in km is required."
        if allow_standalone_fallback:
            message += " Set komega_comparison['standalone_pair']['dz_km']."
        raise ValueError(message)

    # Return the resolved inputs together with source descriptions and fallback flags.
    return {
        "height_values_km": (
            [float(value) for value in height_values_km]
            if np.all(np.isfinite(height_values_km))
            else []
        ),
        "a_by_height_km_s": (
            [float(value) for value in a_by_height]
            if layer_a_available
            else []
        ),
        "a_km_s": a_km_s,
        "a_source": a_source,
        "theta_by_height_deg": (
            [float(value) for value in theta_by_height]
            if layer_angles_available
            else []
        ),
        "theta_deg": theta_deg,
        "theta_source": theta_source,
        "phi_by_height_deg": (
            [float(value) for value in phi_by_height]
            if layer_angles_available
            else []
        ),
        "phi_deg": float(phi_deg),
        "phi_source": phi_source,
        "dz_km": float(dz_km),
        "dz_source": dz_source,
        "standalone_fallback_used": bool(fallback_used),
        "angles_available": angles_available,
        "zero_field": zero_field,
        "angle_note": angle_note,
        "theta_convention": "inclination from +z",
        "phi_convention": "azimuth atan2(By, Bx), +x toward +y",
        "dz_convention": "absolute physical layer separation",
    }


def _model_project_overrides(config: dict, model_name: str) -> dict[str, Any]:
    '''
    Purpose
    -------
    Copy permitted model overrides while protecting dataset-specific pair inputs.

    Inputs
    ------
    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    model_name: str
        Supported model key from MODEL_SPECS.

    Outputs
    -------
    overrides: dict
        Independent model parameter overrides; replacing field
        strength/orientation/separation inputs raises ValueError.
    '''

    # Copy model overrides and reject attempts to replace dataset-specific pair inputs.
    model_settings = config.get("komega_comparison", {}).get("models", {}).get(model_name, {})
    params = copy.deepcopy(model_settings.get("params", {}))
    forbidden = sorted(FORBIDDEN_CONFIG_OVERRIDES.intersection(params))
    if forbidden:
        raise ValueError(
            f"Height-pair parameters may not be overridden for {model_name}: {', '.join(forbidden)}"
        )
    return params


def resolve_model_parameters(
    config: dict,
    model_name: str,
    pair_context: dict,
    vesa_modules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Merge project parameters into Vesa defaults, then apply pair values.

    Inputs
    ------
    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    model_name: str
        Supported model key from MODEL_SPECS.

    pair_context: dict
        Validated height-pair context with dz_km, a_km_s, theta_deg, phi_deg,
        and optional atmospheric initialization data.

    vesa_modules: dict or None
        Preloaded authoritative Vesa modules/path metadata; None loads them
        through the configuration.

    Outputs
    -------
    params: dict
        Copied Vesa defaults plus permitted project/atmosphere values and
        validated pair inputs; angles are radians, speeds km/s, heights km.
        Protect model identifiers and root counts from overrides.
    '''

    # Validate model availability before copying authoritative solver defaults.
    if model_name not in MODEL_BY_NAME:
        raise KeyError(f"Unsupported detailed comparison model: {model_name}")
    vesa_modules = load_vesa_2026_modules(config) if vesa_modules is None else vesa_modules
    authoritative_params = vesa_modules["config_module"].params
    if model_name not in authoritative_params:
        raise KeyError(f"Vesa_2026 does not define model {model_name!r}.")

    # Protect model identity/root counts while applying permitted independent overrides.
    params = copy.deepcopy(authoritative_params[model_name])
    protected = {"model", "kz_order", "omega_order"}
    overrides = _model_project_overrides(config, model_name)
    protected_overrides = sorted(protected.intersection(overrides))
    if protected_overrides:
        raise ValueError(
            f"Authoritative solver structure may not be overridden: {', '.join(protected_overrides)}"
        )
    params.update(overrides)
    if "N2" not in params and "N" in params:
        params["N2"] = params["N"]**2
    # Apply source-matched atmospheric initializations before the final pair-specific
    # values.
    atmosphere = pair_context.get('atmospheric_parameters')
    if atmosphere is not None:
        for key, value in atmosphere['initializations'][model_name].items():
            if key not in {'theta_deg', 'phi_deg'}:
                params[key] = value
    params["model"] = model_name
    params["dz"] = float(pair_context["dz_km"])

    # Convert only the field/separation parameters actually consumed by this model.
    model_uses = MODEL_BY_NAME[model_name]["uses"]
    if "a" in model_uses:
        params["a"] = float(pair_context["a_km_s"])
    if "theta" in model_uses:
        params["theta"] = np.deg2rad(float(pair_context["theta_deg"]))
    if "phi" in model_uses:
        params["phi"] = np.deg2rad(float(pair_context["phi_deg"]))
    # Recompute Cartesian magnetic-speed components from the resolved field orientation.
    if model_name == "nc2009":
        a = float(params["a"])
        theta = float(params["theta"])
        phi = float(params["phi"])
        from vesa_support import support_module
        params["ax"], params["ay"], params["az"] = support_module("magnetic_geometry").components(
            a, theta, phi, degrees=False)

    return params


def _sample_axis(axis, maximum_samples: int) -> np.ndarray:
    '''
    Purpose
    -------
    Retain finite unique axis centers and subsample them deterministically.

    Inputs
    ------
    axis: array-like
        One-dimensional coordinate centers in their native axis units.

    maximum_samples: int
        Maximum number of distinct coordinate centers retained in the sampled
        axis.

    Outputs
    -------
    sampled: np.ndarray
        Sorted distinct finite centers in the input units, using evenly spaced
        rounded indices when needed. Empty finite input raises ValueError.
    '''

    # Remove nonfinite/duplicate coordinates before deterministic index subsampling.
    axis = np.asarray(axis, dtype=float)
    axis = axis[np.isfinite(axis)]
    if axis.size == 0:
        raise ValueError("The observed k-omega axis contains no finite samples.")
    axis = np.unique(axis)
    if axis.size <= maximum_samples:
        return axis
    indices = np.unique(np.rint(np.linspace(0, axis.size - 1, maximum_samples)).astype(int))
    return axis[indices]


def build_solver_grid(k_axis, nu_axis, config: dict):
    '''
    Purpose
    -------
    Sample the observed domain and convert it to Vesa_2026 units.

    Inputs
    ------
    k_axis: array-like
        Observed horizontal-wavenumber axis (Mm^-1).

    nu_axis: array-like
        Observed cyclic-frequency axis (mHz).

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    Outputs
    -------
    grid: dict
        Visible finite sampled axes (Mm^-1, mHz), (n_nu, n_k) solver meshes
        (km^-1, rad/s), display limits, and conversion descriptions. Zero
        frequency is excluded; empty visible domains raise ValueError.
    '''

    # Resolve display limits and cap the requested numerical grid dimensions.
    settings = config.get("komega_comparison", {})
    style = resolve_komega_plot_style(config)
    maximum_k = max(2, int(settings.get("max_k_samples", 64)))
    maximum_nu = max(2, int(settings.get("max_frequency_samples", 64)))
    # Retain observed wavenumbers intersecting the displayed physical domain.
    observed_k = np.asarray(k_axis, dtype=float)
    observed_k = np.unique(observed_k[np.isfinite(observed_k)])
    k_limits = style["xlim_Mm_inverse"]
    visible_k = observed_k[(observed_k >= k_limits[0]) & (observed_k <= k_limits[1])]
    if visible_k.size == 0:
        raise ValueError("The observed k axis does not intersect the configured k-omega limits.")
    k_plot = _sample_axis(visible_k, maximum_k)  # Mm^-1
    # Retain strictly positive observed frequencies inside the displayed domain.
    observed_nu = np.asarray(nu_axis, dtype=float)
    observed_nu = np.unique(observed_nu[np.isfinite(observed_nu)])
    nu_limits = style["ylim_mHz"]
    positive_nu = observed_nu[
        (observed_nu > 0.0)
        & (observed_nu >= nu_limits[0])
        & (observed_nu <= nu_limits[1])
    ]
    if positive_nu.size == 0:
        raise ValueError("Theoretical dispersion diagrams require at least one positive frequency.")
    # The Vesa relations contain omega^-1 and omega^-2 terms.  Evaluate only
    # physical positive frequencies, but retain the full observed axis limits
    # when rendering so all eight rows remain directly comparable.
    nu_plot = _sample_axis(positive_nu, maximum_nu)  # mHz
    # Convert plotting units to the km/rad/s conventions consumed by Vesa.
    kh_km = k_plot/1000.0  # km^-1
    omega_rad_s = nu_plot*1.0e-3*2.0*pi  # rad s^-1
    kh_grid, omega_grid = np.meshgrid(kh_km, omega_rad_s)
    # Retain display limits and unit-conversion provenance alongside the sampled meshes.
    return {
        "k_plot_Mm_inverse": k_plot,
        "nu_plot_mHz": nu_plot,
        "k_display_limits_Mm_inverse": list(k_limits),
        "nu_display_limits_mHz": list(nu_limits),
        "kh_grid_km_inverse": kh_grid,
        "omega_grid_rad_s": omega_grid,
        "conversions": {
            "kh": "k_h [Mm^-1] / 1000 -> [km^-1]",
            "omega": "nu [mHz] * 1e-3 * 2pi -> omega [rad s^-1]",
            "omega_zero": "omega=0 excluded from Vesa solver evaluation; observed axis limit retained",
            "theta_phi": "degrees -> radians",
            "dz": "absolute layer separation retained in km",
        },
    }


def evaluate_model(
    model_name: str,
    solver_grid: dict,
    config: dict,
    pair_context: dict,
    vesa_modules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Evaluate every tracked branch through the authoritative Vesa solver.

    Inputs
    ------
    model_name: str
        Supported model key from MODEL_SPECS.

    solver_grid: dict
        Sampled plotting axes plus matching (n_nu, n_k) kh/omega meshes in km^-1
        and rad/s.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    pair_context: dict
        Validated height-pair context with dz_km, a_km_s, theta_deg, phi_deg,
        and optional atmospheric initialization data.

    vesa_modules: dict or None
        Preloaded authoritative Vesa modules/path metadata; None loads them
        through the configuration.

    Outputs
    -------
    result: dict
        All tracked branch phase maps (deg), complete solver/boundary
        diagnostics, parameters, branch labels, and the diagram object.
        Unavailable models return a reason and zero rendered branches; ambiguity
        masks hide the selected Alfvén/slow/fast phase cells.
    '''

    # Resolve authoritative modules and dataset-specific model parameters.
    vesa_modules = load_vesa_2026_modules(config) if vesa_modules is None else vesa_modules
    params = resolve_model_parameters(config, model_name, pair_context, vesa_modules)
    spec = MODEL_BY_NAME[model_name]

    # There is no physical Alfven branch at exactly zero field, and the Vesa
    # kz form correctly becomes singular through a*cos(theta) in that limit.
    if model_name == "alfven_mode" and pair_context["zero_field"]:
        # Package model identity, branch maps, and solver evidence for downstream row
        # rendering.
        return {
            "model": model_name,
            "spec": spec,
            "params": params,
            "unavailable_reason": "No physical Alfvén branch exists for a = 0 km/s.",
            "kz_branch_count": 0,
            "phase_difference_deg": [],
            "diagram": None,
            "omega_boundaries": None,
            "boundaries_by_kz": None,
            "diagnostics": {},
        }

    # Construct the authoritative solver on the sampled physical grid.
    DiagnosticDiagram = vesa_modules["functions_module"].DiagnosticDiagram
    diagram = DiagnosticDiagram(
        solver_grid["kh_grid_km_inverse"],
        solver_grid["omega_grid_rad_s"],
        params,
    )
    # Solve complete boundary/root sets with the requested numerical diagnostics.
    omega_boundaries, omega_diagnostics = diagram.omega_solve_grid(return_diagnostics=True)
    kz_roots, kz_diagnostics = diagram.kz_solve_grid(
        return_diagnostics=True,
        high_precision_validation=bool(
            config.get("komega_comparison", {}).get("high_precision_validation", False)
        ),
    )
    # Return explicit unavailability when the chosen model has no finite isolated roots.
    if not np.any(np.isfinite(kz_roots.real) & np.isfinite(kz_roots.imag)):
        if model_name == "alfven_mode":
            reason = "No isolated Alfvén k_z roots exist for this geometry/frequency grid."
        elif model_name == "slow_mode":
            reason = "No isolated slow-mode k_z roots exist for this zero-field frequency grid."
        else:
            reason = "No finite vertical-wavenumber roots exist for this model and grid."
        return {
            "model": model_name,
            "spec": spec,
            "params": params,
            "unavailable_reason": reason,
            "kz_branch_count": 0,
            "phase_difference_deg": [],
            "diagram": diagram,
            "omega_boundaries": omega_boundaries,
            "boundaries_by_kz": None,
            "diagnostics": {"omega": omega_diagnostics, "kz": kz_diagnostics},
            "branch_labels": (),
        }
    # Associate frequency boundaries with globally tracked kz families before plotting.
    boundaries_by_kz, association_diagnostics = diagram.associate_omega_boundaries_with_kz(
        omega_boundaries,
        kz_roots,
        return_diagnostics=True,
    )

    # Convert each authoritative phase calculation to degrees without changing its
    # branch labels.
    phase_difference_deg = []
    # Evaluate phase maps for every configured solver branch.
    for branch_index in range(int(params["kz_order"])):
        phase_speed = diagram.phase_speed(
            solver_grid["omega_grid_rad_s"],
            kz_roots[:, :, branch_index],
        )
        phase_difference = diagram.phase_difference(
            solver_grid["omega_grid_rad_s"],
            phase_speed,
            float(pair_context["dz_km"]),
        )
        phase_values = np.real(phase_difference)*180.0/pi
        mode_ambiguous = np.asarray(
            kz_diagnostics.get("mode_ambiguous_mask", np.zeros(kz_roots.shape[:2], dtype=bool)),
            dtype=bool,
        )
        # Mask unresolved physical mode pairs using the model-specific ambiguity
        # diagnostic.
        if model_name in {"alfven_mode", "slow_mode", "fast_mode"}:
            phase_values[mode_ambiguous] = np.nan
        phase_difference_deg.append(phase_values)

    # Prefer selected-mode energy diagnostics when deriving human-readable branch
    # labels.
    group_velocity = kz_diagnostics.get(
        "selected_vertical_group_velocity_km_s",
        kz_diagnostics.get("vertical_group_velocity_km_s"),
    )
    branch_labels = []
    model_prefix = {
        "alfven_mode": "Alfvén",
        "slow_mode": "Slow magnetoacoustic",
        "fast_mode": "Fast magnetoacoustic",
    }.get(model_name)
    for branch_index in range(int(params["kz_order"])):
        if model_prefix is None or group_velocity is None:
            branch_labels.append(f"Tracked k_z branch {branch_index + 1}")
            continue
        velocities = np.asarray(group_velocity)[:, :, branch_index]
        velocities = velocities[np.isfinite(velocities)]
        if velocities.size and np.all(velocities > 0.0):
            direction = "upward energy propagation"
        elif velocities.size and np.all(velocities < 0.0):
            direction = "downward energy propagation"
        elif velocities.size:
            direction = "vertical energy direction varies"
        else:
            direction = "energy direction undefined"
        branch_labels.append(f"{model_prefix}; {direction}")

    return {
        "model": model_name,
        "spec": spec,
        "params": params,
        "unavailable_reason": "",
        "kz_branch_count": int(params["kz_order"]),
        "phase_difference_deg": phase_difference_deg,
        "diagram": diagram,
        "omega_boundaries": omega_boundaries,
        "boundaries_by_kz": boundaries_by_kz,
        "branch_labels": tuple(branch_labels),
        "diagnostics": {
            "omega": omega_diagnostics,
            "kz": kz_diagnostics,
            "association": association_diagnostics,
        },
    }


def _format_parameter(name: str, value: Any) -> str:
    '''
    Purpose
    -------
    Format a solver parameter with its display symbol and physical unit.

    Inputs
    ------
    name: str
        Solver parameter key; determines displayed symbol and unit.

    value: float-like
        Numeric solver parameter; angles use radians and other units follow Vesa
        conventions.

    Outputs
    -------
    text: str
        LaTeX-ready numeric parameter label; theta/phi inputs in radians are
        displayed as degrees.
    '''

    # Convert numeric inputs once, then select the correct symbol and physical display
    # unit.
    value = float(value)
    if name == "a":
        return rf"$a={value:.4g}\,\mathrm{{km\,s^{{-1}}}}$"
    if name == "theta":
        return rf"$\theta={np.rad2deg(value):.3g}^\circ$ (inclination from $+z$)"
    if name == "phi":
        return rf"$\phi={np.rad2deg(value):.3g}^\circ$ ($+x\rightarrow +y$)"
    if name == "dz":
        return rf"$\Delta z={value:.4g}\,\mathrm{{km}}$"
    if name == "cs":
        return rf"$c_s={value:.4g}\,\mathrm{{km\,s^{{-1}}}}$"
    if name == "g":
        return rf"$g={value:.4g}\,\mathrm{{km\,s^{{-2}}}}$"
    if name == "N2":
        return rf"$N^2={value:.4g}\,\mathrm{{s^{{-2}}}}$"
    if name == "wac":
        return rf"$\omega_{{\mathrm{{ac}}}}={value:.4g}\,\mathrm{{rad\,s^{{-1}}}}$"
    if name == "H":
        return rf"$H={value:.4g}\,\mathrm{{km}}$"
    if name == "tau":
        return rf"$\tau={value:.4g}\,\mathrm{{s}}$"
    if name == "gamma":
        return rf"$\gamma={value:.4g}$"
    if name == "epsilon":
        return rf"$\epsilon={value:.4g}$"
    return rf"${_latex_escape_text(name)}={value:.4g}$"


def model_parameter_subtitle(result: dict, pair_context: dict) -> str:
    '''
    Purpose
    -------
    Assemble physical heights and model-specific parameters for a plot subtitle.

    Inputs
    ------
    result: dict
        Evaluated model, parameter dictionary, branch phase maps, boundary
        associations, and solver diagnostics.

    pair_context: dict
        Validated height-pair context with dz_km, a_km_s, theta_deg, phi_deg,
        and optional atmospheric initialization data.

    Outputs
    -------
    subtitle: str
        Pipe-separated height/parameter labels plus applicable zero-field angle
        notes.
    '''

    # Include physical heights when available before appending model-specific parameter
    # labels.
    params = result["params"]
    height_values = np.asarray(pair_context.get("height_values_km", []), dtype=float)
    fields = []
    if height_values.size == 2 and np.all(np.isfinite(height_values)):
        fields.append(
            rf"$h=({height_values[0]:.4g},\,{height_values[1]:.4g})\,\mathrm{{km}}$"
        )
    fields.extend([
        _format_parameter(name, params[name])
        for name in result["spec"]["display"]
        if name in params
    ])
    # Disclose any applicable zero-field direction convention in the plot subtitle.
    if pair_context.get("angle_note", "") and any(
        name in result["spec"]["uses"] for name in ("theta", "phi")
    ):
        fields.append(pair_context["angle_note"])
    return " | ".join(fields)


def _axis_extent_from_centers(axis) -> list[float]:
    '''
    Purpose
    -------
    Estimate outer image bounds from sampled coordinate centers.

    Inputs
    ------
    axis: array-like
        One-dimensional coordinate centers in their native axis units.

    Outputs
    -------
    extent: list of float
        First/last centers extended by half the median step; singleton axes use
        a unit-width cell in their native units.
    '''

    # Extend coordinate centers by half the median step, using unit width for a
    # singleton.
    axis = np.asarray(axis, dtype=float)
    if axis.size == 1:
        step = 1.0
    else:
        step = float(np.median(np.diff(axis)))
    return [float(axis[0] - 0.5*step), float(axis[-1] + 0.5*step)]


def _plot_regular_grid_image(ax, x_axis, y_axis, values, **kwargs):
    '''
    Purpose
    -------
    Match plots.ipynb: nearest-neighbor imshow for regular k-omega grids.

    Inputs
    ------
    ax: matplotlib.axes.Axes
        Axes receiving the image artist; modified in place.

    x_axis: array-like
        One-dimensional horizontal plotting coordinate centers.

    y_axis: array-like
        One-dimensional vertical plotting coordinate centers.

    values: array-like
        Image/mesh values, normally shape (n_y, n_x), in the quantity's plotted
        units.

    **kwargs: dict
        Image/mesh style keyword arguments forwarded to imshow or pcolormesh.

    Outputs
    -------
    artist: matplotlib artist
        AxesImage for compatible regular (n_y, n_x) data, otherwise a pcolormesh
        QuadMesh; modifies ax in place.
    '''

    # Check coordinate regularity and array orientation before selecting the image
    # primitive.
    x_axis = np.asarray(x_axis, dtype=float)
    y_axis = np.asarray(y_axis, dtype=float)
    values = np.asanyarray(values)
    x_regular = x_axis.size < 3 or np.allclose(np.diff(x_axis), np.median(np.diff(x_axis)))
    y_regular = y_axis.size < 3 or np.allclose(np.diff(y_axis), np.median(np.diff(y_axis)))
    # Use nearest-neighbor imshow only when centers and data define a regular image.
    if values.shape == (y_axis.size, x_axis.size) and x_regular and y_regular:
        return ax.imshow(
            values,
            origin="lower",
            aspect="auto",
            interpolation="nearest",
            extent=[*_axis_extent_from_centers(x_axis), *_axis_extent_from_centers(y_axis)],
            **kwargs,
        )
    # Use a coordinate-aware mesh for irregular or alternate supported grid layouts.
    return ax.pcolormesh(x_axis, y_axis, values, shading="auto", **kwargs)


def _make_centered_single_panel_figure(style: dict[str, Any]):
    '''
    Purpose
    -------
    Mirror the centered portrait panel and dedicated colorbar in plots.ipynb.

    Inputs
    ------
    style: dict
        Resolved figure dimensions, phase limits in degrees, axis limits, fonts,
        and render settings.

    Outputs
    -------
    fig, ax, cax: tuple
        Open Matplotlib figure with centered portrait plotting axes and a
        dedicated colorbar axes.
    '''

    # Calculate a centered plotting rectangle with a separately reserved colorbar axis.
    fig = plt.figure(figsize=style["figsize"])
    panel_bottom = 0.14
    panel_top = 0.84
    colorbar_width = 0.022
    colorbar_gap = 0.012
    fig_width, fig_height = fig.get_size_inches()
    panel_height = panel_top - panel_bottom
    panel_width = panel_height*fig_height/(fig_width*style["panel_box_aspect"])
    total_width = panel_width + colorbar_gap + colorbar_width
    left = 0.5 - 0.5*total_width
    ax = fig.add_axes([left, panel_bottom, panel_width, panel_height])
    cax = fig.add_axes([left + panel_width + colorbar_gap, panel_bottom, colorbar_width, panel_height])
    ax.set_box_aspect(style["panel_box_aspect"])
    return fig, ax, cax


def plot_model_result(result: dict, solver_grid: dict, pair_context: dict, config: dict, output_file: Path):
    '''
    Purpose
    -------
    Render one HTML row asset containing every tracked solver branch.

    Inputs
    ------
    result: dict
        Evaluated model, parameter dictionary, branch phase maps, boundary
        associations, and solver diagnostics.

    solver_grid: dict
        Sampled plotting axes plus matching (n_nu, n_k) kh/omega meshes in km^-1
        and rad/s.

    pair_context: dict
        Validated height-pair context with dz_km, a_km_s, theta_deg, phi_deg,
        and optional atmospheric initialization data.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    output_file: str or Path
        Destination plot/composite file; create required parent directories.

    Outputs
    -------
    output_file: Path
        Written row-image path; applies local rc settings, closes the figure,
        and records colorbars_rendered on result.
    '''

    # Apply plot-local font/TeX settings while rendering the model row asset.
    style = resolve_komega_plot_style(config)
    with matplotlib.rc_context(_komega_rc_settings(style)):
        return _plot_model_result(result, solver_grid, pair_context, config, output_file)


def _plot_model_result(result: dict, solver_grid: dict, pair_context: dict, config: dict, output_file: Path):
    '''
    Purpose
    -------
    Render every model branch with the pipeline k-omega visual style.

    Inputs
    ------
    result: dict
        Evaluated model, parameter dictionary, branch phase maps, boundary
        associations, and solver diagnostics.

    solver_grid: dict
        Sampled plotting axes plus matching (n_nu, n_k) kh/omega meshes in km^-1
        and rad/s.

    pair_context: dict
        Validated height-pair context with dz_km, a_km_s, theta_deg, phi_deg,
        and optional atmospheric initialization data.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    output_file: str or Path
        Destination plot/composite file; create required parent directories.

    Outputs
    -------
    output_file: Path
        Saved multi-branch comparison-row image. Unavailable modes receive an
        explanatory panel; numerical suspicion/mode ambiguity is masked. Updates
        result colorbar count and closes the figure.
    '''

    # Prepare the row-image destination and a panel grid covering every available
    # branch.
    output_file = Path(output_file).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    style = resolve_komega_plot_style(config)
    branch_count = int(result["kz_branch_count"])
    panel_count = max(1, branch_count)
    columns = min(3, panel_count)
    rows = int(ceil(panel_count/columns))
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(4.6*columns + 0.8, 5.4*rows + 1.4),
        squeeze=False,
    )
    fig.subplots_adjust(
        left=0.065,
        right=0.97,
        bottom=0.07,
        top=0.88,
        wspace=0.48,
        hspace=0.38,
    )
    axes_flat = axes.ravel()
    # Share the centered phase scale and physical display domain across all branch
    # panels.
    norm = TwoSlopeNorm(vmin=style["vmin_deg"], vcenter=0.0, vmax=style["vmax_deg"])
    cmap = _resolve_komega_cmap(style["cmap"])
    k_display_limits = solver_grid.get(
        "k_display_limits_Mm_inverse",
        [float(np.min(solver_grid["k_plot_Mm_inverse"])), float(np.max(solver_grid["k_plot_Mm_inverse"]))],
    )
    nu_display_limits = solver_grid.get(
        "nu_display_limits_mHz",
        [
            float(np.min(solver_grid["nu_plot_mHz"])),
            float(np.max(solver_grid["nu_plot_mHz"])),
        ],
    )
    # Render an explicit availability explanation when no physical branch can be
    # displayed.
    if result["unavailable_reason"]:
        ax = axes_flat[0]
        ax.set_xlim(float(k_display_limits[0]), float(k_display_limits[1]))
        ax.set_ylim(float(nu_display_limits[0]), float(nu_display_limits[1]))
        reason = result["unavailable_reason"]
        if (
            result["model"] == "alfven_mode"
            and float(result["params"].get("a", 0.0)) <= np.finfo(float).tiny
        ):
            reason = r"No physical Alfv\'en branch exists for $a=0\,\mathrm{km\,s^{-1}}$."
        ax.text(0.5, 0.5, reason, ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Physical branch availability")
        ax.set_xlabel(r"$k_h$ [Mm$^{-1}$]")
        ax.set_ylabel(r"$\nu / 2\pi$ [mHz]")
        ax.set_box_aspect(style["panel_box_aspect"])
        ax.grid(alpha=0.2)
        unavailable_mappable = ScalarMappable(norm=norm, cmap=cmap)
        unavailable_mappable.set_array([])
        fig.colorbar(
            unavailable_mappable,
            ax=ax,
            label=r"$\Delta \phi$ [deg]",
            fraction=0.05,
            pad=0.035,
        )
    # Mask numerical failures separately from visible uncertain-assignment markers.
    else:
        kz_diagnostics = result.get("diagnostics", {}).get("kz", {})
        suspicious = np.asarray(
            kz_diagnostics.get(
                "plot_suspicious_mask",
                np.zeros(solver_grid["omega_grid_rad_s"].shape, dtype=bool),
            ), dtype=bool,
        )
        if result["model"] in {"alfven_mode", "slow_mode", "fast_mode"}:
            suspicious |= np.asarray(
                kz_diagnostics.get("mode_ambiguous_mask", np.zeros_like(suspicious)),
                dtype=bool,
            )
        uncertain = np.asarray(
            kz_diagnostics.get("uncertain_mask", np.zeros_like(suspicious)),
            dtype=bool,
        ) & ~suspicious
        k_mesh, nu_mesh = np.meshgrid(
            solver_grid["k_plot_Mm_inverse"], solver_grid["nu_plot_mHz"]
        )
        # Render each phase sheet with its associated kz-zero boundaries.
        for branch_index in range(branch_count):
            ax = axes_flat[branch_index]
            phase_values = np.ma.masked_where(
                suspicious,
                np.ma.masked_invalid(result["phase_difference_deg"][branch_index]),
            )
            mesh = _plot_regular_grid_image(
                ax,
                solver_grid["k_plot_Mm_inverse"],
                solver_grid["nu_plot_mHz"],
                phase_values,
                cmap=cmap,
                norm=norm,
                rasterized=True,
            )
            # Ask the authoritative solver to draw only boundaries associated with this
            # branch.
            lines = result["diagram"].plot_omega_boundaries_for_kz_branch(
                ax,
                result["boundaries_by_kz"],
                branch_index,
                color="black",
                linewidth=2.0,
            )
            line_styles = ("-", "--", ":", "-.")
            for line_index, line in enumerate(lines):
                line.set_label(f"associated $k_z=0$ boundary {line_index + 1}")
                line.set_linestyle(line_styles[line_index % len(line_styles)])
            # Retain nonmasked uncertain assignments as visible diagnostic markers.
            if np.any(uncertain):
                ax.scatter(
                    k_mesh[uncertain], nu_mesh[uncertain],
                    s=3, marker=".", color="black", alpha=0.3,
                    rasterized=True, label="uncertain root assignment",
                )
            ax.set_xlim(float(k_display_limits[0]), float(k_display_limits[1]))
            ax.set_ylim(float(nu_display_limits[0]), float(nu_display_limits[1]))
            ax.set_xlabel(r"$k_h$ [Mm$^{-1}$]")
            ax.set_ylabel(r"$\nu / 2\pi$ [mHz]")
            ax.set_box_aspect(style["panel_box_aspect"])
            branch_labels = result.get("branch_labels", ())
            title = (
                branch_labels[branch_index]
                if branch_index < len(branch_labels)
                else f"Tracked $k_z$ branch {branch_index + 1} of {branch_count}"
            )
            ax.set_title(title)
            if lines or np.any(uncertain):
                ax.legend(loc="best", fontsize=8)
            fig.colorbar(
                mesh,
                ax=ax,
                label=r"$\Delta \phi$ [deg]",
                fraction=0.05,
                pad=0.035,
            )

    # Remove unused panels before adding the model and physical-parameter titles.
    for unused_axis in axes_flat[panel_count:]:
        unused_axis.remove()

    fig.suptitle(
        result["spec"]["plot_title_tex"],
        x=0.5,
        y=0.985,
        ha="center",
        fontsize=14,
    )
    fig.text(
        0.5,
        0.95,
        model_parameter_subtitle(result, pair_context),
        ha="center",
        va="top",
        fontsize=9,
    )
    # Write the completed row and retain its colorbar count for manifest diagnostics.
    fig.savefig(
        output_file,
        dpi=style["dpi"],
        bbox_inches="tight",
        pad_inches=0.18,
    )
    result["colorbars_rendered"] = panel_count
    plt.close(fig)
    return output_file


def comparison_manifest_path(observed_plot_file: str | Path) -> Path:
    '''
    Purpose
    -------
    Derive the managed JSON manifest destination for an observed figure.

    Inputs
    ------
    observed_plot_file: str or Path
        Existing observed/simulation figure used as the first comparison row.

    Outputs
    -------
    path: Path
        Current dispersion-comparison manifest path; no file is written.
    '''

    # Route the manifest basename through the shared managed JSON-output hierarchy.
    observed_plot_file = Path(observed_plot_file).expanduser().resolve()
    return json_output_path(observed_plot_file.with_name(f"{observed_plot_file.stem}_dispersion_comparison.json"))


def load_komega_fits_dataset(dataset_file: str | Path, config: dict) -> dict[str, Any]:
    '''
    Purpose
    -------
    Load one pipeline k-omega FITS product and its height-pair metadata.

    Inputs
    ------
    dataset_file: str or Path
        Pipeline-generated two-dimensional phase-difference komega FITS product.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    Outputs
    -------
    dataset: dict
        Raw phase values (deg) in (n_k, n_nu) order, FITS header/path, axes in
        Mm^-1 and mHz, and extracted height-pair metadata. Missing files, non-2D
        arrays, or unavailable fallback sampling raise an error.
    '''

    # Load the numeric FITS product and require the two-dimensional k/frequency layout.
    from astropy.io import fits

    dataset_file = Path(dataset_file).expanduser().resolve()
    if not dataset_file.is_file():
        raise FileNotFoundError(
            "K-omega dataset not found. Set DATASET_PATH to a pipeline-generated "
            f"k-omega FITS file: {dataset_file}"
        )

    values = np.asarray(fits.getdata(dataset_file), dtype=float)
    header = fits.getheader(dataset_file)
    if values.ndim != 2:
        raise ValueError(
            f"Expected a two-dimensional k-omega FITS array, received shape {values.shape}."
        )

    # Prepare sampling fallbacks for historical products without axis WCS.
    settings = config.get("komega_comparison", {})
    standalone_sampling = settings.get("standalone_sampling", {})
    time_distance = config.get("time_distance", {})
    paired_data = config.get("data", {}).get("paired_cubes", {})

    # Read the stored horizontal axis or reconstruct it from a positive pixel scale.
    if "CRVAL1" in header and "CDELT1" in header:
        k_axis = float(header["CRVAL1"]) + np.arange(values.shape[0])*float(header["CDELT1"])
    else:
        pixel_size_Mm = _finite_float(time_distance.get("p_dx_Mm"))
        if not np.isfinite(pixel_size_Mm):
            pixel_size_Mm = _finite_float(paired_data.get("p_dx_Mm"))
        if not np.isfinite(pixel_size_Mm):
            pixel_size_Mm = _finite_float(standalone_sampling.get("p_dx_Mm"))
        if not np.isfinite(pixel_size_Mm) or pixel_size_Mm <= 0.0:
            raise ValueError(
                "A FITS file without k-axis WCS requires a positive "
                "komega_comparison['standalone_sampling']['p_dx_Mm']."
            )
        k_axis = np.linspace(0.0, pi/pixel_size_Mm, values.shape[0], dtype=float)

    # Read the stored cyclic-frequency axis or reconstruct it from a positive cadence.
    if "CRVAL2" in header and "CDELT2" in header:
        nu_axis = float(header["CRVAL2"]) + np.arange(values.shape[1])*float(header["CDELT2"])
    else:
        cadence_s = _finite_float(time_distance.get("dt"))
        if not np.isfinite(cadence_s):
            cadence_s = _finite_float(paired_data.get("dt"))
        if not np.isfinite(cadence_s):
            cadence_s = _finite_float(standalone_sampling.get("dt_s"))
        if not np.isfinite(cadence_s) or cadence_s <= 0.0:
            raise ValueError(
                "A FITS file without frequency-axis WCS requires a positive "
                "komega_comparison['standalone_sampling']['dt_s']."
            )
        nu_axis = np.linspace(0.0, 0.5/cadence_s*1.0e3, values.shape[1], dtype=float)

    # Extract height-pair physical inputs retained in the FITS header.
    pair_metadata = {}
    header_mapping = {
        "THAVG1": "theta_mean_h1_deg",
        "THAVG2": "theta_mean_h2_deg",
        "PHAVG1": "phi_mean_h1_deg",
        "PHAVG2": "phi_mean_h2_deg",
        "AKMSH1": "a_h1_km_s",
        "AKMSH2": "a_h2_km_s",
        "PAIRA": "a_km_s",
        "PAIRTHE": "theta_deg",
        "PAIRPHI": "phi_deg",
        "DZ_KM": "dz_km",
        "H1_KM": "h1_km",
        "H2_KM": "h2_km",
    }
    for header_key, metadata_key in header_mapping.items():
        if header_key in header:
            pair_metadata[metadata_key] = float(header[header_key])

    return {
        "dataset_file": dataset_file,
        "values": values,
        "header": header,
        "k_axis_Mm_inverse": np.asarray(k_axis, dtype=float),
        "nu_axis_mHz": np.asarray(nu_axis, dtype=float),
        "pair_metadata": pair_metadata,
    }


def plot_observed_komega_dataset(
    dataset: dict[str, Any],
    output_file: str | Path | None = None,
    *,
    config: dict | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap=None,
):
    '''
    Purpose
    -------
    Plot the unchanged observed/simulated values from one selected dataset.

    Inputs
    ------
    dataset: dict
        Loaded FITS record with values in (n_k, n_nu) order and matching
        physical axes.

    output_file: str or Path or None
        Optional destination image; None leaves the returned figure unsaved.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    vmin: float or None
        Lower phase-color limit (deg); None uses the configured default.

    vmax: float or None
        Upper phase-color limit (deg); None uses the configured default.

    cmap: str or Colormap or None
        Observed phase colormap; None uses the resolved style.

    Outputs
    -------
    fig, ax: tuple
        Open Matplotlib figure/axes showing the original dataset values;
        optionally save the file. Invalid array/axis shapes or phase limits
        raise ValueError.
    '''

    # Apply a local plotting context without changing the original phase values.
    style = resolve_komega_plot_style(config)
    with matplotlib.rc_context(_komega_rc_settings(style)):
        return _plot_observed_komega_dataset(
            dataset,
            output_file,
            style=style,
            vmin=vmin,
            vmax=vmax,
            cmap=cmap,
        )


def _plot_observed_komega_dataset(
    dataset: dict[str, Any],
    output_file: str | Path | None,
    *,
    style: dict[str, Any],
    vmin: float | None,
    vmax: float | None,
    cmap,
):
    '''
    Purpose
    -------
    Render the selected data with the plots.ipynb k-omega conventions.

    Inputs
    ------
    dataset: dict
        Loaded FITS record with values in (n_k, n_nu) order and matching
        physical axes.

    output_file: str or Path or None
        Optional destination image; None leaves the returned figure unsaved.

    style: dict
        Resolved figure dimensions, phase limits in degrees, axis limits, fonts,
        and render settings.

    vmin: float or None
        Lower phase-color limit (deg); None uses the configured default.

    vmax: float or None
        Upper phase-color limit (deg); None uses the configured default.

    cmap: str or Colormap or None
        Observed phase colormap; None uses the resolved style.

    Outputs
    -------
    fig, ax: tuple
        Open centered figure/axes displaying transposed (n_nu, n_k) phase data;
        save to output_file when supplied without altering source values.
    '''

    # Validate observed (n_k, n_nu) values against their physical coordinate axes.
    values = np.asarray(dataset["values"], dtype=float)
    k_axis = np.asarray(dataset["k_axis_Mm_inverse"], dtype=float)
    nu_axis = np.asarray(dataset["nu_axis_mHz"], dtype=float)
    if values.shape != (k_axis.size, nu_axis.size):
        raise ValueError(
            "The observed array shape must be (number of k samples, number of frequency samples)."
        )
    # Resolve a centered phase-color range and the requested colormap.
    vmin = style["vmin_deg"] if vmin is None else float(vmin)
    vmax = style["vmax_deg"] if vmax is None else float(vmax)
    cmap = _resolve_komega_cmap(style["cmap"] if cmap in (None, "") else cmap)
    if not vmin < 0.0 < vmax:
        raise ValueError("Observed plot limits must straddle zero for a centered phase scale.")

    # Display the transposed observed phase map with its dedicated colorbar.
    fig, ax, cax = _make_centered_single_panel_figure(style)
    mesh = _plot_regular_grid_image(
        ax,
        k_axis,
        nu_axis,
        np.ma.masked_invalid(values.T),
        cmap=cmap,
        norm=TwoSlopeNorm(vmin=float(vmin), vcenter=0.0, vmax=float(vmax)),
        rasterized=True,
    )
    ax.set_xlim(*style["xlim_Mm_inverse"])
    ax.set_ylim(*style["ylim_mHz"])
    ax.set_xlabel(r"$k_h$ [Mm$^{-1}$]")
    ax.set_ylabel(r"$\nu / 2\pi$ [mHz]")
    fig.suptitle(
        r"Observed/Simulation $k$--$\omega$ Diagram"
        "\n"
        rf"dataset: {_latex_escape_text(Path(dataset['dataset_file']).name)}",
        x=0.5,
        y=0.98,
        ha="center",
    )
    fig.colorbar(mesh, cax=cax, label=r"$\Delta \phi$ [deg]")

    # Optionally write the figure while leaving it open for the calling notebook.
    if output_file is not None:
        output_file = Path(output_file).expanduser().resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            output_file,
            dpi=style["dpi"],
            bbox_inches="tight",
            pad_inches=0.18,
        )

    return fig, ax


def generate_single_model_plot(
    dataset: dict[str, Any] | str | Path,
    model_name: str,
    config: dict,
    output_file: str | Path,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Evaluate and plot one selected authoritative model for one real dataset.

    Inputs
    ------
    dataset: dict or str or Path
        Loaded FITS dataset record, or a FITS path where this callable accepts
        one; values use (n_k, n_nu) order in degrees.

    model_name: str
        Supported model key from MODEL_SPECS.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    output_file: str or Path
        Destination plot/composite file; create required parent directories.

    Outputs
    -------
    publication: dict
        Saved output Path, source dataset, validated pair context, solver
        grid/result, and authoritative source provenance. Enables standalone
        pair fallbacks for this notebook workflow.
    '''

    # Accept either an existing dataset record or a pipeline FITS product path.
    if not isinstance(dataset, dict):
        dataset = load_komega_fits_dataset(dataset, config)
    if model_name not in MODEL_BY_NAME:
        allowed = ", ".join(spec["model"] for spec in MODEL_SPECS)
        raise ValueError(f"Unknown model {model_name!r}. Choose one of: {allowed}.")

    # Resolve notebook-enabled physical fallbacks and sample the actual observed domain.
    pair_context = resolve_height_pair_context(
        config,
        dataset.get("pair_metadata", {}),
        allow_standalone_fallback=True,
    )
    solver_grid = build_solver_grid(
        dataset["k_axis_Mm_inverse"],
        dataset["nu_axis_mHz"],
        config,
    )
    vesa_modules = load_vesa_2026_modules(config)
    # Evaluate the selected authoritative model before publishing its row image.
    result = evaluate_model(
        model_name,
        solver_grid,
        config,
        pair_context,
        vesa_modules=vesa_modules,
    )
    output_file = plot_model_result(
        result,
        solver_grid,
        pair_context,
        config,
        Path(output_file),
    )
    # Return numerical context and implementation provenance alongside the saved asset.
    return {
        "output_file": output_file,
        "dataset": dataset,
        "pair_context": pair_context,
        "solver_grid": solver_grid,
        "result": result,
        "authoritative_source": {
            "config_file": str(vesa_modules["config_file"]),
            "functions_file": str(vesa_modules["functions_file"]),
            "methods": list(AUTHORITATIVE_METHODS),
        },
    }


def _relative_path(path: Path, parent: Path) -> str:
    '''
    Purpose
    -------
    Represent a manifest asset relative to its parent when possible.

    Inputs
    ------
    path: Path
        Source path resolved before generating the manifest reference.

    parent: Path
        Base directory for relative manifest paths.

    Outputs
    -------
    reference: str
        POSIX relative path within parent, otherwise the resolved absolute path.
    '''

    # Prefer portable root-relative manifest references and retain absolute paths
    # outside the root.
    try:
        return path.resolve().relative_to(parent.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _json_params(params: dict, displayed_names) -> dict[str, Any]:
    '''
    Purpose
    -------
    Copy displayed solver parameters into a JSON-native numeric mapping.

    Inputs
    ------
    params: dict
        Resolved solver parameters with physical units defined by Vesa_2026.

    displayed_names: iterable of str
        Parameter keys copied into the JSON-compatible float mapping.

    Outputs
    -------
    output: dict
        Requested existing parameter keys with float values; absent keys are
        omitted.
    '''

    # Copy only present display parameters and convert NumPy-compatible scalars to
    # floats.
    output = {}
    for name in displayed_names:
        if name in params:
            output[name] = float(params[name])
    return output


def generate_komega_comparison_assets(
    observed_plot_file: str | Path,
    k_axis,
    nu_axis,
    config: dict,
    pair_metadata: dict | None = None,
    *,
    allow_standalone_fallback: bool = False,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Calculate seven model rows and publish their comparison manifest.

    Inputs
    ------
    observed_plot_file: str or Path
        Existing observed/simulation figure used as the first comparison row.

    k_axis: array-like
        Observed horizontal-wavenumber axis (Mm^-1).

    nu_axis: array-like
        Observed cyclic-frequency axis (mHz).

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    pair_metadata: dict or None
        Dataset-specific layer heights (km), Alfvén speeds (km/s), orientations
        (deg), or atmospheric initialization metadata.

    allow_standalone_fallback: bool
        Permit notebook-only configured pair values when direct layer metadata
        is unavailable.

    Outputs
    -------
    manifest: dict
        Observed-plus-seven-model row records, pair context, sampled domain,
        solver quality, and authoritative source paths. Write row images and
        JSON, returning {} when comparison is disabled; the observed image must
        exist.
    '''

    # Require the observed source image before honoring the comparison-generation
    # toggle.
    observed_plot_file = Path(observed_plot_file).expanduser().resolve()
    if not observed_plot_file.exists():
        raise FileNotFoundError(f"Observed/simulation k-omega plot not found: {observed_plot_file}")
    if not config.get("komega_comparison", {}).get("enabled", True):
        return {}

    # Resolve a shared physical pair and numerical domain for all model rows.
    pair_context = resolve_height_pair_context(
        config,
        pair_metadata,
        allow_standalone_fallback=allow_standalone_fallback,
    )
    vesa_modules = load_vesa_2026_modules(config)
    solver_grid = build_solver_grid(k_axis, nu_axis, config)
    asset_dir = observed_plot_file.parent / "dispersion_comparison" / observed_plot_file.stem
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Retain the unchanged observed image as the first required comparison row.
    rows = [
        {
            "label": COMPARISON_ROW_LABELS[0],
            "path": _relative_path(observed_plot_file, observed_plot_file.parent),
            "kind": "observed",
        }
    ]
    model_records = []
    # Evaluate and render every authoritative model in the configured row order.
    for model_spec in MODEL_SPECS:
        result = evaluate_model(
            model_spec["model"],
            solver_grid,
            config,
            pair_context,
            vesa_modules=vesa_modules,
        )
        output_file = plot_model_result(
            result,
            solver_grid,
            pair_context,
            config,
            asset_dir / f"{model_spec['slug']}.png",
        )
        rows.append(
            {
                "label": model_spec["label"],
                "path": _relative_path(output_file, observed_plot_file.parent),
                "kind": "theory",
                "model": model_spec["model"],
            }
        )
        # Summarize solver, association, conditioning, and optional precision-validation
        # evidence.
        diagnostics = result.get("diagnostics", {})
        omega_diagnostics = diagnostics.get("omega", {})
        association_diagnostics = diagnostics.get("association", {})
        kz_diagnostics = diagnostics.get("kz", {})
        finite_residuals = np.asarray(
            kz_diagnostics.get("max_root_residual", []), dtype=float
        )
        finite_residuals = finite_residuals[np.isfinite(finite_residuals)]
        finite_conditions = np.asarray(
            kz_diagnostics.get("max_root_condition", []), dtype=float
        )
        finite_conditions = finite_conditions[np.isfinite(finite_conditions)]
        high_precision = kz_diagnostics.get("high_precision_validation", {})
        hp_differences = np.asarray(
            high_precision.get("max_relative_difference", []), dtype=float
        )
        hp_differences = hp_differences[np.isfinite(hp_differences)]
        model_records.append(
            {
                "model": model_spec["model"],
                "label": model_spec["label"],
                "params_supplied": _json_params(result["params"], model_spec["display"]),
                "kz_branches_rendered": int(result["kz_branch_count"]),
                "kz_branch_labels": list(result.get("branch_labels", ())),
                "kz_mode_ambiguous_cells": int(
                    np.count_nonzero(kz_diagnostics.get("mode_ambiguous_mask", False))
                ),
                "colorbars_rendered": int(result.get("colorbars_rendered", 0)),
                "authoritative_kz_order": int(result["params"]["kz_order"]),
                "authoritative_omega_order": int(result["params"]["omega_order"]),
                "physical_omega_branches": int(
                    np.count_nonzero(np.any(np.isfinite(result["omega_boundaries"]), axis=0))
                ) if result["omega_boundaries"] is not None else 0,
                "associated_boundary_points": int(
                    np.count_nonzero(association_diagnostics.get("association_mask", []))
                ),
                "unavailable_reason": result["unavailable_reason"],
                "omega_solver_failures": int(
                    np.count_nonzero(omega_diagnostics.get("solve_failed_mask", []))
                ),
                "kz_solver_failures": int(
                    np.count_nonzero(kz_diagnostics.get("solve_failed_mask", []))
                ),
                "kz_degree_reduced_points": int(
                    np.count_nonzero(kz_diagnostics.get("degree_reduced_mask", []))
                ),
                "kz_uncertain_points": int(
                    np.count_nonzero(kz_diagnostics.get("uncertain_mask", []))
                ),
                "kz_ill_conditioned_points": int(
                    np.count_nonzero(kz_diagnostics.get("ill_conditioned_mask", []))
                ),
                "kz_max_term_scaled_residual": (
                    float(np.max(finite_residuals)) if finite_residuals.size else None
                ),
                "kz_max_root_condition": (
                    float(np.max(finite_conditions)) if finite_conditions.size else None
                ),
                "kz_high_precision_checked_points": int(
                    np.count_nonzero(high_precision.get("checked_mask", []))
                ),
                "kz_high_precision_failed_points": int(
                    np.count_nonzero(high_precision.get("failed_mask", []))
                ),
                "kz_high_precision_max_relative_difference": (
                    float(np.max(hp_differences)) if hp_differences.size else None
                ),
            }
        )

    # Enforce the exact observed-plus-seven-model row contract before serializing
    # provenance.
    if tuple(row["label"] for row in rows) != COMPARISON_ROW_LABELS:
        raise RuntimeError("The k-omega comparison rows are not in the required order.")

    # Record the sampled domain, physical inputs, authoritative implementation, and
    # model quality.
    manifest = {
        "schema_version": 1,
        "rows": rows,
        "pair_context": pair_context,
        "solver_domain": {
            "k_h_Mm_inverse": [float(solver_grid["k_plot_Mm_inverse"][0]), float(solver_grid["k_plot_Mm_inverse"][-1])],
            "nu_mHz": [float(solver_grid["nu_plot_mHz"][0]), float(solver_grid["nu_plot_mHz"][-1])],
            "shape": [
                int(solver_grid["nu_plot_mHz"].size),
                int(solver_grid["k_plot_Mm_inverse"].size),
            ],
            "conversions": solver_grid["conversions"],
        },
        "authoritative_source": {
            "config_file": str(vesa_modules["config_file"]),
            "functions_file": str(vesa_modules["functions_file"]),
            "methods": list(AUTHORITATIVE_METHODS),
        },
        "models": model_records,
        "souffrin_included": False,
    }
    # Publish the managed manifest after all row images have been written.
    manifest_file = comparison_manifest_path(observed_plot_file)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    manifest["manifest_file"] = str(manifest_file)
    return manifest


def compose_komega_comparison_figure(
    manifest: dict[str, Any],
    row_base_dir: str | Path,
    output_file: str | Path,
    *,
    width_px: int = 1800,
) -> Path:
    '''
    Purpose
    -------
    Stack the eight complete observed/theory row assets into one labeled PNG.

    Inputs
    ------
    manifest: dict
        Comparison record whose ordered rows must exactly match
        COMPARISON_ROW_LABELS.

    row_base_dir: str or Path
        Base directory against which relative row image paths are resolved.

    output_file: str or Path
        Destination plot/composite file; create required parent directories.

    width_px: int
        Composite image width in pixels; must be at least 800.

    Outputs
    -------
    output_file: Path
        Saved composite path. Require the exact configured row order, readable
        image assets, and width_px >= 800; preserve each row aspect ratio while
        resizing.
    '''

    # Require the exact row contract and a readable minimum composite width.
    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFont

    rows = manifest.get("rows", [])
    if tuple(row.get("label") for row in rows) != COMPARISON_ROW_LABELS:
        raise ValueError("A composite k-omega figure requires the exact seven comparison rows.")
    width_px = int(width_px)
    if width_px < 800:
        raise ValueError("The composite width must be at least 800 pixels for readable labels.")

    # Resolve output paths and reserve composite margins and label areas.
    row_base_dir = Path(row_base_dir).expanduser().resolve()
    output_file = Path(output_file).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    margin_px = 28
    header_height_px = 86
    label_height_px = 52
    divider_height_px = 3
    content_width_px = width_px - 2*margin_px

    font_path = font_manager.findfont("DejaVu Sans")
    title_font = ImageFont.truetype(font_path, 32)
    row_font = ImageFont.truetype(font_path, 24)
    rendered_rows = []
    # Load and resize each complete row while preserving its image aspect ratio.
    for row in rows:
        row_file = Path(row["path"])
        if not row_file.is_absolute():
            row_file = row_base_dir / row_file
        if not row_file.is_file():
            raise FileNotFoundError(f"Comparison row image not found: {row_file}")
        with PILImage.open(row_file) as source:
            source = source.convert("RGB")
            resized_height = max(1, round(source.height*content_width_px/source.width))
            rendered_rows.append(
                source.resize(
                    (content_width_px, resized_height),
                    PILImage.Resampling.LANCZOS,
                )
            )

    # Allocate the composite height from all resized rows and their separators.
    total_height_px = (
        header_height_px
        + margin_px
        + sum(label_height_px + image.height + divider_height_px + margin_px for image in rendered_rows)
    )
    composite = PILImage.new("RGB", (width_px, total_height_px), "white")
    draw = ImageDraw.Draw(composite)
    draw.text(
        (width_px//2, header_height_px//2),
        "Seven-row dispersion comparison",
        fill="black",
        font=title_font,
        anchor="mm",
    )

    # Place ordered row labels and images beneath the composite header.
    y = header_height_px + margin_px
    for row_number, (row, row_image) in enumerate(zip(rows, rendered_rows), start=1):
        plain_row_label = str(row["label"]).replace(" k–ω Diagram", "")
        draw.text(
            (margin_px, y + label_height_px//2),
            f"{row_number}. {plain_row_label}",
            fill="black",
            font=row_font,
            anchor="lm",
        )
        y += label_height_px
        composite.paste(row_image, (margin_px, y))
        y += row_image.height + margin_px
        draw.rectangle(
            (margin_px, y, width_px - margin_px, y + divider_height_px - 1),
            fill=(180, 180, 180),
        )
        y += divider_height_px

    # Save the assembled RGB comparison as a PNG artifact.
    composite.save(output_file, format="PNG", optimize=True)
    return output_file


def generate_standalone_komega_comparison(
    dataset: dict[str, Any] | str | Path,
    config: dict,
    output_file: str | Path,
    *,
    observed_vmin: float | None = None,
    observed_vmax: float | None = None,
    observed_cmap=None,
) -> dict[str, Any]:
    '''
    Purpose
    -------
    Generate and combine all eight rows for a notebook-selected dataset.

    Inputs
    ------
    dataset: dict or str or Path
        Loaded FITS dataset record, or a FITS path where this callable accepts
        one; values use (n_k, n_nu) order in degrees.

    config: dict or None
        Project runtime configuration; comparison/model settings live under
        komega_comparison. Only helpers accepting None substitute empty
        defaults.

    output_file: str or Path
        Destination plot/composite file; create required parent directories.

    observed_vmin: float or None
        Lower observed-row color limit in degrees; None uses configuration.

    observed_vmax: float or None
        Upper observed-row color limit in degrees; None uses configuration.

    observed_cmap: str or Colormap or None
        Observed-row colormap override; theoretical rows retain their configured
        style.

    Outputs
    -------
    publication: dict
        Composite/observed image Paths, dataset, and manifest. Write the
        observed row, generate seven theoretical rows, then compose all eight;
        close the intermediate observed figure.
    '''

    # Load the selected dataset and reserve a separate observed/theory asset directory.
    if not isinstance(dataset, dict):
        dataset = load_komega_fits_dataset(dataset, config)
    output_file = Path(output_file).expanduser().resolve()
    asset_dir = output_file.parent / f"{output_file.stem}_assets"
    observed_file = asset_dir / f"{Path(dataset['dataset_file']).stem}_observed.png"
    # Render the unchanged observed phase values with any notebook color overrides.
    observed_figure, _ = plot_observed_komega_dataset(
        dataset,
        observed_file,
        config=config,
        vmin=observed_vmin,
        vmax=observed_vmax,
        cmap=observed_cmap,
    )
    plt.close(observed_figure)

    # Generate all model assets from the same dataset and validated height pair.
    manifest = generate_komega_comparison_assets(
        observed_file,
        dataset["k_axis_Mm_inverse"],
        dataset["nu_axis_mHz"],
        config,
        pair_metadata=dataset.get("pair_metadata", {}),
        allow_standalone_fallback=True,
    )
    # Combine the ordered observed and model images into the standalone comparison.
    composite_file = compose_komega_comparison_figure(
        manifest,
        observed_file.parent,
        output_file,
        width_px=int(config.get("komega_comparison", {}).get("composite_width_px", 1800)),
    )
    return {
        "output_file": composite_file,
        "observed_file": observed_file,
        "dataset": dataset,
        "manifest": manifest,
    }
