from __future__ import annotations

import contextlib
import functools
import io
import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, cast

PAGE_FLAGS: list[list[str]] = [["--list", "--all"], ["--status"], ["--help"]]


@dataclass
class NavPage:
    key: str
    label: str


@functools.lru_cache(maxsize=1)
def discover_pages() -> list[NavPage]:
    """Parse `scop --help` NDJSON to discover root-level command pages."""
    exe = shutil.which("scop") or "scop"
    try:
        result = subprocess.run(
            [exe, "--help"], capture_output=True, text=True, encoding="utf-8", check=False
        )
    except OSError:
        return []

    seen: set[str] = set()
    pages: list[NavPage] = []
    for raw in io.StringIO(result.stdout):
        line = raw.strip()
        if not line:
            continue
        try:
            ev: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("msgid") != "LIST_APPEND" or ev.get("id") != "help":
            continue
        value = ev.get("value")
        if not isinstance(value, dict):
            continue
        command = value.get("command", "")
        if not isinstance(command, str):
            continue
        try:
            tokens = [t for t in shlex.split(command, posix=False) if not t.startswith("-")]
        except ValueError:
            continue
        if len(tokens) != 1 or tokens[0] in seen:
            continue
        key = tokens[0]
        seen.add(key)
        pages.append(NavPage(key=key, label=key.replace("-", " ").title()))

    return pages


def run_scop(args: list[str]) -> str:
    """Run scop with the given args; return stdout, empty string on failure."""
    exe = shutil.which("scop") or "scop"
    try:
        r = subprocess.run(
            [exe, *args], capture_output=True, text=True, encoding="utf-8", check=False
        )
    except OSError:
        r = None
    return r.stdout if r is not None else ""


def parse_ndjson(text: str) -> list[dict[str, Any]]:
    """Parse NDJSON text into event dicts, silently skipping malformed lines."""
    events: list[dict[str, Any]] = []
    for raw in io.StringIO(text):
        line = raw.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            events.append(json.loads(line))
    return events


def is_form_param(p: object) -> bool:
    """True if param p should appear as an editable field in a generated form."""
    if not isinstance(p, dict):
        return False
    d = cast("dict[str, Any]", p)
    return bool(
        (d.get("kind") == "positional" and d.get("required") is not False)
        or (d.get("kind") == "flag" and d.get("metavar") and (d.get("required") or "default" in d))
    )
