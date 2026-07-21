#!/usr/bin/env python3
"""Plot T(r) from a MESA text model file."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np


RSUN_CM = 6.957e10


def mesa_float(value: str) -> float:
    """Convert a MESA/Fortran-style float such as 1.0D+00 to Python float."""
    return float(value.replace("D", "E").replace("d", "e"))


def read_temperature_profile(model_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return radius in cm and temperature in K from a MESA .mod file."""
    radius_cm: list[float] = []
    temperature_k: list[float] = []

    with model_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("!"):
                continue

            parts = line.split()
            if not parts[0].isdigit() or len(parts) < 4:
                continue

            try:
                ln_t = mesa_float(parts[2])
                ln_r = mesa_float(parts[3])
            except ValueError:
                continue

            temperature_k.append(float(np.exp(ln_t)))
            radius_cm.append(float(np.exp(ln_r)))

    if not radius_cm:
        raise ValueError(f"No shell data found in {model_path}")

    radius = np.asarray(radius_cm)
    temperature = np.asarray(temperature_k)

    order = np.argsort(radius)
    return radius[order], temperature[order]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot the radial temperature profile from a MESA .mod file."
    )
    parser.add_argument(
        "model",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("1M_at_TAMS.mod"),
        help="Path to the MESA .mod file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output image path. Defaults to MODEL_temperature_profile.png.",
    )
    parser.add_argument(
        "--radius-unit",
        choices=("cm", "rsun", "rstar"),
        default="rsun",
        help="Unit for the x-axis radius.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the plot interactively after saving it.",
    )
    args = parser.parse_args()

    if not args.show:
        cache_root = Path(tempfile.gettempdir()) / "mesa_temperature_profile_cache"
        mpl_cache = cache_root / "matplotlib"
        xdg_cache = cache_root / "xdg"
        mpl_cache.mkdir(parents=True, exist_ok=True)
        xdg_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))
        os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))

        import matplotlib

        matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    model_path = args.model.expanduser().resolve()
    radius_cm, temperature_k = read_temperature_profile(model_path)

    if args.radius_unit == "cm":
        x = radius_cm
        xlabel = r"$r\ \mathrm{[cm]}$"
    elif args.radius_unit == "rsun":
        x = radius_cm / RSUN_CM
        xlabel = r"$r\ [R_\odot]$"
    else:
        x = radius_cm / radius_cm.max()
        xlabel = r"$r/R_\star$"

    output = args.output
    if output is None:
        output = model_path.with_name(f"{model_path.stem}_temperature_profile.png")

    fig, ax = plt.subplots(figsize=(7, 5), constrained_layout=True)
    ax.plot(x, temperature_k, color="tab:red", linewidth=2)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(r"$T(r)\ \mathrm{[K]}$")
    ax.set_yscale("log")
    ax.grid(True, which="both", alpha=0.3)
    ax.set_title(model_path.name)

    fig.savefig(output, dpi=200)
    print(f"Saved {output}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
