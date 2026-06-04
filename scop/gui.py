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


def _redirect(url: str) -> str:
    safe = escape(url)
    return (
        f"<!DOCTYPE html><html><head>"
        f'<meta http-equiv="refresh" content="0;url={safe}">'
        f"</head><body></body></html>"
    )


def _nav(pages: list[str], current: str) -> str:
    parts = []
    for p in pages:
        if p == current:
            parts.append(f"<strong>[{escape(p)}]</strong>")
        else:
            parts.append(f'<a href="/?page={escape(p)}">{escape(p)}</a>')
    return " | ".join(parts)


def _render(page: UIPage, pages: list[str], current: str) -> str:
    out: list[str] = [
        "<!DOCTYPE html><html><body>",
        f"<p>{_nav(pages, current)}</p><hr>",
        f"<h2>{escape(page.title)}</h2>",
    ]

    # Scalars — raw key/value pairs
    for sid, ev in page.scalars.items():
        label = escape(str(ev.get("label") or sid))
        value = escape(str(ev.get("value", "")))
        unit = escape(str(ev.get("unit") or ""))
        out.append(f"<p>{label}: <b>{value}</b>{' ' + unit if unit else ''}</p>")

    # Tables — unstyled <table>
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

    # Lists — one form per command
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
            last = cmd.split()[-1]

            out.append(
                f'<li><form method="post" action="/run" style="display:inline">'
                f'<input type="hidden" name="__cmd" value="{escape(cmd)}">'
                f'<input type="hidden" name="__page" value="{escape(current)}">'
            )
            for p in params:
                name = str(p.get("name", ""))
                kind = str(p.get("kind", "flag"))
                metavar = escape(str(p.get("metavar") or name))
                default = escape(str(p.get("default") or ""))
                req = " required" if p.get("required", kind == "positional") else ""
                fname = f"pos:{escape(name)}" if kind == "positional" else escape(name)
                out.append(
                    f'<input name="{fname}" placeholder="{metavar}" value="{default}"{req}> '
                )
            out.append(
                f"<button>{escape(last.replace('-', ' ').title())}</button></form> — {desc}</li>"
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

    if not current:
        return "<!DOCTYPE html><html><body><p>No pages found.</p></body></html>"

    page = _fetch(current)
    if page is None:
        return f"<!DOCTYPE html><html><body><p>No data for {escape(current)}.</p></body></html>"

    return _render(page, pages, current)


@_app.route("/run", methods=["POST"])
def run() -> str:
    cmd_parts = request.form.get("__cmd", "").split()
    page_key = request.form.get("__page", "")

    if not cmd_parts:
        return _redirect(f"/?page={page_key}")

    command = cmd_parts[0]
    args: dict[str, Any] = {}

    # Second token is a subaction if it's not a flag
    if len(cmd_parts) > 1 and not cmd_parts[1].startswith("-"):
        args["action"] = cmd_parts[1]

    # Inline boolean flags embedded in the command string
    for part in cmd_parts[1:]:
        if part.startswith("--"):
            args[part.lstrip("-").replace("-", "_")] = True

    # Form inputs
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
