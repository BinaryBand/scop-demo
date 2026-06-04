from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import IO, Any, cast

from scop.app.dispatcher import AppDispatcher
from scop.models.protocol import MSGID


@dataclass
class FormParam:
    name: str
    kind: str
    metavar: str | None = None
    required: bool = False
    default: str | None = None
    short: str | None = None
    input_type: str | None = None
    options: list[str] = field(default_factory=list)


@dataclass
class ActionItem:
    label: str
    command: str
    description: str
    params: list[FormParam] = field(default_factory=list)


@dataclass
class ScalarItem:
    label: str
    value: str
    unit: str = ""


@dataclass
class ListSection:
    label: str
    items: list[ActionItem] = field(default_factory=list)


@dataclass
class TableSection:
    label: str
    schema: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PageView:
    ctas: list[ActionItem] = field(default_factory=list)
    nodes: list[ScalarItem | ListSection | TableSection] = field(default_factory=list)
    forms: list[ActionItem] = field(default_factory=list)


@dataclass
class UIPage:
    key: str
    title: str
    seen: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    scalars: dict[str, dict[str, Any]] = field(default_factory=dict)
    lists: dict[str, dict[str, Any]] = field(default_factory=dict)
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DecodedArgv:
    command: str
    args: dict[str, Any]
    output_path: str | None
    version: bool


