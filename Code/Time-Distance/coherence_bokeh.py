'''
Purpose
-------
Share measured-coherence controls and preserve native phase colors while gating model
visibility.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for coherence_bokeh.py.

Notes
-----
Shared coherence controls and phase-preserving visibility for Bokeh models.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from html import escape
from functools import lru_cache

import numpy as np
from bokeh.layouts import column, row
from bokeh.models import ColorBar, ColumnDataSource, CustomJS, Div, LinearColorMapper, Slider, Toggle
from bokeh.palettes import Viridis256
from matplotlib.colors import to_rgba
from bokeh.plotting import figure

from bokeh_ui_helpers import style_phase_plot, visibility_toggle
from gaussian_filter_explorer import axis_limits
from spectral_coherence import align_coherence, coherence_for_data, coherence_weights, data_key
from vesa_support import support_module

COHERENCE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='spectral-coherence')


class CoherenceControls:
    '''
    Purpose
    -------
    Coordinate one lazy cached measured-coherence estimate per selected baseline pair.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    getter: callable
        Zero-argument getter returning the current loaded ObservationData or None.
    changed: callable
        Zero-argument owner callback invoked when coherence/display state changes.
    loader: callable or None
        Optional zero-argument baseline loader used when a dataset is not already
        loaded.
    x_range: bokeh.models.Range or None
        Optional horizontal range shared with existing komega views.
    y_range: bokeh.models.Range or None
        Optional frequency range shared with existing komega views.

    Outputs
    -------
    controls: CoherenceControls
        Shared controls, measured image, bounded result cache, and model-grid alignment
        cache.

    Notes
    -----
    One lazy, cached estimate per selected pair, shared by every model tab.
    '''
    def __init__(self, doc, getter, changed, *, loader=None, x_range=None, y_range=None):
        '''
        Purpose
        -------
        Build lazy coherence controls, image sources, and session-safe background state.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        getter: callable
            Getter for the selected loaded data.
        changed: callable
            Owner notification callback after accepted state changes.
        loader: callable or None
            Optional baseline loader for deferred coherence calculation.
        x_range: bokeh.models.Range or None
            Shared kh range in Mm^-1.
        y_range: bokeh.models.Range or None
            Shared frequency range in mHz.

        Outputs
        -------
        None
            Registers control/session callbacks and retains the exact-value threshold
            wrapper without calculating coherence initially.
        '''

        # Build lazy coherence controls, image sources, and session-safe background
        # state
        self.doc, self.getter, self.changed, self.loader = doc, getter, changed, loader
        self.result = self.key = self._pending_key = None
        self._generation, self._closed = 0, False
        self._future = None
        self._cache, self._aligned = OrderedDict(), {}
        self._loaded_data = None
        self._async = doc.session_context is not None
        # Build lazy estimator/display controls and the bounded exact coherence
        # threshold
        self.apply = Toggle(label='Apply Coherence Weighting', active=False,
                            sizing_mode='stretch_width', name='coherence:apply')
        self.show = Toggle(label='Show Plot', active=False,
                           sizing_mode='stretch_width', name='coherence:show')
        self.threshold = Slider(title='Minimum coherence C_min', start=0., end=1.,
            value=0., step=.01, width=240, name='coherence:threshold')
        self.numeric = support_module('numeric_controls').ExactSlider(
            self.threshold, 'coherence_threshold', hard_bounds=True)
        self.status = Div(text='', visible=False, sizing_mode='stretch_width', name='coherence:status',
                          styles={'overflow-wrap': 'anywhere', 'font-size': '12px'})
        self.status.on_change('text', lambda attr, old, new: setattr(self.status, 'visible', bool(new)))
        # Initialize the measured image and optional ranges shared with existing phase
        # views
        self.source = ColumnDataSource(dict(image=[np.full((2, 2), np.nan)],
            x=[0.], y=[0.], dw=[1.], dh=[1.]), name='coherence:image')
        self.mapper = LinearColorMapper(palette=Viridis256, low=0., high=1., nan_color='#a6a6a6')
        ranges = {}
        if x_range is not None:
            ranges['x_range'] = x_range
        if y_range is not None:
            ranges['y_range'] = y_range
        self.plot = figure(title='Measured magnitude-squared coherence', height=330,
            sizing_mode='stretch_width', x_axis_label='k_h [Mm⁻¹]', y_axis_label='ν [mHz]',
            tools='pan,wheel_zoom,box_zoom,reset,save', active_scroll=None,
            visible=False, name='coherence:plot', **ranges)
        self.plot.image(image='image', x='x', y='y', dw='dw', dh='dh',
                        source=self.source, color_mapper=self.mapper)
        self.plot.add_layout(ColorBar(color_mapper=self.mapper, title='C', width=16), 'right')
        style_phase_plot(self.plot)
        self.controls = column(self.apply, self.numeric.layout, self.status,
                               sizing_mode='stretch_width')
        self.controls_toggle = visibility_toggle((self.controls,), 'Controls',
                                                name='coherence:controls_toggle')
        self.layout = column(Div(text='<h3>Measured Coherence</h3>'),
            row(self.show, self.controls_toggle, sizing_mode='stretch_width'),
            self.controls, self.plot, sizing_mode='stretch_width',
            name='coherence:controls')
        self.show.js_on_change('active', CustomJS(args=dict(plot=self.plot), code="""
            plot.setv({visible:cb_obj.active}, {sync:false});
            cb_obj.setv({label:cb_obj.active ? 'Hide Plot' : 'Show Plot'}, {sync:false});
        """))
        # Connect presentation and estimator edits after all controls and sources exist
        self.show.on_change('active', self._show_changed)
        for widget, attr in ((self.apply, 'active'), (self.threshold, 'value')):
            widget.on_change(attr, self._changed)
        doc.on_session_destroyed(lambda context: self.close())

    def close(self):
        '''
        Purpose
        -------
        Invalidate pending work and release retained coherence caches on session
        closure.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Marks the instance closed, advances its generation, cancels cancellable
            work, and drops loaded-data references.
        '''

        # Invalidate pending work and release retained coherence caches on session
        # closure
        self._closed = True
        self._generation += 1
        if self._future is not None:
            self._future.cancel()
        self._cache.clear()
        self._aligned.clear()
        self._loaded_data = None

    def _changed(self, attr, old, new):
        '''
        Purpose
        -------
        Synchronize the current estimate and notify the owner after
        threshold/application edits.

        Inputs
        ------
        attr: str
            Bokeh property name supplied by the change callback.
        old: object
            Previous property value supplied by Bokeh.
        new: object
            Updated property value supplied by Bokeh.

        Outputs
        -------
        None
            Refreshes lazy calculation state and invokes the shared display-change
            callback.
        '''

        # Synchronize the current estimate and notify the owner after
        # threshold/application edits
        self.sync()
        self.changed()

    def _show_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Update measured-plot visibility and lazily calculate an absent estimate when
        opened.

        Inputs
        ------
        attr: str
            Bokeh property name supplied by the change callback.
        old: object
            Previous property value supplied by Bokeh.
        new: object
            Updated property value supplied by Bokeh.

        Outputs
        -------
        None
            Updates the Show/Hide label and requests synchronization only when needed.
        '''

        # Update measured-plot visibility and lazily calculate an absent estimate when
        # opened
        self.plot.visible = new
        self.show.label = 'Hide Plot' if new else 'Show Plot'
        if new and self.result is None:
            self.sync()

    def sync(self):
        '''
        Purpose
        -------
        Synchronize source-validated coherence state without repeating cached or pending
        FFT work.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Invalidates changed baselines, reuses a four-entry result cache, and
            computes only when display/application is active. Server sessions use a
            worker; offline documents calculate synchronously.

        Notes
        -----
        Called on dataset changes as well as controls; never repeat a pending FFT.
        '''
        # Synchronize source-validated coherence state without repeating cached or
        # pending FFT work
        if self._closed:
            return
        data = self.getter() if self.loader is None else self._loaded_data
        try:
            key = data_key(data) if data is not None else None
        except (ValueError, OSError) as exc:
            self._invalidate()
            self.status.text = escape(str(exc))
            return
        # Invalidate previous input generations before reusing any cached measured
        # estimate
        if key != self.key:
            self._invalidate()
            self.key = key
        if not (self.apply.active or self.show.active):
            return
        # Reuse exact source-state results and avoid duplicate requests for a pending
        # FFT
        if key in self._cache:
            self._cache.move_to_end(key)
            self._accept_result(self._cache[key])
            return
        if self._pending_key == (key,):
            return
        if data is None and self.loader is None:
            self.status.text = 'Measured coherence unavailable: select a dataset with its original Dopplergrams.'
            return
        generation = self._generation
        self._pending_key = (key,)
        self.status.text = 'Calculating coherence from the selected Dopplergram height pair…'

        # Capture the selected immutable baseline for worker-side coherence estimation
        def work():
            '''
            Purpose
            -------
            Load the selected baseline when needed and compute its measured coherence.

            Inputs
            ------
            None

            Outputs
            -------
            selected, key, result: tuple
                ObservationData, validated immutable baseline key, and CoherenceResult
                from original/post-magnetogram cubes.
            '''

            # Load the selected baseline when needed and compute its measured coherence
            selected = data if data is not None else self.loader()
            return selected, data_key(selected), coherence_for_data(selected)

        def accept(output=None, error=None):
            '''
            Purpose
            -------
            Accept only the current generation's source-validated coherence result.

            Inputs
            ------
            output: object or None
                Completed worker output, or None when an exception is supplied.
            error: Exception or None
                Worker exception, or None after a successful calculation.

            Outputs
            -------
            None
                Updates loaded baseline/result caches and display data, or reports a
                calculation/source-change error before notifying the owner.
            '''

            # Accept only the current generation's source-validated coherence result
            if self._closed or generation != self._generation:
                return
            self._pending_key = None
            if error is not None:
                self.status.text = 'Measured coherence unavailable: ' + escape(str(error))
            else:
                selected, computed_key, result = output
                try:
                    if data_key(selected) != computed_key:
                        raise ValueError('Inputs changed; reselect the dataset.')
                except (ValueError, OSError) as exc:
                    self.status.text = escape(str(exc))
                    self.changed()
                    return
                if self.loader is not None:
                    self._loaded_data = selected
                self.key = computed_key
                self._cache[computed_key] = result
                while len(self._cache) > 4:
                    self._cache.popitem(last=False)
                self._accept_result(result)
            self.changed()

        # Preserve deterministic offline execution and use the shared worker only for
        # live sessions
        if not self._async:
            try:
                output = work()
            except Exception as exc:
                accept(error=exc)
            else:
                accept(output)
            return
        self._future = COHERENCE_POOL.submit(work)

        def done(future):
            '''
            Purpose
            -------
            Collect a background coherence result and schedule its document-thread
            acceptance.

            Inputs
            ------
            future: concurrent.futures.Future
                Background calculation future whose result or exception is collected.

            Outputs
            -------
            None
                Closed instances ignore completion; worker exceptions are forwarded as
                acceptance errors.
            '''

            # Collect a background coherence result and schedule its document-thread
            # acceptance
            if self._closed:
                return
            try:
                output, error = future.result(), None
            except Exception as exc:
                output, error = None, exc
            self.doc.add_next_tick_callback(lambda: accept(output, error))
        self._future.add_done_callback(done)

    def _invalidate(self):
        '''
        Purpose
        -------
        Invalidate pending-generation results and clear current image/alignment state.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Cancels cancellable work, clears current keys/results and alignment cache,
            and publishes a NaN placeholder.
        '''

        # Invalidate pending-generation results and clear current image/alignment state
        self._generation += 1
        if self._future is not None:
            self._future.cancel()
        self.result = self.key = self._pending_key = None
        self._aligned.clear()
        self.source.data = dict(image=[np.full((2, 2), np.nan)], x=[0.], y=[0.], dw=[1.], dh=[1.])
        self.status.text = ''

    def _accept_result(self, result):
        '''
        Purpose
        -------
        Publish a newly accepted coherence estimate with physical image-cell edges.

        Inputs
        ------
        result: CoherenceResult
            Measured dimensionless coherence and exact Mm^-1/mHz axes.

        Outputs
        -------
        None
            Transposes project [kh,nu] values into Bokeh [nu,kh] image order and clears
            status. Reaccepting the identical result is a no-op.
        '''

        # Publish a newly accepted coherence estimate with physical image-cell edges
        if self.result is result:
            return
        self.result = result
        dk, df = result.kh[1]-result.kh[0], result.nu[1]-result.nu[0]
        self.source.data = dict(image=[result.values.T], x=[result.kh[0]-.5*dk],
            y=[result.nu[0]-.5*df], dw=[result.kh[-1]-result.kh[0]+dk],
            dh=[result.nu[-1]-result.nu[0]+df])
        self.status.text = ''

    def aligned(self, result):
        '''
        Purpose
        -------
        Reuse or interpolate the current coherence onto a model's exact coordinate grid.

        Inputs
        ------
        result: DiagramResult
            Model result supplying kh_mm_inv and nu_mhz axes.

        Outputs
        -------
        coherence: np.ndarray or None
            Cached [nu,kh] coherence without extrapolation, or None before an estimate
            exists.
        '''

        # Reuse or interpolate the current coherence onto a model's exact coordinate
        # grid
        if self.result is None:
            return None
        key = (result.kh_mm_inv.tobytes(), result.nu_mhz.tobytes())
        if key not in self._aligned:
            self._aligned[key] = align_coherence(self.result, result.kh_mm_inv, result.nu_mhz)
        return self._aligned[key]

    def metadata(self):
        '''
        Purpose
        -------
        Describe current estimator, threshold, visibility, and spectral-weight
        conventions.

        Inputs
        ------
        None

        Outputs
        -------
        metadata: dict
            Portable state/provenance; full estimator metadata is None before
            calculation.
        '''

        # Describe current estimator, threshold, visibility, and spectral-weight
        # conventions
        return dict(enabled=self.apply.active, threshold=self.threshold.value,
            view_measured_coherence=self.show.active,
            estimator=None if self.result is None else self.result.metadata,
            alignment='linear interpolation on kh/nu; no extrapolation; undefined cells have zero visibility',
            display='finite C >= C_min retains the native phase colors at full opacity; all other bins are hidden',
            application='combined spectral weight = T*C*H(C-C_min); solver fields unchanged')


