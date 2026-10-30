'''
Purpose
-------
Load unit-checked matched atmospheric snapshots and derive representative model inputs
over selected physical height intervals.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for atmospheric_profiles.py.

Notes
-----
Shared, unit-checked snapshot profiles and height-interval model inputs.

No dispersion equations live here. The thermal HDF5 and magnetic/density cube
profiles belong to the same Model and exact snapshot. Heights use the existing
pipeline origin xc3[0]; that origin is not a claim about optical depth unity.
'''
from __future__ import annotations
# Import the libraries and shared helpers used by this module
from output_paths import json_output_path, json_sidecar_path, find_json_sidecar, product_from_json_sidecar
from data_locations import current_source_path, source_identity_path

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

try:
    import netCDF4
except ModuleNotFoundError:
    netCDF4 = None
import numpy as np
from scipy.integrate import quad

VERSION = 2
ALGORITHM_VERSION = 3
MU0 = 4.0*np.pi*1e-7
UNITS = dict(a='km/s', cs='km/s', N2='s^-2', wac='rad/s', H='km',
             gamma='dimensionless', g='km/s^2', tau='s', dz='km',
             theta_deg='deg', phi_deg='deg')
THERMAL_FIELDS = dict(cs='sound_speed', gamma_profile='adiabatic_index',
    N_stored='brunt_vaisala_freq', a_stored='alfven_speed', wac='acoustic_cutoff_freq_isothermal',
    wac_nonisothermal='acoustic_cutoff_freq_non_isothermal', temperature='temperature')
MISSING_INPUTS = dict(
    gamma='The profile adiabatic_index has no verified Cp/Cv definition; not substituted for the radiative models’ specific-heat ratio.',
    tau='Radiative relaxation time is not supplied by these profiles.',
    g='Gravity is not supplied by these profiles; retain the authoritative model constant.')


class ProfileError(ValueError):
    '''
    Purpose
    -------
    Represent missing, inconsistent, unsupported, or nonphysical atmospheric profile
    data.

    Inputs
    ------
    None

    Outputs
    -------
    exception: ProfileError
        ValueError subclass carrying the profile-validation explanation.
    '''

    pass


def _grid(z, q):
    '''
    Purpose
    -------
    Validate a one-dimensional profile grid and orient it toward increasing height.

    Inputs
    ------
    z: array-like
        Finite strictly monotonic height coordinates.
    q: array-like
        Matching scalar profile samples; nonfinite values are retained for interval
        checks.

    Outputs
    -------
    z, q: tuple of np.ndarray
        Increasing coordinate and matching profile, reversed together when needed;
        invalid coordinate shapes/order raise ProfileError.
    '''

    # Validate a one-dimensional profile grid and orient it toward increasing height
    z, q = np.asarray(z, float), np.asarray(q, float)
    if z.ndim != 1 or q.shape != z.shape or len(z) < 2 or not np.isfinite(z).all():
        raise ProfileError('A finite one-dimensional height coordinate and matching profile are required.')
    if np.all(np.diff(z) < 0):
        z, q = z[::-1], q[::-1]
    if not np.all(np.diff(z) > 0):
        raise ProfileError('Profile heights must be strictly monotonic, without duplicates.')
    return z, q


def interval_samples(z, q, z1, z2):
    '''
    Purpose
    -------
    Insert exact interval endpoints without extrapolating across missing profile values.

    Inputs
    ------
    z: array-like
        Native profile coordinates in consistent height units.
    q: array-like
        Scalar profile samples matching z.
    z1: float
        First selected height in the units of z.
    z2: float
        Second selected height in the units of z.

    Outputs
    -------
    points, values: tuple of np.ndarray
        Increasing interval knots and linearly interpolated profile values; out-of-range
        intervals or nonfinite samples raise ProfileError.

    Notes
    -----
    Insert exact endpoints, without extrapolating or bridging invalid cells.
    '''
    # Insert exact interval endpoints without extrapolating across missing profile
    # values
    z, q = _grid(z, q)
    lo, hi = sorted((float(z1), float(z2)))
    if not np.isfinite([lo, hi]).all() or lo < z[0] or hi > z[-1]:
        raise ProfileError(f'Interval [{lo:g}, {hi:g}] lies outside [{z[0]:g}, {z[-1]:g}].')
    points = np.unique(np.r_[lo, z[(z > lo) & (z < hi)], hi])
    values = np.interp(points, z, q)
    if not np.isfinite(values).all():
        raise ProfileError('Interval intersects missing/invalid profile values; they cannot be skipped.')
    return points, values


def interval_average(z, q, z1, z2):
    '''
    Purpose
    -------
    Average a piecewise-linear sampled profile over its exact selected height interval.

    Inputs
    ------
    z: array-like
        Native profile heights.
    q: array-like
        Scalar quantity sampled at z.
    z1: float
        First interval endpoint in z units.
    z2: float
        Second interval endpoint in z units.

    Outputs
    -------
    average: float
        Trapezoidal integral divided by absolute interval width, or the interpolated
        point value for zero separation.

    Notes
    -----
    Exact integral of the piecewise-linear sampled profile, or point value.
    '''
    # Average a piecewise-linear sampled profile over its exact selected height interval
    points, values = interval_samples(z, q, z1, z2)
    return float(values[0] if len(points) == 1 else np.trapz(values, points)/(points[-1]-points[0]))


def alfven_speed(bx, by, bz, rho, *, magnetic_unit='G', density_unit='gm/cm^3'):
    '''
    Purpose
    -------
    Compute physical Alfven speed after explicit magnetic-field and density conversion
    to SI.

    Inputs
    ------
    bx: array-like
        Cartesian x magnetic component in magnetic_unit.
    by: array-like
        Cartesian y magnetic component in magnetic_unit.
    bz: array-like
        Cartesian z magnetic component in magnetic_unit.
    rho: array-like
        Positive mass density in density_unit.
    magnetic_unit: str
        Supported G/gauss/T unit convention.
    density_unit: str
        Supported cgs or SI mass-density unit convention.

    Outputs
    -------
    speed: np.ndarray
        Broadcast Alfven speed in km/s; unsupported units, nonfinite inputs, or
        nonpositive density raise ProfileError.

    Notes
    -----
    Return km/s, converting the explicitly declared field/density units to SI.
    '''
    # Compute physical Alfven speed after explicit magnetic-field and density conversion
    # to SI
    magnetic = {'G': 1e-4, 'gauss': 1e-4, 'T': 1.}.get(magnetic_unit)
    density = {'gm/cm^3': 1e3, 'g/cm^3': 1e3, 'g cm-3': 1e3,
               'kg/m^3': 1., 'kg m-3': 1.}.get(density_unit)
    if magnetic is None or density is None:
        raise ProfileError('Unsupported or absent magnetic-field/density units.')
    bx, by, bz, rho = np.broadcast_arrays(*[np.asarray(v, float) for v in (bx, by, bz, rho)])
    if not all(np.isfinite(v).all() for v in (bx, by, bz, rho)) or np.any(rho <= 0):
        raise ProfileError('Alfvén speed requires finite components and positive finite density.')
    return np.sqrt(bx*bx+by*by+bz*bz)*magnetic/np.sqrt(MU0*rho*density)/1000.


