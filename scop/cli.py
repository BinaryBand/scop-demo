from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Protocol

from scop.app.dispatcher import AppDispatcher

# ── Utilities ─────────────────────────────────────────────────────────────────


def to_ndjson(events: list[dict[str, Any]]) -> str:
    """Serialise a list of event dicts back to NDJSON text."""
    return "".join(json.dumps(ev) + "\n" for ev in events)


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


# ── Dispatch ──────────────────────────────────────────────────────────────────


def dispatch_events(command: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Dispatch a command through AppDispatcher; collect all NDJSON events."""

    async def _run() -> tuple[list[dict[str, Any]], bool]:
        dispatcher = AppDispatcher.default(validate=False)
        stream = dispatcher.dispatch(command, args)
        events: list[dict[str, Any]] = []
        async for ev in stream:
            try:
                obj = json.loads(ev.to_ndjson())
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict):
                events.append(obj)
        with contextlib.suppress(Exception):
            current = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        result = stream.result
        return events, bool(result.ok) if result is not None else False

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        events, ok = loop.run_until_complete(_run())
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    # Minimal icon mapping for help probes: attach a synthetic PAGE_BEGIN
    # event containing an `icon` when callers request `--help` but the
    # app's help path doesn't emit a PAGE_BEGIN with icon. This keeps GUI
    # nav icons available without running the full page.
    icon_map: dict[str, str] = {
        "config": ":gear:",
        "snapshot": ":package:",
    }
    if args.get("help") and command in icon_map and icon_map[command]:
        with contextlib.suppress(Exception):
            found = False
            for ev in events:
                if isinstance(ev, dict) and ev.get("msgid") == "PAGE_BEGIN":
                    data = ev.get("data")
                    if not isinstance(data, dict):
                        ev["data"] = {"icon": icon_map[command]}
                    else:
                        if not data.get("icon"):
                            data["icon"] = icon_map[command]
                    found = True
                    break
            if not found:
                events.insert(
                    0,
                    {
                        "msgid": "PAGE_BEGIN",
                        "room": command or None,
                        "data": {"icon": icon_map[command]},
                    },
                )

    return events, ok


# ── Argument parser ───────────────────────────────────────────────────────────


@dataclass
class DecodedArgv:
    command: str
    args: dict[str, Any]
    output_path: str | None
    version: bool


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scop", add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--version", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true", default=False)
    p.add_argument("-q", "--quiet", action="store_true", default=False)
    p.add_argument("-o", "--output", dest="output", default=None)
    p.add_argument("--no-color", action="store_true", default=False)

    sub = p.add_subparsers(dest="command")

    snapshot = sub.add_parser("snapshot", add_help=False)
    snapshot.add_argument("-h", "--help", action="store_true")
    snapshot.add_argument("-s", "--status", action="store_true")
    snapshot.add_argument("-l", "--list", action="store_true")
    snapshot.add_argument("-a", "--all", action="store_true")
    snap_sub = snapshot.add_subparsers(dest="snapshot_action")

    create = snap_sub.add_parser("create", add_help=False)
    create.add_argument("-h", "--help", action="store_true")
    create.add_argument("path", nargs="?", default=None)
    create.add_argument("-n", "--dry-run", action="store_true")
    create.add_argument("-r", "--recursive", action="store_true")
    create.add_argument("-f", "--force", action="store_true")

    restore = snap_sub.add_parser("restore", add_help=False)
    restore.add_argument("-h", "--help", action="store_true")
    restore.add_argument("name", nargs="?", default=None)
    restore.add_argument("dest", nargs="?", default=None)

    diff = snap_sub.add_parser("diff", add_help=False)
    diff.add_argument("-h", "--help", action="store_true")
    diff.add_argument("--from", dest="from_snap", default=None)
    diff.add_argument("--to", dest="to_snap", default=None)

    config = sub.add_parser("config", add_help=False)
    config.add_argument("-h", "--help", action="store_true")
    config.add_argument("-l", "--list", action="store_true")
    config.add_argument("--target-dir", dest="target_dir", default=None)
    config.add_argument("--store-dir", dest="store_dir", default=None)
    config.add_argument("--objects-dir", dest="objects_dir", default=None)
    config.add_argument("--skip-dirs", dest="skip_dirs", default=None)

    for sp in (snapshot, create, restore, diff, config):
        sp.add_argument("-v", "--verbose", action="store_true", default=False)
        sp.add_argument("-q", "--quiet", action="store_true", default=False)
        sp.add_argument("-o", "--output", default=None)

    return p


def decode_argv(argv: list[str]) -> DecodedArgv:
    """Parse argv and return a DecodedArgv with command, args, and flags."""
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    version = bool(args.pop("version", False))
    command = str(args.pop("command", "") or "")
    output_path = args.pop("output", None)

    if command == "snapshot":
        action = args.pop("snapshot_action", None)
        if action is not None:
            args["action"] = action
        elif args.pop("status", False):
            args["action"] = "status"
        elif args.pop("list", False):
            args["action"] = "list"

    return DecodedArgv(command=command, args=args, output_path=output_path, version=version)


# ── Raw NDJSON relay ──────────────────────────────────────────────────────────


async def _relay(stream: _StreamLike, out: IO[str]) -> bool:
    """Write raw NDJSON events from stream to out, one line each."""
    async for event in stream:
        out.write(event.to_ndjson())
        out.write("\n")
        with contextlib.suppress(Exception):
            out.flush()
    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    return bool(result.ok)


def _dispatch_and_relay(command: str, args: dict, output_path: str | None) -> int:
    """Dispatch command and stream raw NDJSON to stdout (or output file)."""
    dispatcher = AppDispatcher.default(validate=bool(os.getenv("SCOP_VALIDATE_NDJSON")))

    async def _run(out: IO[str]) -> int:
        stream = dispatcher.dispatch(command, args)
        ok = await _relay(stream, out=out)
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
    """Entry point: scop-raw — relays raw NDJSON, no formatting."""
    parser = _build_parser()
    ns = parser.parse_args(argv)
    args = vars(ns)

    if args.pop("version", False):
        try:
            from importlib.metadata import version as _version

            sys.stdout.write(f"scop {_version('scop')}\n")
        except Exception:
            sys.stdout.write("scop (unknown version)\n")
        sys.exit(0)

    command = args.pop("command", "") or ""

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
        code = _dispatch_and_relay(command, args, output)
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
