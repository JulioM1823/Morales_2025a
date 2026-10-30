'''
Purpose
-------
Embed a lazy spatial phase comparison that shares the integrated workspace current
Gaussian-filtered cubes.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for spatial_phase_explorer.py.

Notes
-----
Lazy embedded spatial phase view sharing the combined tool's live filter state.
'''
# Import the libraries and shared helpers used by this module
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

import numpy as np
from bokeh.events import DocumentReady
from bokeh.layouts import column
from bokeh.models import (Button, ColumnDataSource, CustomJS, Div,
                          HoverTool, Range1d, RangeSlider, Slider)
from bokeh.plotting import figure

from bokeh_ui_helpers import (phase_color_mapper, phase_color_bar, style_phase_plot,
                              CollapsibleSection, visibility_toggle)
from spatial_phase_analysis import (DEFAULT_BAND_MHZ, DEFAULT_CONTOUR_SIGMA_MM,
                                    CONTOUR_COVERAGE_LEVEL, contour_lines, magnetic_selection,
                                    ordered_spectrum, prepare_inputs)

SPATIAL_POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='spatial-phase')


class SpatialPhaseExplorer:
    '''
    Purpose
    -------
    Share native raw/filtered spatial phase maps and diagnostic magnetic contours with
    an owning workspace.

    Inputs
    ------
    owner: object
        Owning workspace exposing the document, selected dataset/model, and shared
        controls used here.

    Outputs
    -------
    explorer: SpatialPhaseExplorer
        Lazy source-versioned spatial analysis, independent band selection, visibility
        controls, and plot/numerical export state.
    '''

    def __init__(self, owner):
        '''
        Purpose
        -------
        Create spatial controls, paired plots, sources, and generation-safe background
        state.

        Inputs
        ------
        owner: object
            Owning workspace exposing the document, selected dataset/model, and shared
            controls used here.

        Outputs
        -------
        None
            Builds inactive/empty maps, exact frequency/magnetic controls, presentation
            callbacks, and session-close behavior without loading cubes initially.
        '''

        # Create spatial controls, paired plots, sources, and generation-safe background
        # state
        self.owner,self.doc=owner,owner.doc
        self.data=self.inputs=self.filtered=None
        self._input_key=self._filter_key=None
        self._generations={'input':0,'filter':0}
        self._futures={}
        self._closed=False
        self._suppress=False
        self._closed_callback=lambda context:setattr(self,'_closed',True)
        self.doc.on_session_destroyed(self._closed_callback)
        self.info=Div(sizing_mode='stretch_width',styles={'overflow-wrap':'anywhere'},name='spatial:dataset')
        self.filter_info=Div(sizing_mode='stretch_width',name='spatial:gaussian')
        self.status=Div(sizing_mode='stretch_width',name='spatial:status')
        self.magnetic_info=Div(sizing_mode='stretch_width',name='spatial:magnetic_info')
        # Create exact band and diagnostic magnetic controls before wiring their
        # callbacks
        self.frequency=RangeSlider(title='Frequency band [mHz]',start=0.,end=1.,value=(0.,1.),
            step=.01,disabled=True,sizing_mode='stretch_width',name='spatial:frequency')
        self.strength=Slider(title='Horizontal magnetic-field threshold [G]',start=0.,end=100.,
            value=10.,step=.5,sizing_mode='stretch_width',name='spatial:strength')
        self.inclination=Slider(title='Inclination from either vertical [deg]',start=0.,end=90.,
            value=45.,step=1.,sizing_mode='stretch_width',name='spatial:inclination')
        self.contour_sigma=Slider(title='Contour smoothing σ [Mm]',start=0.,end=3.,
            value=DEFAULT_CONTOUR_SIGMA_MM,step=.1,sizing_mode='stretch_width',name='spatial:contour_sigma')
        from vesa_support import support_module
        ExactSlider = support_module('numeric_controls').ExactSlider
        self.numeric_controls = {key: ExactSlider(widget, key,
            hard_bounds=key in {'frequency', 'inclination'})
            for key, widget in [('frequency', self.frequency), ('strength', self.strength),
                                ('inclination', self.inclination), ('contour_sigma', self.contour_sigma)]}
        for key in ('strength', 'inclination', 'contour_sigma'):
            self.numeric_controls[key].input.width = 72
        self.contour_note=Div(sizing_mode='stretch_width',name='spatial:contour_note')
        self.frequency.on_change('value',self._frequency_changed)
        self.strength.on_change('value',self._magnetic_changed)
        self.inclination.on_change('value',self._magnetic_changed)
        self.contour_sigma.on_change('value',self._magnetic_changed)
        self.save=Button(label='Save Plot',button_type='primary',sizing_mode='stretch_width',name='spatial:save')
        self.save.on_click(self.save_plots)
        self.export_status=Div(sizing_mode='stretch_width',name='spatial:export_status')
        # Build retained raw/filtered phase sources and a shared diagnostic contour
        # source
        self.mapper=phase_color_mapper()
        self.sources=[ColumnDataSource(self.empty(),name='spatial:'+name) for name in ('reference','filtered')]
        self.contours=ColumnDataSource(dict(xs=[],ys=[]),name='spatial:contours')
        self.x_range=Range1d(0.,1.);self.y_range=Range1d(0.,1.)
        self.plots=[]
        for index,title in enumerate(('Unfiltered spatial phase — full positive band','Filtered spatial phase — selected band')):
            plot=figure(title=title,width=470,height=420,frame_width=310,frame_height=310,
                x_range=self.x_range,y_range=self.y_range,x_axis_label='x [Mm]',y_axis_label='y [Mm]',
                tools='pan,wheel_zoom,box_zoom,reset,save',toolbar_location='above',
                output_backend='canvas',name='spatial:plot:'+str(index))
            style_phase_plot(plot)
            image=plot.image(source=self.sources[index],image='image',x='x',y='y',dw='dw',dh='dh',color_mapper=self.mapper)
            plot.add_tools(HoverTool(renderers=[image],tooltips=[('x [Mm]','$x{0.000}'),('y [Mm]','$y{0.000}'),('Phase [deg]','@image{0.00}')]))
            # A light halo keeps regional outlines legible on the native palette.
            plot.multi_line(source=self.contours,xs='xs',ys='ys',line_color='white',line_width=3.)
            plot.multi_line(source=self.contours,xs='xs',ys='ys',line_color='black',line_width=1.4)
            plot.add_layout(phase_color_bar(self.mapper),'right')
            self.plots.append(plot)
        # Compose control and plot visibility sections without preparing numerical
        # inputs yet
        self.controls=column(self.info,
            self.numeric_controls['frequency'].layout,self.filter_info,Div(text='<h3>Magnetic contours</h3>'),
            *[self.numeric_controls[key].layout for key in ('strength', 'inclination', 'contour_sigma')],self.contour_note,
            self.magnetic_info,self.status,self.save,self.export_status,
            sizing_mode='stretch_width',min_width=0,spacing=8)
        self.subplot_toggles = [visibility_toggle((plot,), 'Plot', name=f'spatial:subplot:{i}')
                                for i, plot in enumerate(self.plots)]
        self.plot_sections = [column(Div(text=f'<h3>{title}</h3>'), toggle, plot,
                             sizing_mode='stretch_width', min_width=0)
            for title, toggle, plot in zip(('Unfiltered reference', 'Gaussian-filtered result'),
                                          self.subplot_toggles, self.plots)]
        self.section = CollapsibleSection('Spatial Phase-Difference Analysis', self.controls,
            plots=self.plot_sections, name='spatial:application')
        self.layout=self.section.layout
        self.layout.styles = {'border-top': '1px solid #e2e8f0', 'padding-top': '12px'}
        self.doc.js_on_event(DocumentReady,CustomJS(args=dict(root=self.layout,
            center=owner.middle_section,plots=self.plots),code="""
            const resize = () => {
                const width = Math.max(280, center.width || 280);
                const local = {sync:false};
                for (const plot of plots) {
                    const ratio=(plot.y_range.end-plot.y_range.start)/(plot.x_range.end-plot.x_range.start);
                    const frame_width=Math.max(120,width-160);
                    const frame_height=Math.max(1,Math.round(frame_width*ratio));
                    plot.setv({frame_width, frame_height, width, height:frame_height+110,
                        toolbar_location:width < 550 ? 'right' : 'above'}, local);
                }
            };
            resize(); window.addEventListener('resize',resize);
            plots[0].properties.tags.change.connect(resize);
            center.properties.width.change.connect(resize);
        """))

    @staticmethod
    def empty():
        '''
        Purpose
        -------
        Construct an empty Bokeh image-source payload.

        Inputs
        ------
        None

        Outputs
        -------
        data: dict
            One 1x1 NaN image with unit placeholder geometry.
        '''

        # Construct an empty Bokeh image-source payload
        return dict(image=[np.full((1,1),np.nan)],x=[0.],y=[0.],dw=[1.],dh=[1.])

    def _message(self,text,error=False):
        '''
        Purpose
        -------
        Publish escaped status text with normal or error styling.

        Inputs
        ------
        text: str
            Plain status message escaped before HTML insertion.
        error: bool
            Use the error accent when True.

        Outputs
        -------
        None
            Replaces the status Div text.
        '''

        # Publish escaped status text with normal or error styling
        self.status.text=f'<p style="color:{"#991b1b" if error else "#166534"}">{escape(text)}</p>'

    def _clear_display(self):
        '''
        Purpose
        -------
        Clear spatial maps/contours and disable controls while inputs are unavailable.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Resets sources and dataset/filter/magnetic explanatory labels.
        '''

        # Clear spatial maps/contours and disable controls while inputs are unavailable
        for source in self.sources:
            source.data=self.empty()
        self.contours.data=dict(xs=[],ys=[])
        for widget in (self.frequency,self.strength,self.inclination,self.contour_sigma):
            widget.disabled=True
        for label in (self.info,self.filter_info,self.magnetic_info,self.contour_note):
            label.text=''

    def _cancel(self,kind):
        '''
        Purpose
        -------
        Invalidate one background job category and cancel its queued work if possible.

        Inputs
        ------
        kind: str
            input or filter background-work category.

        Outputs
        -------
        None
            Advances that category's generation and removes its tracked future.
        '''

        # Invalidate one background job category and cancel its queued work if possible
        self._generations[kind]+=1
        future=self._futures.pop(kind,None)
        if future is not None:future.cancel()

    def _work(self,kind,calculate,accept):
        '''
        Purpose
        -------
        Run one category of spatial work and accept only the newest live generation.

        Inputs
        ------
        kind: str
            input or filter background-work category.
        calculate: callable
            Zero-argument calculation performed outside the document callback when
            asynchronous execution is active.
        accept: callable
            Document-thread callback receiving the current calculation result and, where
            supported, its exception.

        Outputs
        -------
        None
            Uses synchronous offline execution or a worker/document-thread publication
            path; stale results are ignored and errors clear the matching state key.
        '''

        # Run one category of spatial work and accept only the newest live generation
        self._cancel(kind)
        generation=self._generations[kind]
        def publish(result=None,error=None):
            '''
            Purpose
            -------
            Publish a current spatial calculation or report its failure.

            Inputs
            ------
            result: object or None
                Completed spatial input or cross-spectrum result.
            error: Exception or None
                Worker exception, or None after a successful calculation.

            Outputs
            -------
            None
                Ignores closed/stale generations, clears failed input/filter keys, and
                otherwise invokes the captured acceptance callback.
            '''

            # Publish a current spatial calculation or report its failure
            if self._closed or generation!=self._generations[kind]:return
            if error is not None:
                if kind=='input':self._input_key=None
                else:self._filter_key=None
                self._message('Spatial analysis unavailable: '+str(error),True)
            else:accept(result)
        if self.doc.session_context is None:
            try:result=calculate()
            except Exception as exc:publish(error=exc)
            else:publish(result)
            return
        future=SPATIAL_POOL.submit(calculate)
        self._futures[kind]=future
        def complete(done):
            '''
            Purpose
            -------
            Collect a worker result and enqueue current-generation document publication.

            Inputs
            ------
            done: concurrent.futures.Future
                Completed background future supplying a result or exception.

            Outputs
            -------
            None
                Closed or cancelled work is ignored; calculation exceptions are
                forwarded as errors.
            '''

            # Collect a worker result and enqueue current-generation document
            # publication
            if self._closed or done.cancelled():return
            try:result,error=done.result(),None
            except Exception as exc:result,error=None,exc
            self.doc.add_next_tick_callback(lambda:publish(result,error))
        future.add_done_callback(complete)

    def sync(self):
        '''
        Purpose
        -------
        Synchronize spatial inputs with the primary workspace's exact selected loaded
        dataset.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Clears stale state while data are missing/loading, prepares newly selected
            raw inputs, and reuses existing input work before syncing filtered cubes.
        '''

        # Synchronize spatial inputs with the primary workspace's exact selected loaded
        # dataset
        primary=self.owner.primary
        data=primary.data
        if (data is None or data.observation.id!=primary.selected_id or
                data.dopplergrams is None or data.analysis_config is None):
            self._cancel('input');self._cancel('filter')
            if self.data is not None or self._input_key is not None:
                self._clear_display()
            self.data=self.inputs=self.filtered=None
            self._input_key=self._filter_key=None
            for widget in (self.frequency,self.strength,self.inclination,self.contour_sigma):
                widget.disabled=True
            pending = primary._loading or primary._load_callback is not None
            self._message('Waiting for the current dataset to finish loading.' if pending else
                          'Spatial analysis requires the selected dataset’s original Dopplergram height pair.')
            return
        if id(data)!=self._input_key:
            self._cancel('filter')
            self.data=data;self.inputs=self.filtered=None
            self._input_key=id(data);self._filter_key=None
            self._clear_display()
            self._message('Preparing the raw full-band reference and magnetic geometry…')
            self._work('input',lambda:prepare_inputs(data),self._accept_inputs)
            return
        if self.inputs is not None:
            self._sync_filtered()

    def _accept_inputs(self,inputs):
        '''
        Purpose
        -------
        Publish raw full-band phase and configure physical axes, band bounds, and
        magnetic availability.

        Inputs
        ------
        inputs: SpatialInputs
            Prepared raw cross spectrum, native Mm coordinates, optional magnetic maps,
            and provenance.

        Outputs
        -------
        None
            Stores native coordinate extents, initializes the frequency selection, and
            requests the current filtered spectrum.
        '''

        # Publish raw full-band phase and configure physical axes, band bounds, and
        # magnetic availability
        self.inputs=inputs
        x,y=inputs.x,inputs.y
        dx,dy=abs(x[1]-x[0]),abs(y[1]-y[0])
        self.x_range.start,self.x_range.end=min(x)-dx/2,max(x)+dx/2
        self.y_range.start,self.y_range.end=min(y)-dy/2,max(y)+dy/2
        self.extent=(self.x_range.start,self.y_range.start,
                     self.x_range.end-self.x_range.start,self.y_range.end-self.y_range.start)
        self.x_range.reset_start,self.x_range.reset_end=self.x_range.start,self.x_range.end
        self.y_range.reset_start,self.y_range.reset_end=self.y_range.start,self.y_range.end
        for plot in self.plots:
            plot.frame_height=round(plot.frame_width*(len(y)*dy)/(len(x)*dx))
            plot.height=plot.frame_height+110
            plot.tags=[len(x),len(y),dx,dy]
        # Display the raw full-positive-frequency reference independently of the
        # editable filtered band
        values,self.reference_band=inputs.reference.band(inputs.reference.full_band)
        self.sources[0].data=self._image(values)
        lo,hi=inputs.reference.full_band
        default=(max(lo,DEFAULT_BAND_MHZ[0]),min(hi,DEFAULT_BAND_MHZ[1]))
        if default[0]>default[1] or not np.any((inputs.reference.frequency_mhz>=default[0])&(inputs.reference.frequency_mhz<=default[1])):
            default=(lo,hi)
        # Set the valid initial band without triggering intermediate map updates
        self._suppress=True
        try:
            # RangeSlider needs distinct limits even for a single positive bin.
            self.frequency.start=lo;self.frequency.end=hi if hi>lo else lo+1e-9
            self.frequency.step=1000./(self.data.dopplergrams[0].shape[0]*self.data.geometry.dt_seconds)
            self.frequency.value=default;self.frequency.disabled=hi==lo
        finally:self._suppress=False
        cfg=self.data.analysis_config['data']
        if cfg['source_type']=='single_cube':
            heights=f"z₁ = {cfg['resolved_h1_km']:g} km; z₂ = {cfg['resolved_h2_km']:g} km"
        else:heights='Observed line pair; absolute formation heights are not supplied'
        self.info.text=('<b>Selected:</b> '+escape(' + '.join(Path(p).name for p in inputs.metadata['files']))+
            '<br>'+escape(heights)+f"<br>Δz = {cfg['resolved_delta_z_km']:g} km"+
            f'<br>Reference: {lo:.4g}–{hi:.4g} mHz, {len(inputs.reference.frequency_mhz)} positive bins')
        # Enable vector-field contours only when native registered magnetic geometry
        # exists
        available=inputs.magnetic is not None
        self.strength.disabled=self.inclination.disabled=self.contour_sigma.disabled=not available
        if available:
            self.strength.end=max(100.,float(np.nanmax(inputs.magnetic[0]))*1.05)
            mag=inputs.metadata['magnetic']
            self.magnetic_info.text=f"First snapshot; lower selected layer z = {mag['height_km']:g} km (index {mag['height_index']}).<br>Contours require both thresholds; they do not alter the data."
        else:self.magnetic_info.text=escape(inputs.metadata['magnetic']['reason'])
        self._magnetic_changed(None,None,None)
        self._sync_filtered()

    def _sync_filtered(self):
        '''
        Purpose
        -------
        Reuse only the exact current Gaussian-filtered cubes supplied by the primary
        workspace.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Waits for matching recalculation parameters when enabled, reuses unfiltered
            cubes when disabled, and schedules a new temporal spectrum only for a
            changed state key.
        '''

        # Reuse only the exact current Gaussian-filtered cubes supplied by the primary
        # workspace
        if self.inputs is None:return
        primary=self.owner.primary
        parameters=primary.filter._current_parameters()
        labels=dict(central_k='Central k₀ [Mm⁻¹]',width_k='FWHM Δk [Mm⁻¹]',
                    central_f='Central ν₀ [mHz]',width_f='FWHM Δν [mHz]')
        self.filter_info.text='<b>Current k–ω Gaussian filter</b><br>'+ '<br>'.join(escape(f'{labels[key]}: {value:g}') for key,value in parameters.items())
        metadata=primary.recalculation_metadata
        current=(metadata or {}).get('recalculation',{}).get('gaussian_parameters')
        cubes=primary.filtered_dopplergrams
        enabled=primary.apply_filter.active
        if not enabled:
            cubes=self.data.dopplergrams
            self.filter_info.text+='<br><b>Gaussian filtering is disabled in k–ω.</b>'
        if cubes is None or (enabled and current!=parameters):
            self._cancel('filter');self._filter_key=None;self.filtered=None
            self.sources[1].data=self.empty()
            self._message('Waiting for the current k–ω Gaussian-filtered Dopplergrams. The raw reference is unchanged.')
            return
        key=(id(self.data),id(cubes),tuple(sorted(parameters.items())) if enabled else ())
        if key==self._filter_key:return
        self._filter_key=key;self.filtered=None
        self.sources[1].data=self.empty()
        self._message('Preparing the filtered temporal cross-spectrum…')
        config=self.data.analysis_config
        self._work('filter',lambda:ordered_spectrum(cubes,config),self._accept_filtered)

    def _accept_filtered(self,spectrum):
        '''
        Purpose
        -------
        Accept the current filtered temporal cross spectrum and refresh its
        selected-band phase.

        Inputs
        ------
        spectrum: TemporalCrossSpectrum
            Cross-spectrum cache of the exact supplied current filtered cubes.

        Outputs
        -------
        None
            Stores the spectrum and applies the current frequency control.
        '''

        # Accept the current filtered temporal cross spectrum and refresh its
        # selected-band phase
        self.filtered=spectrum
        self._frequency_changed(None,None,None)

    def _image(self,values):
        '''
        Purpose
        -------
        Construct a physically registered Bokeh image payload with optional display-axis
        flips.

        Inputs
        ------
        values: np.ndarray
            Native spatial phase array in degrees with (ny,nx) shape.

        Outputs
        -------
        data: dict
            (ny,nx) image and native Mm extent; flips only the display array for
            descending native coordinates.
        '''

        # Construct a physically registered Bokeh image payload with optional
        # display-axis flips
        if self.inputs.x[0]>self.inputs.x[-1]:values=values[:,::-1]
        if self.inputs.y[0]>self.inputs.y[-1]:values=values[::-1,:]
        x,y,dw,dh=self.extent
        return dict(image=[values],x=[x],y=[y],dw=[dw],dh=[dh])

    def _frequency_changed(self,attr,old,new):
        '''
        Purpose
        -------
        Update the filtered spatial map from the complex average over selected frequency
        bins.

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
            Publishes degree-valued phase and exact effective mHz bounds; invalid bands
            clear the filtered image and display an error.
        '''

        # Update the filtered spatial map from the complex average over selected
        # frequency bins
        if self._suppress or self.filtered is None:return
        try:
            values,self.selected_band=self.filtered.band(self.frequency.value)
            self.sources[1].data=self._image(values)
            lo,hi=self.selected_band['effective_mhz']
            correction=' Native line-delay correction included.' if self.filtered.phase_delay_seconds else ''
            self._message(f'Selected {lo:.5g}–{hi:.5g} mHz ({self.selected_band["bin_count"]} FFT bins). '
                'Lower minus higher phase, from the complex band average.'+correction+' Zero-power phase is undefined.')
        except ValueError as exc:
            self.sources[1].data=self.empty();self._message(str(exc),True)

    def _magnetic_changed(self,attr,old,new):
        '''
        Purpose
        -------
        Refresh display-only outlines from the current magnetic thresholds and smoothing
        scale.

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
            Updates physical-coordinate polylines without modifying Dopplergrams or
            phase values.
        '''

        # Refresh display-only outlines from the current magnetic thresholds and
        # smoothing scale
        if self.inputs is None or self.inputs.magnetic is None:
            self.contour_note.text=''
            return
        mask=magnetic_selection(*self.inputs.magnetic,self.strength.value,self.inclination.value)
        x,y=self.inputs.x,self.inputs.y
        if x[0]>x[-1]:x=x[::-1];mask=mask[:,::-1]
        if y[0]>y[-1]:y=y[::-1];mask=mask[::-1,:]
        self.contours.data=contour_lines(mask,x,y,sigma_mm=self.contour_sigma.value)
        self.contour_note.text=(f'Regional outlines: Gaussian σ = {self.contour_sigma.value:g} Mm; '
            f'{100*CONTOUR_COVERAGE_LEVEL:g}% local coverage of the magnetic selection. '
            'Display smoothing only; outlines include neighboring unselected pixels.' if self.contour_sigma.value else 'Native pixel-selection outlines; smoothing disabled.')

    def save_plots(self):
        '''
        Purpose
        -------
        Export current spatial plots, provenance, and unflipped native phase arrays.

        Inputs
        ------
        None

        Outputs
        -------
        paths: tuple of pathlib.Path or None
            HTML/text and numerical NPZ outputs after generation/state validation;
            failures are displayed and return None. Numerical coordinates are saved in
            km and phase maps in degrees.
        '''

        # Export current spatial plots, provenance, and unflipped native phase arrays
        try:
            if self.data is not self.owner.primary.data:
                raise ValueError('The selected dataset changed; wait for its current spatial calculation.')
            key=(id(self.data),id(self.owner.primary.filtered_dopplergrams),
                 tuple(sorted(self.owner.primary.filter._current_parameters().items())))
            if self.owner.primary.apply_filter.active and key!=self._filter_key:
                raise ValueError('The Gaussian state changed; wait for the current spatial calculation.')
            # Require the exact current source/filter/band state before exporting any
            # figures
            if self.inputs is None or self.filtered is None or not np.isfinite(self.sources[1].data['image'][0]).any():
                raise ValueError('Wait for a valid current spatial calculation before saving.')
            from komega_plot_export import save_plot_pair
            metadata=dict(self.inputs.metadata,source_1=dict(id=self.data.observation.id),
                source_2=dict(model_key='spatial_phase'),export_type='spatial_phase',
                reference_band=self.reference_band,selected_band=self.selected_band,
                gaussian_parameters=self.owner.primary.filter._current_parameters(),
                gaussian_enabled=self.owner.primary.apply_filter.active,
                phase_display=dict(palette='CMasher fusion',limits_deg=[self.mapper.low,self.mapper.high],
                    sign_convention='lower * conjugate(higher); positive temporal frequency; + observational phase-delay correction'),
                processing_chain=self.data.metadata.get('processing_chain'),
                magnetic_contours=dict(method='Gaussian-smoothed neighborhood coverage of the unchanged Boolean selection',
                    sigma_Mm=self.contour_sigma.value,coverage_level=CONTOUR_COVERAGE_LEVEL if self.contour_sigma.value else .5),
                magnetic_thresholds=dict(horizontal_G=self.strength.value,inclination_deg=self.inclination.value))
            from output_paths import export_configuration, build_output_file, atomic_npz, register_output
            # Register the effective live Gaussian and spatial-diagnostic settings in
            # the output identity
            cfg=export_configuration(self.data.analysis_config,self.owner.primary.filter._current_parameters(),
                gaussian_enabled=self.owner.primary.apply_filter.active,
                diagnostic_parameters={'spatial_band':self.selected_band,'reference_band':self.reference_band,
                    'magnetic_thresholds':metadata['magnetic_thresholds'],'magnetic_contours':metadata['magnetic_contours']})
            paths=save_plot_pair(self.plots,metadata,self.owner._export_directory_value,config=cfg,product='spatial_phase')
            numerical=build_output_file(cfg['paths']['data_output_dir'],cfg,'spatial_phase','spatial_phase.npz')
            # Save the native maps, before the display's optional axis flips.
            phase,band=self.filtered.band(self.frequency.value)
            reference,_=self.inputs.reference.band(self.inputs.reference.full_band)
            atomic_npz(numerical,phase=phase,reference_phase=reference,x_km=self.inputs.x*1000.,y_km=self.inputs.y*1000.)
            register_output(numerical,cfg,'spatial_phase',extra=metadata)
            paths=(*paths,numerical)
            self.export_status.text='<b>Saved:</b><br>'+'<br>'.join(escape(str(p)) for p in paths)
            return paths
        except Exception as exc:self.export_status.text=escape(str(exc))
