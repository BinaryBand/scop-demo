"""Raw HTML view of the UIModel.

No styling, no routing decisions.  Every page slot — scalars, tables,
lists — is rendered as plain unstyled HTML so you can see exactly what
the model contains.  Each list item gets a form so you can trigger it
directly from the browser.
"""

from __future__ import annotations

from html import escape
from typing import Any

from flask import Flask, request

from scop.cli import dispatch_events
from scop.ui import UIModel, UIPage

_app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _discover_pages(events: list[dict[str, Any]]) -> list[str]:
    """Pull top-level command names from raw help events."""
    pages: list[str] = []
    for ev in events:
        if ev.get("msgid") != "LIST_APPEND":
            continue
        value = ev.get("value")
        if not isinstance(value, dict):
            continue
        tokens = [t for t in str(value.get("command", "")).split() if not t.startswith("-")]
        if len(tokens) == 1 and tokens[0] not in pages:
            pages.append(tokens[0])
    return pages


def _fetch(key: str) -> UIPage | None:
    events, _ = dispatch_events(key, {"help": True})
    m = UIModel()
    m.ingest_many(events)
    return m.current_page()


def _fetch_sub(key: str, sub: str) -> UIPage | None:
    events, _ = dispatch_events(key, {"action": sub, "help": True})
    m = UIModel()
    m.ingest_many(events)
    return m.current_page()


def _redirect(url: str) -> str:
    safe = escape(url)
    return (
        f"<!DOCTYPE html><html><head>"
        f'<meta http-equiv="refresh" content="0;url={safe}">'
        f"</head><body></body></html>"
    )


def _nav(pages: list[str], current: str, sub: str = "") -> str:
    parts = []
    for p in pages:
        if p == current:
            link = f"<strong>[{escape(p)}]</strong>"
        else:
            link = f'<a href="/?page={escape(p)}">{escape(p)}</a>'
        parts.append(link)
    nav = " | ".join(parts)
    if sub:
        back = f'<a href="/?page={escape(current)}">{escape(current)}</a>'
        nav = nav.replace(f"<strong>[{escape(current)}]</strong>", back)
        nav += f" &gt; <strong>{escape(sub)}</strong>"
    return nav


def _form_inputs(cmd: str, current: str, params: list[dict[str, Any]]) -> str:
    """Render hidden cmd/page fields plus one <input> per param."""
    parts = [
        f'<input type="hidden" name="__cmd" value="{escape(cmd)}">',
        f'<input type="hidden" name="__page" value="{escape(current)}">',
    ]
    for p in params:
        name = str(p.get("name", ""))
        kind = str(p.get("kind", "flag"))
        metavar = escape(str(p.get("metavar") or name))
        default = escape(str(p.get("default") or ""))
        req = " required" if p.get("required", kind == "positional") else ""
        fname = f"pos:{escape(name)}" if kind == "positional" else escape(name)
        parts.append(f'<input name="{fname}" placeholder="{metavar}" value="{default}"{req}> ')
    return "".join(parts)


def _render(page: UIPage, pages: list[str], current: str, sub: str = "") -> str:
    is_subpage = bool(sub)
    out: list[str] = [
        "<!DOCTYPE html><html><body>",
        f"<p>{_nav(pages, current, sub)}</p><hr>",
        f"<h2>{escape(page.title)}</h2>",
    ]

    # Scalars
    for sid, ev in page.scalars.items():
        label = escape(str(ev.get("label") or sid))
        value = escape(str(ev.get("value", "")))
        unit = escape(str(ev.get("unit") or ""))
        out.append(f"<p>{label}: <b>{value}</b>{' ' + unit if unit else ''}</p>")

    # Tables
    for entry in page.tables.values():
        decl = entry.get("declare", {})
        rows = entry.get("rows", [])
        schema = [str(c) for c in (decl.get("schema") or [])]
        if not schema:
            continue
        out.append('<table border="1" cellpadding="4"><tr>')
        out.extend(f"<th>{escape(c)}</th>" for c in schema)
        out.append("</tr>")
        for row in rows:
            out.append("<tr>")
            out.extend(f"<td>{escape(str(row.get(c, '')))}</td>" for c in schema)
            out.append("</tr>")
        out.append("</table>")

    # Lists
    for lid, entry in page.lists.items():
        decl = entry.get("declare", {})
        label = escape(str(decl.get("label") or lid))
        items = [x for x in entry.get("items", []) if isinstance(x, dict) and x.get("command")]
        if not items:
            continue
        out.append(f"<p><b>{label}</b></p><ul>")
        for item in items:
            cmd = str(item["command"])
            desc = escape(str(item.get("description", "")))
            params = [p for p in (item.get("params") or []) if isinstance(p, dict)]
            non_flag = [t for t in cmd.split() if not t.startswith("-")]
            last = non_flag[-1] if non_flag else cmd.split()[-1]
            label_str = escape(last.replace("-", " ").title())

            if not is_subpage and len(non_flag) >= 2:
                # Subcommand → navigate into a subpage
                out.append(
                    f'<li><a href="/?page={escape(current)}&sub={escape(last)}">'
                    f"{label_str}</a> — {desc}</li>"
                )
            else:
                # Leaf command or subpage context → inline form
                out.append(
                    f'<li><form method="post" action="/run" style="display:inline">'
                    f"{_form_inputs(cmd, current, params)}"
                    f"<button>{label_str}</button></form> — {desc}</li>"
                )
        out.append("</ul>")

    out.append("</body></html>")
    return "\n".join(out)


# ── Routes ────────────────────────────────────────────────────────────────────


@_app.route("/")
def index() -> str:
    root_events, _ = dispatch_events("", {"help": True})
    pages = _discover_pages(root_events)
    current = request.args.get("page") or (pages[0] if pages else "")
    sub = request.args.get("sub", "")

    if not current:
        return "<!DOCTYPE html><html><body><p>No pages found.</p></body></html>"

    page = _fetch_sub(current, sub) if sub else _fetch(current)

    if page is None:
        label = f"{current}/{sub}" if sub else current
        return f"<!DOCTYPE html><html><body><p>No data for {escape(label)}.</p></body></html>"

    return _render(page, pages, current, sub)


@_app.route("/run", methods=["POST"])
def run() -> str:
    cmd_parts = request.form.get("__cmd", "").split()
    page_key = request.form.get("__page", "")

    if not cmd_parts:
        return _redirect(f"/?page={page_key}")

    command = cmd_parts[0]
    args: dict[str, Any] = {}

    if len(cmd_parts) > 1 and not cmd_parts[1].startswith("-"):
        args["action"] = cmd_parts[1]

    for part in cmd_parts[1:]:
        if part.startswith("--"):
            args[part.lstrip("-").replace("-", "_")] = True

    for key, val in request.form.items():
        if key.startswith("__") or not val.strip():
            continue
        if key.startswith("pos:"):
            args[key[4:]] = val.strip()
        elif key.startswith("--"):
            args[key.lstrip("-").replace("-", "_")] = val.strip()

    events, _ = dispatch_events(command, args)
    root_events, _ = dispatch_events("", {"help": True})
    pages = _discover_pages(root_events)

    result = UIModel()
    result.ingest_many(events)
    page = result.current_page()

    if page:
        return _render(page, pages, page_key)
    return _redirect(f"/?page={page_key}")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    _app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
