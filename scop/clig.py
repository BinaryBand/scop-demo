from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Protocol

from tqdm import tqdm as _tqdm

from scop.app.dispatcher import AppDispatcher
from scop.ui import is_form_param, parse_ndjson

# ── Page model ────────────────────────────────────────────────────────────────


@dataclass
class ScalarItem:
    label: str
    value: str
    unit: str


@dataclass
class TableSection:
    schema: list[str]
    rows: list[dict[str, str]]


@dataclass
class ListSection:
    label: str
    items: list[ActionItem]


@dataclass
class FormParam:
    name: str
    kind: str  # 'positional' | 'flag'
    label: str  # name.lstrip('-').replace('-', ' ').title()
    metavar: str
    required: bool
    default: str
    input_type: str  # 'text' | 'multi'
    options: list[str] = field(default_factory=list)


@dataclass
class ActionItem:
    command: str
    label: str  # last non-flag token, title-cased
    description: str
    params: list[FormParam]  # pre-filtered by is_form_param


@dataclass
class PageView:
    ctas: list[ActionItem]
    nodes: list[ScalarItem | TableSection | ListSection]
    forms: list[ActionItem]
    ok: bool = True


# ── State machine ─────────────────────────────────────────────────────────────


def _make_param(p: dict[str, Any]) -> FormParam:
    name: str = str(p.get("name", ""))
    kind: str = str(p.get("kind", "flag"))
    return FormParam(
        name=name,
        kind=kind,
        label=name.lstrip("-").replace("-", " ").title(),
        metavar=str(p.get("metavar", "")),
        required=bool(p.get("required", kind == "positional")),
        default=str(p.get("default", "")),
        input_type="multi" if p.get("input_type") == "multi" else "text",
        options=list(p["options"]) if isinstance(p.get("options"), list) else [],
    )


def _make_action(item: dict[str, Any]) -> ActionItem:
    command: str = str(item.get("command", ""))
    tokens = [t for t in command.split() if not t.startswith("-")]
    last = tokens[-1] if tokens else ""
    params = [
        _make_param(p)
        for p in (item.get("params") or [])
        if isinstance(p, dict) and is_form_param(p)
    ]
    return ActionItem(
        command=command,
        label=last.replace("-", " ").title(),
        description=str(item.get("description", "")),
        params=params,
    )


def build_page_view(
    events: list[dict[str, Any]],
    *,
    is_subpage: bool = False,
    ok: bool = True,
) -> PageView:
    """Convert a flat list of parsed SCOP events into a PageView.

    Routing mirrors `_to_html` in html.py and `renderEvents` in gui.py:
    LIST_APPEND items with 2+ non-flag tokens → CTAs; items with value params →
    forms; items with no params → ListSection (plain command list, e.g. help);
    SCALAR_SET → ScalarItem; TABLE_DECLARE + TABLE_ROWs → TableSection.
    """
    ctas: list[ActionItem] = []
    forms: list[ActionItem] = []
    nodes: list[ScalarItem | TableSection | ListSection] = []
    scalars: list[ScalarItem] = []
    i = 0

    def flush() -> None:
        nodes.extend(scalars)
        scalars.clear()

    while i < len(events):
        ev = events[i]
        msgid = str(ev.get("msgid", ""))

        if msgid == "TABLE_DECLARE":
            flush()
            schema: list[str] = list(ev.get("schema") or [])
            ev_id = ev.get("id")
            rows: list[dict[str, str]] = []
            i += 1
            while (
                i < len(events)
                and events[i].get("msgid") == "TABLE_ROW"
                and events[i].get("id") == ev_id
            ):
                rows.append({k: str(v) for k, v in (events[i].get("values") or {}).items()})
                i += 1
            nodes.append(TableSection(schema=schema, rows=rows))

        elif msgid == "LIST_DECLARE":
            flush()
            ev_id = ev.get("id")
            list_label = str(ev.get("label") or ev.get("id") or "")
            items: list[Any] = []
            i += 1
            while (
                i < len(events)
                and events[i].get("msgid") == "LIST_APPEND"
                and events[i].get("id") == ev_id
            ):
                items.append(events[i].get("value"))
                i += 1
            plain: list[ActionItem] = []
            for item in items:
                if not isinstance(item, dict) or not item.get("command"):
                    continue
                cmd_tokens = [t for t in str(item["command"]).split() if not t.startswith("-")]
                has_form = any(
                    is_form_param(p) for p in (item.get("params") or []) if isinstance(p, dict)
                )
                action = _make_action(item)
                if is_subpage:
                    forms.append(action)
                elif len(cmd_tokens) >= 2:
                    ctas.append(action)
                elif has_form:
                    forms.append(action)
                else:
                    plain.append(action)
            if plain:
                nodes.append(ListSection(label=list_label, items=plain))

        elif msgid == "SCALAR_SET":
            scalars.append(
                ScalarItem(
                    label=str(ev.get("label") or ev.get("id", "")),
                    value=str(ev.get("value", "")),
                    unit=str(ev.get("unit") or ""),
                )
            )
            i += 1

        elif msgid in {"PAGE_BEGIN", "PAGE_END", "TABLE_END", "LIST_END", "TABLE_UPDATE"}:
            i += 1

        else:
            flush()
            i += 1

    flush()
    return PageView(ctas=ctas, nodes=nodes, forms=forms, ok=ok)


