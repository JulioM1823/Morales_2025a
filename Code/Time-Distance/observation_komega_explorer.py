'''
Purpose
-------
Build the observation/simulation Gaussian-filter explorer with native cube recalculation.

Inputs
------
None

Outputs
-------
ObservationKomegaExplorer, ObservationGaussianExplorer, build_document
    Bokeh controllers for linked phase/filter/result panels and dataset
    parameter persistence. Shared thread pools handle loading and native
    recalculation; document callbacks publish only current-session results.
'''
from __future__ import annotations

# Import safe status rendering, paths, worker pools, and numerical plotting tools
from html import escape
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from bokeh.document import Document
from bokeh.events import DocumentReady
from bokeh.layouts import column, row
from bokeh.models import (Button, ColumnDataSource, CustomJS,
                          Div, GridBox, HoverTool, MultiSelect,
                          Spinner, TextInput, Toggle)
from bokeh.plotting import figure

# Reuse the exact Gaussian preview/filter math and native observation contracts
from gaussian_filter_explorer import (CONFIG_FILE, GaussianFilterExplorer,
    PARAMETER_KEYS, PreviewGeometry, axis_limits, compute_filter_result,
    compute_diagram_filter, filter_boundaries)
from observation_datasets import (discover_observations, file_fingerprint,
                                 load_observation, reproducibility_metadata)
from observation_filter_registry import (DEFAULT_REGISTRY, RegistryError,
                                        read_registry, store_parameters)
from bokeh_ui_helpers import (FileSelector, PHASE_PALETTE, phase_color_mapper,
                              phase_color_bar, style_phase_plot)

# Share bounded worker pools across sessions; publish results only through document callbacks
LOAD_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix='observation-loader')
RECALCULATION_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='dopplergram-recalculation')


class ObservationGaussianExplorer(GaussianFilterExplorer):
    '''
    Purpose
    -------
    Connect the model-tool Gaussian preview to its observation controller.

    Inputs
    ------
    doc: bokeh.document.Document
        Document used by the inherited Gaussian preview.

    controller: ObservationKomegaExplorer
        Owner receiving geometry checks and completed filter results.

    config_file: str or Path
        Configuration path supplying filter defaults.

    Outputs
    -------
    explorer: ObservationGaussianExplorer
        Gaussian preview with initial recomputation disabled; the owner
        controls dataset sampling and native-result updates.
    '''

    def __init__(self, doc, controller, config_file):
        '''
        Purpose
        -------
        Store the observation controller and create the inherited Gaussian-preview widgets.

        Inputs
        ------
        doc: bokeh.document.Document
            Document receiving the inherited layout.

        controller: ObservationKomegaExplorer
            Owner managing datasets, sampling, and persistence.

        config_file: str or Path
            Filter configuration file.

        Outputs
        -------
        None
            Initialize the inherited preview without scheduling its initial solve.
        '''

        # Link inherited filter callbacks to the observation controller before widget creation
        self.controller = controller
        super().__init__(doc, config_file=config_file, schedule_initial=False)

    def _perform_recompute(self):
        '''
        Purpose
        -------
        Validate observation sampling, refresh the Gaussian preview, and notify its controller.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Clear invalid geometry/filter results, or pass a computed FilterResult
            to filter_changed(). Preview errors yield a None result.
        '''

        try:
            # Reject unsupported sampling before the inherited preview calculation
            self.controller._set_geometry()
        except ValueError as exc:
            self._clear_failed_result(str(exc))
            self.controller.filter_changed(None)
            return
        # Forward only a successfully computed Gaussian result to the observation controller
        super()._perform_recompute()
        result = None if self.error_label.visible else compute_filter_result(
            self.geometry, **self._current_parameters())
        self.controller.filter_changed(result)

    def _on_slider_change(self, attr, old, new):
        '''
        Purpose
        -------
        Mark user Gaussian edits unsaved before invoking the inherited change handler.

        Inputs
        ------
        attr: str
            Changed Bokeh property name.

        old, new: object
            Previous and new widget property values.

        Outputs
        -------
        None
            Invalidate the controller recalculation when callbacks are not
            suppressed, then apply the ordinary Gaussian slider-change behavior.
        '''

        if not self._suppress_callbacks:
            self.controller._mark_unsaved()
        super()._on_slider_change(attr, old, new)


