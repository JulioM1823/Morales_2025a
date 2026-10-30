'''
Purpose
-------
Megaplot -> standalone view -> exact data and named 3MAG initial inputs.

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
import ast
import copy
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from bokeh.document import Document
import pytest

TD = Path(__file__).resolve().parents[1] / 'Time-Distance'
sys.path.insert(0, str(TD))
import comparison_gallery as gallery
import komega_bokeh_context as context
import komega_explorer as models
import observation_komega_explorer as observations
from gaussian_filter_explorer import _load_config, CONFIG_FILE


def sample(tmp_path, source_type, strength=2.):
    '''
    Purpose
    -------
    Write a synthetic k-omega product and assemble its recorded model-input context.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    source_type: str
        Dataset mode, such as single_cube or paired_cubes.

    strength: float
        Synthetic field/Alfven-speed parameter in the units declared by the fixture.

    Outputs
    -------
    fixture: tuple
        Numerical dataset record and runtime configuration. Write the FITS
        image with native wavenumber/frequency axes and a nonfinite sample.
    '''

    # Write a known phase array, retaining a nonfinite sample to exercise mask handling.
    values = np.arange(80, dtype=float).reshape(8, 10) - 40.
    values[2, 3] = np.nan
    path = tmp_path / ('renamed ' + str(strength) + '.fits')
    header = fits.Header(dict(SRCMODE=source_type, BUNIT='deg',
        CTYPE1='KH', CTYPE2='NU', CUNIT1='1/Mm', CUNIT2='mHz',
        CRVAL1=0., CDELT1=.5, CRVAL2=0., CDELT2=1.,
        DT_S=10., DX_MM=.2, NX_ORIG=16, NY_ORIG=16, NT_ORIG=20))
    fits.writeto(path, values, header, overwrite=True)
    config = copy.deepcopy(_load_config(CONFIG_FILE))
    # This fixture deliberately exercises legacy schema-1 layer metadata.
    config['atmospheric_profiles']['enabled'] = False
    config['data'].update(source_type=source_type, resolved_h1_km=440., resolved_h2_km=660.)
    config['time_distance'].update(dt=10., p_dx_Mm=.2)
    config['paths']['figure_dir'] = str(tmp_path)
    metadata = {'dispersion_height_pair': {'a_by_height_km_s': [strength, strength+2.],
        'theta_by_height_deg': [80., 100.], 'phi_by_height_deg': [179., -179.],
        'height_values_km': [440., 660.]}, 'mean_sound_speed_km_s_between_heights': 7.2}
    data = dict(data_file=path, values=values, k_axis=np.arange(8)*.5,
                nu_axis=np.arange(10), orientation=metadata)
    return data, config


def decode(url):
    '''
    Purpose
    -------
    Decode the saved context query parameter using the normal Bokeh request-context
    path.

    Inputs
    ------
    url: str
        Launch URL containing the encoded Bokeh context.

    Outputs
    -------
    context: dict
        Validated context reconstructed from the URL query.
    '''

    raw = parse_qs(urlsplit(url).query)['context'][0].encode()
    return context.request_context(SimpleNamespace(session_context=SimpleNamespace(
        request=SimpleNamespace(arguments={'context': [raw]}))))


@pytest.mark.parametrize('comparison_type', list(gallery.COMPARISON_VIEWERS))
def test_all_galleries_launch_exact_observation_and_multiple_simulations(tmp_path, monkeypatch, comparison_type):
    '''
    Purpose
    -------
    Verify all galleries launch exact observation and multiple simulations.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    monkeypatch: pytest.MonkeyPatch
        Fixture used to replace dependencies or settings for this test.

    comparison_type: str
        Gallery comparison mode selected by the test.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    fig, axes = plt.subplots(1, 3, figsize=(10, 3))
    samples = [sample(tmp_path, 'paired_cubes', 0.),
               sample(tmp_path, 'single_cube', 2.), sample(tmp_path, 'single_cube', 8.)]
    for ax, (data, config) in zip(axes, samples):
        ax.imshow(data['values'].T, origin='lower')
        context.register_panel(ax, data, config)
    image = tmp_path / (comparison_type + '_v3_440km_660km_filters_3_demo.jpeg')
    fig.savefig(image, bbox_inches='tight', pad_inches=.18)
    context.publish_comparison_navigation(fig, image)
    plt.close(fig)
    results = gallery.write_default_comparison_viewers(tmp_path)
    page = results[comparison_type]['full_resolution_output_files'][0].read_text()
    targets = json.loads(re.search(r'const targets = (.*);', page).group(1))
    targets = [t for t in targets if t.get('panelKind') == 'komega']
    assert len(targets) == 3
    assert 'Open in Bokeh' in page
    assert set(targets[0]['bokeh']) == {'workspace'}
    for target, (data, config) in zip(targets, samples):
        launch = target['bokeh']['workspace']
        assert urlsplit(launch['url']).path == '/integrated_komega_bokeh_app'
        context_value = decode(launch['url'])
        assert context_value == launch['context']
        data_app = observations.build_document(Document(), launch_context=context_value,
            product_roots=[], raw_roots=[], registry_file=tmp_path/'registry.json', schedule_initial=False)
        assert data_app.selected_id == context_value['dataset']['id']
        np.testing.assert_equal(data_app.data.values, data['values'])
        assert not data_app.apply_filter.active
        model_app = models.build_document(Document(), launch_context=context_value, schedule_initial=False)
        assert model_app.tabs.active == 0
        model = model_app.models[0]
        assert model.definition.key == 'nc2009'
        if config['data']['source_type'] == 'single_cube':
            expected = {'a': np.mean(data['orientation']['dispersion_height_pair']['a_by_height_km_s']),
                        'cs': 7.2, 'theta_deg': 90., 'phi_deg': 180., 'dz': 220.}
            assert model._current_values().items() >= expected.items()
            monkeypatch.setitem(model_app.vesa.RESOLUTION_OPTIONS, 'interactive', (8, 10))
            model._perform_recompute()
            assert model.last_result is not None, model.status.text
        else:
            normal = models.build_document(Document(), schedule_initial=False)
            assert model._current_values() == normal.models[0]._current_values()


