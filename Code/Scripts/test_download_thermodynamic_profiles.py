'''
Purpose
-------
Verify native-height density and thermodynamic profile preservation and rejection rules.

Inputs
------
None

Outputs
-------
unittest test cases
    Build temporary native-grid fixtures and optionally exercise the NCO
    downloader; running this file executes unittest.main().
'''
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import netCDF4
import numpy as np

from download_density_profiles import make_profile
from download_thermodynamic_profiles import import_shared


class DensityProfileTests(unittest.TestCase):
    '''
    Purpose
    -------
    Check full-plane density reduction and native-grid/time validation.

    Inputs
    ------
    None

    Outputs
    -------
    unittest.TestCase
        Tests use temporary NetCDF snapshots and clean them up after each case.
    '''

    def setUp(self):
        '''
        Purpose
        -------
        Create temporary atmospheric, density, and source-field fixtures.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Store paths and reference arrays on the test case and register cleanup.
        '''

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.reference = root/'TEST_t00000030s_atmos_param.h5'
        self.raw = root/'raw.nc'
        self.output = root/'density.h5'
        with netCDF4.Dataset(self.reference, 'w') as d:
            d.createDimension('z', 3)
            d.createVariable('z', 'f8', ('z',))[:] = [1, 3, 8]
        self.values = np.arange(1, 13, dtype=np.float32).reshape(3, 2, 2)
        with netCDF4.Dataset(self.raw, 'w') as d:
            d.Model = 'TEST'
            d.ModelRefName = 'test'
            d.Description = 'synthetic validation fixture'
            d.time_db = 30.125
            for name, values in dict(xc1=[0.5, 1.5], xc2=[0.5, 1.5],
                                     xc3=[1, 3, 8], xb1=[0, 1, 2],
                                     xb2=[0, 1, 2], xb3=[0, 2, 4, 12]).items():
                d.createDimension(name, len(values))
                v = d.createVariable(name, 'f8', (name,))
                v.units = 'cm'
                v[:] = values
            v = d.createVariable('rho', 'f4', ('xc3', 'xc2', 'xc1'))
            v.units = 'gm/cm^3'
            v[:] = self.values

    def test_preserves_native_levels_time_and_full_plane_mean(self):
        '''
        Purpose
        -------
        Verify preserves native levels time and full plane mean.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        record = make_profile(self.reference, self.raw, self.output)
        with netCDF4.Dataset(self.output) as d:
            np.testing.assert_array_equal(d['z'][:], [1, 3, 8])
            np.testing.assert_array_equal(d['rho'][:], [2.5, 6.5, 10.5])
            self.assertEqual(float(d['time'][:]), 30.125)
        self.assertFalse(record['vertical_binning'])
        self.assertEqual(record['native_shape'], [3, 2, 2])

    def test_rejects_different_height_grid(self):
        '''
        Purpose
        -------
        Verify rejects different height grid.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        with netCDF4.Dataset(self.reference, 'a') as d:
            d['z'][1] = 4
        with self.assertRaisesRegex(ValueError, 'Native heights differ'):
            make_profile(self.reference, self.raw, self.output)

    def test_rejects_missing_cells_instead_of_changing_support(self):
        '''
        Purpose
        -------
        Verify rejects missing cells instead of changing support.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        with netCDF4.Dataset(self.raw, 'a') as d:
            d['rho'][0, 0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'missing, nonfinite'):
            make_profile(self.reference, self.raw, self.output)

    def test_rejects_wrong_snapshot_time(self):
        '''
        Purpose
        -------
        Verify rejects wrong snapshot time.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        with netCDF4.Dataset(self.raw, 'a') as d:
            d.time_db = 40.
        with self.assertRaisesRegex(ValueError, 'Native time'):
            make_profile(self.reference, self.raw, self.output)


