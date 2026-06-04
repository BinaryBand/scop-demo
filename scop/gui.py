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

    # Populate `options` for parameters that declare `select_from` by
    # dispatching the referenced command and extracting candidate values
    # (prefer table first-column values, fall back to list-append values).
    for lst in lists:
        for ent in lst.get("entries", []):
            if not isinstance(ent, dict):
                continue
            params_list = ent.get("params") or []
            if not isinstance(params_list, list):
                continue
            for param in params_list:
                if not isinstance(param, dict):
                    continue
                if param.get("options"):
                    # already populated
                    continue
                select_from = param.get("select_from")
                if not select_from:
                    continue
                # Parse a simple command string like "snapshot --list --all"
                tokens = [t for t in str(select_from).split() if t]
                if not tokens:
                    continue
                cmd = tokens[0]
                args: dict[str, Any] = {}
                # If second token is a non-flag, treat as action
                if len(tokens) > 1 and not tokens[1].startswith("-"):
                    args["action"] = tokens[1]
                for part in tokens[1:]:
                    if part.startswith("--"):
                        args[part.lstrip("-").replace("-", "_")] = True
                try:
                    evs, _ok = dispatch_events(cmd, args)
                except Exception:
                    evs = []

                opts: list[str] = []
                # collect table schema by id so we can pick the canonical column
                table_schema: dict[str, list[str]] = {}
                for ev in evs:
                    if ev.get("msgid") == "TABLE_DECLARE":
                        tid = ev.get("id")
                        schema = ev.get("schema") or ev.get("declare", {}).get("schema")
                        if isinstance(schema, list) and isinstance(tid, str):
                            table_schema[tid] = [str(c) for c in schema]

                for ev in evs:
                    mid = ev.get("msgid")
                    if mid == "TABLE_ROW":
                        vals = ev.get("values")
                        if isinstance(vals, dict):
                            tid = ev.get("id")
                            first_col = None
                            if isinstance(tid, str) and tid in table_schema and table_schema[tid]:
                                first_col = table_schema[tid][0]
                            # prefer schema-ordered column, fall back to first value
                            if first_col and first_col in vals:
                                s = str(vals.get(first_col))
                            else:
                                # unstable dict order; take the first value available
                                s = next((str(v) for v in vals.values()), "")
                            if s and s not in opts:
                                opts.append(s)
                    elif mid == "LIST_APPEND":
                        val = ev.get("value")
                        if isinstance(val, dict):
                            if "name" in val:
                                s = str(val.get("name"))
                            elif "id" in val:
                                s = str(val.get("id"))
                            elif "command" in val:
                                cmdval = str(val.get("command") or "")
                                s = cmdval.split()[-1] if cmdval else cmdval
                            else:
                                s = str(val)
                            if s and s not in opts:
                                opts.append(s)
                if opts:
                    param["options"] = opts

    # Build a mapping of page -> icon (if any) by probing each page's PAGE_BEGIN
    # Accept both flattened events (top-level keys) and nested `data` dicts.
    page_icons: dict[str, str] = {}
    for p in pages:
        try:
            evs, _ok = dispatch_events(p, {"help": True})
        except Exception:
            evs = []
        icon_val = ""
        for ev in evs:
            if ev.get("msgid") == "PAGE_BEGIN":
                data = ev.get("data")
                if isinstance(data, dict) and data.get("icon"):
                    icon_val = str(data.get("icon"))
                elif ev.get("icon"):
                    icon_val = str(ev.get("icon"))
                if icon_val:
                    break
        page_icons[p] = icon_val

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
        page_icons=page_icons,
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
            "base.html",
            title="No pages",
            message="No pages found.",
            page_icons={},
            extra_head=MATERIAL_HEAD,
        )

    page = _fetch_sub(current, sub) if sub else _fetch(current)

    if page is None:
        label = f"{current}/{sub}" if sub else current
        return render_template(
            "base.html",
            title="No data",
            message=f"No data for {escape(label)}.",
            page_icons={},
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
    _app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