def parse_ndjson(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _title(s: str) -> str:
    return s.replace("_", " ").replace("-", " ").strip().title()


def _to_form_params(raw_params: object) -> list[FormParam]:
    if not isinstance(raw_params, list):
        return []
    out: list[FormParam] = []
    for raw in raw_params:
        if not isinstance(raw, dict):
            continue
        raw_map = cast(dict[str, object], raw)
        options_raw = raw_map.get("options")
        options = [str(o) for o in options_raw] if isinstance(options_raw, list) else []
        out.append(
            FormParam(
                name=str(raw_map.get("name", "")),
                kind=str(raw_map.get("kind", "")),
                metavar=(None if raw_map.get("metavar") is None else str(raw_map.get("metavar"))),
                required=bool(raw_map.get("required", False)),
                default=(None if raw_map.get("default") is None else str(raw_map.get("default"))),
                short=(None if raw_map.get("short") is None else str(raw_map.get("short"))),
                input_type=(
                    None if raw_map.get("input_type") is None else str(raw_map.get("input_type"))
                ),
                options=options,
            )
        )
    return out


def _value_to_action_item(raw_value: object) -> ActionItem | None:
    if not isinstance(raw_value, dict):
        return None
    value_map = cast(dict[str, object], raw_value)
    command = str(value_map.get("command", "")).strip()
    if not command:
        return None
    description = str(value_map.get("description", ""))
    label = _title(command.split()[-1])
    params = _to_form_params(value_map.get("params"))
    return ActionItem(label=label, command=command, description=description, params=params)


def _has_value_param(item: ActionItem) -> bool:
    for p in item.params:
        if p.kind == "positional" and p.required:
            return True
        if p.kind == "flag" and p.metavar and (p.required or p.default is not None):
            return True
    return False


def build_page_view(
    events: list[dict[str, Any]], *, is_subpage: bool = False, ok: bool = True
) -> PageView:
    del ok  # Kept for backwards compatibility.
    page = PageView()
    pending_scalars: list[ScalarItem] = []
    i = 0

    def flush_scalars() -> None:
        if pending_scalars:
            page.nodes.extend(pending_scalars)
            pending_scalars.clear()

    while i < len(events):
        ev = events[i]
        msgid = str(ev.get("msgid", ""))

        if msgid == MSGID.SCALAR_SET:
            pending_scalars.append(
                ScalarItem(
                    label=str(ev.get("label", ev.get("id", ""))),
                    value=str(ev.get("value", "")),
                    unit=str(ev.get("unit", "")),
                )
            )
            i += 1
            continue

        if msgid == MSGID.TABLE_DECLARE:
            flush_scalars()
            table_id = str(ev.get("id", ""))
            schema_raw = ev.get("schema")
            schema = [str(c) for c in schema_raw] if isinstance(schema_raw, list) else []
            table = TableSection(label=str(ev.get("label", table_id)), schema=schema, rows=[])
            i += 1
            while i < len(events):
                row_ev = events[i]
                row_msgid = str(row_ev.get("msgid", ""))
                if row_msgid == MSGID.TABLE_END and str(row_ev.get("id", "")) == table_id:
                    i += 1
                    break
                if row_msgid == MSGID.TABLE_ROW and str(row_ev.get("id", "")) == table_id:
                    values = row_ev.get("values")
                    if isinstance(values, dict):
                        table.rows.append({str(k): str(v) for k, v in values.items()})
                i += 1
            page.nodes.append(table)
            continue

        if msgid == MSGID.LIST_DECLARE:
            flush_scalars()
            list_id = str(ev.get("id", ""))
            list_label = str(ev.get("label", list_id))
            raw_items: list[ActionItem] = []
            i += 1
            while i < len(events):
                item_ev = events[i]
                item_msgid = str(item_ev.get("msgid", ""))
                if item_msgid == MSGID.LIST_END and str(item_ev.get("id", "")) == list_id:
                    i += 1
                    break
                if item_msgid == MSGID.LIST_APPEND and str(item_ev.get("id", "")) == list_id:
                    parsed = _value_to_action_item(item_ev.get("value"))
                    if parsed is not None:
                        raw_items.append(parsed)
                i += 1

            if is_subpage:
                page.forms.extend(raw_items)
                continue

            list_nodes: list[ActionItem] = []
            for item in raw_items:
                non_flag_tokens = [t for t in item.command.split() if not t.startswith("-")]
                if len(non_flag_tokens) >= 2:
                    page.ctas.append(item)
                elif _has_value_param(item):
                    page.forms.append(item)
                else:
                    list_nodes.append(item)

            if list_nodes:
                page.nodes.append(ListSection(label=list_label, items=list_nodes))
            continue

        # Page framing and unsupported message families do not alter PageView here.
        i += 1

    flush_scalars()
    return page


def render_tty(view: PageView, out: IO[str]) -> None:
    for node in view.nodes:
        if isinstance(node, ScalarItem):
            unit = f" {node.unit}" if node.unit else ""
            out.write(f"{node.label}: {node.value}{unit}\n")
            continue
        if isinstance(node, TableSection):
            out.write(f"\n{node.label}\n")
            if node.schema:
                out.write(" | ".join(node.schema) + "\n")
            for row in node.rows:
                out.write(" | ".join(row.get(col, "") for col in node.schema) + "\n")
            continue
        if isinstance(node, ListSection):
            out.write(f"\n{node.label}:\n")
            for item in node.items:
                out.write(f"  {item.label:<8} {item.description}\n")
            continue

    if view.ctas:
        out.write("\nActions:\n")
        for cta in view.ctas:
            out.write(f"  {cta.label:<8} {cta.description}\n")

    if view.forms:
        out.write("\nForms:\n")
        for form in view.forms:
            out.write(f"  {form.label:<8} {form.description}\n")


def to_ndjson(events: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(ev) + "\n" for ev in events)


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


def _collect_events_sync(command: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    async def _run() -> tuple[list[dict[str, Any]], bool]:
        dispatcher = AppDispatcher.default(validate=False)
        stream = dispatcher.dispatch(command, args)
        events: list[dict[str, Any]] = []
        async for ev in stream:
            events.extend(parse_ndjson(ev.to_ndjson()))
        result = stream.result
        with contextlib.suppress(Exception):
            current = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        if result is None:
            return events, False
        return events, bool(result.ok)

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run())
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def dispatch_events(command: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    return _collect_events_sync(command, args)


def emit_help_ndjson(command: str | None, *, out: IO[str]) -> None:
    if command is None:
        events, _ok = dispatch_events("", {"help": True})
    elif command == "snapshot":
        events, _ok = dispatch_events("snapshot", {"help": True})
    elif command == "snapshot create":
        events, _ok = dispatch_events("snapshot", {"help": True, "action": "create"})
    elif command == "snapshot restore":
        events, _ok = dispatch_events("snapshot", {"help": True, "action": "restore"})
    elif command == "snapshot diff":
        events, _ok = dispatch_events("snapshot", {"help": True, "action": "diff"})
    elif command == "config":
        events, _ok = dispatch_events("config", {"help": True})
    else:
        events, _ok = dispatch_events("", {"help": True})
    out.write(to_ndjson(events))


class UIModel:
    """State-only UI model: command tree, page contents, and active page."""

    def __init__(self) -> None:
        self.pages: dict[str, UIPage] = {}
        self.active_page: str | None = None

    def initialize(self) -> None:
        """Load root help and create one page per top-level command."""
        events, _ok = dispatch_events("", {"help": True})
        for ev in events:
            if ev.get("msgid") != MSGID.LIST_APPEND or ev.get("id") != "help":
                continue
            value = ev.get("value")
            if not isinstance(value, dict):
                continue
            key = str(value.get("command", "")).strip()
            if not key or " " in key:
                continue
            if key in self.pages:
                continue
            label = str(value.get("description", key))
            self.pages[key] = UIPage(key=key, title=label)

        if self.active_page is None and self.pages:
            self.active_page = next(iter(self.pages.keys()))

        if self.active_page is not None:
            self.ensure_loaded(self.active_page)

    def set_active_page(self, key: str) -> None:
        if key not in self.pages:
            self.pages[key] = UIPage(key=key, title=key)
        self.active_page = key
        self.ensure_loaded(key)

    def ensure_loaded(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            page = UIPage(key=key, title=key)
            self.pages[key] = page
        if page.seen:
            return

        # Minimal probing strategy requested: help + status + list.
        probes: list[dict[str, Any]] = [{"help": True}, {"status": True}, {"list": True}]
        for probe in probes:
            events, _ok = dispatch_events(key, probe)
            self.ingest_many(events)
        page.seen = True

    def ingest_many(self, events: list[dict[str, Any]]) -> None:
        for ev in events:
            self.ingest(ev)

    def ingest(self, event: dict[str, Any]) -> None:
        room_raw = event.get("room")
        page_key = self._room_to_page_key(room_raw)
        if page_key is None:
            page_key = self.active_page
        if page_key is None:
            return

        page = self.pages.get(page_key)
        if page is None:
            page = UIPage(key=page_key, title=page_key)
            self.pages[page_key] = page

        msgid = str(event.get("msgid", ""))
        if msgid == MSGID.PAGE_BEGIN:
            # First PAGE_BEGIN creates the page; duplicates are ignored.
            page.seen = True
        elif msgid == MSGID.SCALAR_SET:
            scalar_id = str(event.get("id", ""))
            if scalar_id:
                page.scalars[scalar_id] = event
        elif msgid == MSGID.LIST_DECLARE:
            list_id = str(event.get("id", ""))
            if list_id and list_id not in page.lists:
                page.lists[list_id] = {"declare": event, "items": []}
        elif msgid == MSGID.LIST_APPEND:
            list_id = str(event.get("id", ""))
            entry = page.lists.get(list_id)
            if entry is None:
                entry = {"declare": {"id": list_id, "label": list_id}, "items": []}
                page.lists[list_id] = entry
            items = entry.get("items")
            if isinstance(items, list):
                items.append(event)
        elif msgid == MSGID.TABLE_DECLARE:
            table_id = str(event.get("id", ""))
            if table_id and table_id not in page.tables:
                page.tables[table_id] = {"declare": event, "rows": []}
        elif msgid == MSGID.TABLE_ROW:
            table_id = str(event.get("id", ""))
            entry = page.tables.get(table_id)
            if entry is None:
                entry = {"declare": {"id": table_id, "schema": []}, "rows": []}
                page.tables[table_id] = entry
            rows = entry.get("rows")
            if isinstance(rows, list):
                rows.append(event)

        page.events.append(event)

    def current_page(self) -> UIPage | None:
        if self.active_page is None:
            return None
        return self.pages.get(self.active_page)

    @staticmethod
    def _room_to_page_key(room: object) -> str | None:
        if not isinstance(room, str):
            return None
        key = room.strip()
        if not key:
            return None
        if "/" in key:
            return key.split("/", 1)[0]
        return key


__all__ = [
    "ActionItem",
    "DecodedArgv",
    "FormParam",
    "ListSection",
    "PageView",
    "ScalarItem",
    "TableSection",
    "UIModel",
    "build_page_view",
    "decode_argv",
    "dispatch_events",
    "emit_help_ndjson",
    "parse_ndjson",
    "render_tty",
    "to_ndjson",
]
