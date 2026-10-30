'''
Purpose
-------
Independent SI/native-profile validation for all seven simulation models.

Differentiate with centred local polynomial fits, independently of the loader's
nonuniform-grid gradient. Check paper Eq. 2/4, profile sampling, all height pairs,
and the inputs supplied to each of the seven dispersion adapters. Read-only data.

Inputs
------
None
    Test cases use local fixtures, parameterized inputs, and the imported
    implementation modules.

Outputs
-------
Tests and audit helpers: callable
    Expose the regression cases or measured audit entrypoints defined here.
'''
# Import the test dependencies and implementation modules used by these checks.
import copy
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import atmospheric_profiles as ap
import config
from komega_bokeh_context import atmospheric_initializations


def derivative(z, values):
    '''
    Purpose
    -------
    Independent derivative of the local quadratic through three samples.

    Inputs
    ------
    z: np.array
        One-dimensional coordinate samples; derivative units use this coordinate.

    values: np.array
        Synthetic values or reference samples in the units declared by the fixture.

    Outputs
    -------
    derivative: np.array
        First derivative at each z sample; units are values units divided by z units.
    '''
    return np.array([np.polyfit(z[start:start+3]-z[i], values[start:start+3], 2)[1]
                     for i in range(len(z))
                     for start in [max(0, min(i-1, len(z)-3))]])


