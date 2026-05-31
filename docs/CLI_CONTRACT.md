# CLI Contract

**Implements:** SCOP §§6, 8, 9 — see `SCOP_Spec.md` for the full open specification.

Formalises the mapping from CLI input (GNU standard flags + subcommands) to MSGID output. Every input has exactly one defined output contract. This is the machine-enforceable I/O specification.

> **Meta-rule:** every rule in this document must be machine-enforceable.

---

## Room Derivation

A room is derived mechanically from the subcommand path. Flags never change the room — they modify what is emitted within it.

```text
ourapp                    → room: null       (root)
ourapp snapshot           → room: snapshot
ourapp snapshot diff      → room: snapshot/diff
ourapp snapshot --list    → room: snapshot   (--list is a flag, not a subcommand)
ourapp --help             → room: null       (--help is a flag on the root room)
```

**Rule:** `room = subcommand tokens joined by /`, ignoring all flag tokens.

| Token type | Room effect |
| --- | --- |
| Subcommand (bare word) | appended to room path |
| Flag (`--foo`, `-f`) | no effect on room |
| Flag argument (`--output FILE`) | no effect on room |

---

## GNU Standard Flags

Over time a loose standard has evolved for the meanings of GNU command-line option flags. The following table is the canonical subset relevant to this architecture, each mapped to its MSGID contract.

### Query flags — produce data output, then exit

| Flag | Short | MSGID contract | Room |
| --- | --- | --- | --- |
| `--help` | `-h` | `LIST_DECLARE` → `LIST_APPEND` ×n → `LIST_END` | current |
| `--version` | | `SCALAR_SET` | null |
| `--list` | `-l` | `TABLE_DECLARE` → `TABLE_ROW` ×n → `TABLE_END` **or** `LIST_DECLARE` → `LIST_APPEND` ×n → `LIST_END` (data-dependent) | current |

**`--help` contract:**
Each `LIST_APPEND` item describes one available command or flag:

```json
{"room": null, "msgid": "LIST_DECLARE", "id": "help", "label": "ourapp", "ordered": false, "msg": "ourapp"}
{"room": null, "msgid": "LIST_APPEND", "id": "help", "item_id": "snapshot", "value": {"command": "snapshot", "description": "Manage snapshots"}, "msg": "  snapshot    Manage snapshots"}
{"room": null, "msgid": "LIST_END", "id": "help", "msg": ""}
```

**`--version` contract:**

```json
{"room": null, "msgid": "SCALAR_SET", "id": "version", "label": "version", "value": "1.0.0", "type": "string", "msg": "ourapp 1.0.0"}
```

**`--list` contract:**
Emits a `TABLE` when items have named fields, a `LIST` when items are scalar. The distinction is data-driven — the renderer decides the widget.

---

### Mode flags — filter MSGID output, do not exit

Mode flags adjust which events are emitted. They never produce MSGIDs of their own — they act as a severity filter on the stream.

| Flag | Short | Inverse | Effect on stream |
| --- | --- | --- | --- |
| `--quiet` | `-q` | `--no-quiet` | suppress `PROCESS_LOG` and `severity ≥ NOTICE` |
| `--verbose` | `-v` | `--no-verbose` | include `DEBUG`-level `PROCESS_LOG` events |
| `--all` | `-a` | | expand scope of `LIST` / `TABLE` output (no new MSGIDs) |

`--quiet` and `--verbose` are mutually exclusive. `--verbose` wins if both are passed.

---

### Process modifier flags — annotate PROCESS events

Modifier flags do not change which MSGIDs are emitted — they add fields to `PROCESS_*` events so renderers and consumers can distinguish dry runs, recursive operations, and forced writes.

| Flag | Short | Inverse | Added field | Value |
| --- | --- | --- | --- | --- |
| `--dry-run` | `-n` | | `dry_run` | `true` |
| `--recursive` | `-r` / `-R` | `--no-recursive` | `recursive` | `true` |
| `--force` | `-f` | `--no-force` | `force` | `true` |

```json
{"msgid": "PROCESS_BEGIN", "id": "snap", "label": "Snapshotting", "dry_run": true, "msg": "Snapshotting (dry run)"}
{"msgid": "PROCESS_END", "id": "snap", "ok": true, "dry_run": true, "msg": "Snapshot complete (dry run — no files written)"}
```

---

### I/O flags — redirect output, no MSGID change

| Flag | Short | Effect |
| --- | --- | --- |
| `--output` | `-o` | redirect data output to file — stream continues unchanged |

---

## Full I/O Contract

