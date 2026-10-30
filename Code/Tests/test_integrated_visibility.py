'''
Purpose
-------
Independent presentation, inline spatial state and asynchronous model lifecycle.

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
from unittest.mock import patch

import numpy as np
import pytest
from bokeh.models import Label

from test_integrated_komega_explorer import app, calculate
from test_bokeh_responsiveness import ControlledPool, finish_job, drain


def test_spatial_follows_parameters_in_one_document_without_navigation(app):
    '''
    Purpose
    -------
    Verify spatial follows parameters in one document without navigation.

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

    children = app.middle_section.children
    assert children[children.index(app.dispersion_section.layout)+1] is app.spatial.layout
    assert len(app.doc.roots) == 1
    assert app.spatial.layout.visible and app.komega_view.visible
    assert app.doc.get_model_by_name('integrated:spatial') is None
    assert app.doc.get_model_by_name('spatial:back') is None
    assert app.spatial.inputs.metadata['dataset_id'] == app.primary.selected_id
    assert app.spatial.strength.value == 10. and app.spatial.inclination.value == 45.
    assert app.spatial.section.plot_body.children == app.spatial.plot_sections


def test_all_plot_and_control_switches_preserve_state_and_never_compute(app):
    '''
    Purpose
    -------
    Verify all plot and control switches preserve state and never compute.

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

    calculate(app)
    sections = [app.gaussian_section, app.dispersion_section, app.spatial.section]
    spatial = app.spatial
    original = spatial.filtered
    images = [source.data['image'][0].copy() for source in spatial.sources]
    params = dict(app.state.model_parameters)
    with patch.object(app.model_workspace.vesa, 'compute_diagram', side_effect=AssertionError('root solve')), \
         patch.object(spatial, '_work', side_effect=AssertionError('FFT work')), \
         patch.object(app.primary, '_refresh_preview', side_effect=AssertionError('dataset calculation')):
        for section in sections:
            section.plot_toggle.active = False
            assert section.body.visible
            section.toggle.active = False
            assert not section.body.visible
            section.plot_toggle.active = True
            assert not section.body.visible
            section.toggle.active = True
        for toggle, plot in [(app.dataset_plot_toggle, app.primary.observed_plot),
                             (app.filtered_plot_toggle, app.primary.result_plot),
                             *zip(spatial.subplot_toggles, spatial.plots)]:
            toggle.active = False
            assert not plot.visible
            toggle.active = True
            assert plot.visible
        for toggle in (app.left_controls_toggle, app.right_controls_toggle,
                       app.model_workspace.coherence.controls_toggle):
            toggle.active = False
            toggle.active = True
    assert app.state.model_parameters == params and spatial.filtered is original
    for source, before in zip(spatial.sources, images):
        np.testing.assert_array_equal(source.data['image'][0], before)


def test_worker_result_from_previous_activation_cannot_settle_new_selection(app):
    '''
    Purpose
    -------
    Verify worker result from previous activation cannot settle new selection.

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

    model, workspace = app.model, app.model_workspace
    pool = ControlledPool()
    workspace.async_models = True
    workspace.model_runner.pool = pool
    model._recompute()
    first = pool.jobs[0]
    app.model_select.value = 'mt1981'
    app.model_select.value = 'nc2009'
    model.widgets['cs'].value += .2
    model._recompute()
    finish_job(app.doc, first)
    assert model.last_result is None and model._dirty
    assert len(pool.jobs) == 2
    finish_job(app.doc, pool.jobs[1])
    assert not model._dirty
    assert dict(model.last_result.parameter_values)['cs'] == model.widgets['cs'].value
    assert not any('Updating model' in label.text for plot in model.plots
                   for label in plot.select(type=Label))


def test_executor_submission_failure_settles_busy_status_and_recovers(app):
    '''
    Purpose
    -------
    Verify executor submission failure settles busy status and recovers.

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

    model, workspace = app.model, app.model_workspace
    workspace.async_models = True
    with patch.object(workspace.model_runner.pool, 'submit', side_effect=RuntimeError('executor unavailable')):
        model._recompute()
    assert 'executor unavailable' in model.status.text
    assert 'Calculating' not in model.status.text
    pool = ControlledPool()
    workspace.model_runner.pool = pool
    model._recompute()
    finish_job(app.doc, pool.jobs[0])
    assert model.last_result is not None and not model._dirty


def test_exact_inputs_and_shared_frequency_units_trigger_native_callbacks(app):
    '''
    Purpose
    -------
    Verify exact inputs and shared frequency units trigger native callbacks.

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

    calculate(app)
    model = app.model
    for key in ('cs', 'N2', 'wac', 'dz'):
        control = model.numeric_controls[key]
        old = float(control.input.value)
        control.input.value = repr(old + (.01 if key != 'dz' else 10.))
        assert float(control.input.value) == pytest.approx(control.slider.value)
        if model._dirty:
            model._perform_recompute()
        assert not model._dirty, model.status.text
        assert dict(model.last_result.parameter_values)[key] == model.widgets[key].value
        for other in app.model_workspace.models:
            if key in other.widgets:
                assert other.widgets[key].value == model.widgets[key].value
    value = model.widgets['cs'].value
    app.model_select.value = 'mt1981'
    assert app.model.widgets['cs'].value == value
    app.model.numeric_controls['cs'].input.value = repr(value + .1)
    app.model_select.value = 'nc2009'
    assert app.model.widgets['cs'].value == value + .1


