'''
Purpose
-------
Link the native Gaussian filter and authoritative Vesa dispersion models through
session-local exact-grid display state.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for komega_explorer.py.

Notes
-----
One live workspace for the pipeline Gaussian filter and Vesa dispersion models.

The existing explorers still own their calculations. Filtering multiplies the
cached diagram arrays by a Gaussian constructed on their coordinates.
'''

from __future__ import annotations

# Import the libraries and shared helpers used by this module
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from html import escape
import importlib
from pathlib import Path
import sys
import time
from types import MappingProxyType, ModuleType

import numpy as np
from bokeh.document import Document
from bokeh.events import DocumentReady
from bokeh.layouts import column, gridplot, row
from bokeh.models import Button, CustomJS, Div, GridBox, HoverTool, TabPanel, Tabs, TextInput, Toggle

from gaussian_filter_explorer import (
    CONFIG_FILE,
    FilterResult,
    GaussianFilterExplorer,
    PARAMETER_KEYS,
    _load_config,
    compute_filter_result, compute_diagram_filter,
)
from bokeh_ui_helpers import batch_model_graph, frequency_control, LatestModelRunner
from coherence_bokeh import CoherenceControls, add_coherence_hover, apply_model_visibility, clear_model_visibility

MODEL_TAB_LABELS = {
    "nc2009": "3D MAG", "alfven_mode": "Alfvén", "slow_mode": "Slow", "fast_mode": "Fast",
    "bunte1993": "Bunte 1993", "mt1982": "MT1982", "mt1981": "MT1981",
}


def _expanded_definition(definition, values):
    '''
    Purpose
    -------
    Copy a model definition with local defaults and bounds expanded to contain explicit
    physical values.

    Inputs
    ------
    definition: ModelDefinition
        Native model metadata and ordered physical parameter controls.
    values: dict
        Named native-unit model defaults, with angles in degrees for displayed controls.

    Outputs
    -------
    definition: ModelDefinition
        Replacement metadata without mutating the original definition.
    '''

    # Copy a model definition with local defaults and bounds expanded to contain
    # explicit physical values
    return replace(definition, parameters=tuple(replace(item,
        default=float(values.get(item.key, item.default)),
        minimum=min(item.minimum, float(values.get(item.key, item.default))),
        maximum=max(item.maximum, float(values.get(item.key, item.default))))
        for item in definition.parameters))


def _allow_physical_ranges(vesa, definitions):
    # Only validation ranges are expanded; native equations/defaults are not
    # changed. UI definitions and reset values remain local to this document.
    '''
    Purpose
    -------
    Expand the private adapter's validation ranges to include local model definitions.

    Inputs
    ------
    vesa: types.ModuleType
        Privately imported authoritative Vesa Bokeh/model adapter module.
    definitions: iterable of ModelDefinition
        Document-local definitions whose physical ranges must be accepted.

    Outputs
    -------
    None
        Replaces the adapter's read-only registry mapping while retaining equations and
        original model defaults.
    '''

    adapter = importlib.import_module(vesa.__package__ + '.interactive_models')
    updated = dict(adapter.MODEL_BY_KEY)
    for definition in definitions:
        current = updated[definition.key]
        ranges = {item.key: item for item in definition.parameters}
        updated[definition.key] = replace(current, parameters=tuple(replace(item,
            minimum=min(item.minimum, ranges[item.key].minimum),
            maximum=max(item.maximum, ranges[item.key].maximum)) for item in current.parameters))
    adapter.MODEL_BY_KEY = MappingProxyType(updated)


@lru_cache(maxsize=4)
def load_dispersion_explorer(project_dir: str, bounds: tuple = ()) -> ModuleType:
    '''
    Purpose
    -------
    Import authoritative Vesa modules under a private package identity to avoid notebook
    name collisions.

    Inputs
    ------
    project_dir: str
        Vesa project root containing Code/diagnostic_diagram.
    bounds: tuple
        Hashable parameter/value pairs used to expand private NC2009 validation bounds
        and distinguish import/cache identities.

    Outputs
    -------
    explorer: types.ModuleType
        Cached private interactive_bokeh module with optional local NC2009 bounds;
        missing required solver files raise FileNotFoundError.

    Notes
    -----
    Import Vesa as a private package, avoiding notebook config/name collisions.
    '''

    # Import authoritative Vesa modules under a private package identity to avoid
    # notebook name collisions
    module_dir = Path(project_dir).expanduser().resolve() / "Code" / "diagnostic_diagram"
    for filename in ("config.py", "functions.py", "interactive_models.py", "interactive_bokeh.py"):
        if not (module_dir / filename).is_file():
            raise FileNotFoundError(
                f"Required dispersion explorer file missing: {module_dir / filename}. "
                "Check komega_comparison['vesa_2026_dir'] in config.py."
            )
    name = "_morales_komega_vesa_" + sha256((str(module_dir) + repr(bounds)).encode()).hexdigest()[:16]
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(module_dir)]
        package.__package__ = name
        sys.modules[name] = package
    explorer = importlib.import_module(f"{name}.interactive_bokeh")
    if bounds:
        # A private adapter keeps physical simulation ranges session-independent
        # from the narrower demonstration controls used by ordinary launches.
        adapter = importlib.import_module(f"{name}.interactive_models")
        ranges = dict(bounds)
        definition = adapter.MODEL_BY_KEY['nc2009']
        expanded = replace(definition, parameters=tuple(
            replace(item, minimum=min(item.minimum, ranges.get(item.key, item.minimum)),
                    maximum=max(item.maximum, ranges.get(item.key, item.maximum)))
            for item in definition.parameters))
        adapter.MODEL_BY_KEY = MappingProxyType(dict(adapter.MODEL_BY_KEY, nc2009=expanded))
        explorer.MODEL_DEFINITIONS = tuple(expanded if item.key == 'nc2009' else item
                                          for item in explorer.MODEL_DEFINITIONS)
    return explorer


class LinkedGaussianExplorer(GaussianFilterExplorer):
    '''
    Purpose
    -------
    Reuse the native Gaussian explorer while notifying an owning model workspace after
    exact updates.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    controller: KomegaExplorer
        Owning workspace sharing filter state, comparison axes, and calculation
        lifecycle.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.

    Outputs
    -------
    explorer: LinkedGaussianExplorer
        Linked filter controller using the existing native filter calculation and
        preview.
    '''

    def __init__(self, doc: Document, controller: KomegaExplorer, config_file: Path):
        '''
        Purpose
        -------
        Construct the native filter explorer with deferred initialization and an owning
        controller.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        controller: KomegaExplorer
            Owning workspace sharing filter state, comparison axes, and calculation
            lifecycle.
        config_file: str or pathlib.Path
            Configuration-module path used to reconstruct the runtime settings.

        Outputs
        -------
        None
            Stores the controller and builds native controls without scheduling a
            separate initial calculation.
        '''

        # Construct the native filter explorer with deferred initialization and an
        # owning controller
        self.controller = controller
        super().__init__(doc, config_file=config_file, schedule_initial=False)

    def _perform_recompute(self) -> None:
        '''
        Purpose
        -------
        Recompute exact native filter products and notify the owning workspace of
        success or failure.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Passes FilterResult when valid or None when the native calculation failed.
        '''

        # Recompute exact native filter products and notify the owning workspace of
        # success or failure
        super()._perform_recompute()
        result = None
        if not self.error_label.visible:
            result = compute_filter_result(self.geometry, **self._current_parameters())
        self.controller.filter_changed(result)


