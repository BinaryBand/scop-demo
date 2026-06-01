"""SCOP §10 consumer — routes an NDJSON event stream to rich terminal widgets.

Usage:
    scop [command] | scop-tui
    scop-tui < events.ndjson

No knowledge of scop commands or domain types is required.
All routing is mechanical: MSGID family → layout slot (SCOP §10).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, TextIO

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_console = Console(highlight=False)


# ── In-flight accumulators ────────────────────────────────────────────────────


@dataclass
class _TableState:
    label: str
    schema: list[str]
    rows: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


@dataclass
class _ListState:
    label: str
    ordered: bool
    items: list[tuple[str, Any]] = field(default_factory=list)


@dataclass
class _ProcessState:
    label: str
    total: int | None


# ── Page renderer ─────────────────────────────────────────────────────────────


class _Page:
    """Routes events within one PAGE_BEGIN → PAGE_END block."""

    def __init__(self) -> None:
        self._tables: dict[str, _TableState] = {}
        self._lists: dict[str, _ListState] = {}
        self._procs: dict[str, _ProcessState] = {}

    # PAGE ────────────────────────────────────────────────────────────────────

    def page_begin(self, e: dict[str, Any]) -> None:
        title = e.get("title") or e.get("room") or "scop"
        icon = e.get("icon", "")
        subtitle = e.get("subtitle", "")
        header = f"{icon + ' ' if icon else ''}[bold]{title}[/bold]"
        if subtitle:
            header += f"\n[dim]{subtitle}[/dim]"
        _console.print(Panel(header, expand=False, border_style="blue"))

    def page_end(self, _e: dict[str, Any]) -> None:
        _console.rule(style="dim")

    # SCALAR ──────────────────────────────────────────────────────────────────

    def scalar_set(self, e: dict[str, Any]) -> None:
        label = e.get("label") or e.get("id", "")
        value = e.get("value", "")
        unit = e.get("unit", "")
        display = f"{value}{' ' + unit if unit else ''}"
        _console.print(f"  [dim]{label}:[/dim]  [bold]{display}[/bold]")

    def scalar_clear(self, _e: dict[str, Any]) -> None:
        pass  # no inverse action in a text stream

    # TABLE ───────────────────────────────────────────────────────────────────

    def table_declare(self, e: dict[str, Any]) -> None:
        self._tables[e["id"]] = _TableState(
            label=e.get("label", e["id"]),
            schema=e.get("schema", []),
        )

    def table_row(self, e: dict[str, Any]) -> None:
        state = self._tables.get(e["id"])
        if state:
            state.rows.append((e.get("row_id", ""), e.get("values", {})))

    def table_update(self, e: dict[str, Any]) -> None:
        state = self._tables.get(e["id"])
        if not state:
            return
        row_id = e.get("row_id", "")
        for i, (rid, vals) in enumerate(state.rows):
            if rid == row_id:
                state.rows[i] = (rid, {**vals, **e.get("values", {})})
                break

    def table_end(self, e: dict[str, Any]) -> None:
        state = self._tables.pop(e["id"], None)
        if not state:
            return
        t = Table(title=state.label, box=box.SIMPLE_HEAD, border_style="dim")
        for col in state.schema:
            t.add_column(col)
        for _, vals in state.rows:
            t.add_row(*[str(vals.get(c, "")) for c in state.schema])
        _console.print(t)

    # LIST ────────────────────────────────────────────────────────────────────

    def list_declare(self, e: dict[str, Any]) -> None:
        self._lists[e["id"]] = _ListState(
            label=e.get("label", e["id"]),
            ordered=e.get("ordered", False),
        )

    def list_append(self, e: dict[str, Any]) -> None:
        state = self._lists.get(e["id"])
        if state:
            state.items.append((e.get("item_id", ""), e.get("value", "")))

    def list_update(self, e: dict[str, Any]) -> None:
        state = self._lists.get(e["id"])
        if not state:
            return
        item_id = e.get("item_id", "")
        for i, (iid, _) in enumerate(state.items):
            if iid == item_id:
                state.items[i] = (iid, e.get("value", ""))
                break

    def list_remove(self, e: dict[str, Any]) -> None:
        state = self._lists.get(e["id"])
        if state:
            item_id = e.get("item_id", "")
            state.items = [(iid, v) for iid, v in state.items if iid != item_id]

    def list_end(self, e: dict[str, Any]) -> None:
        state = self._lists.pop(e["id"], None)
        if not state:
            return
        if e["id"] == "help":
            # Actions slot (§10) — render as command palette
            t = Table(
                title=state.label,
                box=box.SIMPLE_HEAD,
                show_header=False,
                border_style="dim",
            )
            t.add_column(style="bold cyan", no_wrap=True)
            t.add_column(style="dim")
            for _, value in state.items:
                if isinstance(value, dict):
                    t.add_row(value.get("command", ""), value.get("description", ""))
                else:
                    t.add_row(str(value), "")
            _console.print(t)
        else:
            # Content slot (§10) — render as list
            _console.print(f"  [bold]{state.label}[/bold]")
            for i, (_, value) in enumerate(state.items, 1):
                prefix = f"{i}." if state.ordered else "•"
                if isinstance(value, dict):
                    display = "  ".join(f"{k}: {v}" for k, v in value.items())
                else:
                    display = str(value)
                _console.print(f"  {prefix} {display}")

    # PROCESS ─────────────────────────────────────────────────────────────────

    def process_begin(self, e: dict[str, Any]) -> None:
        label = e.get("label", e["id"])
        total = e.get("total")
        self._procs[e["id"]] = _ProcessState(label=label, total=total)
        total_str = f" [dim]({total} items)[/dim]" if total else ""
        _console.print(f"  [bold cyan]▶[/bold cyan] {label}{total_str}{_flag_tags(e)}")

    def process_update(self, e: dict[str, Any]) -> None:
        proc = self._procs.get(e["id"])
        current = e.get("current", 0)
        total = e.get("total") or (proc.total if proc else None)
        label = e.get("label", "")
        if total:
            filled = int(current / total * 20)
            bar = "█" * filled + "░" * (20 - filled)
            suffix = f"  {label}" if label else ""
            _console.print(f"  [dim]{bar}[/dim] {current}/{total}{suffix}")
        else:
            _console.print(f"  {current}{('  ' + label) if label else ''}")

    def process_log(self, e: dict[str, Any]) -> None:
        pri = e.get("pri", 6)
        msg = e.get("message") or e.get("msg", "")
        style = "dim" if pri >= 7 else "default"
        _console.print(f"  [dim]│[/dim] [{style}]{msg}[/{style}]")

    def process_end(self, e: dict[str, Any]) -> None:
        proc = self._procs.pop(e["id"], None)
        label = proc.label if proc else e["id"]
        ok = e.get("ok", True)
        icon = "[bold green]✓[/bold green]" if ok else "[bold red]✗[/bold red]"
        _console.print(f"  {icon} {label}{_flag_tags(e)}")


def _flag_tags(e: dict[str, Any]) -> str:
    parts: list[str] = []
    if e.get("dry_run"):
        parts.append("[yellow]dry-run[/yellow]")
    if e.get("recursive"):
        parts.append("[blue]recursive[/blue]")
    if e.get("force"):
        parts.append("[red]force[/red]")
    return ("  " + " ".join(parts)) if parts else ""


# ── Routing table  SCOP §10 ───────────────────────────────────────────────────

_DISPATCH: dict[str, str] = {
    "PAGE_BEGIN": "page_begin",
    "PAGE_END": "page_end",
    "SCALAR_SET": "scalar_set",
    "SCALAR_CLEAR": "scalar_clear",
    "TABLE_DECLARE": "table_declare",
    "TABLE_ROW": "table_row",
    "TABLE_UPDATE": "table_update",
    "TABLE_END": "table_end",
    "LIST_DECLARE": "list_declare",
    "LIST_APPEND": "list_append",
    "LIST_UPDATE": "list_update",
    "LIST_REMOVE": "list_remove",
    "LIST_END": "list_end",
    "PROCESS_BEGIN": "process_begin",
    "PROCESS_UPDATE": "process_update",
    "PROCESS_LOG": "process_log",
    "PROCESS_END": "process_end",
}


def _route(page: _Page, event: dict[str, Any]) -> None:
    """Dispatch one event per the §10 auto-translation table."""
    pri: int = event.get("pri", 6)
    msgid: str = event.get("msgid", "")

    if pri <= 3:
        _console.print(f"[bold red on white] ERROR [/bold red on white]  {event.get('msg', '')}")
        return
    if pri == 4:
        _console.print(f"[bold yellow] ⚠ [/bold yellow]  {event.get('msg', '')}")
        return

    handler = _DISPATCH.get(msgid)
    if handler is None:
        # Unknown MSGID — route to log area using msg (§10 conformance rule)
        _console.print(f"[dim]{event.get('msg', '')}[/dim]")
        return

    getattr(page, handler)(event)


# ── Entry point ───────────────────────────────────────────────────────────────


def _consume(src: TextIO) -> None:
    page = _Page()
    for raw in src:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            _console.print(f"[red]bad json:[/red] {raw!r}")
            continue
        _route(page, event)


def main() -> None:
    """Installed entry point: scop-tui = 'scop.tui:main'"""
    if "--help" in sys.argv or "-h" in sys.argv:
        _console.print(
            Panel(
                "[bold]scop-tui[/bold] — SCOP §10 event stream renderer\n\n"
                "[dim]Reads an NDJSON event stream from stdin and routes each\n"
                "event to a rich terminal widget by MSGID family.\n"
                "No knowledge of the producing application is required.[/dim]\n\n"
                "[dim]Usage:[/dim]\n"
                "  scop \\[command] | [bold]scop-tui[/bold]\n"
                "  [bold]scop-tui[/bold] < events.ndjson",
                title="scop-tui --help",
                expand=False,
                border_style="blue",
            )
        )
        sys.exit(0)
    if sys.stdin.isatty():
        _console.print("[dim]Usage: scop \\[command] | scop-tui[/dim]")
        sys.exit(0)
    _consume(sys.stdin)
