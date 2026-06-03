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

# ── Protocols ─────────────────────────────────────────────────────────────────


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


def _global_flags(p: argparse.ArgumentParser) -> None:
    """Attach global mode/IO flags to a subparser.

    SUPPRESS prevents absent subparser flags from overwriting values already
    set by the root parser — only an explicit flag on the command line wins.
    """
    p.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)
    p.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS)
    p.add_argument("-o", "--output", metavar="FILE", default=argparse.SUPPRESS)
    p.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scop",
        description="File and directory snapshotter.",
        add_help=False,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("-h", "--help", action="store_true", help="Show this help message")
    p.add_argument("--version", action="store_true", help="Show version and exit")
    p.add_argument("-v", "--verbose", action="store_true", help="Include debug events")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    p.add_argument("-o", "--output", metavar="FILE", help="Write NDJSON to FILE instead of stdout")
    p.add_argument("--no-color", action="store_true", help="Disable color output")

    sub = p.add_subparsers(dest="command", metavar="<command>")

    # snapshot ──────────────────────────────────────────────────────────────
    snapshot = sub.add_parser(
        "snapshot", add_help=False, help="Manage snapshots", description="Manage snapshots."
    )
    snapshot.add_argument("-h", "--help", action="store_true")
    snapshot.add_argument("-s", "--status", action="store_true", help="Show snapshot stats")
    snapshot.add_argument("-l", "--list", action="store_true", help="List snapshots")
    snapshot.add_argument("-a", "--all", action="store_true", help="Expand list to all snapshots")
    _global_flags(snapshot)

    snap_sub = snapshot.add_subparsers(dest="snapshot_action", metavar="<action>")

    create = snap_sub.add_parser(
        "create", add_help=False, help="Take a new snapshot", description="Take a new snapshot."
    )
    create.add_argument("-h", "--help", action="store_true")
    create.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Directory to snapshot (default: configured target-dir)",
    )
    create.add_argument(
        "-n", "--dry-run", action="store_true", help="Preview changes without writing"
    )
    create.add_argument("-r", "--recursive", action="store_true")
    create.add_argument("-f", "--force", action="store_true")
    _global_flags(create)

    restore = snap_sub.add_parser(
        "restore",
        add_help=False,
        help="Restore a snapshot",
        description="Restore a snapshot to a directory.",
    )
    restore.add_argument("-h", "--help", action="store_true")
    restore.add_argument("name", nargs="?", default=None, help="Snapshot ID to restore")
    restore.add_argument("dest", nargs="?", default=None, help="Output directory")
    _global_flags(restore)

    diff = snap_sub.add_parser(
        "diff", add_help=False, help="Compare two snapshots", description="Compare two snapshots."
    )
    diff.add_argument("-h", "--help", action="store_true")
    diff.add_argument("--from", dest="from_snap", metavar="ID")
    diff.add_argument("--to", dest="to_snap", metavar="ID")
    _global_flags(diff)

    # config ────────────────────────────────────────────────────────────────
    config = sub.add_parser(
        "config",
        add_help=False,
        help="Application configuration",
        description="Read and write application configuration.",
    )
    config.add_argument("-h", "--help", action="store_true")
    config.add_argument("-l", "--list", action="store_true", help="Show config as a table")
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
    _global_flags(config)

    return p


# ── Stream renderer ───────────────────────────────────────────────────────────


def _is_tty(f: IO[str]) -> bool:
    try:
        return os.isatty(f.fileno())
    except Exception:
        return False


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


async def _render(
    stream: _StreamLike,
    *,
    verbose: bool,
    quiet: bool,
    color: bool,
    out: IO[str],
) -> bool:
    """Write NDJSON to out when piped, human-readable when TTY.

    Progress bars always go to stderr so they never pollute piped output and
    remain visible when output is redirected with -o.
    """
    write_ndjson = not _is_tty(out)
    show_progress = not quiet and _is_tty(sys.stderr)
    bars: dict[str, _tqdm] = {}

    async for event in stream:
        raw = event.to_ndjson()

        if write_ndjson:
            out.write(f"{raw}\n")

        # Always parse: drives progress bars on stderr and human-readable display.
        ev_list = parse_ndjson(raw)
        if not ev_list:
            continue
        ev = ev_list[0]

        msgid_name = str(ev.get("msgid", ""))
        pri = int(ev.get("pri", 0))
        proc_id = str(ev.get("id", ""))

        if msgid_name == "PROCESS_BEGIN" and show_progress:
            bars[proc_id] = _tqdm(
                total=None,
                desc=str(ev.get("label", proc_id)),
                unit="file",
                file=sys.stderr,
                leave=True,
                dynamic_ncols=True,
                mininterval=0,
                colour=None if color else False,
            )
            if write_ndjson:
                continue
        elif msgid_name == "PROCESS_UPDATE" and proc_id in bars:
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
        elif msgid_name == "PROCESS_END" and proc_id in bars:
            bars.pop(proc_id).close()

        if write_ndjson:
            continue

        if pri == 7 and not verbose:
            continue
        if quiet and msgid_name.endswith("PROCESS_LOG"):
            continue

        msg = str(ev.get("msg", "")).strip()
        if msg:
            out.write(f"{msg}\n")

    for bar in bars.values():
        bar.close()

    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    return bool(result.ok)


# ── Entry points ──────────────────────────────────────────────────────────────


async def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    verbose: bool = args.pop("verbose", False)
    quiet: bool = args.pop("quiet", False)
    output_path: str | None = args.pop("output", None)
    no_color: bool = args.pop("no_color", False)
    color = not no_color and "NO_COLOR" not in os.environ

    command = _resolve_command(args)

    dispatcher = AppDispatcher.default(validate=bool(os.getenv("SCOP_VALIDATE_NDJSON")))
    stream = dispatcher.dispatch(command, args)

    with contextlib.ExitStack() as stack:
        out: IO[str] = (
            stack.enter_context(Path(output_path).open("w", encoding="utf-8"))
            if output_path is not None
            else sys.stdout
        )
        try:
            ok = await _render(stream, verbose=verbose, quiet=quiet, color=color, out=out)
        except RuntimeError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1

    return 0 if ok else 1


def main() -> None:
    """Installed entry point: scop = 'scop.cli:main'"""
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # Silence deferred "broken pipe" writes Python may attempt on shutdown.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stderr.fileno())
        sys.exit(0)
