from __future__ import annotations

from html import escape

from flask import Flask, render_template_string, request

from scop.html import _to_html
from scop.ui import PAGE_FLAGS, discover_pages, parse_ndjson, run_scop

_app = Flask(__name__)

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>scop</title>
  <link rel="stylesheet"
        href="https://fonts.googleapis.com/icon?family=Material+Icons">
  <link rel="stylesheet"
        href="https://unpkg.com/material-components-web@latest/dist/material-components-web.min.css">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; font-family: Roboto, sans-serif; }

    body {
      background: #121212;
      color: #e0e0e0;
      padding-top: 56px;
      padding-bottom: 72px;
    }

    /* ── Top app bar ───────────────────────────────────────── */

    .scop-app-bar {
      position: fixed;
      top: 0; left: 0; right: 0;
      height: 56px;
      background: #1e1e1e;
      border-bottom: 1px solid rgba(255,255,255,0.12);
      display: flex;
      align-items: center;
      padding: 0 16px;
      gap: 12px;
      z-index: 10;
    }

    .scop-app-bar-title {
      font-size: 20px;
      font-weight: 500;
      letter-spacing: 0.0125em;
      color: rgba(255,255,255,0.87);
    }

    .scop-back-btn {
      display: flex;
      align-items: center;
      background: none;
      border: none;
      color: #bb86fc;
      text-decoration: none;
      padding: 6px 8px;
      border-radius: 4px;
      transition: background 0.15s;
    }

    .scop-back-btn:hover { background: rgba(187,134,252,0.1); }
    .scop-back-btn .material-icons { font-size: 20px; }

    /* ── Bottom nav ────────────────────────────────────────── */

    .scop-bottom-nav {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      height: 56px;
      background: #1e1e1e;
      border-top: 1px solid rgba(255,255,255,0.12);
      display: flex;
      z-index: 10;
    }

    .scop-nav-tab {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-family: Roboto, sans-serif;
      letter-spacing: 0.03em;
      text-decoration: none;
      color: rgba(255,255,255,0.5);
      border-bottom: 2px solid transparent;
      transition: color 0.15s, background 0.15s;
    }

    .scop-nav-tab:hover { background: rgba(255,255,255,0.04); }

    .scop-nav-tab[aria-current="page"] {
      color: #bb86fc;
      border-bottom-color: #bb86fc;
    }

    /* ── Main content ──────────────────────────────────────── */

    main {
      padding: 20px 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    /* ── Table ─────────────────────────────────────────────── */

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      background: #1e1e2e;
      border-radius: 6px;
      overflow: hidden;
      box-shadow: 0 1px 4px rgba(0,0,0,0.5);
    }

    th {
      text-align: left;
      padding: 10px 16px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.05em;
      color: rgba(255,255,255,0.5);
      border-bottom: 1px solid rgba(255,255,255,0.1);
    }

    td {
      padding: 10px 16px;
      color: rgba(255,255,255,0.87);
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }

    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: rgba(255,255,255,0.04); }

    /* ── Scalars (dl/dt/dd) ────────────────────────────────── */

    dl {
      background: #1e1e2e;
      border-radius: 6px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.5);
    }

    dt {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 8px 16px 0;
      font-size: 14px;
      color: rgba(255,255,255,0.5);
    }

    dd {
      padding: 0 16px 8px;
      font-size: 14px;
      font-weight: 500;
      color: rgba(255,255,255,0.87);
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }

    dd:last-child { border-bottom: none; }

    /* ── CTA links ─────────────────────────────────────────── */

    p:has(> a) {
      background: #1e1e2e;
      border-radius: 6px;
      padding: 12px 16px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.5);
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    p > a {
      display: inline-flex;
      align-items: center;
      height: 36px;
      padding: 0 20px;
      border-radius: 4px;
      font-size: 14px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-decoration: none;
      transition: background 0.15s;
    }

    p > a:first-of-type {
      background: #bb86fc;
      color: #000;
    }

    p > a:first-of-type:hover { background: #c9a2fd; }

    p > a:not(:first-of-type) {
      background: transparent;
      border: 1px solid rgba(187,134,252,0.5);
      color: #bb86fc;
    }

    p > a:not(:first-of-type):hover { background: rgba(187,134,252,0.08); }

    /* ── Form ──────────────────────────────────────────────── */

    form {
      background: #1e1e2e;
      border-radius: 6px;
      padding: 16px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.5);
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    form > p {
      all: unset;
      display: contents;
    }

    form label {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      color: rgba(255,255,255,0.45);
      text-transform: uppercase;
    }

    input[type="text"] {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 4px;
      padding: 10px 12px;
      font-size: 14px;
      font-family: monospace;
      color: rgba(255,255,255,0.87);
      outline: none;
      width: 100%;
      transition: border-color 0.15s;
    }

    input[type="text"]:focus { border-color: #bb86fc; }

    fieldset {
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 4px;
      padding: 8px 12px;
    }

    legend {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      color: rgba(255,255,255,0.45);
      text-transform: uppercase;
      padding: 0 4px;
    }

    input[type="checkbox"] { accent-color: #bb86fc; }

    fieldset label {
      flex-direction: row;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 400;
      letter-spacing: normal;
      text-transform: none;
      color: rgba(255,255,255,0.7);
      margin-right: 12px;
    }

    button[type="submit"] {
      height: 36px;
      padding: 0 20px;
      border-radius: 4px;
      font-size: 14px;
      font-weight: 500;
      font-family: Roboto, sans-serif;
      letter-spacing: 0.04em;
      cursor: pointer;
      background: #bb86fc;
      border: none;
      color: #000;
      align-self: flex-start;
      transition: background 0.15s;
    }

    button[type="submit"]:hover { background: #c9a2fd; }
  </style>
</head>
<body class="mdc-typography">

  <header class="scop-app-bar">
    {% if back_url %}
    <a class="scop-back-btn" href="{{ back_url }}">
      <i class="material-icons">arrow_back</i>
    </a>
    {% endif %}
    <span class="scop-app-bar-title">scop</span>
  </header>

  <main>
    {{ content | safe }}
  </main>

  <nav class="scop-bottom-nav">
    {% for page in pages %}
    <a class="scop-nav-tab" href="/?tab={{ page.key }}"
       {% if page.key == tab %}aria-current="page"{% endif %}>
      {{ page.label }}
    </a>
    {% endfor %}
  </nav>

  <script src="https://unpkg.com/material-components-web@latest/dist/material-components-web.min.js"></script>
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
    _app.run(host="127.0.0.1", port=5002)
