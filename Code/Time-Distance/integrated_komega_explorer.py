'''
Purpose
-------
Compose synchronized native dataset, Gaussian-filter, model, and spatial-phase explorers
in one Bokeh document.

Inputs
------
None

Outputs
-------
IntegratedKomegaExplorer, build_document: callable
    Assemble a shared-state workspace without changing the underlying
    dataset calculations or dispersion solvers.
'''
from __future__ import annotations

# Import native controllers, metadata helpers, and shared presentation tools.
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from hashlib import sha256
from html import escape
import base64
import importlib
import json
from pathlib import Path

import numpy as np
from bokeh.events import DocumentReady
from bokeh.layouts import column, row
from bokeh.models import Button, ColorBar, CustomJS, Div, GridBox, Select, TextInput, Title, Toggle

from gaussian_filter_explorer import CONFIG_FILE, PARAMETER_KEYS, compute_diagram_filter
from komega_explorer import KomegaExplorer, MODEL_TAB_LABELS, _linked_model_class
from komega_plot_export import DEFAULT_EXPORT_DIR, save_plot_pair
from observation_datasets import reproducibility_metadata
from observation_filter_registry import DEFAULT_REGISTRY, gaussian_metadata
from observation_komega_explorer import ObservationKomegaExplorer
from bokeh_ui_helpers import (CollapsibleSection, DispersionControls,
                              batch_model_graph, visibility_toggle,
                              model_graph_update, compact_ui)
from coherence_bokeh import apply_model_visibility, clear_model_visibility, render_model_pixels
from atmospheric_profiles import ProfileError, load_profiles, save_diagnostic
from data_locations import current_source_path


@lru_cache(maxsize=12)
def _profile_image(config_json, heights, folder, source_versions):
    # File versions participate in the cache key, including native supplements.
    '''
    Purpose
    -------
    Cache an exact-source atmospheric diagnostic and encode its saved PNG for display.

    Inputs
    ------
    config_json: str
        JSON-encoded atmospheric configuration; decoded before native profile loading.

    heights: tuple of float
        Selected physical heights in km, also part of the cached profile-image key.

    folder: str or pathlib.Path
        Destination directory for the generated atmospheric diagnostic image.

    source_versions: tuple
        Source path/size/mtime signatures used by lru_cache to invalidate changed native
        profiles; not consumed in the function body.

    Outputs
    -------
    model, snapshot_time_s, encoded_png: tuple
        Profile model name, snapshot time (s), and ASCII base64 PNG. Load the
        provenance-selected profiles and write diagnostic files beneath folder.
    '''

    # Load the exact source configuration and render the selected-height diagnostic.
    profiles = load_profiles(json.loads(config_json))
    outputs = save_diagnostic(profiles, folder, height_pair_km=heights)
    png = next(path for path in outputs if path.suffix == '.png')
    return profiles.model, profiles.provenance['snapshot_time_s'], base64.b64encode(png.read_bytes()).decode('ascii')


def simulation_profile_html(data):
    '''
    Purpose
    -------
    Build the selected simulation's profile display from its exact cube and snapshot
    provenance.

    Inputs
    ------
    data: ObservationData
        Loaded product with phase values ordered (n_kh, n_nu), source metadata, and
        optional analysis configuration.

    Outputs
    -------
    html: str
        Embedded diagnostic/caption HTML, an unavailable/error paragraph, or
        an empty string for non-simulation data. The cached image path may
        generate atmospheric diagnostic files; mismatched provenance is rejected.
    '''
    # Show profiles only for simulation products with available recorded provenance.
    if data.metadata.get('source_type') != 'single_cube':
        return ''
    record = data.metadata.get('atmospheric_parameters')
    if not record or record.get('status') != 'available':
        return '<p>Atmospheric profiles unavailable for this simulation.</p>'
    try:
        # Resolve the saved cube/profile paths before checking the current dataset.
        provenance = record['provenance']
        cube = current_source_path(provenance['cube']['path'])
        profile = current_source_path(provenance['profile']['path'])
        if data.analysis_config is not None:
            selected = data.analysis_config['data']
            selected_cube = selected.get('file') or selected.get('single_cube', {}).get('file')
            if selected_cube and current_source_path(selected_cube) != cube:
                raise ProfileError('Profile provenance does not match the selected simulation cube.')
        from config import default_atmospheric_profiles
        # Reconstruct loader units from configured legacy defaults and recorded source
        # units.
        units = dict(default_atmospheric_profiles['legacy_units'])
        units.update(provenance.get('legacy_units', {}))
        units.update({key: value['unit'] for key, value in provenance['source_units'].items()})
        config = dict(data=dict(file=str(cube)), atmospheric_profiles=dict(
            model_files={record['model']: str(profile)}, legacy_units=units,
            gravity_km_s2=provenance.get('gravity_km_s2', .274),
            co5bold_magnetic_convention=provenance.get('co5bold_magnetic_convention', 'internal')))
        heights = tuple(map(float, record['height_pair_km']))
        # Keep different cubes/snapshots separate even when Model names coincide.
        identity = sha256((str(cube)+'\n'+str(profile)).encode()).hexdigest()[:16]
        from figure_locations import canonical_figure_root
        root = (data.analysis_config or {}).get('paths', {}).get('figure_dir', canonical_figure_root())
        folder = Path(root)/'_atmospheric_profiles'/identity
        # Include native companion profile versions when invalidating the image cache.
        sources = [cube, profile, *sorted(profile.parent.glob(profile.name.replace('_atmos_param.h5', '_*_profile.h5')))]
        versions = tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in sources)
        model, snapshot, encoded = _profile_image(json.dumps(config, sort_keys=True), heights, str(folder), versions)
        # Verify that the rendered model and snapshot match the saved product record.
        if model != record['model'] or snapshot != provenance['snapshot_time_s']:
            raise ProfileError('Profile Model or snapshot does not match the selected diagram.')
        caption = (f'{model} · snapshot t = {snapshot:g} s · '
                   f'black dots: z = {heights[0]/1000:g} and {heights[1]/1000:g} Mm')
        return ('<figure style="margin:16px 0 8px;min-width:0"><figcaption style="margin-bottom:8px;overflow-wrap:anywhere">'
                + escape(caption) + '</figcaption><div style="overflow-x:auto;max-width:100%">'
                + f'<img alt="{escape(caption, quote=True)}" '
                + f'src="data:image/png;base64,{encoded}" '
                + 'style="display:block;width:100%;min-width:1000px;height:auto"></div></figure>')
    # Render escaped provenance/loading failures in the information panel.
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return '<p>Atmospheric profiles unavailable: '+escape(str(exc))+'</p>'


def sampling_html(pairs):
    '''
    Purpose
    -------
    Render current native sampling controls and simulation provenance in an expandable
    information panel.

    Inputs
    ------
    pairs: iterable of tuple
        Display-title and DatasetPair entries whose sampling and profile metadata are
        shown.

    Outputs
    -------
    html: str
        Escaped sampling sections for loaded pairs. Include the exact-source
        atmospheric display when available; empty pairs are skipped.
    '''

    # Build one sampling/provenance section for each currently loaded dataset.
    sections = []
    for title, pair in pairs:
        if pair.data is None:
            continue
        entries = ''.join(
            '<div><dt style="color:#475569;font-size:12px">'+escape(widget.title)
            + f'</dt><dd style="margin:3px 0 0;font-size:16px">{widget.value:g}</dd></div>'
            for widget in pair.sampling.values())
        # Read the accepted sample counts from the native sampling controls.
        nx, ny, nt = (int(pair.sampling[key].value) for key in ('nx', 'ny', 'nt'))
        sections.append(
            '<section style="padding:14px 0;border-top:1px solid #e2e8f0">'
            + f'<h3 style="margin:0 0 6px">{escape(title)}</h3>'
            + f'<p style="margin:0 0 12px">{nx} × {ny} spatial × {nt} temporal samples</p>'
            + '<dl style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:0">'
            + entries + '</dl>' + simulation_profile_html(pair.data) + '</section>')
    return ('<details style="width:100%;max-width:calc(100vw - 48px);min-width:0">'
            + '<summary style="cursor:pointer;padding:8px 0"><b>Extra Information</b></summary>'
            + ''.join(sections) + '</details>')


@dataclass
class WorkspaceState:
    '''
    Purpose
    -------
    Hold the currently synchronized dataset, model, filter, and comparison state.

    Inputs
    ------
    primary_id, secondary_id: str or None
        Canonical dataset identifiers currently selected in each role.

    model_key: str
        Selected dispersion model identifier.

    model_parameters, gaussian_parameters: dict
        Current accepted model and Gaussian control values in their declared units.

    saved_parameters, saved_sampling: dict or None
        Primary dataset registry snapshots, absent until restored or saved.

    left_comparison, right_comparison: bool
        Comparison toggle states synchronized across the two plot columns.

    unfiltered, filtered: dict
        Dataset phase arrays in display order (n_nu, n_kh) and native model result
        objects.

    coherence_enabled, coherence_threshold: bool, float
        Measured-coherence application state and its dimensionless threshold.

    model_gaussian_enabled: bool
        Whether Gaussian transmission weights the theoretical model display.

    Outputs
    -------
    state: WorkspaceState
        Mutable document-local snapshot; dictionaries use independent default
        factories. This container itself does not persist settings to disk.
    '''

    # Keep dataset identity separate from model and filter control snapshots.
    primary_id: str | None = None
    secondary_id: str | None = None
    model_key: str = 'nc2009'
    model_parameters: dict = field(default_factory=dict)
    gaussian_parameters: dict = field(default_factory=dict)
    # Retain the last restored/saved settings for the primary dataset.
    saved_parameters: dict | None = None
    saved_sampling: dict | None = None
    left_comparison: bool = False
    right_comparison: bool = False
    # Hold dataset display arrays and native model results for both columns.
    unfiltered: dict = field(default_factory=dict)
    filtered: dict = field(default_factory=dict)
    # Record independent measured-coherence and model-Gaussian display controls.
    coherence_enabled: bool = False
    coherence_threshold: float = 0.
    model_gaussian_enabled: bool = True


