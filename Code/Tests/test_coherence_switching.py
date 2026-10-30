'''
Purpose
-------
Independent raster, weighting, atomic switching and cache regression checks.

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
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import json

import numpy as np
from bokeh.models import LinearColorMapper
from bokeh.document import Document
from bokeh.document.events import ColumnDataChangedEvent

from test_integrated_komega_explorer import app, calculate
import coherence_bokeh as rendering
import spectral_coherence as spectral
from bokeh_ui_helpers import model_graph_update


def uniform_coherence(app, value):
    '''
    Purpose
    -------
    Replace the active coherence result by a uniform value on the native data axes.

    Inputs
    ------
    app: object
        Bokeh explorer fixture whose controls, sources, and calculation state are
        checked.

    value: float
        Control, coherence, or validation value used by the current case.

    Outputs
    -------
    controls: object
        Updated coherence controls. Replace their result/cache entry and clear
        the aligned-data cache.
    '''

    # Replace coherence on the full native domain and clear the alignment cache.
    controls=app.model_workspace.coherence
    result=controls.result
    if result is None:
        controls.show.active=True
        result=controls.result
    # Cover the entire model domain so C=1 is an exact identity everywhere.
    data=app.primary.data
    result=replace(result,kh=data.kh,nu=data.nu,
                   values=np.full((len(data.kh),len(data.nu)),value))
    controls.result=result
    controls._cache[controls.key]=result
    controls._aligned.clear()
    return controls


def test_native_color_bins_and_pixel_orientation_independently():
    '''
    Purpose
    -------
    Verify native color bins and pixel orientation independently.

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

    mapper=LinearColorMapper(palette=['#010203','#405060','#a0b0c0','#ffffff'],
        low=-80.,high=80.,nan_color='#112233')
    values=np.array([[-90.,-80.,-40.,0.,40.,80.,90.,np.nan],
                     [80.,40.,0.,-40.,-80.,-90.,np.nan,90.]])
    expected_rgb=np.array([[0x030201,0x030201,0x605040,0xc0b0a0,0xffffff,0xffffff,0xffffff,0x332211],
                           [0xffffff,0xffffff,0xc0b0a0,0x605040,0x030201,0x030201,0x332211,0xffffff]],dtype=np.uint32)
    opacity=np.linspace(0.,1.,values.size).reshape(values.shape)
    packed=rendering.rgba_image(values,mapper,opacity)
    np.testing.assert_array_equal(packed & 0xffffff,expected_rgb)
    np.testing.assert_array_equal(packed >> 24,np.rint(opacity*255).astype(np.uint32))
    assert packed.flags.c_contiguous and packed.shape==values.shape
    assert not np.shares_memory(packed,values)


