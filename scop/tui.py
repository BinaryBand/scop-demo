"""SCOP §10 consumer — Textual TUI.

Usage:
    scop-tui                          # standalone: loads home page, nav sidebar
    scop [command] | scop-tui         # pipe mode: render one command's output
    scop-tui --from events.ndjson     # replay a recorded stream
    scop-tui --cmd "scop snapshot"    # run a shell command and render it

Routing is mechanical: MSGID family → layout slot (SCOP §10).
No knowledge of the producing application is required.
"""

from __future__ import annotations

import io
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, TextIO

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    Static,
)

from scop.utils.proc import run_resolved

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

    # Static nav: (key, label, scop-args, parent-key|None)
    # parent=None  → root page, no back button when active
    # parent="xyz" → sub-page, back button navigates to parent
    _PAGES: ClassVar[list[tuple[str, str, list[str], str | None]]] = [
        ("home", "Home", [], None),
        ("snapshot", "Snapshots", ["snapshot"], None),
        ("list", "  List", ["snapshot", "--list"], "snapshot"),
        ("list-all", "  All", ["snapshot", "--list", "--all"], "snapshot"),
        ("diff", "  Diff", ["snapshot", "diff"], "snapshot"),
    ]

    CSS = """
    Horizontal { height: 1fr; }
    #nav {
        width: 20;
        border-right: tall $primary;
    }
    #nav-heading { padding: 1 1 0 1; color: $text-muted; text-style: bold; }
    #right { width: 1fr; }
    #back-btn { margin: 1 1 0 1; width: auto; display: none; }
    #main { height: 1fr; padding: 0 1; }
    #activity { height: 8; border-top: tall $primary; }
    .stat { margin-bottom: 1; }
    DataTable { height: auto; }
    ListView > ListItem { padding: 0 1; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("tab", "focus_next", "Next Pane"),
        Binding("shift+tab", "focus_previous", "Prev Pane"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    def __init__(self, src: TextIO | None = None, *, exit_on_eof: bool = False) -> None:
        super().__init__()
        self._src = src
        self._exit_on_eof = exit_on_eof
        self._current_key: str = "home"
        self._tables: dict[str, _TableState] = {}
        self._lists: dict[str, _ListState] = {}
        self._procs: dict[str, _ProcessState] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="nav"):
                yield Static("Pages", id="nav-heading")
                yield ListView(
                    *[
                        ListItem(Label(label), id=f"page-{key}")
                        for key, label, _, _p in self._PAGES
                    ],
                    id="nav-menu",
                )
            with Vertical(id="right"):
                yield Button("← Back", id="back-btn", variant="default")
                with ScrollableContainer(id="main"):
                    pass
        with ScrollableContainer(id="activity"):
            yield RichLog(id="log", markup=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        if self._src is not None:
            self.run_worker(self._read_stream, thread=True)
        else:
            self._navigate("home")

    # ── Stream workers ────────────────────────────────────────────────────────

    def _read_stream(self) -> None:
        if self._src is None:
            return
        for raw in self._src:
            self._process_line(raw)
        if self._exit_on_eof:
            self.call_from_thread(self.exit)

    def _run_scop(self, args: list[str]) -> None:
        exe = shutil.which("scop") or "scop"
        result = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        for raw in io.StringIO(result.stdout):
            self._process_line(raw)

    def _process_line(self, raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        try:
            event: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            self.call_from_thread(self._log, f"[red]bad json:[/red] {raw!r}")
            return
        self.call_from_thread(self._route, event)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate(self, key: str) -> None:
        page = next((p for p in self._PAGES if p[0] == key), None)
        if not page:
            return
        _, _, args, parent_key = page
        self._current_key = key
        self.query_one("#back-btn", Button).display = parent_key is not None
        captured = list(args)
        self.run_worker(lambda: self._run_scop(captured), thread=True)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if not item_id.startswith("page-"):
            return
        self._navigate(item_id[5:])  # strip "page-" prefix

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            current = next((p for p in self._PAGES if p[0] == self._current_key), None)
            parent_key = current[3] if current else None
            self._navigate(parent_key or "home")

    # ── Routing ───────────────────────────────────────────────────────────────

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

    def _active_table(self) -> DataTable | None:
        focused = self.focused
        if isinstance(focused, DataTable):
            return focused
        return next(self.query("DataTable").results(DataTable), None)

    def action_cursor_down(self) -> None:
        table = self._active_table()
        if table is not None:
            table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self._active_table()
        if table is not None:
            table.action_cursor_up()

    # PAGE ────────────────────────────────────────────────────────────────────

    def page_begin(self, e: dict[str, Any]) -> None:
        title = e.get("title") or e.get("room") or "scop"
        self.title = f"{e.get('icon', '')} {title}".strip()
        self.sub_title = e.get("subtitle", "")
        self.query_one("#main", ScrollableContainer).remove_children()
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
        self.query_one("#main", ScrollableContainer).mount(
            Static(f"[dim]{label}:[/dim]  [bold]{display}[/bold]", classes="stat")
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
        main = self.query_one("#main", ScrollableContainer)
        main.mount(Static(f"[bold]{state.label}[/bold]"), table)
        if not isinstance(self.focused, DataTable):
            table.focus()

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
        pass  # TODO: update item before list_end

    def list_remove(self, _e: dict[str, Any]) -> None:
        pass  # TODO: remove item before list_end

    def list_end(self, e: dict[str, Any]) -> None:
        state = self._lists.pop(e["id"], None)
        if not state:
            return
        main = self.query_one("#main", ScrollableContainer)
        main.mount(Static(f"[bold]{state.label}[/bold]"))
        for i, (_, value) in enumerate(state.items, 1):
            prefix = f"{i}." if state.ordered else "•"
            if isinstance(value, dict):
                cmd = value.get("command", "")
                desc = value.get("description", "")
                main.mount(Static(f"  {prefix} [cyan]{cmd}[/cyan]  [dim]{desc}[/dim]"))
            else:
                main.mount(Static(f"  {prefix} {value}"))

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


def _consume(src: TextIO | None = None, *, exit_on_eof: bool = False) -> None:
    ScopTuiApp(src, exit_on_eof=exit_on_eof).run()


def main() -> None:
    """Installed entry point: scop-tui = 'scop.tui:main'"""
    if "--help" in sys.argv or "-h" in sys.argv:
        sys.stdout.write(
            "scop-tui — SCOP §10 event stream renderer\n\n"
            "Usage:\n"
            "  scop-tui                          # standalone with nav\n"
            "  scop [command] | scop-tui         # pipe a single command\n"
            "  scop-tui --from events.ndjson     # replay recorded stream\n"
            '  scop-tui --cmd "scop snapshot"    # run command directly\n\n'
            "Keys: q quit  tab/shift+tab pane  up/down or j/k rows  ← Back home\n"
        )
        sys.exit(0)

    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--from":
        with Path(args[1]).open(encoding="utf-8") as f:
            _consume(f)
        return

    if len(args) >= 2 and args[0] == "--cmd":
        try:
            cmd_tokens = shlex.split(args[1], posix=False)
        except ValueError as exc:
            sys.stderr.write(f"Invalid --cmd value: {exc}\n")
            sys.exit(2)

        if not cmd_tokens:
            sys.stderr.write("Invalid --cmd value: empty command\n")
            sys.exit(2)

        result = run_resolved(cmd_tokens, capture_output=True, text=True, check=False)
        if result.stderr:
            sys.stderr.write(result.stderr)
        _consume(io.StringIO(result.stdout))
        if result.returncode != 0:
            sys.exit(result.returncode)
        return

    if sys.stdin.isatty():
        _consume()
        return

    _consume(sys.stdin, exit_on_eof=True)
