"""Pytest configuration and fixtures."""

import shutil
from pathlib import Path

from scop.utils.proc import run_resolved

_ROOT = Path(__file__).resolve().parent.parent


def _fix(cmd: list[str]) -> None:
    resolved = shutil.which(cmd[0])
    if resolved is None:
        return
    run_resolved([resolved, *cmd[1:]], cwd=_ROOT, check=False)


def pytest_sessionstart() -> None:
    if __import__("os").getenv("CI"):
        return
    _fix(["ruff", "check", "--fix", "scop", "tests"])
    _fix(["ruff", "format", "scop", "tests"])
