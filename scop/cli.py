# scop/cli.py
from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator
from typing import Protocol

from scop.app.dispatcher import AppDispatcher


class _EventLike(Protocol):
    pri: int

    def to_ndjson(self) -> str: ...


class _ResultLike(Protocol):
    @property
    def ok(self) -> bool: ...


class _StreamLike(Protocol):
    @property
    def result(self) -> _ResultLike | None: ...

    def __aiter__(self) -> AsyncIterator[_EventLike]: ...


# ── Argument parser ───────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scop",
        description="File and directory snapshotter.",
        add_help=False,
    )
    p.add_argument("--help", "-h", action="store_true", help="Show available commands")
    p.add_argument("--version", action="store_true", help="Show version")
    p.add_argument("--verbose", "-v", action="store_true", help="Include debug output")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")

    sub = p.add_subparsers(dest="command")

    snapshot = sub.add_parser("snapshot", add_help=False, help="Manage snapshots")
    snapshot.add_argument("--help", "-h", action="store_true", help="Show snapshot commands")
    snapshot.add_argument("--status", action="store_true", help="Show snapshot stats")
    snapshot.add_argument("--list", "-l", action="store_true", help="List snapshots")
    snapshot.add_argument("--all", "-a", action="store_true", help="Expand list scope")

    snap_sub = snapshot.add_subparsers(dest="snapshot_action")

    create = snap_sub.add_parser("create", add_help=False, help="Take a new snapshot")
    create.add_argument("--help", "-h", action="store_true", help="Show create options")
    create.add_argument("--dry-run", "-n", action="store_true")
    create.add_argument("--recursive", "-r", action="store_true")

    diff = snap_sub.add_parser("diff", add_help=False, help="Compare two snapshots")
    diff.add_argument("--help", "-h", action="store_true", help="Show diff options")
    diff.add_argument("--from", dest="from_snap")
    diff.add_argument("--to", dest="to_snap")

    return p


# ── Stream renderer ───────────────────────────────────────────────────────────


async def _render(stream: _StreamLike, *, verbose: bool, quiet: bool) -> bool:
    """Consume a stream and emit SCOP NDJSON lines to stdout."""
    async for event in stream:
        pri = event.pri
        raw_msgid = getattr(event, "msgid", "")
        msgid_name = getattr(raw_msgid, "name", str(raw_msgid))

        if pri == 7 and not verbose:
            continue
        if quiet and msgid_name.endswith("PROCESS_LOG"):
            continue

        sys.stdout.write(f"{event.to_ndjson()}\n")

    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    return bool(result.ok)


def _resolve_command(args: dict) -> str:
    command = args.pop("command")
    if command != "snapshot":
        return "" if command is None else str(command)

    action = args.pop("snapshot_action", None)
    if action is not None:
        args["action"] = action
    return "snapshot"


# ── Entry points ──────────────────────────────────────────────────────────────


async def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    verbose: bool = args.pop("verbose", False)
    quiet: bool = args.pop("quiet", False)
    command = _resolve_command(args)

    dispatcher = AppDispatcher.default()
    stream = dispatcher.dispatch(command, args)
    ok = await _render(stream, verbose=verbose, quiet=quiet)
    return 0 if ok else 1


def main() -> None:
    """Installed entry point: scop = 'scop.cli:main'"""
    sys.exit(asyncio.run(_main()))