def test_plot_only_array_is_preserved_and_can_be_opened(tmp_path):
    '''
    Purpose
    -------
    Verify plot only array is preserved and can be opened.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    data, config = sample(tmp_path, 'paired_cubes')
    data['computed_for_plot'] = True
    data['cube_shape'] = [21, 18, 16]
    data['values'] = data['values'] + .123456789
    image = tmp_path/'figure.jpeg'
    record = context.publish_context(image, data, config)
    page = context.write_standalone_html(image, record)
    assert 'Open in Bokeh' in page.read_text()
    selected = context.validate_context(record['links']['workspace']['context'])
    assert selected.files[0] != data['data_file']
    app = observations.build_document(Document(), launch_context=record['context'],
        product_roots=[], raw_roots=[], registry_file=tmp_path/'registry.json', schedule_initial=False)
    np.testing.assert_equal(app.data.values, data['values'])
    assert app.data.geometry.nt == 21
    assert app.data.ny == 18


def test_navigation_covers_data_and_text_panels_without_colorbar_hotspots(tmp_path):
    '''
    Purpose
    -------
    Verify navigation covers data and text panels without colorbar hotspots.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    fig, axes = plt.subplots(1, 3, figsize=(10, 3))
    data, config = sample(tmp_path, 'paired_cubes')
    image = axes[0].imshow(data['values'].T, origin='lower')
    fig.colorbar(image, ax=axes[0])
    context.register_panel(axes[0], data, config)
    axes[1].plot([0, 1], [2, 3])
    axes[1].set_title('Diagnostic')
    axes[2].axis('off')
    axes[2].text(.5, .5, 'Gaussian filtering disabled', ha='center')
    output = tmp_path/'panels.jpeg'
    fig.savefig(output, bbox_inches='tight', pad_inches=.18)
    context.publish_comparison_navigation(fig, output)
    record = json.loads(context.navigation_path(output).read_text())
    plt.close(fig)
    assert record['all_axes']
    assert len(record['targets']) == 3
    assert [target['panelKind'] for target in record['targets']] == ['komega', 'figure', 'figure']
    assert all(target['bounds']['width'] > 0 for target in record['targets'])


