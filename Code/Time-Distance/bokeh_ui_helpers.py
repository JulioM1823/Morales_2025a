'''
Purpose
-------
Share Bokeh presentation controls, physical-frequency adapters, and generation-safe
numerical model update lifecycles.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for bokeh_ui_helpers.py.

Notes
-----
Shared Bokeh controls, presentation, and model-update lifecycle helpers.
'''
# Import the libraries and shared helpers used by this module
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
from contextlib import contextmanager
from functools import wraps
from html import escape

from bokeh.events import DocumentReady
from bokeh.layouts import column, row
from bokeh.models import (BasicTicker, Button, ColorBar, Column, CustomJS, Div, GridBox,
                          LayoutDOM, Legend, LinearColorMapper, MultiChoice, Plot, Row,
                          Slider, TextInput, Toggle, Widget)
import cmasher as cmr
from matplotlib.colors import to_hex
import numpy as np


MODEL_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='dispersion-model')


class LatestModelRunner:
    '''
    Purpose
    -------
    Keep one running numerical solve and one replaceable latest request per workspace.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    pool: concurrent.futures.Executor
        Shared worker executor used for model calculations.

    Outputs
    -------
    runner: LatestModelRunner
        Background calculation coordinator whose acceptance callbacks run on the
        document thread and verify current state.

    Notes
    -----
    One running calculation and one replaceable latest request per workspace.

    A running numerical solve is allowed to finish. Intermediate requests never
    enter the executor, and the owner verifies generation/state before display.
    '''
    def __init__(self, doc, pool=MODEL_POOL):
        '''
        Purpose
        -------
        Initialize the document-bound calculation coordinator and session-close cleanup.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        pool: concurrent.futures.Executor
            Worker executor used to run numerical calculations.

        Outputs
        -------
        None
            Stores executor/document state and registers cancellation on session
            destruction.
        '''

        # Initialize the document-bound calculation coordinator and session-close
        # cleanup
        self.doc, self.pool = doc, pool
        self.future = self.pending = None
        self.closed = False
        doc.on_session_destroyed(lambda context: self.close())

    def request(self, calculate, accept, current):
        '''
        Purpose
        -------
        Replace the pending request and start it immediately when no solve is running.

        Inputs
        ------
        calculate: callable
            Zero-argument calculation performed outside the document callback when
            asynchronous execution is active.
        accept: callable
            Document-thread callback receiving the current calculation result and, where
            supported, its exception.
        current: callable
            Zero-argument predicate determining whether the request still matches the
            owner's generation/state.

        Outputs
        -------
        None
            Retains only the latest pending work; closed coordinators ignore requests.
        '''

        # Replace the pending request and start it immediately when no solve is running
        if self.closed:
            return
        self.pending = (calculate, accept, current)
        if self.future is None:
            self._start()

    def _start(self):
        '''
        Purpose
        -------
        Submit the latest current request and arrange document-thread result
        publication.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Handles executor submission errors like calculation failures, then starts
            any newest pending request after publication.
        '''

        # Submit the latest current request and arrange document-thread result
        # publication
        request, self.pending = self.pending, None
        calculate, accept, current = request
        if self.closed or not current():
            return
        try:
            future = self.future = self.pool.submit(calculate)
        except Exception as exc:
            # Submission failures must settle the visible busy state just like
            # numerical failures. No Future exists to publish an error later.
            self.future = None
            if not self.closed and current():
                accept(None, exc)
            return

        def completed(done):
            '''
            Purpose
            -------
            Collect a worker's result or exception and enqueue document-thread
            publication.

            Inputs
            ------
            done: concurrent.futures.Future
                Completed background future supplying a result or exception.

            Outputs
            -------
            None
                Returns without publication when the coordinator has closed.
            '''

            # Collect a worker's result or exception and enqueue document-thread
            # publication
            if self.closed:
                return
            try:
                result, error = done.result(), None
            except Exception as exc:
                result, error = None, exc

            def publish():
                '''
                Purpose
                -------
                Publish a current completed calculation and continue with the latest
                pending request.

                Inputs
                ------
                None

                Outputs
                -------
                None
                    Clears the running future, applies the generation predicate, and
                    starts pending work in a finally block.
                '''

                # Publish a current completed calculation and continue with the latest
                # pending request
                self.future = None
                try:
                    if not self.closed and current():
                        accept(result, error)
                finally:
                    if not self.closed and self.pending is not None:
                        self._start()
            self.doc.add_next_tick_callback(publish)

        future.add_done_callback(completed)

    def close(self):
        '''
        Purpose
        -------
        Mark the coordinator closed and cancel pending/cancellable work.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Drops queued requests; an already running numerical solve may still finish
            without acceptance.
        '''

        # Mark the coordinator closed and cancel pending/cancellable work
        self.closed = True
        self.pending = None
        if self.future is not None:
            self.future.cancel()