def test_coherence_threshold_preserves_gaussian_colors_and_continuous_weights(app):
    '''
    Purpose
    -------
    Verify coherence threshold preserves gaussian colors and continuous weights.

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
    model=app.model
    solver=model.last_result
    controls=uniform_coherence(app,1.)
    controls.apply.active=False
    baseline=[r.data_source.data['image'][0].copy() for r in model.filtered._coherence_overlays]
    baseline_values=[s.data['image'][0].copy() for s in model.filtered.image_sources]
    controls.apply.active=True
    for before,raster,values,source in zip(baseline,model.filtered._coherence_overlays,baseline_values,model.filtered.image_sources):
        np.testing.assert_array_equal(before,raster.data_source.data['image'][0])
        np.testing.assert_array_equal(values,source.data['image'][0])
    np.testing.assert_array_equal(model.filtered.spectral_weight,model.transmission)
    for value in (.5,0.):
        uniform_coherence(app,value)
        model.refresh_filter()
        np.testing.assert_allclose(model.filtered.spectral_weight,value*model.transmission,rtol=0,atol=0)
        for before,raster in zip(baseline,model.filtered._coherence_overlays):
            pixels=raster.data_source.data['image'][0]
            np.testing.assert_array_equal(pixels & 0xffffff,before & 0xffffff)
            # At the default zero threshold even C=0 is a supported visible bin.
            np.testing.assert_array_equal(pixels,before)
        controls.threshold.value = value + .01
        for raster in model.filtered._coherence_overlays:
            assert not np.any(raster.data_source.data['image'][0] >> 24)
        controls.threshold.value = value
        for before,raster in zip(baseline,model.filtered._coherence_overlays):
            np.testing.assert_array_equal(raster.data_source.data['image'][0],before)
        controls.threshold.value = 0.
    controls.apply.active=False
    for before,raster in zip(baseline,model.filtered._coherence_overlays):
        np.testing.assert_array_equal(before,raster.data_source.data['image'][0])
    assert model.last_result is solver


def test_cached_model_switch_reuses_glyphs_layouts_solutions_and_rasters(app):
    '''
    Purpose
    -------
    Verify cached model switch reuses glyphs layouts solutions and rasters.

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

    ctl=uniform_coherence(app,.7)
    ctl.apply.active=True
    originals={}
    for model in app.model_workspace.models:
        app.model_select.value=model.definition.key
        calculate(app)
        originals[model.definition.key]=(model.last_result,
            [r.data_source.data['image'][0].copy() for r in model._coherence_overlays],
            [r.data_source.data['image'][0].copy() for r in model.filtered._coherence_overlays])
    ids={plot.id:tuple(r.id for r in plot.renderers) for plot in app.all_plots()}
    panels=dict(app._control_panels)
    with patch.object(app.model_workspace.vesa,'compute_diagram',side_effect=AssertionError('Repeated solve')), \
         patch.object(rendering,'coherence_for_data',side_effect=AssertionError('Repeated FFT')):
        for _ in range(3):
            for model in app.model_workspace.models:
                app.model_select.value=model.definition.key
                result,unfiltered,filtered=originals[model.definition.key]
                assert model.last_result is result
                assert app._control_panels[model.definition.key] is panels[model.definition.key]
                for before,raster in zip(unfiltered,model._coherence_overlays):
                    np.testing.assert_array_equal(before,raster.data_source.data['image'][0])
                for before,raster in zip(filtered,model.filtered._coherence_overlays):
                    np.testing.assert_array_equal(before,raster.data_source.data['image'][0])
                assert app.left_plots.children[1][0] is model.plots[int(app.branch_select.value)]
                assert app.right_plots.children[1][0] is model.filtered.plots[int(app.branch_select.value)]
    assert ids=={plot.id:tuple(r.id for r in plot.renderers) for plot in app.all_plots()}


def test_threshold_mask_keeps_original_colors_and_hides_undefined_bins(app):
    '''
    Purpose
    -------
    Verify threshold mask keeps original colors and hides undefined bins.

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
    controls = uniform_coherence(app, 1.)
    original = model.last_result
    baseline = [r.data_source.data['image'][0].copy() for r in model.filtered._coherence_overlays]
    values = np.resize([.3, .4, .5, np.nan], controls.result.values.shape)
    controls.result = replace(controls.result, values=values)
    controls._cache[controls.key] = controls.result
    controls._aligned.clear()
    controls.threshold.value = .4
    controls.apply.active = True
    aligned = controls.aligned(original)
    expected = np.isfinite(aligned) & (aligned >= .4)
    assert expected.any() and not expected.all()
    for before, raster in zip(baseline, model.filtered._coherence_overlays):
        pixels = raster.data_source.data['image'][0]
        np.testing.assert_array_equal(pixels[expected], before[expected])
        np.testing.assert_array_equal(pixels >> 24, expected.astype(np.uint32) * 255)
    assert controls.status.text == '' and not controls.status.visible
    assert model.last_result is original
    assert 'full opacity' in controls.metadata()['display']


def test_old_second_stage_callback_cannot_repaint_after_switch_away_and_back(app):
    '''
    Purpose
    -------
    Verify old second stage callback cannot repaint after switch away and back.

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

    model=app.model
    model._recompute()
    old_callbacks=set(app.doc.session_callbacks)
    queued=[c for c in old_callbacks if type(c).__name__=='NextTickCallback']
    assert queued
    app.model_select.value='mt1981'
    app.model_select.value='nc2009'
    with patch.object(model,'_perform_recompute',side_effect=AssertionError('Stale queued solve')):
        for callback in queued: callback.callback()
    calculate(app)
    assert model.last_result is not None


