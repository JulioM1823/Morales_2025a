'''
Purpose
-------
Execute client callbacks and exercise latest-only numerical publication.

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
from concurrent.futures import Future
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import numpy as np
import pytest
from bokeh.document import Document
from bokeh.models import Div, Label

TD = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(TD))
import gaussian_filter_explorer as gaussian
from bokeh_ui_helpers import CollapsibleSection, LatestModelRunner


def node(code, payload):
    '''
    Purpose
    -------
    Execute a JavaScript callback in Node with JSON input and decode its JSON output.

    Inputs
    ------
    code: str
        JavaScript executed with Node to validate the shipped callback.

    payload: object
        JSON-serializable input sent to the Node process.

    Outputs
    -------
    result: object
        Decoded standard output. Skip when Node is unavailable; fail the test
        if the child process exits unsuccessfully.
    '''

    # Send JSON through the real Node process and require a successful callback
    # execution.
    executable = shutil.which('node')
    if executable is None:
        pytest.skip('Node is required to execute the shipped client callback.')
    result = subprocess.run([executable, '-e', code], input=json.dumps(payload),
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('nt', [40, 41, 482, 481])
@pytest.mark.parametrize('parameters', [dict(central_k=1.5, width_k=4., central_f=3., width_f=3.),
    dict(central_k=.5, width_k=10., central_f=0., width_f=12.),
    dict(central_k=6., width_k=.17, central_f=7., width_f=.2)])
def test_live_javascript_matches_python_and_coalesces_drag_events(nt, parameters):
    '''
    Purpose
    -------
    Verify live JavaScript matches python and coalesces drag events.

    Inputs
    ------
    nt: int or None
        Number of temporal samples in the synthetic cube.

    parameters: dict or callable
        Input parameters or the fixture helper that constructs them.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    geometry = gaussian.PreviewGeometry(48, nt, 30., .16, 'regression')
    kh, frequency = gaussian.build_filter_axes(geometry)
    passband, suppressor, reflected = gaussian._filter_grid(tuple(kh), tuple(frequency))
    payload = dict(code=(TD / 'gaussian_preview.js').read_text(), parameters=parameters,
        data=dict(kh=[kh.tolist()], frequency=[frequency.tolist()], passband=[passband.ravel().tolist()],
                  suppressor=[suppressor.tolist()], reflected=[reflected.tolist()],
                  positive=[np.flatnonzero(frequency >= 0).tolist()]))
    actual = node(r'''
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const frames=[], image={}, hover={}, mapper={}, error={};
const grid={data:p.data}, sliders=Object.fromEntries(Object.entries(p.parameters).map(([k,v])=>[k,{value:v}]));
const requestAnimationFrame=f=>{frames.push(f);return frames.length;};
const Bokeh={require:()=>({ndarray:(values,opts)=>({values:Array.from(values),shape:opts.shape})})};
const run=new Function('grid','sliders','image','hover','mapper','error','requestAnimationFrame','performance','Bokeh',p.code);
for(let i=0;i<100;i++)run(grid,sliders,image,hover,mapper,error,requestAnimationFrame,performance,Bokeh);
if(frames.length!==1)throw Error('Unbounded animation-frame queue');
frames.shift()();
if(error.visible)throw Error(error.text);
process.stdout.write(JSON.stringify({image:image.data.image[0],extent:[image.data.x[0],image.data.y[0],image.data.dw[0],image.data.dh[0]],
    hover:hover.data.transmission?Array.from(hover.data.transmission):[],high:mapper.high}));
''', payload)
    expected = gaussian.compute_filter_result(geometry, **parameters)
    values = np.asarray(actual['image']['values']).reshape(actual['image']['shape'])
    np.testing.assert_allclose(values, expected.transmission, rtol=2e-14, atol=2e-15)
    np.testing.assert_array_equal(np.asarray(actual['hover']).reshape(values.shape), values)
    x, y = gaussian.axis_limits(expected.kh), gaussian.axis_limits(expected.nu)
    np.testing.assert_allclose(actual['extent'], [x[0], y[0], x[1]-x[0], y[1]-y[0]], atol=1e-13)
    assert actual['high'] == pytest.approx(max(expected.transmission.max(), 1e-12), abs=2e-15)


