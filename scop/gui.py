from __future__ import annotations

import json
import os
import shlex
import sys
import webbrowser
from dataclasses import dataclass
from html import escape
from urllib.parse import quote_plus

from flask import Flask, Response, request

from scop.models.protocol import MSGID
from scop.utils.proc import run_resolved


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    events: list[dict[str, object]]
    raw_lines: list[str]
    parse_errors: list[str]
    returncode: int
    stderr: str


@dataclass(frozen=True)
class ActionLink:
    command: str
    description: str


@dataclass(frozen=True)
class TableModel:
    label: str
    schema: list[str]
    rows: list[dict[str, object]]


@dataclass(frozen=True)
class ListModel:
    label: str
    ordered: bool
    items: list[object]


@dataclass(frozen=True)
class PageModel:
    room: str | None
    title: str
    subtitle: str
    scalars: list[tuple[str, object]]
    tables: list[TableModel]
    lists: list[ListModel]
    actions: list[ActionLink]


def _as_str_object_map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {k: v for k, v in value.items() if isinstance(k, str)}


def _run_scop(tokens: list[str]) -> CommandResult:
    cmd = [sys.executable, "-m", "scop.cli", *tokens]
    proc = run_resolved(cmd, capture_output=True, text=True, check=False)

    events: list[dict[str, object]] = []
    raw_lines: list[str] = []
    parse_errors: list[str] = []

    for idx, raw in enumerate(proc.stdout.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        raw_lines.append(line)
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {idx}: {exc.msg}")
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
        else:
            parse_errors.append(f"line {idx}: expected object")

    return CommandResult(
        command=tokens,
        events=events,
        raw_lines=raw_lines,
        parse_errors=parse_errors,
        returncode=proc.returncode,
        stderr=proc.stderr,
    )


def _extract_actions(events: list[dict[str, object]]) -> list[ActionLink]:
    actions: list[ActionLink] = []
    for event in events:
        if event.get("msgid") != "LIST_APPEND":
            continue
        if event.get("id") != "help":
            continue
        value_map = _as_str_object_map(event.get("value"))
        if value_map is None:
            continue
        command = value_map.get("command")
        description = value_map.get("description", "")
        if isinstance(command, str):
            actions.append(
                ActionLink(
                    command=command,
                    description=description if isinstance(description, str) else "",
                )
            )
    return actions


def _parse_page(events: list[dict[str, object]], actions: list[ActionLink]) -> PageModel:
    room: str | None = None
    title = "scop"
    subtitle = ""

    scalars: list[tuple[str, object]] = []
    tables_by_id: dict[str, tuple[str, list[str], list[dict[str, object]]]] = {}
    lists_by_id: dict[str, tuple[str, bool, list[object]]] = {}

    for event in events:
        msgid = event.get("msgid")

        if msgid == MSGID.PAGE_BEGIN:
            event_room = event.get("room")
            room = event_room if isinstance(event_room, str) else None
            data_title = event.get("title")
            data_subtitle = event.get("subtitle")
            if isinstance(data_title, str) and data_title:
                title = data_title
            if isinstance(data_subtitle, str):
                subtitle = data_subtitle

        elif msgid == MSGID.SCALAR_SET:
            label = event.get("label")
            value = event.get("value")
            if isinstance(label, str):
                scalars.append((label, value))

        elif msgid == MSGID.TABLE_DECLARE:
            table_id = event.get("id")
            label = event.get("label")
            schema = event.get("schema")
            if isinstance(table_id, str) and isinstance(label, str) and isinstance(schema, list):
                columns = [c for c in schema if isinstance(c, str)]
                tables_by_id[table_id] = (label, columns, [])

        elif msgid == MSGID.TABLE_ROW:
            table_id = event.get("id")
            values = event.get("values")
            if isinstance(table_id, str) and isinstance(values, dict) and table_id in tables_by_id:
                label, cols, rows = tables_by_id[table_id]
                row = {k: v for k, v in values.items() if isinstance(k, str)}
                rows.append(row)
                tables_by_id[table_id] = (label, cols, rows)

        elif msgid == MSGID.TABLE_UPDATE:
            table_id = event.get("id")
            row_id = event.get("row_id")
            values = event.get("values")
            if (
                isinstance(table_id, str)
                and isinstance(row_id, str)
                and isinstance(values, dict)
                and table_id in tables_by_id
            ):
                label, cols, rows = tables_by_id[table_id]
                updated = False
                for row in rows:
                    existing_row_id = row.get("row_id")
                    if isinstance(existing_row_id, str) and existing_row_id == row_id:
                        row.update({k: v for k, v in values.items() if isinstance(k, str)})
                        updated = True
                        break
                if not updated:
                    row = {k: v for k, v in values.items() if isinstance(k, str)}
                    row["row_id"] = row_id
                    rows.append(row)
                tables_by_id[table_id] = (label, cols, rows)

        elif msgid == MSGID.LIST_DECLARE:
            list_id = event.get("id")
            label = event.get("label")
            ordered = event.get("ordered")
            if isinstance(list_id, str) and isinstance(label, str):
                lists_by_id[list_id] = (label, bool(ordered), [])

        elif msgid == MSGID.LIST_APPEND:
            list_id = event.get("id")
            value = event.get("value")
            if isinstance(list_id, str) and list_id in lists_by_id:
                label, ordered, items = lists_by_id[list_id]
                if list_id != "help":
                    items.append(value)
                    lists_by_id[list_id] = (label, ordered, items)

        elif msgid == MSGID.LIST_UPDATE:
            list_id = event.get("id")
            item_id = event.get("item_id")
            value = event.get("value")
            if isinstance(list_id, str) and isinstance(item_id, str) and list_id in lists_by_id:
                label, ordered, items = lists_by_id[list_id]
                replaced = False
                for i, item in enumerate(items):
                    item_map = _as_str_object_map(item)
                    if item_map is not None and item_map.get("item_id") == item_id:
                        items[i] = value
                        replaced = True
                        break
                if not replaced:
                    items.append(value)
                lists_by_id[list_id] = (label, ordered, items)

    tables: list[TableModel] = [
        TableModel(label=label, schema=schema, rows=rows)
        for (label, schema, rows) in tables_by_id.values()
    ]
    lists: list[ListModel] = [
        ListModel(label=label, ordered=ordered, items=items)
        for (label, ordered, items) in lists_by_id.values()
        if label.lower() != "help"
    ]

    return PageModel(
        room=room,
        title=title,
        subtitle=subtitle,
        scalars=scalars,
        tables=tables,
        lists=lists,
        actions=actions,
    )


def _help_tokens_for(tokens: list[str]) -> list[str]:
    if not tokens:
        return ["--help"]

    if "--help" in tokens or "-h" in tokens:
        return tokens

    command_tokens: list[str] = []
    for tok in tokens:
        if tok.startswith("-"):
            break
        command_tokens.append(tok)

    if not command_tokens:
        return ["--help"]

    return [*command_tokens, "--help"]


def _tokens_from_query(query_value: str) -> list[str]:
    try:
        parsed = shlex.split(query_value)
    except ValueError:
        return []
    return [tok.strip() for tok in parsed if tok.strip()]


def _is_safe_token(tok: str) -> bool:
    if not tok:
        return False
    for ch in tok:
        if ch.isalnum() or ch in {"-", "_", "/", ".", ":"}:
            continue
        return False
    return True


def _is_allowed_command(tokens: list[str]) -> bool:
    if not tokens:
        return True

    if not all(_is_safe_token(tok) for tok in tokens):
        return False

    if tokens[0].startswith("-"):
        return tokens[0] in {"--help", "--version"}

    if tokens[0] != "snapshot":
        return False

    allowed_flags = {
        "--help",
        "-h",
        "--status",
        "--list",
        "-l",
        "--all",
        "-a",
        "--dry-run",
        "-n",
        "--recursive",
        "-r",
        "--force",
        "-f",
        "--from",
        "--to",
        "--verbose",
        "-v",
        "--quiet",
        "-q",
    }
    allowed_words = {"snapshot", "create", "diff"}

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in {"--from", "--to"}:
            if i + 1 >= len(tokens):
                return False
            value = tokens[i + 1]
            if value.startswith("-"):
                return False
            i += 2
            continue
        if tok in allowed_flags or tok in allowed_words:
            i += 1
            continue
        return False

    return True


def _build_view(
    tokens: list[str],
) -> tuple[PageModel, CommandResult, CommandResult | None, str | None]:
    if not _is_allowed_command(tokens):
        primary = CommandResult(tokens, [], [], ["command blocked by GUI safety filter"], 2, "")
        page = PageModel(
            room=None,
            title="Blocked command",
            subtitle="The GUI safety filter rejected this command.",
            scalars=[],
            tables=[],
            lists=[],
            actions=[],
        )
        return page, primary, None, "command is not allowed in this POC"

    primary = _run_scop(tokens)
    help_tokens = _help_tokens_for(tokens)
    help_result: CommandResult | None = None

    actions = _extract_actions(primary.events)
    if help_tokens != tokens:
        help_result = _run_scop(help_tokens)
        if not actions:
            actions = _extract_actions(help_result.events)

    page = _parse_page(primary.events, actions)
    warning: str | None = None
    if primary.returncode != 0:
        warning = "command returned a non-zero exit status"

    return page, primary, help_result, warning


def _render_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return escape(json.dumps(value, ensure_ascii=True))
    return escape(str(value))


def _render_page(
    page: PageModel,
    primary: CommandResult,
    help_result: CommandResult | None,
    warning: str | None,
) -> str:
    room_display = page.room if page.room is not None else "root"

    actions_html = "".join(
        (
            "<li>"
            f'<a href="/run?cmd={quote_plus(link.command)}">{escape(link.command)}</a>'
            f" <span>{escape(link.description)}</span>"
            "</li>"
        )
        for link in page.actions
    )
    if not actions_html:
        actions_html = "<li>(no actions discovered)</li>"

    scalar_html = "".join(
        f"<li><strong>{escape(label)}</strong>: {_render_value(value)}</li>"
        for label, value in page.scalars
    )
    if not scalar_html:
        scalar_html = "<li>(no scalar values)</li>"

    list_sections: list[str] = []
    for lst in page.lists:
        tag = "ol" if lst.ordered else "ul"
        list_items = (
            "".join(f"<li>{_render_value(item)}</li>" for item in lst.items) or "<li>(empty)</li>"
        )
        list_sections.append(
            f"<section><h3>{escape(lst.label)}</h3><{tag}>{list_items}</{tag}></section>"
        )
    lists_html = "".join(list_sections) if list_sections else "<p>(no list content)</p>"

    table_sections: list[str] = []
    for tbl in page.tables:
        headers = "".join(f"<th>{escape(col)}</th>" for col in tbl.schema)
        rows = []
        for row in tbl.rows:
            cells = "".join(f"<td>{_render_value(row.get(col, ''))}</td>" for col in tbl.schema)
            rows.append(f"<tr>{cells}</tr>")
        body = "".join(rows) if rows else "<tr><td colspan='99'>(empty)</td></tr>"
        table_sections.append(
            "<section>"
            f"<h3>{escape(tbl.label)}</h3>"
            "<table border='1' cellspacing='0' cellpadding='4'>"
            f"<thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table>"
            "</section>"
        )
    tables_html = "".join(table_sections) if table_sections else "<p>(no table content)</p>"

    parse_errors = list(primary.parse_errors)
    if help_result is not None:
        parse_errors.extend(help_result.parse_errors)

    parse_html = "".join(f"<li>{escape(err)}</li>" for err in parse_errors) or "<li>(none)</li>"

    event_dump = "\n".join(primary.raw_lines)

    warning_html = ""
    if warning:
        warning_html = f"<p><strong>Warning:</strong> {escape(warning)}</p>"

    stderr_html = ""
    if primary.stderr.strip():
        stderr_html = f"<pre>{escape(primary.stderr.strip())}</pre>"

    current_cmd = " ".join(primary.command) if primary.command else "(root)"

    return (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'><title>scop-gui</title></head><body>"
        "<h1>scop-gui</h1>"
        f"<p><strong>Room:</strong> {escape(room_display)}</p>"
        f"<h2>{escape(page.title)}</h2>"
        f"<p>{escape(page.subtitle)}</p>"
        f"<p><strong>Command:</strong> {escape(current_cmd)}</p>"
        f"{warning_html}"
        "<nav><h3>Actions (auto-generated from --help)</h3><ul>"
        f"{actions_html}"
        "</ul></nav>"
        "<section><h3>Scalars</h3><ul>"
        f"{scalar_html}"
        "</ul></section>"
        "<section><h3>Tables</h3>"
        f"{tables_html}"
        "</section>"
        "<section><h3>Lists</h3>"
        f"{lists_html}"
        "</section>"
        "<section><h3>Parse Errors</h3><ul>"
        f"{parse_html}"
        "</ul></section>"
        "<section><h3>stderr</h3>"
        f"{stderr_html or '<p>(none)</p>'}"
        "</section>"
        "<section><h3>Raw NDJSON</h3>"
        f"<pre>{escape(event_dump)}</pre>"
        "</section>"
        "</body></html>"
    )


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def home() -> Response:
        page, primary, help_result, warning = _build_view([])
        return Response(
            _render_page(page, primary, help_result, warning),
            mimetype="text/html",
        )

    @app.get("/run")
    def run_command() -> Response:
        query_cmd = request.args.get("cmd", "")
        tokens = _tokens_from_query(query_cmd)
        page, primary, help_result, warning = _build_view(tokens)
        return Response(
            _render_page(page, primary, help_result, warning),
            mimetype="text/html",
        )

    @app.get("/room/<path:room>")
    def run_room(room: str) -> Response:
        tokens = [tok for tok in room.split("/") if tok]
        page, primary, help_result, warning = _build_view(tokens)
        return Response(
            _render_page(page, primary, help_result, warning),
            mimetype="text/html",
        )

    return app


def main() -> None:
    host = os.getenv("SCOP_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("SCOP_GUI_PORT", "8765"))
    auto_open = os.getenv("SCOP_GUI_OPEN", "1") != "0"

    url = f"http://{host}:{port}/"
    if auto_open:
        webbrowser.open(url)

    app = create_app()
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
