"""SCOP §10 consumer — Textual TUI.

Usage:
    scop-tui                          # standalone: loads nav, starts on first page
    scop [command] | scop-tui         # pipe mode: render one command's output
    scop-tui --from events.ndjson     # replay a recorded stream
    scop-tui --cmd "scop snapshot"    # run a shell command and render it

Routing is mechanical: MSGID family → layout slot (SCOP §10).
No knowledge of the producing application is required.
"""

from __future__ import annotations

import io
import json
import pathlib
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, ClassVar, TextIO

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    SelectionList,
    Static,
)

from scop.utils.proc import run_resolved

# ── Accumulators ──────────────────────────────────────────────────────────────


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


@dataclass(frozen=True)
class _PageSpec:
    key: str
    label: str
    base_args: list[str]
    query_flags: list[list[str]]
    parent_key: str | None = None


def _action_needs_input(item: dict[str, Any]) -> bool:
    """True if the action has at least one required param with no pre-supplied default."""
    for p in item.get("params") or []:
        if not isinstance(p, dict):
            continue
        required = p.get("required", p.get("kind") == "positional")
        if required and "default" not in p:
            return True
    return False


# ── Error modal ───────────────────────────────────────────────────────────────


class _ErrorModal(ModalScreen[None]):
    """Blocking overlay for SCOP pri 0-3 (EMERG / ALERT / CRIT / ERR)."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape,enter,space", "dismiss_modal", show=False)]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="error-modal-box"):
            yield Static("[bold red]Error[/bold red]")
            yield Static(self._message)
            yield Button("Dismiss", variant="error", id="error-dismiss")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss_modal(self) -> None:
        self.dismiss()


# ── App ───────────────────────────────────────────────────────────────────────


class ScopTuiApp(App[None]):
    """SCOP §10 TUI consumer."""

    TITLE = "scop-tui"

    CSS = """
    Horizontal { height: 1fr; }
    #nav { width: 20; border-right: tall $primary; }
    #right { width: 1fr; }
    #back-btn { margin: 0 1; width: auto; display: none; }
    #cta-row { height: auto; margin-bottom: 1; }
    #cta-row Button { margin-right: 1; }
    #main { height: 1fr; padding: 0 1; }
    #action-form { height: auto; margin-bottom: 1; }
    #action-form Input { margin: 0 0 1 0; }
    #action-form SelectionList { height: auto; max-height: 12; margin: 0 0 1 0; }
    #activity { height: 8; border-top: tall $primary; display: none; }
    DataTable { height: auto; }
    _ErrorModal { align: center middle; }
    #error-modal-box { background: $surface; border: tall $error; padding: 1 2; width: auto;
                       max-width: 60; height: auto; }
    #error-modal-box Static { margin-bottom: 1; }
    #error-dismiss { width: auto; }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+l", "toggle_log", "Log"),
    ]

    def __init__(self, src: TextIO | None = None, *, exit_on_eof: bool = False) -> None:
        super().__init__()
        self._src = src
        self._exit_on_eof = exit_on_eof
        self._current_key: str = ""
        self._tables: dict[str, _TableState] = {}
        self._lists: dict[str, _ListState] = {}
        self._procs: dict[str, str] = {}  # id → label
        self._pages: dict[str, _PageSpec] = {}
        self._page_order: list[str] = []
        self._composite_active = False
        self._composite_page_started = False
        self._composite_page_end_remaining = 0
        self._form_inputs: dict[str, list[tuple[str, str, str, bool]]] = {}
        self._form_flags: dict[str, list[str]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="nav"):
                yield ListView(id="nav-menu")
            with Vertical(id="right"):
                yield Button("← Back", id="back-btn", variant="default")
                yield ScrollableContainer(id="main")
        with ScrollableContainer(id="activity"):
            yield RichLog(id="log")
        yield Footer()

    def on_mount(self) -> None:
        self._prime_root_pages()
        self._refresh_nav_menu()
        if self._src is not None:
            self.run_worker(self._read_stream, thread=True)
        elif self._page_order:
            self._navigate(self._page_order[0])

    # ── Stream ────────────────────────────────────────────────────────────────

    def _read_stream(self) -> None:
        if self._src is None:
            return
        for raw in self._src:
            self._process_line(raw)
        if self._exit_on_eof:
            self.call_from_thread(self.exit)

    def _run_scop(self, args: list[str]) -> None:
        exe = shutil.which("scop") or "scop"
        result = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8")
        for raw in io.StringIO(result.stdout):
            self._process_line(raw)

    def _prime_root_pages(self) -> None:
        exe = shutil.which("scop") or "scop"
        try:
            result = subprocess.run(
                [exe, "--help"], capture_output=True, text=True, encoding="utf-8", check=False
            )
        except OSError:
            return
        items: list[tuple[str, Any]] = []
        for raw in io.StringIO(result.stdout):
            line = raw.strip()
            if not line:
                continue
            try:
                ev: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("msgid") == "LIST_APPEND" and ev.get("id") == "help":
                items.append((str(ev.get("item_id", "")), ev.get("value", "")))
        if items:
            self._ingest_help_items(items)

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _page_by_key(self, key: str) -> _PageSpec | None:
        return self._pages.get(key)

    def _commands_for_page(self, page: _PageSpec) -> list[list[str]]:
        if not page.query_flags:
            return [list(page.base_args)]
        return [[*page.base_args, *f] for f in page.query_flags]

    @staticmethod
    def _kid(prefix: str, key: str) -> str:
        return f"{prefix}{key.replace('/', '__')}"

    @staticmethod
    def _kfromid(prefix: str, widget_id: str) -> str | None:
        if not widget_id.startswith(prefix):
            return None
        return widget_id[len(prefix) :].replace("__", "/")

    def _ensure_page(self, page: _PageSpec) -> None:
        if page.key not in self._pages:
            self._pages[page.key] = page
            self._page_order.append(page.key)

    def _refresh_nav_menu(self) -> None:
        nav = self.query_one("#nav-menu", ListView)
        for key in self._page_order:
            iid = self._kid("page-", key)
            item = next(nav.query(f"#{iid}").results(ListItem), None)
            if item is None:
                nav.mount(ListItem(Label(self._pages[key].label), id=iid))
            else:
                lbl = next(item.query(Label).results(Label), None)
                if lbl is not None:
                    lbl.update(self._pages[key].label)
        self._sync_nav_highlight()

    def _infer_page_from_command(self, command: str) -> _PageSpec | None:
        try:
            tokens = [t for t in shlex.split(command, posix=False) if t]
        except ValueError:
            return None
        subs = [t for t in tokens if not t.startswith("-")]
        if not subs:
            return None
        key = "/".join(subs)
        depth = len(subs) - 1
        label = f"{'  ' * depth}{subs[-1].replace('-', ' ').title()}"
        query_flags = (
            [["--list", "--all"], ["--status"], ["--help"]] if depth == 0 else [["--help"]]
        )
        return _PageSpec(
            key=key,
            label=label,
            base_args=subs,
            query_flags=query_flags,
            parent_key="/".join(subs[:-1]) if depth > 0 else None,
        )

    def _ingest_help_items(self, items: list[tuple[str, Any]]) -> None:
        changed = False
        for _, value in items:
            if not isinstance(value, dict):
                continue
            command = value.get("command")
            if not isinstance(command, str):
                continue
            page = self._infer_page_from_command(command)
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
        self._sync_nav_highlight()
        commands = self._commands_for_page(page)
        self._composite_active = len(commands) > 1
        self._composite_page_started = False
        self._composite_page_end_remaining = len(commands)
        captured = [list(c) for c in commands]
        self.run_worker(lambda: [self._run_scop(c) for c in captured], thread=True)

    def _sync_nav_highlight(self) -> None:
        nav = self.query_one("#nav-menu", ListView)
        key = self._current_key
        # Walk up to root page for highlight
        seen: set[str] = set()
        while key not in seen:
            seen.add(key)
            p = self._page_by_key(key)
            if p is None or p.parent_key is None:
                break
            key = p.parent_key
        if key in self._page_order:
            nav.index = self._page_order.index(key)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = self._kfromid("page-", event.item.id or "")
        if key:
            self._navigate(key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "back-btn":
            current = self._page_by_key(self._current_key)
            self._navigate((current.parent_key if current else None) or self._page_order[0])
            return

        form_key = self._kfromid("form-submit-", bid)
        if form_key is not None:
            page = self._page_by_key(form_key)
            if page is None:
                return
            args = list(page.base_args) + list(self._form_flags.get(form_key, []))
            missing: list[str] = []
            for iid, pname, pkind, preq in self._form_inputs.get(form_key, []):
                ml = next(self.query(f"#{iid}").results(SelectionList), None)
                if ml is not None:
                    value = ",".join(str(v) for v in ml.selected)
                else:
                    fi = next(self.query(f"#{iid}").results(Input), None)
                    value = fi.value.strip() if fi is not None else ""
                if not value:
                    if preq:
                        missing.append(pname)
                    continue
                args.extend([value] if pkind == "positional" else [pname, value])
            if missing:
                self._log(f"[yellow]missing:[/yellow] {', '.join(missing)}")
                return
            self.run_worker(lambda a=args: self._run_scop(a), thread=True)
            return

        cta_key = self._kfromid("cta-", bid)
        if cta_key:
            self._navigate(cta_key)

    # ── Form ──────────────────────────────────────────────────────────────────

    def _mount_action_form(
        self,
        main: ScrollableContainer,
        page: _PageSpec,
        items: list[tuple[str, Any]],
    ) -> bool:
        cmd = " ".join(page.base_args)
        action = next(
            (
                v
                for _, v in items
                if isinstance(v, dict)
                and v.get("command") == cmd
                and v.get("kind", "action") == "action"
            ),
            None,
        )
        self._form_inputs[page.key] = []
        self._form_flags[page.key] = []
        if action is None:
            return False

        params = action.get("params") if isinstance(action.get("params"), list) else []
        rows: list[tuple[str, str, str, bool, dict[str, Any]]] = []

        for idx, p in enumerate(params):
            if not isinstance(p, dict):
                continue
            name = (p.get("name") or "").strip()
            kind = p.get("kind")
            if not name or kind not in {"flag", "positional"}:
                continue
            required = bool(p.get("required", kind == "positional"))
            has_default = "default" in p
            if not required and not has_default:
                continue
            expects_value = (
                kind == "positional"
                or p.get("metavar")
                or has_default
                or p.get("type") != "boolean"
            )
            if not expects_value:
                self._form_flags[page.key].append(name)
                continue
            iid = f"finput-{page.key.replace('/', '__')}-{idx}"
            rows.append((iid, name, str(kind), required, p))
            self._form_inputs[page.key].append((iid, name, str(kind), required))

        if not rows and not self._form_flags[page.key]:
            return False

        form = Vertical(id="action-form")
        main.mount(form)
        for iid, name, _kind, _req, p in rows:
            form.mount(Static(f"  [dim]{name}[/dim]"))
            default_val = str(p.get("default", ""))
            placeholder = (p.get("metavar") or "value").strip()
            if p.get("input_type") == "multi":
                opts = [str(o) for o in (p.get("options") or []) if o]
                sel = {s.strip() for s in default_val.split(",") if s.strip()}
                form.mount(
                    SelectionList(
                        *[(o, o, o in sel) for o in opts + [s for s in sel if s not in opts]],
                        id=iid,
                    )
                )
            else:
                form.mount(Input(value=default_val, placeholder=placeholder, id=iid))
        return True

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route(self, event: dict[str, Any]) -> None:
        handler = _DISPATCH.get(event.get("msgid", ""))
        if handler is not None:
            getattr(self, handler)(event)
            return
        pri: int = event.get("pri", 6)
        if pri <= 3:
            self.push_screen(_ErrorModal(event.get("msg", "")))
        elif pri == 4:
            self.notify(event.get("msg", ""), severity="warning")
        else:
            self._log(f"[dim]{event.get('msg', '')}[/dim]")

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def action_toggle_log(self) -> None:
        panel = self.query_one("#activity", ScrollableContainer)
        panel.display = not panel.display

    # ── PAGE ──────────────────────────────────────────────────────────────────

    def page_begin(self, e: dict[str, Any]) -> None:
        if self._composite_active and self._composite_page_started:
            return
        self._composite_page_started = self._composite_active
        self.title = e.get("title") or e.get("room") or "scop"
        self.sub_title = e.get("subtitle", "")
        self.query_one("#main", ScrollableContainer).remove_children()
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

    # ── SCALAR ────────────────────────────────────────────────────────────────

    def scalar_set(self, e: dict[str, Any]) -> None:
        label = e.get("label") or e.get("id", "")
        value = e.get("value", "")
        unit = e.get("unit", "")
        display = f"{value}{' ' + unit if unit else ''}"
        self.query_one("#main", ScrollableContainer).mount(
            Static(f"[dim]{label}:[/dim]  [bold]{display}[/bold]")
        )

    # ── TABLE ─────────────────────────────────────────────────────────────────

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
        self.query_one(f"#table-{e['id']}", DataTable).add_row(
            *[str(vals.get(c, "")) for c in state.schema], key=row_id
        )

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

    # ── LIST ──────────────────────────────────────────────────────────────────

    def list_declare(self, e: dict[str, Any]) -> None:
        self._lists[e["id"]] = _ListState(
            label=e.get("label", e["id"]), ordered=e.get("ordered", False)
        )

    def list_append(self, e: dict[str, Any]) -> None:
        state = self._lists.get(e["id"])
        if state:
            state.items.append((e.get("item_id", ""), e.get("value", "")))

    def list_end(self, e: dict[str, Any]) -> None:
        state = self._lists.pop(e["id"], None)
        if not state:
            return

        main = self.query_one("#main", ScrollableContainer)

        if e["id"] == "help":
            self._ingest_help_items(state.items)

            current_page = self._page_by_key(self._current_key)
            if current_page is not None:
                # CTA buttons for child pages
                requires_input = {
                    v.get("command", ""): _action_needs_input(v)
                    for _, v in state.items
                    if isinstance(v, dict)
                }
                cta_entries = [
                    (p.base_args[-1].replace("-", " ").title() if p.base_args else p.key, p)
                    for p in self._pages.values()
                    if p.parent_key == current_page.key
                ]
                if cta_entries:
                    row = Horizontal(id="cta-row")
                    first = next(iter(main.children), None)
                    main.mount(row, before=first) if first else main.mount(row)
                    for label, page in cta_entries:
                        variant = (
                            "default" if requires_input.get(" ".join(page.base_args)) else "primary"
                        )
                        row.mount(Button(label, id=self._kid("cta-", page.key), variant=variant))

                # Scope help items to this page's sub-tree when on a sub-page
                render_items = state.items
                if len(current_page.base_args) > 1:
                    prefix = " ".join(current_page.base_args)
                    scoped = [
                        (i, v)
                        for i, v in state.items
                        if isinstance(v, dict) and str(v.get("command", "")).startswith(prefix)
                    ]
                    if scoped:
                        render_items = scoped

                form_built = self._mount_action_form(main, current_page, render_items)
                if form_built:
                    main.mount(
                        Button(
                            "Submit",
                            id=self._kid("form-submit-", current_page.key),
                            variant="success",
                        )
                    )
                else:
                    cmd_key = " ".join(current_page.base_args)
                    for _, v in render_items:
                        if (
                            isinstance(v, dict)
                            and v.get("command") == cmd_key
                            and v.get("kind") == "action"
                        ):
                            run_args = list(current_page.base_args)
                            self.run_worker(lambda a=run_args: self._run_scop(a), thread=True)
                            break

        main.mount(Static(f"[bold]{state.label}[/bold]"))
        for _, value in state.items:
            if isinstance(value, dict):
                cmd = value.get("command", "")
                desc = value.get("description", "")
                main.mount(Static(f"  • [bold]{cmd}[/bold]  [dim]{desc}[/dim]"))
            else:
                main.mount(Static(f"  • {value}"))

    # ── PROCESS ───────────────────────────────────────────────────────────────

    def process_begin(self, e: dict[str, Any]) -> None:
        label = e.get("label", e["id"])
        total = e.get("total")
        self._procs[e["id"]] = label
        main = self.query_one("#main", ScrollableContainer)
        main.mount(Static(f"[cyan]▶[/cyan] [bold]{label}[/bold]"))
        main.mount(
            ProgressBar(
                total=float(total) if total is not None else None,
                id=f"proc-{e['id']}",
                show_eta=False,
            )
        )

    def process_update(self, e: dict[str, Any]) -> None:
        for bar in self.query(f"#proc-{e['id']}").results(ProgressBar):
            raw_total = e.get("total")
            if raw_total is not None and bar.total is None:
                bar.total = float(raw_total)
            bar.progress = float(e.get("current", 0))
            break

    def process_log(self, e: dict[str, Any]) -> None:
        self._log(f"  [dim]│[/dim] {e.get('message') or e.get('msg', '')}")

    def process_end(self, e: dict[str, Any]) -> None:
        label = self._procs.pop(e["id"], e["id"])
        ok = e.get("ok", True)
        for bar in self.query(f"#proc-{e['id']}").results(ProgressBar):
            bar.remove()
            break
        if ok:
            self._log(f"  [green]✓[/green] {label}")
        else:
            pri: int = e.get("pri", 6)
            if pri <= 3:
                self.push_screen(_ErrorModal(e.get("msg", label)))
            else:
                self.notify(e.get("msg", label), severity="warning")


# ── Dispatch table ────────────────────────────────────────────────────────────

_DISPATCH: dict[str, str] = {
    "PAGE_BEGIN": "page_begin",
    "PAGE_END": "page_end",
    "SCALAR_SET": "scalar_set",
    "TABLE_DECLARE": "table_declare",
    "TABLE_ROW": "table_row",
    "TABLE_UPDATE": "table_update",
    "LIST_DECLARE": "list_declare",
    "LIST_APPEND": "list_append",
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
            "  scop-tui                       # standalone with nav\n"
            "  scop [command] | scop-tui      # pipe a single command\n"
            "  scop-tui --from events.ndjson  # replay recorded stream\n"
            '  scop-tui --cmd "scop snapshot" # run command directly\n\n'
            "Keys: q quit  ctrl+l toggle log\n"
        )
        sys.exit(0)

    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--from":
        with pathlib.Path(args[1]).open(encoding="utf-8") as f:
            _consume(f)
        return
    if len(args) >= 2 and args[0] == "--cmd":
        try:
            cmd_tokens = shlex.split(args[1], posix=False)
        except ValueError as exc:
            sys.stderr.write(f"Invalid --cmd: {exc}\n")
            sys.exit(2)
        if not cmd_tokens:
            sys.stderr.write("Invalid --cmd: empty command\n")
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
