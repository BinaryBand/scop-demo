"""SCOP §10 consumer — Textual TUI proof of concept.

Usage:
    scop [command] | scop-tui
    scop-tui < events.ndjson

Routing is mechanical: MSGID family → layout slot (SCOP §10).
No knowledge of the producing application is required.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, ClassVar, TextIO

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import DataTable, Footer, Header, ProgressBar, RichLog, Static

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
    total: float | None


# ── App ───────────────────────────────────────────────────────────────────────


class ScopTuiApp(App[None]):
    """SCOP §10 TUI consumer."""

    TITLE = "scop-tui"

    CSS = """
    Horizontal { height: 1fr; }
    #stats  { width: 25%; border-right: tall $primary; padding: 0 1; }
    #content { width: 75%; padding: 0 1; }
    #activity { height: 8; border-top: tall $primary; }
    .stat { margin-bottom: 1; }
    DataTable { height: auto; }
    """

    BINDINGS: ClassVar[list[Binding]] = [Binding("q", "quit", "Quit")]

    def __init__(self, src: TextIO) -> None:
        super().__init__()
        self._src = src
        self._tables: dict[str, _TableState] = {}
        self._lists: dict[str, _ListState] = {}
        self._procs: dict[str, _ProcessState] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="stats"):
                pass
            with ScrollableContainer(id="content"):
                pass
        with ScrollableContainer(id="activity"):
            yield RichLog(id="log", markup=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._read_stream, thread=True)

    def _read_stream(self) -> None:
        for raw in self._src:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                self.call_from_thread(self._log, f"[red]bad json:[/red] {raw!r}")
                continue
            self.call_from_thread(self._route, event)

    def _route(self, event: dict[str, Any]) -> None:
        pri: int = event.get("pri", 6)
        msgid: str = event.get("msgid", "")

        if pri <= 3:
            self._log(f"[bold red]ERROR[/bold red] {event.get('msg', '')}")
            return
        if pri == 4:
            self._log(f"[yellow]WARNING[/yellow] {event.get('msg', '')}")
            return

        handler = _DISPATCH.get(msgid)
        if handler is None:
            self._log(f"[dim]{event.get('msg', '')}[/dim]")
            return
        getattr(self, handler)(event)

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    # PAGE ────────────────────────────────────────────────────────────────────

    def page_begin(self, e: dict[str, Any]) -> None:
        title = e.get("title") or e.get("room") or "scop"
        self.title = f"{e.get('icon', '')} {title}".strip()
        self.sub_title = e.get("subtitle", "")
        self.query_one("#stats", ScrollableContainer).remove_children()
        self.query_one("#content", ScrollableContainer).remove_children()
        self._tables.clear()
        self._lists.clear()
        self._procs.clear()

    def page_end(self, _e: dict[str, Any]) -> None:
        self._log("[dim]── end ──[/dim]")

    # SCALAR ──────────────────────────────────────────────────────────────────

    def scalar_set(self, e: dict[str, Any]) -> None:
        label = e.get("label") or e.get("id", "")
        value = e.get("value", "")
        unit = e.get("unit", "")
        display = f"{value}{' ' + unit if unit else ''}"
        self.query_one("#stats", ScrollableContainer).mount(
            Static(f"[dim]{label}[/dim]\n[bold]{display}[/bold]", classes="stat")
        )

    def scalar_clear(self, _e: dict[str, Any]) -> None:
        pass

    # TABLE ───────────────────────────────────────────────────────────────────

    def table_declare(self, e: dict[str, Any]) -> None:
        state = _TableState(label=e.get("label", e["id"]), schema=e.get("schema", []))
        self._tables[e["id"]] = state
        table = DataTable(id=f"table-{e['id']}", cursor_type="row", zebra_stripes=True)
        for col in state.schema:
            table.add_column(col, key=col)
        content = self.query_one("#content", ScrollableContainer)
        content.mount(Static(f"[bold]{state.label}[/bold]"), table)

    def table_row(self, e: dict[str, Any]) -> None:
        state = self._tables.get(e["id"])
        if not state:
            return
        vals = e.get("values", {})
        row_id = e.get("row_id", "")
        state.rows.append((row_id, vals))
        table = self.query_one(f"#table-{e['id']}", DataTable)
        table.add_row(*[str(vals.get(c, "")) for c in state.schema], key=row_id)

    def table_update(self, e: dict[str, Any]) -> None:
        state = self._tables.get(e["id"])
        if not state:
            return
        row_id = e.get("row_id", "")
        new_vals = e.get("values", {})
        for i, (rid, vals) in enumerate(state.rows):
            if rid == row_id:
                state.rows[i] = (rid, {**vals, **new_vals})
                table = self.query_one(f"#table-{e['id']}", DataTable)
                for col, val in new_vals.items():
                    table.update_cell(row_id, col, str(val))
                break

    def table_end(self, _e: dict[str, Any]) -> None:
        pass  # table populated row-by-row via table_row

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

    def list_update(self, _e: dict[str, Any]) -> None:
        pass  # TODO: update item in accumulated list before list_end

    def list_remove(self, _e: dict[str, Any]) -> None:
        pass  # TODO: remove item from accumulated list before list_end

    def list_end(self, e: dict[str, Any]) -> None:
        state = self._lists.pop(e["id"], None)
        if not state:
            return
        content = self.query_one("#content", ScrollableContainer)
        content.mount(Static(f"[bold]{state.label}[/bold]"))
        for i, (_, value) in enumerate(state.items, 1):
            prefix = f"{i}." if state.ordered else "•"
            if isinstance(value, dict):
                cmd = value.get("command", "")
                desc = value.get("description", "")
                content.mount(Static(f"  {prefix} [cyan]{cmd}[/cyan]  [dim]{desc}[/dim]"))
            else:
                content.mount(Static(f"  {prefix} {value}"))

    # PROCESS ─────────────────────────────────────────────────────────────────

    def process_begin(self, e: dict[str, Any]) -> None:
        label = e.get("label", e["id"])
        total = e.get("total")
        self._procs[e["id"]] = _ProcessState(
            label=label, total=float(total) if total is not None else None
        )
        self._log(f"[cyan]▶[/cyan] {label}{_flag_tags(e)}")
        self.query_one("#activity", ScrollableContainer).mount(
            ProgressBar(
                total=float(total) if total is not None else None,
                id=f"proc-{e['id']}",
                show_eta=False,
            )
        )

    def process_update(self, e: dict[str, Any]) -> None:
        if e["id"] not in self._procs:
            return
        for bar in self.query(f"#proc-{e['id']}").results(ProgressBar):
            bar.progress = float(e.get("current", 0))
            break

    def process_log(self, e: dict[str, Any]) -> None:
        pri = e.get("pri", 6)
        msg = e.get("message") or e.get("msg", "")
        style = "dim" if pri >= 7 else "default"
        self._log(f"  [dim]│[/dim] [{style}]{msg}[/{style}]")

    def process_end(self, e: dict[str, Any]) -> None:
        proc = self._procs.pop(e["id"], None)
        label = proc.label if proc else e["id"]
        ok = e.get("ok", True)
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        self._log(f"  {icon} {label}{_flag_tags(e)}")
        for bar in self.query(f"#proc-{e['id']}").results(ProgressBar):
            bar.remove()
            break


# ── Helpers ───────────────────────────────────────────────────────────────────


def _flag_tags(e: dict[str, Any]) -> str:
    parts: list[str] = []
    if e.get("dry_run"):
        parts.append("[yellow]dry-run[/yellow]")
    if e.get("recursive"):
        parts.append("[blue]recursive[/blue]")
    if e.get("force"):
        parts.append("[red]force[/red]")
    return ("  " + " ".join(parts)) if parts else ""


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


# ── Entry point ───────────────────────────────────────────────────────────────


def _consume(src: TextIO) -> None:
    ScopTuiApp(src).run()


def main() -> None:
    """Installed entry point: scop-tui = 'scop.tui:main'"""
    if "--help" in sys.argv or "-h" in sys.argv:
        sys.stdout.write(
            "scop-tui — SCOP §10 event stream renderer\n\n"
            "Usage:\n"
            "  scop [command] | scop-tui\n"
            "  scop-tui < events.ndjson\n\n"
            "Keys: q quit\n"
        )
        sys.exit(0)
    if sys.stdin.isatty():
        sys.stdout.write("Usage: scop [command] | scop-tui\n")
        sys.exit(0)
    _consume(sys.stdin)
