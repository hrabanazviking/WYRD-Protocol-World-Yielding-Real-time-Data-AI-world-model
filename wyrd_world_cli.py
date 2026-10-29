#!/usr/bin/env python3
"""WYRD World CLI — root shim (Phase E2).

The implementation lives in ``src/wyrd_world_cli.py``, shipped as a
top-level module by the package build (see ``[project.scripts]`` and
``[tool.setuptools] py-modules`` in pyproject.toml) so the installed
``wyrd-world`` console script can import it from any directory.

Running ``python wyrd_world_cli.py`` from the repo root — the
documented invocation — still works exactly as before: this shim
loads the implementation by path and calls its ``main()``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parent / "src" / "wyrd_world_cli.py"

sys.path.insert(0, str(_IMPL.parent))

_spec = importlib.util.spec_from_file_location("wyrd_world_cli_impl", _IMPL)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

main = _module.main

if __name__ == "__main__":
    main()
