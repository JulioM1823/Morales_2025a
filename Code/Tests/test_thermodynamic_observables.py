'''
Purpose
-------
Pressure/beta keep their native values and require spatial/time cubes.

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
import importlib.util
import ast
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np
import pytest

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
from simulation_observables import profile_units, select_field
import output_paths

spec = importlib.util.spec_from_file_location('thermodynamic_filter', TD/'filter.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('observable,stored,units', [
    ('pressure', 'pressure', 'dyn/cm^2'), ('pressure', 'pgas', 'Pa'),
    ('gas_pressure', 'p', 'dyn/cm^2'), ('plasma_beta', 'beta', '1'),
    ('beta', 'plasma_beta', 'dimensionless')])
def test_loads_actual_time_and_height_slices_without_velocity_scaling(tmp_path, observable, stored, units):
    '''
    Purpose
    -------
    Verify loads actual time and height slices without velocity scaling.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    observable: str
        Numerical observable selected from the source cube.

    stored: np.array or scalar
        Numerical values as stored in the synthetic source variable.

    units: str
        Unit metadata attached to the synthetic numerical variable.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    path = tmp_path/'cube.nc'
    values = 2.+np.arange(4*3*2*2).reshape(4, 3, 2, 2)
    with netCDF4.Dataset(path, 'w') as d:
        for dim, length in [('time', 4), ('xc3', 3), ('xc2', 2), ('xc1', 2)]:
            d.createDimension(dim, length)
        z = d.createVariable('xc3', 'f8', ('xc3',)); z.units = 'cm'; z[:] = [1e5, 2e5, 3e5]
        d.createVariable('v3', 'f8', ('time', 'xc3', 'xc2', 'xc1'))[:] = -1.
        v = d.createVariable(stored, 'f8', ('time', 'xc3', 'xc2', 'xc1'))
        v.units = units; v[:] = values
    cfg = dict(data=dict(observable=observable, h1=0, h2=2), time_distance={})
    loader = module.AGWFilter(cfg)
    lower, upper = loader.load_netcdf_height_pair(path)
    np.testing.assert_array_equal(lower, values[:, 0])
    np.testing.assert_array_equal(upper, values[:, 2])
    assert cfg['data']['observable'] == stored
    assert output_paths.normalize_observable_slug(stored) in {'pressure', 'plasma_beta'}


@pytest.mark.parametrize('field', ['pressure', 'plasma_beta'])
def test_rejects_one_dimensional_profiles_instead_of_substituting_velocity(tmp_path, field):
    '''
    Purpose
    -------
    Verify rejects one dimensional profiles instead of substituting velocity.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    field: str
        Observable or profile field selected by the current test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    with netCDF4.Dataset(tmp_path/'profile.nc', 'w') as d:
        d.createDimension('z', 3)
        v = d.createVariable(field, 'f8', ('z',)); v.units = '1' if field == 'plasma_beta' else 'Pa'
        with pytest.raises(ValueError, match='requires a stored 4D field'):
            select_field(d.variables, field, ndim=4)


def test_pressure_and_beta_units_are_not_internal_energy_units():
    '''
    Purpose
    -------
    Verify pressure and beta units are not internal energy units.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    assert profile_units('pressure', 'Pa') == ('dyn/cm^2', 10.)
    assert profile_units('plasma_beta', '1') == ('1', 1.)
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='Unsupported'):
        profile_units('pressure', 'erg/gm')
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='Unsupported'):
        profile_units('plasma_beta', '')


def test_notebook_spatial_maps_use_pressure_and_beta_units():
    '''
    Purpose
    -------
    Verify notebook spatial maps use pressure and beta units.

    Inputs
    ------
    None
        Uses the surrounding fixture or object state where needed.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    notebook = json.loads((TD/'plots.ipynb').read_text())
    tree = ast.parse(''.join(notebook['cells'][0]['source']))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'convert_velocity_to_km_s', 'spatial_observable_label'}]
    assert len(functions) == 2
    namespace = {'np': np}
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<notebook>', 'exec'), namespace)
    values = np.array([100., 200.])
    pressure = dict(data=dict(source_type='single_cube', observable='pressure', observable_units='Pa'))
    beta = dict(data=dict(source_type='single_cube', observable='plasma_beta', observable_units='1'))
    velocity = dict(data=dict(source_type='single_cube', observable='v3'))
    np.testing.assert_array_equal(namespace['convert_velocity_to_km_s'](values, pressure), values*10.)
    np.testing.assert_array_equal(namespace['convert_velocity_to_km_s'](values, beta), values)
    np.testing.assert_array_equal(namespace['convert_velocity_to_km_s'](values, velocity), values/1e5)
    assert 'dyn' in namespace['spatial_observable_label'](pressure)
    assert 'dimensionless' in namespace['spatial_observable_label'](beta)