Combined view — every CLI invocation maps to a predictable stream shape.

| Invocation | Room | Stream shape |
| --- | --- | --- |
| `ourapp` | null | `SCALAR_SET` ×n (stats) + `LIST` (commands) |
| `ourapp --help` | null | `LIST` (commands) |
| `ourapp --version` | null | `SCALAR_SET` (version) |
| `ourapp snapshot` | snapshot | `SCALAR_SET` ×n (snapshot stats) |
| `ourapp snapshot --help` | snapshot | `LIST` (snapshot commands + flags) |
| `ourapp snapshot --list` | snapshot | `TABLE` or `LIST` (snapshot records) |
| `ourapp snapshot create` | snapshot | `PROCESS_*` lifecycle |
| `ourapp snapshot diff` | snapshot | `TABLE` or `LIST` (diff records) |
| `ourapp snapshot --list --all` | snapshot | `TABLE` or `LIST` (all records, expanded) |
| `ourapp snapshot --list --quiet` | snapshot | `TABLE` or `LIST` (no `PROCESS_LOG`) |
| `ourapp snapshot create --dry-run` | snapshot | `PROCESS_*` with `dry_run: true` |
| `ourapp snapshot create --verbose` | snapshot | `PROCESS_*` with `DEBUG` log events |

---

## Room → GUI Page Mapping

A GUI derives its navigation automatically from the room field — no `NAV_*` MSGID is needed.

| Room | GUI page | Populated by |
| --- | --- | --- |
| `null` | Home screen | `SCALAR_SET` (stats) + `LIST` (commands) from `ourapp` |
| `snapshot` | Snapshot page | `SCALAR_SET` + `TABLE`/`LIST` from `ourapp snapshot` |
| `snapshot/diff` | Diff page | `TABLE`/`LIST` from `ourapp snapshot diff` |

`--help` at any level re-emits the room's `LIST` of available commands. A GUI renders this as a context menu, command palette, or drawer — whichever fits. The CLI just prints it.

---

## Page Template

Every room in a scop-based app can be fully described using three flags: `--status`, `--list`, and `--help`. A GUI renderer that calls all three has everything it needs to build any page automatically — no app-specific code required. This is the **mad-libs contract**: the template defines the slots, the app fills them, the renderer assembles the page.

---

### PAGE_BEGIN / PAGE_END

Every command response is wrapped in a `PAGE_BEGIN` / `PAGE_END` pair. This makes every NDJSON stream self-describing — the GUI always knows which room is active and what the page is called.

| MSGID | STRUCTURED-DATA fields | CLI rendering |
| --- | --- | --- |
| `PAGE_BEGIN` | `room`, `title`, `subtitle` (optional), `icon` (optional) | prints title as a section header |
| `PAGE_END` | `room` | prints nothing (structural marker only) |

