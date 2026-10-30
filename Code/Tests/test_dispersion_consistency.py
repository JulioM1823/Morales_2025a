'''
Purpose
-------
Independent scientific and callback regressions for the dispersion controls.

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
import importlib
from pathlib import Path
import sys
from unittest.mock import patch

import netCDF4
import numpy as np
import pytest
from bokeh.document import Document
from bokeh.models import Slider, TextInput

TD = Path(__file__).resolve().parents[1]/'Time-Distance'
sys.path.insert(0, str(TD))
import atmospheric_profiles as ap
import komega_explorer as ke
from vesa_support import support_module
from test_atmospheric_profiles import atmosphere

geometry = support_module('magnetic_geometry')


@pytest.fixture
def app(monkeypatch):
    '''
    Purpose
    -------
    Construct the explorer fixture with synthetic inputs and small numerical grids.

    Inputs
    ------
    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    app: object
        Bokeh explorer document with initial scheduling disabled. Apply the
        temporary control/grid settings required by this module's tests.
    '''

    # Use a fresh document and small grids so the test controls the first calculation.
    cfg = ke._load_config(ke.CONFIG_FILE)
    vesa = ke.load_dispersion_explorer(cfg['komega_comparison']['vesa_2026_dir'])
    monkeypatch.setitem(vesa.RESOLUTION_OPTIONS, 'interactive', (8, 10))
    return ke.build_document(Document(), schedule_initial=False)


@pytest.mark.parametrize('vector', [(0,0,0), (0,0,3), (0,0,-3), (3,0,0),
    (-3,0,0), (0,-4,0), (3,4,-5), (-1,-2,3), (1e-20,0,0)])
def test_cartesian_round_trip(vector):
    '''
    Purpose
    -------
    Verify cartesian round trip.

    Inputs
    ------
    vector: tuple
        Cartesian field vector for the coordinate round-trip test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    b, theta, phi = geometry.orientation(*vector)
    assert 0 <= theta <= 180 and -180 <= phi <= 180
    np.testing.assert_allclose(geometry.components(b, theta, phi), vector, atol=1e-14)


@pytest.mark.parametrize('theta', [-180., -90., 0., 90., 180., -55.123456789])
def test_signed_equivalent_orientations(theta):
    '''
    Purpose
    -------
    Verify signed equivalent orientations.

    Inputs
    ------
    theta: float
        Field inclination in the angular convention used by the tested API.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    np.testing.assert_allclose(geometry.components(3., -theta, 27.),
                              geometry.components(3., theta, -153.), atol=2e-15)
    bx, _, bz = geometry.components(1., theta, 27.)
    assert geometry.field_aligned_wavenumber(.003, -.004, theta, 27.) == pytest.approx(.003*bx-.004*bz)


def test_all_sliders_have_exact_inputs_and_shared_precision(app):
    '''
    Purpose
    -------
    Verify all sliders have exact inputs and shared precision.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    sliders = list(app.doc.select({'type': Slider}))
    inputs = {m.name for m in app.doc.select({'type': TextInput})}
    assert all(slider.name+':exact' in inputs for slider in sliders)
    first, _, slow, fast = app.models[:4]
    field = first.numeric_controls['theta_deg'].input
    field.value = '55.1234567890123'
    expected = float(field.value)
    for section in (first, slow, fast):
        assert section.widgets['theta_deg'].value == expected
        assert float(section.numeric_controls['theta_deg'].input.value) == expected
    slow.numeric_controls['theta_deg'].input.value = '-30.123456789'
    assert first.widgets['theta_deg'].value == -30.123456789
    app.tabs.active = 3
    assert fast.widgets['theta_deg'].value == -30.123456789
    first.widgets['theta_deg'].value = -180.
    assert float(field.value) == -180.


def test_invalid_edits_do_not_mutate_state_and_valid_outside_range_expands(app):
    '''
    Purpose
    -------
    Verify invalid edits do not mutate state and valid outside range expands.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    section = app.models[0]
    control = section.numeric_controls['theta_deg']
    saved = section._current_values()
    for value in ('-', '', '1e', 'nan', 'inf', '180.1', '-180.1', 'oops'):
        control.input.value = value
        assert section._current_values() == saved
        assert control.message.visible
    control = section.numeric_controls['cs']
    control.input.value = '42.1234567890123'
    assert control.slider.value == 42.1234567890123
    assert control.slider.end == 42.1234567890123
    assert 'expanded' in control.message.text
    control.input.value = '-1'
    assert control.slider.value == 42.1234567890123
    control = section.numeric_controls['N2']
    control.input.value = '-0.0001234567890123'
    # The visible control is signed sqrt(|N2|) in mHz; the solver retains
    # signed angular-frequency squared in s^-2. Verify that conversion once.
    frequency_mhz = float(control.input.value)
    expected_n2 = np.copysign((frequency_mhz * 2*np.pi/1000)**2, frequency_mhz)
    for section in app.models:
        if 'N2' in section.widgets:
            assert section.widgets['N2'].value == pytest.approx(expected_n2, rel=2e-15, abs=0)
            assert float(section.numeric_controls['N2'].input.value) == pytest.approx(frequency_mhz, rel=2e-15, abs=0)


def test_shared_edit_debounces_once_and_preserves_unrelated_inputs(app):
    '''
    Purpose
    -------
    Verify shared edit debounces once and preserves unrelated inputs.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    first, _, slow = app.models[:3]
    before = first._current_values()
    with patch.object(first, 'schedule_recompute') as schedule:
        first.numeric_controls['theta_deg'].input.value = '-30.123'
        assert schedule.call_count == 1
    for key in before.keys()-{'theta_deg'}:
        assert first.widgets[key].value == before[key]
    assert not slow._active and slow._dirty and slow._pending_callback is None
    first.numeric_controls['theta_deg'].input.value = '-55'
    first._restore_defaults()
    assert slow.widgets['theta_deg'].value == first.widgets['theta_deg'].value