class DatasetPair(ObservationKomegaExplorer):
    '''
    Purpose
    -------
    Extend the native dataset explorer with primary/comparison roles and shared
    workspace synchronization.

    Inputs
    ------
    doc: bokeh.document.Document
        Document that owns the explorer models, callbacks, and final layout root.

    owner: IntegratedKomegaExplorer
        Workspace providing shared primary/secondary data, model, filter, and display
        state.

    secondary: bool, optional
        Use the comparison-dataset role when True. Secondary settings do not replace the
        primary global Gaussian parameters.

    **kwargs: object
        ObservationKomegaExplorer constructor options: configuration/registry paths,
        product/raw discovery roots, scheduling and launch context, supplied catalog
        records, explicit input observation, and initial-selection policy.

    Outputs
    -------
    pair: DatasetPair
        Native loader, saved-settings registry, filter, and two phase plots
        connected to the enclosing integrated workspace.
    '''
    def __init__(self, doc, owner, *, secondary=False, **kwargs):
        '''
        Purpose
        -------
        Initialize a dataset pair and adapt native controls and plot styling for the
        integrated workspace.

        Inputs
        ------
        doc: bokeh.document.Document
            Document that owns the explorer models, callbacks, and final layout root.

        owner: IntegratedKomegaExplorer
            Workspace providing shared primary/secondary data, model, filter, and
            display state.

        secondary: bool, optional
            Use the comparison-dataset role when True. Secondary settings do not replace
            the primary global Gaussian parameters.

        **kwargs: object
            ObservationKomegaExplorer constructor options: configuration/registry paths,
            product/raw discovery roots, scheduling and launch context, supplied catalog
            records, explicit input observation, and initial-selection policy.

        Outputs
        -------
        None
            Register native callbacks, enable filtering, and retain saved-parameter
            and sampling snapshots for this dataset role.
        '''

        # Store the role before invoking inherited construction callbacks.
        self.owner, self.secondary = owner, secondary
        self.saved_parameters = None
        self.saved_sampling = None
        # Construct the native dataset loader, filter controls, and source plots.
        super().__init__(doc, **kwargs)
        self.apply_filter.active = True
        prefix = 'secondary' if secondary else 'primary'
        # Distinct names make the two independently searchable browsers explicit.
        for widget in (self.search, self.selector, self.status, self.selected):
            widget.name = widget.name.replace('observations:', prefix + ':')
        # Adapt integrated labels while retaining native controller behavior.
        self.store_button.label = 'Save Filter Parameters'
        self.selector.title = 'Comparison dataset' if secondary else 'Primary observation / simulation'
        for plot in (self.observed_plot, self.result_plot):
            plot.title.text_font_style = 'normal'
            for axis in (plot.xaxis[0], plot.yaxis[0]):
                axis.axis_label_text_font = axis.major_label_text_font = 'Times New Roman'
                axis.axis_label_text_font_style = 'normal'
                axis.axis_label_text_font_size, axis.major_label_text_font_size = '16pt', '12pt'
                axis.major_tick_in, axis.major_tick_out = 8, 0
                axis.minor_tick_in, axis.minor_tick_out = 4, 0

    def _build_layout(self):
        # The integrated layout owns resizing; do not install the legacy layout JS.
        '''
        Purpose
        -------
        Expose the two native phase plots for composition by the integrated layout.

        Inputs
        ------
        None

        Outputs
        -------
        layout: bokeh.models.Column
            Observed/result plots, without installing the legacy layout resize script.
        '''

        return column(self.observed_plot, self.result_plot)

    def _load_settings(self, data):
        '''
        Purpose
        -------
        Restore primary dataset settings while keeping comparison datasets on the shared
        global filter.

        Inputs
        ------
        data: ObservationData
            Loaded product with phase values ordered (n_kh, n_nu), source metadata, and
            optional analysis configuration.

        Outputs
        -------
        parameters, sampling, message, error: tuple
            Filter values, native sample counts/cadence/pixel scale, status text,
            and error flag. Retain primary saved settings when restored from the
            registry.
        '''

        # Clear previous saved snapshots before loading another dataset.
        self.saved_parameters = None
        self.saved_sampling = None
        if self.secondary:
            # Secondary selection must not restore a different global filter.
            return (self.filter.defaults,
                    dict(nx=data.geometry.nx, ny=data.ny, nt=data.geometry.nt,
                         dt_seconds=data.geometry.dt_seconds, dx_Mm=data.geometry.dx_Mm),
                    f'Loaded comparison dataset {data.observation.label}', False)
        # Restore primary settings through the native per-dataset registry path.
        params, sampling, message, error = super()._load_settings(data)
        if message.startswith('Loaded stored parameters'):
            self.saved_parameters = dict(params)
            self.saved_sampling = dict(sampling)
        return params, sampling, message, error

    def _status(self, message, error=False):
        '''
        Purpose
        -------
        Update native status text and synchronize successful saved-setting snapshots.

        Inputs
        ------
        message: str
            Status text displayed by the native controller or by cleared model panels.

        error: bool, optional
            Mark the status as an error when True.

        Outputs
        -------
        None
            Display source filenames, retain saved parameters/sampling after storage,
            and refresh the enclosing workspace state.
        '''

        # Replace friendly labels by the selected source filenames in status text.
        selected = self.catalog.get(getattr(self, 'selected_id', None))
        if selected is not None and not error:
            message = message.replace(selected.label, ' + '.join(path.name for path in selected.files))
        super()._status(message.replace('Store Parameters', 'Save Filter Parameters'), error)
        # Capture the accepted registry snapshot after a successful storage message.
        if message.startswith('Parameters stored'):
            self.saved_parameters = self.filter._current_parameters()
            self.saved_sampling = {key: widget.value for key, widget in self.sampling.items()}
        self.owner.sync_state()

    def _selection_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Delegate dataset selection and refresh the shared filter/state for primary
        changes.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: list of str
            Previously selected canonical dataset identifiers.

        new: list of str
            Updated selector identifiers; the inherited loader retains the newest
            chosen dataset as the single selection.

        Outputs
        -------
        None
            Use the native selection callback, then synchronize the integrated
            workspace.
        '''

        super()._selection_changed(attr, old, new)
        if not self.secondary and self.filter_result is None:
            self.owner.filter_changed()
        self.owner.sync_state()

    def _sampling_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Delegate sampling edits and notify the integrated filter when the primary result
        is unavailable.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: int, float, or None
            Previous spatial/temporal count, cadence (s), or pixel-scale (Mm) value.

        new: int, float, or None
            Updated native sampling value; incomplete numeric edits may be None
            and are validated by the inherited sampling handler.

        Outputs
        -------
        None
            Update native sampling state and invalidate dependent primary calculations.
        '''

        super()._sampling_changed(attr, old, new)
        if not self.secondary and self.filter_result is None:
            self.owner.filter_changed()

    def _perform_load(self, identity, **kwargs):
        '''
        Purpose
        -------
        Complete native dataset loading and align primary model inputs with the selected
        product.

        Inputs
        ------
        identity: str
            Canonical dataset identifier selected in this primary or comparison browser.

        **kwargs: object
            Loader options forwarded to ObservationKomegaExplorer._perform_load:
            loaded_data is an ObservationData or None, and load_error is an
            Exception or None. Without supplied data/error, native loading is synchronous.

        Outputs
        -------
        None
            Set the model comparison grid and atmospheric defaults for a ready primary
            workspace; report a diagram with no finite phase values explicitly.
        '''

        # Complete the inherited load before updating model grids and atmospheric
        # defaults.
        super()._perform_load(identity, **kwargs)
        if not self.secondary and self.owner.ready:
            self.owner.model_workspace.set_comparison_grid(self.data)
        if not self.secondary and self.owner.ready and self.data is not None:
            self.owner.initialize_dataset_models(identity, self.data.metadata.get('atmospheric_parameters'))
        if not self.secondary and self.data is None:
            self.owner.filter_changed()
        if self.data is not None and not np.isfinite(self.data.values).any():
            self._status('The selected diagram contains no finite phase values to display.', error=True)

    def _mark_unsaved(self):
        '''
        Purpose
        -------
        Invalidate recalculation after Gaussian edits and mark the current dataset
        settings unsaved.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Invalidate this pair and, for a ready primary, the comparison pair;
            display the unsaved-filter status when data are loaded.
        '''

        # Invalidate source reconstructions before displaying the unsaved-filter state.
        self._gaussian_unsaved = True
        self._invalidate_recalculation()
        if not self.secondary and self.owner.ready:
            self.owner.secondary._invalidate_recalculation()
        if self.data is not None:
            self._status('Unsaved filter changes for ' + self.data.observation.label
                         + '. Click Save Filter Parameters to save.')

    def _saved_model_context(self):
        '''
        Purpose
        -------
        Record the model visualization controls alongside a processed dataset's saved
        settings.

        Inputs
        ------
        None

        Outputs
        -------
        context: dict or None
            Model key, widget/base parameters and units, selected branch/field,
            Gaussian state, resolution, and warning/reference toggles. Return None
            until processed data and the owner workspace are available.
        '''

        # Require processed data and a ready owner before recording model visualization
        # state.
        if self.data is None or not self.data.metadata.get('processing_chain') or not self.owner.ready:
            return None
        model = self.owner.model
        return dict(role='model visualization; not a Dopplergram preprocessing stage',
                    model=model.definition.key,
                    inputs={key: widget.value for key, widget in model.widgets.items()},
                    units={item.key: item.unit for item in model.definition.parameters},
                    base_configuration=dict(model._base_params),
                    branch=self.owner.branch_select.value, field=model.field_select.value,
                    gaussian_enabled=self.owner.model_gaussian.active,
                    resolution=model.resolution_select.value,
                    mask_numerical_warnings=0 in model.mask_warnings.active,
                    show_fmode=0 in model.show_fmode.active)

    def _refresh_preview(self):
        '''
        Purpose
        -------
        Refresh the native recalculated preview and synchronize the workspace snapshot.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Delegate the native preview path before updating owner state.
        '''

        super()._refresh_preview()
        self.owner.sync_state()

    def filter_changed(self, result):
        '''
        Purpose
        -------
        Route a primary filter result through the shared workspace or delegate the
        native comparison update.

        Inputs
        ------
        result: object
            Native Gaussian controller result supplied by the primary or comparison
            filter.

        Outputs
        -------
        None
            Store the primary filter result and save-button state when ready;
            otherwise use the inherited filter callback.
        '''

        if not self.secondary and self.owner.ready:
            self.filter_result = result
            self.store_button.disabled = self.data is None or result is None
            self.owner.filter_changed()
            return
        super().filter_changed(result)
        if not self.secondary:
            self.owner.filter_changed()


