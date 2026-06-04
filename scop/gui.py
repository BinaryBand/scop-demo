"""Raw HTML view of the UIModel.

No styling, no routing decisions.  Every page slot — scalars, tables,
lists — is rendered as plain unstyled HTML so you can see exactly what
the model contains.  Each list item gets a form so you can trigger it
directly from the browser.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.wrappers import Response as WResponse

from scop.cli import dispatch_events
from scop.ui import UIModel, UIPage

_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _ROOT / "static" / "templates"
_STATIC_DIR = _ROOT / "static"
_app = Flask(__name__, template_folder=str(_TEMPLATE_DIR), static_folder=str(_STATIC_DIR))

# Minimal MUI resources so the GUI can opt-in to Material styles.
MATERIAL_HEAD = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/icon?family=Material+Icons">'
    "\n"
    '<link rel="stylesheet" href="https://unpkg.com/material-components-web@latest/dist/material-components-web.min.css">'
)


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


_PROBES: list[dict[str, object]] = [
    {"action": "status"},
    {"action": "list", "all": True},
    {"list": True},
    {"help": True},
]


def _fetch(key: str) -> UIPage | None:
    m = UIModel()
    for args in _PROBES:
        events, _ = dispatch_events(key, dict(args))
        m.ingest_many(events)
    return m.current_page()


def _fetch_sub(key: str, sub: str) -> UIPage | None:
    events, _ = dispatch_events(key, {"action": sub, "help": True})
    m = UIModel()
    m.ingest_many(events)
    return m.current_page()


def _render(page: UIPage, pages: list[str], current: str, sub: str = "") -> str:
    # Prepare context for template rendering to keep presentation logic out of templates
    is_subpage = bool(sub)

    scalars = []
    for sid, ev in page.scalars.items():
        scalars.append({
            "label": str(ev.get("label") or sid),
            "value": str(ev.get("value", "")),
            "unit": str(ev.get("unit") or ""),
        })

    tables = []
    for entry in page.tables.values():
        decl = entry.get("declare", {})
        rows = entry.get("rows", [])
        schema = [str(c) for c in (decl.get("schema") or [])]
        if not schema:
            continue
        tables.append({"schema": schema, "rows": rows})

    lists = []
    for lid, entry in page.lists.items():
        decl = entry.get("declare", {})
        label = str(decl.get("label") or lid)
        items = [x for x in entry.get("items", []) if isinstance(x, dict) and x.get("command")]
        if not items:
            continue
        processed = []
        for item in items:
            cmd = str(item["command"])
            desc = str(item.get("description", ""))
            params = [p for p in (item.get("params") or []) if isinstance(p, dict)]
            non_flag = [t for t in cmd.split() if not t.startswith("-")]
            last = non_flag[-1] if non_flag else cmd.split()[-1]
            label_str = last.replace("-", " ").title()
            is_sub_target = (not is_subpage) and len(non_flag) >= 2
            processed.append({
                "cmd": cmd,
                "desc": desc,
                "params": params,
                "non_flag": non_flag,
                "last": last,
                "label_str": label_str,
                "is_sub_target": is_sub_target,
                # templates will render form inputs from `params` safely
            })
        lists.append({"label": label, "entries": processed})

    return render_template(
        "base.html",
        pages=pages,
        current=current,
        sub=sub,
        page=page,
        scalars=scalars,
        tables=tables,
        lists=lists,
        is_subpage=is_subpage,
        extra_head=MATERIAL_HEAD,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@_app.route("/")
def index() -> str:
    root_events, _ = dispatch_events("", {"help": True})
    pages = _discover_pages(root_events)
    current = request.args.get("page") or (pages[0] if pages else "")
    sub = request.args.get("sub", "")

    if not current:
        return render_template(
            "base.html", title="No pages", message="No pages found.", extra_head=MATERIAL_HEAD
        )

    page = _fetch_sub(current, sub) if sub else _fetch(current)

    if page is None:
        label = f"{current}/{sub}" if sub else current
        return render_template(
            "base.html",
            title="No data",
            message=f"No data for {escape(label)}.",
            extra_head=MATERIAL_HEAD,
        )

    return _render(page, pages, current, sub)


@_app.route("/run", methods=["POST"])
def run() -> WResponse | str:
    cmd_parts = request.form.get("__cmd", "").split()
    page_key = request.form.get("__page", "")

    if not cmd_parts:
        return redirect(url_for("index", page=page_key))

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
    return redirect(url_for("index", page=page_key))


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    _app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
