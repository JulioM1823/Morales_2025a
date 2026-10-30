'''
Purpose
-------
Legacy migration entry points and geometry-migration safety regressions.

The retired filter_N/move-based hierarchy is intentionally no longer asserted.

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
from pathlib import Path
import importlib.util
import json
import subprocess
import sys

import numpy as np
from astropy.io import fits

ROOT=Path(__file__).resolve().parents[2]
TD=ROOT/'Code/Time-Distance'
sys.path.insert(0,str(TD))
from migrate_geometry_outputs import migrate
from migrate_output_hierarchy import infer_filtering_from_name, infer_geometry_from_name


def test_both_legacy_cli_entry_points_forward_to_geometry_manager():
    '''
    Purpose
    -------
    Verify both legacy CLI entry points forward to geometry manager.

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

    for filename in ('migrate_output_hierarchy.py','migrate_figure_animation_hierarchy.py'):
        result=subprocess.run([sys.executable,str(TD/filename),'--help'],capture_output=True,text=True,check=True)
        assert '--figure-root' in result.stdout
        assert '--apply' in result.stdout
        assert 'Non-destructive' in result.stdout


def test_filename_without_original_provenance_is_flagged_without_modification(tmp_path):
    '''
    Purpose
    -------
    Verify filename without original provenance is flagged without modification.

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

    legacy=tmp_path/'legacy';legacy.mkdir()
    product=legacy/'hx_10g_v3_0km_220km_gaussian_filtered_gauss_ck_2_wk_2_cf_1_5_wf_1_5_phase_diff.jpeg'
    product.write_bytes(b'figure')
    data=tmp_path/'legacy_data';data.mkdir()
    report=migrate(data,legacy,tmp_path/'Data',figure_root=tmp_path/'Figures',apply=True)
    assert report['counts']=={'flagged':1}
    assert product.read_bytes()==b'figure'
    assert not list((tmp_path/'Figures').rglob('*.jpeg'))


def test_complete_figure_and_data_provenance_create_linked_views(tmp_path):
    '''
    Purpose
    -------
    Verify complete figure and data provenance create linked views.

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

    data=tmp_path/'legacy_data';data.mkdir()
    legacy=tmp_path/'legacy_figures';legacy.mkdir()
    original=tmp_path/'simulation_hx_10G.nc';original.write_bytes(b'original source')
    stem='hx_10g_v3_20km_240km_unfiltered'
    product=data/(stem+'_komega.fits')
    array=np.arange(6,dtype=np.float32).reshape(2,3)
    fits.writeto(product,array)
    reference=dict(data=dict(source_type='single_cube',file=str(original),observable='v3',h1=0,h2=1,
        resolved_h1_index=0,resolved_h2_index=1,resolved_h1_km=20.,resolved_h2_km=240.),
        sampling={'dt':30.,'p_dx_Mm':.16},filtering={'enabled':False,'filter_sequence':[]},
        magnetogram_mode={'single_cube':'bottom'})
    product.with_suffix('.inputs.json').write_text(json.dumps(reference))
    figure=legacy/(stem+'_phase_diff.jpeg');figure.write_bytes(b'figure')
    report=migrate(data,legacy,tmp_path/'Data',figure_root=tmp_path/'Figures',apply=True)
    assert report['counts']=={'linked':2}
    for record in report['records']:
        destination=Path(record['destination'])
        assert destination.is_symlink() and destination.samefile(record['source'])
        root=tmp_path/('Data' if destination.is_relative_to(tmp_path/'Data') else 'Figures')
        groups=list((root/'simulations/v3/Annulus/hx/h10G/delta_z_220_km').rglob('*'+destination.suffix))
        assert any(alias.is_symlink() and alias.samefile(destination) for alias in groups)
    np.testing.assert_array_equal(fits.getdata(product),array)
    assert figure.read_bytes()==b'figure'


def test_legacy_filter_and_geometry_parsers_preserve_historical_values():
    '''
    Purpose
    -------
    Verify legacy filter and geometry parsers preserve historical values.

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

    filtering=infer_filtering_from_name('25apr2019_gaussian_filtered_gauss_ck_2_wk_3_cf_1_5_wf_2_b_gt_50g.fits')
    assert filtering['gaussian']['central_f']==1.5
    assert filtering['magnetogram']['threshold_G']==50.
    assert filtering['magnetogram']['selection']=='magnetic'
    assert infer_geometry_from_name('hx_10g_v3_0km_220km_north_xc.fits')=='north'
