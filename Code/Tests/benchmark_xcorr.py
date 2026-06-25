#!/usr/bin/env python3
"""Alias entry point for the xcorrj benchmark harness."""

from __future__ import annotations

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