def test_collapsible_client_callback_changes_only_local_presentation():
    '''
    Purpose
    -------
    Verify collapsible client callback changes only local presentation.

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

    section = CollapsibleSection('Gaussian Filter', Div(text='controls'),
                                 name='regression', related=(Div(text='related'),))
    callback = section.toggle.js_property_callbacks['change:active'][0]
    assert not section.toggle.syncable
    result = node(r'''
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let patches=0;
const model=()=>({value:2.345,visible:true,setv(v,o){if(o.sync!==false)patches++;Object.assign(this,v);}});
const targets=[model(),model()],button=model();
const run=new Function('targets','title','button','grids','comparison',p.code);
for(let i=0;i<20;i++)for(const active of [false,true]) {
    button.active=active;run(targets,'Gaussian Filter',button,[],null);
    if(targets.some(t=>t.visible!==active||t.value!==2.345))throw Error('Lost state');
    if(button.label!==(active?'Hide ':'Show ')+'Gaussian Filter')throw Error('Wrong label');
}
process.stdout.write(JSON.stringify({patches}));
''', dict(code=callback.code))
    assert result['patches'] == 0


class ControlledPool:
    '''
    Purpose
    -------
    Record deferred calculation/Future pairs so tests control completion order.

    Inputs
    ------
    None
        Constructed by the test framework or its enclosing fixture.

    Outputs
    -------
    instance: ControlledPool
        Fixture or test-suite object providing the documented methods.
    '''

    def __init__(self):
        '''
        Purpose
        -------
        Initialize the synthetic object state required by the enclosing test.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        None
            Store fixture values, metadata, or mutable call-recording containers on
            self.
        '''

        self.jobs = []

    def submit(self, calculate):
        '''
        Purpose
        -------
        Record deferred worker work and return the controlled Future used by the test.

        Inputs
        ------
        calculate: callable
            Deferred calculation recorded instead of being executed immediately.

        Outputs
        -------
        future: concurrent.futures.Future
            Future retained by the enclosing fixture; the test decides when the
            recorded callable runs or when the Future is completed.
        '''

        future = Future()
        self.jobs.append((calculate, future))
        return future


def drain(doc):
    '''
    Purpose
    -------
    Execute and remove the currently scheduled next-tick Bokeh callbacks.

    Inputs
    ------
    doc: bokeh.document.Document
        Document whose pending callbacks are executed synchronously.

    Outputs
    -------
    None
        Mutate the document callback queue and run each captured callback.
    '''

    # Capture the queue before removing and running the current next-tick callbacks.
    callbacks = list(doc.session_callbacks)
    for callback in callbacks:
        doc.remove_next_tick_callback(callback)
        callback.callback()


def test_runner_bounds_work_discards_obsolete_results_recovers_errors_and_closes():
    '''
    Purpose
    -------
    Verify runner bounds work discards obsolete results recovers errors and closes.

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

    doc, pool = Document(), ControlledPool()
    runner = LatestModelRunner(doc, pool)
    generation, published = [0], []
    for i in range(100):
        generation[0] = i
        runner.request(lambda i=i: i, lambda value, error: published.append((value,error)),
                       lambda i=i: generation[0] == i)
    assert len(pool.jobs) == 1
    pool.jobs[0][1].set_result(0)
    drain(doc)
    assert published == [] and len(pool.jobs) == 2
    pool.jobs[1][1].set_exception(ValueError('numerical failure'))
    drain(doc)
    assert len(published) == 1 and isinstance(published[0][1], ValueError)
    runner.request(lambda: 100, lambda value,error: published.append((value,error)), lambda: True)
    pool.jobs[2][1].set_result(100)
    drain(doc)
    assert published[-1] == (100, None)
    runner.request(lambda: 101, lambda value,error: published.append((value,error)), lambda: True)
    runner.close()
    assert pool.jobs[-1][1].cancelled()
    assert runner.pending is None