def _linked_model_class(vesa: ModuleType):
    '''
    Purpose
    -------
    Construct a native ModelExplorer subclass with exact comparison grids and linked
    visibility/filtering.

    Inputs
    ------
    vesa: types.ModuleType
        Privately imported authoritative Vesa Bokeh/model adapter module.

    Outputs
    -------
    model_class: type
        LinkedModelExplorer subclass reusing authoritative solver and rendering methods.

    Notes
    -----
    Reuse native solvers with comparison sampling and linked filtering.
    '''

    # Construct a native ModelExplorer subclass with exact comparison grids and linked
    # visibility/filtering
    class LinkedModelExplorer(vesa.ModelExplorer):
        '''
        Purpose
        -------
        Extend the native model explorer with exact dataset sampling and session-linked
        filter/coherence display.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        definition: ModelDefinition
            Native model metadata and ordered physical parameter controls.
        controller: KomegaExplorer
            Owning workspace sharing filter state, comparison axes, and calculation
            lifecycle.

        Outputs
        -------
        explorer: LinkedModelExplorer
            Native roots remain owned by the authoritative Vesa adapter; linked state
            controls display and calculation acceptance.
        '''

        def __init__(self, doc, definition, controller):
            '''
            Purpose
            -------
            Build native model controls/plots and attach transmission/coherence hover
            fields.

            Inputs
            ------
            doc: bokeh.document.Document
                Session document used for request arguments and callbacks.
            definition: ModelDefinition
                Native model metadata and ordered physical parameter controls.
            controller: KomegaExplorer
                Owning workspace sharing filter state, comparison axes, and calculation
                lifecycle.

            Outputs
            -------
            None
                Stores the controller, initializes comparison-grid choices, and retains
                native model sources.
            '''

            # Build native model controls/plots and attach transmission/coherence hover
            # fields
            self.controller = controller
            self.transmission = None
            super().__init__(doc, definition)
            self._sync_comparison_grid(initial=True)
            for plot in self.plots:
                for hover in plot.select(type=HoverTool):
                    hover.tooltips = list(hover.tooltips) + [
                        ("Filter amplitude T", "@transmission{0.0000}"),
                        ("Retained power T²", "@power_transmission{0.0000}"),
                        ("Apply Filter", "@filter_applied"),
                    ]
            self.hover_source.data = dict(self.hover_source.data,
                transmission=[], power_transmission=[], filter_applied=[])
            add_coherence_hover(self)

        def _build_controls(self):
            '''
            Purpose
            -------
            Compose native physical controls with mHz adapters and validated custom-grid
            inputs.

            Inputs
            ------
            None

            Outputs
            -------
            controls: Bokeh layout
                Native model control layout with responsive parameter grids and explicit
                sample-count validation.
            '''

            # Compose native physical controls with mHz adapters and validated
            # custom-grid inputs
            controls = super()._build_controls()
            for key in ('N2', 'wac'):
                if key not in self.widgets:
                    continue
                previous = self.numeric_controls[key]
                converted = frequency_control(self.widgets[key], key, self.controller.vesa.ExactSlider)
                for group in controls.children:
                    if previous.layout in group.children:
                        group.children[group.children.index(previous.layout)] = converted.layout
                self.numeric_controls[key] = converted
            self.parameter_grids = []
            for group, role in zip(controls.children[:2], ('dispersion', 'diagram')):
                layouts = [self.numeric_controls[item.key].layout
                           for item in self.definition.parameters if item.role == role]
                for layout in layouts:
                    layout.margin = 0
                    control = next(c for c in self.numeric_controls.values() if c.layout is layout)
                    control.slider.width = None
                    control.slider.min_width = 40
                    control.slider.sizing_mode = 'stretch_width'
                    control.input.width = 72
                    control.input.margin = (0, 0, 0, 5)
                    control.label.margin = (0, 0, 2, 0)
                grid = GridBox(children=[(layout, i, 0) for i, layout in enumerate(layouts)],
                    spacing=(6, 12), sizing_mode='stretch_width', min_width=0,
                    name=f'{self.definition.key}:{role}:parameters')
                # Preserve headings, references and native implementation notes.
                remaining = [child for child in group.children if child not in layouts]
                heading_count = 2 if role == 'dispersion' else 1
                group.children = remaining[:heading_count] + [grid] + remaining[heading_count:]
                self.parameter_grids.append(grid)

            self.mask_warnings.visible = False
            display = controls.children[-1]
            display.children = [child for child in display.children
                                if child is not self.mask_warnings]
            # The final native Div contains the wheel-zoom instructions.
            display.children = display.children[:-1]
            default = vesa.RESOLUTION_OPTIONS['interactive']
            self.custom_kh = TextInput(title='kₕ samples (8–220)', value=str(default[0]),
                sizing_mode='stretch_width', min_width=0, name=f'{self.definition.key}:grid:kh')
            self.custom_nu = TextInput(title='ν samples (8–220)', value=str(default[1]),
                sizing_mode='stretch_width', min_width=0, name=f'{self.definition.key}:grid:nu')
            self.grid_error = Div(text='', visible=False, sizing_mode='stretch_width',
                styles={'color': '#b91c1c', 'font-size': '12px'})
            self.custom_grid = column(row(self.custom_kh, self.custom_nu,
                sizing_mode='stretch_width', spacing=10), self.grid_error,
                visible=False, sizing_mode='stretch_width', min_width=0,
                name=f'{self.definition.key}:grid:custom')
            display.children.insert(display.children.index(self.resolution_select) + 1, self.custom_grid)
            for widget in (self.custom_kh, self.custom_nu):
                widget.on_change('value', self._custom_grid_changed)

            for child in controls.children:
                child.width = 240
            self.recalculate_button.width = self.reset_button.width = 108
            return controls

        def _custom_resolution(self):
            '''
            Purpose
            -------
            Parse accepted custom horizontal and frequency sample counts.

            Inputs
            ------
            None

            Outputs
            -------
            resolution: tuple of int
                (n_kh,n_nu), each from 8 to 220; invalid text/counts raise ValueError.
            '''

            # Parse accepted custom horizontal and frequency sample counts
            try:
                values = tuple(int(widget.value.strip()) for widget in (self.custom_kh, self.custom_nu))
            except ValueError:
                raise ValueError('Enter whole sample counts from 8 to 220.') from None
            if not all(8 <= value <= 220 for value in values):
                raise ValueError('Each grid dimension must contain 8 to 220 samples.')
            return values

        def _custom_grid_changed(self, attr, old, new):
            '''
            Purpose
            -------
            Validate custom-grid text and request calculation only when custom sampling
            is selected.

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
                Updates the validation message and delegates valid current custom-grid
                changes.
            '''

            # Validate custom-grid text and request calculation only when custom
            # sampling is selected
            try:
                self._custom_resolution()
            except ValueError as exc:
                self.grid_error.text, self.grid_error.visible = str(exc), True
                return
            self.grid_error.text, self.grid_error.visible = '', False
            if self.resolution_select.value == 'custom':
                self._calculation_changed(attr, old, new)

        def _calculation_changed(self, attr, old, new):
            '''
            Purpose
            -------
            Update custom-grid visibility and validate its dimensions before native
            recomputation.

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
                Invalid custom counts retain the current result and show the explicit
                grid error.
            '''

            # Update custom-grid visibility and validate its dimensions before native
            # recomputation
            self.custom_grid.visible = self.resolution_select.value == 'custom'
            if self.custom_grid.visible:
                try:
                    self._custom_resolution()
                except ValueError as exc:
                    self.grid_error.text, self.grid_error.visible = str(exc), True
                    return
            super()._calculation_changed(attr, old, new)

        def _build_plot(self):
            '''
            Purpose
            -------
            Build native model plots and apply the linked workspace's retained panel
            layout.

            Inputs
            ------
            None

            Outputs
            -------
            None
                Preserves native scientific sources while changing panel sizing,
                typography, toolbar placement, and plot-grid composition.
            '''

            # Build native model plots and apply the linked workspace's retained panel
            # layout
            super()._build_plot()
            for plot in self.plots:
                plot.title.text = ''
                plot.width = plot.height = 440
                plot.toolbar_location = "right"
                plot.sizing_mode = "fixed"
                plot.min_width = 340
                plot.max_width = 700
                plot.title.text_font_size = "11pt"
                for axis in (plot.xaxis[0], plot.yaxis[0]):
                    axis.axis_label_text_font_size = "16pt"
                    axis.major_label_text_font_size = "13pt"
            for legend in self.legends:
                legend.label_text_font_size = "10pt"
            self.plot_grid = gridplot(
                [self.plots[index:index + 2] for index in range(0, self.branch_count, 2)],
                merge_tools=False, toolbar_location=None, sizing_mode="stretch_width",
            )

        def set_active(self, active):
            '''
            Purpose
            -------
            Advance activation generations when the native model tab changes activity.

            Inputs
            ------
            active: bool
                Whether this model is the current visible active calculation tab.

            Outputs
            -------
            None
                Delegates lazy calculation state to the native explorer and refreshes
                linked filtering for a newly active clean result.
            '''

            # Advance activation generations when the native model tab changes activity
            changed = bool(active) != self._active
            if changed:
                self._solve_generation = getattr(self, '_solve_generation', 0)+1
                self._activation_generation = getattr(self, '_activation_generation', 0)+1
            super().set_active(active)
            if changed and active and not self._dirty and self.last_result is not None:
                self.refresh_filter()

        def _sync_comparison_grid(self, initial=False):
            '''
            Purpose
            -------
            Synchronize resolution options with the primary dataset's exact axes or
            native default grid.

            Inputs
            ------
            initial: bool
                Reset the resolution selection to its dataset/default mode when True.

            Outputs
            -------
            None
                Updates controls under callback suppression while retaining an
                explicitly selected custom grid unless initial is True.
            '''

            # Synchronize resolution options with the primary dataset's exact axes or
            # native default grid
            axes = self.controller.comparison_axes
            default = 'dataset' if axes is not None else 'interactive'
            shape = tuple(map(len, axes)) if axes is not None else vesa.RESOLUTION_OPTIONS['interactive']
            label = f'Default — {shape[0]} × {shape[1]}'
            if axes is not None:
                label += ' (match dataset)'
            self._suppress_callbacks = True
            try:
                self.resolution_select.options = [(default, label), ('custom', 'Custom grid size')]
                if initial or self.resolution_select.value != 'custom':
                    self.resolution_select.value = default
                self.custom_grid.visible = self.resolution_select.value == 'custom'
            finally:
                self._suppress_callbacks = False

        def _restore_defaults(self):
            '''
            Purpose
            -------
            Restore native model defaults and reset its comparison-grid selection.

            Inputs
            ------
            None

            Outputs
            -------
            None
                Delegates native widget/reset behavior before selecting dataset/default
                resolution.
            '''

            # Restore native model defaults and reset its comparison-grid selection
            super()._restore_defaults()
            self._sync_comparison_grid(initial=True)

        @staticmethod
        def _result_state_key(result):
            '''
            Purpose
            -------
            Build a panel-order key including the exact physical grid coordinates.

            Inputs
            ------
            result: DiagramResult
                Native model result with axes in Mm^-1 and mHz.

            Outputs
            -------
            key: tuple
                Model key, normalized physical inputs, complete kh-axis tuple, and
                complete nu-axis tuple.
            '''

            # Build a panel-order key including the exact physical grid coordinates
            return (result.model_key, result.parameter_values,
                    tuple(result.kh_mm_inv), tuple(result.nu_mhz))

        def _order_result_for_panels(self, result):
            '''
            Purpose
            -------
            Retain native branch-panel alignment only across compatible physical
            domains.

            Inputs
            ------
            result: DiagramResult
                New solver result before native panel alignment/cache restoration.

            Outputs
            -------
            ordered, alignment, cache_hit: tuple
                Native panel-order result/diagnostics after resetting incompatible
                explicit-axis references.
            '''

            # Retain native branch-panel alignment only across compatible physical
            # domains
            previous = self._last_ordering_result
            if (previous is not None and
                    ('explicit_axes' in (previous.summary.get('grid_source'), result.summary.get('grid_source')))
                    and (not np.array_equal(previous.kh_mm_inv, result.kh_mm_inv)
                         or not np.array_equal(previous.nu_mhz, result.nu_mhz))):
                # Different domains cannot be matched at normalized pixel positions.
                self._last_ordering_result = None
            return super()._order_result_for_panels(result)

        def _solve_state(self):
            '''
            Purpose
            -------
            Snapshot accepted physical values, resolution choice, and exact optional
            dataset axes.

            Inputs
            ------
            None

            Outputs
            -------
            state: tuple
                Sorted parameter pairs, custom dimensions or resolution token, and
                dataset axes when selected.
            '''

            # Snapshot accepted physical values, resolution choice, and exact optional
            # dataset axes
            resolution = (self._custom_resolution() if self.resolution_select.value == 'custom'
                          else self.resolution_select.value)
            return (tuple(sorted(self._current_values().items())), resolution,
                    self.controller.comparison_axes if self.resolution_select.value == 'dataset' else None)

        def _root_state(self, state):
            '''
            Purpose
            -------
            Restrict a full solve state to root-changing physical values and exact
            sampling.

            Inputs
            ------
            state: tuple
                Complete accepted state from _solve_state().

            Outputs
            -------
            state: tuple
                Dispersion-role inputs plus resolution and axes, excluding diagram-only
                postprocessing values.
            '''

            # Restrict a full solve state to root-changing physical values and exact
            # sampling
            values, resolution, axes = state
            keys = {item.key for item in self.definition.parameters if item.role == 'dispersion'}
            return (tuple((key, value) for key, value in values if key in keys), resolution, axes)

        def _calculation(self, state):
            '''
            Purpose
            -------
            Create a worker callable capturing physical values and exact sampling
            without live widget access.

            Inputs
            ------
            state: tuple
                Document-thread snapshot of values, resolution, and optional exact axes.

            Outputs
            -------
            calculate: callable
                Zero-argument authoritative compute_diagram call for explicit axes or
                the selected preset/custom dimensions.
            '''

            # Create a worker callable capturing physical values and exact sampling
            # without live widget access
            values, resolution, axes = state
            # Snapshot all inputs on the document thread. Workers never read
            # widgets, order panels, render, or modify the Bokeh document.
            key = self.definition.key
            preset = resolution if isinstance(resolution, tuple) else vesa.RESOLUTION_OPTIONS.get(resolution)
            def calculate():
                '''
                Purpose
                -------
                Solve the captured native model on exact dataset axes or the requested
                preset grid.

                Inputs
                ------
                None

                Outputs
                -------
                result: DiagramResult
                    Authoritative native solver output; numerical/parameter validation
                    errors propagate.
                '''

                # Solve the captured native model on exact dataset axes or the requested
                # preset grid
                if axes is not None:
                    return vesa.compute_diagram(key, dict(values), kh_mm_inv=axes[0], nu_mhz=axes[1])
                return vesa.compute_diagram(key, dict(values), preset)
            return calculate

        @batch_model_graph
        def _accept_model_result(self, raw=None, error=None):
            '''
            Purpose
            -------
            Accept roots, apply any current diagram-only postprocessing, and update
            stable native panels.

            Inputs
            ------
            raw: DiagramResult or None
                Completed authoritative solver result, or None when error is supplied.
            error: Exception or None
                Worker exception, or None after a successful calculation.

            Outputs
            -------
            None
                Preserves root identity, aligns panels, publishes linked display, and
                records timing; exceptions clear stale fields and show a calculation
                error.
            '''

            # Accept roots, apply any current diagram-only postprocessing, and update
            # stable native panels
            try:
                if error is not None:
                    raise error
                started = time.perf_counter()
                values = self._current_values()
                if dict(raw.parameter_values) != values:
                    # Δz/reference edits during a solve reuse its exact roots.
                    # The native postprocessor also rejects any physics change.
                    raw = vesa.update_diagram_postprocessing(raw, values)
                result, _, _ = self._order_result_for_panels(raw)
                self.last_result = self._last_ordering_result = result
                self._dirty = False
                self._update_display(result)
                self.last_display_seconds = time.perf_counter() - started
                if result.warnings:
                    self._set_status('<b>Warnings:</b> ' + '; '.join(map(escape, result.warnings)), 'warning')
                else:
                    self._set_status('', 'ok')
            except Exception as exc:
                self._dirty = True
                self._clear_plot(f'No valid solution: {exc}')
                self._set_status(f'<b>Calculation failed:</b> {escape(str(exc))}', 'error')

        def _perform_recompute(self):
            '''
            Purpose
            -------
            Run and accept the active model synchronously for deterministic offline
            execution.

            Inputs
            ------
            None

            Outputs
            -------
            None
                Inactive models remain dirty; solver errors use the same acceptance
                failure path.
            '''

            # Run and accept the active model synchronously for deterministic offline
            # execution
            if not self._active:
                self._dirty = True
                return
            try:
                raw = self._calculation(self._solve_state())()
            except Exception as exc:
                self._accept_model_result(error=exc)
            else:
                self._accept_model_result(raw)

        def _parameter_changed(self, key, role, attr, old, new):
            '''
            Purpose
            -------
            Invalidate physical solve generations and stale model pixels before
            delegating native parameter handling.

            Inputs
            ------
            key: str
                Physical parameter identifier associated with this update.
            role: str
                Parameter change category: dispersion requires roots, diagram allows
                postprocessing.
            attr: str
                Bokeh property name supplied by the change callback.
            old: object
                Previous property value supplied by Bokeh.
            new: object
                Updated property value supplied by Bokeh.

            Outputs
            -------
            None
                Diagram-only edits retain reusable roots; suppressed programmatic
                changes do not advance the solve generation.
            '''

            # Invalidate physical solve generations and stale model pixels before
            # delegating native parameter handling
            if not self._suppress_callbacks:
                self._solve_generation = getattr(self, '_solve_generation', 0)+1
                if role != 'diagram':
                    vesa.ModelExplorer._clear_plot(self, 'Updating model…')
                    clear_model_visibility(self)
            super()._parameter_changed(key, role, attr, old, new)

        def _recompute(self):
            '''
            Purpose
            -------
            Snapshot current root state and request generation-safe asynchronous or
            offline model work.

            Inputs
            ------
            None

            Outputs
            -------
            None
                Inactive tabs remain lazy; completion is accepted only for matching
                physical inputs, axes, and activation state.
            '''

            # Snapshot current root state and request generation-safe asynchronous or
            # offline model work
            self._pending_callback = None
            if not self._active:
                self._dirty = True
                return
            self._solve_generation = getattr(self, '_solve_generation', 0)+1
            generation = self._solve_generation
            activation = getattr(self, '_activation_generation', 0)
            try:
                state = self._solve_state()
                roots = self._root_state(state)
                calculate = self._calculation(state)
            except Exception as exc:
                self._accept_model_result(error=exc)
                return
            self._set_status('Calculating exact polynomial roots and tracking branches…', 'busy')
            def current():
                # A newer diagram-only edit does not obsolete a root solve.
                # Physical inputs and exact sampling must still match, and an
                # already accepted result can never be overwritten.
                '''
                Purpose
                -------
                Check whether captured roots still belong to the active dirty model
                state.

                Inputs
                ------
                None

                Outputs
                -------
                current: bool
                    True only for matching physical inputs, exact sampling, and
                    activation generation; invalid current controls return False.
                '''

                try:
                    return (self._active and self._dirty
                            and activation == getattr(self, '_activation_generation', 0)
                            and roots == self._root_state(self._solve_state()))
                except (ValueError, TypeError):
                    return False
            if self.controller.async_models:
                self.controller.model_runner.request(calculate, self._accept_model_result, current)
            else:
                # Preserve deterministic execution for headless documents.
                self.doc.add_next_tick_callback(lambda: self._perform_recompute()
                    if generation == self._solve_generation and current() else None)

        def _set_status(self, message, state):
            # Numerical diagnostics stay in result/export metadata.
            '''
            Purpose
            -------
            Display only active calculation/error text while retaining numerical
            warnings in result provenance.

            Inputs
            ------
            message: str
                Status or missing-result text displayed by the native model presentation
                path.
            state: str
                Native pending, busy, ok, warning, or error status category.

            Outputs
            -------
            None
                Delegates native styling, clears ok/warning text, and synchronizes
                status visibility/wrapping.
            '''

            if state in {"ok", "warning"}:
                message = ""
            super()._set_status(message, state)
            self.status.visible = bool(message)
            self.status.styles = dict(self.status.styles, **{"overflow-wrap": "anywhere"})

        def _update_display(self, result):
            '''
            Purpose
            -------
            Route an accepted native model result through linked filter and coherence
            presentation.

            Inputs
            ------
            result: DiagramResult
                Accepted native solution to render.

            Outputs
            -------
            None
                Delegates to refresh_filter without altering the cached original
                physical solution.
            '''

            # Route an accepted native model result through linked filter and coherence
            # presentation
            self.refresh_filter(result)

        def _render_native(self, result):
            '''
            Purpose
            -------
            Use authoritative model plotting and retain the linked workspace's compact
            untitled panels.

            Inputs
            ------
            result: DiagramResult
                Native or display-filtered model fields.

            Outputs
            -------
            None
                Updates native sources/color scales before clearing per-panel title
                text.
            '''

            # Use authoritative model plotting and retain the linked workspace's compact
            # untitled panels
            vesa.ModelExplorer._update_display(self, result)
            # Native rendering restores mode/propagation titles on every draw.
            for plot in self.plots:
                plot.title.text = ''

        def refresh_filter(self, result=None):
            '''
            Purpose
            -------
            Evaluate the Gaussian on exact model bins and publish filtered display
            fields plus coherence visibility.

            Inputs
            ------
            result: DiagramResult or None
                Explicit model result, otherwise the current cached last_result.

            Outputs
            -------
            None
                Multiplies replacement display arrays only when enabled, retains cached
                original fields, and updates transmission/power/visibility hover
                metadata. Shape mismatches raise ValueError.
            '''

            # Evaluate the Gaussian on exact model bins and publish filtered display
            # fields plus coherence visibility
            result = self.last_result if result is None else result
            if result is None:
                return
            self.transmission = (None if self.controller.filter_result is None else
                compute_diagram_filter(result.kh_mm_inv, result.nu_mhz,
                    self.controller.filter.geometry, **self.controller.filter._current_parameters()))
            enabled = self.controller.apply_filter.active and self.transmission is not None
            displayed = result
            if enabled:
                # Add only a branch axis for broadcasting; preserve cached originals.
                transmission = self.transmission[..., None]
                if transmission.shape[:2] != result.phase_deg.shape[:2]:
                    raise ValueError("Filter and model dimensions do not match.")
                displayed = replace(result, phase_deg=result.phase_deg * transmission,
                    kz_real=result.kz_real * transmission, kz_imag=result.kz_imag * transmission)
            # Use the unchanged model plotting routine, including its color scaling.
            self._render_native(displayed)
            transmission = (np.zeros(result.phase_deg.shape[:2])
                            if self.transmission is None else self.transmission)
            self.hover_source.data = dict(self.hover_source.data,
                transmission=transmission.ravel(),
                power_transmission=(transmission ** 2).ravel(),
                filter_applied=np.full(transmission.size, "yes" if enabled else "no"))
            apply_model_visibility(self, displayed, self.controller.coherence,
                                   transmission if enabled else None)

        def _clear_plot(self, message):
            '''
            Purpose
            -------
            Clear native panels and remove stale linked coherence/filter result state.

            Inputs
            ------
            message: str
                Status or missing-result text displayed by the native model presentation
                path.

            Outputs
            -------
            None
                Restores scalar visibility and resets last_result/transmission after
                native source clearing.
            '''

            # Clear native panels and remove stale linked coherence/filter result state
            super()._clear_plot(message)
            clear_model_visibility(self)
            self.last_result = None
            self.transmission = None

    return LinkedModelExplorer


