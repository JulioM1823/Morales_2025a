#!/usr/bin/env python3
'''
Purpose
-------
Alias entry point for the xcorrj benchmark harness.

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

from __future__ import annotations

# Import the test dependencies and implementation modules used by these checks.
import importlib.util
import sys
from pathlib import Path


_IMPLEMENTATION_PATH = Path(__file__).resolve().with_name("benchmark_xcorrj.py")
_SPEC = importlib.util.spec_from_file_location("_tests_benchmark_xcorrj", _IMPLEMENTATION_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Could not import benchmark_xcorrj from {_IMPLEMENTATION_PATH}.")

_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

__all__ = [name for name in vars(_MODULE) if not name.startswith("_")]
globals().update({name: getattr(_MODULE, name) for name in __all__})


if __name__ == "__main__":
    raise SystemExit(_MODULE.main())
