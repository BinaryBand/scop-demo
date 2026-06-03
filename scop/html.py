from __future__ import annotations

from html import escape
from typing import Any, cast

from flask import Flask, render_template_string, request

from scop.ui import PAGE_FLAGS, discover_pages, is_form_param, parse_ndjson, run_scop

_app = Flask(__name__)


def _build_form(item: dict[str, Any], tab: str) -> str:
    cmd = item.get("command", "")
    params = [p for p in (item.get("params") or []) if is_form_param(p)]
    tokens = [t for t in cmd.split() if not t.startswith("-")]
    btn = escape(tokens[-1].replace("-", " ").title() if tokens else "Submit")
    positionals = ",".join(p["name"] for p in params if p.get("kind") == "positional")

    parts = [
        '<div class="mdc-card">',
        '<form class="scop-form" method="post" action="/run">',
        f'<input type="hidden" name="__cmd" value="{escape(cmd)}">',
        f'<input type="hidden" name="__tab" value="{escape(tab)}">',
        f'<input type="hidden" name="__pos" value="{escape(positionals)}">',
    ]

    for p in params:
        name: str = p.get("name", "")
        kind: str = p.get("kind", "flag")
        default = str(p.get("default", ""))
        metavar = str(p.get("metavar", ""))
        required = p.get("required", kind == "positional") is not False
        lbl = escape(name.lstrip("-").replace("-", " ").title())
        req_mark = " *" if required else ""
        req_attr = " required" if required else ""

        if p.get("input_type") == "multi" and isinstance(p.get("options"), list):
            selected = {s.strip() for s in default.split(",") if s.strip()}
            parts.append(f"<fieldset><legend>{lbl}{req_mark}</legend>")
            for opt in p["options"]:
                eo = escape(opt)
                checked = " checked" if opt in selected else ""
                parts.append(
                    f'<div class="mdc-form-field">'
                    f'<div class="mdc-checkbox">'
                    f'<input type="checkbox" class="mdc-checkbox__native-control"'
                    f' name="multi:{escape(name)}" value="{eo}"{checked}>'
                    f'<div class="mdc-checkbox__background">'
                    f'<svg class="mdc-checkbox__checkmark" viewBox="0 0 24 24">'
                    f'<path class="mdc-checkbox__checkmark-path" fill="none"'
                    f' d="M1.73,12.91 8.1,19.28 22.79,4.59"/>'
                    f'</svg><div class="mdc-checkbox__mixedmark"></div>'
                    f'</div><div class="mdc-checkbox__ripple"></div>'
                    f"</div><label>{eo}</label></div>"
                )
            parts.append("</fieldset>")
        else:
            field_name = f"pos:{escape(name)}" if kind == "positional" else escape(name)
            parts.append(
                f'<label class="mdc-text-field mdc-text-field--filled">'
                f'<span class="mdc-text-field__ripple"></span>'
                f'<span class="mdc-floating-label">{lbl}{req_mark}</span>'
                f'<input class="mdc-text-field__input" type="text"'
                f' name="{field_name}" value="{escape(default)}"'
                f' placeholder="{escape(metavar)}"{req_attr}>'
                f'<span class="mdc-line-ripple"></span>'
                f"</label>"
            )

    parts.extend([
        (
            f'<button type="submit" class="mdc-button mdc-button--raised">'
            f'<span class="mdc-button__ripple"></span>'
            f'<span class="mdc-button__label">{btn}</span></button>'
        ),
        "</form></div>",
    ])
    return "\n".join(parts)