FACTOR = 1000 / (2 * math.pi)


def to_mhz(key, value):
    '''
    Purpose
    -------
    Convert a native angular frequency or signed squared buoyancy value into its display
    mHz value.

    Inputs
    ------
    key: str
        N2 selects the signed-square-root buoyancy convention; other keys use angular
        frequency.
    value: float
        Signed N2 in s^-2 or an angular frequency in rad/s.

    Outputs
    -------
    value: float
        Cyclic mHz frequency, using signed sqrt(abs(N2)) before conversion for N2.
    '''

    # Convert a native angular frequency or signed squared buoyancy value into its
    # display mHz value
    return (math.copysign(math.sqrt(abs(value)), value) if key == 'N2' else value) * FACTOR


def from_mhz(key, value):
    '''
    Purpose
    -------
    Convert displayed cyclic mHz back to a native angular frequency or signed N2 value.

    Inputs
    ------
    key: str
        N2 selects the signed-square conversion.
    value: float
        Displayed cyclic frequency in mHz, signed for buoyancy.

    Outputs
    -------
    value: float
        Angular frequency in rad/s, or signed squared buoyancy frequency in s^-2 for N2.
    '''

    # Convert displayed cyclic mHz back to a native angular frequency or signed N2 value
    value /= FACTOR
    return math.copysign(value * value, value) if key == 'N2' else value


def frequency_control(native, key, exact_slider):
    '''
    Purpose
    -------
    Link an exact-value mHz control to an existing native physical-frequency slider.

    Inputs
    ------
    native: bokeh.models.Slider
        Existing N2 (s^-2) or cutoff angular-frequency (rad/s) slider.
    key: str
        Native physical parameter identifier.
    exact_slider: type
        ExactSlider-compatible wrapper class used to construct the visible control.

    Outputs
    -------
    control: ExactSlider
        Display wrapper with bidirectional guarded synchronization; native callbacks
        remain the physical source of state.

    Notes
    -----
    Link a visible mHz slider to the existing physical value and callbacks.
    '''
    # Link an exact-value mHz control to an existing native physical-frequency slider
    squared = key == 'N2'
    title = ('Brunt–Väisälä frequency (signed √|N²|) [mHz]' if squared
             else 'Acoustic cutoff frequency [mHz]')
    display = Slider(title=title, start=to_mhz(key, native.start),
                     end=to_mhz(key, native.end), value=to_mhz(key, native.value),
                     step=0.01, format='0.000', width=native.width,
                     name=native.name + ':mhz', disabled=native.disabled)
    def validate(value):
        '''
        Purpose
        -------
        Validate a displayed cyclic-frequency edit before updating the native control.

        Inputs
        ------
        value: float
            Displayed frequency in mHz, signed when representing N2.

        Outputs
        -------
        None
            Rejects nonfinite input and negative nonsquared cutoff frequency.
        '''

        # Validate a displayed cyclic-frequency edit before updating the native control
        if not math.isfinite(value):
            raise ValueError('Enter a finite number.')
        if not squared and value < 0:
            raise ValueError('Value must be nonnegative.')

    # Pair the visible mHz slider with exact-value validation and a shared recursion
    # guard
    control = exact_slider(display, key, validator=validate)
    syncing = False

    def refresh(attr, old, new):
        '''
        Purpose
        -------
        Refresh displayed frequency, limits, and editability after a native control
        change.

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
            Uses the shared recursion guard while converting native physical units to
            mHz.
        '''

        # Refresh displayed frequency, limits, and editability after a native control
        # change
        nonlocal syncing
        if syncing:
            return
        syncing = True
        try:
            display.start = to_mhz(key, native.start)
            display.end = to_mhz(key, native.end)
            display.value = to_mhz(key, native.value)
            display.disabled = native.disabled
        finally:
            syncing = False

    def commit(attr, old, new):
        '''
        Purpose
        -------
        Convert an accepted mHz edit and apply it to the native physical slider.

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
            Expands suggested native bounds as needed while holding the recursion guard.
        '''

        # Convert an accepted mHz edit and apply it to the native physical slider
        nonlocal syncing
        if syncing:
            return
        syncing = True
        try:
            value = from_mhz(key, new)
            native.start = min(native.start, value)
            native.end = max(native.end, value)
            native.value = value
        finally:
            syncing = False

    # Synchronize native limits, accepted value, and editability in both directions
    for attribute in ('start', 'end', 'value', 'disabled'):
        native.on_change(attribute, refresh)
    display.on_change('value', commit)
    return control