def test_enter_submission_commits_exactly_once(app):
    '''
    Purpose
    -------
    Verify enter submission commits exactly once.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    from bokeh import events
    if not hasattr(events, 'ValueSubmit'):
        pytest.skip('This Bokeh version commits TextInput on blur only.')
    section = app.models[0]
    control = section.numeric_controls['theta_deg']
    with patch.object(section, 'schedule_recompute') as schedule:
        control.input._trigger_event(events.ValueSubmit(control.input, '-55.123456789'))
        assert section.widgets['theta_deg'].value == -55.123456789
        control.input.value = '-55.123456789'  # A subsequent blur has no extra work.
        assert schedule.call_count == 1


def test_state_is_document_local(app):
    '''
    Purpose
    -------
    Verify state is document local.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    other = ke.build_document(Document(), schedule_initial=False)
    before = other.models[0].widgets['theta_deg'].value
    app.models[0].widgets['theta_deg'].value = 12.345
    assert other.models[0].widgets['theta_deg'].value == before


@pytest.mark.parametrize('model', ['nc2009', 'alfven_mode', 'slow_mode', 'fast_mode'])
def test_equivalent_geometry_gives_same_polynomial_and_extreme_angles_are_finite(app, model):
    '''
    Purpose
    -------
    Verify equivalent geometry gives same polynomial and extreme angles are finite.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    model: str
        Dispersion model identifier selected for the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    adapter = importlib.import_module(app.vesa.__package__+'.interactive_models')
    def diagram(theta, phi):
        '''
        Purpose
        -------
        Construct the angle-varied diagnostic used by the geometry-equivalence check.

        Inputs
        ------
        theta: float
            Field inclination in the angular convention used by the tested API.

        phi: float
            Field azimuth in the angular convention used by the tested API.

        Outputs
        -------
        diagram: DiagnosticDiagram
            Solver using the enclosing model and fixed frequency/wavenumber samples.
        '''

        return adapter.DiagnosticDiagram(*np.meshgrid([.003], [.02]),
            adapter.build_model_parameters(model, dict(a=4.,theta_deg=theta,phi_deg=phi)))
    left, right = diagram(-55., 20.), diagram(55., -160.)
    np.testing.assert_allclose(left.kz_coefficients(.02,.003), right.kz_coefficients(.02,.003), atol=1e-25, rtol=3e-14)
    for theta in (-180., -90., 0., 90., 180.):
        d = diagram(theta, 90.)
        assert np.isfinite(d.kz_coefficients(.02,.003)).all()


@pytest.mark.parametrize('phi', [0., 37.])
def test_nc_polynomial_matches_published_determinant_and_2d_factorization(app, phi):
    '''
    Purpose
    -------
    Verify NC polynomial matches published determinant and 2D factorization.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    phi: float
        Field azimuth in the angular convention used by the tested API.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    adapter = importlib.import_module(app.vesa.__package__+'.interactive_models')
    p = adapter.build_model_parameters('nc2009', dict(a=4.,theta_deg=-55.,phi_deg=phi,N2=-.0002))
    kh, kz, w = .003, -.004, .02
    d = adapter.DiagnosticDiagram(*np.meshgrid([kh], [w]),p)
    k2 = kh**2+kz**2
    kp = kh*np.sin(p['theta'])*np.cos(p['phi'])+kz*np.cos(p['theta'])
    alfven = w*w-p['a']**2*kp*kp
    mag = w**4-(p['a']**2+p['cs']**2)*w*w*k2+p['a']**2*p['cs']**2*k2*kp*kp+p['cs']**2*p['N2']*kh*kh-(w*w-p['az']**2*k2)*p['wac']**2
    expected = w*w*p['wac']**2*p['ay']**2*kh*kh+alfven*mag
    assert np.polyval(d.kz_coefficients(w,kh),kz) == pytest.approx(expected,rel=1e-12,abs=1e-25)
    if phi == 0:
        assert expected == pytest.approx(alfven*mag,rel=1e-14)