def paired_model_class(vesa):
    '''
    Purpose
    -------
    Create a linked model subclass with one solved result and separate original/weighted
    renderers.

    Inputs
    ------
    vesa: types.ModuleType
        Loaded Vesa Bokeh implementation used to construct the linked model subclass.

    Outputs
    -------
    PairedModel: type
        Model class whose second renderer shares the first calculation and
        applies display weights without an additional dispersion root solve.
    '''
    # Reuse the native linked model implementation for both paired renderers.
    Linked = _linked_model_class(vesa)

    class PairedModel(Linked):
        '''
        Purpose
        -------
        Display one native model calculation in original and Gaussian/coherence-weighted
        views.

        Inputs
        ------
        doc: bokeh.document.Document
            Document that owns the explorer models, callbacks, and final layout root.

        definition: ModelDefinition
            Solver metadata and ordered physical parameter definitions for this model.

        controller: object
            Native model-workspace or dataset-filter controller supplying the shared
            filter and owner.

        Outputs
        -------
        model: PairedModel
            Linked model with a separate filtered renderer and shared plot ranges.
        '''

        def __init__(self, doc, definition, controller):
            '''
            Purpose
            -------
            Initialize both linked renderers and bind the filtered plots to the shared
            physical ranges.

            Inputs
            ------
            doc: bokeh.document.Document
                Document that owns the explorer models, callbacks, and final layout
                root.

            definition: ModelDefinition
                Solver metadata and ordered physical parameter definitions for this
                model.

            controller: object
                Native model-workspace or dataset-filter controller supplying the shared
                filter and owner.

            Outputs
            -------
            None
                Create native and filtered views, clear filtered cache state, and label
                the original and weighted model plot headers.
            '''

            # Create the solving renderer before allocating the separate weighted
            # display.
            super().__init__(doc, definition, controller)
            self.filtered = Linked(doc, definition, controller)
            self.filtered_result = None
            self._filtered_display_key = None
            for plot in [*self.plots, *self.filtered.plots]:
                plot.add_layout(Title(text='Model', text_font_size='14pt', align='left'), 'above')
            # Share the Gaussian preview ranges with every weighted model plot.
            for plot in self.filtered.plots:
                plot.add_layout(Title(text='Gaussian and Coherence Weighted Model',text_font_size='10pt',align='left'),'above')
                plot.x_range = controller.filter.plot.x_range
                plot.y_range = controller.filter.plot.y_range
            self.filtered.shared_x_range = controller.filter.plot.x_range
            self.filtered.shared_y_range = controller.filter.plot.y_range

        def _update_display(self, result):
            '''
            Purpose
            -------
            Render a completed clean model and refresh its paired filtered display.

            Inputs
            ------
            result: DiagramResult
                Completed dispersion result containing phase_deg, vertical-root fields,
                physical grid axes, and the native model diagnostics.

            Outputs
            -------
            None
                Preserve native masking/scaling, mark the original hover values as
                unfiltered, and update shared dispersion-curve visibility.
            '''

            if self._dirty:
                return
            # This is the same native rendering/masking/scaling as the old tool.
            self._render_native(result)
            render_model_pixels(self, result)
            # Mark original model hover samples as unfiltered before refreshing the
            # paired view.
            zeros = np.zeros(result.phase_deg.shape[:2])
            self.hover_source.data = dict(self.hover_source.data, transmission=zeros.ravel(),
                power_transmission=zeros.ravel(), filter_applied=np.full(zeros.size, 'no'))
            self.refresh_filter(result)
            self.controller.owner.curves_updated()

        @batch_model_graph
        def refresh_filter(self, result=None):
            '''
            Purpose
            -------
            Reuse the solved result to refresh Gaussian-weighted fields and coherence
            visibility.

            Inputs
            ------
            result: DiagramResult or None
                Model result to reuse; None selects last_result or clears a dirty
                pending view.

            Outputs
            -------
            None
                Cache by result/control/data identity; scale display phase and kz fields
                by amplitude transmission, retain transmission squared for power hover,
                and apply coherence visibility. Invalid inputs clear the filtered view
                and status; the underlying solver result is not recalculated.
            '''

            # Clear stale weighted pixels while a new solver result is pending.
            if result is None and self._dirty:
                if hasattr(self, 'filtered'):
                    self.filtered_result = self.filtered.last_result = None
                    vesa.ModelExplorer._clear_plot(self.filtered, 'Updating model…')
                    clear_model_visibility(self.filtered)
                return
            result = self.last_result if result is None else result
            if result is None or not hasattr(self, 'filtered'):
                return
            shared = self.controller.filter
            coherence = self.controller.coherence
            try:
                # Key weighted-display reuse by result identity and every relevant
                # display/data setting.
                display_key = (id(result), self.field_select.value, tuple(self.mask_warnings.active),
                    tuple(self.show_fmode.active), shared.geometry,
                    tuple(sorted(shared._current_parameters().items())),
                    id(self.controller.owner.primary.data), id(self.controller.owner.primary.filter_result),
                    self.controller.owner.model_gaussian.active,
                    coherence.apply.active, id(coherence.result), coherence.threshold.value)
            except (ValueError, TypeError):
                display_key = None
            if self._filtered_display_key == display_key and self.filtered_result is not None:
                return
            # Mirror native display controls without triggering a second calculation.
            self.filtered._suppress_callbacks = True
            try:
                self.filtered.field_select.value = self.field_select.value
                self.filtered.mask_warnings.active = list(self.mask_warnings.active)
                self.filtered.show_fmode.active = list(self.show_fmode.active)
            finally:
                self.filtered._suppress_callbacks = False
            try:
                shared = self.controller.filter
                enabled = self.controller.owner.model_gaussian.active
                if (self.controller.owner.primary.data is None or
                        (enabled and self.controller.owner.primary.filter_result is None)):
                    raise ValueError('Filter unavailable. Check the Gaussian inputs and sampling.')
                # Evaluate amplitude transmission on the solved model grid, or use
                # identity weights.
                self.transmission = (compute_diagram_filter(result.kh_mm_inv, result.nu_mhz,
                    shared.geometry, **shared._current_parameters()) if enabled
                    else np.ones(result.phase_deg.shape[:2]))
                if self.transmission.shape != result.phase_deg.shape[:2]:
                    raise ValueError('Filter and model dimensions do not match.')
                transmission = self.transmission[..., None]
                # The Gaussian baseline is identical with coherence on/off.
                # Coherence modifies its visibility, never the solver or phase.
                self.filtered_result = replace(result, phase_deg=result.phase_deg * transmission,
                    kz_real=result.kz_real * transmission, kz_imag=result.kz_imag * transmission)
                self.filtered.last_result = self.filtered_result
                self.filtered._render_native(self.filtered_result)
                self.filtered.hover_source.data = dict(self.filtered.hover_source.data,
                    transmission=self.transmission.ravel(),
                    power_transmission=(self.transmission ** 2).ravel(),
                    filter_applied=np.full(self.transmission.size, 'yes' if enabled else 'no'))
                apply_model_visibility(self.filtered, result, self.controller.coherence, self.transmission)
                self._filtered_display_key = display_key
            # Clear unavailable weighted results and report invalid filter/numerical
            # inputs.
            except (ValueError, FloatingPointError) as exc:
                self._filtered_display_key = None
                self.filtered_result = self.filtered.last_result = None
                self.transmission = None
                vesa.ModelExplorer._clear_plot(self.filtered, str(exc))
                clear_model_visibility(self.filtered)
            self.controller.owner.curves_updated()
            self.controller.owner.sync_state()

        def _parameter_changed(self, key, role, attr, old, new):
            '''
            Purpose
            -------
            Invalidate weighted displays and delegate parameter edits to the native
            model controller.

            Inputs
            ------
            key: str
                Physical parameter identifier whose widget value changed.

            role: str
                Parameter role: diagram-only postprocessing or a dispersion/root
                calculation.

            attr: str
                Changed Bokeh property name accepted by the callback signature.

            old: float or None
                Previous physical parameter value in the units declared by its control.

            new: float or None
                Updated physical parameter value in control units; coalesced programmatic
                updates may pass None because the handler reads the widgets directly.

            Outputs
            -------
            None
                Promote a diagram edit during a pending solve to dispersion handling
                so it uses the new roots; respect callback-suppression guards.
            '''

            if role == 'diagram' and self._dirty and self._pending_callback is not None:
                # A diagram edit during a pending root solve must use those new
                # roots, rather than postprocess the previous parameter set.
                role = 'dispersion'
            if not self._suppress_callbacks and role != 'diagram':
                self.filtered_result = None
                if hasattr(self, 'filtered'):
                    vesa.ModelExplorer._clear_plot(self.filtered, 'Updating model…')
                    clear_model_visibility(self.filtered)
            super()._parameter_changed(key, role, attr, old, new)

        def _clear_plot(self, message):
            '''
            Purpose
            -------
            Clear the original and weighted model views together.

            Inputs
            ------
            message: str
                Status text displayed by the native controller or by cleared model
                panels.

            Outputs
            -------
            None
                Reset filtered result/visibility and synchronize workspace state.
            '''

            super()._clear_plot(message)
            if hasattr(self, 'filtered'):
                self.filtered_result = self.filtered.last_result = None
                vesa.ModelExplorer._clear_plot(self.filtered, message)
                clear_model_visibility(self.filtered)
            self.controller.owner.sync_state()

    return PairedModel