@contextmanager
def model_graph_update(doc, *, constructing=False):
    '''
    Purpose
    -------
    Batch initial/offline model construction while preserving live server reference
    updates.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    constructing: bool
        Force initial-construction batching even for a server document.

    Outputs
    -------
    context: context manager
        Yields during model updates. Offline construction freezes the graph and defers
        body exceptions until the freeze context exits; live updates resolve
        immediately.

    Notes
    -----
    Batch offline graph construction; publish live changes with current refs.

    A server serializes each change immediately. Freezing its reference graph
    lets later events resend already attached models, whose updated attributes
    the browser then discards as duplicate definitions. Model/solution switches
    must therefore attach/detach their sources before the next event is sent.
    Bokeh 3.2 freeze() does not unwind its counter when the body raises, so defer
    offline error propagation until its context exits normally. Python widget
    callbacks stay synchronous in both cases.
    '''
    # During initial application construction no client has received this
    # document yet. Resolve its complete graph once, after composition, even
    # for server sessions. Incremental live updates still resolve immediately.
    if doc.session_context is not None and not constructing:
        yield
        return
    error = None
    with doc.models.freeze():
        try:
            yield
        except BaseException as exc:
            error = exc
    if error is not None:
        raise error


def batch_model_graph(method):
    '''
    Purpose
    -------
    Wrap an explorer method in the document model-graph update context.

    Inputs
    ------
    method: callable
        Explorer method whose self object exposes doc.

    Outputs
    -------
    wrapper: callable
        Signature-preserving method wrapper returning the original method's result.
    '''

    # Wrap an explorer method in the document model-graph update context
    @wraps(method)
    def batched(self, *args, **kwargs):
        '''
        Purpose
        -------
        Execute the wrapped explorer method inside its model-graph update context.

        Inputs
        ------
        args: tuple
            Positional arguments forwarded unchanged to the wrapped method.
        kwargs: dict
            Keyword arguments forwarded unchanged to the wrapped method.

        Outputs
        -------
        result: object
            Original method return value; exceptions propagate after context cleanup.
        '''

        # Execute the wrapped explorer method inside its model-graph update context
        with model_graph_update(self.doc):
            return method(self, *args, **kwargs)
    return batched


PHASE_PALETTE = [to_hex(cmr.fusion(v)) for v in np.linspace(0., 1., cmr.fusion.N)]


_COMPACT_UI_STYLES = """
:host {font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 12px;}
h1, h2, h3, h4 {line-height: 1.3; margin: 0 0 4px; color: #253449;}
h2 {font-size: 16px;} h3 {font-size: 13px;}
p {margin: 4px 0; line-height: 1.45;}
.bk-btn, .bk-input, label, .choices {font-family: inherit; font-size: 12px;}
.bk-btn {min-height: 30px; padding: 5px 9px; border-radius: 5px;
    box-shadow: none; white-space: normal; line-height: 1.3;}
.bk-btn-default {background: #f8fafc; border-color: #cbd5e1; color: #334155;}
.bk-btn-default:hover {background: #edf2f7; border-color: #94a3b8;}
.bk-btn-default.bk-active {background: #e5edf7; border-color: #94a9c2; color: #243e5d;}
.bk-btn.bk-btn-default.bk-active, .bk-btn.bk-btn-default:active {box-shadow: none;}
.bk-input {border-radius: 5px; border-color: #cbd5e1; box-shadow: none;}
.bk-input:focus, .bk-btn:focus-visible {outline: 2px solid #93b4dc; outline-offset: 1px;}
.choices__inner {border-radius: 5px; border-color: #cbd5e1; background: #fff;}
"""