@lru_cache(maxsize=16)
def _palette_rgba(palette):
    '''
    Purpose
    -------
    Convert and cache an immutable palette as floating-point RGBA channels.

    Inputs
    ------
    palette: tuple of color values
        Hashable native mapper palette converted through Matplotlib to_rgba.

    Outputs
    -------
    colors: np.ndarray
        Read-only (n_colors, 4) channel array in [0, 1].
    '''

    # Convert and cache an immutable palette as floating-point RGBA channels
    colors = np.asarray([to_rgba(color) for color in palette])
    colors.setflags(write=False)
    return colors


def rgba_image(values, mapper, opacity):
    '''
    Purpose
    -------
    Materialize a complete contiguous packed RGBA raster using native linear-mapper
    bins.

    Inputs
    ------
    values: array-like
        Two-dimensional scalar image values in their native physical units.
    mapper: bokeh.models.LinearColorMapper
        Native palette, range limits, missing color, and optional out-of-range colors.
    opacity: array-like or float
        Alpha multiplier broadcast to values.shape; nonfinite opacity becomes zero and
        values are clipped to [0,1].

    Outputs
    -------
    image: np.ndarray, uint32
        Independent C-contiguous packed RGBA image matching values.shape; opacity
        affects alpha while native RGB mapping and missing/out-of-range colors are
        retained.

    Notes
    -----
    Materialize a complete contiguous raster using native linear mapper bins.

    Never reuse a browser color-mapped canvas or a partially filled pixel buffer.
    Physical scalar arrays remain in their native sources and are not modified.
    '''
    # Materialize a complete contiguous packed RGBA raster using native linear-mapper
    # bins
    values = np.asarray(values, dtype=float)
    opacity = np.broadcast_to(np.asarray(opacity, dtype=float), values.shape)
    palette = _palette_rgba(tuple(mapper.palette))
    span = mapper.high - mapper.low
    with np.errstate(invalid='ignore', divide='ignore'):
        normalized = (values-mapper.low)/span if span else np.zeros_like(values)
    index = np.floor(np.nan_to_num(normalized, nan=0., posinf=1., neginf=0.)
                     .clip(0., 1.)*len(palette)).astype(int).clip(0, len(palette)-1)
    colors = palette[index].copy()
    colors[np.isnan(values)] = to_rgba(mapper.nan_color)
    if mapper.low_color is not None:
        colors[values < mapper.low] = to_rgba(mapper.low_color)
    if mapper.high_color is not None:
        colors[values > mapper.high] = to_rgba(mapper.high_color)
    channels = np.rint(colors*255).astype(np.uint32)
    channels[..., 3] = np.rint(colors[..., 3]*np.nan_to_num(opacity, nan=0.).clip(0.,1.)*255).astype(np.uint32)
    packed = (channels[..., 0] | channels[..., 1] << 8 |
              channels[..., 2] << 16 | channels[..., 3] << 24)
    return np.array(packed, dtype=np.uint32, order='C', copy=True)


