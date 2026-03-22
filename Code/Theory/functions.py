"""Dispersion and diagnostic tools for solar atmospheric wave models.

This module provides a DiagnosticDiagram class that evaluates model-specific
polynomials for omega and kz, solves for dispersion boundaries, and computes
phase speeds and phase differences.
"""

from __future__ import annotations

from typing import Mapping, Tuple

import numpy as np
from numpy.typing import ArrayLike
from scipy import optimize


_MODEL_KEYS = {
    "sf1966": ("N", "wac"),
    "mt1981": ("H", "N"),
    "mt1982": ("gamma", "N", "H", "tau"),
    "bunte1993": ("a", "epsilon", "gamma", "H", "tau", "wac"),
    "nc2009": ("a", "ax", "ay", "az", "theta", "phi", "N", "wac"),
}

_BASE_KEYS = ("cs", "g", "kz_order", "omega_order", "model")


def _as_1d_grid(grid: ArrayLike, name: str, axis: str) -> np.ndarray:
    """Coerce a 1D meshgrid axis to a 1D numpy array."""
    arr = np.asarray(grid)
    if np.iscomplexobj(arr):
        if not np.allclose(arr.imag, 0.0):
            raise ValueError(f"{name} must be real-valued.")
        arr = arr.real
    arr = np.asarray(arr, dtype=float)
    if arr.ndim == 0:
        raise ValueError(f"{name} must be array-like, not a scalar.")
    if arr.ndim == 1:
        grid_1d = arr
    elif arr.ndim == 2:
        if axis == "row":
            grid_1d = arr[0, :]
            if not np.allclose(arr, grid_1d[None, :]):
                raise ValueError(
                    f"{name} must be 1D or a meshgrid with identical rows."
                )
        elif axis == "col":
            grid_1d = arr[:, 0]
            if not np.allclose(arr, grid_1d[:, None]):
                raise ValueError(
                    f"{name} must be 1D or a meshgrid with identical columns."
                )
        else:
            raise ValueError("axis must be 'row' or 'col'.")
    else:
        raise ValueError(f"{name} must be 1D or 2D array-like.")

    if grid_1d.size == 0:
        raise ValueError(f"{name} must not be empty.")
    if not np.all(np.isfinite(grid_1d)):
        raise ValueError(f"{name} must contain only finite values.")

    return grid_1d


def _require_real_array(value: ArrayLike, name: str) -> np.ndarray:
    """Return a real-valued array, rejecting NaNs/Infs and complex values."""
    arr = np.asarray(value)
    if np.iscomplexobj(arr):
        if not np.allclose(arr.imag, 0.0):
            raise ValueError(f"{name} must be real-valued.")
        arr = arr.real
    arr = np.asarray(arr, dtype=float)
    if arr.size == 0:
        raise ValueError(f"{name} must not be empty.")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain only finite values.")
    return arr


def _require_scalar(value: ArrayLike, name: str) -> float:
    """Return a scalar float and reject non-scalars."""
    arr = _require_real_array(value, name)
    if arr.ndim != 0:
        raise ValueError(f"{name} must be a scalar.")
    return float(arr)


def _require_positive_int(value: object, name: str) -> int:
    """Validate a positive integer setting."""
    try:
        as_float = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a positive integer.") from exc
    if not as_float.is_integer():
        raise ValueError(f"{name} must be a positive integer.")
    as_int = int(as_float)
    if as_int <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return as_int


def _maybe_scalar(value: np.ndarray):
    """Return a numpy scalar if value is 0d, else the array itself."""
    if isinstance(value, np.ndarray) and value.ndim == 0:
        return value[()]
    return value