def _to_html(events: list[dict[str, Any]], *, tab: str, is_subpage: bool = False) -> str:
    parts: list[str] = []
    cta_items: list[dict[str, Any]] = []
    form_items: list[dict[str, Any]] = []
    scalars: list[dict[str, Any]] = []
    i = 0

    def flush_scalars() -> None:
        if not scalars:
            return
        parts.append('<div class="mdc-card"><ul class="mdc-list">')
        for ev in scalars:
            lbl = escape(str(ev.get("label") or ev.get("id", "")))
            val = str(ev.get("value", ""))
            unit = str(ev.get("unit", ""))
            display = escape(val + (" " + unit if unit else ""))
            parts.append(
                f'<li class="mdc-list-item">'
                f'<span class="mdc-list-item__text">{lbl}</span>'
                f'<span class="mdc-list-item__meta">{display}</span>'
                f"</li>"
            )
        parts.append("</ul></div>")
        scalars.clear()

    while i < len(events):
        ev = events[i]
        m = ev.get("msgid", "")

        if m == "TABLE_DECLARE":
            flush_scalars()
            schema: list[str] = ev.get("schema", [])
            ev_id = ev.get("id")
            rows: list[dict[str, Any]] = []
            i += 1
            while (
                i < len(events)
                and events[i].get("msgid") == "TABLE_ROW"
                and events[i].get("id") == ev_id
            ):
                rows.append(events[i].get("values", {}))
                i += 1
            th_row = "".join(
                f'<th class="mdc-data-table__header-cell">{escape(c.upper())}</th>' for c in schema
            )
            tr_rows = [
                '<tr class="mdc-data-table__row">'
                + "".join(
                    f'<td class="mdc-data-table__cell">{escape(str(row.get(c, "")))}</td>'
                    for c in schema
                )
                + "</tr>"
                for row in rows
            ]
            parts.extend([
                '<div class="mdc-data-table"><div class="mdc-data-table__table-container">',
                (
                    '<table class="mdc-data-table__table"><thead>'
                    f'<tr class="mdc-data-table__header-row">{th_row}</tr></thead>'
                ),
                '<tbody class="mdc-data-table__content">',
                *tr_rows,
                "</tbody></table></div></div>",
            ])

        elif m == "LIST_DECLARE":
            flush_scalars()
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
                cmd_tokens = [t for t in item["command"].split() if not t.startswith("-")]
                has_form = any(is_form_param(p) for p in (item.get("params") or []))
                if is_subpage:
                    form_items.append(cast("dict[str, Any]", item))
                elif len(cmd_tokens) >= 2:
                    cta_items.append(cast("dict[str, Any]", item))
                elif has_form:
                    form_items.append(cast("dict[str, Any]", item))

        elif m == "SCALAR_SET":
            scalars.append(ev)
            i += 1

        elif m in {"PAGE_BEGIN", "PAGE_END", "TABLE_END", "LIST_END", "TABLE_UPDATE"}:
            i += 1

        else:
            flush_scalars()
            i += 1

    flush_scalars()

    if cta_items:
        link_parts: list[str] = []
        first = True
        for item in cta_items:
            cmd_tokens = [t for t in item["command"].split() if not t.startswith("-")]
            if len(cmd_tokens) < 2:
                continue
            lbl = escape(cmd_tokens[-1].replace("-", " ").title())
            href = f"/?tab={escape(tab)}&sub={escape(item['command'])}"
            cls = "mdc-button mdc-button--raised" if first else "mdc-button mdc-button--outlined"
            first = False
            link_parts.append(
                f'<a class="{cls}" href="{href}">'
                f'<span class="mdc-button__ripple"></span>'
                f'<span class="mdc-button__label">{lbl}</span></a>'
            )
        if link_parts:
            parts.insert(0, '<div class="mdc-card">' + "".join(link_parts) + "</div>")

    parts.extend(_build_form(item, tab) for item in form_items)

    return "\n".join(parts)


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>scop</title>
</head>
<body>
  <nav>
    {% for page in pages %}
    <a href="/?tab={{ page.key }}"{% if page.key == tab %} aria-current="page"{% endif %}>
      {{ page.label }}</a>
    {% endfor %}
  </nav>
  <hr>
  {% if back_url %}
  <p><a href="{{ back_url }}">← Back</a></p>
  {% endif %}
  <main>
    {{ content | safe }}
  </main>
</body>
</html>
"""


@_app.route("/")
def index() -> str:
    pages = discover_pages()
    tab = request.args.get("tab") or (pages[0].key if pages else "")
    sub = request.args.get("sub", "")

    if sub:
        content = _to_html(
            parse_ndjson(run_scop([*sub.split(), "--help"])), tab=tab, is_subpage=True
        )
        back_url = f"/?tab={escape(tab)}"
    else:
        ndjson = "".join(run_scop([tab, *flags]) for flags in PAGE_FLAGS)
        content = _to_html(parse_ndjson(ndjson), tab=tab)
        back_url = ""

    return render_template_string(
        _TEMPLATE, pages=pages, tab=tab, content=content, back_url=back_url
    )


@_app.route("/run", methods=["POST"])
def run() -> str:
    cmd = request.form.get("__cmd", "").split()
    tab = request.form.get("__tab", "")
    positionals = [p for p in request.form.get("__pos", "").split(",") if p]

    args: list[str] = list(cmd)
    for pos_name in positionals:
        val = request.form.get(f"pos:{pos_name}", "").strip()
        if val:
            args.append(val)

    seen: set[str] = set()
    for key in request.form:
        if key.startswith(("__", "pos:")) or key in seen:
            continue
        seen.add(key)
        if key.startswith("multi:"):
            flag = key[len("multi:") :]
            vals = [v for v in request.form.getlist(key) if v.strip()]
            if vals:
                args.extend([flag, ",".join(vals)])
        elif key.startswith("--"):
            val = request.form.get(key, "").strip()
            if val:
                args.extend([key, val])

    ndjson = run_scop(args)
    content = _to_html(parse_ndjson(ndjson), tab=tab) if ndjson.strip() else "<p>Done.</p>"
    pages = discover_pages()
    return render_template_string(
        _TEMPLATE, pages=pages, tab=tab, content=content, back_url=f"/?tab={escape(tab)}"
    )


def main() -> None:
    _app.run(host="127.0.0.1", port=5001)