class KomegaExplorer:
    '''
    Purpose
    -------
    Share session-local Gaussian, coherence, and exact-grid state across the registered
    native model tabs.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    schedule_initial: bool
        Schedule the initial calculation after document construction when True.
    launch_context: dict or None
        Optional validated exact numerical dataset/model/atmosphere launch context.
    shared_filter: GaussianFilterExplorer or None
        Existing filter controller to reuse; None constructs a linked local filter.
    model_class_factory: callable or None
        Optional factory producing the linked native ModelExplorer subclass.
    comparison_data: ObservationData or None
        Loaded primary dataset whose exact kh/nu bins define dataset-mode model
        sampling.

    Outputs
    -------
    explorer: KomegaExplorer
        Linked authoritative model workspace with private adapter imports, shared
        physical controls, and optional exact dataset/atmosphere initialization.
    '''

    def __init__(self, doc: Document, *, config_file: Path = CONFIG_FILE,
                 schedule_initial: bool = True, launch_context=None,
                 shared_filter=None, model_class_factory=None, comparison_data=None):
        '''
        Purpose
        -------
        Build the linked native model/filter workspace from optional exact dataset and
        atmospheric context.

        Inputs
        ------
        doc: bokeh.document.Document
            Session document used for request arguments and callbacks.
        config_file: str or pathlib.Path
            Configuration-module path used to reconstruct the runtime settings.
        schedule_initial: bool
            Schedule the initial calculation after document construction when True.
        launch_context: dict or None
            Optional validated exact numerical dataset/model/atmosphere launch context.
        shared_filter: GaussianFilterExplorer or None
            Existing filter controller to reuse; None constructs a linked local filter.
        model_class_factory: callable or None
            Optional factory producing the linked native ModelExplorer subclass.
        comparison_data: ObservationData or None
            Loaded primary dataset whose exact kh/nu bins define dataset-mode model
            sampling.

        Outputs
        -------
        None
            Loads private solver definitions, validates/discloses initial physical
            defaults, shares native axes/parameters, adds one application root, and
            optionally schedules the first lazy model calculation.
        '''

        # Build the linked native model/filter workspace from optional exact dataset and
        # atmospheric context
        self.doc = doc
        self.async_models = doc.session_context is not None
        self.model_runner = LatestModelRunner(doc)
        self.filter_result: FilterResult | None = None
        config = _load_config(config_file)
        self.config = config
        project = config.get("komega_comparison", {}).get("vesa_2026_dir")
        if not project:
            raise KeyError("komega_comparison['vesa_2026_dir'] is required in config.py.")
        initial_parameters = {}
        atmosphere = None
        if launch_context is not None:
            from komega_bokeh_context import validate_context
            validate_context(launch_context)
            initial_parameters = dict(launch_context['model']['parameters'])
            if launch_context['dataset']['source_type'] == 'paired_cubes':
                source = launch_context.get('processing', {}).get('input_reference', {}).get('data', {})
                separation = source.get('resolved_delta_z_km', source.get('paired_cubes', {}).get('delta_z_km'))
                if separation is not None:
                    if not np.isfinite(separation) or float(separation) < 0:
                        raise ValueError('Recorded observational height separation must be finite and nonnegative.')
                    initial_parameters['dz'] = float(separation)
            atmosphere = launch_context.get('atmosphere')
            if 'N' in initial_parameters:
                initial_parameters = dict(initial_parameters)
                initial_parameters.setdefault('N2', initial_parameters.pop('N')**2)
        self.vesa = load_dispersion_explorer(str(project))
        definition = next(item for item in self.vesa.MODEL_DEFINITIONS if item.key == 'nc2009')
        bounds = []
        for item in definition.parameters:
            value = initial_parameters.get(item.key, item.default)
            if atmosphere is None and item.key in initial_parameters and not item.minimum <= value <= item.maximum:
                # Share the full physical inclination range across simulations,
                # rather than importing a new solver package for each average.
                bounds.append((item.key, 180. if item.key == 'theta_deg' else value))
        if bounds:
            self.vesa = load_dispersion_explorer(str(project), tuple(sorted(bounds)))
        if atmosphere is not None:
            from atmospheric_profiles import upgrade_atmosphere
            from komega_bokeh_context import atmospheric_initializations
            atmosphere = upgrade_atmosphere(atmosphere)
            atmosphere['initializations'], atmosphere['fallbacks'] = atmospheric_initializations(config, atmosphere)
        self.models = []
        if comparison_data is None and launch_context is not None and shared_filter is None:
            from observation_datasets import load_observation
            comparison_data = load_observation(validate_context(launch_context), config_file=config_file)
        self.comparison_axes = (None if comparison_data is None else
            (tuple(map(float, comparison_data.kh)), tuple(map(float, comparison_data.nu))))
        self.atmosphere = atmosphere
        self.atmosphere_info = Div(text='', sizing_mode='stretch_width',
            styles={'color': '#475569', 'font-size': '12px', 'overflow-wrap': 'anywhere'},
            name='komega:atmospheric_defaults')
        self._native_definitions = {}
        self.apply_filter = Toggle(label="Apply Filter", active=False, button_type="primary",
                                   width=390, name="komega:apply_filter")
        self.remove_filter = Button(label="Remove Filter", width=390, name="komega:remove_filter")
        self.remove_filter.on_click(lambda: setattr(self.apply_filter, "active", False))
        self.filter = (shared_filter if shared_filter is not None else
                       LinkedGaussianExplorer(doc, self, Path(config_file)))
        # The legacy filter controller adds its own root; compose its existing
        # widgets/plot below into a single application root instead.
        if shared_filter is None:
            doc.remove_root(self.filter.layout)

        self.config_file, self.launch_context = Path(config_file), launch_context
        self.coherence = CoherenceControls(doc, self._coherence_data, self._refresh_filter,
            loader=self._load_coherence_data if shared_filter is None else None,
            x_range=self.filter.plot.x_range, y_range=self.filter.plot.y_range)

        ModelExplorer = (model_class_factory or _linked_model_class)(self.vesa)
        for definition in self.vesa.MODEL_DEFINITIONS:
            adjustments = [item for item in definition.parameters
                           if not item.minimum <= item.default <= item.maximum]
            # Some current Vesa configs set a=0 for models whose established
            # interactive range excludes zero. Start those controls at their
            # supported endpoint and disclose the adjustment next to the model.
            bounded = replace(definition, parameters=tuple(
                replace(item, default=float(np.clip(item.default, item.minimum, item.maximum)))
                for item in definition.parameters
            ))
            self._native_definitions[definition.key] = bounded
            values = ((atmosphere or {}).get('initializations', {}).get(definition.key, {})
                      if atmosphere is not None else initial_parameters if definition.key == 'nc2009' else {})
            initialized = _expanded_definition(bounded, values)
            _allow_physical_ranges(self.vesa, [initialized])
            section = ModelExplorer(doc, initialized, self)
            if values:
                for key, widget in section.widgets.items():
                    widget.format = '0.000000' if key in {'a', 'cs', 'N2', 'wac'} else '0.000'
            if adjustments and not values:
                note = "; ".join(
                    f"{escape(item.label)}: configured {item.default:g}, starting at "
                    f"{np.clip(item.default, item.minimum, item.maximum):g} {escape(item.unit)}"
                    for item in adjustments
                )
                section.layout.children.insert(1, Div(
                    text=f"<p style='color:#475569;margin:4px'>Supported control range — {note}.</p>",
                    sizing_mode="stretch_width"))
            # Pan and zoom use the same coordinates on both sides and all tabs.
            for plot in section.plots:
                plot.x_range = self.filter.plot.x_range
                plot.y_range = self.filter.plot.y_range
            section.shared_x_range = self.filter.plot.x_range
            section.shared_y_range = self.filter.plot.y_range
            self.models.append(section)

        self.parameter_state = self.vesa.SharedParameterState(self.models)
        self.tabs = Tabs(
            tabs=[TabPanel(child=section.layout, title=MODEL_TAB_LABELS[section.definition.key])
                  for section in self.models],
            active=0, width=880, min_width=730, width_policy="fixed", name="model_tabs",
        )
        self.tabs.on_change("active", self._active_changed)
        self.apply_filter.on_change("active", self._filter_toggled)
        self.layout = self._build_layout()
        self.layout.children.insert(0, self.atmosphere_info)
        self.update_atmosphere_info('nc2009')
        doc.add_root(self.layout)
        doc.title = "Gaussian Filter & Dispersion k–ω Explorer"
        doc.theme = self.vesa._theme()
        self.models[0]._active = True
        # The inexpensive filter is ready before any model is lazily computed.
        self.filter._perform_recompute()
        if schedule_initial:
            self.models[0].schedule_recompute(delay_ms=20)

    def _coherence_data(self):
        '''
        Purpose
        -------
        Provide the default no-loaded-dataset coherence getter for the standalone linked
        workspace.

        Inputs
        ------
        None

        Outputs
        -------
        data: None
            Standalone coherence instead uses the configured or exact-launch baseline
            loader.
        '''

        # Provide the default no-loaded-dataset coherence getter for the standalone
        # linked workspace
        return None

    def set_comparison_grid(self, data):
        '''
        Purpose
        -------
        Replace dataset-mode sampling with the primary diagram's exact bins and
        invalidate stale model solves.

        Inputs
        ------
        data: ObservationData or None
            Primary loaded dataset supplying exact Mm^-1/mHz axes, or None for native
            default sampling.

        Outputs
        -------
        None
            Resets ordering caches/results and schedules active lazy recomputation only
            when axes change.

        Notes
        -----
        Use the primary diagram's exact bins for all dataset-mode solves.
        '''
        # Replace dataset-mode sampling with the primary diagram's exact bins and
        # invalidate stale model solves
        axes = (None if data is None else
                (tuple(map(float, data.kh)), tuple(map(float, data.nu))))
        if axes == self.comparison_axes:
            return
        self.comparison_axes = axes
        for section in self.models:
            section._solve_generation = getattr(section, '_solve_generation', 0) + 1
            section._sync_comparison_grid()
            section._last_ordering_result = None
            section._ordered_state_cache.clear()
            section._clear_plot('Loading dataset grid…')
            section._dirty = True
            section.schedule_recompute(delay_ms=20)

    def _load_coherence_data(self):
        '''
        Purpose
        -------
        Load the exact launched dataset or native configured original-cube baseline for
        measured coherence.

        Inputs
        ------
        None

        Outputs
        -------
        data: ObservationData
            Original/post-magnetogram cubes, native phase axes, sampling, and
            provenance.

        Notes
        -----
        Legacy tool uses the exact launch dataset, or the configured height pair.
        '''
        # Load the exact launched dataset or native configured original-cube baseline
        # for measured coherence
        from observation_datasets import Observation, ObservationData, load_observation
        if self.launch_context is not None:
            from komega_bokeh_context import validate_context
            return load_observation(validate_context(self.launch_context), config_file=self.config_file)
        import copy
        import pipeline
        from dopplergram_recalculation import input_reference, load_baseline
        from gaussian_filter_explorer import PreviewGeometry
        config = copy.deepcopy(self.config)
        config['_module_dir'] = str(self.config_file.parent)
        config = pipeline.prepare_runtime_config(config)
        baseline = load_baseline(input_reference(config), self.config_file)
        source = baseline.config['data']
        files = ((Path(source['file']),) if source['source_type'] == 'single_cube'
                 else tuple(Path(source[key]) for key in ('v1', 'v2')))
        record = Observation('configured:' + '|'.join(map(str, files)),
                             'Configured Dopplergram height pair', source['source_type'], files)
        nt, ny, nx = baseline.cubes[0].shape
        sampling = baseline.config['time_distance']
        geometry = PreviewGeometry(nx, nt, sampling['dt'], sampling['p_dx_Mm'], 'Native input sampling')
        return ObservationData(record, baseline.values, baseline.kh, baseline.nu, geometry,
                               ny, baseline.metadata, baseline.cubes, baseline.config)

    def update_atmosphere_info(self, model_key):
        '''
        Purpose
        -------
        Show the selected simulation snapshot and physical height pair when available.

        Inputs
        ------
        model_key: str
            Compatibility model identifier; currently unused by the shared atmosphere
            summary.

        Outputs
        -------
        None
            Updates the atmosphere-information Div; the retained model_key argument does
            not alter its current contents.
        '''

        # Show the selected simulation snapshot and physical height pair when available
        record = self.atmosphere
        if record is None:
            self.atmosphere_info.text = ''
            return
        if record.get('status') == 'available':
            heights = record['height_pair_km']
            provenance = record['provenance']
            text = (f'Simulation defaults: {escape(record["model"])} · '
                    f'{heights[0]:g}–{heights[1]:g} km · snapshot t = {provenance["snapshot_time_s"]:g} s.')
        else:
            text = ''
        self.atmosphere_info.text = text

    def set_atmospheric_defaults(self, record):
        '''
        Purpose
        -------
        Replace every native model's dataset defaults and invalidate stale cached
        solves.

        Inputs
        ------
        record: dict or None
            Dataset-specific atmosphere initializations/fallbacks, or None to restore
            native model definitions.

        Outputs
        -------
        None
            Upgrades available records, rebuilds per-model definitions/ranges, resets
            widgets under suppression, clears ordering caches, and synchronizes shared
            physical values.

        Notes
        -----
        On dataset changes, replace defaults for every model and clear stale solves.
        '''
        # Replace every native model's dataset defaults and invalidate stale cached
        # solves
        if record is not None:
            from atmospheric_profiles import upgrade_atmosphere
            record = upgrade_atmosphere(record)
        if record is not None and 'initializations' not in record:
            from komega_bokeh_context import atmospheric_initializations
            import copy
            record = copy.deepcopy(record)
            record['initializations'], record['fallbacks'] = atmospheric_initializations(self.config, record)
        self.atmosphere = record
        # Replace each native model's defaults/ranges while suppressing intermediate
        # physical callbacks
        for section in self.models:
            values = (record or {}).get('initializations', {}).get(section.definition.key, {})
            definition = _expanded_definition(self._native_definitions[section.definition.key], values)
            _allow_physical_ranges(self.vesa, [definition])
            if section._pending_callback is not None:
                try:
                    self.doc.remove_timeout_callback(section._pending_callback)
                except ValueError:
                    pass
                section._pending_callback = None
            section._suppress_callbacks = True
            try:
                section.definition = definition
                for item in definition.parameters:
                    widget = section.widgets[item.key]
                    widget.start, widget.end = item.minimum, item.maximum
                    widget.format = ('0.00000000' if item.key in {'N2', 'wac'} else
                                     ('0.000000' if item.key in {'a', 'cs'} else '0.000') if record is not None else '0[.]00')
                    widget.value = item.default
            finally:
                section._suppress_callbacks = False
            section._clear_plot('Loading atmospheric defaults…')
            section._last_ordering_result = None
            section._ordered_state_cache.clear()
            section._dirty = True
            section.schedule_recompute(delay_ms=20)
        # Synchronize common physical values after every model definition has been
        # updated
        shared = {}
        for section in self.models:
            for key, widget in section.widgets.items():
                shared.setdefault(key, float(widget.value))
        self.parameter_state.apply(shared, notify=False)

    def _build_layout(self):
        '''
        Purpose
        -------
        Compose native filter/coherence controls and lazy model tabs in a responsive
        workspace.

        Inputs
        ------
        None

        Outputs
        -------
        layout: bokeh.models.Column
            Application layout with shared physical ranges and browser-local
            presentation reflow; no new numerical calculation occurs here.
        '''

        # Compose native filter/coherence controls and lazy model tabs in a responsive
        # workspace
        plot = self.filter.plot
        plot.width, plot.height = 430, 550
        plot.toolbar_location = "right"
        plot.title.text_font_size = "15pt"
        plot.yaxis[0].axis_label = "ν [mHz]"
        plot.x_range.end, plot.y_range.end = self.vesa.DEFAULT_DOMAIN[1], self.vesa.DEFAULT_DOMAIN[3]
        for axis in (plot.xaxis[0], plot.yaxis[0]):
            axis.axis_label_text_font_size = "16pt"
            axis.major_label_text_font_size = "13pt"
        for slider in self.filter.sliders.values():
            slider.width = 275
        self.filter.status.width = 390
        reset_filter = Button(label="Restore filter defaults", width=390)
        reset_filter.on_click(self._reset_filter)
        sidebar = column(
            Div(text="<h2 style='margin:0'>Gaussian filter</h2>", width=390),
            *[self.filter.numeric_controls[key].layout for key in PARAMETER_KEYS],
            reset_filter, self.apply_filter, self.remove_filter, plot, self.coherence.layout,
            width=440, styles={"padding": "8px", "position": "sticky", "top": "0"},
            name="komega:filter_panel",
        )
        self.workspace = GridBox(
            children=[(sidebar, 0, 0), (self.tabs, 0, 1)], spacing=12,
            sizing_mode="stretch_width", name="komega:workspace",
        )
        # Native Bokeh layout reflows into one column in a narrow browser panel.
        # Numerical callbacks remain Python; this only selects the layout.
        self.doc.js_on_event(DocumentReady, CustomJS(
            args={"workspace": self.workspace, "sidebar": sidebar, "tabs": self.tabs,
                  "layouts": [section.layout for section in self.models],
                  "grids": [section.plot_grid for section in self.models],
                  "plots": [plot for section in self.models for plot in section.plots]},
            code="""
                const media = window.matchMedia('(max-width: 1200px)');
                const update = () => {
                    workspace.children = media.matches
                        ? [[sidebar, 0, 0], [tabs, 1, 0]]
                        : [[sidebar, 0, 0], [tabs, 0, 1]];
                    sidebar.styles = media.matches
                        ? {padding: '8px'}
                        : {padding: '8px', position: 'sticky', top: '0'};
                    const width = Math.max(730, window.innerWidth - (media.matches ? 16 : 452));
                    tabs.width = width;
                    for (const layout of layouts) {
                        layout.sizing_mode = null;
                        layout.width_policy = 'fixed';
                        layout.width = width;
                    }
                    for (const grid of grids) {
                        grid.sizing_mode = null;
                        grid.width_policy = 'fixed';
                        grid.width = width;
                    }
                    const panelWidth = Math.max(340, Math.floor(width / 2));
                    for (const plot of plots) {
                        plot.width = panelWidth;
                        plot.height = panelWidth;
                    }
                };
                update();
                window.addEventListener('resize', update);
            """,
        ))
        return column(
            Div(text=("<h1 style='margin:0 0 6px'>Gaussian Filter & Dispersion k–ω Explorer</h1>"
                      "<p style='margin:0;color:#475569'>Construct a filter on the left and adjust a model "
                      "on the right. Apply Filter multiplies every solution by the filter. "
                      "Pan and zoom are linked; select Wheel Zoom in a toolbar to enable it.</p>"),
                sizing_mode="stretch_width", styles={"padding": "12px"}),
            self.workspace,
            sizing_mode="stretch_width", name="application_root",
        )

    def _reset_filter(self):
        '''
        Purpose
        -------
        Restore native Gaussian defaults under callback suppression and request one
        immediate product update.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Reuses the existing filter controller and debounce path.
        '''

        # Restore native Gaussian defaults under callback suppression and request one
        # immediate product update
        self.filter._suppress_callbacks = True
        try:
            for key, value in self.filter.defaults.items():
                self.filter.sliders[key].value = value
        finally:
            self.filter._suppress_callbacks = False
        self.filter.schedule_recompute(delay_ms=0)

    def _active_changed(self, attr, old, new):
        '''
        Purpose
        -------
        Activate only the selected native model tab.

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
            Retains lazy calculation for all inactive model sections.
        '''

        # Activate only the selected native model tab
        for index, section in enumerate(self.models):
            section.set_active(index == new)

    def _filter_toggled(self, attr, old, new):
        '''
        Purpose
        -------
        Refresh model presentation after the filter-application toggle changes.

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
            Reuses existing roots and current Gaussian inputs.
        '''

        # Refresh model presentation after the filter-application toggle changes
        self._refresh_filter()

    def filter_changed(self, result: FilterResult | None):
        '''
        Purpose
        -------
        Store the newest exact filter result and refresh linked model displays.

        Inputs
        ------
        result: FilterResult or None
            Native exact Gaussian product received from the linked filter controller.

        Outputs
        -------
        None
            None represents an unavailable/failed filter result.
        '''

        # Store the newest exact filter result and refresh linked model displays
        self.filter_result = result
        self._refresh_filter()

    @batch_model_graph
    def _refresh_filter(self):
        '''
        Purpose
        -------
        Refresh retained model views using current Gaussian and coherence state.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Runs inside the model-graph update context and does not request new
            dispersion roots.
        '''

        # Refresh retained model views using current Gaussian and coherence state
        for section in self.models:
            section.refresh_filter()


def build_document(doc: Document, *, config_file: Path = CONFIG_FILE,
                   schedule_initial: bool = True, launch_context=None) -> KomegaExplorer:
    '''
    Purpose
    -------
    Construct the standalone linked Gaussian and dispersion Bokeh workspace.

    Inputs
    ------
    doc: bokeh.document.Document
        Session document used for request arguments and callbacks.
    config_file: str or pathlib.Path
        Configuration-module path used to reconstruct the runtime settings.
    schedule_initial: bool
        Schedule the initial calculation after document construction when True.
    launch_context: dict or None
        Optional validated exact numerical dataset/model/atmosphere launch context.

    Outputs
    -------
    explorer: KomegaExplorer
        Created document-root workspace with optional exact launch context and initial
        lazy model calculation.
    '''

    # Construct the standalone linked Gaussian and dispersion Bokeh workspace
    return KomegaExplorer(doc, config_file=config_file, schedule_initial=schedule_initial,
                         launch_context=launch_context)


__all__ = ["KomegaExplorer", "build_document", "load_dispersion_explorer"]