def render_model_pixels(model, result, opacity=1., *, branch=None):
    '''
    Purpose
    -------
    Publish complete pixels through persistent model RGBA renderers in weighted and
    unweighted states.

    Inputs
    ------
    model: Bokeh model or explorer
        Model/layout or dispersion explorer operated on by this helper.
    result: DiagramResult
        Model grid coordinates and physical result shape.
    opacity: array-like or float
        Display alpha multiplier broadcast to the selected scalar images.
    branch: int or None
        Optional zero-based branch restriction; None updates every panel.

    Outputs
    -------
    None
        Retains scalar sources for hover/export, aligns image edges to solver cell
        centers, and replaces complete raster buffers without changing physical arrays.

    Notes
    -----
    Use one persistent RGBA glyph in both weighted and unweighted states.
    '''
    # Publish complete pixels through persistent model RGBA renderers in weighted and
    # unweighted states
    rasters = getattr(model, '_coherence_overlays', None)
    if rasters is None:
        rasters = []
        model._coherence_overlays = rasters
    # Image coordinates describe cell EDGES, whereas the solver axes are centers.
    kh, nu = result.kh_mm_inv, result.nu_mhz
    dk, df = np.median(np.diff(kh)), np.median(np.diff(nu))
    for renderer in model.hover_renderers:
        renderer.glyph.width, renderer.glyph.height = dk, df
    x, xe = axis_limits(kh)
    y, ye = axis_limits(nu)
    geometry = dict(x=[x], y=[y], dw=[xe-x], dh=[ye-y])
    for index, (plot, source, scalar) in enumerate(zip(
            model.plots, model.image_sources, model.image_renderers)):
        if branch is not None and index != branch:
            continue
        scalar_data = dict(source.data, **geometry)
        # Keep hover/export scalar data registered to exactly the same cells.
        source.data = scalar_data
        packed = rgba_image(scalar_data['image'][0], model.mapper, opacity)
        raster_data = dict(scalar_data, image=[packed])
        if index == len(rasters):
            # The renderers event can serialize new references immediately,
            # while a frozen model graph has not yet attached their sources.
            # Populate pixels before attachment; later updates then emit the
            # normal data-source events on the persistent renderer.
            rgba_source = ColumnDataSource(raster_data,
                name=f'{model.definition.key}:coherence_opacity:{index}')
            raster = plot.image_rgba(image='image', x='x', y='y', dw='dw', dh='dh',
                source=rgba_source, level='image',
                name=f'{model.definition.key}:coherence_overlay:{index}')
            rasters.append(raster)
        else:
            raster = rasters[index]
            raster.data_source.data = raster_data
        scalar.visible = False
        raster.visible = True


