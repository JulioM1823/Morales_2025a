'''
Purpose
-------
Load the shared numerical-control or magnetic-geometry support module from the
configured Vesa checkout.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for vesa_support.py.

Notes
-----
Load shared, solver-independent utilities from the existing Vesa dependency.
'''
# Import the libraries and shared helpers used by this module
from functools import lru_cache
import importlib.util
from pathlib import Path


@lru_cache(maxsize=None)
def support_module(name):
    '''
    Purpose
    -------
    Import an allowed shared support module from the configured Vesa source directory.

    Inputs
    ------
    name: str
        Allowed module name: numeric_controls or magnetic_geometry.

    Outputs
    -------
    module: types.ModuleType
        Executed support module; unsupported names raise ValueError and missing
        files/import failures propagate.
    '''

    # Import an allowed shared support module from the configured Vesa source directory
    if name not in {'numeric_controls', 'magnetic_geometry'}:
        raise ValueError(name)
    # Read the same configured dependency location as the model workspace.
    spec = importlib.util.spec_from_file_location('_morales_support_config', Path(__file__).with_name('config.py'))
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    path = Path(config.vesa_2026_dir)/'Code'/'diagnostic_diagram'/(name+'.py')
    spec = importlib.util.spec_from_file_location('_morales_support_'+name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