class DiagnosticDiagram:
    """Compute dispersion diagnostics for multiple atmospheric wave models.

    Parameters
    ----------
    kh_grid : array-like
        Horizontal wavenumber grid (km^-1). Accepts a 1D array or a 2D
        meshgrid with identical rows.
    omega_grid : array-like
        Angular frequency grid (rad/s). Accepts a 1D array or a 2D meshgrid
        with identical columns.
    params : Mapping[str, float]
        Model parameters. Must include base keys: cs, g, kz_order, omega_order,
        and model. Additional keys are model dependent.
    """

    _OMEGA_FINE_POINTS = 5_000
    _KZ_FINE_POINTS = 5_000
    _KZ_FINE_RANGE = (-1.0, 1.0)

    def __init__(self, kh_grid: ArrayLike, omega_grid: ArrayLike, params: Mapping[str, float]):
        self.kh = _as_1d_grid(kh_grid, "kh_grid", axis="row")  # km^-1
        self.omega = _as_1d_grid(omega_grid, "omega_grid", axis="col")  # rad/s

        if not isinstance(params, Mapping):
            raise TypeError("params must be a mapping of parameter names to values.")
        self.params = dict(params)
        self.model = self.params.get("model")
        if self.model not in _MODEL_KEYS:
            raise ValueError(
                "Model not recognized. Please choose from "
                "'sf1966', 'mt1981', 'mt1982', 'bunte1993', 'nc2009'."
            )

        missing = [key for key in _BASE_KEYS if key not in self.params]
        missing += [key for key in _MODEL_KEYS[self.model] if key not in self.params]
        if missing:
            raise ValueError(
                f"Missing required parameters for model '{self.model}': {sorted(set(missing))}"
            )

        self.cs = _require_scalar(self.params["cs"], "cs")  # km/s
        if self.cs <= 0:
            raise ValueError("cs (sound speed) must be positive.")
        self.g = _require_scalar(self.params["g"], "g")  # km/s^2
        self.kz_order = _require_positive_int(self.params["kz_order"], "kz_order")
        self.omega_order = _require_positive_int(self.params["omega_order"], "omega_order")

        # Aliases with clearer names for internal readability.
        self.sound_speed = self.cs
        self.gravity = self.g

        if self.model == "sf1966":
            self.N = _require_scalar(self.params["N"], "N")
            self.wac = _require_scalar(self.params["wac"], "wac")
        elif self.model == "mt1981":
            self.H = _require_scalar(self.params["H"], "H")
            self.N = _require_scalar(self.params["N"], "N")
        elif self.model == "mt1982":
            self.gamma = _require_scalar(self.params["gamma"], "gamma")
            self.N = _require_scalar(self.params["N"], "N")
            self.H = _require_scalar(self.params["H"], "H")
            self.tau = _require_scalar(self.params["tau"], "tau")
            self.a = 0.0
        elif self.model == "bunte1993":
            self.a = _require_scalar(self.params["a"], "a")
            self.epsilon = _require_scalar(self.params["epsilon"], "epsilon")
            self.gamma = _require_scalar(self.params["gamma"], "gamma")
            self.H = _require_scalar(self.params["H"], "H")
            self.tau = _require_scalar(self.params["tau"], "tau")
            self.wac = _require_scalar(self.params["wac"], "wac")
        elif self.model == "nc2009":
            self.a = _require_scalar(self.params["a"], "a")
            self.ax = _require_scalar(self.params["ax"], "ax")
            self.ay = _require_scalar(self.params["ay"], "ay")
            self.az = _require_scalar(self.params["az"], "az")
            self.theta = _require_scalar(self.params["theta"], "theta")
            self.phi = _require_scalar(self.params["phi"], "phi")
            self.N = _require_scalar(self.params["N"], "N")
            self.wac = _require_scalar(self.params["wac"], "wac")

        self._omega_fine_grid = np.linspace(0.0, float(np.max(self.omega)), self._OMEGA_FINE_POINTS)
        self._kz_fine_grid = np.linspace(
            self._KZ_FINE_RANGE[0], self._KZ_FINE_RANGE[1], self._KZ_FINE_POINTS
        )

    def fmode_dispersion(self) -> np.ndarray:
        """Compute the f-mode dispersion curve omega(kh).

        Returns
        -------
        omega : numpy.ndarray
            Angular frequency for each kh in the grid (rad/s), computed as
            sqrt(g * kh).
        """
        omega = np.sqrt(self.g * np.asarray(self.kh, dtype=float))
        return omega

    def omega_poly(self, omega: ArrayLike, kh: ArrayLike):
        """Evaluate the model-specific dispersion polynomial in omega.

        Parameters
        ----------
        omega : array-like
            Angular frequency (rad/s). Must be real and finite.
        kh : array-like
            Horizontal wavenumber (km^-1). Must be real and finite.

        Returns
        -------
        poly : numpy.ndarray or numpy scalar
            Polynomial value(s) for the provided omega and kh.

        Notes
        -----
        This method does not solve for omega; it only evaluates the polynomial.
        """
        omega_arr = _require_real_array(omega, "omega")
        kh_arr = _require_real_array(kh, "kh")
        omega_arr, kh_arr = np.broadcast_arrays(omega_arr, kh_arr)

        cs = self.cs
        g = self.g

        if self.model == "sf1966":
            c4 = cs ** (-2)
            c3 = 0.0
            c2 = -(kh_arr ** 2 + self.wac ** 2 * cs ** (-2))
            c1 = 0.0
            c0 = self.N ** 2 * kh_arr ** 2
            poly = c4 * omega_arr ** 4 + c3 * omega_arr ** 3 + c2 * omega_arr ** 2 + c1 * omega_arr + c0
        elif self.model == "mt1981":
            c4 = cs ** (-2)
            c3 = 0.0
            c2 = -(kh_arr ** 2 + (4 * self.H ** 2) ** (-1))
            c1 = 0.0
            c0 = self.N ** 2 * kh_arr ** 2
            poly = c4 * omega_arr ** 4 + c3 * omega_arr ** 3 + c2 * omega_arr ** 2 + c1 * omega_arr + c0
        elif self.model in {"bunte1993", "mt1982"}:
            a = 0.0 if self.model == "mt1982" else self.a
            gamma = self.gamma
            H = self.H
            tau = self.tau
            cs2 = cs ** 2
            cs4 = cs2 ** 2
            a2 = a ** 2
            a4 = a2 ** 2
            kh2 = kh_arr ** 2
            kh4 = kh2 ** 2
            kh6 = kh4 * kh2

            c8 = 4 * H ** 2 * a2 * gamma ** 2 * tau ** 2 + 4 * H ** 2 * cs2 * gamma ** 2 * tau ** 2
            c7 = 0.0
            c6 = (
                -4 * H ** 2 * a4 * gamma ** 2 * kh2 * tau ** 2
                - 12 * H ** 2 * a2 * cs2 * gamma ** 2 * kh2 * tau ** 2
                + 4 * H ** 2 * a2 * gamma ** 2
                - 4 * H ** 2 * cs4 * gamma ** 2 * kh2 * tau ** 2
                + 4 * H ** 2 * cs2 * gamma
                - a4 * gamma ** 2 * tau ** 2
                - 2 * a2 * cs2 * gamma ** 2 * tau ** 2
                - cs4 * gamma ** 2 * tau ** 2
            )
            c5 = 0.0
            c4 = (
                8 * H ** 2 * a4 * cs2 * gamma ** 2 * kh4 * tau ** 2
                - 4 * H ** 2 * a4 * gamma ** 2 * kh2
                + 8 * H ** 2 * a2 * cs4 * gamma ** 2 * kh4 * tau ** 2
                - 12 * H ** 2 * a2 * cs2 * gamma * kh2
                - 4 * H ** 2 * a2 * g ** 2 * gamma ** 2 * kh2 * tau ** 2
                - 4 * H ** 2 * cs4 * kh2
                - 4 * H ** 2 * cs2 * g ** 2 * gamma ** 2 * kh2 * tau ** 2
                + 4 * H * a2 * cs2 * g * gamma ** 2 * kh2 * tau ** 2
                + 4 * H * cs4 * g * gamma ** 2 * kh2 * tau ** 2
                + 2 * a4 * cs2 * gamma ** 2 * kh2 * tau ** 2
                - a4 * gamma ** 2
                + 2 * a2 * cs4 * gamma ** 2 * kh2 * tau ** 2
                - 2 * a2 * cs2 * gamma
                - cs4
            )
            c3 = 0.0
            c2 = (
                -4 * H ** 2 * a4 * cs4 * gamma ** 2 * kh6 * tau ** 2
                + 8 * H ** 2 * a4 * cs2 * gamma * kh4
                + 8 * H ** 2 * a2 * cs4 * kh4
                + 4 * H ** 2 * a2 * cs2 * g ** 2 * gamma ** 2 * kh4 * tau ** 2
                - 4 * H ** 2 * a2 * g ** 2 * gamma ** 2 * kh2
                - 4 * H ** 2 * cs2 * g ** 2 * gamma * kh2
                - 4 * H * a2 * cs4 * g * gamma ** 2 * kh4 * tau ** 2
                + 4 * H * a2 * cs2 * g * gamma * kh2
                + 4 * H * cs4 * g * kh2
                - a4 * cs4 * gamma ** 2 * kh4 * tau ** 2
                + 2 * a4 * cs2 * gamma * kh2
                + 2 * a2 * cs4 * kh2
            )
            c1 = 0.0
            c0 = (
                -4 * H ** 2 * a4 * cs4 * kh6
                + 4 * H ** 2 * a2 * cs2 * g ** 2 * gamma * kh4
                - 4 * H * a2 * cs4 * g * kh4
                - a4 * cs4 * kh4
            )
            poly = (
                c8 * omega_arr ** 8
                + c7 * omega_arr ** 7
                + c6 * omega_arr ** 6
                + c5 * omega_arr ** 5
                + c4 * omega_arr ** 4
                + c3 * omega_arr ** 3
                + c2 * omega_arr ** 2
                + c1 * omega_arr
                + c0
            )
        elif self.model == "nc2009":
            c6 = 1.0
            c5 = 0.0
            c4 = -self.ax ** 2 * kh_arr ** 2 - self.a ** 2 * kh_arr ** 2 - cs ** 2 * kh_arr ** 2 - self.wac ** 2
            c3 = 0.0
            c2 = (
                self.N ** 2 * cs ** 2 * kh_arr ** 2
                + self.ax ** 4 * kh_arr ** 4
                + 2 * self.ax ** 2 * cs ** 2 * kh_arr ** 4
                + self.ay ** 2 * kh_arr ** 2 * self.wac ** 2
                + self.ax ** 2 * kh_arr ** 2 * self.wac ** 2
                + self.az ** 2 * kh_arr ** 2 * self.wac ** 2
            )
            c1 = 0.0
            c0 = (
                -self.N ** 2 * self.ax ** 2 * cs ** 2 * kh_arr ** 4
                - self.ax ** 4 * cs ** 2 * kh_arr ** 6
                - self.ax ** 2 * self.az ** 2 * kh_arr ** 4 * self.wac ** 2
            )
            poly = (
                c6 * omega_arr ** 6
                + c5 * omega_arr ** 5
                + c4 * omega_arr ** 4
                + c3 * omega_arr ** 3
                + c2 * omega_arr ** 2
                + c1 * omega_arr
                + c0
            )
        else:
            raise ValueError(
                "Model for omega polynomial not recognized. Please choose from "
                "'sf1966', 'mt1981', 'mt1982', 'bunte1993', 'nc2009'."
            )

        return _maybe_scalar(poly)

    def kz_poly(self, kz: ArrayLike, omega: ArrayLike, kh: ArrayLike):
        """Evaluate the model-specific polynomial in kz.

        Parameters
        ----------
        kz : array-like
            Vertical wavenumber (km^-1). Must be real and finite.
        omega : array-like
            Angular frequency (rad/s). Must be real, finite, and non-zero for
            models that include omega^-2 terms.
        kh : array-like
            Horizontal wavenumber (km^-1). Must be real and finite.

        Returns
        -------
        poly : numpy.ndarray or numpy scalar
            Polynomial value(s) for the provided kz, omega, and kh.

        Notes
        -----
        For models containing omega^-2 terms, omega must be non-zero to avoid
        division by zero.
        """
        kz_arr = _require_real_array(kz, "kz")
        omega_arr = _require_real_array(omega, "omega")
        kh_arr = _require_real_array(kh, "kh")
        kz_arr, omega_arr, kh_arr = np.broadcast_arrays(kz_arr, omega_arr, kh_arr)

        if np.any(omega_arr == 0.0) and self.model in {"sf1966", "mt1981", "mt1982"}:
            raise ValueError("omega must be non-zero for this kz polynomial.")
        if np.any(omega_arr == 0.0) and self.model == "bunte1993" and self.a == 0.0:
            raise ValueError("omega must be non-zero when a=0 for this kz polynomial.")

        cs = self.cs
        g = self.g

        if self.model == "sf1966":
            c2 = 1.0
            c1 = 0.0
            c0 = kh_arr ** 2 * (omega_arr ** 2 - self.N ** 2) * omega_arr ** (-2) - (
                omega_arr ** 2 - self.wac ** 2
            ) * cs ** (-2)
            poly = c2 * kz_arr ** 2 + c1 * kz_arr + c0
        elif self.model == "mt1981":
            c2 = 1.0
            c1 = 0.0
            c0 = (
                kh_arr ** 2
                + (4 * self.H ** 2) ** (-1)
                - self.N ** 2 * kh_arr ** 2 * omega_arr ** (-2)
                - omega_arr ** 2 * cs ** (-2)
            )
            poly = c2 * kz_arr ** 2 + c1 * kz_arr + c0
        elif self.model == "mt1982":
            c2 = 1.0
            c1 = 0.0
            gamma = self.gamma
            tau = self.tau
            H = self.H
            term_a = self.N ** 2 * kh_arr ** 2 * omega_arr ** (-2)
            term_b = omega_arr ** 2 * (gamma - 1) * cs ** (-2)
            denom = (omega_arr ** 2 * tau ** 2 + 1) ** (-1)
            denom2 = (omega_arr ** 2 * tau ** 2 + 1) ** (-2)
            sqrt_term = (
                omega_arr ** 2 * tau ** 2 * (-term_a + term_b) ** 2 * denom2
                + (
                    term_a
                    - kh_arr ** 2
                    + (-term_a + term_b) * denom
                    + omega_arr ** 2 * cs ** (-2)
                    - (4 * H ** 2) ** (-1)
                )
                ** 2
            ) ** 0.5
            c0 = -0.5 * (
                term_a
                - kh_arr ** 2
                + sqrt_term
                + (-term_a + term_b) * denom
                + omega_arr ** 2 * cs ** (-2)
                - (4 * H ** 2) ** (-1)
            )
            poly = c2 * kz_arr ** 2 + c1 * kz_arr + c0
        elif self.model == "bunte1993":
            a0 = self.a
            gamma_hat = (1 - 1j * omega_arr * self.tau * self.gamma) * (
                1 - 1j * omega_arr * self.tau
            ) ** (-1)
            c2_hat = cs ** 2 * gamma_hat
            n2_hat = (gamma_hat ** 2 - 1) * g * (gamma_hat * self.H) ** (-1)
            omega2_hat = c2_hat * (2 * self.H) ** (-1)
            p1 = (cs ** 2 + a0 ** 2) * omega_arr ** 2 - cs ** 2 * a0 ** 2 * kh_arr ** 2
            p_gamma = (cs ** 2 + self.gamma * a0 ** 2) * omega_arr ** 2 - cs ** 2 * a0 ** 2 * kh_arr ** 2
            g1 = omega_arr ** 4 + g ** 2 * (cs ** 2 * (g * self.H) ** (-1) - 1) * kh_arr ** 2
            g_gamma = self.gamma * omega_arr ** 4 + self.gamma * g ** 2 * (
                cs ** 2 * (self.gamma * g * self.H) ** (-1) - 1
            ) * kh_arr ** 2
            if self.a == 0:
                c2 = 1.0
                c1 = 0.0
                c0 = -(omega_arr ** 2 - omega2_hat) * (c2_hat) ** (-1) - kh_arr ** 2 * (
                    n2_hat * omega_arr ** (-2) - 1
                )
            else:
                c2 = 1.0
                c1 = 0.0
                c0 = (
                    (4 * self.H ** 2) ** (-1)
                    + kh_arr ** 2
                    - (p_gamma * g_gamma + (omega_arr * self.tau * self.gamma) ** 2 * p1 * g1)
                    * (p_gamma ** 2 + (omega_arr * self.tau * self.gamma) ** 2 * p1 ** 2) ** (-1)
                )
            poly = c2 * kz_arr ** 2 + c1 * kz_arr + c0
        elif self.model == "nc2009":
            sin_th = np.sin(self.theta)
            cos_th = np.cos(self.theta)
            cos_phi = np.cos(self.phi)

            c6 = -self.a ** 4 * cs ** 2 * cos_th ** 4
            c5 = -4 * kh_arr * self.a ** 4 * cs ** 2 * sin_th * cos_phi * cos_th ** 3
            c4 = (
                -6 * kh_arr ** 2 * self.a ** 4 * cs ** 2 * sin_th ** 2 * cos_phi ** 2 * cos_th ** 2
                - kh_arr ** 2 * self.a ** 4 * cs ** 2 * cos_th ** 4
                + omega_arr ** 2 * self.a ** 4 * cos_th ** 2
                + 2 * omega_arr ** 2 * self.a ** 2 * cs ** 2 * cos_th ** 2
                - self.a ** 2 * self.az ** 2 * self.wac ** 2 * cos_th ** 2
            )
            c3 = (
                -4 * kh_arr ** 3 * self.a ** 4 * cs ** 2 * sin_th ** 3 * cos_phi ** 3 * cos_th
                - 4 * kh_arr ** 3 * self.a ** 4 * cs ** 2 * sin_th * cos_phi * cos_th ** 3
                + 2 * kh_arr * omega_arr ** 2 * self.a ** 4 * sin_th * cos_phi * cos_th
                + 4 * kh_arr * omega_arr ** 2 * self.a ** 2 * cs ** 2 * sin_th * cos_phi * cos_th
                - 2 * kh_arr * self.a ** 2 * self.az ** 2 * self.wac ** 2 * sin_th * cos_phi * cos_th
            )
            c2 = (
                -kh_arr ** 4 * self.a ** 4 * cs ** 2 * sin_th ** 4 * cos_phi ** 4
                - 6 * kh_arr ** 4 * self.a ** 4 * cs ** 2 * sin_th ** 2 * cos_phi ** 2 * cos_th ** 2
                + kh_arr ** 2 * omega_arr ** 2 * self.a ** 4 * sin_th ** 2 * cos_phi ** 2
                + kh_arr ** 2 * omega_arr ** 2 * self.a ** 4 * cos_th ** 2
                + 2 * kh_arr ** 2 * omega_arr ** 2 * self.a ** 2 * cs ** 2 * sin_th ** 2 * cos_phi ** 2
                + 2 * kh_arr ** 2 * omega_arr ** 2 * self.a ** 2 * cs ** 2 * cos_th ** 2
                - kh_arr ** 2 * self.N ** 2 * self.a ** 2 * cs ** 2 * cos_th ** 2
                - kh_arr ** 2 * self.a ** 2 * self.az ** 2 * self.wac ** 2 * sin_th ** 2 * cos_phi ** 2
                - kh_arr ** 2 * self.a ** 2 * self.az ** 2 * self.wac ** 2 * cos_th ** 2
                - omega_arr ** 4 * self.a ** 2 * cos_th ** 2
                - omega_arr ** 4 * self.a ** 2
                - omega_arr ** 4 * cs ** 2
                + omega_arr ** 2 * self.a ** 2 * self.wac ** 2 * cos_th ** 2
                + omega_arr ** 2 * self.az ** 2 * self.wac ** 2
            )
            c1 = (
                -4 * kh_arr ** 5 * self.a ** 4 * cs ** 2 * sin_th ** 3 * cos_phi ** 3 * cos_th
                + 2 * kh_arr ** 3 * omega_arr ** 2 * self.a ** 4 * sin_th * cos_phi * cos_th
                + 4 * kh_arr ** 3 * omega_arr ** 2 * self.a ** 2 * cs ** 2 * sin_th * cos_phi * cos_th
                - 2 * kh_arr ** 3 * self.N ** 2 * self.a ** 2 * cs ** 2 * sin_th * cos_phi * cos_th
                - 2 * kh_arr ** 3 * self.a ** 2 * self.az ** 2 * self.wac ** 2 * sin_th * cos_phi * cos_th
                - 2 * kh_arr * omega_arr ** 4 * self.a ** 2 * sin_th * cos_phi * cos_th
                + 2 * kh_arr * omega_arr ** 2 * self.a ** 2 * self.wac ** 2 * sin_th * cos_phi * cos_th
            )
            c0 = (
                -kh_arr ** 6 * self.a ** 4 * cs ** 2 * sin_th ** 4 * cos_phi ** 4
                + kh_arr ** 4 * omega_arr ** 2 * self.a ** 4 * sin_th ** 2 * cos_phi ** 2
                + 2 * kh_arr ** 4 * omega_arr ** 2 * self.a ** 2 * cs ** 2 * sin_th ** 2 * cos_phi ** 2
                - kh_arr ** 4 * self.N ** 2 * self.a ** 2 * cs ** 2 * sin_th ** 2 * cos_phi ** 2
                - kh_arr ** 4 * self.a ** 2 * self.az ** 2 * self.wac ** 2 * sin_th ** 2 * cos_phi ** 2
                - kh_arr ** 2 * omega_arr ** 4 * self.a ** 2 * sin_th ** 2 * cos_phi ** 2
                - kh_arr ** 2 * omega_arr ** 4 * self.a ** 2
                - kh_arr ** 2 * omega_arr ** 4 * cs ** 2
                + kh_arr ** 2 * omega_arr ** 2 * self.N ** 2 * cs ** 2
                + kh_arr ** 2 * omega_arr ** 2 * self.a ** 2 * self.wac ** 2 * sin_th ** 2 * cos_phi ** 2
                + kh_arr ** 2 * omega_arr ** 2 * self.ay ** 2 * self.wac ** 2
                + kh_arr ** 2 * omega_arr ** 2 * self.az ** 2 * self.wac ** 2
                + omega_arr ** 6
                - omega_arr ** 4 * self.wac ** 2
            )
            poly = (
                c6 * kz_arr ** 6
                + c5 * kz_arr ** 5
                + c4 * kz_arr ** 4
                + c3 * kz_arr ** 3
                + c2 * kz_arr ** 2
                + c1 * kz_arr
                + c0
            )
        else:
            raise ValueError(
                "Model for kz polynomial not recognized. Please choose from "
                "'sf1966', 'mt1981', 'mt1982', 'bunte1993', 'nc2009'."
            )

        return _maybe_scalar(poly)

    def omega_solve(self, kh: ArrayLike) -> np.ndarray:
        """Find omega roots for a single kh by bracketing sign changes.

        Parameters
        ----------
        kh : float
            Horizontal wavenumber (km^-1).

        Returns
        -------
        omega_bounds : numpy.ndarray
            Roots of the omega polynomial, length omega_order. Missing roots
            are returned as zeros for backwards compatibility.
        """
        kh_scalar = _require_scalar(kh, "kh")

        fine_grid = self._omega_fine_grid
        poly = self.omega_poly(fine_grid, kh_scalar)
        if np.iscomplexobj(poly) and not np.allclose(np.imag(poly), 0.0):
            raise ValueError("omega_poly returned complex values; brentq requires real roots.")
        poly = np.real(poly)

        sign_changes = np.nonzero(np.diff(np.sign(poly)))[0]
        if sign_changes.size > self.omega_order:
            raise ValueError(
                "Found more omega sign changes than omega_order. "
                "Increase omega_order or adjust the omega grid."
            )

        roots = np.zeros(self.omega_order)
        for ind, idx in enumerate(sign_changes):
            A0, B0 = fine_grid[idx], fine_grid[idx + 1]
            try:
                root = optimize.brentq(self.omega_poly, A0, B0, args=(kh_scalar,))
                roots[ind] = root
            except ValueError:
                roots[ind] = np.nan

        return np.nan_to_num(roots, nan=0.0)

    def kz_solve(self, kh: ArrayLike) -> np.ndarray:
        """Solve for kz roots across the omega grid for a single kh.

        Parameters
        ----------
        kh : float
            Horizontal wavenumber (km^-1).

        Returns
        -------
        roots : numpy.ndarray
            Array of shape (len(omega), kz_order) with roots for each omega.
            Missing roots are returned as zeros for backwards compatibility.
        """
        kh_scalar = _require_scalar(kh, "kh")

        fine_grid = self._kz_fine_grid
        roots = np.full((len(self.omega), self.kz_order), np.nan)

        for j, omega_j in enumerate(self.omega):
            poly = self.kz_poly(fine_grid, omega_j, kh_scalar)
            if np.iscomplexobj(poly) and not np.allclose(np.imag(poly), 0.0):
                raise ValueError(
                    "kz_poly returned complex values; brentq requires real roots."
                )
            poly = np.real(poly)

            sign_changes = np.nonzero(np.diff(np.sign(poly)))[0]
            if sign_changes.size > self.kz_order:
                roots[j, :] = np.nan
                continue

            for ind, idx in enumerate(sign_changes):
                A0, B0 = fine_grid[idx], fine_grid[idx + 1]
                try:
                    root = optimize.brentq(self.kz_poly, A0, B0, args=(omega_j, kh_scalar))
                    roots[j, ind] = root
                except ValueError:
                    roots[j, ind] = np.nan

        return np.nan_to_num(roots, nan=0.0)

    def phase_speed(self, omega: ArrayLike, kz: ArrayLike):
        """Compute phase speed v_phase = omega / kz.

        Parameters
        ----------
        omega : array-like
            Angular frequency (rad/s). Must be real and finite.
        kz : array-like
            Vertical wavenumber (km^-1). Must be real and finite.

        Returns
        -------
        v_phase : numpy.ndarray or numpy scalar
            Phase speed (km/s). Division by zero yields +/-inf.
        """
        omega_arr = _require_real_array(omega, "omega")
        kz_arr = _require_real_array(kz, "kz")
        omega_arr, kz_arr = np.broadcast_arrays(omega_arr, kz_arr)
        v_phase = omega_arr * kz_arr ** (-1)
        return _maybe_scalar(v_phase)

    def phase_difference(self, omega: ArrayLike, v_phase: ArrayLike, dz: ArrayLike):
        """Compute phase difference between two heights.

        Parameters
        ----------
        omega : array-like
            Angular frequency (rad/s). Must be real and finite.
        v_phase : array-like
            Phase speed (km/s). Must be real and finite.
        dz : float
            Height separation (km).

        Returns
        -------
        delta_phi : numpy.ndarray or numpy scalar
            Phase difference (rad). Division by zero yields +/-inf.
        """
        omega_arr = _require_real_array(omega, "omega")
        v_phase_arr = _require_real_array(v_phase, "v_phase")
        dz_scalar = _require_scalar(dz, "dz")

        omega_arr, v_phase_arr = np.broadcast_arrays(omega_arr, v_phase_arr)
        delta_phi = omega_arr * dz_scalar * v_phase_arr ** (-1)
        return _maybe_scalar(delta_phi)