def apply_model_visibility(model, result, controls, gaussian=None):
    '''
    Purpose
    -------
    Gate native model colors by finite threshold-qualified measured coherence.

    Inputs
    ------
    model: Bokeh model or explorer
        Model/layout or dispersion explorer operated on by this helper.
    result: DiagramResult
        Model result whose image grid receives aligned coherence.
    controls: CoherenceControls
        Current measured estimate, threshold, and application toggle.
    gaussian: np.ndarray or None
        Optional continuous Gaussian transfer multiplied into exported spectral weights.

    Outputs
    -------
    None
        Updates binary display alpha and hover/export spectral weights independently;
        physical solver fields remain unchanged.

    Notes
    -----
    Gate native colors by measured coherence without fading their RGB values.

    Display visibility is binary and includes the threshold. The full precision
    continuous spectral weight remains available for hover/export independently.
    Neither operation changes the native scalar sources or physical solutions.
    '''
    # Gate native model colors by finite threshold-qualified measured coherence
    coherence = controls.aligned(result)
    shape = result.phase_deg.shape[:2]
    coherence = np.full(shape, np.nan) if coherence is None else coherence
    relative = (coherence_weights(coherence, controls.threshold.value)
                if controls.apply.active else np.ones(shape))
    visibility = ((np.isfinite(coherence) & (coherence >= controls.threshold.value)).astype(float)
                  if controls.apply.active else np.ones(shape))
    baseline = np.ones(shape) if gaussian is None else gaussian
    model.coherence_weight = relative
    model.coherence_visibility = visibility
    model.spectral_weight = baseline*relative
    render_model_pixels(model, result, visibility)
    model.hover_source.data = dict(model.hover_source.data,
        coherence=coherence.ravel(), coherence_weight=relative.ravel(),
        coherence_visibility=visibility.ravel(),
        spectral_weight=model.spectral_weight.ravel())


