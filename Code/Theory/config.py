"""Configuration parameters for diagnostic diagram models."""

from __future__ import annotations
import numpy as np

sin = np.sin
cos = np.cos
sqrt = np.sqrt
pi = np.pi

# Use same constants as @vesaMultiheightObservationsAtmospheric2023 Figure 3
cs: float = 7.8  # km/s
dz: float = 150.0  # km
g: float = 0.274  # km/s^2
gamma: float = 5.0 / 3.0
H: float = 125.0  # km
N: float = sqrt((g / H) - (g ** 2 / cs ** 2))  # Hz
tau: float = 200.0  # s
wac: float = cs / (2.0 * H)  # Hz

# Magnetic parameters
B: float = 100.0  # Gauss
epsilon: float = 0.0
phi: float = 40.0 * pi / 180.0  # deg -> rad
theta: float = 80.0 * pi / 180.0  # deg -> rad

# Alfven velocity components
a:  float = 0.33 * cs  # km/s
ax: float = a * sin(theta) * cos(phi)
ay: float = a * sin(theta) * sin(phi)
az: float = a * cos(theta)

# Define the input parameters
params_sf1966 = {
    "cs": cs,
    "dz": dz,
    "g": g,
    "N": N,
    "wac": wac,
    "kz_order": 2,
    "omega_order": 4,
    "model": "sf1966",
    "title": "(SF, 1966)",
}

params_mt1981 = {
    "cs": cs,
    "dz": dz,
    "g": g,
    "H": H,
    "N": N,
    "kz_order": 2,
    "omega_order": 4,
    "model": "mt1981",
    "title": r"(M\&T, 1981)",
}

params_mt1982 = {
    "cs": cs,
    "dz": dz,
    "g": g,
    "gamma": gamma,
    "H": H,
    "N": N,
    "tau": tau,
    "kz_order": 2,
    "omega_order": 8,
    "model": "mt1982",
    "title": r"$\tau = \,$" + f"{tau:.0f}" + r"s, (M\&T, 1982)",
}

params_bunte1993 = {
    "a": a,
    "B": B,
    "cs": cs,
    "dz": dz,
    "epsilon": epsilon,
    "g": g,
    "gamma": gamma,
    "N": N,
    "H": H,
    "tau": tau,
    "wac": wac,
    "kz_order": 2,
    "omega_order": 8,
    "model": "bunte1993",
    "title": r"$a = \,$"
    + f"{a / cs:.2f}"
    + r"$c_s$"
    + r", $\tau = \,$"
    + f"{tau:.0f}"
    + r"s, $\epsilon = \,$"
    + f"{epsilon:.1f}"
    + r" (B\&B, 1993)",
}

params_nc2009 = {
    "a": a,
    "ax": ax,
    "ay": ay,
    "az": az,
    "cs": cs,
    "dz": dz,
    "g": g,
    "N": N,
    "phi": phi,
    "theta": theta,
    "wac": wac,
    "kz_order": 6,
    "omega_order": 6,
    "model": "nc2009",
    "title": r"$a = \,$"
    + f"{a / cs:.2f}"
    + r"$c_s$"
    + r", $\theta = \,$"
    + f"{theta * 180 / pi:.0f}"
    + r"$^\circ$, $\phi = \,$"
    + f"{phi * 180 / pi:.0f}"
    + r"$^\circ$ (N\&C, 2009)",
}

# Dictionary of all models
params = {
    "sf1966": params_sf1966,  # @schatzmanWavesSolarAtmosphere1967
    "mt1981": params_mt1981,  # @mihalasInternalGravityWaves1981
    "mt1982": params_mt1982,  # @mihalasInternalGravityWaves1982
    "bunte1993": params_bunte1993,  # @bunteMagnetoatmosphericWavesSubject1994
    "nc2009": params_nc2009,  # @newingtonReflectionConversionMagnetogravity2010
}