def _functional_average(z, arrays, z1, z2, function):
    '''
    Purpose
    -------
    Integrate a nonlinear function of interpolated linear profiles before height
    averaging.

    Inputs
    ------
    z: np.ndarray
        Increasing native interpolation knots.
    arrays: sequence of np.ndarray
        Matching scalar profiles passed to function after separate interpolation.
    z1: float
        First integration endpoint in z units.
    z2: float
        Second integration endpoint in z units.
    function: callable
        Scalar function receiving the interpolated profile values.

    Outputs
    -------
    average: float
        Adaptive-quadrature interval mean, or the function value for a zero-width
        interval; input interval validation errors propagate.

    Notes
    -----
    Integrate a nonlinear function of linear profiles, before averaging it.
    '''
    # Integrate a nonlinear function of interpolated linear profiles before height
    # averaging
    for q in arrays:
        interval_samples(z, q, z1, z2)
    lo, hi = sorted((float(z1), float(z2)))
    def at(height):
        '''
        Purpose
        -------
        Evaluate the nonlinear profile function at one integration height.

        Inputs
        ------
        height: float
            Integration coordinate in the enclosing profile height units.

        Outputs
        -------
        value: float
            Function applied to separately interpolated profile values.
        '''

        # Evaluate the nonlinear profile function at one integration height
        return float(function(*[np.interp(height, z, q) for q in arrays]))
    if lo == hi:
        return at(lo)
    knots = np.r_[lo, z[(z > lo) & (z < hi)], hi]
    total = sum(quad(at, left, right, epsabs=1e-10, epsrel=1e-10)[0]
                for left, right in zip(knots[:-1], knots[1:]))
    return float(total/(hi-lo))


def _version(path):
    '''
    Purpose
    -------
    Record the verified original source label and current file version.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.

    Outputs
    -------
    version: tuple
        Original identity path, current byte size, and nanosecond modification time.
    '''

    # Record the verified original source label and current file version
    path = current_source_path(path)
    stat = path.stat()
    return str(source_identity_path(path)), stat.st_size, stat.st_mtime_ns


def _source(path, *, content_hash=False):
    '''
    Purpose
    -------
    Describe a current atmospheric source with stable identity and optional content
    checksum.

    Inputs
    ------
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    content_hash: bool
        Read complete source bytes and add their checksum when True.

    Outputs
    -------
    record: dict
        Original/current paths, size, mtime, and optional SHA-256 checksum.
    '''

    # Describe a current atmospheric source with stable identity and optional content
    # checksum
    path = current_source_path(path)
    name, size, modified = _version(path)
    record = dict(path=name, size_bytes=size, mtime_ns=modified)
    record['current_path'] = str(current_source_path(path))
    if content_hash:
        record['sha256'] = sha256(Path(path).read_bytes()).hexdigest()
    return record


def _length_km(values, units):
    '''
    Purpose
    -------
    Convert explicitly declared native length units to kilometers.

    Inputs
    ------
    values: array-like
        Native length coordinates.
    units: str
        Supported cm, m, km, or Mm unit label.

    Outputs
    -------
    heights: np.ndarray
        Floating-point coordinates in km; absent/unsupported units raise ProfileError.
    '''

    # Convert explicitly declared native length units to kilometers
    factor = {'cm': 1e-5, 'm': 1e-3, 'km': 1., 'Mm': 1e3}.get(units)
    if factor is None:
        raise ProfileError(f'Height units must be explicit and supported: {units!r}.')
    return np.asarray(values, float)*factor


def _horizontal_profile(variable, frame):
    '''
    Purpose
    -------
    Extract a matched cube frame and average its supported horizontal dimensions.

    Inputs
    ------
    variable: netCDF4.Variable
        Field with supported time/xc3/xc2/xc1 dimensions.
    frame: int
        Exact snapshot time index selected from the time dimension.

    Outputs
    -------
    profile: np.ndarray
        Vertical xc3 profile; missing cells remain invalid through ordinary means and
        unsupported dimension names raise ProfileError.
    '''

    # Extract a matched cube frame and average its supported horizontal dimensions
    selectors = [frame if dim == 'time' else slice(None) for dim in variable.dimensions]
    value = np.ma.filled(variable[tuple(selectors)], np.nan).astype(float)
    dimensions = [dim for dim in variable.dimensions if dim != 'time']
    if 'xc3' not in dimensions or any(dim not in {'xc3', 'xc2', 'xc1'} for dim in dimensions):
        raise ProfileError(f'Unsupported profile dimensions: {variable.dimensions}.')
    # Missing cells invalidate a horizontal mean, rather than silently changing
    # its spatial support. Already horizontally averaged rho is kept as stored.
    axes = tuple(i for i, dim in enumerate(dimensions) if dim != 'xc3')
    return np.mean(value, axis=axes) if axes else value


