from __future__ import annotations

from dataclasses import dataclass, field
from typing import IO, Any

from scop.ui import is_form_param

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
    nodes: list[ScalarItem | TableSection]
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

    The routing logic mirrors `_to_html` in html.py and `renderEvents` in gui.py:
    LIST_APPEND items with 2+ non-flag tokens → CTAs; items with value params →
    forms; SCALAR_SET accumulates into ScalarItems; TABLE_DECLARE + TABLE_ROWs →
    TableSection.  All three renderers (HTML, JS, terminal) share this contract.
    """
    ctas: list[ActionItem] = []
    forms: list[ActionItem] = []
    nodes: list[ScalarItem | TableSection] = []
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
            items: list[Any] = []
            i += 1
            while (
                i < len(events)
                and events[i].get("msgid") == "LIST_APPEND"
                and events[i].get("id") == ev_id
            ):
                items.append(events[i].get("value"))
                i += 1
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

    for form in view.forms:
        _render_form(form, out)
