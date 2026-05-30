"""Spawn, capture stdout/stderr, pipe, timeout, kill.
Boundary: external processes only — not internal concurrency.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


def run_resolved(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a subprocess, resolving the executable via PATH before spawning."""
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    return subprocess.run(cmd, **kwargs)  # noqa: S603
