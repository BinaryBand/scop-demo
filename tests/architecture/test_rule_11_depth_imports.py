"""Contract tests for architecture rule 11: depth imports only.

Rule 11 is documented in ARCHITECTURE.md as the requirement that a file may only
import from deeper modules, never from a neighbour or anything closer to root.
The concrete example called out in the doc is AppDispatcher, which must resolve
concrete apps through app.registry rather than importing sibling app modules.
"""

from __future__ import annotations

from pathlib import Path

from scop.utils.code import imported_modules

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER_PATH = ROOT / "scop" / "app" / "dispatcher.py"


def test_app_dispatcher_only_imports_deeper_app_modules() -> None:
    """AppDispatcher must route concrete app wiring through app.registry only."""
    modules = imported_modules(DISPATCHER_PATH)
    app_imports = {module for module in modules if module.startswith("scop.app.")}

    assert app_imports == {"scop.app.registry.builder"}, app_imports
