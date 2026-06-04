from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO, Protocol

from scop.app.dispatcher import AppDispatcher


class _EventLike(Protocol):
    def to_ndjson(self) -> str: ...


class _ResultLike(Protocol):
    @property
    def ok(self) -> bool: ...


class _StreamLike(Protocol):
    @property
    def result(self) -> _ResultLike | None: ...

    def __aiter__(self) -> AsyncIterator[_EventLike]: ...


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scop", description="File and directory snapshotter.")
    p.add_argument("--version", action="store_true", help="Show version")

    sub = p.add_subparsers(dest="command")

    snapshot = sub.add_parser("snapshot", help="Manage snapshots")
    snapshot.add_argument("--status", "-s", action="store_true", help="Show snapshot stats")
    snapshot.add_argument("--list", "-l", action="store_true", help="List snapshots")
    snapshot.add_argument("--all", "-a", action="store_true", help="Expand list scope")
    snap_sub = snapshot.add_subparsers(dest="snapshot_action")

    create = snap_sub.add_parser("create", help="Take a new snapshot")
    create.add_argument("path", nargs="?", default=None)
    create.add_argument("--dry-run", "-n", action="store_true")
    create.add_argument("--recursive", "-r", action="store_true")
    create.add_argument("--force", "-f", action="store_true")

    restore = snap_sub.add_parser("restore", help="Restore a snapshot")
    restore.add_argument("name", nargs="?", default=None)
    restore.add_argument("dest", nargs="?", default=None)

    diff = snap_sub.add_parser("diff", help="Compare two snapshots")
    diff.add_argument("--from", dest="from_snap")
    diff.add_argument("--to", dest="to_snap")

    config = sub.add_parser("config", help="Application configuration")
    config.add_argument("--list", "-l", action="store_true")
    config.add_argument("--target-dir", dest="target_dir")
    config.add_argument("--store-dir", dest="store_dir")
    config.add_argument("--objects-dir", dest="objects_dir")
    config.add_argument("--skip-dirs", dest="skip_dirs")

    # Global mode flags
    for sp in (snapshot, create, restore, diff, config):
        sp.add_argument("--verbose", "-v", action="store_true", default=False)
        sp.add_argument("--quiet", "-q", action="store_true", default=False)
        sp.add_argument("--output", "-o", metavar="FILE", default=None)

    return p


async def _render_raw(stream: _StreamLike, out: IO[str]) -> bool:
    """Write raw NDJSON events from the stream to `out` (one per line)."""
    async for event in stream:
        out.write(event.to_ndjson())
        out.write("\n")
        with contextlib.suppress(Exception):
            out.flush()

    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    return bool(result.ok)


def _dispatch_and_stream(command: str, args: dict, output_path: str | None) -> int:
    dispatcher = AppDispatcher.default(validate=bool(os.getenv("SCOP_VALIDATE_NDJSON")))

    async def _run(out: IO[str]) -> int:
        stream = dispatcher.dispatch(command, args)
        ok = await _render_raw(stream, out=out)
        # let runtime-spawned tasks finish
        with contextlib.suppress(Exception):
            current = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks() if t is not current]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        return 0 if ok else 1

    with contextlib.ExitStack() as stack:
        out: IO[str] = (
            stack.enter_context(Path(output_path).open("w", encoding="utf-8"))
            if output_path is not None
            else sys.stdout
        )
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_run(out))
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    # handle top-level version
    if args.pop("version", False):
        try:
            from importlib.metadata import version as _version

            sys.stdout.write(f"scop {_version('scop')}\n")
        except Exception:
            sys.stdout.write("scop (unknown version)\n")
        sys.exit(0)

    command = args.pop("command", "") or ""

    # Normalize snapshot action
    if command == "snapshot":
        action = args.pop("snapshot_action", None)
        if action is not None:
            args["action"] = action
        elif args.pop("status", False):
            args["action"] = "status"
        elif args.pop("list", False):
            args["action"] = "list"
        else:
            args.pop("status", None)
            args.pop("list", None)
        args.pop("all", None)

    output = args.pop("output", None)

    try:
        code = _dispatch_and_stream(command, args, output)
    except KeyboardInterrupt:
        code = 130
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stderr.fileno())
        code = 0
    except Exception as exc:
        sys.stderr.write(f"error: {exc}\n")
        code = 1

    sys.exit(code)


if __name__ == "__main__":
    main()
