"""Spawn, capture stdout/stderr, pipe, timeout, kill.
Boundary: external processes only — not internal concurrency.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Literal


def resolve_executable(name: str) -> str:
    """Return an absolute path to *name* if it exists and is executable.

    If *name* already contains a path separator it is treated as a path
    and validated. Otherwise ``shutil.which`` is used.
    """
    if os.sep in name or name.startswith("."):
        path_obj = Path(name).expanduser()
        if path_obj.exists() and os.access(path_obj, os.X_OK):
            return str(path_obj.resolve())
        raise FileNotFoundError(f"Executable not found or not executable: {name}")

    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"Executable not found in PATH: {name}")
    return path


def executable_exists(name: str) -> bool:
    """Return True if *name* can be resolved from PATH."""
    return shutil.which(name) is not None


def env_var(name: str) -> str | None:
    """Return environment variable value, or None when unset."""
    return os.getenv(name)


def env_without(*keys: str) -> dict[str, str]:
    """Return a copy of os.environ with the provided keys removed."""
    blocked = set(keys)
    return {k: v for k, v in os.environ.items() if k not in blocked}


def run_resolved(
    cmd: Iterable[str],
    /,
    *,
    cwd: Path | str | None = None,
    capture_output: bool = False,
    text: Literal[True] = True,
    encoding: str | None = None,
    errors: str | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Resolve the command's executable and call ``subprocess.run``.

    The first element of *cmd* is resolved with :func:`resolve_executable`.
    All other positional and keyword arguments are forwarded to
    :func:`subprocess.run`.
    """
    cmd_list: list[str] = list(cmd)
    if not cmd_list:
        raise ValueError("empty command")

    resolved = resolve_executable(cmd_list[0])
    full_cmd = [resolved, *cmd_list[1:]]
    return subprocess.run(
        full_cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=text,
        encoding=encoding,
        errors=errors,
        check=check,
        env=env,
    )


__all__ = [
    "env_var",
    "env_without",
    "executable_exists",
    "resolve_executable",
    "run_resolved",
]
