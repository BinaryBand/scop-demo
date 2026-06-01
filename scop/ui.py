"""UI-introspection helpers for SCOP applications.

This module "explores" AppDispatcher by exposing a stable, typed view of:
- registered commands and their resolved app classes,
- derived room mapping used during dispatch,
- one-off route explanation for a command + args payload.

It is intentionally read-only: no streams are spawned and no app coroutines are run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

from scop.app.dispatcher import AppDispatcher


@dataclass(frozen=True)
class CommandRoute:
    """Single dispatcher route record."""

    command: str
    room: str | None
    app_class: str


@dataclass(frozen=True)
class DispatcherOverview:
    """Serializable overview of AppDispatcher wiring."""

    runtime_class: str
    routes: list[CommandRoute]


def _route_sort_key(route: CommandRoute) -> tuple[int, str]:
    # Keep root route first, then alphabetical command order.
    return (0 if route.command == "" else 1, route.command)


def get_dispatcher_overview() -> DispatcherOverview:
    """Return a structured snapshot of default AppDispatcher wiring."""
    dispatcher = AppDispatcher.default()
    registry = dispatcher._registry
    runtime = dispatcher._runtime

    routes: list[CommandRoute] = []
    for command, app in registry.items():
        room = None if command == "" else command
        routes.append(
            CommandRoute(
                command=command,
                room=room,
                app_class=app.__class__.__name__,
            )
        )

    routes.sort(key=_route_sort_key)
    return DispatcherOverview(runtime_class=runtime.__class__.__name__, routes=routes)


def explain_dispatch(command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain how AppDispatcher would route a command.

    The returned dictionary mirrors AppDispatcher.dispatch routing logic, including
    the injected ``_room`` key, without creating a stream or spawning app.run().
    """
    dispatcher = AppDispatcher.default()
    resolved_app = dispatcher._resolve(command)  # intentional internal inspection
    room = None if command == "" else command

    merged_args: dict[str, Any] = dict(args or {})
    merged_args["_room"] = room

    return {
        "command": command,
        "room": room,
        "app_class": resolved_app.__class__.__name__,
        "args": merged_args,
    }


def _json_dumps(payload: object, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=True)
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    """CLI utility for dispatcher exploration."""
    parser = argparse.ArgumentParser(prog="python -m scop.ui")
    parser.add_argument(
        "--command",
        default=None,
        help="Command key to explain (e.g. '', snapshot). Omit for full overview.",
    )
    parser.add_argument(
        "--args-json",
        default="{}",
        help="JSON object of args used with --command.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    ns = parser.parse_args(argv)

    if ns.command is None:
        overview = get_dispatcher_overview()
        sys.stdout.write(f"{_json_dumps(asdict(overview), pretty=ns.pretty)}\n")
        return 0

    try:
        parsed_args = json.loads(ns.args_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--args-json must be valid JSON: {exc}")

    if not isinstance(parsed_args, dict):
        parser.error("--args-json must decode to a JSON object")

    result = explain_dispatch(ns.command, parsed_args)
    sys.stdout.write(f"{_json_dumps(result, pretty=ns.pretty)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