@dataclass(frozen=True)
class AtmosphericProfiles:
    '''
    Purpose
    -------
    Hold matched thermal, magnetic, density, and provenance profiles on their native
    physical grids.

    Inputs
    ------
    model: str
        Verified simulation Model identity.
    height_km: np.ndarray
        Common increasing thermal/derived coordinate in km relative to xc3[0].
    quantities: dict
        Native/interpolated scalar profiles with units documented by UNITS and
        provenance.
    cube_height_km: np.ndarray
        Simulation cube cell-center heights in km using the same origin.
    components_G: tuple of np.ndarray
        Horizontally averaged physical magnetic components in gauss on the cube grid.
    density_cgs: np.ndarray
        Cube-grid density in g/cm^3.
    provenance: dict
        Snapshot identity, source units/versions, derivations, and limitations.
    density_height_km: np.ndarray or None
        Optional matched native density coordinate in km.
    density_native_cgs: np.ndarray or None
        Optional matched native density samples in g/cm^3.

    Outputs
    -------
    profiles: AtmosphericProfiles
        Frozen profile container used for interval defaults and diagnostic exports.
    '''

    model: str
    height_km: np.ndarray
    quantities: dict
    cube_height_km: np.ndarray
    components_G: tuple
    density_cgs: np.ndarray
    provenance: dict
    density_height_km: np.ndarray | None = None
    density_native_cgs: np.ndarray | None = None

    def samples(self):
        '''
        Purpose
        -------
        Serialize sampled atmospheric profiles without nonfinite JSON numeric values.

        Inputs
        ------
        None

        Outputs
        -------
        samples: dict
            Physical coordinates and profile lists; unavailable numeric values are
            represented by None.
        '''

        # Serialize sampled atmospheric profiles without nonfinite JSON numeric values
        def finite(values):
            '''
            Purpose
            -------
            Convert one numeric profile to a JSON-safe list with unavailable values as
            None.

            Inputs
            ------
            values: np.ndarray
                Numeric sampled profile to serialize.

            Outputs
            -------
            values: list
                Original finite numbers with nonfinite entries replaced by None.
            '''

            # Convert one numeric profile to a JSON-safe list with unavailable values as
            # None
            return np.where(np.isfinite(values), values, None).tolist()
        return dict(height_km=self.height_km.tolist(),
            quantities={key: finite(values) for key, values in self.quantities.items() if key != 'H'},
            cube_height_km=self.cube_height_km.tolist(),
            components_G=[finite(values) for values in self.components_G],
            density_cgs=finite(self.density_cgs), density_scale_height_km=finite(self.quantities['H']),
            density_scale_height_coordinate_km=self.height_km.tolist(),
            density_height_km=(self.density_height_km if self.density_height_km is not None else self.cube_height_km).tolist(),
            density_native_cgs=finite(self.density_native_cgs if self.density_native_cgs is not None else self.density_cgs))

    def parameters(self, z1, z2):
        '''
        Purpose
        -------
        Derive representative physical model inputs over one exact selected height
        interval.

        Inputs
        ------
        z1: float
            First selected cube-layer height in km.
        z2: float
            Second selected cube-layer height in km.

        Outputs
        -------
        record: dict
            Available scalar parameters, units, source descriptions, unavailable-input
            reasons, and limitations. Magnetic direction uses the height-integrated unit
            vector; no exact stratified solution is claimed.
        '''

        # Derive representative physical model inputs over one exact selected height
        # interval
        parameters = dict(dz=abs(float(z2)-float(z1)))
        unavailable = dict(MISSING_INPUTS, **self.provenance.get('unavailable_inputs', {}))
        sources = dict(dz='absolute separation of the selected cube-layer centres')
        for key in ('cs', 'N2', 'wac', 'H'):
            try:
                z = self.height_km
                _, samples = interval_samples(z, self.quantities[key], z1, z2)
                if (key != 'N2' and np.any(samples < 0)) or (key in {'cs', 'H'} and np.any(samples == 0)):
                    raise ProfileError(f'Nonphysical {key} in the selected interval.')
                value = interval_average(z, self.quantities[key], z1, z2)
                parameters[key] = value
                sources[key] = ('density scale height -1/(d ln rho/dz), derived before averaging'
                    if key == 'H' else ('height integral of signed -g*d(ln rho)/dz - g²/cs², derived before averaging'
                    if key == 'N2' else 'height integral of cs/(2 H_rho), locally isothermal cutoff'
                    if key == 'wac' else f'height integral of {THERMAL_FIELDS[key]}'))
            except (KeyError, ProfileError) as exc:
                unavailable.setdefault(key, f'Required {key} profile is missing.' if isinstance(exc, KeyError) else str(exc))
        try:
            if 'a' in self.quantities:
                _, samples = interval_samples(self.height_km, self.quantities['a'], z1, z2)
                if np.any(samples < 0):
                    raise ProfileError('Nonphysical Alfven speed in the selected interval.')
                parameters['a'] = interval_average(self.height_km, self.quantities['a'], z1, z2)
                sources['a'] = 'height integral of supplied horizontal mean of local Alfven speed; cm/s to km/s, native thermal grid'
            if 'a' not in parameters:
                density_z = self.density_height_km if self.density_height_km is not None else self.cube_height_km
                density = self.density_native_cgs if self.density_native_cgs is not None else self.density_cgs
                # Include every density knot inside the magnetic grid. Interpolate
                # components and density separately before applying the nonlinear
                # Alfven formula; do not replace rho by a bin/global mean.
                lo, hi = self.cube_height_km[[0, -1]]
                field_z = np.unique(np.r_[self.cube_height_km, density_z[(density_z > lo) & (density_z < hi)]])
                _, _ = interval_samples(density_z, density, lo, hi)
                fields = [np.interp(field_z, self.cube_height_km, value) for value in self.components_G]
                rho = np.interp(field_z, density_z, density)
                parameters['a'] = _functional_average(field_z, (*fields, rho), z1, z2, alfven_speed)
                sources['a'] = 'integral of |B(z)|/sqrt(mu0*rho(z)); matched native density when available, cube component interpolation, adaptive quadrature'
            if parameters['a'] == 0.:
                parameters.update(theta_deg=0., phi_deg=0.)
                sources.update(theta_deg='direction undefined at zero field; solver-neutral zero',
                               phi_deg='direction undefined at zero field; solver-neutral zero')
            else:
                def unit_component(index):
                    '''
                    Purpose
                    -------
                    Average one magnetic unit-vector component over the selected height
                    interval.

                    Inputs
                    ------
                    index: int
                        Cartesian component index 0, 1, or 2.

                    Outputs
                    -------
                    average: float
                        Height mean of the selected normalized field component.
                    '''

                    # Average one magnetic unit-vector component over the selected
                    # height interval
                    def component(*field):
                        '''
                        Purpose
                        -------
                        Normalize one instantaneous magnetic component by the full
                        vector magnitude.

                        Inputs
                        ------
                        field: tuple of float
                            Interpolated Bx, By, and Bz values supplied as positional
                            arguments.

                        Outputs
                        -------
                        value: float
                            Selected Cartesian unit-vector component; a zero field at
                            this height raises ProfileError.
                        '''

                        # Normalize one instantaneous magnetic component by the full
                        # vector magnitude
                        norm = np.hypot(np.hypot(field[0], field[1]), field[2])
                        if norm == 0.:
                            raise ProfileError('Magnetic direction is undefined inside the interval.')
                        return field[index]/norm
                    return _functional_average(self.cube_height_km, self.components_G,
                                               z1, z2, component)
                direction = np.array([unit_component(i) for i in range(3)])
                if np.linalg.norm(direction) <= 1e-12:
                    raise ProfileError('Mean magnetic direction cancels; no unique representative orientation.')
                from vesa_support import support_module
                _, theta, phi = support_module('magnetic_geometry').orientation(*direction)
                parameters['theta_deg'], parameters['phi_deg'] = float(theta), float(phi)
                sources.update(theta_deg='direction of height-integrated unit vector, inclination from +z',
                               phi_deg='direction of height-integrated unit vector, atan2(By,Bx) from +x toward +y')
        except ProfileError as exc:
            for key in ('a', 'theta_deg', 'phi_deg'):
                if key not in parameters:
                    unavailable.setdefault(key, str(exc))
        return dict(schema_version=VERSION, status='available', model=self.model,
            height_pair_km=[float(z1), float(z2)], parameters=parameters,
            units={key: UNITS[key] for key in parameters}, parameter_sources=sources,
            unavailable=unavailable, provenance=self.provenance,
            averaging='height integral / absolute height separation; exact point value for zero separation',
            approximation='Locally uniform representative inputs, not an exact vertically stratified dispersion solution.')


def _supplemental_versions(reference):
    '''
    Purpose
    -------
    Find matched native density, pressure, and plasma-beta profile versions.

    Inputs
    ------
    reference: str or pathlib.Path
        Thermal *_atmos_param.h5 profile reference.

    Outputs
    -------
    versions: tuple
        Available field/version pairs derived from the thermal reference filename.
    '''

    # Find matched native density, pressure, and plasma-beta profile versions
    reference = current_source_path(reference)
    suffixes = dict(rho='density', pressure='pressure', plasma_beta='plasma_beta')
    return tuple((field, _version(path)) for field, suffix in suffixes.items()
                 if (path := Path(reference).with_name(Path(reference).name.replace(
                     '_atmos_param.h5', f'_{suffix}_profile.h5'))).is_file() and path != Path(reference))