def compact_ui(*roots):
    '''
    Purpose
    -------
    Apply compact control typography and spacing while leaving scientific plot models
    untouched.

    Inputs
    ------
    roots: tuple of Bokeh layout models
        Layout roots passed as positional arguments for presentation traversal.

    Outputs
    -------
    None
        Traverses layout children once, preserves existing stylesheets, and updates only
        layout/widget presentation.

    Notes
    -----
    Apply control spacing and typography without visiting scientific models.

    Only layout children are traversed, including GridBox's positioned tuples.
    Plot models and their sources, renderers, axes, and toolbars are untouched.
    Repeated calls preserve existing stylesheets and do not append duplicates.
    '''
    # Apply compact control typography and spacing while leaving scientific plot models
    # untouched
    seen = set()

    # Traverse only layout children, keeping plot/scientific model graphs outside
    # presentation updates
    def children(model):
        '''
        Purpose
        -------
        Extract layout children while unwrapping GridBox positioned child tuples.

        Inputs
        ------
        model: Bokeh model or explorer
            Model/layout or dispersion explorer operated on by this helper.

        Outputs
        -------
        children: list
            Direct child models, or an empty list for a model without children.
        '''

        # Extract layout children while unwrapping GridBox positioned child tuples
        return [item[0] if isinstance(item, (tuple, list)) else item
                for item in getattr(model, 'children', ())]

    def has_plot(model):
        '''
        Purpose
        -------
        Determine whether a layout subtree contains a plot model.

        Inputs
        ------
        model: Bokeh model or explorer
            Model/layout or dispersion explorer operated on by this helper.

        Outputs
        -------
        contains_plot: bool
            True for a Plot or any layout descendant containing a Plot.
        '''

        # Determine whether a layout subtree contains a plot model
        return isinstance(model, Plot) or any(has_plot(child) for child in children(model)
                                             if isinstance(child, LayoutDOM))

    def visit(model):
        '''
        Purpose
        -------
        Apply compact presentation once to an eligible nonplot layout/widget subtree.

        Inputs
        ------
        model: Bokeh model or explorer
            Model/layout or dispersion explorer operated on by this helper.

        Outputs
        -------
        None
            Updates margins/spacing/styles and recurses only through layout children.
        '''

        # Apply compact presentation once to an eligible nonplot layout/widget subtree
        if not isinstance(model, LayoutDOM) or isinstance(model, Plot) or model.id in seen:
            return
        seen.add(model.id)
        if not isinstance(model, GridBox) or not has_plot(model):
            model.margin = 0
            if isinstance(model, GridBox):
                model.cols = 'minmax(0, 1fr)'
        if isinstance(model, Row):
            model.spacing = 8
        elif isinstance(model, Column):
            model.spacing = min(max(model.spacing, 4), 8)
        if isinstance(model, (Widget, Div)):
            if _COMPACT_UI_STYLES not in model.stylesheets:
                model.stylesheets = [*model.stylesheets, _COMPACT_UI_STYLES]
        if isinstance(model, (Button, Toggle)):
            model.min_height = max(model.min_height or 0, 30)
        for child in children(model):
            visit(child)

    for root in roots:
        visit(root)


def visibility_toggle(targets, title, *, name, active=True, plot_grids=(), comparison=None):
    '''
    Purpose
    -------
    Construct a local visibility control without recomputing scientific arrays.

    Inputs
    ------
    targets: iterable of Bokeh models
        Presentation models whose visible state follows the toggle.
    title: str
        Human-readable section name used in Show/Hide labels.
    name: str
        Stable Bokeh model name.
    active: bool
        Initial visible state.
    plot_grids: iterable
        Optional mounted comparison grids whose current secondary plot follows
        visibility.
    comparison: Bokeh toggle or None
        Comparison-state toggle controlling whether secondary grid visibility is
        overridden.

    Outputs
    -------
    toggle: bokeh.models.Toggle
        Initially applied presentation switch with matching Python and browser-local
        visibility handlers.

    Notes
    -----
    A local presentation switch; no scientific callback or server round trip.
    '''
    # Construct a local visibility control without recomputing scientific arrays
    targets = list(targets)
    toggle = Toggle(label=('Hide ' if active else 'Show ') + title, active=active,
                    min_width=0, sizing_mode='stretch_width', name=name, syncable=False)
    # Install the existing browser-local visibility script without changing scientific
    # callbacks
    callback = CustomJS(args=dict(targets=targets, title=title, button=toggle,
                                 grids=list(plot_grids), comparison=comparison), code="""
        for (const target of targets)
            target.setv({visible: button.active}, {sync: false});
        // Keep only the currently mounted figures in the graph. Model/branch
        // switches inherit presentation locally without serializing every
        // inactive figure and its cached scientific arrays into the document.
        if (comparison == null || !comparison.active)
            for (const grid of grids)
                if (grid.children.length > 1)
                    grid.children[1][0].setv({visible:button.active}, {sync:false});
        button.setv({label: (button.active ? 'Hide ' : 'Show ') + title}, {sync: false});
    """)
    toggle.js_on_change('active', callback)
    for grid in plot_grids:
        grid.js_on_change('children', callback)
    def changed(attr, old, new):
        '''
        Purpose
        -------
        Mirror the local presentation switch in Python model state.

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
            Updates target/eligible comparison visibility and the Show/Hide button
            label.
        '''

        # Mirror the local presentation switch in Python model state
        for target in targets:
            target.visible = new
        if comparison is None or not comparison.active:
            for grid in plot_grids:
                if len(grid.children) > 1:
                    grid.children[1][0].visible = new
        toggle.label = ('Hide ' if new else 'Show ') + title
    toggle.on_change('active', changed)
    changed(None, None, active)
    return toggle