def test_subplot_labels_and_margins_link_without_overlapping_adjacent_panels():
    '''
    Purpose
    -------
    Verify subplot labels and margins link without overlapping adjacent panels.

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

    targets = [{'bounds': dict(left=x, top=y, width=30., height=30.)}
               for y in (10., 60.) for x in (10., 60.)]
    originals = copy.deepcopy(targets)
    gallery.subplot_hit_bounds(targets)
    assert targets[0]['hitBounds']['left'] < 10.
    assert targets[0]['hitBounds']['top'] < 10.
    assert targets[0]['hitBounds']['left'] + targets[0]['hitBounds']['width'] == 50.
    assert targets[1]['hitBounds']['left'] == 50.
    assert targets[0]['hitBounds']['top'] + targets[0]['hitBounds']['height'] == 50.
    assert targets[2]['hitBounds']['top'] == 50.
    assert [t['bounds'] for t in targets] == [t['bounds'] for t in originals]


def test_abutting_seven_panel_columns_are_partitioned_uniformly():
    '''
    Purpose
    -------
    Verify abutting seven panel columns are partitioned uniformly.

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

    assert gallery._expand_segments_to_count([(10, 709)], 7) == [
        (10+100*i, 109+100*i) for i in range(7)]
    assert gallery._expand_segments_to_count([(10, 309), (400, 799)], 7) == [
        (10+100*i, 109+100*i) for i in range(3)] + [(400+100*i, 499+100*i) for i in range(4)]


def test_short_filter_row_margins_do_not_overlap_the_wider_row_above():
    '''
    Purpose
    -------
    Verify short filter row margins do not overlap the wider row above.

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

    targets = [{'bounds': dict(left=x, top=10., width=30., height=30.)}
               for x in (5., 35., 65.)]
    targets.append({'bounds': dict(left=35., top=50., width=30., height=30.)})
    gallery.subplot_hit_bounds(targets)
    lower = targets[-1]['hitBounds']
    assert lower['left'] < 35.
    for upper in targets[:-1]:
        hit = upper['hitBounds']
        assert hit['top'] + hit['height'] == lower['top']
    assert [target['bounds']['height'] for target in targets] == [30.]*4


@pytest.mark.parametrize('supplied_index', [False, True])
def test_identical_image_names_require_matching_scientific_filter_metadata(tmp_path, supplied_index):
    '''
    Purpose
    -------
    Verify identical image names require matching scientific filter metadata.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    supplied_index: bool
        Whether the lookup is passed a precomputed image index.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    request = 'hx_100g_v3_440km_660km_gaussian_filtered_gauss_ck_2_5_wk_1_cf_5_wf_1_5'
    stem = gallery._clean_source_image_stem(request + '_komega')
    images = []
    for folder, parameters in [('filter_1', (1., 1., 4., 1.)),
                               ('filter_7', (2.5, 1., 5., 1.5))]:
        root = tmp_path/folder
        root.mkdir()
        (root/'filter_parameters.txt').write_text(
            'filtering.filter_sequence: [gaussian]\n' + '\n'.join(
                f'filtering.gaussian.{key}: {value}' for key, value in zip(
                    ('central_k', 'width_k', 'central_f', 'width_f'), parameters)))
        image = root/(stem + '.jpeg')
        image.write_bytes(b'original image')
        images.append(image)
    def lookup():
        '''
        Purpose
        -------
        Find the exact source-panel image with or without the optional prebuilt stem
        index.

        Inputs
        ------
        None
            Uses the surrounding fixture or object state where needed.

        Outputs
        -------
        image: pathlib.Path or None
            Result of the source-panel lookup for the enclosing recorded request.
        '''

        index = gallery._build_image_stem_index(tmp_path) if supplied_index else None
        return gallery._find_source_panel_image(tmp_path, request, 'komega', index)
    assert lookup() == images[1]
    images[1].unlink()
    # A sole remaining image with the wrong filter must not be substituted.
    assert lookup() is None