def audit():
    '''
    Purpose
    -------
    Independently validate all seven configured native atmospheric models and their
    height-pair inputs.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    report: dict
        Passed status, algorithm version, model reports, interval counts, and
        initialization checks. Raise assertions when profiles disagree.
    '''

    reports = []
    # Check every configured simulation against independently reconstructed profiles.
    for path in sorted(Path(config.co5bold_batch_root).glob('*/*/*.nc')):
        cfg = copy.deepcopy(config.config)
        cfg['data'].update(source_type='single_cube', file=str(path))
        profiles = ap.load_profiles(cfg)
        provenance = profiles.provenance
        with netCDF4.Dataset(path) as cube, netCDF4.Dataset(provenance['profile']['path']) as thermal:
            native = provenance['native_profiles']['rho']
            with netCDF4.Dataset(native['path']) as density:
                # Convert the native density coordinate to metres relative to the
                # recorded height origin.
                density_z = np.asarray(density['z'][:], float)*.01-provenance['height_origin_native_km']*1000.
                rho_si = np.asarray(density['rho'][:], float)*1000.
            np.testing.assert_array_equal(profiles.density_native_cgs*1000., rho_si)
            native_slope = derivative(density_z, np.log(rho_si))
            grid = profiles.height_km*1000.
            thermal_z = np.asarray(thermal['z'][:], float)*.01-provenance['height_origin_native_km']*1000.
            sound = np.interp(grid, thermal_z, np.asarray(thermal['sound_speed'][:], float)*.01)
            slope = np.interp(grid, density_z, native_slope)
            # Apply the stated buoyancy/cutoff relations in SI units before comparison.
            n2_si = -274.*slope-274.**2/sound**2
            cutoff_si = -sound*slope/2.
            np.testing.assert_allclose(profiles.quantities['cs']*1000., sound, rtol=2e-14)
            np.testing.assert_allclose(profiles.quantities['N2'], n2_si, rtol=1e-9, atol=2e-15)
            np.testing.assert_allclose(profiles.quantities['wac'], cutoff_si, rtol=1e-10, atol=2e-15)
            expected_H = -1./slope/1000.
            np.testing.assert_allclose(profiles.quantities['H'], expected_H, rtol=1e-9)
            if 'alfven_speed' in thermal.variables:
                alfven = np.interp(grid, thermal_z, np.asarray(thermal['alfven_speed'][:], float)*1e-5)
            else:
                alfven = np.zeros_like(grid)
            hydrostatic = profiles.quantities.get('hydrostatic_gravity_km_s2')
            pressure_check = None
            # Check the optional pressure-gradient gravity against the native density
            # profile.
            if hydrostatic is not None:
                with netCDF4.Dataset(provenance['native_profiles']['pressure']['path']) as pressure:
                    pressure_si = np.asarray(pressure['pressure'][:], float)*.1
                independent_g = -np.interp(grid, density_z, derivative(density_z, pressure_si))/np.interp(grid, density_z, rho_si)/1000.
                np.testing.assert_allclose(hydrostatic, independent_g,
                                           rtol=1e-9, atol=2e-12)
                pressure_check = dict(effective_hydrostatic_g_range_km_s2=[float(hydrostatic.min()), float(hydrostatic.max())],
                    median_fractional_departure_from_solar_g=float(np.median(hydrostatic/.274-1.)),
                    max_difference_N2_pressure_vs_paper_s_inverse_squared=float(np.max(np.abs(
                        profiles.quantities['N2_pressure_gradient']-profiles.quantities['N2']))))
            point_records = []
            # Check point samples independently before testing finite height-interval
            # means.
            for height in profiles.cube_height_km:
                values = profiles.parameters(height, height)['parameters']
                assert np.isclose(values['a'], np.interp(height*1000., grid, alfven), rtol=2e-14, atol=1e-15)
                assert np.isclose(values['N2'], np.interp(height*1000., grid, n2_si), rtol=1e-9, atol=2e-15)
                point_records.append(dict(height_km=float(height), **values))
            interval_count = 0
            # Visit every distinct height pair and compare integral means and adapter
            # inputs.
            for left in range(len(profiles.cube_height_km)):
                for right in range(left+1, len(profiles.cube_height_km)):
                    z1, z2 = profiles.cube_height_km[[left, right]]
                    selected = (profiles.height_km >= z1)&(profiles.height_km <= z2)
                    record = profiles.parameters(z1, z2)
                    for key, expected in [('N2', n2_si), ('wac', cutoff_si), ('cs', sound/1000.), ('a', alfven)]:
                        average = np.trapz(expected[selected], profiles.height_km[selected])/(z2-z1)
                        assert np.isclose(record['parameters'][key], average, rtol=1e-9, atol=2e-15), (profiles.model, key)
                    initializations, _ = atmospheric_initializations(cfg, record)
                    for model, inputs in initializations.items():
                        for key in inputs.keys()&record['parameters'].keys():
                            assert inputs[key] == record['parameters'][key], (model, key)
                    interval_count += 1
            vertical_flux = None
            # Check the stored-to-Gauss conversion for vertical-flux model labels.
            if getattr(cube, 'ModelRefName', '').startswith('Sun-v') and 'bb3' in cube.variables:
                raw = np.mean(cube['bb3'][provenance['cube_frame'], :, :, :], axis=(1, 2), dtype=np.float64)
                gauss = raw*np.sqrt(4*np.pi)
                physical_flux = float(cube.ModelRefName.removeprefix('Sun-v'))
                np.testing.assert_allclose(gauss, physical_flux, rtol=2e-7)
                vertical_flux = dict(expected_G=physical_flux, mean_stored=float(np.mean(raw)),
                                     mean_converted_G=float(np.mean(gauss)))
            reports.append(dict(model=profiles.model, snapshot_time_s=provenance['snapshot_time_s'],
                native_density=native, native_levels=len(density_z), magnetic_levels=len(profiles.cube_height_km),
                signed_N2_range_s_inverse_squared=[float(n2_si.min()), float(n2_si.max())],
                negative_N2_sample_count=int(np.count_nonzero(n2_si<0)),
                max_N2_absolute_error=float(np.max(np.abs(n2_si-profiles.quantities['N2']))),
                pressure_check=pressure_check, vertical_flux_check=vertical_flux,
                checked_height_intervals=interval_count, point_values=point_records))
    assert len(reports) == 7
    return dict(status='passed', algorithm_version=ap.ALGORITHM_VERSION,
        model_count=7, height_intervals=sum(r['checked_height_intervals'] for r in reports),
        model_initialization_checks=sum(r['checked_height_intervals'] for r in reports)*7, models=reports)


if __name__ == '__main__':
    output = Path(sys.argv[1])
    output.write_text(json.dumps(audit(), indent=2, allow_nan=False)+'\n')
    print(output)