```json
{"msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": "📸", "msg": "=== Snapshots ==="}
...
{"msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

`PAGE_BEGIN` is always the first event of any command response.
`PAGE_END` is always the last.

---

### The Three-Flag Protocol

A GUI calls these three in sequence to build any page:

| Flag | Emits | GUI slot |
| --- | --- | --- |
| `--status` | `PAGE_BEGIN` + `SCALAR_SET` ×n + `PAGE_END` | page chrome + stats area |
| `--list` | `PAGE_BEGIN` + `TABLE` or `LIST` + `PAGE_END` | main content area |
| `--help` | `PAGE_BEGIN` + `LIST` (commands + flags) + `PAGE_END` | actions area |

No flag combination is required — each is independently useful. A page with only `--status` is a valid dashboard. A page with only `--help` is a valid command palette.

---

### Page Slot Map

The complete mad-libs template. Every slot is optional except `PAGE_BEGIN`.

```text
PAGE_BEGIN          ← page title, subtitle, icon
│
├── SCALAR_SET ×n   ← [STATS]    stat cards, key metrics
│                               filled by: --status
│
├── TABLE or LIST   ← [CONTENT]  main data area
│                               filled by: --list
│
├── LIST            ← [ACTIONS]  buttons, command palette, nav
│                               filled by: --help
│
├── PROCESS_* ×n   ← [ACTIVITY] in-flight operations (if any)
│                               filled by: any active command
│
└── PAGE_END
```

**CLI rendering** of this structure is always readable:

- `PAGE_BEGIN.msg` → section header line
- `SCALAR_SET.msg` → `"label: value"` lines
- `TABLE` / `LIST` → tabular or bulleted text
- `LIST` (help) → indented command list
- `PROCESS_*` → `"x of n: label"` lines
- `PAGE_END.msg` → empty

**GUI rendering** routes each MSGID family to a layout slot automatically. No routing code is needed per-app — the MSGID family is the slot address.

---

### Optional Slots

Cookie-cutter snippets a developer may add to enrich the GUI without breaking the CLI.

| Slot | How to fill it | GUI widget | CLI rendering |
| --- | --- | --- | --- |
| Page description | `SCALAR_SET` with `id="page.description"` | hero text / caption | printed as a line |
| Diagram / chart | `TABLE` with `display_hint: "chart"` field | chart, graph, sparkline | printed as table |
| Breadcrumb | derived from `room` path automatically | breadcrumb bar | not printed |
| Badge / tag | `SCALAR_SET` with `type: "badge"` | coloured badge | printed inline |
| Empty state | `SCALAR_SET` with `id="page.empty"` | empty state illustration | printed as a line |

`display_hint` is advisory — renderers may ignore it. The data is always valid without it.

---

### Auto-Translation Rule

A GUI renderer that receives an NDJSON stream needs exactly one rule:

> **Route each event to its slot by MSGID family.**

| MSGID family | Slot |
| --- | --- |
| `PAGE_BEGIN` | open page, set title / subtitle / icon |
| `SCALAR_SET` | stats area |
| `TABLE_*` | main content area (table) |
| `LIST_*` | actions area if room is `--help`; content area otherwise |
| `PROCESS_*` | activity indicator |
| `PAGE_END` | close page |
| RFC 5424 pri 0–3 | error modal |
| RFC 5424 pri 4 | warning banner |

The renderer needs no knowledge of the app, its commands, or its data models. Any scop-based app that follows this contract is automatically GUI-translatable.

---

### Example — Full Page Manifest for `ourapp snapshot`

Three flag calls, assembled into one page:

```json
{"msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": "📸", "msg": "=== Snapshots ==="}

{"msgid": "SCALAR_SET", "room": "snapshot", "id": "last_snap", "label": "Last snapshot", "value": "2026-05-30T14:32:00Z", "type": "string", "msg": "Last snapshot: 2026-05-30T14:32:00Z"}
{"msgid": "SCALAR_SET", "room": "snapshot", "id": "tracked", "label": "Tracked files", "value": 1042, "type": "number", "msg": "Tracked files: 1042"}
{"msgid": "SCALAR_SET", "room": "snapshot", "id": "changed", "label": "Changed since last snap", "value": 3, "type": "number", "msg": "Changed since last snap: 3"}

{"msgid": "TABLE_DECLARE", "room": "snapshot", "id": "snaps", "label": "Snapshots", "schema": ["name", "files", "size", "date"], "msg": "Snapshots"}
{"msgid": "TABLE_ROW", "room": "snapshot", "id": "snaps", "row_id": "s1", "values": {"name": "snap-001", "files": 42, "size": "1.2MB", "date": "2026-05-30"}, "msg": "snap-001  42 files  1.2MB  2026-05-30"}
{"msgid": "TABLE_END", "room": "snapshot", "id": "snaps", "msg": "1 snapshot"}

{"msgid": "LIST_DECLARE", "room": "snapshot", "id": "actions", "label": "Commands", "ordered": false, "msg": "Commands"}
{"msgid": "LIST_APPEND", "room": "snapshot", "id": "actions", "item_id": "create", "value": {"command": "snapshot create", "description": "Take a new snapshot"}, "msg": "  create    Take a new snapshot"}
{"msgid": "LIST_APPEND", "room": "snapshot", "id": "actions", "item_id": "diff", "value": {"command": "snapshot diff", "description": "Compare two snapshots"}, "msg": "  diff      Compare two snapshots"}
{"msgid": "LIST_APPEND", "room": "snapshot", "id": "actions", "item_id": "restore", "value": {"command": "snapshot restore", "description": "Restore a snapshot"}, "msg": "  restore   Restore a snapshot"}
{"msgid": "LIST_END", "room": "snapshot", "id": "actions", "msg": ""}

{"msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

**CLI output** (just the `msg` fields):

```text
=== Snapshots ===
Last snapshot: 2026-05-30T14:32:00Z
Tracked files: 1042
Changed since last snap: 3
Snapshots
snap-001  42 files  1.2MB  2026-05-30
1 snapshot
Commands
  create    Take a new snapshot
  diff      Compare two snapshots
  restore   Restore a snapshot
```

**GUI output**: a page with a header, three stat cards, a data table, and three action buttons — assembled automatically from the stream.