@pytest.mark.parametrize('model', ['nc2009', 'mt1981', 'mt1982'])
def test_n2_is_consumed_once_and_changes_kz_polynomial(app, model):
    '''
    Purpose
    -------
    Verify N2 is consumed once and changes k_z polynomial.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    model: str
        Dispersion model identifier selected for the parameterized case.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    adapter = importlib.import_module(app.vesa.__package__+'.interactive_models')
    values = {'N2': -.0002}
    p = adapter.build_model_parameters(model, values)
    assert p['N2'] == -.0002 and 'N' not in p
    d = adapter.DiagnosticDiagram(*np.meshgrid([.003], [.02]),p)
    original = d.kz_coefficients(.02,.003)
    p['N2'] = .0002
    d = adapter.DiagnosticDiagram(*np.meshgrid([.003], [.02]),p)
    assert np.max(np.abs(d.kz_coefficients(.02,.003)-original)) > 0


@pytest.mark.parametrize('n2', [-.0002, 0., .0002])
def test_unmagnetized_limit_matches_equation_five(app, n2):
    '''
    Purpose
    -------
    Verify unmagnetized limit matches equation five.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    n2: float
        Signed squared buoyancy frequency (s^-2).

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    adapter = importlib.import_module(app.vesa.__package__+'.interactive_models')
    p = adapter.build_model_parameters('nc2009', {'a':0., 'N2':n2})
    kh,w = .003,.02
    kz2 = (n2-w*w)*kh*kh/(w*w)+(w*w-p['wac']**2)/p['cs']**2
    d = adapter.DiagnosticDiagram(*np.meshgrid([kh],[w]),p)
    for root in (np.sqrt(complex(kz2)), -np.sqrt(complex(kz2))):
        assert abs(np.polyval(d.kz_coefficients(w,kh),root)) < 1e-24


def test_native_standalone_document_uses_the_same_shared_architecture(app):
    '''
    Purpose
    -------
    Verify native standalone document uses the same shared architecture.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    sections = app.vesa.build_document(Document(), schedule_initial=False)
    sections[0].numeric_controls['theta_deg'].input.value = '-123.456789'
    for section in sections:
        if 'theta_deg' in section.widgets:
            assert section.widgets['theta_deg'].value == -123.456789


def test_n2_and_cutoff_derived_on_correct_height_grid(atmosphere):
    '''
    Purpose
    -------
    Verify N2 and cutoff derived on correct height grid.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    _, profiles = atmosphere
    z = profiles.height_km
    cs = 6+z/1000.
    expected = .274/200.-.274**2/cs**2
    np.testing.assert_allclose(profiles.quantities['N2'], expected, rtol=2e-14)
    np.testing.assert_allclose(profiles.quantities['wac'], cs/400., rtol=2e-14)
    record = profiles.parameters(50.,250.)
    points = np.unique(np.r_[50.,z[(z>50)&(z<250)],250.])
    independent = np.trapz(np.interp(points,z,expected),points)/200.
    assert record['parameters']['N2'] == pytest.approx(independent)
    assert record['units']['N2'] == 's^-2'
    assert record['parameters']['N2'] != pytest.approx(ap.interval_average(z,profiles.quantities['N_stored'],50.,250.)**2)


def test_unstable_stratification_preserves_negative_n2(atmosphere):
    '''
    Purpose
    -------
    Verify unstable stratification preserves negative N2.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    cfg, _ = atmosphere
    with netCDF4.Dataset(cfg['data']['file'], 'a') as cube:
        cube['rho'][:] = 1e-10
    profiles = ap.load_profiles(cfg)
    record = profiles.parameters(50.,250.)
    assert record['parameters']['N2'] < 0
    assert np.all(profiles.quantities['N2'] < 0)


def test_legacy_n_without_stratification_does_not_invent_a_sign():
    '''
    Purpose
    -------
    Verify legacy n without stratification does not invent a sign.

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

    record = ap.upgrade_atmosphere(dict(schema_version=1, parameters={'N': .02},unavailable={}))
    assert 'N' not in record['parameters'] and 'N2' not in record['parameters']
    assert 'cannot recover' in record['unavailable']['N2']


def test_legacy_metadata_refreshes_signed_n2_from_its_source(atmosphere):
    '''
    Purpose
    -------
    Verify legacy metadata refreshes signed N2 from its source.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    _, profiles = atmosphere
    record = profiles.parameters(50.,250.)
    expected = record['parameters'].pop('N2')
    record['schema_version'] = 1
    record['parameters']['N'] = .99  # Never trust this old unsigned diagnostic.
    record['initializations'] = {'nc2009': {'N':.99}}
    upgraded = ap.upgrade_atmosphere(record)
    assert upgraded['parameters']['N2'] == pytest.approx(expected)
    assert 'N' not in upgraded['parameters'] and 'initializations' not in upgraded