class ModelWorkspace(KomegaExplorer):
    '''
    Purpose
    -------
    Compose the native model controller with paired renderers and the primary dataset's
    filter.

    Inputs
    ------
    doc: bokeh.document.Document
        Document that owns the explorer models, callbacks, and final layout root.

    owner: IntegratedKomegaExplorer
        Workspace providing shared primary/secondary data, model, filter, and display
        state.

    **kwargs: object
        Remaining KomegaExplorer constructor settings, such as config_file,
        schedule_initial, and launch_context. This workspace supplies the shared
        primary filter, paired model factory, and comparison data itself.

    Outputs
    -------
    workspace: ModelWorkspace
        Native model tabs/controller sharing primary sampling, filter, and coherence
        data.
    '''

    def __init__(self, doc, owner, **kwargs):
        '''
        Purpose
        -------
        Initialize the native model workspace with the primary filter and paired-model
        factory.

        Inputs
        ------
        doc: bokeh.document.Document
            Document that owns the explorer models, callbacks, and final layout root.

        owner: IntegratedKomegaExplorer
            Workspace providing shared primary/secondary data, model, filter, and
            display state.

        **kwargs: object
            Remaining KomegaExplorer constructor settings, such as config_file,
            schedule_initial, and launch_context. This workspace supplies the shared
            primary filter, paired model factory, and comparison data itself.

        Outputs
        -------
        None
            Store the owner and delegate model construction with primary comparison
            data.
        '''

        # Supply primary data and filter state to the native paired-model controller.
        self.owner = owner
        super().__init__(doc, shared_filter=owner.primary.filter,
                         model_class_factory=paired_model_class,
                         comparison_data=owner.primary.data, **kwargs)

    def _build_layout(self):
        '''
        Purpose
        -------
        Expose the native model tabs for integration into the shared workspace.

        Inputs
        ------
        None

        Outputs
        -------
        layout: bokeh.models.Column
            Column containing the native tabs container.
        '''

        return column(self.tabs)

    def _coherence_data(self):
        '''
        Purpose
        -------
        Use the primary loaded dataset as the measured-coherence source.

        Inputs
        ------
        None

        Outputs
        -------
        data: ObservationData or None
            Current primary numerical dataset, or None while unavailable.
        '''

        return self.owner.primary.data