class CollapsibleSection:
    '''
    Purpose
    -------
    Compose a named section with separate optional controls and plot visibility
    switches.

    Inputs
    ------
    title: str
        Escaped displayed section heading.
    name: str
        Stable prefix for section and toggle model names.
    related: iterable
        Additional models hidden with the control/body content.
    plots: iterable or None
        Optional plots wrapped in a separately toggled plot body.
    plot_targets: iterable
        Additional plot models controlled by the plot switch.
    plot_grids: iterable
        Mounted comparison grids connected to plot visibility.
    comparison: Bokeh toggle or None
        Comparison-state switch used by the plot visibility helper.
    children: tuple of Bokeh layout models
        Control/body children supplied as positional arguments.

    Outputs
    -------
    section: CollapsibleSection
        Retained native layout models with visibility toggles; data sources and
        scientific state are not detached or recalculated.

    Notes
    -----
    Hide native layout content without detaching models or touching data.

    Related controls can retain their existing positions outside the body. All
    targets use Bokeh visibility, so hidden content contributes no layout space.
    '''
    def __init__(self, title, *children, name, related=(), plots=None, plot_targets=(),
                 plot_grids=(), comparison=None):
        '''
        Purpose
        -------
        Build retained section layouts and independent visibility controls for body and
        optional plots.

        Inputs
        ------
        title: str
            Displayed section heading.
        name: str
            Stable Bokeh name prefix.
        related: iterable
            Additional controls/body targets following the body switch.
        plots: iterable or None
            Optional separately wrapped plot content.
        plot_targets: iterable
            Additional plot-visible targets.
        plot_grids: iterable
            Comparison grids whose mounted plots participate in visibility.
        comparison: Bokeh toggle or None
            Comparison-state flag used for secondary plot visibility.
        children: tuple of Bokeh layout models
            Section body children supplied as positional arguments.

        Outputs
        -------
        None
            Stores the section layout and visibility targets without changing their
            scientific arrays.
        '''

        # Build retained section layouts and independent visibility controls for body
        # and optional plots
        self.title = title
        self.body = column(*children, margin=0, min_width=0,
                           sizing_mode='stretch_width', name=name + ':body')
        self._targets = (self.body, *related)
        split = plots is not None or bool(plot_targets) or bool(plot_grids)
        self.toggle = visibility_toggle(self._targets, 'Controls' if split else title,
                                       name=name + ':toggle')
        buttons = [self.toggle]
        content = [self.body]
        # Keep plot visibility independent of control visibility when separate plot
        # targets exist
        if split:
            self.plot_body = (None if plots is None else column(*plots, margin=0, min_width=0,
                sizing_mode='stretch_width', name=name + ':plots'))
            targets = tuple(plot_targets)
            if self.plot_body is not None:
                targets = (self.plot_body, *targets)
            self.plot_toggle = visibility_toggle(targets, 'Plot',
                name=name + ':plot_toggle', plot_grids=plot_grids, comparison=comparison)
            buttons.insert(0, self.plot_toggle)
            if plots is not None:
                content.append(self.plot_body)
        self.layout = column(Div(text=f'<h2 style="margin:0">{escape(title)}</h2>',
                                 sizing_mode='stretch_width', min_width=0, margin=0),
                             row(*buttons, sizing_mode='stretch_width', spacing=8, margin=0),
                             *content, margin=0, min_width=0, spacing=8,
                             sizing_mode='stretch_width', name=name)

def phase_color_mapper():
    '''
    Purpose
    -------
    Construct the native phase palette with fixed symmetric degree limits.

    Inputs
    ------
    None

    Outputs
    -------
    mapper: bokeh.models.LinearColorMapper
        CMasher fusion mapper spanning -80 to 80 degrees with gray missing values.

    Notes
    -----
    The existing k–ω phase palette, fixed degree limits and missing color.
    '''
    # Construct the native phase palette with fixed symmetric degree limits
    return LinearColorMapper(palette=PHASE_PALETTE, low=-80., high=80., nan_color=to_hex('0.65'))


def phase_color_bar(mapper):
    '''
    Purpose
    -------
    Construct the shared native phase color bar.

    Inputs
    ------
    mapper: bokeh.models.LinearColorMapper
        Native palette, range limits, missing color, and optional out-of-range colors.

    Outputs
    -------
    color_bar: bokeh.models.ColorBar
        Degree-labeled color bar using the supplied mapper and shared typography.
    '''

    # Construct the shared native phase color bar
    return ColorBar(color_mapper=mapper, ticker=BasicTicker(), title='Δφ [deg]',
        title_text_font='Times New Roman', title_text_font_size='13pt',
        major_label_text_font='Times New Roman', major_label_text_font_size='11pt', width=16)


