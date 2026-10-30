'''
Purpose
-------
Publishing controls, exact source binding, and height markers.

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
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import netCDF4
import numpy as np
import pytest
from matplotlib.figure import Figure

from test_integrated_komega_explorer import app, calculate, select
from test_atmospheric_profiles import atmosphere, write_native
from test_coherence_switching import uniform_coherence
import atmospheric_profiles as profiles_module
import integrated_komega_explorer as sampling


@pytest.mark.parametrize('model_key', ['nc2009', 'alfven_mode', 'slow_mode', 'fast_mode', 'bunte1993', 'mt1982', 'mt1981'])
def test_independent_model_gaussian_and_coherence_switches(app, model_key):
    '''
    Purpose
    -------
    Verify independent model gaussian and coherence switches.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    model_key: str
        Model identifier selected in the explorer or solver fixture.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    app.model_select.value = model_key
    calculate(app)
    model = app.model
    original = model.last_result
    dataset = app.primary.result_source.data['image'][0].copy()
    transmission = model.transmission.copy()
    coherence = uniform_coherence(app, .5)
    with patch.object(app.model_workspace.vesa, 'compute_diagram', side_effect=AssertionError('Repeated roots')):
        for gaussian in (False, True, False):
            app.model_gaussian.active = gaussian
            expected = transmission if gaussian else np.ones_like(transmission)
            for enabled in (True, False):
                coherence.apply.active = enabled
                model.refresh_filter()
                assert model.last_result is original
                for field in ('phase_deg', 'kz_real', 'kz_imag'):
                    np.testing.assert_array_equal(getattr(model.filtered_result, field),
                        getattr(original, field)*expected[..., None])
                np.testing.assert_allclose(model.filtered.spectral_weight, expected*(.5 if enabled else 1.))
                np.testing.assert_array_equal(app.primary.result_source.data['image'][0], dataset)
                assert set(model.filtered.hover_source.data['filter_applied']) == {'yes' if gaussian else 'no'}
        assert app.state.model_gaussian_enabled is False
        assert not model.status.visible
        assert all(plot.title.text == '' for plot in [*model.plots, *model.filtered.plots])
        assert any(title.text == 'Gaussian and Coherence Weighted Model' for title in model.filtered.plot.above
                   if hasattr(title, 'text'))
        metadata = app.collect_metadata('filtered', [app.primary.result_plot, model.filtered.plot])
        assert metadata['gaussian_filter']['model_enabled'] is False


def test_sampling_format_no_counts_defaults_or_unsaved_text(app):
    '''
    Purpose
    -------
    Verify sampling format no counts defaults or unsaved text.

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

    primary_html = app.sampling_info.text
    select(app.secondary, app.primary.observations[1].id)
    app.left_toggle.active = True
    assert app.state.left_comparison and app.state.right_comparison
    html = app.sampling_info.text
    assert html == primary_html
    assert '<dl ' in html and '<dt ' in html and '<dd ' in html
    assert html.count('<section ') == 1
    assert 'Primary dataset' in html and 'Comparison dataset' not in html
    app.primary.search.value_input = 'a'
    assert not app.primary.count.visible and not app.primary.count.text
    app.primary._mark_unsaved()
    assert not app.primary.status.text
    app.model._set_status('<b>Warnings:</b> diagnostic', 'warning')
    assert not app.model.status.visible and 'diagnostic' not in app.model.status.text
    app.model_workspace.atmosphere = dict(status='unavailable', fallbacks={'nc2009': {'g': {}}})
    app.model_workspace.update_atmosphere_info('nc2009')
    assert not app.model_workspace.atmosphere_info.text
    assert app.sampling_info.text == html


def test_every_available_profile_line_gets_exact_black_height_markers(atmosphere, monkeypatch):
    '''
    Purpose
    -------
    Verify every available profile line gets exact black height markers.

    Inputs
    ------
    atmosphere: tuple
        Fixture containing the synthetic atmospheric configuration and loaded profiles.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    config, profiles = atmosphere
    write_native(config, profiles, 'pressure', [1000., 800., 500., 200., 100.], 'dyn/cm^2')
    write_native(config, profiles, 'plasma_beta', [100., 80., 50., 20., 10.], 'dimensionless')
    profiles = profiles_module.load_profiles(config)
    captured = []
    original = Figure.savefig

    def inspect(fig, *args, **kwargs):
        '''
        Purpose
        -------
        Inspect the generated figure against the enclosing reference values before
        delegating.

        Inputs
        ------
        fig: matplotlib.figure.Figure
            Figure inspected before delegating to the original writer.

        *args: tuple
            Positional arguments accepted by the wrapper, or parsed benchmark options.

        **kwargs: dict
            Keyword arguments accepted by the substituted or wrapped callable.

        Outputs
        -------
        result: object
            Original figure-writer result after the fixture-specific assertions.
        '''

        if str(args[0]).endswith('.png'):
            for axis in fig.axes:
                curves = [line for line in axis.lines if line.get_label() != '_nolegend_']
                markers = [line for line in axis.lines if line.get_label() == '_nolegend_']
                assert len(curves) == len(markers)
                for curve, marker in zip(curves, markers):
                    np.testing.assert_array_equal(marker.get_xdata(), [.05, .25])
                    np.testing.assert_array_equal(marker.get_ydata(),
                        np.interp([.05, .25], curve.get_xdata(), curve.get_ydata()))
                    assert marker.get_color() == 'black' and marker.get_marker() == 'o'
                    captured.append(curve.get_label())
        return original(fig, *args, **kwargs)

    monkeypatch.setattr(Figure, 'savefig', inspect)
    first = profiles_module.save_diagnostic(profiles, config['paths']['figure_dir'], height_pair_km=(50., 250.))
    assert len(captured) == 9
    monkeypatch.setattr(Figure, 'savefig', original)
    second = profiles_module.save_diagnostic(profiles, config['paths']['figure_dir'], height_pair_km=(0., 300.))
    assert first != second


def test_selected_source_and_height_pair_control_embedded_profile(atmosphere):
    '''
    Purpose
    -------
    Verify selected source and height pair control embedded profile.

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

    config, profiles = atmosphere
    record = profiles.parameters(0., 300.)
    data = SimpleNamespace(metadata=dict(source_type='single_cube', atmospheric_parameters=record), analysis_config=config)
    first = sampling.simulation_profile_html(data)
    assert 'data:image/png;base64,' in first and 'black dots: z = 0 and 0.3 Mm' in first
    data.metadata['atmospheric_parameters'] = profiles.parameters(100., 300.)
    second = sampling.simulation_profile_html(data)
    assert first != second and 'black dots: z = 0.1 and 0.3 Mm' in second
    # A second simulation with a different Model/profile must produce different art.
    import shutil
    root = Path(config['data']['file']).parent
    other_cube, other_profile = root/'second.nc', root/'OTHER_t00000020s_atmos_param.h5'
    shutil.copy(config['data']['file'], other_cube)
    shutil.copy(profiles.provenance['profile']['path'], other_profile)
    with netCDF4.Dataset(other_cube, 'a') as cube:
        cube.Model = 'OTHER'
    other_config = deepcopy(config)
    other_config['data']['file'] = str(other_cube)
    other = profiles_module.load_profiles(other_config)
    data.analysis_config = other_config
    data.metadata['atmospheric_parameters'] = other.parameters(0., 300.)
    third = sampling.simulation_profile_html(data)
    assert 'OTHER' in third and third != first and 'data:image/png;base64,' in third
    data.metadata['atmospheric_parameters'] = record
    assert 'does not match the selected simulation' in sampling.simulation_profile_html(data)