class IntegratedKomegaExplorer:
    '''
    Purpose
    -------
    Coordinate primary/comparison datasets, native models, shared Gaussian controls,
    exports, and spatial phase.

    Inputs
    ------
    doc: bokeh.document.Document
        Document that owns the explorer models, callbacks, and final layout root.

    config_file: str or pathlib.Path, optional
        Python configuration supplying dataset paths, sampling, and solver defaults.

    registry_file: str or pathlib.Path, optional
        JSON registry containing saved per-dataset Gaussian and sampling settings.

    product_roots: sequence of paths or None
        Numerical-product directories searched by the primary dataset explorer.

    raw_roots: sequence of paths or None
        Original-input directories searched by the primary dataset explorer.

    export_dir: str or pathlib.Path, optional
        Initial destination shown by the plot-export control.

    launch_context: dict or None
        Validated saved context used to restore the exact selected dataset and model
        inputs.

    schedule_initial: bool, optional
        Let native controllers schedule their initial loading/calculation when True;
        test/offline paths may load synchronously.

    input_observation: Observation or None
        Explicit recorded original-input observation placed first in the primary
        catalog.

    Outputs
    -------
    explorer: IntegratedKomegaExplorer
        Stateful owner of a single Bokeh application root and its synchronized
        controllers.
    '''

    def __init__(self, doc, *, config_file=CONFIG_FILE, registry_file=DEFAULT_REGISTRY,
                 product_roots=None, raw_roots=None, export_dir=DEFAULT_EXPORT_DIR,
                 launch_context=None, schedule_initial=True, input_observation=None):
        '''
        Purpose
        -------
        Construct native component explorers and compose their models into one
        synchronized document.

        Inputs
        ------
        doc: bokeh.document.Document
            Document that owns the explorer models, callbacks, and final layout root.

        config_file: str or pathlib.Path, optional
            Python configuration supplying dataset paths, sampling, and solver defaults.

        registry_file: str or pathlib.Path, optional
            JSON registry containing saved per-dataset Gaussian and sampling settings.

        product_roots: sequence of paths or None
            Numerical-product directories searched by the primary dataset explorer.

        raw_roots: sequence of paths or None
            Original-input directories searched by the primary dataset explorer.

        export_dir: str or pathlib.Path, optional
            Initial destination shown by the plot-export control.

        launch_context: dict or None
            Validated saved context used to restore the exact selected dataset and model
            inputs.

        schedule_initial: bool, optional
            Let native controllers schedule their initial loading/calculation when True;
            test/offline paths may load synchronously.

        input_observation: Observation or None
            Explicit recorded original-input observation placed first in the primary
            catalog.

        Outputs
        -------
        None
            Register controls/callbacks, shared ranges, retained model references,
            spatial analysis, export state, and the final application root. A live
            hidden comparison remains unselected until requested.
        '''

        # Guard callbacks until the full workspace has been constructed.
        self.doc, self.ready = doc, False
        self.state = WorkspaceState()
        self._syncing = False
        self._branches = {}
        self._control_panels = {}
        self._switching_model = False
        common = dict(config_file=config_file, registry_file=registry_file,
                      schedule_initial=schedule_initial)
        # Build the primary dataset/filter controller and remove its temporary root.
        self.primary = DatasetPair(doc, self, product_roots=product_roots,
            raw_roots=raw_roots, launch_context=launch_context, input_observation=input_observation, **common)
        doc.remove_root(self.primary.layout)
        # Reuse the catalog for comparison while preserving deferred live selection.
        self.secondary = DatasetPair(doc, self, secondary=True,
            observations=self.primary.observations,
            select_initial=doc.session_context is None, **common)
        doc.remove_root(self.secondary.layout)
        for plot in (self.secondary.observed_plot, self.secondary.result_plot):
            plot.x_range = self.primary.filter.plot.x_range
            plot.y_range = self.primary.filter.plot.y_range
        # Bind native model controllers to the primary dataset and filter state.
        self.model_workspace = ModelWorkspace(doc, self, config_file=config_file,
            launch_context=launch_context, schedule_initial=schedule_initial)
        doc.remove_root(self.model_workspace.layout)
        atmosphere_info = self.model_workspace.atmosphere_info
        atmosphere_info.visible = bool(atmosphere_info.text)
        atmosphere_info.on_change('text', lambda attr, old, new:
                                 setattr(atmosphere_info, 'visible', bool(new)))
        self._model_dataset_id = self.primary.selected_id if launch_context is not None or self.primary.data is not None else None
        if launch_context is None and self.primary.data is not None and self.primary.data.metadata.get('atmospheric_parameters') is not None:
            self.model_workspace.set_atmospheric_defaults(self.primary.data.metadata.get('atmospheric_parameters'))
        for model in self.model_workspace.models:
            for widget in model.widgets.values():
                widget.on_change('value', lambda attr, old, new: self.sync_state())
        # Create independent model, solution, display-weight, and comparison controls.
        self.model_select = Select(title='Model', value='nc2009',
            options=[(item.definition.key, MODEL_TAB_LABELS[item.definition.key])
                     for item in self.model_workspace.models], width=235, name='integrated:model')
        self.branch_select = Select(title='Model solution', value='0', width=235,
                                    name='integrated:branch')
        self.model_gaussian = Toggle(label='Apply Gaussian to Model', active=True,
            sizing_mode='stretch_width', name='integrated:model_gaussian')
        self.model_gaussian.on_change('active', self._model_gaussian_changed)
        self.left_toggle = Toggle(label='Compare with another dataset', width=250,
                                  name='integrated:left_comparison')
        self.right_toggle = Toggle(label='Compare with another dataset', width=250,
                                   name='integrated:right_comparison')
        self.export_directory = TextInput(title='Plot export directory', value=str(export_dir),
                                          width=280, name='integrated:export_directory')
        self._export_directory_value = str(export_dir)
        # TextInput.value commits on change/blur; value_input follows typing.
        # Saving should honor the directory visibly entered in the field.
        self.export_directory.on_change('value_input', self._export_directory_changed)
        self.export_directory.on_change('value', self._export_directory_changed)
        self.export_status = Div(width=280, styles={'overflow-wrap': 'anywhere'},
                                 name='integrated:export_status')
        self.filter_state = Div(width=280, name='integrated:filter_state')
        self.model_controls = column(width=520, name='integrated:model_controls')
        self.left_plots = GridBox(children=[], spacing=10, name='integrated:left_plots')
        self.right_plots = GridBox(children=[], spacing=10, name='integrated:right_plots')
        # Register export actions for original, filter, and filtered plot pairs.
        self.save_buttons = {}
        for kind in ('unfiltered', 'filter', 'filtered'):
            button = Button(label='Save Plot', button_type='primary', width=180,
                            name=f'integrated:save:{kind}')
            button.on_click(lambda kind=kind: self.save_plot(kind))
            self.save_buttons[kind] = button
        self.model_select.on_change('value', self._model_changed)
        self.branch_select.on_change('value', self._branch_changed)
        self.left_toggle.on_change('active', self._comparison_changed)
        self.right_toggle.on_change('active', self._comparison_changed)
        self.layout = self._build_layout()
        # Keep native figures/sources in the document when their layout slot is
        # showing another solution. Otherwise Bokeh detaches their renderers and
        # serializes them again on return, while the browser can still have
        # asynchronous canvas/view updates referring to the previous objects.
        # CustomJS args retain references without creating hidden layout views.
        # Document-level JS callbacks are serialized, but Bokeh 3.2 does not
        # include their args in doc.models. Anchor these references on the root
        # itself so Python and BokehJS agree about already-known model IDs.
        from spatial_phase_explorer import SpatialPhaseExplorer
        self.spatial = SpatialPhaseExplorer(self)
        # One document and one dataset/filter state. Spatial analysis follows the
        # native parameter section, rather than replacing the entire workspace.
        position = self.middle_section.children.index(self.dispersion_section.layout) + 1
        self.middle_section.children.insert(position, self.spatial.layout)
        self.model_views = CustomJS(args=dict(layouts=[
            layout for model in self.model_workspace.models
            for layout in (model.layout, model.filtered.layout)], callbacks=[
                callback for callbacks in doc.callbacks._js_event_callbacks.values()
                for callback in callbacks]), code='', name='integrated:model_views')
        self.layout.js_on_change('name', self.model_views)
        doc.add_root(self.layout)
        doc.title = 'Integrated k–ω Dataset, Model & Gaussian Filter Explorer'
        self.curves = DispersionControls(self)
        # Apply only to layout/control models; native scientific figures retain
        # their own typography, axes, sizing and rendering configuration.
        compact_ui(self.layout)
        for model in self.model_workspace.models:
            compact_ui(model.controls)
        # Activate callbacks only after all native references and layout sections exist.
        self.ready = True
        self._model_changed('value', None, 'nc2009')
        self.filter_changed()
        self.sync_state()

    @property
    def model(self):
        '''
        Purpose
        -------
        Resolve the native model section selected by the model control.

        Inputs
        ------
        None

        Outputs
        -------
        model: PairedModel
            Existing controller matching the current model key; an unsupported key
            raises StopIteration through the lookup.
        '''

        return next(item for item in self.model_workspace.models
                    if item.definition.key == self.model_select.value)

    def initialize_dataset_models(self, identity, record):
        '''
        Purpose
        -------
        Apply atmospheric model defaults once per primary dataset identity.

        Inputs
        ------
        identity: str
            Canonical dataset identifier selected in the primary browser.

        record: dict or None
            Atmospheric parameter/provenance record associated with the selected
            dataset.

        Outputs
        -------
        None
            Resolve missing per-model initializations, preserve an explicit unavailable
            legacy-simulation record, and refresh model atmosphere/filter displays.
        '''

        # Avoid reinitializing model defaults when the same primary dataset is selected.
        if identity == self._model_dataset_id:
            return
        self._model_dataset_id = identity
        if record is None and self.primary.data.metadata.get('source_type') == 'single_cube':
            record = dict(status='unavailable', parameters={},
                unavailable={'all': 'This legacy simulation product has no saved atmospheric profile metadata.'})
        # Resolve per-model initialization records from the saved atmospheric
        # parameters.
        if record is not None and 'initializations' not in record:
            from komega_bokeh_context import atmospheric_initializations
            from gaussian_filter_explorer import _load_config
            import copy
            record = copy.deepcopy(record)
            record['initializations'], record['fallbacks'] = atmospheric_initializations(
                _load_config(self.primary.config_file), record)
        self.model_workspace.set_atmospheric_defaults(record)
        self.model_workspace.update_atmosphere_info(self.model_select.value)
        self.filter_changed()

    def _browser(self, pair):
        '''
        Purpose
        -------
        Adapt a native dataset browser to the integrated column width.

        Inputs
        ------
        pair: DatasetPair
            Loaded dataset/controller pair used for browser layout or export provenance.

        Outputs
        -------
        layout: bokeh.models.Column
            Searchable file selector and dataset count with stretching controls.
        '''

        pair.file_selector.layout.sizing_mode = 'stretch_width'
        pair.search.width = pair.selector.width = None
        pair.search.sizing_mode = pair.selector.sizing_mode = 'stretch_width'
        return column(pair.file_selector.layout, pair.count, sizing_mode='stretch_width')

    def all_plots(self):
        '''
        Purpose
        -------
        Collect the Gaussian preview, dataset plots, and every original/weighted model
        plot.

        Inputs
        ------
        None

        Outputs
        -------
        plots: list
            Existing figure models; spatial-phase plots are not included in this list.
        '''

        return [self.primary.filter.plot,
                self.primary.observed_plot, self.primary.result_plot,
                self.secondary.observed_plot, self.secondary.result_plot,
                *[plot for model in self.model_workspace.models
                  for plot in [*model.plots, *model.filtered.plots]]]

    def curves_updated(self):
        '''
        Purpose
        -------
        Refresh shared dispersion-curve visibility after a ready model display changes.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Apply curve visibility when the workspace and curve controller exist.
        '''

        if self.ready and hasattr(self, 'curves'):
            self.curves.apply_visibility()

    def _build_layout(self):
        '''
        Purpose
        -------
        Arrange original, shared-filter/control, and weighted views with responsive
        native control layouts.

        Inputs
        ------
        None

        Outputs
        -------
        layout: bokeh.models.Column
            Application header, sampling information, and three workspace sections.
            Register browser-side resize/reflow callbacks on the document.
        '''

        # Create the information panel and independent comparison browser controls.
        self.sampling_info = Div(name='integrated:sampling_info', sizing_mode='stretch_width', min_width=0)
        self.secondary_controls = column(self._browser(self.secondary), self.secondary.status,
                                         sizing_mode='stretch_width')
        self.secondary_browser = column(self.secondary_controls, visible=False,
                                        sizing_mode='stretch_width')
        left_controls = column(self.save_buttons['unfiltered'], self._browser(self.primary),
            self.left_toggle, sizing_mode='stretch_width')
        self.dataset_plot_toggle = visibility_toggle((self.primary.observed_plot,),
            'Dataset Plot', name='integrated:unfiltered:plot_toggle')
        self.left_controls_toggle = visibility_toggle((left_controls,), 'Controls',
            name='integrated:unfiltered:controls_toggle')
        self.secondary_plot_toggle = visibility_toggle((self.secondary.observed_plot,),
            'Comparison Plot', name='integrated:comparison:unfiltered:plot_toggle')
        self.secondary_controls_toggle = visibility_toggle((self.secondary_controls,),
            'Comparison Controls', name='integrated:comparison:controls_toggle')
        self.secondary_visibility = row(self.secondary_plot_toggle, self.secondary_controls_toggle,
            visible=False, sizing_mode='stretch_width')
        self.left_section = column(Div(text='<h2>Unfiltered</h2>'),
            row(self.dataset_plot_toggle, self.left_controls_toggle, sizing_mode='stretch_width'),
            self.secondary_visibility, self.left_plots, left_controls, self.secondary_browser,
            width=460, min_width=0, name='integrated:unfiltered')
        # Bind filter reset and normalize control widths before composing the center
        # section.
        reset = Button(label='Restore filter defaults', sizing_mode='stretch_width')
        reset.on_click(self.primary._reset_filter)
        for widget in [*self.primary.filter.sliders.values(), self.model_workspace.coherence.threshold,
                       self.primary.store_button,
                       self.primary.status, self.filter_state, self.export_directory, self.export_status,
                       self.model_select, self.branch_select, self.model_controls]:
            widget.width = None
            widget.min_width = 0
            widget.sizing_mode = 'stretch_width'
        preview = self.primary.filter.plot
        preview.width, preview.height = 440, 470
        preview.min_width = 0
        preview.title.text = 'Gaussian filter'
        preview.yaxis[0].axis_label = 'ν [mHz]'
        preview.title.text_font_size = '12pt'
        preview.xaxis[0].axis_label_text_font_size = preview.yaxis[0].axis_label_text_font_size = '12pt'
        preview.xaxis[0].major_label_text_font_size = preview.yaxis[0].major_label_text_font_size = '10pt'
        for color_bar in preview.select(type=ColorBar):
            color_bar.title_text_font_size = '10pt'
            color_bar.major_label_text_font_size = '9pt'
            color_bar.width = 16
        preview.toolbar_location = 'above'
        preview.x_range.end, preview.y_range.end = 8., 11.
        # Scalar exact inputs use the same compact width as model parameters.
        # Keep range inputs wider so both committed bounds remain readable.
        for control in [*self.primary.filter.numeric_controls.values(),
                        self.model_workspace.coherence.numeric]:
            control.input.width = 72
            control.slider.width = None
            control.slider.min_width = 40
            control.slider.sizing_mode = 'stretch_width'
        # Arrange exact Gaussian controls separately from native model parameters.
        self.gaussian_controls = GridBox(children=[
            (self.primary.filter.numeric_controls[key].layout, i, 0)
            for i, key in enumerate(PARAMETER_KEYS)], spacing=(8, 12),
            sizing_mode='stretch_width', min_width=0, name='integrated:gaussian_parameters')
        self.gaussian_section = CollapsibleSection('Gaussian Filter',
            self.gaussian_controls, reset,
            name='integrated:gaussian_section', plots=(preview,),
            related=(self.primary.store_button, self.filter_state,
                     self.primary.status, self.save_buttons['filter']))
        self.model_selection = GridBox(children=[(self.model_select, 0, 0),
            (self.branch_select, 0, 1)], spacing=(8, 12), sizing_mode='stretch_width',
            min_width=0, name='integrated:model_selection')
        self.dispersion_section = CollapsibleSection('Dispersion Model Parameters',
            self.model_workspace.atmosphere_info, self.model_selection,
            self.model_gaussian, self.model_controls, name='integrated:dispersion_section',
            plot_grids=(self.left_plots, self.right_plots), comparison=self.left_toggle)
        self.middle_section = column(self.gaussian_section.layout,
            self.model_workspace.coherence.layout,
            self.primary.store_button, self.filter_state, self.primary.status,
            self.dispersion_section.layout,
            self.save_buttons['filter'], self.export_directory, self.export_status, width=460,
            min_width=0, name='integrated:filter')
        for section in (self.model_workspace.coherence.layout, self.dispersion_section.layout):
            section.styles = dict(section.styles, **{'border-top': '1px solid #e2e8f0',
                                                     'padding-top': '12px'})
        # Build the weighted display column with independent dataset/comparison
        # visibility.
        right_controls = column(self.save_buttons['filtered'], self.right_toggle,
                                sizing_mode='stretch_width')
        self.filtered_plot_toggle = visibility_toggle((self.primary.result_plot,),
            'Dataset Plot', name='integrated:filtered:plot_toggle')
        self.right_controls_toggle = visibility_toggle((right_controls,), 'Controls',
            name='integrated:filtered:controls_toggle')
        self.secondary_filtered_toggle = visibility_toggle((self.secondary.result_plot,),
            'Comparison Plot', name='integrated:comparison:filtered:plot_toggle')
        self.secondary_filtered_toggle.visible = False
        self.right_section = column(Div(text='<h2>Filtered</h2>'),
            row(self.filtered_plot_toggle, self.right_controls_toggle, sizing_mode='stretch_width'),
            self.secondary_filtered_toggle, self.right_plots, right_controls,
            width=460, min_width=0, name='integrated:filtered')
        # Compose the three columns and register browser-only responsive reflow.
        workspace = GridBox(children=[(self.left_section, 0, 0),
            (self.middle_section, 0, 1), (self.right_section, 0, 2)], spacing=18,
            name='integrated:workspace')
        self.doc.js_on_event(DocumentReady, CustomJS(args=dict(workspace=workspace,
            left=self.left_section, middle=self.middle_section, right=self.right_section,
            left_grid=self.left_plots, right_grid=self.right_plots, preview=preview), code="""
            let sizing = false;
            const resize = () => {
                if (sizing) return;
                sizing = true;
                try {
                    const available = Math.max(280, window.innerWidth - 48);
                    const desktop = available >= 1100;
                    const center = desktop ? Math.floor((available - 36) * .34) : available;
                    const side = desktop ? Math.floor((available - center - 36) / 2) : available;
                    // Presentation changes must not echo old grid children back
                    // over a newer server-side model/branch selection.
                    const local = {sync: false};
                    left.setv({width: side}, local);
                    right.setv({width: side}, local);
                    middle.setv({width: center}, local);
                    preview.setv({width: center,
                        toolbar_location: center < 400 ? 'right' : 'above'}, local);
                    workspace.setv({children: desktop
                        ? [[left, 0, 0], [middle, 0, 1], [right, 0, 2]]
                        : [[middle, 0, 0], [left, 1, 0], [right, 2, 0]]}, local);
                    for (const grid of [left_grid, right_grid]) {
                        const pair = grid.children.map(item => item[0]);
                        const n = side >= 850 ? 2 : 1;
                        const next = pair.map((plot, i) => [plot, Math.floor(i/n), i%n]);
                        if (grid.children.some((item, i) => item[1] !== next[i][1] || item[2] !== next[i][2]))
                            grid.setv({children: next}, local);
                        for (const plot of pair) {
                            // Native model figures otherwise retain a 340px minimum.
                            plot.setv({min_width: 0,
                                width: Math.floor((side - (n - 1) * 10) / n),
                                height: 470}, local);
                        }
                    }
                } finally { sizing = false; }
            };
            resize(); window.addEventListener('resize', resize);
            left_grid.properties.children.change.connect(resize);
            right_grid.properties.children.change.connect(resize);
        """))
        self.doc.js_on_event(DocumentReady, CustomJS(args=dict(middle=self.middle_section,
            selection=self.model_selection, gaussian=self.gaussian_controls,
            grids=[grid for model in self.model_workspace.models for grid in model.parameter_grids]), code="""
            const reflow = (grid, columns) => {
                const children = grid.children.map((item, i) => [item[0], Math.floor(i / columns), i % columns]);
                if (grid.children.some((item, i) => item[1] !== children[i][1] || item[2] !== children[i][2]))
                    grid.setv({children}, {sync: false});
            };
            const resize = () => {
                const columns = middle.width >= 360 ? 2 : 1;
                for (const grid of grids) reflow(grid, columns);
                reflow(selection, columns);
                reflow(gaussian, middle.width >= 560 ? 2 : 1);
            };
            resize(); middle.properties.width.change.connect(resize);
        """))
        self.komega_view = column(self.sampling_info, workspace, sizing_mode='stretch_width')
        return column(Div(text='<h1 style="margin:0">k–ω Dataset, Model & Gaussian Filter Explorer</h1>',
                          sizing_mode='stretch_width'), self.komega_view,
                      sizing_mode='stretch_width', styles={'padding': '12px'},
                      name='integrated:application')

    @batch_model_graph
    def _model_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Activate the selected native model, restore its branch choice, and mount its
        cached controls/views.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: str or None
            Previously selected dispersion-model key; None is used by the explicit
            initial activation call during construction.

        new: str
            Updated dispersion-model key used to activate its native controller.

        Outputs
        -------
        None
            Update atmosphere/coherence, active controllers, branch options, shared
            ranges, and filtered display while retaining native model references.
        '''

        # Refresh model-specific atmosphere metadata before activating its native
        # controller.
        self.model_workspace.update_atmosphere_info(new)
        if not self.ready:
            return
        self.model_workspace.coherence.sync()
        index = self.model_workspace.models.index(self.model)
        # Retain native selection metadata, then enforce activation explicitly:
        # this layout does not mount the Tabs container and must not depend on
        # its presentation callback being the sole activation path.
        self.model_workspace.tabs.active = index
        for position, model in enumerate(self.model_workspace.models):
            active = position == index
            if model._active != active:
                model.set_active(active)
        # Restore per-model branch choices without recursively handling an intermediate
        # branch edit.
        self._switching_model = True
        try:
            self.branch_select.options = [(str(i), f'Solution {i + 1}')
                                          for i in range(self.model.branch_count)]
            self.branch_select.value = self._branches.get(new, '0')
        finally:
            self._switching_model = False
        if new not in self._control_panels:
            # Reflow the native controls without removing scientific inputs/notes.
            native = self.model.controls.children
            for group in native:
                group.width = None
                group.min_width = 0
                group.sizing_mode = 'stretch_width'
                for widget in group.children:
                    widget.width = None
                    widget.min_width = 0
                    widget.sizing_mode = 'stretch_width'
            grid = column(*native, spacing=8, sizing_mode='stretch_width')
            notes = [child for child in self.model.layout.children if child not in
                     (self.model.status, self.model.controls, self.model.plot_grid)]
            panel = [self.model.status, *notes, grid, Div(text='<h3>Dispersion curves</h3>'), self.curves.layout]
            compact_ui(*panel)
            self._control_panels[new] = panel
        # Mount the cached native control panel and refresh its current filtered view.
        self.model_controls.children = self._control_panels[new]
        self._update_views()
        self.model.refresh_filter()

    @batch_model_graph
    def _branch_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Remember the selected branch and refresh mounted views without changing model
        controls.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: str
            Previous zero-based branch index encoded as text.

        new: str
            Updated zero-based branch index encoded as text, retained for the
            currently selected model.

        Outputs
        -------
        None
            Retain the per-model branch value unless a model switch is already active.
        '''

        if not self.ready or self._switching_model:
            return
        self._branches[self.model_select.value] = new
        self._update_views()

    def _export_directory_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Track the visible export-directory edit before a save action.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: str
            Previous export-directory text.

        new: str
            Updated export-directory text from either value_input or value callbacks.

        Outputs
        -------
        None
            Store the current text from either typing or committed-value callbacks.
        '''

        self._export_directory_value = new

    def _comparison_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Synchronize comparison toggles and lazily choose the secondary dataset when
        requested.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: bool
            Previous comparison-toggle active state.

        new: bool
            Updated comparison-toggle active state, mirrored to both plot columns.

        Outputs
        -------
        None
            Guard recursive callbacks, initialize an unselected comparison catalog
            entry, and switch the mounted plot views.
        '''

        # Guard reciprocal toggle updates before changing comparison visibility.
        if self._syncing:
            return
        self._syncing = True
        try:
            self.left_toggle.active = self.right_toggle.active = bool(new)
        finally:
            self._syncing = False
        # Loading a hidden comparison at startup repeats cube/filter work and
        # competes with the visible primary. Select it only when requested.
        if new and self.secondary.selected_id is None and self.secondary.observations:
            identity = (self.primary.selected_id if self.primary.selected_id in self.secondary.catalog
                        else self.secondary.observations[0].id)
            self.secondary.selector.value = [identity]
        self._update_views()

    def _update_views(self):
        '''
        Purpose
        -------
        Mount the selected model branch or comparison dataset in both original and
        weighted plot grids.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Preserve controllers and section state, republish complete model pixel
            buffers when available, bind curve sources, and synchronize workspace state.
        '''

        if not self.ready:
            return
        comparison = self.left_toggle.active
        self.secondary_browser.visible = comparison
        self.secondary_visibility.visible = self.secondary_filtered_toggle.visible = comparison
        # Comparison mode hides the section as a whole, preserving its independent
        # expanded state when switching datasets, models or solution branches.
        self.dispersion_section.layout.visible = not comparison
        # Choose a dataset comparison or the selected native model branch for both
        # grids.
        branch = int(self.branch_select.value)
        left_second = self.secondary.observed_plot if comparison else self.model.plots[branch]
        right_second = self.secondary.result_plot if comparison else self.model.filtered.plots[branch]
        # Keep native plots/controls; switching modes never destroys controllers.
        self.left_plots.children = [(self.primary.observed_plot, 0, 0), (left_second, 1, 0)]
        self.right_plots.children = [(self.primary.result_plot, 0, 0), (right_second, 1, 0)]
        if not comparison and not self.model._dirty and self.model.last_result is not None:
            # Publish a complete owned pixel buffer after mounting the selected
            # branch, including cached returns that do not run the solver or
            # refresh_filter(). Never reuse the previous branch's canvas pixels.
            render_model_pixels(self.model, self.model.last_result, branch=branch)
            if self.model.filtered_result is not None:
                render_model_pixels(self.model.filtered, self.model.filtered_result,
                    getattr(self.model.filtered, 'coherence_visibility', 1.), branch=branch)
        # Apply integrated plot dimensions while preserving native data controllers.
        for plot in (self.primary.observed_plot, self.primary.result_plot,
                     self.secondary.observed_plot, self.secondary.result_plot):
            plot.width, plot.height = self.left_section.width, 470
            plot.min_width = 0
            plot.max_width = None
            plot.title.text_font = 'Times New Roman'
            plot.title.text_font_size = '12pt'
        self.curves.bind()
        self.sync_state()

    @batch_model_graph
    def filter_changed(self):
        '''
        Purpose
        -------
        Refresh primary/comparison reconstructions and active model display weights
        after a shared filter edit.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Synchronize coherence and previews; invalidate inactive weighted-renderer
            keys so those views refresh on selection without rerunning every model.
        '''

        if not self.ready:
            return
        # Refresh measured coherence and both independent native dataset
        # reconstructions.
        self.model_workspace.coherence.sync()
        self.primary._refresh_preview()
        self.secondary._refresh_preview()
        for model in self.model_workspace.models:
            if model._active:
                model.refresh_filter()
            else:
                # Inactive renderers are refreshed on selection with the latest
                # filter, without redrawing every cached model during a drag.
                model._filtered_display_key = None
        self.curves_updated()
        self.sync_state()

    @batch_model_graph
    def _model_gaussian_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Refresh active model display weights after changing the model-only Gaussian
        toggle.

        Inputs
        ------
        attr: str
            Changed Bokeh property name accepted by the callback signature.

        old: bool
            Previous active state of the model-only Gaussian-weighting toggle.

        new: bool
            Updated model Gaussian-weighting state; active model displays read the
            current toggle while their cached weighting keys are invalidated.

        Outputs
        -------
        None
            Invalidate every weighted-display key, refresh active models, and record
            state.
        '''

        if not self.ready:
            return
        # Invalidate every weighted-view key and update only active model renderers.
        for model in self.model_workspace.models:
            model._filtered_display_key = None
            if model._active:
                model.refresh_filter()
        self.sync_state()

    def sync_state(self):
        '''
        Purpose
        -------
        Capture current dataset/model/filter controls and update saved-settings and
        sampling status.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Store phase arrays in display order (n_nu, n_kh), model results and control
            snapshots. Retain earlier valid parameter dictionaries during invalid
            numeric edits, refresh sampling HTML when its key changes, and sync spatial
            analysis.
        '''

        if not self.ready:
            return
        # Copy current identities and independent model/filter display controls into the
        # snapshot.
        state = self.state
        state.primary_id, state.secondary_id = self.primary.selected_id, self.secondary.selected_id
        state.model_key = self.model.definition.key
        state.coherence_enabled = self.model_workspace.coherence.apply.active
        state.coherence_threshold = self.model_workspace.coherence.threshold.value
        state.model_gaussian_enabled = self.model_gaussian.active
        try:
            state.model_parameters = self.model._current_values()
            state.gaussian_parameters = self.primary.filter._current_parameters()
        except (ValueError, TypeError):
            # The native controllers surface invalid numeric inputs themselves.
            pass
        state.saved_parameters = self.primary.saved_parameters
        state.saved_sampling = self.primary.saved_sampling
        state.left_comparison, state.right_comparison = self.left_toggle.active, self.right_toggle.active
        # Retain dataset phases in display order and keep native model result objects.
        state.unfiltered = {name: None if pair.data is None else pair.data.values.T
                            for name, pair in [('primary', self.primary), ('secondary', self.secondary)]}
        state.filtered = {name: None if pair.transmission is None else pair.result_source.data['image'][0]
                          for name, pair in [('primary', self.primary), ('secondary', self.secondary)]}
        state.unfiltered['model'] = self.model.last_result
        state.filtered['model'] = self.model.filtered_result
        # Describe whether current parameters and sampling agree with the saved dataset
        # settings.
        if self.primary.data is None:
            label = 'Waiting for the primary dataset.'
        elif state.saved_parameters is None:
            label = 'Current filter has not been saved for this dataset.'
        elif (state.saved_parameters == state.gaussian_parameters and state.saved_sampling ==
              {key: widget.value for key, widget in self.primary.sampling.items()}):
            label = 'Current filter matches this dataset’s saved parameters and sampling.'
        else:
            label = 'Current filter or sampling differs from this dataset’s saved settings.'
        self.filter_state.text = escape(label)
        # Regenerate information HTML only when dataset identity or sampling values
        # change.
        sampling_key = tuple((id(pair.data), tuple(widget.value for widget in pair.sampling.values()))
                             for pair in (self.primary, self.secondary))
        if sampling_key != getattr(self, '_sampling_key', None):
            self.sampling_info.text = sampling_html([
                ('Primary dataset', self.primary)])
            self._sampling_key = sampling_key
        self.spatial.sync()

    def _dataset_metadata(self, pair):
        '''
        Purpose
        -------
        Capture native dataset provenance, active sampling, and recalculation metadata
        for export.

        Inputs
        ------
        pair: DatasetPair
            Loaded dataset/controller pair used for browser layout or export provenance.

        Outputs
        -------
        metadata: dict
            Reproducibility record including native array shape (n_kh, n_nu),
            spatial y count, and the recorded Dopplergram recalculation information.
        '''

        # Capture native reproducibility information before adding current y sampling
        # and recalculation.
        metadata = reproducibility_metadata(pair.data, pair.filter.geometry)
        metadata['sampling']['ny'] = int(pair.sampling['ny'].value)
        metadata['array_shape_kh_nu'] = list(pair.data.values.shape)
        metadata['recalculation'] = pair.recalculation_metadata
        return metadata

    @staticmethod
    def _plot_metadata(plot):
        '''
        Purpose
        -------
        Record the currently displayed image plot's ranges, axis labels, dimensions, and
        color scaling.

        Inputs
        ------
        plot: bokeh.plotting.figure
            Image plot whose ranges, axes, dimensions, and color mapper are recorded.

        Outputs
        -------
        metadata: dict
            Presentation configuration from the first color-mapped image renderer;
            requires such a renderer and labeled x/y axes.
        '''

        # Use the first displayed color-mapped image to record exact presentation
        # settings.
        images = [renderer for renderer in plot.renderers
                  if hasattr(getattr(renderer, 'glyph', None), 'color_mapper')]
        mapper = images[0].glyph.color_mapper
        return dict(title=plot.title.text, x_range=[plot.x_range.start, plot.x_range.end],
                    y_range=[plot.y_range.start, plot.y_range.end],
                    x_axis=plot.xaxis[0].axis_label, y_axis=plot.yaxis[0].axis_label,
                    width=plot.width, height=plot.height, scaling=type(mapper).__name__,
                    color_limits=[mapper.low, mapper.high], palette=list(mapper.palette),
                    nan_color=mapper.nan_color)

    def collect_metadata(self, kind, plots):
        '''
        Purpose
        -------
        Assemble exact dataset/model inputs, display settings, and Gaussian/coherence
        provenance for a plot pair.

        Inputs
        ------
        kind: str
            Export type: unfiltered, filter, or filtered.

        plots: sequence of figures
            Currently mounted plot pair whose presentation metadata is captured.

        Outputs
        -------
        metadata: dict
            Export type, primary and second-source records, presentation settings,
            solver/display inputs with units, saved registry/sampling state, and
            atmospheric/coherence information. Requires loaded selected sources.
        '''

        # Describe the second column as either a loaded dataset or an explicitly
        # parameterized model.
        model = self.model
        if self.left_toggle.active:
            second = self._dataset_metadata(self.secondary)
        else:
            result = model.last_result
            adapter = importlib.import_module(self.model_workspace.vesa.__package__ + '.interactive_models')
            second = dict(type='model', model_key=model.definition.key,
                title=model.definition.title, reference=model.definition.reference,
                implementation_note=model.definition.metadata_note,
                parameters=model._current_values(),
                calculated_parameters=dict(result.parameter_values),
                parameter_units={item.key: item.unit for item in model.definition.parameters},
                base_configuration=dict(model._base_params),
                solver_parameters=adapter.build_model_parameters(model.definition.key, dict(result.parameter_values)),
                derived_parameter_units={'theta': 'rad', 'phi': 'rad',
                                         'ax': 'km s^-1', 'ay': 'km s^-1', 'az': 'km s^-1'},
                field=model.field_select.value, resolution=model.resolution_select.value,
                shape_nu_kh_branches=list(result.phase_deg.shape),
                axes=dict(kh_Mm_inverse=result.kh_mm_inv.tolist(), nu_mHz=result.nu_mhz.tolist()),
                solution_index=int(self.branch_select.value), branch_labels=list(result.branch_labels),
                mask_numerical_warnings=0 in model.mask_warnings.active,
                show_fmode=0 in model.show_fmode.active,
                warnings=list(result.warnings),
                implementation=str(Path(self.model_workspace.vesa.__file__).resolve()))
        # Record export type and shared Gaussian settings alongside source provenance.
        metadata = dict(export_type=kind, filtered=kind != 'unfiltered',
                        comparison_mode=self.left_toggle.active)
        gaussian = gaussian_metadata(self.primary.filter._current_parameters())
        gaussian['model_enabled'] = self.model_gaussian.active
        gaussian['model_filter_sampling'] = asdict(self.primary.filter.geometry)
        gaussian['approved_registry_file'] = str(self.primary.registry_file)
        gaussian['saved_primary_parameters'] = self.primary.saved_parameters
        gaussian['saved_primary_sampling'] = self.primary.saved_sampling
        if kind == 'filter':
            metadata['gaussian_filter'] = gaussian
        metadata.update(source_1=self._dataset_metadata(self.primary), source_2=second,
                        plot_configuration=[self._plot_metadata(plot) for plot in plots])
        metadata['atmospheric_initialization'] = self.model_workspace.atmosphere
        metadata['coherence_weighting'] = self.model_workspace.coherence.metadata()
        if kind != 'filter':
            metadata['gaussian_filter'] = gaussian
        # State which display weights were active without changing the recorded solver
        # inputs.
        weights = [name for name, enabled in (
            ('Gaussian', self.model_gaussian.active),
            ('measured coherence', self.model_workspace.coherence.apply.active)) if enabled]
        metadata['application'] = ('Dataset: independent 3-D cube filtering, checked inverse FFT and native phase recalculation. '
            + 'Theoretical model display weights: '+(' times '.join(weights) if weights else 'none')
            + '; physical solver fields and dispersion roots unchanged.')
        metadata['unfiltered_definition'] = 'Original or supplied post-magnetogram Dopplergrams before the current Gaussian; previous Gaussian settings never compound.'
        return metadata

    def save_plot(self, kind):
        '''
        Purpose
        -------
        Validate the current pair and save its displayed plots with reproducibility
        metadata.

        Inputs
        ------
        kind: str
            Export type: unfiltered, filter, or filtered.

        Outputs
        -------
        paths: sequence of pathlib.Path or None
            Written plot/metadata artifact paths on success. Reject stale/unavailable
            sources, incomplete filter/coherence results, empty rasters, or a blank
            export destination; display escaped error text and return None on failure.
        '''

        try:
            # Require current selected sources and completed numerical/display results
            # before exporting.
            if kind not in self.save_buttons:
                raise ValueError('Unknown plot export type.')
            if self.primary.data is None or self.primary.data.observation.id != self.primary.selected_id:
                raise ValueError('Wait for the primary dataset to finish loading.')
            if self.left_toggle.active:
                if self.secondary.data is None or self.secondary.data.observation.id != self.secondary.selected_id:
                    raise ValueError('Wait for the comparison dataset to finish loading.')
            elif self.model._dirty or self.model.last_result is None:
                raise ValueError('Wait for the selected model to finish calculating, or press Recalculate.')
            if (kind != 'unfiltered' and not self.left_toggle.active
                    and self.model_workspace.coherence.apply.active
                    and self.model_workspace.coherence.result is None):
                raise ValueError('Cannot save a coherence-weighted model until measured coherence is available.')
            # Refresh the accepted filter geometry before validating the displayed plot
            # pair.
            self.primary._set_geometry()
            self.primary.filter._perform_recompute()
            if kind != 'unfiltered' and (self.primary.transmission is None
                    or (self.secondary.transmission is None if self.left_toggle.active
                        else self.model.filtered_result is None)):
                raise ValueError('Cannot save filtered plots: the filter is unavailable.')
            grid = self.left_plots if kind == 'unfiltered' else self.right_plots
            plots = [item[0] for item in grid.children]
            # Reject empty image sources before writing either member of the export
            # pair.
            for plot in plots:
                images = [renderer for renderer in plot.renderers
                          if hasattr(getattr(renderer, 'glyph', None), 'color_mapper')]
                if not images or not np.isfinite(images[0].data_source.data['image'][0]).any():
                    raise ValueError('Cannot save this pair: a selected plot has no finite displayed values.')
            if not self._export_directory_value.strip():
                raise ValueError('Choose a plot export directory before saving.')
            # Build the export identity and save plots with their exact
            # presentation/input metadata.
            from output_paths import export_configuration
            cfg = export_configuration(self.primary.data.analysis_config, self.primary.filter._current_parameters(),
                gaussian_enabled=kind!='unfiltered', diagnostic_parameters={'export_type':kind})
            paths = save_plot_pair(plots, self.collect_metadata(kind, plots), self._export_directory_value, config=cfg)
            self.export_status.text = '<b>Plot and metadata saved:</b><br>' + '<br>'.join(escape(str(p)) for p in paths)
            return paths
        # Surface export failures in the workspace and return no artifact paths.
        except Exception as exc:
            self.export_status.text = f'<p style="color:#991b1b">Plot was not saved: {escape(str(exc))}</p>'
            return None


def build_document(doc, **kwargs):
    # The temporary component roots are composed into one final application.
    # Traversing every reference after each construction edit is quadratic in
    # the full workspace size. Publish one complete graph before first render.
    '''
    Purpose
    -------
    Construct the integrated explorer while batching initial offline graph assembly.

    Inputs
    ------
    doc: bokeh.document.Document
        Document that owns the explorer models, callbacks, and final layout root.

    **kwargs: object
        Options forwarded to IntegratedKomegaExplorer, including configuration and
        registry paths, discovery roots, export directory, launch context, scheduling,
        and an explicit initial input observation.

    Outputs
    -------
    explorer: IntegratedKomegaExplorer
        Constructed controller; add its complete application root to doc through
        model_graph_update(), retaining normal live publication behavior.
    '''

    with model_graph_update(doc, constructing=not doc.roots):
        return IntegratedKomegaExplorer(doc, **kwargs)