def style_phase_plot(plot, title_size='12pt'):
    '''
    Purpose
    -------
    Apply shared native phase typography and axis/tick styling.

    Inputs
    ------
    plot: bokeh.models.Plot
        Native plot whose presentation is updated in place.
    title_size: str
        CSS font-size value for the plot title.

    Outputs
    -------
    None
        Mutates plot grid/background/outline/font/tick presentation without changing
        physical geometry.

    Notes
    -----
    Shared native k–ω typography and axes, without changing plot geometry.
    '''
    # Apply shared native phase typography and axis/tick styling
    plot.grid.visible = False
    plot.background_fill_color = plot.border_fill_color = 'white'
    plot.outline_line_color = 'black'
    plot.title.text_font = 'Times New Roman'
    plot.title.text_font_size = title_size
    plot.title.text_font_style = 'normal'
    for axis in (plot.xaxis[0], plot.yaxis[0]):
        axis.axis_label_text_font = axis.major_label_text_font = 'Times New Roman'
        axis.axis_label_text_font_style = 'normal'
        axis.axis_label_text_font_size, axis.major_label_text_font_size = '16pt', '12pt'
        axis.major_tick_in, axis.major_tick_out = 8, 0
        axis.minor_tick_in, axis.minor_tick_out = 4, 0


class FileSelector:
    '''
    Purpose
    -------
    Provide a searchable single-choice dataset dropdown using canonical dataset
    identifiers.

    Inputs
    ------
    records: iterable
        Dataset records exposing id, label, and ordered files.
    title: str
        Displayed dataset-selector title.
    prefix: str
        Stable Bokeh model-name prefix.
    width: int
        Initial control width in pixels.

    Outputs
    -------
    selector: FileSelector
        Search field, path-label toggle, retained selection, and closed-dropdown
        presentation.

    Notes
    -----
    Searchable closed dropdown; option values remain the canonical dataset IDs.
    '''
    def __init__(self, records, *, title, prefix, width=520):
        '''
        Purpose
        -------
        Construct searchable dataset controls and browser-local single-choice dropdown
        behavior.

        Inputs
        ------
        records: iterable
            Dataset records with canonical id, label, and files fields.
        title: str
            Selector title.
        prefix: str
            Stable widget-name prefix.
        width: int
            Initial control width in pixels.

        Outputs
        -------
        None
            Stores records and widgets, registers search/path callbacks, and populates
            options.
        '''

        # Construct searchable dataset controls and browser-local single-choice dropdown
        # behavior
        self.records = list(records)
        self.search = TextInput(title='Search filenames or paths', width=width, min_width=0,
                                sizing_mode='stretch_width',
                                name=prefix + ':search')
        self.selector = MultiChoice(title=title, options=[], value=[],
            placeholder='Click to select a file…', delete_button=False,
            option_limit=100, search_option_limit=100, width=width-120,
            min_width=0, sizing_mode='stretch_width',
            name=prefix + ':selector', stylesheets=[
                '.choices__list--multiple .choices__item {max-width:100%; white-space:normal; overflow-wrap:anywhere;}'
            ])
        self.full_path = Toggle(label='Show full path', active=False, width=112, min_width=0,
                                align='end', name=prefix + ':full_path')
        self.layout = column(self.search, row(self.selector, self.full_path,
                             sizing_mode='stretch_width', min_width=0, spacing=8),
                             sizing_mode='stretch_width', min_width=0, spacing=8)
        self.full_path.on_change('active', self._refresh)
        self.search.on_change('value_input', self._refresh)
        self.selector.js_on_change('value', CustomJS(code="""
            // Bokeh's MultiChoice normally retains focus and its menu after a choice.
            // Normalize to one ID immediately, then close the actual Choices menu.
            if (cb_obj.value.length > 1) cb_obj.value = [cb_obj.value.at(-1)];
            const close = (view) => {
                if (view.model === cb_obj && view.choice_el) {
                    view.choice_el.hideDropdown();
                    view.choice_el.input.element.blur();
                }
                for (const child of view.child_views || []) close(child);
            };
            for (const view of Object.values(Bokeh.index)) close(view);
        """))
        self.refresh()

    def _refresh(self, attr, old, new):
        '''
        Purpose
        -------
        Route a search/path-presentation property change to option refresh.

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
            Rebuilds visible labels without changing the scientific dataset identifier.
        '''

        # Route a search/path-presentation property change to option refresh
        self.refresh()

    def refresh(self):
        '''
        Purpose
        -------
        Filter dataset labels by search text while retaining the current selection.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Updates selector options using basenames or full paths; the active canonical
            ID is never removed solely by search filtering.
        '''

        # Filter dataset labels by search text while retaining the current selection
        needle = self.search.value_input.strip().casefold()
        options = []
        for item in self.records:
            paths = tuple(Path(path).expanduser().resolve() for path in item.files)
            haystack = ' '.join([item.id, item.label, *map(str, paths)]).casefold()
            # Retain the active option when searching: filtering display must never
            # silently clear or change the underlying scientific selection.
            if needle and needle not in haystack and item.id not in self.selector.value:
                continue
            label = ' + '.join(str(path) if self.full_path.active else path.name for path in paths)
            options.append((item.id, label))
        self.selector.options = options


