from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import cast

from scop.models.manifest import (
    ManifestCommand,
    ManifestParam,
    ManifestRoomList,
    ManifestRoomStat,
    ScopManifest,
)
from scop.utils.proc import run_resolved

DEFAULT_OUT = "scop.toml"
SCHEMA_REL_PATH = "scop/models/schemas/scop.manifest.schema.json"
SCHEMA_TAG = f"#:schema {SCHEMA_REL_PATH}"


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


def _try_run_scop_ndjson(args: list[str]) -> list[dict[str, object]]:
    try:
        return _run_scop_ndjson(args)
    except RuntimeError:
        return []


def _split_command_tokens(command: str) -> list[str]:
    return [token for token in command.strip().split() if token]


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
    tokens = _split_command_tokens(exec_command)
    flag_tokens = [token for token in tokens if token.startswith("--")]
    if flag_tokens:
        leaf = flag_tokens[0].lstrip("-")
    else:
        non_flag_tokens = [token for token in tokens if not token.startswith("-")]
        leaf = non_flag_tokens[-1] if non_flag_tokens else exec_command
    return leaf.replace("-", " ").title()


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

        kind_raw = help_value.get("kind", "action")
        kind = kind_raw if isinstance(kind_raw, str) else "action"
        cmd: dict[str, object] = {
            "name": _display_name(command_value),
            "exec": command_value,
            "description": description_value,
            "kind": kind,
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
                kind = raw_dict.get("kind")
                required = raw_dict.get("required", False)
                if isinstance(name, str) and kind == "flag" and required is False:
                    by_name[name] = dict(raw_dict)
            if by_name:
                action_param_sets.append(by_name)

    if not action_param_sets:
        return []

    common_names = set(action_param_sets[0])
    for by_name in action_param_sets[1:]:
        common_names &= set(by_name)

    return [dict(action_param_sets[0][name]) for name in sorted(common_names)]


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
        kind_raw = item.get("kind", "action")
        kind = kind_raw if isinstance(kind_raw, str) else "action"
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
            nav_room = cmd_dict.get("navigates")
            if not isinstance(exec_command, str) or not isinstance(nav_room, str):
                continue
            if nav_room in discovered_rooms:
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


def _as_obj_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return value


def _load_app_defaults() -> dict[str, str]:
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        return {"name": "scop", "version": "0.1.0", "description": "", "scop_version": "0.1.2"}

    payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = _as_obj_dict(payload.get("project"))
    if project is None:
        return {"name": "scop", "version": "0.1.0", "description": "", "scop_version": "0.1.2"}

    return {
        "name": str(project.get("name", "scop")),
        "version": str(project.get("version", "0.1.0")),
        "description": str(project.get("description", "")),
        "scop_version": "0.1.2",
    }


def _normalize_param(raw: dict[str, object]) -> dict[str, object]:
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
        value = raw.get(key)
        if value is None:
            continue
        normalized[key] = value

    # Help payloads may omit `type` on some flags; infer a safe default.
    if "type" not in normalized:
        kind = normalized.get("kind")
        has_metavar = isinstance(normalized.get("metavar"), str)
        if kind == "flag" and not has_metavar:
            normalized["type"] = "boolean"
        else:
            normalized["type"] = "string"

    return normalized


def _normalize_discovered_to_manifest_payload(draft: dict[str, object]) -> dict[str, object]:
    app_defaults = _load_app_defaults()
    app_raw = _as_obj_dict(draft.get("app"))

    app: dict[str, object] = {
        "name": app_defaults["name"],
        "version": app_defaults["version"],
        "description": app_defaults["description"],
        "scop_version": app_defaults["scop_version"],
        "global_param": [],
    }

    if app_raw is not None:
        for key in ("name", "version", "description", "scop_version"):
            value = app_raw.get(key)
            if isinstance(value, str) and value:
                app[key] = value

    global_raw = draft.get("app_global_param")
    if isinstance(global_raw, list):
        params: list[dict[str, object]] = []
        for raw in global_raw:
            raw_dict = _as_obj_dict(raw)
            if raw_dict is None:
                continue
            params.append(_normalize_param(raw_dict))
        app["global_param"] = params

    room_payloads: list[dict[str, object]] = []
    rooms_raw = draft.get("rooms")
    if isinstance(rooms_raw, list):
        for raw_room in rooms_raw:
            room_dict = _as_obj_dict(raw_room)
            if room_dict is None:
                continue

            room: dict[str, object] = {
                "id": room_dict.get("id", ""),
                "title": room_dict.get("title", ""),
                "command": [],
            }

            subtitle = room_dict.get("subtitle")
            if isinstance(subtitle, str) and subtitle:
                room["subtitle"] = subtitle

            icon = room_dict.get("icon")
            if isinstance(icon, str) and icon:
                room["icon"] = icon

            stats_raw = room_dict.get("stats")
            if isinstance(stats_raw, list):
                stats: list[dict[str, object]] = []
                for raw_stat in stats_raw:
                    stat_dict = _as_obj_dict(raw_stat)
                    if stat_dict is None:
                        continue
                    item: dict[str, object] = {}
                    for key in ("id", "label", "type", "unit"):
                        value = stat_dict.get(key)
                        if value is not None:
                            item[key] = value
                    if {"id", "label", "type"}.issubset(item):
                        stats.append(item)
                if stats:
                    room["stat"] = stats

            list_raw = _as_obj_dict(room_dict.get("list"))
            if list_raw is not None:
                list_item: dict[str, object] = {}
                schema = list_raw.get("schema")
                if isinstance(schema, list):
                    cols = [col for col in schema if isinstance(col, str)]
                    if cols:
                        list_item["schema"] = cols
                display_hint = list_raw.get("display_hint")
                if isinstance(display_hint, str):
                    list_item["display_hint"] = display_hint
                if "schema" in list_item:
                    room["list"] = list_item

            commands_raw = room_dict.get("commands")
            commands: list[dict[str, object]] = []
            if isinstance(commands_raw, list):
                for raw_command in commands_raw:
                    command_dict = _as_obj_dict(raw_command)
                    if command_dict is None:
                        continue
                    name = command_dict.get("name")
                    exec_command = command_dict.get("exec")
                    description = command_dict.get("description")
                    kind = command_dict.get("kind")
                    if not (
                        isinstance(name, str)
                        and isinstance(exec_command, str)
                        and isinstance(description, str)
                        and isinstance(kind, str)
                    ):
                        continue

                    cmd: dict[str, object] = {
                        "name": name,
                        "exec": exec_command,
                        "description": description,
                        "kind": kind,
                    }

                    navigates = command_dict.get("navigates")
                    if isinstance(navigates, str) and navigates:
                        cmd["navigates"] = navigates

                    raw_params = command_dict.get("params")
                    if isinstance(raw_params, list):
                        params: list[dict[str, object]] = []
                        for raw_param in raw_params:
                            param_dict = _as_obj_dict(raw_param)
                            if param_dict is None:
                                continue
                            params.append(_normalize_param(param_dict))
                        if params:
                            cmd["param"] = params

                    commands.append(cmd)

            room["command"] = commands
            room_payloads.append(room)

    room_payloads.sort(key=lambda item: str(item.get("id", "")))
    return {"app": app, "room": room_payloads}


def _manifest_to_dict(manifest: ScopManifest) -> dict[str, object]:
    app = {
        "name": manifest.app.name,
        "version": manifest.app.version,
        "description": manifest.app.description,
        "scop_version": manifest.app.scop_version,
        "global_param": [_param_to_dict(param) for param in manifest.app.global_param],
    }

    rooms: list[dict[str, object]] = []
    for room in manifest.room:
        room_dict: dict[str, object] = {
            "id": room.id,
            "title": room.title,
            "command": [_command_to_dict(command) for command in room.command],
        }
        if room.subtitle is not None:
            room_dict["subtitle"] = room.subtitle
        if room.icon is not None:
            room_dict["icon"] = room.icon
        if room.stat:
            room_dict["stat"] = [_stat_to_dict(stat) for stat in room.stat]
        if room.list_ is not None:
            room_dict["list"] = _list_to_dict(room.list_)
        rooms.append(room_dict)

    return {"app": app, "room": rooms}


def _param_to_dict(param: ManifestParam) -> dict[str, object]:
    item = asdict(param)
    return {key: value for key, value in item.items() if value is not None}


def _command_to_dict(command: ManifestCommand) -> dict[str, object]:
    item: dict[str, object] = {
        "name": command.name,
        "exec": command.exec,
        "description": command.description,
        "kind": command.kind,
    }
    if command.navigates is not None:
        item["navigates"] = command.navigates
    if command.param:
        item["param"] = [_param_to_dict(param) for param in command.param]
    return item


def _stat_to_dict(stat: ManifestRoomStat) -> dict[str, object]:
    item: dict[str, object] = {"id": stat.id, "label": stat.label, "type": stat.type}
    if stat.unit is not None:
        item["unit"] = stat.unit
    return item


def _list_to_dict(listing: ManifestRoomList) -> dict[str, object]:
    item: dict[str, object] = {"schema": listing.schema_}
    if listing.display_hint is not None:
        item["display_hint"] = listing.display_hint
    return item


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    return json.dumps(str(value))


def _manifest_dict_to_toml(payload: dict[str, object]) -> str:
    lines: list[str] = []

    app = _as_obj_dict(payload.get("app"))
    if app is not None:
        lines.append("[app]")
        lines.extend(
            f"{key} = {_toml_scalar(app[key])}"
            for key in ("name", "version", "description", "scop_version")
            if key in app
        )
        lines.append("")

        global_params = app.get("global_param")
        if isinstance(global_params, list):
            for param in global_params:
                param_dict = _as_obj_dict(param)
                if param_dict is None:
                    continue
                lines.append("[[app.global_param]]")
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

    rooms = payload.get("room")
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

            stats = room_dict.get("stat")
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
                lines.extend(
                    f"{key} = {_toml_scalar(list_def[key])}"
                    for key in ("schema", "display_hint")
                    if key in list_def
                )
                lines.append("")

            commands = room_dict.get("command")
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

                    params = command_dict.get("param")
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


def _ensure_schema_file() -> None:
    schema_path = Path(SCHEMA_REL_PATH)
    if schema_path.exists():
        return

    result = run_resolved(
        [sys.executable, "scripts/generate.manifest_schema.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "unknown error"
        raise RuntimeError(f"failed to generate schema at {SCHEMA_REL_PATH}: {details}")


def _with_schema_tag(toml_payload: str) -> str:
    lines = toml_payload.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and lines[0].strip().startswith("#:schema "):
        lines[0] = SCHEMA_TAG
        return "\n".join(lines) + "\n"

    return f"{SCHEMA_TAG}\n\n{toml_payload.lstrip()}"


def generate_manifest() -> ScopManifest:
    draft = discover_manifest_draft()
    payload = _normalize_discovered_to_manifest_payload(draft)
    return ScopManifest.model_validate(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/generate.manifest.py",
        description="Generate SCOP manifest by exploring live app entrypoints.",
    )
    parser.add_argument(
        "--format",
        choices=("toml", "json"),
        default="toml",
        help="Output format for generated manifest.",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output path, or '-' for stdout.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    ns = parser.parse_args(argv)

    manifest = generate_manifest()
    manifest_dict = _manifest_to_dict(manifest)

    if ns.format == "json":
        output = json.dumps(
            manifest_dict,
            indent=2 if ns.pretty else None,
            sort_keys=ns.pretty,
            separators=(",", ":") if not ns.pretty else None,
        )
        if not output.endswith("\n"):
            output += "\n"
    else:
        _ensure_schema_file()
        output = _with_schema_tag(_manifest_dict_to_toml(manifest_dict))

    if ns.out == "-":
        sys.stdout.write(output)
        return 0

    out_path = Path(ns.out)
    out_path.write_text(output, encoding="utf-8")
    sys.stdout.write(f"wrote {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
