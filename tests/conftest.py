"""Pytest configuration and fixtures."""

from pathlib import Path

from scop.utils.proc import env_var, executable_exists, run_resolved

_ROOT = Path(__file__).resolve().parent.parent


def _fix(cmd: list[str]) -> None:
    if not executable_exists(cmd[0]):
        return
    run_resolved(cmd, cwd=_ROOT, check=False)


def pytest_sessionstart() -> None:
    if env_var("CI"):
        return
    _fix(["ruff", "check", "--fix", "scop", "tests"])
    _fix(["ruff", "format", "scop", "tests"])