def test_image_edges_match_solver_sample_centers_for_all_fields(app):
    '''
    Purpose
    -------
    Verify image edges match solver sample centers for all fields.

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

    for key in ('nc2009','bunte1993','mt1981'):
        app.model_select.value=key
        calculate(app)
        model=app.model
        for field in ('phase','kz_real','kz_imag'):
            model.field_select.value=field
            result=model.last_result
            for raster,source in zip(model._coherence_overlays,model.image_sources):
                data=raster.data_source.data
                nx,ny=len(result.kh_mm_inv),len(result.nu_mhz)
                np.testing.assert_allclose(data['x'][0]+(np.arange(nx)+.5)*data['dw'][0]/nx,result.kh_mm_inv,atol=1e-12)
                np.testing.assert_allclose(data['y'][0]+(np.arange(ny)+.5)*data['dh'][0]/ny,result.nu_mhz,atol=1e-12)
                assert data['image'][0].shape==source.data['image'][0].shape


def test_graph_batch_does_not_leave_document_frozen_after_failure():
    '''
    Purpose
    -------
    Verify graph batch does not leave document frozen after failure.

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

    doc=Document()
    try:
        with model_graph_update(doc): raise ValueError('test')
    except ValueError: pass
    assert doc.models._freeze_count==0


def test_latest_saved_megaplot_launch_context_preserves_identity_and_parameters():
    '''
    Purpose
    -------
    Verify latest saved megaplot launch context preserves identity and parameters.

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

    import komega_bokeh_context as context
    import komega_explorer as models
    import integrated_komega_explorer as integrated
    from figure_locations import canonical_figure_root,legacy_figure_root
    paths=[p for pattern in ('*.bokeh.json','*.subplots.json')
           for p in canonical_figure_root().rglob(pattern) if not p.is_symlink()]
    if not paths:
        archive=legacy_figure_root()
        paths=[] if archive is None else list((archive/'komega_contexts').glob('*.bokeh.json'))
    launch=None
    for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
        record=json.loads(path.read_text())
        if path.name.endswith('.subplots.json'):
            # Current megaplots embed each panel's exact workspace launch record.
            contexts=[target.get('bokeh',{}).get('workspace',{}).get('context')
                      for target in record.get('targets',[])]
            launch=next((item for item in contexts if item),None)
        else:
            launch=record.get('context',record)
        if launch is not None:
            break
    if launch is None:
        import pytest
        pytest.skip('No generated megaplot launch contexts in this checkout.')
    selected=context.validate_context(launch)
    application=integrated.build_document(Document(),launch_context=launch,
        product_roots=[],raw_roots=[],schedule_initial=True)
    assert application.primary.selected_id==selected.id
    assert application.model.definition.key=='nc2009'
    atmosphere=application.model_workspace.atmosphere
    expected=dict(atmosphere['initializations']['nc2009'] if atmosphere is not None
                  else launch['model']['parameters'])
    if 'N' in expected: expected['N2']=expected.pop('N')**2
    assert application.model._current_values().items()>=expected.items()


def test_bilinear_coherence_alignment_and_combined_weight_for_every_model(app):
    '''
    Purpose
    -------
    Verify bilinear coherence alignment and combined weight for every model.

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

    controls=uniform_coherence(app,1.)
    result=replace(controls.result,
        kh=np.linspace(app.primary.data.kh[0],app.primary.data.kh[-1],9),
        nu=np.linspace(app.primary.data.nu[0],app.primary.data.nu[-1],12))
    kh_grid,nu_grid=np.meshgrid(result.kh,result.nu,indexing='ij')
    analytic=.1+.2*kh_grid/result.kh[-1]+.3*nu_grid/result.nu[-1]
    controls.result=replace(result,values=analytic)
    controls._cache[controls.key]=controls.result
    controls._aligned.clear()
    controls.apply.active=True
    for model in app.model_workspace.models:
        app.model_select.value=model.definition.key
        calculate(app)
        raw=model.last_result
        kh,nu=np.meshgrid(raw.kh_mm_inv,raw.nu_mhz)
        expected=.1+.2*kh/result.kh[-1]+.3*nu/result.nu[-1]
        np.testing.assert_allclose(model.filtered.coherence_weight,expected,atol=1e-15)
        np.testing.assert_allclose(model.filtered.spectral_weight,expected*model.transmission,atol=1e-15)
        np.testing.assert_array_equal(raw.kz_real,model.last_result.kz_real)
    np.testing.assert_array_equal(controls.result.values,analytic)