def test_live_preview_is_wired_to_continuous_value_and_geometry_changes():
    '''
    Purpose
    -------
    Verify live preview is wired to continuous value and geometry changes.

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

    app = gaussian.build_document(Document(), schedule_initial=False)
    for slider in app.sliders.values():
        assert slider.js_property_callbacks['change:value'] == [app.preview_callback]
        assert 'change:value_throttled' not in slider.js_property_callbacks
    app._perform_recompute()
    grid = app.preview_grid.data
    app.sliders['central_k'].value += .5
    app._perform_recompute()
    assert app.preview_grid.data is grid  # No invariant-grid retransmission.
    app.geometry = gaussian.PreviewGeometry(50, 41, 11.88, .43, 'changed sampling')
    app._perform_recompute()
    assert app.preview_grid.data is not grid


def test_invalid_sampling_clears_client_grid_and_valid_sampling_restores_it():
    '''
    Purpose
    -------
    Verify invalid sampling clears client grid and valid sampling restores it.

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

    app = gaussian.build_document(Document(), schedule_initial=False)
    geometry = app.geometry
    app._perform_recompute()
    app.geometry = gaussian.PreviewGeometry(0, 41, 30., .16, 'invalid')
    app._perform_recompute()
    assert app.error_label.visible and app.preview_grid.data['kh'] == []
    app.geometry = geometry
    app._perform_recompute()
    assert not app.error_label.visible and len(app.preview_grid.data['kh']) == 1


def test_server_preview_renders_on_document_ready_without_old_source_writeback():
    '''
    Purpose
    -------
    Verify server preview renders on document ready without old source writeback.

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

    doc = Document()
    with patch.object(Document, 'session_context', property(lambda self: object())):
        app = gaussian.build_document(doc, schedule_initial=False)
        app._perform_recompute()
        assert app.preview_callback in doc.callbacks._js_event_callbacks['document_ready']
        assert len(app.preview_grid.data['kh']) == 1
        original = app.image_source.data
        app.sliders['central_k'].value += .5
        app._perform_recompute()
        assert app.image_source.data is original


from test_integrated_komega_explorer import app, calculate, run_scheduled


def finish_job(doc, job):
    '''
    Purpose
    -------
    Complete a controlled worker job and run the callbacks it schedules.

    Inputs
    ------
    doc: bokeh.document.Document
        Document whose pending callbacks are executed synchronously.

    job: tuple
        Deferred callable and Future recorded by the controlled executor.

    Outputs
    -------
    None
        Resolve the Future, then execute newly registered document callbacks.
    '''

    # Resolve the recorded worker and execute only callbacks newly scheduled by its
    # completion.
    before = set(doc.session_callbacks)
    job[1].set_result(job[0]())
    for callback in set(doc.session_callbacks) - before:
        doc.remove_next_tick_callback(callback)
        callback.callback()


def test_live_model_runner_publishes_only_latest_snapshot_and_recovers_failure(app):
    '''
    Purpose
    -------
    Verify live model runner publishes only latest snapshot and recovers failure.

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
    # The numerical worker must not read changing widgets.
    with patch.object(model, '_current_values', side_effect=AssertionError('Worker read a widget')):
        original = first[0]()
    for value in [7.9, 8.0, 8.1]:
        model.widgets['cs'].value = value
        model._recompute()
    assert len(pool.jobs) == 1
    before = set(app.doc.session_callbacks)
    first[1].set_result(original)
    for callback in set(app.doc.session_callbacks) - before:
        app.doc.remove_next_tick_callback(callback)
        callback.callback()
    assert model.last_result is None and len(pool.jobs) == 2
    finish_job(app.doc, pool.jobs[1])
    assert not model._dirty
    assert dict(model.last_result.parameter_values)['cs'] == 8.1
    expected = workspace.vesa.compute_diagram(model.definition.key, model._current_values(),
        kh_mm_inv=app.primary.data.kh, nu_mhz=app.primary.data.nu)
    np.testing.assert_array_equal(model.last_result.phase_deg, expected.phase_deg)
    np.testing.assert_array_equal(model.last_result.kz_real, expected.kz_real)
    model.widgets['cs'].value = 8.2
    model._recompute()
    before = set(app.doc.session_callbacks)
    pool.jobs[-1][1].set_exception(ValueError('Injected numerical failure'))
    for callback in set(app.doc.session_callbacks) - before:
        app.doc.remove_next_tick_callback(callback)
        callback.callback()
    assert 'Calculation failed' in model.status.text
    assert 'Injected numerical failure' in model.status.text
    assert model.last_result is None and model.filtered_result is None
    assert all('Updating model' not in label.text for plot in [*model.plots, *model.filtered.plots]
               for label in plot.select(type=Label))
    model.widgets['cs'].value = 8.3
    model._recompute()
    finish_job(app.doc, pool.jobs[-1])
    assert model.last_result is not None and 'Calculating' not in model.status.text