# ── Terminal renderer ─────────────────────────────────────────────────────────


def _render_table(table: TableSection, out: IO[str]) -> None:
    if not table.rows:
        return
    widths = {c: len(c) for c in table.schema}
    for row in table.rows:
        for c in table.schema:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))
    header = "  " + "  ".join(c.upper().ljust(widths[c]) for c in table.schema)
    rule = "  " + "  ".join("-" * widths[c] for c in table.schema)
    out.write(f"{header}\n{rule}\n")
    for row in table.rows:
        out.write(
            "  " + "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in table.schema) + "\n"
        )


def _render_form(form: ActionItem, out: IO[str]) -> None:
    out.write(f"\n{form.label}:\n")
    if not form.params:
        return
    name_width = max(len(p.name) for p in form.params)
    meta_width = max(len(p.metavar) for p in form.params)
    for p in form.params:
        req = "required" if p.required else f"default: {p.default}" if p.default else ""
        suffix = f"  ({req})" if req else ""
        out.write(f"  {p.name.ljust(name_width)}  {p.metavar.ljust(meta_width)}{suffix}\n")


def render_tty(view: PageView, out: IO[str]) -> None:
    """Render a PageView to a terminal in clig style."""
    if view.ctas:
        cta_width = max(len(a.label) for a in view.ctas)
        out.write("\nActions:\n")
        for item in view.ctas:
            desc = f"  {item.description}" if item.description else ""
            out.write(f"  {item.label.ljust(cta_width)}{desc}\n")

    for node in view.nodes:
        if isinstance(node, ScalarItem):
            display = f"{node.value} {node.unit}".rstrip()
            out.write(f"  {node.label:<22}{display}\n")
        elif isinstance(node, TableSection):
            _render_table(node, out)
        elif isinstance(node, ListSection):
            if node.label:
                out.write(f"\n{node.label.title()}:\n")
            width = max((len(a.label) for a in node.items), default=0)
            for item in node.items:
                desc = f"  {item.description}" if item.description else ""
                out.write(f"  {item.label.ljust(width)}{desc}\n")

    for form in view.forms:
        _render_form(form, out)


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


# ── Helpers ───────────────────────────────────────────────────────────────────


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


# ── Stream renderer ───────────────────────────────────────────────────────────


async def _render_stream(
    stream: _StreamLike,
    *,
    verbose: bool,
    quiet: bool,
    color: bool,
    out: IO[str],
) -> bool:
    """Consume a SCOP event stream.

    PROCESS_* events drive real-time tqdm progress bars on stderr and are kept
    out of the PageView.  All structured data events are collected, converted to
    a PageView via build_page_view, then rendered by render_tty.  When stdout is
    not a TTY the raw NDJSON is forwarded to out unchanged.
    """
    write_ndjson = not _is_tty(out)
    show_progress = not quiet and _is_tty(sys.stderr)
    bars: dict[str, _tqdm] = {}
    events: list[dict[str, Any]] = []

    async for event in stream:
        raw = event.to_ndjson()

        if write_ndjson:
            out.write(f"{raw}\n")

        ev_list = parse_ndjson(raw)
        if not ev_list:
            continue
        ev = ev_list[0]
        msgid = str(ev.get("msgid", ""))
        pri = int(ev.get("pri", 0))
        proc_id = str(ev.get("id", ""))

        if msgid == "PROCESS_BEGIN":
            if show_progress:
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
            continue

        if msgid == "PROCESS_UPDATE" and proc_id in bars:
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

        if msgid == "PROCESS_END" and proc_id in bars:
            bars.pop(proc_id).close()
            if not write_ndjson:
                msg = str(ev.get("msg", "")).strip()
                if msg:
                    out.write(f"{msg}\n")
            continue

        if write_ndjson:
            continue

        if pri == 7 and not verbose:
            continue

        if msgid == "PROCESS_LOG":
            if not quiet:
                msg = str(ev.get("msg", "")).strip()
                if msg:
                    out.write(f"{msg}\n")
            continue

        events.append(ev)

    for bar in bars.values():
        bar.close()

    result = stream.result
    if result is None:
        raise RuntimeError("stream completed without resolve() being called")
    ok = bool(result.ok)

    if not write_ndjson:
        render_tty(build_page_view(events, ok=ok), out)

    return ok


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
            ok = await _render_stream(stream, verbose=verbose, quiet=quiet, color=color, out=out)
        except RuntimeError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1

    return 0 if ok else 1


def main() -> None:
    """Installed entry point: scop = 'scop.clig:main'"""
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stderr.fileno())
        sys.exit(0)
