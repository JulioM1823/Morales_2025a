'''
Purpose
-------
Build a separate native magnetogram preprocessing workspace with process-isolated cube
loading and FFT calculations.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for magnetogram_explorer.py.

Notes
-----
Separate Bokeh magnetogram workspace; expensive jobs run outside its document.
'''
from __future__ import annotations

# Import the libraries and shared helpers used by this module
from concurrent.futures import ProcessPoolExecutor
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from bokeh.events import DocumentReady
from bokeh.layouts import column, row
from bokeh.models import (Button, ColorBar, ColumnDataSource, CustomJS, Div,
                          GridBox, LinearColorMapper, Range1d, Select, Slider, Spinner, TextInput)
from bokeh.palettes import Greys256
from bokeh.plotting import figure
from matplotlib import colormaps
from matplotlib.colors import to_hex

from gaussian_filter_explorer import CONFIG_FILE, axis_limits
from magnetogram_workflow import (compute_result, defaults, discover_dopplergrams,
                                  prepare_dataset, validate_parameters)
from observation_komega_explorer import PHASE_PALETTE
from processing_results import DEFAULT_RESULT_CACHE, ResultStore
from bokeh_ui_helpers import FileSelector, remove_plot_legends

# NetCDF/HDF5 readers and large FFTs are isolated from Bokeh's IOLoop. One worker
# also avoids overlapping large cubes and non-thread-safe NetCDF library calls.
COMPUTE_POOL = ProcessPoolExecutor(max_workers=1)


def process_dataset(dataset, parameters, inputs, config_file, cache_root):
    '''
    Purpose
    -------
    Prepare aligned native cubes and compute the requested magnetic-filter processing
    result.

    Inputs
    ------
    dataset: DopplerDataset
        Original observational pair or simulation cube selection with canonical
        identity.
    parameters: dict
        Validated physical filtering parameters with their native units.
    inputs: dict
        Mode-specific original sampling, observable, and selected-height settings.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    cache_root: str or pathlib.Path
        Content-addressed processing-result cache directory.

    Outputs
    -------
    prepared_id, result_id: tuple of str
        Published content-addressed aligned-input and final-result identifiers;
        numerical/I/O errors propagate to the caller.
    '''

    # Prepare aligned native cubes and compute the requested magnetic-filter processing
    # result
    prepared, config = prepare_dataset(dataset, parameters, inputs=inputs,
                                       config_file=config_file, cache_root=cache_root)
    result = compute_result(prepared, config, parameters, cache_root=cache_root)
    return prepared.id, result.id