def test_gaussian_and_toggles_do_not_enqueue_roots_and_diagram_edit_during_yield_recovers(app):
    '''
    Purpose
    -------
    Verify gaussian and toggles do not enqueue roots and diagram edit during yield
    recovers.

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
    with patch.object(app.model_workspace.vesa, 'compute_diagram', side_effect=AssertionError('Repeated solve')):
        app.gaussian_section.toggle.active = False
        app.dispersion_section.toggle.active = False
        app.primary.filter.sliders['width_f'].value = 2.4
        app.primary.filter._perform_recompute()
        model.widgets['dz'].value += 10
    model.widgets['cs'].value += .2
    model._recompute()  # Debounce has fired; old implementation lost its handle.
    assert model._pending_callback is None
    model.widgets['dz'].value += 10
    assert model._pending_callback is not None
    run_scheduled(app.doc, model._pending_callback)
    assert model.last_result is not None and not model._dirty
    assert dict(model.last_result.parameter_values)['dz'] == model.widgets['dz'].value


def test_diagram_edit_during_background_solve_reuses_exact_roots(app):
    '''
    Purpose
    -------
    Verify diagram edit during background solve reuses exact roots.

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
    for value in [230., 240., 250.]:
        model.widgets['dz'].value = value
        model._recompute()
    finish_job(app.doc, pool.jobs[0])
    assert len(pool.jobs) == 1
    assert dict(model.last_result.parameter_values)['dz'] == 250.
    expected = workspace.vesa.compute_diagram(model.definition.key, model._current_values(),
        kh_mm_inv=app.primary.data.kh, nu_mhz=app.primary.data.nu)
    np.testing.assert_allclose(model.last_result.phase_deg, expected.phase_deg, rtol=1e-13, atol=1e-13, equal_nan=True)
    np.testing.assert_array_equal(model.last_result.kz_real, expected.kz_real)


def test_responsive_layout_preserves_selection_without_server_writebacks(app):
    '''
    Purpose
    -------
    Verify responsive layout preserves selection without server writebacks.

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

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required to execute the responsive JavaScript regression.')
    callback = next(cb for cb in app.doc.callbacks._js_event_callbacks['document_ready']
                    if 'left_grid' in cb.args)
    # Proxy setters emulate Bokeh's default property synchronization. setv with
    # sync:false still changes presentation but must emit no server patch.
    harness = r'''
const {code} = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const assert = require('node:assert/strict');
const outbound = [], connected = [];
function model(initial) {
    const values = {...initial};
    const methods = {
        setv(changes, options={}) {
            Object.assign(values, changes);
            if (options.sync !== false) outbound.push(...Object.keys(changes));
        },
        properties: {children: {change: {connect(f) { connected.push(f); }}}},
    };
    return new Proxy(methods, {
        get(target, key) { return key in target ? target[key] : values[key]; },
        set(target, key, value) { values[key] = value; outbound.push(key); return true; },
    });
}
const first=model({id:'data'}), a=model({id:'model-A'}), b=model({id:'model-B'});
const filtered=model({id:'filtered-data'}), fa=model({id:'filtered-A'}), fb=model({id:'filtered-B'});
const left=model({}), middle=model({}), right=model({}), preview=model({});
const left_grid=model({children:[[first,0,0],[a,1,0]]});
const right_grid=model({children:[[filtered,0,0],[fa,1,0]]});
const workspace=model({children:[[left,0,0],[middle,0,1],[right,0,2]]});
const listeners={};
const window={innerWidth:420, addEventListener(name,fn){listeners[name]=fn;}};
new Function('workspace','left','middle','right','left_grid','right_grid','preview','window',code)
    (workspace,left,middle,right,left_grid,right_grid,preview,window);
for (const width of [1280,2400,420]) {
    // A new server selection must survive both responsive grid arrangements.
    left_grid.setv({children:[[first,0,0],[b,1,0]]},{sync:false});
    right_grid.setv({children:[[filtered,0,0],[fb,1,0]]},{sync:false});
    window.innerWidth=width;
    for (const callback of connected) callback();
    listeners.resize();
    assert.equal(left_grid.children[1][0],b);
    assert.equal(right_grid.children[1][0],fb);
    assert(left_grid.children[0][0].width>0);
    assert.equal(b.height,470);
}
assert.deepEqual(outbound,[], 'Presentation updates can overwrite newer server selections');
'''
    completed = subprocess.run([node, '-e', harness],
        input=json.dumps(dict(code=callback.code)), text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