def test_client_plot_visibility_follows_new_branches_without_echoing_layout(app):
    '''
    Purpose
    -------
    Verify client plot visibility follows new branches without echoing layout.

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

    from test_bokeh_responsiveness import node
    button = app.dispersion_section.plot_toggle
    callbacks = button.js_property_callbacks['change:active']
    assert len(callbacks) == 1
    callback = callbacks[0]
    for grid in (app.left_plots, app.right_plots):
        assert grid.js_property_callbacks['change:children'] == [callback]
    result = node(r'''
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let patches=0;
const model=()=>({visible:true,data:[1,2,3],setv(v,o){if(o.sync!==false)patches++;Object.assign(this,v);}});
const button=model(),data=model(),comparison={active:false};
const grids=[{children:[[data,0,0],[model(),1,0]]},{children:[[data,0,0],[model(),1,0]]}];
const run=new Function('targets','title','button','grids','comparison',p.code);
for(const active of [false,true,false,true]) {
    button.active=active;
    for(let i=0;i<10;i++) {
        for(const grid of grids)grid.children[1][0]=model();
        run([], 'Plot',button,grids,comparison);
        if(grids.some(g=>g.children[1][0].visible!==active))throw Error('New model lost visibility');
        if(!data.visible)throw Error('Dataset hidden with model');
    }
}
comparison.active=true;button.active=false;
run([],'Plot',button,grids,comparison);
if(grids.some(g=>!g.children[1][0].visible))throw Error('Comparison hidden by model controls');
process.stdout.write(JSON.stringify({patches}));
''',dict(code=callback.code))
    assert result['patches'] == 0


def test_unavailable_spatial_source_clears_prior_dataset_labels_and_disables_inputs(app):
    '''
    Purpose
    -------
    Verify unavailable spatial source clears prior dataset labels and disables inputs.

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

    from dataclasses import replace
    view = app.spatial
    assert view.inputs is not None and view.info.text
    data = app.primary.data
    before = (view.strength.value, view.inclination.value, view.frequency.value)
    app.primary.data = replace(data, dopplergrams=None)
    view.sync()
    assert view.inputs is None and view.filtered is None
    assert not view.info.text and not view.filter_info.text and not view.magnetic_info.text
    assert all(widget.disabled for widget in (view.frequency, view.strength,
                                             view.inclination, view.contour_sigma))
    assert before == (view.strength.value, view.inclination.value, view.frequency.value)
    assert all(np.isnan(source.data['image'][0]).all() for source in view.sources)
    app.primary.data = data
    view.sync()
    assert view.inputs is not None and not view.frequency.disabled


def test_comparison_controls_collapse_independently_from_primary_controls(app):
    '''
    Purpose
    -------
    Verify comparison controls collapse independently from primary controls.

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

    app.left_toggle.active = True
    assert app.secondary_visibility.visible and app.secondary_browser.visible
    app.secondary_controls_toggle.active = False
    assert not app.secondary_controls.visible
    app.left_controls_toggle.active = False
    app.secondary_controls_toggle.active = True
    assert app.secondary_controls.visible
    assert app.secondary_browser.visible
    assert not app.left_controls_toggle.active
    app.right_toggle.active = False
    app.left_toggle.active = True
    assert app.secondary_controls.visible
    assert app.secondary_visibility.visible


def test_selection_enforces_activation_if_detached_tab_callback_is_absent(app):
    '''
    Purpose
    -------
    Verify selection enforces activation if detached tab callback is absent.

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

    workspace = app.model_workspace
    workspace.tabs.remove_on_change('active', workspace._active_changed)
    for index, model in enumerate(workspace.models):
        app.model_select.value = model.definition.key
        assert workspace.tabs.active == index
        assert model._active
        assert sum(item._active for item in workspace.models) == 1
        if index:
            assert model._pending_callback is not None
