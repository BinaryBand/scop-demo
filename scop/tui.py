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


@dataclass(frozen=True)
class _PageSpec:
    key: str
    label: str
    base_args: list[str]
    query_flags: list[list[str]]
    parent_key: str | None = None


# ── App ───────────────────────────────────────────────────────────────────────


class ScopTuiApp(App[None]):
    """SCOP §10 TUI consumer."""

    TITLE = "scop-tui"

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
    #cta-slot { height: auto; margin-bottom: 1; }
    #cta-row { height: auto; }
    #cta-row Button { margin-right: 1; min-width: 12; }
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
        self._pages: dict[str, _PageSpec] = {}
        self._page_order: list[str] = []
        self._composite_active = False
        self._composite_page_started = False
        self._composite_page_end_remaining = 0
        self._ensure_page(
            _PageSpec(
                key="home",
                label="Home",
                base_args=[],
                query_flags=[["--version"], ["--help"]],
                parent_key=None,
            )
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="nav"):
                yield Static("Pages", id="nav-heading")
                yield ListView(
                    *[
                        ListItem(Label(self._pages[key].label), id=self._nav_id_for_key(key))
                        for key in self._page_order
                    ],
                    id="nav-menu",
                )
            with Vertical(id="right"):
                yield Button("← Back", id="back-btn", variant="default")
                with ScrollableContainer(id="main"):
                    yield Vertical(id="cta-slot")
        with ScrollableContainer(id="activity"):
            yield RichLog(id="log", markup=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self._prime_root_pages()
        self._refresh_nav_menu()
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

    def _run_scop_pipeline(self, commands: list[list[str]]) -> None:
        for args in commands:
            self._run_scop(args)

    def _prime_root_pages(self) -> None:
        exe = shutil.which("scop") or "scop"
        try:
            result = subprocess.run(
                [exe, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        except OSError:
            return

        items: list[tuple[str, Any]] = []
        for raw in io.StringIO(result.stdout):
            line = raw.strip()
            if not line:
                continue
            try:
                event: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("msgid") != "LIST_APPEND" or event.get("id") != "help":
                continue
            items.append((str(event.get("item_id", "")), event.get("value", "")))

        if items:
            self._ingest_help_items(items)

    def _page_by_key(self, key: str) -> _PageSpec | None:
        return self._pages.get(key)

    def _commands_for_page(self, page: _PageSpec) -> list[list[str]]:
        if not page.query_flags:
            return [list(page.base_args)]
        return [[*page.base_args, *flags] for flags in page.query_flags]

    def _nav_id_for_key(self, key: str) -> str:
        return f"page-{key.replace('/', '__')}"

    def _key_from_nav_id(self, item_id: str) -> str | None:
        if not item_id.startswith("page-"):
            return None
        encoded = item_id[5:]
        return encoded.replace("__", "/")

    def _cta_id_for_key(self, key: str) -> str:
        return f"cta-{key.replace('/', '__')}"

    def _key_from_cta_id(self, item_id: str) -> str | None:
        if not item_id.startswith("cta-"):
            return None
        encoded = item_id[4:]
        return encoded.replace("__", "/")

    def _ensure_page(self, page: _PageSpec) -> None:
        if page.key in self._pages:
            return
        self._pages[page.key] = page
        self._page_order.append(page.key)

    def _refresh_nav_menu(self) -> None:
        nav = self.query_one("#nav-menu", ListView)
        for key in self._page_order:
            item_id = self._nav_id_for_key(key)
            mounted_item = next(nav.query(f"#{item_id}").results(ListItem), None)
            if mounted_item is None:
                nav.mount(ListItem(Label(self._pages[key].label), id=item_id))
                continue
            label = next(mounted_item.query("Label").results(Label), None)
            if label is not None:
                label.update(self._pages[key].label)

    def _infer_page_from_command(self, command: str, description: str) -> _PageSpec | None:
        try:
            tokens = [tok for tok in shlex.split(command, posix=False) if tok]
        except ValueError:
            return None
        subcommands = [tok for tok in tokens if not tok.startswith("-")]
        if not subcommands:
            return None

        key = "/".join(subcommands)
        if key == "home":
            return None

        depth = len(subcommands) - 1
        title = subcommands[-1].replace("-", " ").title()
        label = f"{'  ' * depth}{title}"
        if description and depth == 0:
            label = title

        if len(subcommands) == 1:
            # Render list first so primary records stay visible near the top.
            query_flags = [["--list", "--all"], ["--status"], ["--help"]]
            parent_key = "home"
        else:
            query_flags = [["--help"]]
            parent_key = "/".join(subcommands[:-1])

        return _PageSpec(
            key=key,
            label=label,
            base_args=subcommands,
            query_flags=query_flags,
            parent_key=parent_key,
        )

    def _ingest_help_items(self, items: list[tuple[str, Any]]) -> None:
        changed = False
        for _item_id, value in items:
            if not isinstance(value, dict):
                continue
            command = value.get("command")
            description = value.get("description", "")
            if not isinstance(command, str):
                continue
            page = self._infer_page_from_command(
                command, description if isinstance(description, str) else ""
            )
            if page is None or page.key in self._pages:
                continue
            self._ensure_page(page)
            changed = True
        if changed:
            self._refresh_nav_menu()

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
        page = self._page_by_key(key)
        if not page:
            return
        self._current_key = page.key
        self.query_one("#back-btn", Button).display = page.parent_key is not None

        commands = self._commands_for_page(page)
        if len(commands) > 1:
            self._composite_active = True
            self._composite_page_started = False
            self._composite_page_end_remaining = len(commands)
            captured_pipeline = [list(cmd) for cmd in commands]
            self.run_worker(lambda: self._run_scop_pipeline(captured_pipeline), thread=True)
            return

        self._composite_active = False
        self._composite_page_started = False
        self._composite_page_end_remaining = 0
        captured = list(commands[0])
        self.run_worker(lambda: self._run_scop(captured), thread=True)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        key = self._key_from_nav_id(item_id)
        if key is None:
            return
        self._navigate(key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "back-btn":
            current = self._page_by_key(self._current_key)
            parent_key = current.parent_key if current else None
            self._navigate(parent_key or "home")
            return

        cta_key = self._key_from_cta_id(button_id)
        if cta_key is not None:
            self._navigate(cta_key)

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
        if self._composite_active and self._composite_page_started:
            # In composite mode we keep one page shell while appending data from
            # subsequent SCOP query runs.
            return

        self._composite_page_started = self._composite_active
        title = e.get("title") or e.get("room") or "scop"
        icon = e.get("icon", "")
        self.title = f"{icon} {title}".strip()
        self.sub_title = e.get("subtitle", "")
        # If SCOP provided an icon, update the matching nav label (root pages only).
        # Sub-page icons (List, All, Diff) come from _PAGES defaults, not PAGE_BEGIN.
        if icon:
            page = self._page_by_key(self._current_key)
            if page and page.parent_key is None:  # root pages only — sub-pages use _PAGES defaults
                bare = " ".join(w for w in page.label.split() if all(ord(c) <= 127 for c in w))
                for item in self.query(f"#{self._nav_id_for_key(self._current_key)}").results(
                    ListItem
                ):
                    for lbl in item.query(Label).results(Label):
                        lbl.update(f"{icon} {bare}")
                    break
        main = self.query_one("#main", ScrollableContainer)
        cta_slot = self.query_one("#cta-slot", Vertical)
        cta_slot.remove_children()
        for child in list(main.children):
            if child.id == "cta-slot":
                continue
            child.remove()
        self._tables.clear()
        self._lists.clear()
        self._procs.clear()

    def page_end(self, _e: dict[str, Any]) -> None:
        if self._composite_active:
            self._composite_page_end_remaining -= 1
            if self._composite_page_end_remaining > 0:
                return
            self._composite_active = False
            self._composite_page_started = False
            self._composite_page_end_remaining = 0
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
        if e["id"] == "help":
            self._ingest_help_items(state.items)

            current_page = self._page_by_key(self._current_key)
            cta_entries: list[tuple[str, _PageSpec]] = []
            if current_page is not None:
                for key in self._page_order:
                    page = self._pages[key]
                    if page.parent_key != current_page.key:
                        continue
                    cta_label = (
                        page.base_args[-1].replace("-", " ").title() if page.base_args else page.key
                    )
                    cta_entries.append((cta_label, page))

            cta_slot = self.query_one("#cta-slot", Vertical)
            cta_slot.remove_children()
            if cta_entries:
                cta_slot.mount(Static("[bold]Actions[/bold]"))
                cta_row = Horizontal(id="cta-row")
                cta_slot.mount(cta_row)
                for label, page in cta_entries:
                    cta_row.mount(
                        Button(label, id=self._cta_id_for_key(page.key), variant="primary")
                    )

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