def test_legacy_without_numerical_context_never_substitutes_another_dataset(tmp_path):
    '''
    Purpose
    -------
    Verify legacy without numerical context never substitutes another dataset.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    plot = gallery.ComparisonPlot(
        'field_orientation_comparison', tmp_path/'comparison.jpeg', '',
        440., 660., None, None,
    )
    target = {'id': 'legacy-komega', 'label': 'legacy k-omega',
        'src': '../legacy.jpeg', 'panelKind': 'komega',
        'bounds': {'left': 0., 'top': 0., 'width': 100., 'height': 100.}}
    page = gallery.render_full_resolution_view_html(
        plot, 'Field Orientation Comparison', '440-660 km',
        navigation_targets=[target], document_dir=tmp_path,
    )
    assert page.count('<a data-bokeh-workspace>') == 1
    assert 'Open in Bokeh' in page
    assert 'Open Integrated k–ω Workspace in Bokeh' not in page
    assert 'Open Dataset &amp; Filter in Bokeh' not in page
    assert 'Open Models &amp; Filter in Bokeh' not in page
    assert 'datasetLink' not in page
    assert 'modelLink' not in page
    assert '/observation_komega_bokeh_app' not in page
    assert '/komega_bokeh_app' not in page
    assert 'No dataset will be substituted' in page
    assert 'workspaceLink.removeAttribute("href")' in page


def test_zero_field_and_legacy_averages_use_metadata_without_model_defaults(tmp_path):
    '''
    Purpose
    -------
    Verify zero field and legacy averages use metadata without model defaults.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    data, config = sample(tmp_path, 'single_cube', 0.)
    data['orientation']['dispersion_height_pair']['a_by_height_km_s'] = [0., 0.]
    record = context.publish_context(tmp_path/'zero.jpeg', data, config)
    model = models.build_document(Document(), launch_context=record['context'], schedule_initial=False)
    assert model.models[0].widgets['a'].value == 0.
    normal = models.build_document(Document(), schedule_initial=False)
    assert normal.models[0].widgets['a'].start == 0.
    legacy = {'alfven_speed_km_s': 1.23, 'theta_mean_h1_deg': 80., 'theta_mean_h2_deg': 100.,
              'phi_mean_h1_deg': 179., 'phi_mean_h2_deg': -179.,
              'mean_sound_speed_km_s_between_heights': 6.7}
    assert context.simulation_parameters(config, legacy) == {'a': 1.23, 'theta_deg': 90.,
                                                            'phi_deg': 180., 'dz': 220., 'cs': 6.7}
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError):
        context.simulation_parameters(config, {})


def test_bad_context_cannot_silently_select_another_dataset(tmp_path):
    '''
    Purpose
    -------
    Verify bad context cannot silently select another dataset.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    data, config = sample(tmp_path, 'paired_cubes')
    record = context.publish_context(tmp_path/'example.jpeg', data, config)
    value = copy.deepcopy(record['context'])
    value['dataset']['id'] = 'fits:wrong-file.fits'
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='disagree'):
        context.validate_context(value)
    value = copy.deepcopy(record['context'])
    value['model']['parameters'] = {'a': 2.}
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError, match='Observational'):
        context.validate_context(value)
    assert context.request_context(SimpleNamespace(session_context=None)) is None
    # Require the expected ValueError from this failure case.
    with pytest.raises(ValueError):
        context.request_context(SimpleNamespace(session_context=SimpleNamespace(
            request=SimpleNamespace(arguments={'context': [b'{bad json']}))))


def test_notebook_save_paths_publish_context(tmp_path):
    '''
    Purpose
    -------
    Verify notebook save paths publish context.

    Inputs
    ------
    tmp_path: pathlib.Path
        Isolated temporary directory supplied by pytest.

    Outputs
    -------
    None
        Complete this regression case; report mismatches through the test
        assertions and expected-exception checks.
    '''

    nb = json.loads((TD/'plots.ipynb').read_text())
    trees = [ast.parse(''.join(cell['source'])) for cell in nb['cells'] if cell['cell_type']=='code']
    functions = {node.name: node for tree in trees for node in tree.body if isinstance(node, ast.FunctionDef)}
    # Execute the actual ordinary save helper, including its metadata hook.
    ns = {'Path': Path, 'publish_comparison_navigation': context.publish_comparison_navigation}
    exec(compile(ast.Module(body=[functions['maybe_save_figure']], type_ignores=[]), 'plots.ipynb', 'exec'), ns)
    fig, ax = plt.subplots()
    data, config = sample(tmp_path, 'paired_cubes')
    ax.imshow(data['values'].T)
    context.register_panel(ax, data, config)
    saved = ns['maybe_save_figure'](fig, 'field_strength_comparison_v3_440km_660km_example.jpeg', figure_dir=tmp_path)
    assert context.navigation_path(saved).is_file()
    plt.close(fig)
    for name in ['make_field_strength_comparison_plot','make_field_orientation_comparison_plot',
                 'make_gaussian_filter_comparison_plot','make_paired_cubes_gaussian_filter_comparison_plot']:
        assert 'register_panel' in ast.unparse(functions[name])
    assert 'publish_context' in ast.unparse(functions['make_komega_plot'])
    assert 'publish_comparison_navigation' in ast.unparse(functions['save_gaussian_filter_comparison_figure'])
