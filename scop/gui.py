from __future__ import annotations

import functools
import io
import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from flask import Flask, render_template_string

_app = Flask(__name__)

_ICONS: dict[str, str] = {
    "snapshot": "photo_camera",
    "config": "settings",
}

# Commands run per root page (mirrors tui.py composite query_flags for depth-0 pages).
_PAGE_FLAGS: list[list[str]] = [["--list", "--all"], ["--status"], ["--help"]]


@dataclass
class _NavPage:
    key: str
    label: str
    icon: str


@functools.lru_cache(maxsize=1)
def _nav_pages() -> list[_NavPage]:
    """Discover root-level pages by parsing `scop --help` NDJSON output."""
    exe = shutil.which("scop") or "scop"
    try:
        result = subprocess.run(
            [exe, "--help"], capture_output=True, text=True, encoding="utf-8", check=False
        )
    except OSError:
        return []

    seen: set[str] = set()
    pages: list[_NavPage] = []

    for raw in io.StringIO(result.stdout):
        line = raw.strip()
        if not line:
            continue
        try:
            ev: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("msgid") != "LIST_APPEND" or ev.get("id") != "help":
            continue
        value = ev.get("value")
        if not isinstance(value, dict):
            continue
        command = value.get("command", "")
        if not isinstance(command, str):
            continue
        try:
            tokens = [t for t in shlex.split(command, posix=False) if not t.startswith("-")]
        except ValueError:
            continue
        if len(tokens) != 1 or tokens[0] in seen:
            continue
        key = tokens[0]
        seen.add(key)
        pages.append(
            _NavPage(
                key=key,
                label=key.replace("-", " ").title(),
                icon=_ICONS.get(key, "circle"),
            )
        )

    return pages


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
      display: flex;
      flex-direction: column;
      background: #121212;
      color: #e0e0e0;
    }

    main {
      flex: 1;
      overflow-y: auto;
      padding: 20px 16px 72px;
    }

    .tab-page { display: none; }
    .tab-page.active { display: block; }

    .events-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 12px;
    }

    .event-card {
      background: #1e1e2e;
      border-radius: 6px;
      padding: 12px 16px;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
    }

    .event-msgid {
      display: block;
      font-family: monospace;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      color: #bb86fc;
      margin-bottom: 8px;
    }

    .event-json {
      font-family: monospace;
      font-size: 12px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-all;
      color: rgba(255, 255, 255, 0.65);
      margin: 0;
    }

    .bottom-nav {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      height: 56px;
      background: #1e1e1e;
      display: flex;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
      z-index: 10;
    }

    .nav-tab {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 3px;
      border: none;
      background: none;
      color: rgba(255, 255, 255, 0.5);
      font-size: 11px;
      letter-spacing: 0.03em;
      cursor: pointer;
      transition: color 0.15s;
      position: relative;
      overflow: hidden;
    }

    .nav-tab.active { color: #bb86fc; }
    .nav-tab .material-icons { font-size: 22px; }
  </style>
</head>
<body>

  <main>
    {% for page in pages %}
    <div id="page-{{ page.key }}" class="tab-page{% if loop.first %} active{% endif %}">
      <h2>{{ page.label }}</h2>
      <div class="events-container"><span style="opacity:.4">Loading…</span></div>
    </div>
    {% endfor %}
  </main>

  <nav class="bottom-nav">
    {% for page in pages %}
    <button class="nav-tab{% if loop.first %} active{% endif %} mdc-ripple-surface"
            data-page="{{ page.key }}">
      <i class="material-icons">{{ page.icon }}</i>
      <span>{{ page.label }}</span>
    </button>
    {% endfor %}
  </nav>

  <script src="https://unpkg.com/material-components-web@latest/dist/material-components-web.min.js"></script>
  <script>
    document.querySelectorAll('.mdc-ripple-surface').forEach(el => {
      mdc.ripple.MDCRipple.attachTo(el);
    });

    const loaded = new Set();

    async function loadTab(key) {
      if (loaded.has(key)) return;
      loaded.add(key);
      const container = document.querySelector(`#page-${key} .events-container`);
      try {
        const res = await fetch(`/api/page/${key}`);
        const text = await res.text();
        const fragment = document.createDocumentFragment();
        for (const line of text.split('\\n')) {
          if (!line.trim()) continue;
          let obj;
          try { obj = JSON.parse(line); } catch (_) { continue; }
          const card = document.createElement('div');
          card.className = 'event-card';
          if (obj.msgid) {
            const label = document.createElement('span');
            label.className = 'event-msgid';
            label.textContent = obj.msgid;
            card.appendChild(label);
          }
          const pre = document.createElement('pre');
          pre.className = 'event-json';
          pre.textContent = JSON.stringify(obj, null, 2);
          card.appendChild(pre);
          fragment.appendChild(card);
        }
        container.textContent = '';
        container.appendChild(fragment);
      } catch (e) {
        container.textContent = `Error: ${e}`;
      }
    }

    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`page-${tab.dataset.page}`).classList.add('active');
        loadTab(tab.dataset.page);
      });
    });

    // Load the first tab on startup.
    const firstTab = document.querySelector('.nav-tab');
    if (firstTab) loadTab(firstTab.dataset.page);
  </script>
</body>
</html>
"""


@_app.route("/")
def index() -> str:
    return render_template_string(_TEMPLATE, pages=_nav_pages())


@_app.route("/api/page/<key>")
def page_data(key: str) -> str:
    exe = shutil.which("scop") or "scop"
    output: list[str] = []
    for flags in _PAGE_FLAGS:
        try:
            r = subprocess.run(
                [exe, key, *flags], capture_output=True, text=True, encoding="utf-8", check=False
            )
        except OSError:
            r = None
        if r is not None:
            output.append(r.stdout)
    return "".join(output)


def main() -> None:
    _app.run(host="127.0.0.1", port=5000)
