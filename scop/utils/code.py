"""Python source analysis helpers.

Boundary: Python code introspection and parsing only.
"""

from __future__ import annotations

import ast
from pathlib import Path


def imported_modules(path: Path) -> set[str]:
    """Return all imported module names found in a Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)

    return modules


__all__ = ["imported_modules"]
