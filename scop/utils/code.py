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


def top_level_class_names(path: Path) -> list[str]:
    """Return the names of all top-level class definitions in a Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node.name for node in ast.iter_child_nodes(tree) if isinstance(node, ast.ClassDef)]


def class_var_annotation_names(path: Path, class_name: str, attr: str) -> list[str]:
    """Return the type names annotated or assigned to `attr` in `class_name`.

    Handles both ``attr: ClassVar[type[Foo]] = Foo`` and ``attr = Foo``.
    Returns all Name nodes found on the right-hand side / annotation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign):
                target = stmt.target
                if isinstance(target, ast.Name) and target.id == attr and stmt.value:
                    names.extend(_extract_names(stmt.value))
            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == attr:
                        names.extend(_extract_names(stmt.value))

    return names


def _extract_names(node: ast.expr) -> list[str]:
    return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


__all__ = [
    "class_var_annotation_names",
    "imported_modules",
    "top_level_class_names",
]