def _snapshot_scalar(reference, path, model, snapshot, origin_km, field):
    '''
    Purpose
    -------
    Read one unit-checked scalar profile matching the thermal Model, snapshot, and
    native height coordinate.

    Inputs
    ------
    reference: str or pathlib.Path
        Thermal reference file supplying the matching native coordinate.
    path: str or pathlib.Path
        Filesystem path operated on by this helper.
    model: str
        Required Model identity.
    snapshot: float
        Required snapshot label time in seconds.
    origin_km: float
        Native cube xc3[0] origin subtracted from profile heights in km.
    field: str
        rho, pressure, or plasma_beta field to read and validate.

    Outputs
    -------
    height, values, source: tuple
        Heights in km relative to the cube origin, converted scalar samples, and
        checksummed provenance. Identity/units/grid mismatches raise ProfileError.

    Notes
    -----
    One unit-checked matched native profile, shared by models and diagnostics.
    '''
    # Read one unit-checked scalar profile matching the thermal Model, snapshot, and
    # native height coordinate
    reference, path = current_source_path(reference), current_source_path(path)
    from simulation_observables import profile_units
    with netCDF4.Dataset(path) as source, netCDF4.Dataset(reference) as thermal:
        if source.Model != model or float(source.snapshot_label_time_s) != snapshot:
            raise ProfileError(f'{field} profile Model/snapshot differs from thermal profile.')
        if source[field].dimensions != ('z',):
            raise ProfileError(f'{field} must be a one-dimensional native profile.')
        if not np.array_equal(source['z'][:], thermal['z'][:]):
            raise ProfileError(f'{field} native heights differ from thermal profile.')
        height = _length_km(source['z'][:], source['z'].units)-origin_km
        units = getattr(source[field], 'units', '')
        if field == 'rho':
            factor = {'gm/cm^3': 1., 'g/cm^3': 1., 'kg/m^3': 1e-3}.get(units)
            if factor is None:
                raise ProfileError('Native density units must be explicit and supported.')
            units = 'gm/cm^3'
        else:
            units, factor = profile_units(field, units)
        values = np.ma.filled(source[field][:], np.nan).astype(float)*factor
        _grid(height, values)
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise ProfileError(f'{field} profile requires positive finite values.')
    return height, values, dict(_source(path, content_hash=True), units=units)


