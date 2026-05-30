"""Pytest configuration and fixtures."""

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _fix(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, cwd=_ROOT, check=False, shell=(os.name == "nt"))  # noqa: S603
    except FileNotFoundError:
        pass


def pytest_sessionstart() -> None:
    if os.getenv("CI"):
        return
    _fix(["ruff", "check", "--fix", "scop", "tests"])
    _fix(["ruff", "format", "scop", "tests"])
