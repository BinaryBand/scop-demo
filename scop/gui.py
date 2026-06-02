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
      gap: 12px;
      margin-top: 12px;
    }

    /* ── Table ─────────────────────────────────────────────── */

    .scop-table-wrap {
      background: #1e1e2e;
      border-radius: 6px;
      overflow: hidden;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
    }

    .scop-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }

    .scop-table th {
      text-align: left;
      padding: 10px 16px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.05em;
      color: rgba(255, 255, 255, 0.5);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }

    .scop-table td {
      padding: 10px 16px;
      color: rgba(255, 255, 255, 0.87);
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .scop-table tbody tr:last-child td { border-bottom: none; }

    .scop-table tbody tr:hover td {
      background: rgba(255, 255, 255, 0.04);
    }

    /* ── List ──────────────────────────────────────────────── */

    .scop-list {
      background: #1e1e2e;
      border-radius: 6px;
      overflow: hidden;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
    }

    .scop-list-item {
      padding: 10px 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .scop-list-item:last-child { border-bottom: none; }

    .scop-list-primary {
      font-size: 13px;
      font-family: monospace;
      color: rgba(255, 255, 255, 0.87);
    }

    .scop-list-secondary {
      font-size: 12px;
      color: rgba(255, 255, 255, 0.45);
      margin-top: 2px;
    }

    /* ── Scalars ───────────────────────────────────────────── */

    .scop-scalars {
      background: #1e1e2e;
      border-radius: 6px;
      padding: 4px 0;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
    }

    .scop-scalar-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
      padding: 8px 16px;
      font-size: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .scop-scalars .scop-scalar-row:last-child { border-bottom: none; }

    .scop-scalar-label { color: rgba(255, 255, 255, 0.5); }
    .scop-scalar-value { color: rgba(255, 255, 255, 0.87); font-weight: 500; }

    /* ── CTA banner ────────────────────────────────────────── */

    .scop-cta-banner {
      background: #1e1e2e;
      border-radius: 6px;
      padding: 12px 16px;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .scop-cta-btn {
      height: 36px;
      padding: 0 20px;
      border-radius: 4px;
      font-size: 14px;
      font-weight: 500;
      font-family: Roboto, sans-serif;
      letter-spacing: 0.04em;
      cursor: pointer;
      position: relative;
      overflow: hidden;
      transition: background 0.15s;
    }

    .scop-cta-primary {
      background: #bb86fc;
      border: none;
      color: #000;
    }

    .scop-cta-primary:hover { background: #c9a2fd; }

    .scop-cta-secondary {
      background: transparent;
      border: 1px solid rgba(187, 134, 252, 0.5);
      color: #bb86fc;
    }

    .scop-cta-secondary:hover { background: rgba(187, 134, 252, 0.08); }

    /* ── Form ──────────────────────────────────────────────── */

    .scop-form {
      background: #1e1e2e;
      border-radius: 6px;
      padding: 16px;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .scop-field { display: flex; flex-direction: column; gap: 6px; }

    .scop-field-label {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      color: rgba(255, 255, 255, 0.45);
      text-transform: uppercase;
    }

    .scop-field-input {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 4px;
      padding: 10px 12px;
      font-size: 14px;
      font-family: monospace;
      color: rgba(255, 255, 255, 0.87);
      outline: none;
      width: 100%;
      transition: border-color 0.15s;
    }

    .scop-field-input:focus { border-color: #bb86fc; }

    .scop-checkboxes { display: flex; flex-wrap: wrap; gap: 6px; }

    .scop-chip {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 16px;
      font-size: 12px;
      cursor: pointer;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: rgba(255, 255, 255, 0.7);
      user-select: none;
      transition: background 0.12s, border-color 0.12s;
    }

    .scop-chip input[type="checkbox"] { display: none; }

    .scop-chip.checked {
      background: rgba(187, 134, 252, 0.15);
      border-color: rgba(187, 134, 252, 0.5);
      color: #bb86fc;
    }

    /* ── Fallback card ─────────────────────────────────────── */

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

    // ── Component builders ────────────────────────────────────

    function mkCTAs(items) {
      // Subcommands: command with 2+ non-flag tokens (e.g. "snapshot create").
      // Flag-only variants like "snapshot --list" are excluded.
      const subs = items.filter(item => {
        if (!item || typeof item !== 'object' || !item.command) return false;
        return item.command.trim().split(/\\s+/).filter(t => !t.startsWith('-')).length >= 2;
      });
      if (!subs.length) return null;
      const banner = document.createElement('div');
      banner.className = 'scop-cta-banner';
      subs.forEach((item, idx) => {
        const btn = document.createElement('button');
        btn.className = 'scop-cta-btn mdc-ripple-surface ' +
                        (idx === 0 ? 'scop-cta-primary' : 'scop-cta-secondary');
        const tokens = item.command.trim().split(/\\s+/).filter(t => !t.startsWith('-'));
        const word = tokens[tokens.length - 1].replace(/-/g, ' ');
        btn.textContent = word.charAt(0).toUpperCase() + word.slice(1);
        banner.appendChild(btn);
      });
      return banner;
    }

    function mkForm(item) {
      const params = (item.params ?? []).filter(p =>
        p && typeof p === 'object' && p.kind === 'flag' && p.metavar
      );
      if (!params.length) return null;

      const wrap = document.createElement('div');
      wrap.className = 'scop-form';

      params.forEach(p => {
        const field = document.createElement('div');
        field.className = 'scop-field';

        const lbl = document.createElement('label');
        lbl.className = 'scop-field-label';
        lbl.textContent = p.name.replace(/^--/, '').replace(/-/g, ' ');
        field.appendChild(lbl);

        if (p.input_type === 'multi' && Array.isArray(p.options)) {
          const selected = new Set((p.default ?? '').split(',').map(s => s.trim()).filter(Boolean));
          const chips = document.createElement('div');
          chips.className = 'scop-checkboxes';
          p.options.forEach(opt => {
            const chip = document.createElement('label');
            chip.className = 'scop-chip' + (selected.has(opt) ? ' checked' : '');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = selected.has(opt);
            cb.addEventListener('change', () => chip.classList.toggle('checked', cb.checked));
            chip.appendChild(cb);
            chip.appendChild(document.createTextNode(opt));
            chips.appendChild(chip);
          });
          field.appendChild(chips);
        } else {
          const input = document.createElement('input');
          input.type = 'text';
          input.className = 'scop-field-input';
          input.value = p.default ?? '';
          input.placeholder = p.metavar ?? '';
          field.appendChild(input);
        }

        wrap.appendChild(field);
      });

      const btn = document.createElement('button');
      btn.className = 'scop-cta-btn scop-cta-primary mdc-ripple-surface';
      btn.style.alignSelf = 'flex-start';
      btn.textContent = 'Save';
      wrap.appendChild(btn);

      return wrap;
    }

    // ── ────────────────────────────────────────────────────── */

    function mkTable(label, schema, rows) {
      const wrap = document.createElement('div');
      wrap.className = 'scop-table-wrap';
      const table = document.createElement('table');
      table.className = 'scop-table';
      const thead = document.createElement('thead');
      const hr = document.createElement('tr');
      schema.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col.toUpperCase();
        hr.appendChild(th);
      });
      thead.appendChild(hr);
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      rows.forEach(vals => {
        const tr = document.createElement('tr');
        schema.forEach(col => {
          const td = document.createElement('td');
          td.textContent = vals[col] ?? '';
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      return wrap;
    }

    function mkList(items) {
      const wrap = document.createElement('div');
      wrap.className = 'scop-list';
      items.forEach(item => {
        const li = document.createElement('div');
        li.className = 'scop-list-item';
        const primary = document.createElement('div');
        primary.className = 'scop-list-primary';
        const secondary = document.createElement('div');
        secondary.className = 'scop-list-secondary';
        if (item && typeof item === 'object') {
          primary.textContent = item.command ?? item.label ?? JSON.stringify(item);
          secondary.textContent = item.description ?? '';
        } else {
          primary.textContent = String(item);
        }
        li.appendChild(primary);
        if (secondary.textContent) li.appendChild(secondary);
        wrap.appendChild(li);
      });
      return wrap;
    }

    function mkScalars(evts) {
      const wrap = document.createElement('div');
      wrap.className = 'scop-scalars';
      evts.forEach(ev => {
        const row = document.createElement('div');
        row.className = 'scop-scalar-row';
        const lbl = document.createElement('span');
        lbl.className = 'scop-scalar-label';
        lbl.textContent = ev.label ?? ev.id ?? '';
        const val = document.createElement('span');
        val.className = 'scop-scalar-value';
        val.textContent = ev.unit ? `${ev.value} ${ev.unit}` : String(ev.value ?? '');
        row.appendChild(lbl);
        row.appendChild(val);
        wrap.appendChild(row);
      });
      return wrap;
    }

    function mkCard(ev) {
      const card = document.createElement('div');
      card.className = 'event-card';
      if (ev.msgid) {
        const lbl = document.createElement('span');
        lbl.className = 'event-msgid';
        lbl.textContent = ev.msgid;
        card.appendChild(lbl);
      }
      const pre = document.createElement('pre');
      pre.className = 'event-json';
      pre.textContent = JSON.stringify(ev, null, 2);
      card.appendChild(pre);
      return card;
    }

    // ── State-machine renderer ────────────────────────────────

    const SKIP = new Set(['PAGE_BEGIN','PAGE_END','TABLE_END','LIST_END','TABLE_UPDATE']);

    function renderEvents(ndjson) {
      const evts = [];
      for (const line of ndjson.split('\\n')) {
        if (!line.trim()) continue;
        try { evts.push(JSON.parse(line)); } catch (_) {}
      }

      const nodes = [];
      const ctaItems  = [];   // 2+ non-flag tokens → CTA buttons at top
      const formItems = [];   // 1 non-flag token + value params → form at bottom
      let scalars = [];
      let i = 0;

      const flushScalars = () => {
        if (scalars.length) { nodes.push(mkScalars(scalars)); scalars = []; }
      };

      while (i < evts.length) {
        const ev = evts[i];
        const m = ev.msgid;

        if (m === 'TABLE_DECLARE') {
          flushScalars();
          const schema = ev.schema ?? [];
          const rows = [];
          i++;
          while (i < evts.length && evts[i].msgid === 'TABLE_ROW' && evts[i].id === ev.id) {
            rows.push(evts[i].values ?? {});
            i++;
          }
          nodes.push(mkTable(ev.label ?? ev.id, schema, rows));

        } else if (m === 'LIST_DECLARE') {
          flushScalars();
          const items = [];
          i++;
          while (i < evts.length && evts[i].msgid === 'LIST_APPEND' && evts[i].id === ev.id) {
            items.push(evts[i].value);
            i++;
          }
          // Route each action item by command depth:
          //   2+ non-flag tokens  → CTA button
          //   1 non-flag token + value params → form
          //   otherwise           → plain list
          const plain = [];
          items.forEach(x => {
            if (!x || typeof x !== 'object' || !x.command) { plain.push(x); return; }
            const tokens = x.command.trim().split(/\\s+/).filter(t => !t.startsWith('-'));
            if (tokens.length >= 2) {
              ctaItems.push(x);
            } else if ((x.params ?? []).some(p => p && p.kind === 'flag' && p.metavar)) {
              formItems.push(x);
            } else {
              plain.push(x);
            }
          });
          if (plain.length) nodes.push(mkList(plain));

        } else if (m === 'SCALAR_SET') {
          scalars.push(ev);
          i++;

        } else if (SKIP.has(m)) {
          i++;

        } else {
          flushScalars();
          nodes.push(mkCard(ev));
          i++;
        }
      }

      flushScalars();

      const banner = mkCTAs(ctaItems);
      const forms  = formItems.map(mkForm).filter(Boolean);
      return [...(banner ? [banner] : []), ...nodes, ...forms];
    }

    // ── Tab loading ───────────────────────────────────────────

    const loaded = new Set();

    async function loadTab(key) {
      if (loaded.has(key)) return;
      loaded.add(key);
      const container = document.querySelector(`#page-${key} .events-container`);
      try {
        const res = await fetch(`/api/page/${key}`);
        const nodes = renderEvents(await res.text());
        container.textContent = '';
        const frag = document.createDocumentFragment();
        nodes.forEach(n => frag.appendChild(n));
        container.appendChild(frag);
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
