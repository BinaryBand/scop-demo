"""Entry point — the only file permitted to use argparse and sys.exit."""
from __future__ import annotations

import argparse
import asyncio
import sys

from scop.app.dispatcher import AppDispatcher


async def _main() -> None:
    parser = argparse.ArgumentParser(prog="scop", description="Structured CLI Output Protocol")
    parser.add_argument("command", help="Subcommand to run (snap, diff, …)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Subcommand arguments")
    ns = parser.parse_args()

    dispatcher = AppDispatcher()
    stream = await dispatcher.dispatch(ns.command, {"args": ns.args})

    async for event in stream:
        print(event.to_ndjson(), flush=True)

    if stream.result and not stream.result.ok:
        sys.exit(1)


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(130)
