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
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from scop.app.dispatcher import AppDispatcher
from scop.utils.proc import run_resolved


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


def _run_scop_ndjson(args: list[str]) -> list[dict[str, object]]:
    result = run_resolved(
        ["scop", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"scop {' '.join(args)} failed")

    events: list[dict[str, object]] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(cast(dict[str, object], payload))
    return events


def _as_obj_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _split_command_tokens(command: str) -> list[str]:
    # SCOP help command values are plain command lines; whitespace tokenization
    # keeps this helper stdlib-allowlist friendly in this module.
    return [token for token in command.strip().split() if token]


def _try_run_scop_ndjson(args: list[str]) -> list[dict[str, object]]:
    try:
        return _run_scop_ndjson(args)
    except RuntimeError:
        return []


def _find_page_begin(events: list[dict[str, object]]) -> tuple[str, str, str]:
    for event in events:
        if event.get("msgid") != "PAGE_BEGIN":
            continue
        room = event.get("room")
        title = event.get("title")
        subtitle = event.get("subtitle")
        return (
            room if isinstance(room, str) else "",
            title if isinstance(title, str) else "",
            subtitle if isinstance(subtitle, str) else "",
        )
    return "", "", ""


def _help_items(events: list[dict[str, object]]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for event in events:
        if event.get("msgid") != "LIST_APPEND" or event.get("id") != "help":
            continue
        value = _as_obj_dict(event.get("value"))
        if value is not None:
            items.append(value)
    return items


def _status_stats(events: list[dict[str, object]]) -> list[dict[str, object]]:
    stats: list[dict[str, object]] = []
    for event in events:
        if event.get("msgid") != "SCALAR_SET":
            continue
        item: dict[str, object] = {}
        for key in ("id", "label", "type", "unit"):
            value = event.get(key)
            if isinstance(value, (str, int, float, bool)):
                item[key] = value
        if "id" in item and "label" in item and "type" in item:
            stats.append(item)
    return stats


def _list_schema(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in events:
        if event.get("msgid") != "TABLE_DECLARE":
            continue
        schema = event.get("schema")
        if not isinstance(schema, list):
            continue
        cols = [col for col in schema if isinstance(col, str)]
        if cols:
            return {"schema": cols}
    return None


def _display_name(exec_command: str) -> str:
    tokens = [t for t in _split_command_tokens(exec_command) if not t.startswith("-")]
    if not tokens:
        tokens = [exec_command]
    leaf = tokens[-1] if tokens else exec_command
    return leaf.replace("-", " ").title()


def _normalize_param(param: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in (
        "name",
        "kind",
        "type",
        "short",
        "metavar",
        "description",
        "required",
        "repeatable",
        "default",
        "pattern",
        "choices",
        "min",
        "max",
        "format",
        "min_length",
        "max_length",
    ):
        value = param.get(key)
        if value is None:
            continue
        normalized[key] = value
    return normalized


def _route_room_for_exec(exec_command: str) -> str | None:
    tokens = _split_command_tokens(exec_command)
    if not tokens or any(token.startswith("-") for token in tokens):
        return None
    help_events = _try_run_scop_ndjson([*tokens, "--help"])
    room, _title, _subtitle = _find_page_begin(help_events)
    return room or None


def _discover_room(exec_tokens: list[str]) -> dict[str, object]:
    help_events = _run_scop_ndjson([*exec_tokens, "--help"])
    room_id, title, subtitle = _find_page_begin(help_events)

    room: dict[str, object] = {"id": room_id, "title": title, "subtitle": subtitle}

    status_events = _try_run_scop_ndjson([*exec_tokens, "--status"])
    stats = _status_stats(status_events)
    if stats:
        room["stats"] = stats

    list_events = _try_run_scop_ndjson([*exec_tokens, "--list"])
    schema = _list_schema(list_events)
    if schema is not None:
        room["list"] = schema

    commands: list[dict[str, object]] = []
    for help_value in _help_items(help_events):
        command_value = help_value.get("command")
        description_value = help_value.get("description")
        if not isinstance(command_value, str) or not isinstance(description_value, str):
            continue

        cmd: dict[str, object] = {
            "name": _display_name(command_value),
            "exec": command_value,
            "description": description_value,
            "kind": help_value.get("kind", "action")
            if isinstance(help_value.get("kind", "action"), str)
            else "action",
        }

        raw_params = help_value.get("params")
        if isinstance(raw_params, list):
            params: list[dict[str, object]] = []
            for raw in raw_params:
                raw_dict = _as_obj_dict(raw)
                if raw_dict is None:
                    continue
                normalized = _normalize_param(raw_dict)
                if normalized:
                    params.append(normalized)
            if params:
                cmd["params"] = params

        navigates = _route_room_for_exec(command_value)
        if isinstance(navigates, str) and navigates != room_id:
            cmd["navigates"] = navigates

        commands.append(cmd)
    room["commands"] = commands
    return room


def _common_global_params(rooms: list[dict[str, object]]) -> list[dict[str, object]]:
    action_param_sets: list[dict[str, dict[str, object]]] = []
    for room in rooms:
        commands = room.get("commands")
        if not isinstance(commands, list):
            continue
        for command in commands:
            command_dict = _as_obj_dict(command)
            if command_dict is None:
                continue
            if command_dict.get("kind") != "action":
                continue
            params = command_dict.get("params")
            if not isinstance(params, list):
                continue
            by_name: dict[str, dict[str, object]] = {}
            for raw in params:
                raw_dict = _as_obj_dict(raw)
                if raw_dict is None:
                    continue
                name = raw_dict.get("name")
                if not isinstance(name, str):
                    continue
                kind = raw_dict.get("kind")
                required = raw_dict.get("required", False)
                if kind == "flag" and required is False:
                    by_name[name] = dict(raw_dict)
            if by_name:
                action_param_sets.append(by_name)

    if not action_param_sets:
        return []

    common_names = set(action_param_sets[0])
    for by_name in action_param_sets[1:]:
        common_names &= set(by_name)

    globals_out: list[dict[str, object]] = []
    for name in sorted(common_names):
        template = dict(action_param_sets[0][name])
        globals_out.append(template)
    return globals_out


def _remove_global_params(
    rooms: list[dict[str, object]], global_params: list[dict[str, object]]
) -> list[dict[str, object]]:
    global_names = {
        name for param in global_params for name in [param.get("name")] if isinstance(name, str)
    }
    if not global_names:
        return rooms

    out_rooms: list[dict[str, object]] = []
    for room in rooms:
        room_copy = dict(room)
        commands = room.get("commands")
        if not isinstance(commands, list):
            out_rooms.append(room_copy)
            continue

        new_commands: list[dict[str, object]] = []
        for command in commands:
            command_dict = _as_obj_dict(command)
            if command_dict is None:
                continue
            command_copy = dict(command_dict)
            params = command_dict.get("params")
            if isinstance(params, list):
                filtered: list[dict[str, object]] = []
                for raw in params:
                    raw_dict = _as_obj_dict(raw)
                    if raw_dict is None:
                        continue
                    name = raw_dict.get("name")
                    if isinstance(name, str) and name in global_names:
                        continue
                    filtered.append(dict(raw_dict))
                if filtered:
                    command_copy["params"] = filtered
                else:
                    command_copy.pop("params", None)
            new_commands.append(command_copy)

        room_copy["commands"] = new_commands
        out_rooms.append(room_copy)
    return out_rooms


def discover_manifest_draft() -> dict[str, object]:
    """Discover a draft SCOP-M manifest from live CLI discovery calls."""
    root_help = _run_scop_ndjson(["--help"])
    _root_room, root_title, root_subtitle = _find_page_begin(root_help)

    discovered_rooms: dict[str, dict[str, object]] = {}

    root_room: dict[str, object] = {
        "id": "",
        "title": root_title or "scop",
        "subtitle": root_subtitle,
        "commands": [],
    }

    seed_commands: list[str] = []
    for item in _help_items(root_help):
        command = item.get("command")
        description = item.get("description")
        if not isinstance(command, str) or not isinstance(description, str):
            continue
        kind = (
            item.get("kind", "action") if isinstance(item.get("kind", "action"), str) else "action"
        )
        cmd: dict[str, object] = {
            "name": _display_name(command),
            "exec": command,
            "description": description,
            "kind": kind,
        }
        nav_room = _route_room_for_exec(command)
        if isinstance(nav_room, str) and nav_room:
            cmd["navigates"] = nav_room
            if all(not tok.startswith("-") for tok in _split_command_tokens(command)):
                seed_commands.append(command)
        root_room["commands"].append(cmd)

    discovered_rooms[""] = root_room

    for command in seed_commands:
        tokens = _split_command_tokens(command)
        room = _discover_room(tokens)
        room_id = room.get("id")
        if isinstance(room_id, str) and room_id not in discovered_rooms:
            discovered_rooms[room_id] = room

        commands = room.get("commands")
        if not isinstance(commands, list):
            continue
        for raw_cmd in commands:
            cmd_dict = _as_obj_dict(raw_cmd)
            if cmd_dict is None:
                continue
            exec_command = cmd_dict.get("exec")
            if not isinstance(exec_command, str):
                continue
            nav_room = cmd_dict.get("navigates")
            if not isinstance(nav_room, str) or nav_room in discovered_rooms:
                continue
            if any(tok.startswith("-") for tok in _split_command_tokens(exec_command)):
                continue
            nested = _discover_room(_split_command_tokens(exec_command))
            nested_id = nested.get("id")
            if isinstance(nested_id, str) and nested_id == nav_room:
                discovered_rooms[nested_id] = nested

    rooms = [discovered_rooms[key] for key in sorted(discovered_rooms.keys())]
    global_params = _common_global_params(rooms)
    rooms = _remove_global_params(rooms, global_params)

    return {
        "app": {
            "name": "scop",
            "version": "0.1.0",
            "description": "File and directory snapshotter",
            "scop_version": "0.1.2",
        },
        "app_global_param": global_params,
        "rooms": rooms,
    }


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    return json.dumps(str(value))


def _manifest_to_toml(draft: dict[str, object]) -> str:
    lines: list[str] = []

    app = _as_obj_dict(draft.get("app"))
    if app is not None:
        lines.append("[app]")
        lines.extend(
            f"{key} = {_toml_scalar(app[key])}"
            for key in ("name", "version", "description", "scop_version")
            if key in app
        )
        lines.append("")

    global_params = draft.get("app_global_param")
    if isinstance(global_params, list):
        for param in global_params:
            param_dict = _as_obj_dict(param)
            if param_dict is None:
                continue
            lines.append("[[app.global_param]]")
            lines.extend(
                f"{key} = {_toml_scalar(param_dict[key])}"
                for key in ("name", "kind", "short", "type", "metavar", "required")
                if key in param_dict
            )
            lines.append("")

    rooms = draft.get("rooms")
    if isinstance(rooms, list):
        for room in rooms:
            room_dict = _as_obj_dict(room)
            if room_dict is None:
                continue
            lines.append("[[room]]")
            lines.extend(
                f"{key} = {_toml_scalar(room_dict[key])}"
                for key in ("id", "title", "subtitle", "icon")
                if key in room_dict
            )
            lines.append("")

            stats = room_dict.get("stats")
            if isinstance(stats, list):
                for stat in stats:
                    stat_dict = _as_obj_dict(stat)
                    if stat_dict is None:
                        continue
                    lines.append("[[room.stat]]")
                    lines.extend(
                        f"{key} = {_toml_scalar(stat_dict[key])}"
                        for key in ("id", "label", "type", "unit")
                        if key in stat_dict
                    )
                    lines.append("")

            list_def = _as_obj_dict(room_dict.get("list"))
            if list_def is not None:
                lines.append("[room.list]")
                if "schema" in list_def:
                    lines.append(f"schema = {_toml_scalar(list_def['schema'])}")
                if "display_hint" in list_def:
                    lines.append(f"display_hint = {_toml_scalar(list_def['display_hint'])}")
                lines.append("")

            commands = room_dict.get("commands")
            if isinstance(commands, list):
                for command in commands:
                    command_dict = _as_obj_dict(command)
                    if command_dict is None:
                        continue
                    lines.append("[[room.command]]")
                    lines.extend(
                        f"{key} = {_toml_scalar(command_dict[key])}"
                        for key in ("name", "exec", "description", "kind", "navigates")
                        if key in command_dict
                    )
                    lines.append("")

                    params = command_dict.get("params")
                    if isinstance(params, list):
                        for param in params:
                            param_dict = _as_obj_dict(param)
                            if param_dict is None:
                                continue
                            lines.append("[[room.command.param]]")
                            lines.extend(
                                f"{key} = {_toml_scalar(param_dict[key])}"
                                for key in (
                                    "name",
                                    "kind",
                                    "type",
                                    "short",
                                    "metavar",
                                    "description",
                                    "required",
                                    "repeatable",
                                    "default",
                                    "pattern",
                                    "choices",
                                    "min",
                                    "max",
                                    "format",
                                    "min_length",
                                    "max_length",
                                )
                                if key in param_dict
                            )
                            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _normalize_manifest(value: dict[str, object]) -> dict[str, object]:
    app: dict[str, object] = {}
    app_global_param: list[dict[str, object]] = []

    app_raw = _as_obj_dict(value.get("app"))
    if app_raw is not None:
        for key, raw in app_raw.items():
            if key == "global_param":
                continue
            app[key] = raw

        global_raw = app_raw.get("global_param")
        if isinstance(global_raw, list):
            for item in global_raw:
                item_dict = _as_obj_dict(item)
                if item_dict is not None:
                    app_global_param.append(dict(item_dict))

    if not app_global_param:
        global_alt = value.get("app_global_param")
        if isinstance(global_alt, list):
            for item in global_alt:
                item_dict = _as_obj_dict(item)
                if item_dict is not None:
                    app_global_param.append(dict(item_dict))

    rooms: list[dict[str, object]] = []
    rooms_raw = value.get("room")
    if not isinstance(rooms_raw, list):
        rooms_raw = value.get("rooms")

    if isinstance(rooms_raw, list):
        for raw_room in rooms_raw:
            room_dict = _as_obj_dict(raw_room)
            if room_dict is None:
                continue

            normalized_room: dict[str, object] = {}
            for key in ("id", "title", "subtitle", "icon"):
                if key in room_dict:
                    normalized_room[key] = room_dict[key]

            stats_raw = room_dict.get("stat")
            if not isinstance(stats_raw, list):
                stats_raw = room_dict.get("stats")
            if isinstance(stats_raw, list):
                stats: list[dict[str, object]] = []
                for raw_stat in stats_raw:
                    stat_dict = _as_obj_dict(raw_stat)
                    if stat_dict is not None:
                        stats.append(dict(stat_dict))
                if stats:
                    normalized_room["stats"] = stats

            list_raw = _as_obj_dict(room_dict.get("list"))
            if list_raw is not None:
                normalized_room["list"] = dict(list_raw)

            commands_raw = room_dict.get("command")
            if not isinstance(commands_raw, list):
                commands_raw = room_dict.get("commands")
            if isinstance(commands_raw, list):
                commands: list[dict[str, object]] = []
                for raw_command in commands_raw:
                    command_dict = _as_obj_dict(raw_command)
                    if command_dict is None:
                        continue
                    normalized_command = dict(command_dict)

                    params_raw = command_dict.get("param")
                    if not isinstance(params_raw, list):
                        params_raw = command_dict.get("params")
                    if isinstance(params_raw, list):
                        params: list[dict[str, object]] = []
                        for raw_param in params_raw:
                            param_dict = _as_obj_dict(raw_param)
                            if param_dict is not None:
                                params.append(dict(param_dict))
                        if params:
                            normalized_command["params"] = params
                    normalized_command.pop("param", None)
                    commands.append(normalized_command)
                if commands:
                    normalized_room["commands"] = commands

            rooms.append(normalized_room)

    rooms.sort(key=lambda room: str(room.get("id", "")))
    return {"app": app, "app_global_param": app_global_param, "rooms": rooms}


def _comparison_summary(draft: dict[str, object], existing: dict[str, object]) -> dict[str, object]:
    draft_norm = _normalize_manifest(draft)
    existing_norm = _normalize_manifest(existing)

    draft_ids: list[str] = []
    draft_rooms = draft_norm.get("rooms")
    if isinstance(draft_rooms, list):
        for raw_room in draft_rooms:
            room_dict = _as_obj_dict(raw_room)
            if room_dict is None:
                continue
            room_id = room_dict.get("id")
            if isinstance(room_id, str):
                draft_ids.append(room_id)

    existing_ids: list[str] = []
    existing_rooms = existing_norm.get("rooms")
    if isinstance(existing_rooms, list):
        for raw_room in existing_rooms:
            room_dict = _as_obj_dict(raw_room)
            if room_dict is None:
                continue
            room_id = room_dict.get("id")
            if isinstance(room_id, str):
                existing_ids.append(room_id)

    draft_json = json.dumps(draft_norm, sort_keys=True, separators=(",", ":"))
    existing_json = json.dumps(existing_norm, sort_keys=True, separators=(",", ":"))

    return {
        "matches": draft_json == existing_json,
        "draft_room_ids": sorted(draft_ids),
        "existing_room_ids": sorted(existing_ids),
        "missing_in_existing": sorted(set(draft_ids) - set(existing_ids)),
        "missing_in_draft": sorted(set(existing_ids) - set(draft_ids)),
    }


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
    parser.add_argument(
        "--discover-manifest",
        action="store_true",
        help="Build a draft SCOP-M manifest from live --help/--status/--list discovery.",
    )
    parser.add_argument(
        "--manifest-format",
        choices=("json", "toml"),
        default="json",
        help="Output format when using --discover-manifest.",
    )
    parser.add_argument(
        "--compare-manifest",
        default=None,
        help="Path to an existing manifest (e.g. scop.toml) for comparison summary.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    ns = parser.parse_args(argv)

    if ns.discover_manifest:
        draft = discover_manifest_draft()

        comparison: dict[str, object] | None = None
        if isinstance(ns.compare_manifest, str) and ns.compare_manifest:
            existing_path = Path(ns.compare_manifest)
            existing_manifest = tomllib.loads(existing_path.read_text(encoding="utf-8"))
            comparison = _comparison_summary(draft, dict(existing_manifest))

        if ns.manifest_format == "toml":
            sys.stdout.write(_manifest_to_toml(draft))
            if comparison is not None:
                summary = _json_dumps(comparison, pretty=True)
                sys.stderr.write(f"\ncomparison summary:\n{summary}\n")
            return 0

        payload: dict[str, object] = {"draft": draft}
        if comparison is not None:
            payload["comparison"] = comparison
        sys.stdout.write(f"{_json_dumps(payload, pretty=ns.pretty)}\n")
        return 0

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
