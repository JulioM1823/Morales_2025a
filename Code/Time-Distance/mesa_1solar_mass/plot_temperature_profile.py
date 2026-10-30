#!/usr/bin/env python3
'''
Purpose
-------
Plot radial temperature from a MESA text model and save the resulting figure.

Inputs
------
None

Outputs
-------
Command-line program
    Read a .mod file, plot shell temperature in K versus the requested
    radius coordinate, and write an image; --show also displays it.
'''

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np


# Define the solar-radius conversion used for the optional radius axis
RSUN_CM = 6.957e10


def mesa_float(value: str) -> float:
    '''
    Purpose
    -------
    Convert a Fortran-style real literal to a Python float.

    Inputs
    ------
    value: str
        Number text; D and d exponent markers are accepted.

    Outputs
    -------
    number: float
        Converted value. Invalid numeric text raises ValueError.
    '''
    return float(value.replace("D", "E").replace("d", "e"))


def read_temperature_profile(model_path: Path) -> tuple[np.ndarray, np.ndarray]:
    '''
    Purpose
    -------
    Read shell log-temperature/log-radius values and return a radius-sorted profile.

    Inputs
    ------
    model_path: Path
        MESA text model; shell records contain index and natural-log T/r columns.

    Outputs
    -------
    radius, temperature: tuple of np.ndarray
        One-dimensional radius in cm and temperature in K, sorted by radius.
        Comments, non-shell rows, and malformed numeric rows are skipped; no
        valid shell data raises ValueError.
    '''
    radius_cm: list[float] = []
    temperature_k: list[float] = []

    # Skip headers/comments and decode shell natural logarithms
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

    # Return shells in ascending physical radius
    order = np.argsort(radius)
    return radius[order], temperature[order]


def main() -> None:
    '''
    Purpose
    -------
    Parse MESA plotting settings and save the radial temperature figure.

    Inputs
    ------
    None

    Outputs
    -------
    None
        Save the selected image and optionally display it. Headless runs use
        the Agg backend and temporary Matplotlib/XDG cache directories.
    '''

    # Parse model path, output image, radius unit, and display preference
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

    # Select a headless renderer and writable cache locations before importing pyplot
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

    # Convert radius to cm, solar radii, or fractions of the maximum model radius
    if args.radius_unit == "cm":
        x = radius_cm
        xlabel = r"$r\ \mathrm{[cm]}$"
    elif args.radius_unit == "rsun":
        x = radius_cm / RSUN_CM
        xlabel = r"$r\ [R_\odot]$"
    else:
        x = radius_cm / radius_cm.max()
        xlabel = r"$r/R_\star$"

    # Derive the default output filename alongside the source model
    output = args.output
    if output is None:
        output = model_path.with_name(f"{model_path.stem}_temperature_profile.png")

    # Plot temperature on a logarithmic axis and save the completed figure
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