def test_cached_and_fresh_physical_solver_arrays_are_identical(app):
    '''
    Purpose
    -------
    Verify cached and fresh physical solver arrays are identical.

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

    vesa=app.model_workspace.vesa
    for model in app.model_workspace.models:
        values=model._current_values()
        cached=vesa.compute_diagram(model.definition.key,values,(8,10),use_cache=True)
        fresh=vesa.compute_diagram(model.definition.key,values,(8,10),use_cache=False)
        for field in ('phase_deg','kz_real','kz_imag','omega_boundaries_mhz'):
            if hasattr(cached,field):
                np.testing.assert_array_equal(getattr(cached,field),getattr(fresh,field))


def test_document_ready_arguments_are_registered_before_browser_updates(app):
    # BokehJS keeps document callback args, but Python Document.from_json does
    # not restore them. A Python-only replay misses duplicate browser refs.
    '''
    Purpose
    -------
    Verify document ready arguments are registered before browser updates.

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

    for callbacks in app.doc.callbacks._js_event_callbacks.values():
        for callback in callbacks:
            for model in callback.references() - {callback}:
                assert app.doc.get_model_by_id(model.id) is model, model


def test_cached_solution_switch_keeps_sources_and_republishes_complete_pixels(app):
    '''
    Purpose
    -------
    Verify cached solution switch keeps sources and republishes complete pixels.

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
    original = model.last_result
    sides = (model, model.filtered)
    rasters = [side._coherence_overlays for side in sides]
    before = [[r.data_source.data['image'][0].copy() for r in side] for side in rasters]
    scalar = [[source.data['image'][0].copy() for source in side.image_sources]
              for side in sides]
    changes = []
    app.doc.on_change(changes.append)
    with patch.object(app.model_workspace.vesa, 'compute_diagram',
                      side_effect=AssertionError('Repeated solve')):
        for branch in (1, 0, model.branch_count - 1, 0):
            changes.clear()
            app.branch_select.value = str(branch)
            for side_index, side in enumerate(sides):
                raster = rasters[side_index][branch]
                assert any(isinstance(event, ColumnDataChangedEvent)
                           and event.model is raster.data_source for event in changes)
                for index, other in enumerate(rasters[side_index]):
                    assert app.doc.get_model_by_id(other.id) is other
                    assert other.data_source.document is app.doc
                    np.testing.assert_array_equal(other.data_source.data['image'][0],
                                                  before[side_index][index])
                    np.testing.assert_array_equal(side.image_sources[index].data['image'][0],
                                                  scalar[side_index][index])
    assert model.last_result is original


def test_switching_models_retains_cached_plot_models_in_document(app):
    '''
    Purpose
    -------
    Verify switching models retains cached plot models in document.

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

    originals = {}
    for model in app.model_workspace.models:
        app.model_select.value = model.definition.key
        calculate(app)
        originals[model.definition.key] = model.last_result
    for model in app.model_workspace.models:
        app.model_select.value = model.definition.key
        assert model.last_result is originals[model.definition.key]
        for other in app.model_workspace.models:
            for side in (other, other.filtered):
                for raster in side._coherence_overlays:
                    assert app.doc.get_model_by_id(raster.id) is raster
                    assert raster.data_source.document is app.doc
