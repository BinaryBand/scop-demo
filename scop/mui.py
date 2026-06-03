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
    /* ── MDC dark theme variables ──────────────────────────── */
    :root {
      --mdc-theme-primary: #bb86fc;
      --mdc-theme-on-primary: #000;
      --mdc-theme-secondary: #03dac6;
      --mdc-theme-background: #121212;
      --mdc-theme-surface: #1e1e2e;
      --mdc-theme-on-surface: rgba(255, 255, 255, 0.87);
      --mdc-theme-error: #cf6679;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--mdc-theme-background);
      color: var(--mdc-theme-on-surface);
      font-family: Roboto, sans-serif;
      padding-top: 56px;
      padding-bottom: 56px;
    }

    /* ── Shell: top app bar ────────────────────────────────── */
    .scop-app-bar {
      position: fixed; top: 0; left: 0; right: 0; height: 56px;
      background: #1e1e1e; border-bottom: 1px solid rgba(255,255,255,0.12);
      display: flex; align-items: center; padding: 0 16px; gap: 12px; z-index: 10;
    }
    .scop-app-bar-title { font-size: 20px; font-weight: 500; color: rgba(255,255,255,0.87); }
    .scop-back-btn {
      display: flex; align-items: center; color: #bb86fc;
      text-decoration: none; padding: 6px 8px; border-radius: 4px;
    }
    .scop-back-btn:hover { background: rgba(187,134,252,0.1); }
    .scop-back-btn .material-icons { font-size: 20px; }

    /* ── Shell: bottom nav ─────────────────────────────────── */
    .scop-bottom-nav {
      position: fixed; bottom: 0; left: 0; right: 0; height: 56px;
      background: #1e1e1e; border-top: 1px solid rgba(255,255,255,0.12);
      display: flex; z-index: 10;
    }
    .scop-nav-tab {
      flex: 1; display: flex; align-items: center; justify-content: center;
      font-size: 13px; text-decoration: none; color: rgba(255,255,255,0.5);
      border-bottom: 2px solid transparent; transition: color 0.15s;
    }
    .scop-nav-tab:hover { background: rgba(255,255,255,0.04); }
    .scop-nav-tab[aria-current="page"] { color: #bb86fc; border-bottom-color: #bb86fc; }

    /* ── Content layout ────────────────────────────────────── */
    main { padding: 20px 16px; display: flex; flex-direction: column; gap: 12px; }
    .scop-form { display: flex; flex-direction: column; gap: 16px; padding: 16px; }
    .mdc-text-field { width: 100%; }
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
  <script>
    document.querySelectorAll('.mdc-text-field').forEach(el => {
      new mdc.textField.MDCTextField(el);
    });
    document.querySelectorAll('.mdc-data-table').forEach(el => {
      new mdc.dataTable.MDCDataTable(el);
    });
    document.querySelectorAll('.mdc-checkbox').forEach(el => {
      new mdc.checkbox.MDCCheckbox(el);
    });
  </script>
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
