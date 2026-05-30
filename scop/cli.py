"""Entry point — the only file permitted to use argparse and sys.exit."""

from __future__ import annotations

import argparse
import asyncio
import sys

from scop.app.dispatcher import AppDispatcher


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="scop", add_help=False)
    root.add_argument("-h", "--help", action="store_true")
    root.add_argument("--version", action="store_true")
    root.add_argument("-q", "--quiet", action="store_true")
    root.add_argument("-v", "--verbose", action="store_true")
    root.add_argument("--json", action="store_true", help="Emit raw NDJSON instead of plain text")

    subs = root.add_subparsers(dest="command")

    # -- snapshot -------------------------------------------------------------
    snap = subs.add_parser("snapshot", add_help=False)
    snap.add_argument("-h", "--help", action="store_true")
    snap.add_argument("--status", action="store_true")
    snap.add_argument("-l", "--list", action="store_true")
    snap.add_argument("-a", "--all", action="store_true")
    snap.add_argument("-q", "--quiet", action="store_true")
    snap.add_argument("-v", "--verbose", action="store_true")

    snap_subs = snap.add_subparsers(dest="action")

    create = snap_subs.add_parser("create", add_help=False)
    create.add_argument("-h", "--help", action="store_true")
    create.add_argument("-n", "--dry-run", action="store_true", dest="dry_run")
    create.add_argument("-v", "--verbose", action="store_true")

    diff = snap_subs.add_parser("diff", add_help=False)
    diff.add_argument("-h", "--help", action="store_true")
    diff.add_argument("--from", dest="from_snap", metavar="SNAP")
    diff.add_argument("--to", dest="to_snap", metavar="SNAP")

    return root


async def _main() -> None:
    parser = _build_parser()
    ns = parser.parse_args()
    args = vars(ns)

    dispatcher = AppDispatcher()
    stream = await dispatcher.dispatch(args.get("command"), args)
    use_json = args.get("json", False)

    async for event in stream:
        if use_json:
            print(event.to_ndjson(), flush=True)
        elif event.msg:
            print(event.msg, flush=True)

    if stream.result and not stream.result.ok:
        sys.exit(1)


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(130)