def clear_model_visibility(model):
    '''
    Purpose
    -------
    Hide retained coherence rasters and restore native scalar image visibility.

    Inputs
    ------
    model: Bokeh model or explorer
        Model/layout or dispersion explorer operated on by this helper.

    Outputs
    -------
    None
        Used when a model is disabled, invalidated, or cleared.

    Notes
    -----
    Remove weighted pixels when a model is disabled, invalidated or cleared.
    '''
    # Hide retained coherence rasters and restore native scalar image visibility
    for renderer in getattr(model, '_coherence_overlays', []):
        renderer.visible = False
    for renderer in model.image_renderers:
        renderer.visible = True


def add_coherence_hover(model):
    '''
    Purpose
    -------
    Extend native model hover tools with measured-coherence and spectral-weight fields.

    Inputs
    ------
    model: Bokeh model or explorer
        Model/layout or dispersion explorer operated on by this helper.

    Outputs
    -------
    None
        Appends tooltips referencing coherence, binary visibility, and combined
        continuous weight.
    '''

    # Extend native model hover tools with measured-coherence and spectral-weight fields
    from bokeh.models import HoverTool
    for plot in model.plots:
        for hover in plot.select(type=HoverTool):
            hover.tooltips = list(hover.tooltips) + [
                ('Measured C', '@coherence{0.0000}'),
                ('Coherence visibility', '@coherence_visibility{0}'),
                ('Combined spectral weight', '@spectral_weight{0.0000}')]