def remove_plot_legends(plots):
    '''
    Purpose
    -------
    Detach legend models from every plot-layout side, including reserved margins.

    Inputs
    ------
    plots: iterable of bokeh.models.Plot
        Native plots updated without recalculating their physical fields.

    Outputs
    -------
    None
        Filters Legend entries from above/below/left/right/center layout collections.

    Notes
    -----
    Detach legends from every layout side, including their reserved margins.
    '''
    # Detach legend models from every plot-layout side, including reserved margins
    for plot in plots:
        for side in ('above', 'below', 'left', 'right', 'center'):
            setattr(plot, side, [item for item in getattr(plot, side) if not isinstance(item, Legend)])


class DispersionControls:
    '''
    Purpose
    -------
    Reuse native branch-associated curve sources across all workspace views.

    Inputs
    ------
    owner: object
        Owning workspace exposing the document, selected dataset/model, and shared
        controls used here.

    Outputs
    -------
    controls: DispersionControls
        Visibility controls and shared overlays; this class does not solve dispersion
        curves.

    Notes
    -----
    Reuse native, branch-associated sources on every view; never solve curves here.
    '''
    def __init__(self, owner):
        '''
        Purpose
        -------
        Build curve-visibility controls and replace plot-specific line overlays with
        shared-source presentation.

        Inputs
        ------
        owner: object
            Owning workspace exposing the document, selected dataset/model, and shared
            controls used here.

        Outputs
        -------
        None
            Stores curve controls, wires responsive layout, hides superseded native
            selectors/legends, and preserves model source arrays.
        '''

        # Build curve-visibility controls and replace plot-specific line overlays with
        # shared-source presentation
        self.owner = owner
        self.toggles = {}
        self.overlays = {}
        self._bound_selection = None
        self.layout = GridBox(children=[], spacing=(6, 8), min_width=0,
                              sizing_mode='stretch_width', name='integrated:curves')
        owner.doc.js_on_event(DocumentReady, CustomJS(args=dict(grid=self.layout,
            middle=owner.middle_section), code="""
            const resize = () => {
                const columns = middle.width >= 400 ? 2 : 1;
                const children = grid.children.map((item, i) =>
                    [item[0], Math.floor(i / columns), i % columns]);
                if (grid.children.some((item, i) =>
                    item[1] !== children[i][1] || item[2] !== children[i][2]))
                    grid.setv({children}, {sync: false});
            };
            resize(); middle.properties.width.change.connect(resize);
            grid.properties.children.change.connect(resize);
        """))
        self.fmode = Toggle(label='f-mode', active=True, sizing_mode='stretch_width',
                            name='integrated:curve:fmode')
        self.fmode.on_change('active', self._changed)
        # Existing Gaussian reference curves use the exact primary reference source.
        self.references = {}
        for key, label in [('lamb', 'Gaussian Lamb boundary'), ('cap', 'Gaussian frequency cap')]:
            toggle = Toggle(label=label, active=True, sizing_mode='stretch_width',
                            name='integrated:curve:' + key)
            toggle.on_change('active', self._changed)
            self.references[key] = toggle
        pair_plots = [p for pair in (owner.primary, owner.secondary)
                      for p in (pair.observed_plot, pair.result_plot)]
        # Replace the old plot-specific fixed lines with shared sources below.
        for plot in [*pair_plots, owner.primary.filter.plot]:
            plot.renderers = [r for r in plot.renderers
                              if type(getattr(r, 'glyph', None)).__name__ != 'Line']
        for model in owner.model_workspace.models:
            model.show_fmode.visible = False
            remove_plot_legends([*model.plots, *model.filtered.plots])

    def _changed(self, attr, old, new):
        '''
        Purpose
        -------
        Apply curve-visibility changes to retained shared overlays.

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
            Does not invoke a model or boundary solve.
        '''

        # Apply curve-visibility changes to retained shared overlays
        self.apply_visibility()

    def bind(self):
        '''
        Purpose
        -------
        Bind the selected model/branch curves and shared Gaussian references across
        workspace plots.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Reuses retained renderers and switches their data sources; new curve
            toggles/renderers are created only when required.
        '''

        # Bind the selected model/branch curves and shared Gaussian references across
        # workspace plots
        selection = (self.owner.model_select.value, self.owner.branch_select.value)
        if selection == self._bound_selection:
            self.apply_visibility()
            return
        model = self.owner.model
        branch = int(self.owner.branch_select.value)
        count = len(model.boundary_sources_by_branch[branch])
        controls = []
        for index in range(count):
            key = (model.definition.key, index)
            if key not in self.toggles:
                if model.definition.key == 'slow_mode':
                    label = 'Slow magnetoacoustic boundary'
                elif model.definition.key == 'fast_mode':
                    label = 'Fast magnetoacoustic boundary'
                else:
                    label = f'Dispersion boundary {index + 1}'
                toggle = Toggle(label=label, active=True, sizing_mode='stretch_width',
                                name=f'integrated:curve:{model.definition.key}:{index}')
                toggle.on_change('active', self._changed)
                self.toggles[key] = toggle
            controls.append(self.toggles[key])
        self.layout.children = [(control, i // 2, i % 2)
            for i, control in enumerate([self.fmode, *controls, *self.references.values()])]
        compact_ui(self.layout)
        plots = [self.owner.primary.filter.plot,
                 self.owner.primary.observed_plot, self.owner.primary.result_plot,
                 self.owner.secondary.observed_plot, self.owner.secondary.result_plot]
        for plot in plots:
            renderers = self.overlays.get(plot)
            if renderers is None:
                renderers = [plot.line('kh', 'nu', source=model.fmode_source,
                                       line_color='gray', line_width=1.5)]
                renderers.extend(plot.line('kh', 'nu', source=model.boundary_sources_by_branch[branch][0],
                    line_color='black', line_width=1.5) for _ in range(count))
                self.overlays[plot] = renderers
            renderers[0].data_source = model.fmode_source
            for index, source in enumerate(model.boundary_sources_by_branch[branch]):
                if index+1 >= len(renderers):
                    renderers.append(plot.line('kh','nu',source=source,line_color='black',line_width=1.5))
                renderers[index+1].data_source = source
            for renderer in renderers[count+1:]:
                renderer.visible = False
        self._bound_selection = selection
        # Native filtered curves share the unfiltered numerical sources too.
        for m in self.owner.model_workspace.models:
            for renderer in m.filtered.fmode_renderers:
                renderer.data_source = m.fmode_source
            for native, filtered in zip(m.boundary_sources_by_branch,
                                        m.filtered.boundary_renderers_by_branch):
                for source, renderer in zip(native, filtered):
                    renderer.data_source = source
        # Keep the Gaussian's fixed physical references on all model views as well.
        all_plots = plots + [p for m in self.owner.model_workspace.models
                             for p in [*m.plots, *m.filtered.plots]]
        for plot in all_plots:
            if not hasattr(plot, '_gaussian_reference_renderers'):
                plot._gaussian_reference_renderers = {
                    key: plot.line('kh', key, source=self.owner.primary.boundary_source,
                        color='black', line_width=2,
                        line_dash='dashed' if key == 'lamb' else 'dotted')
                    for key in self.references}
        self.apply_visibility()

    def apply_visibility(self):
        '''
        Purpose
        -------
        Apply f-mode, branch-boundary, and Gaussian-reference visibility to every
        retained view.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Uses curve toggles plus finite-boundary availability while preserving
            numerical curve sources.
        '''

        # Apply f-mode, branch-boundary, and Gaussian-reference visibility to every
        # retained view
        model = self.owner.model
        for plot, renderers in self.overlays.items():
            renderers[0].visible = self.fmode.active
            for index, renderer in enumerate(renderers[1:]):
                toggle = self.toggles.get((model.definition.key, index))
                renderer.visible = index < len(model.boundary_sources_by_branch[int(self.owner.branch_select.value)]) and toggle is not None and toggle.active
        for m in self.owner.model_workspace.models:
            for renderer in [*m.fmode_renderers, *m.filtered.fmode_renderers]:
                renderer.visible = self.fmode.active
            for side in (m, m.filtered):
                for renderers in side.boundary_renderers_by_branch:
                    for index, renderer in enumerate(renderers):
                        toggle = self.toggles.get((m.definition.key, index))
                        values = renderer.data_source.data['nu']
                        renderer.visible = ((toggle is None or toggle.active)
                                            and bool(np.isfinite(values).any()))
        for plot in self.owner.all_plots():
            for key, renderer in getattr(plot, '_gaussian_reference_renderers', {}).items():
                renderer.visible = self.references[key].active
