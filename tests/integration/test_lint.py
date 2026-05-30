"""Linting tests that enforce repository quality and architecture gates."""

from __future__ import annotations

import os
from pathlib import Path

from scop.utils.proc import run_resolved

_ENV_WITHOUT_VIRTUAL_ENV = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

ROOT = Path(__file__).resolve().parents[2]


class TestRuff:
    """Ensure the codebase passes ruff linting and formatting checks."""

    PATHS = ["scop/", "tests/"]

    def test_ruff_check(self):
        """Fail if ruff reports any lint violations."""
        result = run_resolved(
            ["poetry", "run", "ruff", "check", *self.PATHS],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_ruff_format(self):
        """Fail if ruff reports any formatting violations."""
        result = run_resolved(
            ["poetry", "run", "ruff", "format", "--check", *self.PATHS],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestImportLinter:
    """Ensure the codebase obeys the import layer contract."""

    def test_lint_imports(self):
        """Fail if import-linter reports any contract violations."""
        result = run_resolved(
            ["poetry", "run", "lint-imports"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestAstGrep:
    """Ensure the codebase passes all ast-grep structural rules."""

    def test_ast_grep_scan(self):
        """Fail if ast-grep reports any rule violations."""
        result = run_resolved(
            ["poetry", "run", "ast-grep", "scan"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestTy:
    """Ensure the codebase passes the current ty gate."""

    def test_ty(self):
        """Fail if ty reports any type-checking violations."""
        result = run_resolved(
            ["poetry", "run", "ty", "check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_ENV_WITHOUT_VIRTUAL_ENV,
        )
        assert result.returncode == 0, result.stdout + result.stderr