@lru_cache(maxsize=24)
def _load_profiles(cube_version, profile_version, legacy_units_json, gravity_km_s2,
                   supplemental_versions=(), co5bold_magnetic_convention='internal'):
    '''
    Purpose
    -------
    Load matched snapshot profiles and derive physical stratification inputs before
    interval averaging.

    Inputs
    ------
    cube_version: tuple
        Original cube path, byte size, and mtime cache key.
    profile_version: tuple
        Thermal profile path, byte size, and mtime cache key.
    legacy_units_json: str
        Explicit verified legacy-unit mapping encoded as sorted JSON.
    gravity_km_s2: float
        Positive finite gravity magnitude used in signed N2/cutoff derivations.
    supplemental_versions: tuple
        Matched native density/pressure/beta source versions.
    co5bold_magnetic_convention: str
        internal or physical convention used for explicitly identified CO5BOLD fields.

    Outputs
    -------
    profiles: AtmosphericProfiles
        Cached thermal/magnetic/density profiles and detailed provenance. Unsupported
        identities, units, geometry, or snapshots raise ProfileError; unavailable
        individual fields are recorded explicitly.
    '''

    # Load matched snapshot profiles and derive physical stratification inputs before
    # interval averaging
    cube_path, profile_path = current_source_path(cube_version[0]), current_source_path(profile_version[0])
    legacy_units = json.loads(legacy_units_json)
    with netCDF4.Dataset(cube_path) as cube, netCDF4.Dataset(profile_path) as profile:
        model = str(getattr(cube, 'Model', '')).strip()
        if not model or not profile_path.name.startswith(model+'_'):
            raise ProfileError('Profile and cube Model identity disagree.')
        raw_cube_z = _length_km(cube['xc3'][:], cube['xc3'].units)
        origin = float(raw_cube_z[0])
        raw_profile_z = np.asarray(profile['z'][:], float)
        height_unit = getattr(profile['z'], 'units', '')
        if not height_unit:
            # Verify actual coordinate membership and centre means against the
            # unit-bearing native cell boundaries. Some cubes omit the binning
            # command from history; the coordinates themselves retain the bins.
            if 'xb3' not in cube.variables:
                raise ProfileError('Unitless profile z requires matching native cube cell boundaries.')
            edges = _length_km(cube['xb3'][:], cube['xb3'].units)*1e5
            if len(edges) != len(raw_cube_z)+1 or not np.all(np.diff(edges) > 0):
                raise ProfileError('Invalid cube cell boundaries for profile height validation.')
            groups = [raw_profile_z[(raw_profile_z >= left) & (raw_profile_z < right)]
                      for left, right in zip(edges[:-1], edges[1:])]
            if any(len(group) == 0 for group in groups):
                raise ProfileError('Unitless profile z does not sample every cube vertical bin.')
            binned = np.array([np.mean(group) for group in groups])
            cm_cube = raw_cube_z*1e5
            if not np.allclose(binned, cm_cube, rtol=1e-7, atol=10.):
                raise ProfileError('Unitless profile z is inconsistent with cube xc3 in centimetres.')
            height_unit = 'cm'
        height = _length_km(raw_profile_z, height_unit)-origin
        _grid(height, height)
        if height[0] > height[-1]:
            raise ProfileError('Profile order is inconsistent with the cube coordinate convention.')
        time_match = re.search(r'_t(\d+)s_', profile_path.name)
        if time_match is None:
            raise ProfileError('Profile snapshot time is missing.')
        snapshot = float(time_match[1])
        matches = np.flatnonzero(np.isclose(cube['time'][:], snapshot, rtol=0., atol=1e-6))
        if len(matches) != 1:
            raise ProfileError('The atmospheric-profile snapshot must match exactly one cube frame.')
        frame = int(matches[0])
        quantities, unit_sources = {}, {}
        for key, field in THERMAL_FIELDS.items():
            if field not in profile.variables:
                continue
            variable = profile[field]
            unit = getattr(variable, 'units', '') or legacy_units.get(field)
            expected = 'cm/s' if key in {'cs', 'a_stored'} else ('K' if key == 'temperature' else
                       ('dimensionless' if key == 'gamma_profile' else 'rad/s'))
            if key == 'a_stored' and not unit:
                continue
            if unit != expected:
                raise ProfileError(f'{field} units are absent or inconsistent: {unit!r}; expected {expected}.')
            values = np.ma.filled(variable[:], np.nan).astype(float)
            _grid(height, values)
            quantities[key] = values*(1e-5 if key in {'cs', 'a_stored'} else 1.)
            unit_sources[field] = dict(unit=unit, source='file attribute' if getattr(variable, 'units', '')
                                      else 'explicit atmospheric_profiles.legacy_units configuration')
        unavailable_inputs = {}
        rho_unit, density_cell_methods = '', ''
        try:
            if 'rho' not in cube.variables:
                raise ProfileError('Missing density variable rho.')
            rho_var = cube['rho']
            rho_unit = getattr(rho_var, 'units', '')
            density_cell_methods = getattr(rho_var, 'cell_methods', '')
            density_factor = {'gm/cm^3': 1., 'g/cm^3': 1., 'kg/m^3': 1e-3}.get(rho_unit)
            if density_factor is None:
                raise ProfileError('The cube density must have explicit supported units.')
            rho = _horizontal_profile(rho_var, frame)*density_factor
        except (KeyError, ProfileError) as exc:
            rho = np.full(raw_cube_z.shape, np.nan)
            for key in ('a', 'H', 'N2', 'wac'):
                unavailable_inputs[key] = 'Density profile unavailable: '+str(exc)
        components = []
        magnetic_convention = getattr(cube, 'magnetic_field_convention', '') or (
            co5bold_magnetic_convention if getattr(cube, 'SOLMETA_CREATOR', '') == 'CO5BOLD' else 'physical')
        if magnetic_convention not in {'internal', 'physical'}:
            raise ProfileError('Magnetic convention must be internal or physical.')
        magnetic_normalization = np.sqrt(4*np.pi) if magnetic_convention == 'internal' else 1.
        zero_field = (getattr(cube, 'ModelRefName', '') == 'Sun-v0' and
                      '0 G flux density' in getattr(cube, 'Description', ''))
        for name in ('bb1', 'bb2', 'bb3'):
            if name not in cube.variables:
                if not zero_field:
                    components.append(np.full_like(rho, np.nan))
                    for key in ('a', 'theta_deg', 'phi_deg'):
                        unavailable_inputs[key] = f'Missing magnetic component {name} in a nonzero/unknown-field simulation.'
                    continue
                components.append(np.zeros_like(rho))
                continue
            variable = cube[name]
            factor = {'G': 1., 'gauss': 1., 'T': 1e4}.get(getattr(variable, 'units', ''))
            if factor is None:
                components.append(np.full_like(rho, np.nan))
                for key in ('a', 'theta_deg', 'phi_deg'):
                    unavailable_inputs[key] = f'Magnetic component {name} has absent/unsupported units.'
                continue
            components.append(_horizontal_profile(variable, frame)*factor*magnetic_normalization)
        cube_height = raw_cube_z-origin
        _grid(cube_height, rho)
        native_profiles = {}
        density_z, density_native = cube_height, rho
        scalar_profiles = {}
        for field, version in supplemental_versions:
            native_z, values, source_record = _snapshot_scalar(
                profile_path, version[0], model, snapshot, origin, field)
            native_profiles[field] = source_record
            if field == 'rho':
                density_z, density_native = native_z, values
                # A native density profile is sufficient even when the cube
                # omits its old horizontally averaged density variable.
                for key in ('a', 'H', 'N2', 'wac'):
                    unavailable_inputs.pop(key, None)
            else:
                scalar_profiles[field] = (native_z, values)
        valid_rho = np.where(np.isfinite(density_native) & (density_native > 0), density_native, np.nan)
        gradient = np.gradient(np.log(valid_rho), density_z,
                               edge_order=2 if len(density_z)>2 else 1)
        if not np.isfinite(gravity_km_s2) or gravity_km_s2 <= 0:
            raise ProfileError('Gravity magnitude must be positive and finite.')
        # Differentiate native ln(rho) before interpolation or height averaging.
        # Include magnetic/cube knots so every model samples the same state.
        common = np.unique(np.r_[height, cube_height[(cube_height >= height[0]) & (cube_height <= height[-1])]])
        quantities = {key: np.interp(common, height, values) for key, values in quantities.items()}
        height = common
        slope = np.interp(height, density_z, gradient, left=np.nan, right=np.nan)
        quantities['rho'] = np.interp(height, density_z, density_native, left=np.nan, right=np.nan)
        quantities['H'] = np.divide(-1., slope, out=np.full_like(slope, np.nan), where=slope != 0)
        cs = quantities.get('cs', np.full_like(height, np.nan))
        valid_cs = np.where(cs > 0, cs, np.nan)
        quantities['N2'] = -gravity_km_s2*slope - gravity_km_s2**2/valid_cs**2
        quantities['wac_stored'] = quantities.get('wac', np.full_like(height, np.nan))
        quantities['wac'] = -valid_cs*slope/2.
        if 'a_stored' in quantities:
            quantities['a'] = quantities['a_stored'].copy()
            unavailable_inputs.pop('a', None)
        for field, (native_z, values) in scalar_profiles.items():
            quantities[field] = np.interp(height, native_z, values, left=np.nan, right=np.nan)
        # Pressure permits an independent hydrostatic-background check. Keep
        # it diagnostic: the requested NC relation uses Eq. 4 with true g;
        # do not tune gravity or substitute Cp/Cv with an effective Gamma1.
        if 'pressure' in scalar_profiles:
            pressure_z, pressure = scalar_profiles['pressure']
            edge_order = 2 if len(pressure_z)>2 else 1
            pressure_slope = np.gradient(np.log(pressure), pressure_z, edge_order=edge_order)
            pressure_gradient_si = np.gradient(pressure*.1, pressure_z*1000., edge_order=edge_order)
            pressure_slope = np.interp(height, pressure_z, pressure_slope)
            pressure_gradient_si = np.interp(height, pressure_z, pressure_gradient_si)
            quantities['pressure_scale_height'] = np.divide(-1., pressure_slope,
                out=np.full_like(pressure_slope, np.nan), where=pressure_slope != 0)
            quantities['Gamma1_effective'] = quantities['rho']*(valid_cs*1e5)**2/quantities['pressure']
            quantities['hydrostatic_gravity_km_s2'] = -pressure_gradient_si/(quantities['rho']*1000.)/1000.
            quantities['N2_pressure_gradient'] = gravity_km_s2*1000.*(
                pressure_gradient_si/(quantities['rho']*1000.*(valid_cs*1000.)**2)-slope/1000.)
        provenance = dict(cube=_source(cube_path), profile=_source(profile_path, content_hash=True),
            snapshot_time_s=snapshot, cube_frame=frame, source_model=model,
            height_origin_native_km=origin, height_coordinate='native xc3 minus xc3[0], as in the time_distance pipeline',
            height_units='km; unitless legacy profile z verified against recorded cube bins in cm',
            source_units=unit_sources, density_units=rho_unit, native_profiles=native_profiles,
            legacy_units=legacy_units, co5bold_magnetic_convention=co5bold_magnetic_convention,
            density_derivative_source='native unbinned density profile' if 'rho' in native_profiles else 'cube density; native profile absent',
            unit_contract_basis='User confirmed cm/s sound speed and rad/s frequencies on 2026-10-13. Temperature follows the notebook K-to-kK convention. The adiabatic-index diagnostic is dimensionless; its thermodynamic definition remains unverified.',
            magnetic_units=f'Cube fields converted to physical G; {magnetic_convention} convention, factor {magnetic_normalization:.17g}. CO5BOLD internal B/sqrt(4pi) follows the original MHD manual.',
            reduction='horizontal means of the exact profile snapshot; cube fields are already vertically binned',
            density_cell_methods=density_cell_methods, unavailable_inputs=unavailable_inputs,
            alfven_limitation=('Supplied native horizontal mean of local Alfven speeds; independently verified from a native staggered layer. Direction is still inferred from horizontally averaged cube components.' if 'a' in quantities else
                'Fallback Alfven speed of independently horizontally averaged components/density; not a horizontal mean of local speeds.'),
            temporal_limitation='One atmospheric snapshot represents the full time series used by the k–omega diagram.',
            vertical_limitation='Magnetic components retain the cube resolution; density derivatives use the native profile when supplied. Interpolation cannot recover unresolved magnetic structure.',
            scale_height_definition='H_rho = -1/(d ln rho/dz), nonuniform-coordinate gradient before height averaging',
            cutoff_definition='isothermal acoustic cutoff for the existing locally isothermal NC2009 relation; non-isothermal cutoff retained in diagnostics',
            buoyancy_definition='N2 = -g*d ln rho/dz - g²/cs² (Newington & Cally 2010 Eq. 4); signed s^-2',
            buoyancy_assumption='NC2010 Eq. 4 assumes a hydrostatic adiabatic background. Pressure-gradient buoyancy and hydrostatic gravity are diagnostic comparisons when pressure is supplied; dynamic snapshot averages need not obey hydrostatic balance. Gamma1_effective is not assumed to equal Cp/Cv.',
            gravity_km_s2=gravity_km_s2, gravity_source='explicit atmospheric_profiles.gravity_km_s2, default solar magnitude 0.274; absent from files',
            geometry='bb1=x=xc1, bb2=y=xc2, bb3=z=xc3 upward; x-z propagation plane is the xc1-xc3 plane',
            propagation_limitation='The k_h diagram is horizontally azimuth-averaged; phi is relative to the selected xc1 reference plane, not a measured unique propagation direction.',
            stored_frequency_limitation='Legacy real N does not encode signed N2; stored cutoff retained only for diagnostic comparison.',
            algorithm_version=ALGORITHM_VERSION)
    result = AtmosphericProfiles(model, height, quantities, cube_height, tuple(components), rho, provenance, density_z, density_native)
    provenance['sampled_profiles_sha256'] = sha256(json.dumps(result.samples(), sort_keys=True,
                                                           allow_nan=False).encode()).hexdigest()
    provenance['implementation_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def load_profiles(config):
    '''
    Purpose
    -------
    Resolve one uniquely matched thermal profile and load source-versioned atmospheric
    data.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.

    Outputs
    -------
    profiles: AtmosphericProfiles
        Matched cached profile container; missing netCDF4 or ambiguous Model/profile
        matches raise ProfileError.
    '''

    # Resolve one uniquely matched thermal profile and load source-versioned atmospheric
    # data
    if netCDF4 is None:
        raise ProfileError('Simulation atmospheric profiles require netCDF4.')
    settings = config.get('atmospheric_profiles', {})
    cube_path = current_source_path(config['data'].get('file') or config['data'].get('single_cube', {}).get('file', ''))
    with netCDF4.Dataset(cube_path) as cube:
        model = str(getattr(cube, 'Model', '')).strip()
    directory = Path(settings.get('directory', cube_path.parent.parent.parent/'co5bold_1d_profiles'))
    explicit = settings.get('model_files', {}).get(model)
    candidates = [current_source_path(explicit)] if explicit else sorted(directory.glob(model+'_*_atmos_param.h5')) if model else []
    if len(candidates) != 1:
        raise ProfileError(f'Expected one explicit atmospheric profile for Model {model!r}; found {len(candidates)}.')
    return _load_profiles(_version(cube_path), _version(candidates[0]),
                          json.dumps(settings.get('legacy_units', {}), sort_keys=True),
                          float(settings.get('gravity_km_s2', .274)), _supplemental_versions(candidates[0]),
                          settings.get('co5bold_magnetic_convention', 'internal'))


def save_diagnostic(profiles, figure_dir, *, height_pair_km=None):
    '''
    Purpose
    -------
    Publish matched native atmospheric diagnostic plots under an exclusive model lock.

    Inputs
    ------
    profiles: AtmosphericProfiles
        Validated matched snapshot data.
    figure_dir: str or pathlib.Path
        Diagnostic output directory created as needed.
    height_pair_km: sequence of two float or None
        Optional exact selected heights in km, included in plot identity and point
        markers.

    Outputs
    -------
    paths: list of pathlib.Path
        PDF and PNG diagnostic paths, reusing matching provenance when available.

    Notes
    -----
    Publish a native diagnostic, optionally marking an exact selected height pair.
    '''
    # Publish matched native atmospheric diagnostic plots under an exclusive model lock
    import file_lock as fcntl
    folder = Path(figure_dir).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/('.simulation_atmospheric_profiles_'+profiles.model+'.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return _save_diagnostic_locked(profiles, folder, height_pair_km=height_pair_km)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _diagnostic_scalar_profile(profiles, field):
    '''
    Purpose
    -------
    Load an optional matched scalar profile while retaining its native vertical grid.

    Inputs
    ------
    profiles: AtmosphericProfiles
        Validated thermal reference and snapshot provenance.
    field: str
        Supplemental pressure or plasma_beta field name.

    Outputs
    -------
    profile: tuple or None
        Heights in Mm, scalar values, and source provenance; None when the supplemental
        file is absent.

    Notes
    -----
    Read a separately retrieved snapshot, retaining its native vertical grid.
    '''
    # Load an optional matched scalar profile while retaining its native vertical grid
    reference = Path(profiles.provenance['profile']['path'])
    path = reference.with_name(reference.name.replace('_atmos_param.h5', f'_{field}_profile.h5'))
    if not path.is_file():
        return None
    height, values, source = _snapshot_scalar(reference, path, profiles.model,
        profiles.provenance['snapshot_time_s'], profiles.provenance['height_origin_native_km'], field)
    return height/1000., values, source


def _save_diagnostic_locked(profiles, figure_dir, *, height_pair_km=None):
    '''
    Purpose
    -------
    Render and atomically publish native profile diagnostic PDF/PNG files and
    provenance.

    Inputs
    ------
    profiles: AtmosphericProfiles
        Matched native profiles and physical source provenance.
    figure_dir: str or pathlib.Path
        Diagnostic destination directory.
    height_pair_km: sequence of two float or None
        Optional exact selected cube heights in km.

    Outputs
    -------
    paths: list of pathlib.Path
        Reused or newly written diagnostic products, plus a separate JSON
        sample/provenance manifest. Profile coverage or selected-height errors raise
        ProfileError.

    Notes
    -----
    Native speeds, frequencies, temperature/density, and pressure/beta.
    '''
    # Render and atomically publish native profile diagnostic PDF/PNG files and
    # provenance
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    folder = Path(figure_dir).expanduser().resolve()
    stem = folder/('simulation_atmospheric_profiles_'+profiles.model)
    if height_pair_km is not None:
        heights = np.asarray(height_pair_km, dtype=float)
        if (heights.shape != (2,) or not np.isfinite(heights).all()
                or np.any(heights < profiles.cube_height_km[0])
                or np.any(heights > profiles.cube_height_km[-1])):
            raise ProfileError('Diagnostic height pair must lie inside the simulation height range.')
        height_pair_km = heights.tolist()
        identity = sha256(json.dumps(height_pair_km).encode()).hexdigest()[:12]
        stem = stem.with_name(stem.name+'_heights_'+identity)
    paths = [stem.with_suffix(suffix) for suffix in ('.pdf', '.png')]
    manifest = json_output_path(stem.with_suffix('.json'))
    provenance = dict(profiles.provenance, diagnostic_layout_version=5)
    if height_pair_km is not None:
        provenance['diagnostic_height_pair_km'] = height_pair_km
    scalar_profiles = {key: _diagnostic_scalar_profile(profiles, key)
                       for key in ('pressure', 'plasma_beta')}
    provenance['diagnostic_thermodynamic_profiles'] = {
        key: record[2] if record else {'status': 'unavailable', 'reason': 'No matched stored profile file.'}
        for key, record in scalar_profiles.items()}
    density_path = Path(provenance['profile']['path']).with_name(
        Path(provenance['profile']['path']).name.replace('_atmos_param.h5', '_density_profile.h5'))
    density_z, density = profiles.cube_height_km/1000., profiles.density_cgs
    if density_path.is_file():
        with netCDF4.Dataset(density_path) as source, netCDF4.Dataset(provenance['profile']['path']) as thermal:
            if source.Model != profiles.model:
                raise ProfileError('Diagnostic density Model does not match atmospheric profile.')
            np.testing.assert_array_equal(source['z'][:], thermal['z'][:])
            if float(source.snapshot_label_time_s) != provenance['snapshot_time_s']:
                raise ProfileError('Diagnostic density snapshot does not match atmospheric profile.')
            if source['rho'].units not in {'gm/cm^3', 'g/cm^3'} or source['z'].units != 'cm':
                raise ProfileError('Diagnostic density requires cm heights and g/cm^3 density.')
            density_z = (_length_km(source['z'][:], 'cm')-provenance['height_origin_native_km'])/1000.
            density = np.asarray(source['rho'][:], float)
            _grid(density_z, density)
            if not np.isfinite(density).all() or np.any(density <= 0):
                raise ProfileError('Diagnostic density must be finite and positive.')
        provenance['diagnostic_density'] = _source(density_path, content_hash=True)
    provenance['diagnostic_height_alignment'] = dict(
        origin_native_km=provenance['height_origin_native_km'],
        displayed_range_km=(profiles.cube_height_km[[0, -1]]).tolist(),
        domain='simulation cell centres; common origin subtracted from all profiles',
        resampling='retain native profile samples and interpolate only display endpoints; no vertical binning')
    if manifest.is_file() and all(path.is_file() for path in paths):
        if json.loads(manifest.read_text()).get('provenance') == provenance:
            return paths
    folder.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({'text.usetex': False, 'font.family': 'serif', 'font.size': 11,
                         'axes.labelsize': 12, 'axes.titlesize': 13, 'legend.fontsize': 10,
                         'xtick.labelsize': 10, 'ytick.labelsize': 10,
                         'figure.facecolor': 'white', 'axes.facecolor': 'white',
                         'savefig.facecolor': 'white', 'pdf.fonttype': 42, 'ps.fonttype': 42}):
        fig = Figure(figsize=(24, 6), constrained_layout=True)
        FigureCanvasAgg(fig)
        axes = fig.subplots(1, 4)
        z, q = profiles.height_km/1000., profiles.quantities
        lo, hi = profiles.cube_height_km[[0, -1]]/1000.
        # Use one physical origin and the simulation's actual cell centres.
        # Never stretch the full-atmosphere grid to the truncated cube or let
        # np.interp silently clamp a profile that does not cover its domain.
        for name, coordinate in (('thermal', z), ('density', density_z)):
            if coordinate[0] > lo or coordinate[-1] < hi:
                raise ProfileError(f'{name.capitalize()} profile does not cover the simulation height range.')
        plotted_z = np.unique(np.r_[lo, z[(z > lo) & (z < hi)], hi])

        def plot_quantity(axis, key, scale, color, label):
            '''
            Purpose
            -------
            Plot an available scalar quantity on the exact shared diagnostic height
            interval.

            Inputs
            ------
            axis: matplotlib.axes.Axes
                Target diagnostic axis or twin axis.
            key: str
                Scalar profile key in the enclosing quantities dictionary.
            scale: float
                Multiplicative display-unit conversion.
            color: str
                Matplotlib line color.
            label: str
                Legend label for the quantity.

            Outputs
            -------
            None
                Adds a scaled profile line to axis only when the quantity key exists.
            '''

            # Plot an available scalar quantity on the exact shared diagnostic height
            # interval
            if key in q:
                axis.plot(plotted_z, np.interp(plotted_z, z, q[key])*scale,
                          color=color, label=label, linewidth=1.6)

        speed_twin = axes[0].twinx()
        plot_quantity(axes[0], 'cs', 1., 'blue', r'$c_s$')
        plot_quantity(speed_twin, 'gamma_profile', 1., 'red', r'$\gamma$')
        axes[0].set(ylabel='Sound speed [km/s]', title='Sound speed and adiabatic index')
        speed_twin.set_ylabel('Adiabatic index (profile)')

        # A real buoyancy frequency exists only where N² >= 0. Unstable
        # samples remain gaps; never take abs(N²) to manufacture a frequency.
        if 'N2' in q:
            n2 = np.interp(plotted_z, z, q['N2'])
            frequency = np.sqrt(np.where(n2 >= 0, n2, np.nan))*1e3/(2*np.pi)
            axes[1].plot(plotted_z, frequency, color='orange', label=r'$N/(2\pi)$ ($N^2\geq0$)', linewidth=1.6)
        plot_quantity(axes[1], 'wac_nonisothermal', 1e3/(2*np.pi), 'purple',
                      r'$\omega_{ac}/(2\pi)$ (non-isothermal)')
        plot_quantity(axes[1], 'wac', 1e3/(2*np.pi), 'brown',
                      r'$\omega_{ac}/(2\pi)$ (isothermal)')
        axes[1].set(ylabel='Frequency [mHz]', title='Buoyancy and acoustic cutoff')

        density_twin = axes[2].twinx()
        plot_quantity(axes[2], 'temperature', 1e-3, 'green', r'$T$')
        # Keep every native density level inside the displayed domain.
        density_plot_z = np.unique(np.r_[lo, density_z[(density_z > lo) & (density_z < hi)], hi])
        density_twin.plot(density_plot_z, np.interp(density_plot_z, density_z, density),
                          color='brown', label=r'$\rho$', linewidth=1.6)
        density_twin.set(yscale='log', ylabel=r'Density [g cm$^{-3}$]')
        axes[2].set(ylabel='Temperature [kK]', title='Temperature and density')
        beta_twin = axes[3].twinx()
        axes[3].set(yscale='log', ylabel=r'Gas pressure [dyn cm$^{-2}$]',
                    title='Gas pressure and plasma beta')
        beta_twin.set(yscale='log', ylabel=r'Plasma $\beta$ [dimensionless]')
        missing = []
        for key, target, color, label in (('pressure', axes[3], 'blue', r'$P_{gas}$'),
                                         ('plasma_beta', beta_twin, 'red', r'$\beta$')):
            record = scalar_profiles[key]
            if record is None:
                zero_field = all(np.all(component == 0) for component in profiles.components_G)
                missing.append('Plasma beta undefined for zero magnetic field' if key == 'plasma_beta' and zero_field
                               else f'{"Pressure" if key == "pressure" else "Plasma beta"} profile unavailable')
                continue
            native_z, values, _ = record
            if native_z[0] > lo or native_z[-1] < hi:
                raise ProfileError(f'{key} profile does not cover the simulation height range.')
            display_z = np.unique(np.r_[lo, native_z[(native_z > lo) & (native_z < hi)], hi])
            target.plot(display_z, np.interp(display_z, native_z, values),
                        color=color, label=label, linewidth=1.6)
        if missing:
            axes[3].text(.5, .5, '\n'.join(missing), transform=axes[3].transAxes,
                         ha='center', va='center', fontsize=10)
        for axis, twin in zip(axes, (speed_twin, None, density_twin, beta_twin)):
            axis.set(xlabel='z [Mm]', xlim=(lo, hi))
            lines = list(axis.lines)+(list(twin.lines) if twin is not None else [])
            if height_pair_km is not None:
                points = np.unique(np.asarray(height_pair_km)/1000.)
                for target in (axis, twin):
                    if target is None:
                        continue
                    for line in list(target.lines):
                        values = np.interp(points, line.get_xdata(), line.get_ydata())
                        target.plot(points, values, 'o', color='black', markersize=4,
                                    label='_nolegend_', zorder=5)
            if lines:
                axis.legend(lines, [line.get_label() for line in lines], loc='upper right', frameon=False)
        fig.suptitle(f'{profiles.model} — horizontally averaged snapshot t = {provenance["snapshot_time_s"]:g} s')
        for path in paths:
            fd, temporary = tempfile.mkstemp(dir=folder, suffix=path.suffix)
            os.close(fd)
            try:
                fig.savefig(temporary, dpi=400)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        fig.clear()
    from komega_bokeh_context import _write_json
    _write_json(manifest, dict(provenance=provenance, samples=profiles.samples(),
                              outputs=list(map(str, paths))))
    return paths


def resolve_parameters(config, *, make_figure=True):
    '''
    Purpose
    -------
    Resolve selected-height atmospheric inputs or report explicit unavailable
    provenance.

    Inputs
    ------
    config: dict
        Resolved pipeline configuration, including data, sampling, filtering, and output
        settings.
    make_figure: bool
        Publish the native diagnostic figure when True.

    Outputs
    -------
    record: dict or None
        Available/unavailable parameter record, or None for disabled/non-simulation
        inputs. Optional diagnostic publication writes plots; inconsistent recorded
        heights are flagged fatal.

    Notes
    -----
    Return parameters or explicit unavailable provenance; never silent defaults.
    '''
    # Resolve selected-height atmospheric inputs or report explicit unavailable
    # provenance
    data = config.get('data', {})
    if data.get('source_type') != 'single_cube' or not config.get('atmospheric_profiles', {}).get('enabled', False):
        return None
    try:
        profiles = load_profiles(config)
        simulation = data.get('single_cube', {})
        # Check selected native layer indices and recorded physical heights against the
        # cube
        indices = [int(data.get('resolved_'+key+'_index', data.get(key, simulation.get(key))))
                   for key in ('h1', 'h2')]
        if any(index < 0 or index >= len(profiles.cube_height_km) for index in indices):
            raise ProfileError('Selected height indices are outside the cube.')
        heights = [float(profiles.cube_height_km[index]) for index in indices]
        for key, height in zip(('resolved_h1_km', 'resolved_h2_km'), heights):
            if key in data and not np.isclose(float(data[key]), height, rtol=1e-9, atol=1e-6):
                raise ProfileError('Diagram height metadata disagrees with the cube coordinate.')
        record = profiles.parameters(*heights)
        record['height_indices'] = indices
        # Publish optional native profile diagnostics under the matching managed
        # category
        if make_figure:
            folder = Path(config['paths']['figure_dir'])
            from output_paths import terminal_directory, organization_prefix, resolve_category
            if config.get('_output_context'):
                terminal = terminal_directory(config['_output_context']['identity'])
            else:
                terminal = organization_prefix(config)
                try:
                    terminal = terminal / resolve_category(config)
                except ValueError:
                    pass  # A standalone profile can lack a model field category.
            folder = folder / terminal / '_atmospheric_profiles'
            record['diagnostic_figures'] = list(map(str, save_diagnostic(profiles, folder)))
        return record
    # Preserve explicit unavailable reasons and any independently known height
    # separation
    except (OSError, KeyError, IndexError, TypeError, ValueError) as exc:
        parameters = {}
        if all(key in data for key in ('resolved_h1_km', 'resolved_h2_km')):
            heights = [float(data[key]) for key in ('resolved_h1_km', 'resolved_h2_km')]
            if np.isfinite(heights).all():
                parameters['dz'] = abs(heights[1]-heights[0])
        return dict(schema_version=VERSION, status='unavailable', parameters=parameters,
                    units={key: UNITS[key] for key in parameters},
                    fatal='Diagram height metadata disagrees' in str(exc),
                    unavailable={'all': str(exc)}, approximation='Authoritative model defaults retained and disclosed.')


def sidecar_path(product):
    '''
    Purpose
    -------
    Construct the managed atmospheric metadata sidecar for a numerical product.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.

    Outputs
    -------
    path: pathlib.Path
        Product companion ending in .atmosphere.json under json_files.
    '''

    # Construct the managed atmospheric metadata sidecar for a numerical product
    return json_sidecar_path(product, '.atmosphere.json')


def write_sidecar(product, record):
    '''
    Purpose
    -------
    Persist nonempty atmospheric metadata only when its recorded contents changed.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.
    record: dict or None
        Resolved atmospheric parameter/provenance record, or None to do nothing.

    Outputs
    -------
    None
        Writes the atmospheric sidecar atomically when record is not None and differs
        from existing JSON.
    '''

    # Persist nonempty atmospheric metadata only when its recorded contents changed
    if record is not None:
        path = sidecar_path(product)
        if path.is_file() and json.loads(path.read_text()) == record:
            return
        from komega_bokeh_context import _write_json
        _write_json(path, record)


def read_sidecar(product):
    '''
    Purpose
    -------
    Read, validate, and upgrade an available atmospheric product sidecar.

    Inputs
    ------
    product: str or pathlib.Path
        Product kind or artifact path, as required by this operation.

    Outputs
    -------
    record: dict or None
        Current parameter/provenance record or None when absent; unsupported schemas
        raise ProfileError.
    '''

    # Read, validate, and upgrade an available atmospheric product sidecar
    path = find_json_sidecar(product, '.atmosphere.json')
    if not path.is_file():
        return None
    record = json.loads(path.read_text())
    if record.get('schema_version') not in {1, VERSION} or not isinstance(record.get('parameters'), dict):
        raise ProfileError(f'Invalid atmospheric metadata: {path}.')
    return upgrade_atmosphere(record)


def upgrade_atmosphere(record):
    '''
    Purpose
    -------
    Refresh legacy/coarse atmospheric defaults while preserving usable portable exports.

    Inputs
    ------
    record: dict
        Existing atmospheric sidecar or embedded export metadata.

    Outputs
    -------
    record: dict
        Independent current record or refreshed native-source defaults. If refresh
        sources are unavailable, removes unsupported legacy quantities/initializations
        and records explicit reasons.

    Notes
    -----
    Refresh coarse-density metadata while keeping current exports portable.
    '''
    # Refresh legacy/coarse atmospheric defaults while preserving usable portable
    # exports
    import copy
    record = copy.deepcopy(record)
    provenance = record.get('provenance', {})
    if (record.get('schema_version') == VERSION and 'N' not in record.get('parameters', {})
            and provenance.get('algorithm_version') == ALGORITHM_VERSION):
        # Embedded exports remain usable without the original local data.
        # When those sources are available, detect changed or newly supplied
        # native profiles rather than returning stale scalar initializations.
        try:
            reference = provenance['profile']['path']
            known = {key: (value['path'], value['size_bytes'], value['mtime_ns'])
                     for key, value in provenance.get('native_profiles', {}).items()}
            current = dict(_supplemental_versions(reference))
            changed = current != known if Path(reference).is_file() else False
            for key in ('cube', 'profile'):
                source = provenance[key]
                if Path(source['path']).is_file():
                    changed |= _version(source['path']) != (source['path'], source['size_bytes'], source['mtime_ns'])
            if not changed:
                return record
        except (KeyError, OSError):
            return record
    try:
        from config import default_atmospheric_profiles
        units = dict(default_atmospheric_profiles['legacy_units'])
        units.update(provenance.get('legacy_units', {}))
        units.update({key: value['unit'] for key, value in provenance['source_units'].items()})
        profiles = _load_profiles(_version(provenance['cube']['path']),
            _version(provenance['profile']['path']), json.dumps(units, sort_keys=True),
            float(provenance.get('gravity_km_s2', .274)),
            _supplemental_versions(provenance['profile']['path']),
            provenance.get('co5bold_magnetic_convention', 'internal'))
        updated = profiles.parameters(*record['height_pair_km'])
        for key in ('height_indices', 'height_identification', 'diagnostic_figures'):
            if key in record:
                updated[key] = record[key]
        return updated
    except (KeyError, OSError, ProfileError):
        unsigned = 'N' in record.get('parameters', {})
        record.setdefault('parameters', {}).pop('N', None)
        record.pop('initializations', None)
        record.pop('fallbacks', None)
        for key in ('N2', 'H', 'wac', 'a'):
            record['parameters'].pop(key, None)
            record.setdefault('unavailable', {})[key] = (
                'Legacy N cannot recover signed N²; its source stratification is unavailable.'
                if key == 'N2' and unsigned else
                'Legacy coarse-density parameters require refresh, but their source profiles are unavailable.')
        record['schema_version'] = VERSION
        return record