class SharedProfileTests(unittest.TestCase):
    '''
    Purpose
    -------
    Check publisher 1D field preservation and explicit pressure-unit contracts.

    Inputs
    ------
    None

    Outputs
    -------
    unittest.TestCase
        Tests compare copied pressure/beta values and exact native heights.
    '''

    def setUp(self):
        '''
        Purpose
        -------
        Create temporary atmospheric, density, and source-field fixtures.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Store paths and reference arrays on the test case and register cleanup.
        '''

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root/'TEST_t00000030s_atmos_param.h5'
        self.source = self.root/'source'/self.reference.name
        self.source.parent.mkdir()
        self.stage = self.root/'stage'; self.stage.mkdir()
        self.z = np.array([1., 3., 8.])
        self.pressure = np.array([100., 40., 10.])
        self.beta = np.array([1000., 10., .1])
        with netCDF4.Dataset(self.reference, 'w') as d:
            d.createDimension('z', 3)
            d.createVariable('z', 'f8', ('z',))[:] = self.z
        with netCDF4.Dataset(self.reference.with_name('TEST_t00000030s_density_profile.h5'), 'w') as d:
            d.createDimension('z', 3)
            d.createVariable('z', 'f8', ('z',))[:] = self.z
            d.createVariable('rho', 'f8', ('z',))[:] = [1, .4, .1]
            d.createVariable('time', 'f8', ()).assignValue(30.125)
        with netCDF4.Dataset(self.source, 'w') as d:
            d.createDimension('z', 3)
            for name, values in dict(z=self.z, pressure=self.pressure,
                                     plasma_beta=self.beta, rho=[1, .4, .1], sound_speed=[12, 12, 12]).items():
                d.createVariable(name, 'f8', ('z',))[:] = values

    def test_preserves_publisher_arrays_without_recomputing_beta(self):
        '''
        Purpose
        -------
        Verify preserves publisher arrays without recomputing beta.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        result = import_shared(self.reference, self.source, self.stage, 'test-source', 'dyn/cm^2')
        self.assertEqual(len(result['profiles']), 2)
        for item in result['profiles']:
            with netCDF4.Dataset(self.stage/item['profile_file']) as d:
                np.testing.assert_array_equal(d['z'][:], self.z)
                np.testing.assert_array_equal(d[item['field']][:], self.pressure if item['field']=='pressure' else self.beta)
                self.assertEqual(float(d['time'][:]), 30.125)
                self.assertEqual(d.vertical_binning, 'none')

    def test_absent_pressure_units_require_explicit_contract(self):
        '''
        Purpose
        -------
        Verify absent pressure units require explicit contract.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        with self.assertRaisesRegex(ValueError, 'Unsupported or missing pressure units'):
            import_shared(self.reference, self.source, self.stage, 'test-source', None)

    def test_rejects_height_mismatch(self):
        '''
        Purpose
        -------
        Verify rejects height mismatch.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        with netCDF4.Dataset(self.source, 'a') as d:
            d['z'][1] = 4.
        with self.assertRaises(AssertionError):
            import_shared(self.reference, self.source, self.stage, 'test-source', 'dyn/cm^2')


class DownloaderThermodynamicTests(unittest.TestCase):
    '''
    Purpose
    -------
    Check pressure/beta retention through both vertical sampling modes.

    Inputs
    ------
    None

    Outputs
    -------
    unittest.TestCase
        Integration checks run only when zsh and all required NCO tools exist.
    '''

    @unittest.skipUnless(all(shutil.which(name) for name in ('zsh', 'ncks', 'ncap2', 'ncwa', 'ncatted', 'ncrename')),
                         'Existing NCO runtime required')
    def test_pressure_beta_survive_both_vertical_sampling_modes(self):
        '''
        Purpose
        -------
        Verify pressure beta survive both vertical sampling modes.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Assert the stated invariant or expected exception; assertion failures
            are reported by unittest. Temporary files remain isolated to the fixture.
        '''

        script = Path(__file__).with_name('download_files.sh')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'rhd_t00000030s.h5'
            values = 1.+np.arange(6*4*4).reshape(6, 4, 4)
            with netCDF4.Dataset(source, 'w') as d:
                d.Model = 'TEST'; d.time_db = 30.125
                for dim, n in [('xc1', 4), ('xc2', 4), ('xc3', 6), ('xb1', 5), ('xb2', 5), ('xb3', 7)]:
                    d.createDimension(dim, n)
                    v = d.createVariable(dim, 'f8', (dim,)); v[:] = np.arange(n)*1e5; v.units = 'cm'
                for name in ['rho', 'v1', 'v2', 'v3', 'ei', 'pressure', 'plasma_beta']:
                    v = d.createVariable(name, 'f8', ('xc3', 'xc2', 'xc1')); v[:] = values
                    v.units = 'dyn/cm^2' if name == 'pressure' else '1'
            urls = root/'urls.txt'; urls.write_text(str(source)+'\n')
            native_expected = values.reshape(6, 2, 2, 2, 2).mean(axis=(2, 4))
            for enabled in ('0', '1'):
                with self.subTest(vertical_binning=enabled):
                    env = dict(os.environ, Z_BIN_ENABLED=enabled, Z_BIN='3',
                               Z_SUBSET_START='0', Z_SUBSET_END='5', MAX_JOBS='1')
                    output = root/('output'+enabled)
                    completed = subprocess.run(['zsh', str(script), str(urls), str(output)],
                        env=env, capture_output=True, text=True, timeout=60)
                    self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)
                    expected = native_expected if enabled == '0' else native_expected.reshape(2, 3, 2, 2).mean(axis=1)
                    with netCDF4.Dataset(next(output.glob('*.nc'))) as d:
                        for field, unit in [('pressure', 'dyn/cm^2'), ('plasma_beta', '1')]:
                            np.testing.assert_array_equal(d[field][:], expected)
                            self.assertEqual(d[field].units, unit)
                            self.assertEqual(d[field].dimensions, ('xc3', 'xc2', 'xc1'))


if __name__ == '__main__':
    unittest.main()
