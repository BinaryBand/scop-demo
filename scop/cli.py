# scop/cli.py
from __future__ import annotations

import argparse
import asyncio
import sys

from scop.app.dispatcher import AppDispatcher
from scop.app.stream import StreamingResult
from scop.models.protocol import MSGID

# ── Argument parser ───────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scop",
        description="File and directory snapshotter.",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Include debug output")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")

    sub = p.add_subparsers(dest="command")

    snap = sub.add_parser("snap", help="Take a snapshot of a directory")
    snap.add_argument("path", nargs="?", default=".", help="Directory to snapshot")
    snap.add_argument("--dry-run", "-n", action="store_true")
    snap.add_argument("--recursive", "-r", action="store_true")

    diff = sub.add_parser("diff", help="Compare two snapshots")
    diff.add_argument("a", help="First snapshot name")
    diff.add_argument("b", help="Second snapshot name")

    sub.add_parser("status", help="Show current snapshot state")
    sub.add_parser("log", help="List all snapshots")

    restore = sub.add_parser("restore", help="Restore a snapshot")
    restore.add_argument("name", help="Snapshot to restore")
    restore.add_argument("--dry-run", "-n", action="store_true")

    return p


# ── Stream renderer ───────────────────────────────────────────────────────────


async def _render(stream: StreamingResult, *, verbose: bool, quiet: bool) -> bool:
    """Consume a StreamingResult and print each event's msg field.

    Follows SCOP §4.2 severity rendering:
        pri 0-3  → stderr          (errors)
        pri 4    → stderr [WARN]   (warnings)
        pri 5-6  → stdout          (normal)
        pri 7    → suppressed      (debug, unless --verbose)
    """
    async for event in stream:
        pri = event.pri
        msg = event.msg
        msgid = event.msgid

        if msgid == MSGID.PAGE_END:
            continue
        if pri == 7 and not verbose:
            continue
        if quiet and msgid == MSGID.PROCESS_LOG:
            continue

        if pri <= 3:
            print(msg, file=sys.stderr)
        elif pri == 4:
            print(f"[WARN] {msg}", file=sys.stderr)
        else:
            print(msg)

    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    return result.ok


# ── Entry points ──────────────────────────────────────────────────────────────


async def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    command: str | None = args.pop("command")
    verbose: bool = args.pop("verbose", False)
    quiet: bool = args.pop("quiet", False)

    dispatcher = AppDispatcher.default()
    stream = dispatcher.dispatch("" if command is None else command, args)
    ok = await _render(stream, verbose=verbose, quiet=quiet)
    return 0 if ok else 1


def main() -> None:
    """Installed entry point: scop = 'scop.cli:main'"""
    sys.exit(asyncio.run(_main()))