class ObservationKomegaExplorer:
    '''
    Purpose
    -------
    Manage linked dataset phase, Gaussian transmission, and recalculated phase panels.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document receiving the controls, images, and callbacks.

    config_file: str or Path, optional
        Pipeline configuration file used for discovery/filtering defaults.

    registry_file: str or Path, optional
        Dataset-specific Gaussian parameter registry.

    product_roots, raw_roots: iterable or None, optional
        Discovery roots for saved numerical products and raw source cubes.

    schedule_initial: bool, optional
        Schedule selection-triggered loading when True. With an available initial
        record and select_initial=True, False loads that record synchronously.

    launch_context: dict or None, optional
        Validated launch provenance identifying an initial dataset and optional
        selected-subplot processing settings.

    observations: iterable of Observation or None, optional
        Supplied dataset catalog. None discovers immediately for non-session
        documents or after DocumentReady for a server session.

    input_observation: Observation or None, optional
        Explicit initial dataset record, taking precedence over a launch record.

    select_initial: bool, optional
        Select/load an available record during construction when True. Deferred
        catalog discovery uses schedule_initial for its later auto-selection.

    Outputs
    -------
    explorer: ObservationKomegaExplorer
        Dataset browser, parameter/sampling controls, asynchronous work state,
        linked plots, and per-dataset registry actions attached to doc.
    '''

    def __init__(self, doc: Document, *, config_file=CONFIG_FILE,
                 registry_file=DEFAULT_REGISTRY, product_roots=None, raw_roots=None,
                 schedule_initial=True, launch_context=None, observations=None, input_observation=None,
                 select_initial=True):
        '''
        Purpose
        -------
        Initialize dataset discovery, linked controls/plots, and initial selection behavior.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document receiving the controls, images, and callbacks.

        config_file: str or Path, optional
            Pipeline configuration file used for discovery/filtering defaults.

        registry_file: str or Path, optional
            Dataset-specific Gaussian parameter registry.

        product_roots, raw_roots: iterable or None, optional
            Discovery roots for saved numerical products and raw source cubes.

        schedule_initial: bool, optional
            Schedule selection-triggered loading when True. With an available initial
            record and select_initial=True, False loads that record synchronously.

        launch_context: dict or None, optional
            Validated launch provenance identifying an initial dataset and optional
            selected-subplot processing settings.

        observations: iterable of Observation or None, optional
            Supplied dataset catalog. None discovers immediately for non-session
            documents or after DocumentReady for a server session.

        input_observation: Observation or None, optional
            Explicit initial dataset record, taking precedence over a launch record.

        select_initial: bool, optional
            Select/load an available record during construction when True. Deferred
            catalog discovery uses schedule_initial for its later auto-selection.

        Outputs
        -------
        None
            Add the explorer root, register callbacks, and choose an initial
            dataset when requested. Server catalog discovery waits for rendering;
            explicit launch/input records remain available before discovery finishes.
        '''

        # Resolve per-session paths and choose immediate versus deferred catalog discovery
        self.doc = doc
        self.launch_context = launch_context
        self.config_file = Path(config_file).expanduser().resolve()
        self.registry_file = Path(registry_file).expanduser().resolve()
        deferred_catalog = observations is None and doc.session_context is not None
        self.observations = ([] if deferred_catalog else list(observations) if observations is not None else
            discover_observations(config_file=self.config_file, product_roots=product_roots,
                                  raw_roots=raw_roots, include_simulations=True))
        # Prioritize validated launch provenance, then any explicit input observation
        initial_id = None
        if launch_context is not None:
            from komega_bokeh_context import validate_context
            initial = validate_context(launch_context)
            initial_id = initial.id
            # The validated launch can carry complete original-input provenance
            # even when discovery found only the removed intermediate export.
            self.observations = [initial] + [item for item in self.observations if item.id != initial_id]
        if input_observation is not None:
            initial_id = input_observation.id
            self.observations = [input_observation] + [item for item in self.observations
                                                      if item.id != initial_id]
        # Initialize dataset/filter state and independent stale-work generation guards
        self.catalog = {item.id: item for item in self.observations}
        self.data = None
        self.filter_result = None
        self.transmission = None
        self.selected_id = None
        self._suppress = False
        self._load_callback = None
        self._load_generation = 0
        self._loading = False
        self._closed = False
        self._recalculation_generation = 0
        self._recalculation_key = None
        self._recalculation_future = None
        self._async_recalculation = doc.session_context is not None
        self.filtered_dopplergrams = None
        self.recalculation_metadata = None
        self._gaussian_unsaved = False
        doc.on_session_destroyed(lambda context: setattr(self, '_closed', True))

        # Build the dataset browser and persistence/filter actions
        self.file_selector = FileSelector(self.observations,
            title='Observations & simulations — select one', prefix='observations', width=520)
        self.search, self.selector = self.file_selector.search, self.file_selector.selector
        self.full_path = self.file_selector.full_path
        self.count = Div(width=370, visible=False, name='observations:count')
        self.selected = Div(text='No dataset selected.', sizing_mode='stretch_width',
                            name='observations:selected')
        self.status = Div(width=330, styles={'overflow-wrap': 'anywhere'}, name='observations:status')
        self.store_button = Button(label='Store Parameters', button_type='success',
            width=330, height=40, disabled=True, name='observations:store')
        self.apply_filter = Toggle(label='Apply Filter', active=False, button_type='primary',
            width=340, name='observations:apply_filter')
        self.remove_filter = Button(label='Remove Filter', width=340, name='observations:remove_filter')
        self.remove_filter.on_click(lambda: setattr(self.apply_filter, 'active', False))
        # Expose exact native dimensions, cadence in seconds, and pixel scale in Mm
        self.sampling = {
            'nx': Spinner(title='Spatial samples nx', low=2, high=16384, step=1, value=160, width=155),
            'ny': Spinner(title='Spatial samples ny', low=2, high=16384, step=1, value=160, width=155),
            'nt': Spinner(title='Temporal samples nt', low=3, high=100000, step=1, value=840, width=155),
            'dt_seconds': Spinner(title='Cadence [s]', low=0.00001, step=.01, value=11.88, width=155),
            'dx_Mm': Spinner(title='Pixel scale [Mm]', low=0.00001, step=.001, value=.43, width=155),
        }
        for key, widget in self.sampling.items():
            widget.name = f'observations:sampling:{key}'
            widget.on_change('value', self._sampling_changed)
        # Embed the shared Gaussian controls without retaining their standalone document root
        self.filter = ObservationGaussianExplorer(doc, self, self.config_file)
        doc.remove_root(self.filter.layout)
        for slider in self.filter.sliders.values():
            slider.width = 230
        self.filter.status.sizing_mode = 'stretch_width'
        self.filter.status.width = None
        # Create separate original/result images and a common physical hover table
        self.image_source = ColumnDataSource(self._empty_image(), name='observations:image')
        self.result_source = ColumnDataSource(self._empty_image(), name='observations:result')
        self.hover_source = ColumnDataSource({'kh': [], 'nu': [], 'phase': [], 'result': [], 'transmission': [], 'power': []},
                                            name='observations:hover')
        self.mapper = phase_color_mapper()
        self.boundary_source = ColumnDataSource({
            'kh': [], 'f_mode': [], 'lamb': [], 'cap': []
        }, name='observations:boundary')
        self.observed_plot = self._phase_plot('Observed phase difference', 'observations:plot', self.image_source, 'phase')
        self.result_plot = self._phase_plot('Filtered result', 'observations:result_plot', self.result_source, 'result')
        # Wire selection, storage, and filter-application actions before attaching the layout
        self.search.on_change('value_input', self._search_changed)
        self.selector.on_change('value', self._selection_changed)
        self.store_button.on_click(self._store)
        self.apply_filter.on_change('active', lambda attr, old, new: self._refresh_preview())
        self.layout = self._build_layout()
        doc.add_root(self.layout)
        doc.title = 'Observation & Simulation Gaussian k–ω Filter Explorer'
        self._search_changed('value_input', '', '')
        # Defer cloud catalog reads until the server page is visible
        if deferred_catalog:
            def discover_after_render(event):
                '''
                Purpose
                -------
                Start deferred dataset discovery after the Bokeh session has rendered.

                Inputs
                ------
                event: bokeh.events.DocumentReady
                    Document-ready event; its payload is not otherwise used.

                Outputs
                -------
                None
                    Submit catalog discovery to LOAD_POOL and attach a completion callback.
                '''

                # Perform directory discovery away from the Bokeh document thread
                future = LOAD_POOL.submit(discover_observations,
                    config_file=self.config_file, product_roots=product_roots,
                    raw_roots=raw_roots, include_simulations=True)
                def complete_catalog(done):
                    '''
                    Purpose
                    -------
                    Move completed catalog discovery from its worker onto the document callback queue.

                    Inputs
                    ------
                    done: concurrent.futures.Future
                        Discovery future containing Observation records or an exception.

                    Outputs
                    -------
                    None
                        Ignore closed sessions; otherwise schedule accept_catalog on the
                        Bokeh document thread.
                    '''

                    if self._closed:
                        return
                    def accept_catalog():
                        '''
                        Purpose
                        -------
                        Merge discovered records with explicit catalog entries and refresh dataset selectors.

                        Inputs
                        ------
                        None

                        Outputs
                        -------
                        None
                            Ignore closed sessions, log discovery failures, and preserve explicit
                            records over discovered duplicates. Update the primary/available
                            secondary catalogs and optionally select the first record after rendering.
                        '''

                        if self._closed:
                            return
                        try:
                            discovered = done.result()
                        except Exception:
                            import logging
                            logging.getLogger(__name__).exception('Dataset catalog discovery failed')
                            return
                        # Preserve explicit launch/input records when merging discovered catalog entries
                        records = {item.id: item for item in discovered}
                        records.update(self.catalog)
                        targets = [self]
                        secondary = getattr(getattr(self, 'owner', None), 'secondary', None)
                        if secondary is not None:
                            targets.append(secondary)
                        for target in targets:
                            target.observations = list(records.values())
                            target.catalog = dict(records)
                            target.file_selector.records = target.observations
                            target._search_changed('value_input', '', target.search.value_input)
                        # Direct opens have no launch record. Select the same
                        # first catalog entry as before, after the page renders.
                        if self.selected_id is None and self.observations and schedule_initial:
                            self.selector.value = [self.observations[0].id]
                        elif not self.observations:
                            self._status('No numerical datasets found. Check data/raw roots and config.py.', error=True)
                    self.doc.add_next_tick_callback(accept_catalog)
                future.add_done_callback(complete_catalog)
            doc.on_event(DocumentReady, discover_after_render)
        self._refresh_preview()
        # Select the initial record through callbacks or load it synchronously when requested
        if self.observations and select_initial:
            first = initial_id or self.observations[0].id
            if schedule_initial:
                self.selector.value = [first]
            else:
                self._suppress = True
                self.selector.value = [first]
                self._suppress = False
                self.selected_id = first
                self._perform_load(first)
        elif not select_initial:
            self._status('No dataset selected.')
        elif deferred_catalog:
            self._status('Loading dataset catalog…')
        else:
            self._status('No numerical datasets found. Check data/raw roots and config.py.', error=True)

    @staticmethod
    def _empty_image():
        '''
        Purpose
        -------
        Create a fresh unavailable-image payload with the default diagnostic extent.

        Inputs
        ------
        None

        Outputs
        -------
        data: dict
            Bokeh image source with a 2 by 2 NaN raster spanning kh = 0..8 Mm^-1
            and frequency = 0..11 mHz.
        '''

        return {'image': [np.full((2, 2), np.nan)],
                'x': [0.], 'y': [0.], 'dw': [8.], 'dh': [11.]}

    def _phase_plot(self, title, name, source, field):
        '''
        Purpose
        -------
        Create a linked phase panel with displayed-value hover and shared reference curves.

        Inputs
        ------
        title: str
            Initial panel title.

        name: str
            Bokeh model name.

        source: bokeh.models.ColumnDataSource
            Image and physical rectangle fields.

        field: str
            Hover column name selecting original phase or recalculated result.

        Outputs
        -------
        plot: bokeh.plotting.figure
            Styled phase image sharing the Gaussian plot ranges and this controller's
            phase mapper, with hover coordinates in Mm^-1/mHz and phase in degrees.
        '''

        # Share the filter plot ranges so observed and recalculated panels pan/zoom together
        plot = figure(title=title, width=430, height=510,
            x_range=self.filter.plot.x_range, y_range=self.filter.plot.y_range,
            x_axis_label='kₕ [Mm⁻¹]', y_axis_label='ν [mHz]',
            tools='pan,wheel_zoom,box_zoom,reset,save', active_scroll=None,
            toolbar_location='right', name=name)
        style_phase_plot(plot)
        plot.image(image='image', x='x', y='y', dw='dw', dh='dh', source=source,
                   color_mapper=self.mapper, level='image')
        # Hover uses the values actually displayed by each image.
        dk = .1
        renderer = plot.rect(x='kh', y='nu', width=dk, height=dk,
            source=self.hover_source, fill_alpha=0., line_alpha=0.)
        plot.add_tools(HoverTool(renderers=[renderer], tooltips=[
            ('kₕ', '@kh{0.000} Mm⁻¹'), ('ν', '@nu{0.000} mHz'),
            ('Phase difference', f'@{field}{{0.00}} deg'), ('Filter amplitude T', '@transmission{0.0000}'),
            ('Retained power T²', '@power{0.0000}')], point_policy='follow_mouse'))
        # Draw common f-mode, Lamb, and cap references on the phase axes
        plot.line('kh', 'f_mode', source=self.boundary_source, color='#8c8c8c', line_width=3)
        plot.line('kh', 'lamb', source=self.boundary_source, color='black', line_width=3,
                  line_dash='dashed')
        plot.line('kh', 'cap', source=self.boundary_source, color='black', line_width=2,
                  line_dash='dotted')
        plot.add_layout(phase_color_bar(self.mapper), 'right')
        return plot

    def _build_layout(self):
        '''
        Purpose
        -------
        Arrange dataset, filter, persistence/sampling controls and the three linked panels.

        Inputs
        ------
        None

        Outputs
        -------
        layout: bokeh.models.Column
            Explorer application root. Register a layout-only browser resize
            callback; numerical loading, filter calculations, and registry writes
            remain Python operations.
        '''

        # Arrange browser, filter controls, and persistence/sampling in three control groups
        reset = Button(label='Restore filter defaults', width=340)
        reset.on_click(self._reset_filter)
        browser = column(Div(text="<h2 style='margin:0'>Dataset Selection</h2>"),
            self.file_selector.layout, self.count, width=540)
        controls = column(Div(text="<h2 style='margin:0'>Filter Controls</h2>"),
            *[self.filter.numeric_controls[key].layout for key in PARAMETER_KEYS], reset, self.apply_filter, self.remove_filter, width=360)
        persistence = column(Div(text="<h2 style='margin:0'>Persistence & sampling</h2>"),
            self.store_button, self.status,
            row(self.sampling['nx'], self.sampling['ny']),
            row(self.sampling['nt'], self.sampling['dt_seconds']), self.sampling['dx_Mm'],
            width=350)
        self.controls_grid = GridBox(children=[(browser, 0, 0), (controls, 0, 1), (persistence, 0, 2)],
            spacing=12, sizing_mode='stretch_width')
        # Link the three panels and apply the shared diagnostic typography
        plots = [self.observed_plot, self.filter.plot, self.result_plot]
        self.plots_grid = GridBox(children=[(plot, 0, i) for i, plot in enumerate(plots)],
            spacing=8, sizing_mode='stretch_width')
        self.filter.plot.x_range.end = 8.
        self.filter.plot.y_range.end = 11.
        self.filter.plot.title.text = 'Gaussian filter'
        self.filter.plot.yaxis[0].axis_label = 'ν [mHz]'
        for plot in plots:
            plot.toolbar_location = 'right'
            plot.width, plot.height = 430, 510
            plot.title.text_font = 'Times New Roman'
            plot.title.text_font_size = '15pt'
            plot.title.text_font_style = 'normal'
            for axis in (plot.xaxis[0], plot.yaxis[0]):
                axis.axis_label_text_font = axis.major_label_text_font = 'Times New Roman'
                axis.axis_label_text_font_style = 'normal'
                axis.axis_label_text_font_size, axis.major_label_text_font_size = '16pt', '12pt'
                axis.major_tick_in, axis.major_tick_out = 8, 0
                axis.minor_tick_in, axis.minor_tick_out = 4, 0
        # Only layout runs in JS. Data loading, exact Gaussian maths and atomic
        # registry writes remain Python callbacks in this independent server app.
        self.doc.js_on_event(DocumentReady, CustomJS(args=dict(plots=plots,
            plot_grid=self.plots_grid, controls=self.controls_grid,
            browser=browser, filters=controls, persistence=persistence), code="""
            const resize = () => {
                const w = Math.max(360, window.innerWidth - 32);
                const n = w >= 1120 ? 3 : (w >= 850 ? 2 : 1);
                plot_grid.children = plots.map((p, i) => [p, Math.floor(i/n), i%n]);
                for (const p of plots) {
                    p.width = Math.floor(w/n) - 8;
                    p.height = Math.round(Math.max(440, Math.min(650, p.width * 1.18)));
                }
                controls.children = w >= 1120
                    ? [[browser, 0, 0], [filters, 0, 1], [persistence, 0, 2]]
                    : (w >= 770 ? [[browser, 0, 0], [filters, 0, 1], [persistence, 1, 0]]
                    : [[browser, 0, 0], [filters, 1, 0], [persistence, 2, 0]]);
            };
            resize(); window.addEventListener('resize', resize);
        """))
        return column(Div(text=("<h1 style='margin:0 0 5px'>Observation & Simulation Gaussian k–ω Filter Explorer</h1>"
            "<p style='margin:0;color:#475569'>Select an observation or simulation, tune the same Gaussian filter used by the model tool, "
            "and store its parameters. Stored settings load automatically on selection. Pan and zoom are linked.</p>"),
            sizing_mode='stretch_width'), self.controls_grid, self.selected, self.plots_grid,
            sizing_mode='stretch_width', styles={'padding': '12px'}, name='observations:application')

    def _status(self, message, error=False):
        '''
        Purpose
        -------
        Display escaped success/error text while suppressing selected routine status phrases.

        Inputs
        ------
        message: str
            Plain status message, escaped before insertion into HTML.

        error: bool, optional
            Use error styling and retain all messages when True.

        Outputs
        -------
        None
            Update status text/visibility. Non-error Gaussian-applied and Unsaved
            messages are intentionally hidden by their recognized prefixes.
        '''

        # Hide routine status prefixes while escaping all visible dynamic text
        if not error and message.startswith(('Gaussian filter applied independently', 'Unsaved')):
            message = ''
        self.status.text = (f"<p style='margin:3px 0;color:{'#991b1b' if error else '#166534'}'>{escape(message)}</p>"
                            if message else '')
        self.status.visible = bool(message)

    def _search_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Refresh the file-selector search while suppressing resulting selection callbacks.

        Inputs
        ------
        attr: str
            Changed Bokeh property name.

        old, new: object
            Previous and new widget property values.

        Outputs
        -------
        None
            Refresh selector records and restore the callback-suppression flag in
            a finally block.
        '''

        self._suppress = True
        try:
            self.file_selector.refresh()
        finally:
            self._suppress = False

    def _selection_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Keep one selected dataset and schedule its loading after clearing stale displays.

        Inputs
        ------
        attr: str
            Changed selector property name.

        old, new: list of str
            Previous and new selected dataset identifier lists.

        Outputs
        -------
        None
            Ignore suppressed/empty/unknown selections. Retain the newest chosen
            item, advance the load generation, clear data, disable editing, and
            replace any queued next-tick loading callback.
        '''

        if self._suppress or not new:
            return
        # MultiSelect supplies a native scrolling list; retain only the newly
        # handpicked item even when the user holds Ctrl/Command to multi-select.
        identity = next((value for value in reversed(new) if value not in old), new[-1])
        if identity not in self.catalog:
            return
        self._suppress = True
        self.selector.value = [identity]
        self._suppress = False
        # Advance the generation before clearing old data and disabling edits
        self.selected_id = identity
        # Keep any previous worker completion from publishing into this new selection
        self._load_generation += 1
        self.data = None
        self.filter_result = None
        self.store_button.disabled = True
        for widget in [*self.filter.sliders.values(), *self.sampling.values()]:
            widget.disabled = True
        self.image_source.data = self._empty_image()
        self.result_source.data = self._empty_image()
        self.boundary_source.data = {
            'kh': [], 'f_mode': [], 'lamb': [], 'cap': []
        }
        self.hover_source.data = {key: [] for key in self.hover_source.data}
        self.selected.text = f'<b>Selected:</b> {escape(identity)}'
        self._status('Loading dataset…')
        if self._load_callback is not None:
            try:
                self.doc.remove_next_tick_callback(self._load_callback)
            except ValueError:
                pass
        # Queue the worker-launch step after the cleared selection state can render
        self._load_callback = self.doc.add_next_tick_callback(lambda: self._start_load(identity))

    def _start_load(self, identity):
        '''
        Purpose
        -------
        Load cloud-backed data or raw-cube FFT products in a worker and reject stale completions.

        Inputs
        ------
        identity: str
            Selected identifier present in this controller catalog.

        Outputs
        -------
        None
            Start a background load and a 30-second timeout, extended to 120
            seconds for source-backed/raw/processing records. Completion reaches
            the document thread only while its generation, loading state, and
            session remain current; cancellation cannot stop an already running task.
        '''
        self._load_callback = None
        generation = self._load_generation
        self._loading = True
        # Execute cloud reads and original-cube analysis outside the document event loop
        future = LOAD_POOL.submit(load_observation, self.catalog[identity], config_file=self.config_file)
        record = self.catalog[identity]
        # A saved phase product with source companions now performs the same
        # full cube read/native analysis as a raw pair, not an image-only load.
        from output_paths import find_json_sidecar
        source_backed = record.kind == 'recorded_input' or any(
            find_json_sidecar(path, '.inputs.json').is_file() for path in record.files)
        timeout_ms = 120000 if source_backed or record.kind in {'raw_pair', 'processing_result'} else 30000

        # Bound this generation load and leave newer/closed work untouched
        def expired():
            '''
            Purpose
            -------
            Handle the active load timeout without affecting newer selections.

            Inputs
            ------
            None

            Outputs
            -------
            None
                Check the captured load generation/loading/session state, request
                cancellation, and pass a timeout error to the current dataset loader.
            '''

            if generation != self._load_generation or not self._loading or self._closed:
                return
            self._loading = False
            future.cancel()
            self._perform_load(identity, load_error=ValueError(
                'Loading timed out. Ensure the source files and filter_parameters.txt are downloaded '
                'locally, then select another dataset and reselect this one.'))

        timeout = self.doc.add_timeout_callback(expired, timeout_ms)

        def complete(done):
            '''
            Purpose
            -------
            Schedule a load-result callback on the Bokeh document thread.

            Inputs
            ------
            done: concurrent.futures.Future
                Completed ObservationData load or raised worker exception.

            Outputs
            -------
            None
                Ignore a closed session; otherwise queue the nested accept callback.
            '''

            if self._closed:
                return

            def accept():
                '''
                Purpose
                -------
                Accept a worker load only when its captured generation is still active.

                Inputs
                ------
                None

                Outputs
                -------
                None
                    Discard stale/closed/timed-out loads, remove the active timeout, and
                    pass either ObservationData or its exception to _perform_load.
                '''

                # Discard timed-out, superseded, or closed-session completions before touching UI models
                if generation != self._load_generation or not self._loading or self._closed:
                    return
                self._loading = False
                try:
                    self.doc.remove_timeout_callback(timeout)
                except ValueError:
                    pass
                try:
                    data = done.result()
                except Exception as exc:
                    self._perform_load(identity, load_error=exc)
                else:
                    self._perform_load(identity, loaded_data=data)
            self.doc.add_next_tick_callback(accept)

        future.add_done_callback(complete)

    def _perform_load(self, identity, *, loaded_data=None, load_error=None):
        '''
        Purpose
        -------
        Install the current dataset, restore its settings, and refresh linked source models.

        Inputs
        ------
        identity: str
            Dataset identifier; requests for a different current selection are ignored.

        loaded_data: ObservationData or None, optional
            Worker-loaded data; None triggers a synchronous load when no error is supplied.

        load_error: Exception or None, optional
            Existing load failure to report instead of installing data.

        Outputs
        -------
        None
            Apply sampling/filter settings under callback suppression, publish
            degree-valued phase/boundaries/hover data, and recompute the filter.
            Failures clear active data/filter state and report dataset unavailability.
        '''

        self._load_callback = None
        if identity != self.selected_id:
            return
        try:
            if load_error is not None:
                raise load_error
            data = loaded_data if loaded_data is not None else load_observation(
                self.catalog[identity], config_file=self.config_file)
            self.data = data
            self._gaussian_unsaved = False
            self.observed_plot.title.text = ('Simulated phase difference'
                if data.metadata.get('source_type') == 'single_cube' else 'Observed phase difference')
            # Restore launch/registry settings before assigning widget values under suppression
            params, sampling, message, error = self._load_settings(data)
            self._suppress = self.filter._suppress_callbacks = True
            try:
                for key, value in sampling.items():
                    self.sampling[key].value = value
                for key, value in params.items():
                    slider = self.filter.sliders[key]
                    slider.start, slider.end = min(slider.start, value), max(slider.end, value)
                    slider.value = value
            finally:
                self._suppress = self.filter._suppress_callbacks = False
            self._set_geometry()
            # Publish original phase in image order while retaining physical center coordinates
            x, xe = axis_limits(data.kh)
            y, ye = axis_limits(data.nu)
            self.image_source.data = {'image': [data.values.T], 'x': [x], 'y': [y], 'dw': [xe-x], 'dh': [ye-y]}
            boundaries = filter_boundaries(data.kh)
            self.boundary_source.data = {
                'kh': data.kh, 'f_mode': boundaries['f_mode'],
                'lamb': boundaries['lamb'], 'cap': boundaries['cap'],
            }
            kh, nu = np.meshgrid(data.kh, data.nu)
            self.hover_source.data = dict(kh=kh.ravel(), nu=nu.ravel(), phase=data.values.T.ravel(),
                result=data.values.T.ravel(), transmission=np.zeros(kh.size), power=np.zeros(kh.size))
            self.selected.text = f'<b>Selected:</b> {escape(identity)}'
            self.filter._perform_recompute()
            for widget in [*self.filter.sliders.values(), *self.sampling.values()]:
                widget.disabled = False
            self._status(message, error)
        except Exception as exc:
            self.data = None
            self.filter_result = None
            self.store_button.disabled = True
            self.filter._clear_failed_result('Dataset unavailable')
            self._status(f'Cannot load {self.catalog[identity].label}: {exc}', error=True)
            self._refresh_preview()

    def _load_settings(self, data):
        '''
        Purpose
        -------
        Restore selected-subplot or fingerprint-matched dataset filter settings.

        Inputs
        ------
        data: ObservationData
            Loaded phase axes, source fingerprints, native sampling, and metadata.

        Outputs
        -------
        params, sampling, message, error: tuple
            Gaussian parameters, nx/ny/nt plus cadence (s)/pixel scale (Mm), and
            user status. Matching launch-processing settings take precedence;
            registry records require unchanged source hashes, axes, and optional
            Dopplergram versions. Registry mismatches return defaults with an error.
        '''
        params = self.filter.defaults
        sampling = dict(nx=data.geometry.nx, ny=data.ny, nt=data.geometry.nt,
                        dt_seconds=data.geometry.dt_seconds, dx_Mm=data.geometry.dx_Mm)
        message = f'Using default parameters for {data.observation.label}'
        error = False
        # A matching selected-subplot launch overrides stored dataset Gaussian parameters
        launch = self.launch_context
        if launch and data.observation.id == launch['dataset']['id'] and launch.get('processing'):
            reference = launch['processing']['input_reference']
            effective = reference['filtering']
            if effective.get('enabled') and 'gaussian' in effective.get('filter_sequence', []) and effective.get('gaussian', {}).get('enabled'):
                from observation_filter_registry import validate_parameters
                params = validate_parameters({key: effective['gaussian'][key] for key in PARAMETER_KEYS})
            return params, sampling, f'Loaded selected subplot parameters for {data.observation.label}', False
        try:
            # Require unchanged source fingerprints and axes before reusing persisted settings
            saved = read_registry(self.registry_file)['observations'].get(data.observation.id)
            if saved:
                original = saved['dataset']
                old_hashes = [item['sha256'] for item in original['metadata']['source_fingerprints']]
                hashes = [item['sha256'] for item in data.metadata['source_fingerprints']]
                axes_match = (np.array_equal(original['axes']['kh_Mm_inverse'], data.kh)
                              and np.array_equal(original['axes']['nu_mHz'], data.nu))
                if old_hashes != hashes or not axes_match:
                    raise RegistryError('Source data or axes changed since storing. Using defaults; review before replacing the record.')
                old_versions = original['metadata'].get('dopplergram_source_versions')
                if old_versions is not None and tuple(map(tuple,old_versions)) != tuple(map(tuple,data.metadata.get('dopplergram_source_versions',[]))):
                    raise RegistryError('Original Dopplergram changed since storing. Using defaults; review before replacing the record.')
                params = saved['gaussian']['parameters']
                sampling = saved['dataset']['sampling']
                message = f'Loaded stored parameters for {data.observation.label}'
        except RegistryError as exc:
            message, error = str(exc), True
        return params, sampling, message, error

    def _set_geometry(self):
        '''
        Purpose
        -------
        Validate sampling controls and construct the exact Gaussian preview geometry.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Require integer nx/ny >= 2, nt >= 3, and positive finite cadence (s)
            and pixel scale (Mm). Loaded Dopplergram sampling must match its native
            dimensions/scales within tolerance; no resizing or resampling occurs.
            Store the validated PreviewGeometry or raise ValueError.
        '''

        values = {key: widget.value for key, widget in self.sampling.items()}
        # Require finite integer dimensions and positive physical sampling scales
        for key in ('nx', 'ny', 'nt'):
            value = values[key]
            if value is None or not np.isfinite(value) or int(value) != value or value < (3 if key == 'nt' else 2):
                raise ValueError(f'{key} must be an integer sample count in the displayed range.')
        for key in ('dt_seconds', 'dx_Mm'):
            if values[key] is None or not np.isfinite(values[key]) or values[key] <= 0:
                raise ValueError(f'{key} must be positive and finite.')
        # Native cube sampling is immutable here; edited values cannot imply resampling
        if self.data is not None and self.data.dopplergrams is not None:
            expected = dict(nx=self.data.geometry.nx,ny=self.data.ny,nt=self.data.geometry.nt,
                dt_seconds=self.data.geometry.dt_seconds,dx_Mm=self.data.geometry.dx_Mm)
            if any(not np.isclose(values[key],expected[key],rtol=1e-10,atol=1e-12) for key in expected):
                raise ValueError('Sampling must match the loaded Dopplergram cubes; no implicit resizing or resampling is applied.')
        # Store the validated geometry used by both filter and native phase previews
        self.filter.geometry = PreviewGeometry(int(values['nx']), int(values['nt']),
            float(values['dt_seconds']), float(values['dx_Mm']),
            f"{int(values['nx'])} × {int(values['ny'])} spatial × {int(values['nt'])} temporal samples")

    def _sampling_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Validate edited sampling and schedule a filter refresh when data is loaded.

        Inputs
        ------
        attr: str
            Changed Bokeh property name.

        old, new: object
            Previous and new widget property values.

        Outputs
        -------
        None
            Mark valid edits unsaved and schedule the filter; invalid sampling
            disables storage, clears the filter result, and reports the error.
        '''

        if self._suppress or self.data is None:
            return
        try:
            self._set_geometry()
            self._mark_unsaved()
            self.filter.schedule_recompute()
        except ValueError as exc:
            self.filter_result = None
            self.store_button.disabled = True
            self._status(str(exc), error=True)
            self._refresh_preview()

    def _mark_unsaved(self):
        '''
        Purpose
        -------
        Mark Gaussian state unsaved and invalidate any derived native recalculation.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Set the unsaved flag, clear/cancel current recalculation state, and
            request the dataset-specific unsaved status when data is present.
        '''

        self._gaussian_unsaved = True
        self._invalidate_recalculation()
        if self.data is not None:
            self._status('Unsaved changes for this dataset. Click Store Parameters to save.')

    def _reset_filter(self):
        '''
        Purpose
        -------
        Restore Gaussian sliders to configuration defaults and request immediate recomputation.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Suppress intermediate slider callbacks, restore defaults, schedule one
            filter refresh, and display the explicit storage reminder.
        '''

        self.filter._suppress_callbacks = True
        try:
            for key, value in self.filter.defaults.items():
                self.filter.sliders[key].value = value
        finally:
            self.filter._suppress_callbacks = False
        self.filter.schedule_recompute(delay_ms=0)
        self._status('Filter controls restored to config.py defaults. Click Store Parameters to save.')

    def filter_changed(self, result):
        '''
        Purpose
        -------
        Receive a Gaussian result and refresh the dataset preview/storage availability.

        Inputs
        ------
        result: FilterResult or None
            Computed Gaussian preview result; None indicates an unavailable/failed filter.

        Outputs
        -------
        None
            Store the filter result, disable storage when data/filter is absent,
            and refresh the native-result preview.
        '''

        self.filter_result = result
        self.store_button.disabled = self.data is None or result is None
        self._refresh_preview()

    def _refresh_preview(self):
        '''
        Purpose
        -------
        Apply Gaussian filtering to both source cubes and rerun their native phase diagnostic.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Use shared primary filter controls when available. Display the original
            phase when filtering is disabled; require original cubes and runtime
            metadata before recalculation. Deduplicate work by data/parameter key,
            use a worker for server sessions, and publish only current-generation
            results. Phase images are never multiplied directly by transmission.
        '''
        # Use the ready primary controller as the shared filter-state owner when available
        shared = self.owner.primary if hasattr(self,'owner') and self.owner.ready else self
        if self.data is None:
            self._invalidate_recalculation()
            self.transmission = None
            self.result_source.data = self._empty_image()
            return
        data = self.data
        original = data.values.T
        # Evaluate transmission on the loaded phase axes without modifying phase values
        self.transmission = (None if shared.filter_result is None else
            compute_diagram_filter(self.data.kh, self.data.nu, self.filter.geometry,
                **shared.filter._current_parameters()))
        if self.transmission is not None and self.transmission.shape != original.shape:
            raise ValueError('Filter and dataset dimensions do not match.')
        # Restore original phase immediately when Gaussian application is disabled
        if not shared.apply_filter.active:
            self._invalidate_recalculation()
            self._show_recalculated(data.values,data.kh,data.nu)
            return
        if self.transmission is None:
            self._invalidate_recalculation()
            return
        # Native recalculation requires the original cube pair and its resolved runtime
        if data.dopplergrams is None or data.analysis_config is None:
            self._invalidate_recalculation()
            self._status('Cannot recalculate Gaussian filtering: '+data.metadata.get('recalculation_error',
                'Original Dopplergram cubes and their analysis runtime are unavailable for this phase-only product.'),error=True)
            self.store_button.disabled = True
            return
        parameters = shared.filter._current_parameters()
        # Deduplicate calculations for the same loaded-data identity and parameter tuple
        key = (id(data),tuple(sorted(parameters.items())))
        if key == self._recalculation_key:
            return
        self._invalidate_recalculation()
        generation = self._recalculation_generation
        self._recalculation_key = key
        self.store_button.disabled = True
        self._status('Reconstructing both filtered Dopplergrams and recalculating k–ω…')
        # Capture source data and generation before entering synchronous or worker execution
        from dopplergram_recalculation import recalculate
        def calculate():
            '''
            Purpose
            -------
            Recalculate the captured source-cube pair using the captured Gaussian parameters.

            Inputs
            ------
            None

            Outputs
            -------
            values, kh, nu, metadata, cubes: tuple
                Native phase in degrees with [kh, nu] shape, axes in Mm^-1/mHz,
                recalculation provenance, and the two filtered Dopplergram cubes.
                Preserve any required pre-Gaussian raw cubes and stage order.
            '''

            return recalculate(data.dopplergrams,data.analysis_config,parameters,raw_cubes=data.pre_gaussian_raw)
        def accept(result=None,error=None):
            '''
            Purpose
            -------
            Publish a recalculation only while its data, parameters, filter state, and generation match.

            Inputs
            ------
            result: tuple or None, optional
                Completed phase/axes/metadata/cubes tuple from calculate().

            error: Exception or None, optional
                Recalculation failure to display instead of publishing a result.

            Outputs
            -------
            None
                Discard stale/closed/disabled-filter results. On success retain filtered
                cubes/provenance, update images/hover, enable storage, and synchronize
                an available owner; on failure clear the work key and report the error.
            '''

            # Verify the entire captured state before publishing worker output
            if (self._closed or generation != self._recalculation_generation or self.data is not data
                    or parameters != shared.filter._current_parameters() or not shared.apply_filter.active):
                return
            if error is not None:
                self._recalculation_key = None
                self._status('Cannot recalculate Gaussian filtering: '+str(error),error=True)
                return
            # Publish recalculated phase and retain the two filtered cubes with their provenance
            values,kh,nu,metadata,cubes = result
            self.filtered_dopplergrams,self.recalculation_metadata = cubes,metadata
            self._show_recalculated(values,kh,nu)
            self.store_button.disabled = False
            self._status('Gaussian filter applied independently to both Dopplergrams; native k–ω recalculated.'
                + (' Unsaved filter changes.' if self._gaussian_unsaved else ''))
            if hasattr(self,'owner'): self.owner.sync_state()
        # Use synchronous execution for non-session documents and a worker for server sessions
        if not self._async_recalculation:
            try: result = calculate()
            except Exception as exc: accept(error=exc)
            else: accept(result=result)
            return
        future = RECALCULATION_POOL.submit(calculate)
        self._recalculation_future = future
        def complete(done):
            '''
            Purpose
            -------
            Retrieve a recalculation future and move its result/error onto the document thread.

            Inputs
            ------
            done: concurrent.futures.Future
                Completed native diagnostic recalculation.

            Outputs
            -------
            None
                Ignore closed sessions and cancelled futures; otherwise queue accept
                with the result or captured worker exception.
            '''

            if self._closed or done.cancelled(): return
            try: result,error = done.result(),None
            except Exception as exc: result,error = None,exc
            self.doc.add_next_tick_callback(lambda: accept(result,error))
        future.add_done_callback(complete)

    def _invalidate_recalculation(self):
        '''
        Purpose
        -------
        Advance the recalculation generation and clear its displayed/source-derived state.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Clear the work key, request future cancellation, discard filtered cubes
            and metadata, replace the result raster with NaNs, and clear result
            hover values. Running workers become stale through the generation check.
        '''

        # Invalidate running work even when Future.cancel cannot stop an active worker
        self._recalculation_generation += 1
        self._recalculation_key = None
        if self._recalculation_future is not None:
            self._recalculation_future.cancel()
        self.filtered_dopplergrams = self.recalculation_metadata = None
        self.result_source.data = self._empty_image()
        if self.hover_source.data.get('result') is not None:
            self.hover_source.data = dict(self.hover_source.data,result=np.full(len(self.hover_source.data['result']),np.nan))

    def _show_recalculated(self,values,kh,nu):
        '''
        Purpose
        -------
        Publish a phase image and matching original/result/filter hover values.

        Inputs
        ------
        values: array-like
            Recalculated phase in degrees, with shape (n_kh, n_nu).

        kh: array-like
            Horizontal-wavenumber centers in Mm^-1.

        nu: array-like
            Frequency centers in mHz.

        Outputs
        -------
        None
            Transpose to image order (nu, kh), derive outer image bounds, and
            flatten matching hover values. Use unit transmission when no filter
            exists and report retained power as transmission squared.
        '''

        # Convert center axes to image bounds and retain phase values in matching hover order
        x,xe = axis_limits(kh);y,ye = axis_limits(nu)
        displayed = np.asarray(values).T
        self.result_source.data = dict(image=[displayed],x=[x],y=[y],dw=[xe-x],dh=[ye-y])
        xx,yy = np.meshgrid(kh,nu)
        transmission = self.transmission if self.transmission is not None else np.ones_like(displayed)
        self.hover_source.data = dict(kh=xx.ravel(),nu=yy.ravel(),phase=self.data.values.T.ravel(),
            result=displayed.ravel(),transmission=transmission.ravel(),power=(transmission**2).ravel())

    def _store(self):
        '''
        Purpose
        -------
        Store dataset filter parameters only after rechecking source identity and sampling.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Recheck file hashes and original Dopplergram versions, validate sampling
            and filter computation, build reproducibility metadata, and call the
            registry writer with any saved model context. Clear the unsaved flag on
            success; registry/value/filesystem errors become visible status messages.
        '''

        try:
            if self.data is None or self.data.observation.id != self.selected_id:
                raise RegistryError('Wait for the selected dataset to finish loading.')
            # Catch external changes before associating current controls with an
            # outdated map; reselect the dataset to load its new contents.
            hash_file = file_fingerprint
            if self.data.observation.input_reference is not None:
                from processing_results import fingerprint
                hash_file = fingerprint
            current_hashes = [hash_file(p)['sha256'] for p in self.data.observation.files]
            loaded_hashes = [p['sha256'] for p in self.data.metadata['source_fingerprints']]
            if current_hashes != loaded_hashes:
                raise RegistryError('Source changed while open. Reselect the dataset before storing.')
            # Verify original cube versions in addition to the selected product fingerprints
            versions = self.data.metadata.get('dopplergram_source_versions',[])
            if versions:
                from dopplergram_recalculation import _version
                if _version([Path(entry[0]) for entry in versions]) != tuple(tuple(entry) for entry in versions):
                    raise RegistryError('Original Dopplergram changed while open. Reselect it before storing.')
            self._set_geometry()
            self.filter._perform_recompute()
            if self.filter_result is None:
                raise RegistryError('Filter calculation failed; parameters were not stored.')
            # Persist the exact accepted filter controls and sampling/provenance contract
            metadata = reproducibility_metadata(self.data, self.filter.geometry)
            metadata['sampling']['ny'] = int(self.sampling['ny'].value)
            store_parameters(self.selected_id, metadata, self.filter._current_parameters(), self.registry_file,
                             model_context=self._saved_model_context())
            self._gaussian_unsaved = False
            self._status(f'Parameters stored for {self.data.observation.label}')
        except (RegistryError, ValueError, OSError) as exc:
            self._status(str(exc), error=True)

    def _saved_model_context(self):
        '''
        Purpose
        -------
        Provide the base observation explorer model-context persistence hook.

        Inputs
        ------
        None

        Outputs
        -------
        None
            The base explorer stores no model context; derived controllers may
            override this method.
        '''

        return None


def build_document(doc, **kwargs):
    '''
    Purpose
    -------
    Create and attach one observation/simulation explorer to a Bokeh document.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document receiving the application root and callbacks.

    **kwargs: object
        Keyword options forwarded unchanged to ObservationKomegaExplorer.

    Outputs
    -------
    explorer: ObservationKomegaExplorer
        Created controller attached to the supplied document.
    '''

    return ObservationKomegaExplorer(doc, **kwargs)