class MagnetogramExplorer:
    '''
    Purpose
    -------
    Coordinate original dataset selection, magnetic preprocessing, native previews, and
    result handoff.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    cache_root: str or pathlib.Path
        Content-addressed processing-result cache directory.
    raw_roots: iterable of path-like or None
        Optional original observational cube roots; None uses configured discovery.
    simulation_roots: iterable of path-like or None
        Optional original NetCDF simulation roots/files; None uses configured discovery.
    datasets: iterable or None
        Explicit dataset records; None runs the normal discovery path.
    schedule_initial: bool
        Schedule the initial calculation after document construction when True.

    Outputs
    -------
    explorer: MagnetogramExplorer
        Document-root controls/plots with debounced process-worker calculations and
        immutable cached result references.
    '''

    def __init__(self, doc, *, config_file=CONFIG_FILE, cache_root=DEFAULT_RESULT_CACHE,
                 raw_roots=None, simulation_roots=None, datasets=None, schedule_initial=True):
        '''
        Purpose
        -------
        Construct the magnetogram workspace, source catalog, controls, plots, and
        background lifecycle.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        config_file: str or pathlib.Path
            Configuration-module path used to reconstruct the runtime settings.
        cache_root: str or pathlib.Path
            Content-addressed processing-result cache directory.
        raw_roots: iterable of path-like or None
            Optional original observational cube roots; None uses configured discovery.
        simulation_roots: iterable of path-like or None
            Optional original NetCDF simulation roots/files; None uses configured
            discovery.
        datasets: iterable or None
            Explicit dataset records; None runs the normal discovery path.
        schedule_initial: bool
            Schedule the initial calculation after document construction when True.

        Outputs
        -------
        None
            Adds the workspace to doc, wires selection/science/display callbacks, and
            optionally selects the first original dataset.
        '''

        # Construct the magnetogram workspace, source catalog, controls, plots, and
        # background lifecycle
        self.doc = doc
        self.config_file = Path(config_file).resolve()
        self.store = ResultStore(cache_root)
        records = discover_dopplergrams(config_file=config_file, raw_roots=raw_roots,
            simulation_roots=simulation_roots) if datasets is None else list(datasets)
        self.catalog = {item.id: item for item in records}
        self.current = None
        self.prepared = self.result = None
        self.prepared_arrays = self.result_arrays = {}
        self._suppress = False
        self._generation = 0
        self._pending = self._future = None
        self._queued_request = None
        self._closed = False
        doc.on_session_destroyed(self._destroyed)

        # Build source selection and accepted magnetic/sampling controls before
        # registering science callbacks
        self.file_selector = FileSelector(records, title='Observations and simulations — select one',
                                          prefix='magnetogram', width=700)
        self.search, self.selector = self.file_selector.search, self.file_selector.selector
        self.full_path = self.file_selector.full_path
        self.selection_status = Div(width=630, name='magnetogram:selected')
        self.status = Div(sizing_mode='stretch_width', name='magnetogram:status')
        self.selection = Select(title='Retain pixels', value='magnetic',
            options=[('magnetic', 'Magnetic: |B| > threshold'), ('nonmagnetic', 'Nonmagnetic: |B| ≤ threshold')],
            width=290, name='magnetogram:selection')
        self.threshold = Spinner(title='Threshold [G]', low=0, value=3., step=.5, width=290,
                                 name='magnetogram:threshold')
        self.fill = TextInput(title='Removed-pixel value (number or NaN)', value='0.0', width=290,
                              name='magnetogram:fill')
        self.mode = Select(title='Simulation magnetic map', value='bottom',
            options=[('bottom', 'Bottom layer (shared map)'), ('per_height_pair', 'Separate map at each selected height')],
            width=290, name='magnetogram:mode')
        self.magnetic_variable = TextInput(title='Simulation magnetic variable (blank: automatic)',
            value='', width=290, name='magnetogram:observable')
        self.h1 = Spinner(title='h1 height index', low=0, value=2, step=1, width=145,
                          name='magnetogram:h1')
        self.h2 = Spinner(title='h2 height index', low=0, value=4, step=1, width=145,
                          name='magnetogram:h2')
        self.dt = Spinner(title='Cadence [s]', low=.00001, value=11.88, step=.01, width=145,
                          name='magnetogram:dt')
        self.dx = Spinner(title='Pixel scale [Mm]', low=.00001, value=.43, step=.001, width=145,
                          name='magnetogram:dx')
        self.dz = Spinner(title='Observational height separation [km]', low=0, value=168., step=1, width=290,
                          name='magnetogram:dz')
        self.frame_label = Div(text='Frame', name='magnetogram:frame_label', width=500)
        self.frame = Slider(title='', start=0, end=1, value=0, step=1, width=500,
                            disabled=True, show_value=False, name='magnetogram:frame')
        self.channel = Select(title='Displayed Dopplergram / magnetic map', value='1',
            options=[('1', 'First diagnostic / h1'), ('2', 'Second diagnostic / h2')], width=290,
            name='magnetogram:channel')
        self.retry = Button(label='Recalculate', width=180, name='magnetogram:retry')
        self.reset = Button(label='Restore magnetogram defaults', width=290, name='magnetogram:reset')
        # Keep processing-result handoff disabled until a current validated worker
        # result exists
        self.launch_state = ColumnDataSource(dict(url=['']), name='magnetogram:launch_state')
        self.launch = Button(label='Open Gaussian & Models Filter Tool', button_type='primary',
            disabled=True, width=350, height=45, name='magnetogram:launch')
        self.launch.js_on_click(CustomJS(args=dict(state=self.launch_state), code="""
            const url = state.data.url[0];
            if (url) window.open(url, '_blank', 'noopener');
        """))
        # Create persistent original/filtered/magnetic/phase image sources and native
        # color mappers
        self.sources = {name: ColumnDataSource(self._empty(), name='magnetogram:' + name)
                        for name in ('original', 'filtered', 'magnetic', 'komega')}
        self.velocity_mapper = LinearColorMapper(palette=Greys256, low=-1., high=1., nan_color='#aaaaaa')
        magnetic_palette = [to_hex(colormaps['RdBu_r'](v)) for v in np.linspace(0., 1., 256)]
        self.magnetic_mapper = LinearColorMapper(palette=magnetic_palette, low=-3., high=3., nan_color='#aaaaaa')
        self.phase_mapper = LinearColorMapper(palette=PHASE_PALETTE, low=-80., high=80., nan_color='#aaaaaa')
        self.original_plot = self._plot('Unfiltered Dopplergram slice', 'original', self.velocity_mapper)
        self.filtered_plot = self._plot('Filtered dopplergram slice [cm/s]', 'filtered', self.velocity_mapper)
        self.magnetic_plot = self._plot('Magnetogram — retained pixels [G]', 'magnetic', self.magnetic_mapper)
        self.komega_plot = self._plot('Recalculated k–ω phase difference', 'komega', self.phase_mapper, width=490)
        self.komega_plot.x_range, self.komega_plot.y_range = Range1d(0., 7.), Range1d(0., 10.)
        self.komega_plot.xaxis.axis_label, self.komega_plot.yaxis.axis_label = 'kₕ [Mm⁻¹]', 'ν [mHz]'
        self.komega_plot.add_layout(ColorBar(color_mapper=self.phase_mapper, title='Δφ [deg]'), 'right')
        self.magnetic_plot.add_layout(ColorBar(color_mapper=self.magnetic_mapper, title='B [G]'), 'right')
        self.velocity_colorbars = []
        for plot in (self.original_plot, self.filtered_plot):
            bar = ColorBar(color_mapper=self.velocity_mapper, title='v [cm/s]', width=16)
            plot.add_layout(bar, 'right')
            self.velocity_colorbars.append(bar)
        for plot in (self.filtered_plot, self.magnetic_plot):
            plot.x_range = self.original_plot.x_range
            plot.y_range = self.original_plot.y_range
        for widget in (self.selection, self.threshold, self.fill, self.mode, self.magnetic_variable,
                       self.h1, self.h2, self.dt, self.dx, self.dz, self.channel, self.reset):
            widget.width = 390
        self.parameters = column(self.selection, self.threshold, self.fill, self.mode, self.magnetic_variable,
            self.h1, self.h2, self.dt, self.dx, self.dz, self.channel, self.reset,
            spacing=10, width=410, name='magnetogram:controls')
        plots = (self.original_plot, self.filtered_plot, self.magnetic_plot, self.komega_plot)
        for plot in plots:
            plot.width = 680
            plot.min_width = 0
            plot.sizing_mode = 'fixed'
            plot.title.text_font_size = '11pt'
        # Arrange native plots and retain their physical aspect ratios for browser
        # presentation
        self.plot_aspects = ColumnDataSource(dict(ratio=[1., 1., 1., 1.]),
                                            name='magnetogram:display_aspects')
        self.plot_grid = GridBox(children=[(plot, index//2, index%2)
                                          for index, plot in enumerate(plots)],
                                 spacing=18, name='magnetogram:plots')
        remove_plot_legends(plots)
        from vesa_support import support_module
        self.frame_control = support_module('numeric_controls').ExactSlider(self.frame, 'frame', hard_bounds=True, integer=True)
        self.frame.width = 385
        self.layout = column(Div(text='<h1>Magnetogram Dopplergram Filter</h1>'),
            self.file_selector.layout, self.status,
            self.parameters, row(self.launch, self.retry), column(self.frame_label, self.frame_control.layout, spacing=0),
            self.plot_grid, sizing_mode='stretch_width', styles={'padding': '12px'},
            name='magnetogram:workspace')
        # Install the existing responsive layout script without resizing scientific data
        # coordinates
        doc.js_on_event(DocumentReady, CustomJS(args=dict(plots=list(plots),
            grid=self.plot_grid, aspects=self.plot_aspects), code="""
            let generation = 0;
            const resize = () => {
                const available = Math.max(280, window.innerWidth - 48);
                const columns = available >= 1000 ? 2 : 1;
                const width = Math.floor((available - (columns - 1) * 18) / columns);
                const children = plots.map((plot, i) => [plot, Math.floor(i/columns), i%columns]);
                if (grid.children.some((item, i) => item[1] !== children[i][1] || item[2] !== children[i][2]))
                    grid.children = children;
                for (const plot of plots) {
                    if (plot.width !== width) { plot.width = width; plot.height = width; }
                }
                const current = ++generation;
                let remaining = 24;
                const fit = () => {
                    if (current !== generation) return;
                    for (let i = 0; i < plots.length; i++) {
                        const plot = plots[i];
                        // Measure the actual frame after Bokeh allocates titles,
                        // axes, colorbars and toolbars. Never resize data ranges.
                        if (!(plot.inner_width > 0 && plot.inner_height > 0) ||
                            Math.abs(plot.outer_width - width) > 1) continue;
                        const ratio = aspects.data.ratio[i];
                        const height = Math.round(plot.outer_height + plot.inner_width / ratio - plot.inner_height);
                        if (Math.abs(plot.height - height) > 1) plot.height = Math.max(180, height);
                    }
                    if (--remaining > 0) requestAnimationFrame(fit);
                };
                requestAnimationFrame(fit);
            };
            resize();
            window.addEventListener('resize', resize);
            aspects.properties.data.change.connect(resize);
        """))
        doc.add_root(self.layout)
        doc.title = 'Magnetogram Dopplergram & k–ω Filter'
        # Wire dataset, physical-state, frame/channel, reset, and explicit recalculation
        # handlers
        self.selector.on_change('value', self._select)
        for widget in (self.selection, self.threshold, self.fill, self.mode, self.magnetic_variable, self.h1, self.h2, self.dt, self.dx, self.dz):
            widget.on_change('value', self._science_changed)
        self.frame.on_change('value', self._display_changed)
        self.channel.on_change('value', self._display_changed)
        self.retry.on_click(self._schedule)
        self.reset.on_click(self._reset)
        if records and schedule_initial:
            self.selector.value = [records[0].id]
        elif not records:
            self._status('No original Dopplergram datasets found. Configure the raw/simulation roots; '
                         'saved k–ω FITS diagrams cannot reconstruct the original Dopplergram or magnetogram.', True)

    @staticmethod
    def _empty():
        '''
        Purpose
        -------
        Construct a NaN placeholder for a Bokeh image source.

        Inputs
        ------
        None

        Outputs
        -------
        data: dict
            One 2x2 missing image and unit placeholder extent.
        '''

        # Construct a NaN placeholder for a Bokeh image source
        return dict(image=[np.full((2, 2), np.nan)], x=[0.], y=[0.], dw=[1.], dh=[1.])

    def _plot(self, title, name, mapper, width=340):
        '''
        Purpose
        -------
        Build an image plot backed by one named persistent workspace source.

        Inputs
        ------
        title: str
            Displayed plot title.
        name: str
            Workspace source key and stable plot-name suffix.
        mapper: bokeh.models.LinearColorMapper
            Native palette, range limits, missing color, and optional out-of-range
            colors.
        width: int
            Initial plot width in pixels.

        Outputs
        -------
        plot: bokeh.models.Plot
            Native x/y image plot with the supplied mapper; physical source data are
            populated later.
        '''

        # Build an image plot backed by one named persistent workspace source
        plot = figure(title=title, width=width, height=490, tools='pan,wheel_zoom,box_zoom,reset,save',
                      x_axis_label='x [Mm]', y_axis_label='y [Mm]', name='magnetogram:plot:' + name)
        plot.grid.visible = False
        plot.image(image='image', x='x', y='y', dw='dw', dh='dh', source=self.sources[name], color_mapper=mapper)
        return plot

    def _status(self, text, error=False):
        '''
        Purpose
        -------
        Publish escaped workspace status text with an optional error accent.

        Inputs
        ------
        text: str
            Plain status or error explanation.
        error: bool
            Use error styling when True.

        Outputs
        -------
        None
            Replaces the status Div HTML safely for plain text input.
        '''

        # Publish escaped workspace status text with an optional error accent
        self.status.text = '<p' + (' style="color:#991b1b"' if error else '') + '>' + escape(text) + '</p>'

    def _search(self, attr, old, new):
        '''
        Purpose
        -------
        Refresh dataset search labels without changing the selected canonical identity.

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
            Delegates to the shared FileSelector presentation helper.
        '''

        # Refresh dataset search labels without changing the selected canonical identity
        self.file_selector.refresh()

    def _select(self, attr, old, new):
        '''
        Purpose
        -------
        Apply one valid canonical dataset selection and reset stale processing displays.

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
            Restores mode-specific defaults under callback suppression, clears old
            arrays, and schedules the selected dataset calculation.
        '''

        # Apply one valid canonical dataset selection and reset stale processing
        # displays
        if self._suppress or not new:
            return
        identity = next((item for item in new if item not in old), new[-1])
        if identity not in self.catalog:
            self._status('The selected dataset is unavailable.', True)
            return
        self._suppress = True
        try:
            self.selector.value = [identity]
            self.current = self.catalog[identity]
            self._set_defaults()
            self.frame.value = 0
        finally:
            self._suppress = False
        self.prepared = self.result = None
        self.prepared_arrays = self.result_arrays = {}
        for source in self.sources.values():
            source.data = self._empty()
        self.frame.disabled = True
        self._schedule()

    def _set_defaults(self):
        '''
        Purpose
        -------
        Populate magnetic and source-specific input controls from the current dataset
        defaults.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Shows simulation height/magnetic-variable controls or observational sampling
            controls as appropriate.
        '''

        # Populate magnetic and source-specific input controls from the current dataset
        # defaults
        values = defaults(self.config_file, self.current.source_type)
        self.selection.value, self.threshold.value = values['selection'], values['threshold_G']
        self.fill.value = str(values['fill_value'])
        simulation = self.current.source_type == 'single_cube'
        self.mode.visible = self.magnetic_variable.visible = self.h1.visible = self.h2.visible = simulation
        self.dt.visible = self.dx.visible = self.dz.visible = not simulation
        self.mode.value = values['mode'] if simulation else 'bottom'
        self.magnetic_variable.value = values['observable']
        if simulation:
            self.h1.value, self.h2.value = self.current.inputs['h1'], self.current.inputs['h2']
        else:
            self.dt.value, self.dx.value = self.current.inputs['dt'], self.current.inputs['p_dx_Mm']
            self.dz.value = self.current.inputs['delta_z_km']

    def _reset(self):
        '''
        Purpose
        -------
        Restore current dataset defaults and schedule one recalculation.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Suppresses intermediate callbacks and does nothing without a selected
            dataset.
        '''

        # Restore current dataset defaults and schedule one recalculation
        if self.current is None:
            return
        self._suppress = True
        try:
            self._set_defaults()
        finally:
            self._suppress = False
        self._schedule()

    def current_parameters(self):
        '''
        Purpose
        -------
        Read and validate accepted magnetic-filter settings from current controls.

        Inputs
        ------
        None

        Outputs
        -------
        parameters: dict
            Selection, threshold in G, fill value, dataset/simulation mode, and optional
            magnetic observable.
        '''

        # Read and validate accepted magnetic-filter settings from current controls
        return validate_parameters(dict(selection=self.selection.value, threshold_G=self.threshold.value,
            fill_value=self.fill.value, mode='dataset' if self.current.source_type == 'paired_cubes' else self.mode.value,
            observable='' if self.current.source_type == 'paired_cubes' else self.magnetic_variable.value))

    def current_inputs(self):
        '''
        Purpose
        -------
        Read current original sampling/height settings without modifying the dataset
        defaults.

        Inputs
        ------
        None

        Outputs
        -------
        inputs: dict
            Copied mode-specific inputs with validated integer simulation height indices
            or current observational cadence/pixel scale/separation.
        '''

        # Read current original sampling/height settings without modifying the dataset
        # defaults
        inputs = dict(self.current.inputs)
        if self.current.source_type == 'single_cube':
            for key, widget in (('h1', self.h1), ('h2', self.h2)):
                if widget.value is None or int(widget.value) != widget.value or widget.value < 0:
                    raise ValueError('Simulation heights must be nonnegative integer indices.')
                inputs[key] = int(widget.value)
        else:
            inputs.update(dt=self.dt.value, p_dx_Mm=self.dx.value, delta_z_km=self.dz.value)
        return inputs

    def _science_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Schedule recalculation after an unsuppressed physical-input edit.

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
            Display-only frame/channel edits use a separate callback.
        '''

        # Schedule recalculation after an unsuppressed physical-input edit
        if not self._suppress:
            self._schedule()

    def _schedule(self):
        '''
        Purpose
        -------
        Invalidate stale outputs, validate controls, and debounce the newest
        process-worker request.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Clears invalid launch state/results, cancels cancellable work, and schedules
            one request after 250 ms; invalid inputs display an error.
        '''

        # Invalidate stale outputs, validate controls, and debounce the newest
        # process-worker request
        if self.current is None or self._closed:
            return
        self._generation += 1
        self._queued_request = None
        self.launch.disabled = True
        self.launch_state.data = dict(url=[''])
        self.result = None
        self.result_arrays = {}
        for name in ('filtered', 'magnetic', 'komega'):
            self.sources[name].data = self._empty()
        if self._pending is not None:
            self.doc.remove_timeout_callback(self._pending)
            self._pending = None
        if self._future is not None:
            self._future.cancel()
        try:
            parameters, inputs = self.current_parameters(), self.current_inputs()
        except (ValueError, TypeError, OverflowError) as exc:
            self._status(str(exc), True)
            self._pending = None
            return
        self._status('Updating magnetogram filtering and k–ω…')
        generation = self._generation
        self._pending = self.doc.add_timeout_callback(
            lambda: self._start(generation, self.current, parameters, inputs), 250)

    def _start(self, generation, dataset, parameters, inputs):
        '''
        Purpose
        -------
        Submit one current calculation or retain it as the replaceable latest queued
        request.

        Inputs
        ------
        generation: int
            Request generation captured before background work; stale generations are
            ignored.
        dataset: DopplerDataset
            Original observational pair or simulation cube selection with canonical
            identity.
        parameters: dict
            Validated physical filtering parameters with their native units.
        inputs: dict
            Mode-specific original sampling, observable, and selected-height settings.

        Outputs
        -------
        None
            Runs process_dataset outside the document and accepts only a live matching
            request generation.
        '''

        # Submit one current calculation or retain it as the replaceable latest queued
        # request
        self._pending = None
        if generation != self._generation or self._closed:
            return
        if self._future is not None and not self._future.done():
            self._queued_request = (generation, dataset, parameters, inputs)
            return
        future = COMPUTE_POOL.submit(process_dataset, dataset, parameters, inputs,
                                     self.config_file, self.store.root)
        self._future = future

        def done(completed):
            '''
            Purpose
            -------
            Schedule document-thread acceptance of a completed process-worker
            calculation.

            Inputs
            ------
            completed: concurrent.futures.Future
                Completed worker future returning aligned-input and final-result
                identifiers.

            Outputs
            -------
            None
                Closed sessions ignore completion.
            '''

            # Schedule document-thread acceptance of a completed process-worker
            # calculation
            if self._closed:
                return
            def accept():
                '''
                Purpose
                -------
                Accept current worker identifiers and then launch any newest queued
                calculation.

                Inputs
                ------
                None

                Outputs
                -------
                None
                    Clears the tracked future, loads valid results, or displays the
                    worker error; stale results do not replace current state.
                '''

                # Accept current worker identifiers and then launch any newest queued
                # calculation
                if self._closed:
                    return
                if self._future is completed:
                    self._future = None
                if generation == self._generation:
                    try:
                        prepared_id, result_id = completed.result()
                        self.accept_result(prepared_id, result_id)
                    except Exception as exc:
                        self._status('Could not filter this dataset: ' + str(exc), True)
                queued, self._queued_request = self._queued_request, None
                if queued is not None and queued[0] == self._generation:
                    self._start(*queued)
            self.doc.add_next_tick_callback(accept)
        future.add_done_callback(done)

    def accept_result(self, prepared_id, result_id):
        # These immutable products were fully validated by the completed worker.
        '''
        Purpose
        -------
        Load validated published manifests/arrays and enable the exact processing-result
        handoff.

        Inputs
        ------
        prepared_id: str
            Aligned-input cache identifier validated by the completed worker.
        result_id: str
            Final magnetic-filter result identifier validated by the completed worker.

        Outputs
        -------
        None
            Memory-maps result arrays read-only, updates phase/slice displays, and
            constructs the integrated workspace result URL.
        '''

        self.prepared, self.result = self.store.manifest(prepared_id), self.store.manifest(result_id)
        self.prepared_arrays = {name: np.load(self.store.directory(prepared_id)/(name+'.npy'), mmap_mode='r',
                                             allow_pickle=False) for name in self.prepared['arrays']}
        self.result_arrays = {name: np.load(self.store.directory(result_id)/(name+'.npy'), mmap_mode='r',
                                           allow_pickle=False) for name in self.result['arrays']}
        # Set frame limits from accepted filtered cubes without triggering intermediate
        # display updates
        self._suppress = True
        try:
            self.frame.end = max(1, self.result_arrays['dopplergram_v1'].shape[0] - 1)
            self.frame.value = min(self.frame.value, self.frame.end)
            self.frame.disabled = False
        finally:
            self._suppress = False
        data = self.result_arrays
        x, xe = axis_limits(data['kh'])
        y, ye = axis_limits(data['nu'])
        self.sources['komega'].data = dict(image=[data['komega'].T], x=[x], y=[y], dw=[xe-x], dh=[ye-y])
        self.komega_plot.x_range.start, self.komega_plot.x_range.end = 0., 7.
        self.komega_plot.y_range.start, self.komega_plot.y_range.end = 0., 10.
        self._display_changed(None, None, None)
        # Enable the integrated filter/model tool only for this exact published result
        # identifier
        url = '/integrated_komega_bokeh_app?' + urlencode({'result': result_id})
        self.launch_state.data = dict(url=[url])
        self.launch.disabled = False
        if np.isfinite(data['komega']).any():
            kind = 'Simulation' if self.current.source_type == 'single_cube' else 'Observed'
            self.status.text = (f'<p><b>Selected:</b> {kind} Magnetogram Filter and Recalculated k–ω Done.'
                                '<br>Open the Gaussian tool to apply Gaussian filtering next.</p>')
        else:
            self._status('The filtered cubes produced no finite phase values. The native FFT propagates NaNs; '
                         'check the source data and removed-pixel value.', True)

    def _display_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Refresh the selected frame/channel's original, filtered, and retained-magnetic
        maps.

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
            Applies display-only orientation flips, native physical extents, and finite
            color ranges; does not repeat filtering or FFTs.
        '''

        # Refresh the selected frame/channel's original, filtered, and retained-magnetic
        # maps
        if self._suppress or not self.prepared_arrays:
            return
        index, channel = int(self.frame.value), self.channel.value
        original = self.prepared_arrays['original_v' + channel][index]
        self.frame_label.text = f'Frame {index}:  t = {self.prepared_arrays["time_seconds"][index]:g} sec'
        x, y = self.prepared_arrays['x_mm'], self.prepared_arrays['y_mm']
        dx, dy = abs(x[1]-x[0]), abs(y[1]-y[0])
        def oriented(image):
            '''
            Purpose
            -------
            Orient a spatial display copy consistently with native x/y coordinate
            direction.

            Inputs
            ------
            image: np.ndarray
                Native (ny,nx) frame array before display orientation.

            Outputs
            -------
            image: np.ndarray
                View with reversed rows/columns only when the corresponding physical
                axis descends.
            '''

            # Orient a spatial display copy consistently with native x/y coordinate
            # direction
            return image[::(-1 if y[-1] < y[0] else 1), ::(-1 if x[-1] < x[0] else 1)]
        shape = original.shape
        # Compute image-cell edges from native spatial coordinates and preserve physical
        # aspect ratio
        geometry = dict(x=[min(x)-.5*dx], y=[min(y)-.5*dy], dw=[shape[1]*dx], dh=[shape[0]*dy])
        aspect = geometry['dw'][0] / geometry['dh'][0]
        self.plot_aspects.data = dict(ratio=[aspect, aspect, aspect, 1.])
        self.sources['original'].data = dict(geometry, image=[oriented(original)])
        units = self.prepared['metadata']['coordinates']['dopplergram_units']
        self.original_plot.title.text = 'Unfiltered Dopplergram slice [' + units + ']'
        self.filtered_plot.title.text = 'Filtered dopplergram slice [cm/s]'
        for bar in self.velocity_colorbars:
            bar.title = 'v [' + units + ']'
        images = [original]
        # Show retained magnetic pixels and the selected filtered frame using unchanged
        # numerical arrays
        if self.result_arrays:
            filtered = self.result_arrays['dopplergram_v' + channel][index]
            images.append(filtered)
            magnetic = np.array(self.prepared_arrays['magnetogram_v' + channel][index], copy=True)
            mask = self.result_arrays['removed_mask_v' + channel][index]
            magnetic[mask] = np.nan
            self.sources['filtered'].data = dict(geometry, image=[oriented(filtered)])
            self.sources['magnetic'].data = dict(geometry, image=[oriented(magnetic)])
            finite = np.abs(magnetic[np.isfinite(magnetic)])
            limit = max(1., float(finite.max())) if finite.size else 1.
            self.magnetic_mapper.low, self.magnetic_mapper.high = -limit, limit
        # Share finite velocity color limits between original and filtered frames
        finite = np.concatenate([image[np.isfinite(image)] for image in images])
        low, high = (float(finite.min()), float(finite.max())) if finite.size else (-1., 1.)
        if low == high:
            low, high = low - 1., high + 1.
        self.velocity_mapper.low, self.velocity_mapper.high = low, high
        self.original_plot.x_range.start, self.original_plot.x_range.end = min(x)-.5*dx, max(x)+.5*dx
        self.original_plot.y_range.start, self.original_plot.y_range.end = min(y)-.5*dy, max(y)+.5*dy

    def _destroyed(self, context):
        '''
        Purpose
        -------
        Invalidate pending results and cancel cancellable work after session closure.

        Inputs
        ------
        context: object
            Bokeh session-destruction context supplied by the server.

        Outputs
        -------
        None
            Marks the workspace closed and advances its request generation.
        '''

        # Invalidate pending results and cancel cancellable work after session closure
        self._closed = True
        self._generation += 1
        if self._future is not None:
            self._future.cancel()


def build_document(doc, **kwargs):
    '''
    Purpose
    -------
    Construct the separate magnetogram preprocessing Bokeh document.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    kwargs: dict
        Keyword options forwarded to MagnetogramExplorer, including config/cache roots,
        dataset discovery, and initial scheduling.

    Outputs
    -------
    explorer: MagnetogramExplorer
        Created workspace with its layout attached to doc.
    '''

    # Construct the separate magnetogram preprocessing Bokeh document
    return MagnetogramExplorer(doc, **kwargs)
