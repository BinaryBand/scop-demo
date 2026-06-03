# scop/cli.py
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO, Protocol

from tqdm import tqdm as _tqdm

from scop.app.dispatcher import AppDispatcher
from scop.ui import parse_ndjson


class _EventLike(Protocol):
    def to_ndjson(self) -> str: ...


class _ResultLike(Protocol):
    @property
    def ok(self) -> bool: ...


class _StreamLike(Protocol):
    @property
    def result(self) -> _ResultLike | None: ...

    def __aiter__(self) -> AsyncIterator[_EventLike]: ...


# ── Argument parser ───────────────────────────────────────────────────────────


def _add_mode_flags(p: argparse.ArgumentParser) -> None:
    """Add global mode/IO flags to a subparser.

    SUPPRESS keeps these from resetting the root parser's values when absent —
    only an explicit flag on the command line updates the namespace.
    """
    p.add_argument("--verbose", "-v", action="store_true", default=argparse.SUPPRESS)
    p.add_argument("--quiet", "-q", action="store_true", default=argparse.SUPPRESS)
    p.add_argument("--output", "-o", metavar="FILE", default=argparse.SUPPRESS)


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
    p.add_argument("--output", "-o", metavar="FILE", help="Write output to FILE instead of stdout")

    sub = p.add_subparsers(dest="command")

    snapshot = sub.add_parser("snapshot", add_help=False, help="Manage snapshots")
    snapshot.add_argument("--help", "-h", action="store_true", help="Show snapshot commands")
    snapshot.add_argument("--status", action="store_true", help="Show snapshot stats")
    snapshot.add_argument("--list", "-l", action="store_true", help="List snapshots")
    snapshot.add_argument("--all", "-a", action="store_true", help="Expand list scope")
    _add_mode_flags(snapshot)

    snap_sub = snapshot.add_subparsers(dest="snapshot_action")

    create = snap_sub.add_parser("create", add_help=False, help="Take a new snapshot")
    create.add_argument("path", nargs="?", default=None, help="Directory to snapshot")
    create.add_argument("--help", "-h", action="store_true", help="Show create options")
    create.add_argument("--dry-run", "-n", action="store_true")
    create.add_argument("--recursive", "-r", action="store_true")
    create.add_argument("--force", "-f", action="store_true")
    _add_mode_flags(create)

    restore = snap_sub.add_parser("restore", add_help=False, help="Restore a snapshot")
    restore.add_argument("name", nargs="?", default=None, help="Snapshot ID to restore")
    restore.add_argument("dest", nargs="?", default=None, help="Output directory")
    restore.add_argument("--help", "-h", action="store_true", help="Show restore options")
    _add_mode_flags(restore)

    diff = snap_sub.add_parser("diff", add_help=False, help="Compare two snapshots")
    diff.add_argument("--help", "-h", action="store_true", help="Show diff options")
    diff.add_argument("--from", dest="from_snap")
    diff.add_argument("--to", dest="to_snap")
    _add_mode_flags(diff)

    config = sub.add_parser("config", add_help=False, help="Application configuration")
    config.add_argument("--help", "-h", action="store_true", help="Show config form")
    config.add_argument("--list", "-l", action="store_true", help="Show config as a table")
    config.add_argument(
        "--target-dir", dest="target_dir", metavar="PATH", help="Directory to snapshot"
    )
    config.add_argument(
        "--store-dir", dest="store_dir", metavar="PATH", help="Snapshot store directory"
    )
    config.add_argument(
        "--objects-dir", dest="objects_dir", metavar="PATH", help="Object store directory"
    )
    config.add_argument(
        "--skip-dirs", dest="skip_dirs", metavar="CSV", help="Comma-separated dirs to skip"
    )
    _add_mode_flags(config)

    return p


# ── Stream renderer ───────────────────────────────────────────────────────────


def _is_tty(f: IO[str]) -> bool:
    try:
        return os.isatty(f.fileno())
    except Exception:
        return False


async def _render(stream: _StreamLike, *, verbose: bool, quiet: bool, out: IO[str]) -> bool:
    """Consume a stream: tqdm progress + human-readable msg on a TTY, NDJSON otherwise."""
    tty = _is_tty(out)
    bars: dict[str, _tqdm] = {}

    async for event in stream:
        raw = event.to_ndjson()

        if not tty:
            out.write(f"{raw}\n")
            continue

        # Parse via ui.parse_ndjson so event field access is consistent with all SCOP UIs.
        ev_list = parse_ndjson(raw)
        if not ev_list:
            continue
        ev = ev_list[0]

        msgid_name = str(ev.get("msgid", ""))
        pri = int(ev.get("pri", 0))
        proc_id = str(ev.get("id", ""))

        if msgid_name == "PROCESS_BEGIN":
            bars[proc_id] = _tqdm(
                total=None,
                desc=str(ev.get("label", proc_id)),
                unit="file",
                file=out,
                leave=True,
                dynamic_ncols=True,
                mininterval=0,
            )
            continue
        if msgid_name == "PROCESS_UPDATE" and proc_id in bars:
            bar = bars[proc_id]
            current = int(ev.get("current", 0))
            raw_total = ev.get("total")
            if raw_total == 0 or (raw_total is None and bar.total is None):
                bar.set_description(f"Scanning ({current} found)")
                bar.refresh()
            else:
                if raw_total is not None and bar.total is None:
                    bar.total = int(raw_total)
                    bar.set_description(str(ev.get("label", proc_id)))
                bar.n = current
                bar.refresh()
            continue
        if msgid_name == "PROCESS_END" and proc_id in bars:
            bars.pop(proc_id).close()

        if pri == 7 and not verbose:
            continue
        if quiet and msgid_name.endswith("PROCESS_LOG"):
            continue

        msg = str(ev.get("msg", "")).strip()
        if msg:
            _tqdm.write(msg, file=out) if bars else out.write(f"{msg}\n")

    for bar in bars.values():
        bar.close()

    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    return bool(result.ok)


def _resolve_command(args: dict) -> str:
    command = args.pop("command")
    if command == "snapshot":
        action = args.pop("snapshot_action", None)
        if action is not None:
            args["action"] = action
        return "snapshot"
    if command == "config":
        return "config"
    return "" if command is None else str(command)


# ── Entry points ──────────────────────────────────────────────────────────────


async def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    verbose: bool = args.pop("verbose", False)
    quiet: bool = args.pop("quiet", False)
    output_path: str | None = args.pop("output", None)
    command = _resolve_command(args)

    dispatcher = AppDispatcher.default(validate=bool(os.getenv("SCOP_VALIDATE_NDJSON")))
    stream = dispatcher.dispatch(command, args)

    with contextlib.ExitStack() as stack:
        out: IO[str] = (
            stack.enter_context(Path(output_path).open("w", encoding="utf-8"))
            if output_path is not None
            else sys.stdout
        )
        ok = await _render(stream, verbose=verbose, quiet=quiet, out=out)

    return 0 if ok else 1


def main() -> None:
    """Installed entry point: scop = 'scop.cli:main'"""
    sys.exit(asyncio.run(_main()))
