# Structured CLI Output Protocol (SCOP)

**Version:** 0.1.0-draft  
**Status:** Draft Specification  
**License:** CC0 1.0 Universal (Public Domain)

---

## Abstract

SCOP defines a machine-readable output format for CLI applications that is simultaneously human-readable as plain text and automatically translatable to graphical user interfaces. It composes three existing standards — POSIX.1 Utility Conventions, GNU Coding Standards, and RFC 5424 — adding a typed event vocabulary, a room-based page model, and a three-flag protocol that together enable any conforming CLI application to be rendered as a GUI without application-specific code.

---

## Status of This Document

Draft specification, published for review and comment. The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY", and "OPTIONAL" are interpreted as described in RFC 2119.

---

## 1. Introduction

CLI applications lack a formal output standard. Every CLI-to-GUI bridge must be written per-application, duplicating effort and coupling tightly to application internals. SCOP addresses this by defining structured output that is CLI-first (`msg` always readable as plain text), standard-grounded (builds on POSIX, GNU, RFC 5424), and auto-translatable (a conforming renderer needs no app-specific code).

SCOP defines a wire format, event vocabulary, room model, GNU flag contracts, and page template. It does not define GUI rendering details, transport beyond stdout, authentication, or application business logic.

SCOP is a composition, not a replacement:

| Layer | Standard | Role |
| --- | --- | --- |
| Input | POSIX.1 Ch.12 + GNU | flags, subcommands |
| Envelope | RFC 5424 | event fields, severity |
| Serialisation | NDJSON | wire format |
| Output | SCOP | vocabulary + page model |

---

## 2. Terminology

**Producer** — a SCOP-conforming CLI application that emits events.  
**Consumer** — software that reads a SCOP event stream and renders it.  
**Event** — a single NDJSON line emitted by a producer.  
**Stream** — the ordered sequence of events from one command invocation.  
**MSGID** — a string identifier classifying an event by its data type (§7).  
**Room** — a page context derived from the subcommand path (§6).  
**Page** — a GUI display unit corresponding to one room, assembled from one or more streams.  
**Slot** — a named region in a page layout; events are routed to slots by MSGID family.

---

## 3. Design Principles

| Principle | Rule |
| --- | --- |
| CLI first | `msg` MUST always be a complete, human-readable line |
| Standard-grounded | SCOP MUST NOT conflict with POSIX or GNU; it defers to them |
| Data-typed | MSGIDs name the data type, not the display form |
| Rooms derived | Room is always derived from the command path — never declared |
| Zero app knowledge | A consumer MUST build any page from the stream alone |
| Additive | Consumers MUST ignore unknown MSGIDs and fields |

---

## 4. Foundation Standards

### 4.1 POSIX.1 and GNU

Applications SHOULD conform to POSIX.1 Utility Syntax Guidelines (Chapter 12): single-hyphen short options (`-f`), `--` to end option processing, operands following options. Applications SHOULD implement GNU standard flags; each flag's event contract is defined in §8.

| Flag | Short | Meaning |
| --- | --- | --- |
| `--help` | `-h` | Emit available commands and flags; exit |
| `--version` | | Emit version information; exit |
| `--list` | `-l` | List items without taking other action |
| `--status` | | Emit current application state |
| `--all` | `-a` | Expand scope of list or status output |
| `--quiet` | `-q` | Suppress non-essential output |
| `--verbose` | `-v` | Include debug-level output |
| `--dry-run` | `-n` | Execute without side effects |
| `--recursive` | `-r` | Operate recursively |
| `--force` | `-f` | Override safety checks |
| `--output` | `-o` | Redirect output to file |

Inverse flags (`--no-quiet`, `--no-recursive`, etc.) SHOULD be supported where the positive flag is supported.

### 4.2 RFC 5424 Fields

Every SCOP event is a serialised RFC 5424 message.

**Required:**

| Field | Key | Description |
| --- | --- | --- |
| PRI | `pri` | Facility (16) + severity, encoded as integer |
| MSGID | `msgid` | SCOP event type (§7) |
| MSG | `msg` | Complete, human-readable line |

**Optional:** `ts` (ISO 8601 timestamp), `app` (application name), `pid` (process id).

**Severity → GUI rendering:**

| Severity | Value | Rendering |
| --- | --- | --- |
| EMERG–ERR | 0–3 | error modal |
| WARNING | 4 | warning banner |
| NOTICE–INFO | 5–6 | log line |
| DEBUG | 7 | suppressed by default |

---

## 5. Wire Format

Events are serialised as **NDJSON** — one complete JSON object per line, separated by `\n`. Each line MUST be independently parseable. Producers MUST write to stdout.

Every event MUST contain `pri`, `msgid`, `room`, and `msg`. The `msg` field MUST be a complete standalone readable line — it MUST NOT require other fields to be meaningful, and MUST NOT verbatim duplicate them.

```json
{"pri": 6, "msgid": "PROCESS_BEGIN", "room": "snapshot", "id": "snap", "label": "Snapshotting ./docs", "total": 142, "msg": "Snapshotting ./docs (142 files)"}
{"pri": 6, "msgid": "PROCESS_UPDATE", "room": "snapshot", "id": "snap", "current": 71, "total": 142, "msg": "71 of 142: README.md"}
{"pri": 6, "msgid": "PROCESS_END", "room": "snapshot", "id": "snap", "ok": true, "msg": "Snapshot complete"}
```

---

## 6. Room Model

A **room** is derived mechanically from the subcommand path — it is never declared explicitly.

**Derivation rule:** `room = subcommand tokens joined by "/"`, excluding all flag tokens. Root room = `null`.

| Invocation | Room |
| --- | --- |
| `ourapp` | `null` |
| `ourapp snapshot` | `"snapshot"` |
| `ourapp snapshot diff` | `"snapshot/diff"` |
| `ourapp snapshot --list` | `"snapshot"` |

Room strings MUST be stable across versions. Changing a room string is a breaking change.

---

## 7. Event Vocabulary

All MSGIDs are grouped into families by data type. Consumers route events to GUI slots by family (§10).

### 7.1 PAGE — Page Frame

Every stream MUST begin with `PAGE_BEGIN` and end with `PAGE_END`. `PAGE_END.msg` SHOULD be empty.

| MSGID | Required | Optional |
| --- | --- | --- |
| `PAGE_BEGIN` | `room`, `title` | `subtitle`, `icon` |
| `PAGE_END` | `room` | |

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": "📸", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

### 7.2 PROCESS — Running Operation

Lifecycle: `PROCESS_BEGIN` → `PROCESS_UPDATE` ×n → `PROCESS_END`. Omit `total` when unknown; consumers SHOULD render an indeterminate indicator. `dry_run: true` MUST be present on all events when `--dry-run` is active.

| MSGID | Required | Optional |
| --- | --- | --- |
| `PROCESS_BEGIN` | `id`, `label` | `total`, `dry_run`, `recursive` |
| `PROCESS_UPDATE` | `id`, `current` | `total`, `label` |
| `PROCESS_END` | `id`, `ok` | `dry_run` |
| `PROCESS_LOG` | `id`, `message` | |

```json
{"pri": 6, "msgid": "PROCESS_BEGIN", "room": "snapshot", "id": "snap", "label": "Hashing files", "total": 42, "msg": "Hashing files (42)"}
{"pri": 6, "msgid": "PROCESS_UPDATE", "room": "snapshot", "id": "snap", "current": 21, "total": 42, "msg": "21 of 42: intro.md"}
{"pri": 6, "msgid": "PROCESS_LOG", "room": "snapshot", "id": "snap", "message": "skipping binary", "msg": "skipping binary"}
{"pri": 6, "msgid": "PROCESS_END", "room": "snapshot", "id": "snap", "ok": true, "msg": "Hashing complete"}
```

### 7.3 SCALAR — Single Named Value

`type` MUST be one of: `number`, `string`, `boolean`, `duration`, `bytes`.

| MSGID | Required | Optional |
| --- | --- | --- |
| `SCALAR_SET` | `id`, `label`, `value`, `type` | `unit` |
| `SCALAR_CLEAR` | `id` | |

```json
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "tracked", "label": "Tracked files", "value": 1042, "type": "number", "unit": "files", "msg": "Tracked files: 1042 files"}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "last_snap", "label": "Last snapshot", "value": "2026-05-30T14:32:00Z", "type": "string", "msg": "Last snapshot: 2026-05-30T14:32:00Z"}
```

### 7.4 LIST — Sequence

`ordered: true` renders as numbered; `false` as bullets. `value` MAY be scalar or a JSON object.

| MSGID | Required | Optional |
| --- | --- | --- |
| `LIST_DECLARE` | `id`, `label`, `ordered` | |
| `LIST_APPEND` | `id`, `item_id`, `value` | |
| `LIST_UPDATE` | `id`, `item_id`, `value` | |
| `LIST_REMOVE` | `id`, `item_id` | |
| `LIST_END` | `id` | |

```json
{"pri": 6, "msgid": "LIST_DECLARE", "room": "snapshot", "id": "changes", "label": "Changed files", "ordered": false, "msg": "Changed files"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "changes", "item_id": "f1", "value": "docs/intro.md", "msg": "+ docs/intro.md"}
{"pri": 6, "msgid": "LIST_UPDATE", "room": "snapshot", "id": "changes", "item_id": "f1", "value": "docs/intro.md (modified)", "msg": "~ docs/intro.md (modified)"}
{"pri": 6, "msgid": "LIST_END", "room": "snapshot", "id": "changes", "msg": "1 changed file"}
```

### 7.5 TABLE — Relation

`schema` MUST be an ordered array of column names. `values` MUST be a JSON object keyed by column name. `display_hint` is OPTIONAL and advisory (`"table"`, `"chart"`, `"cards"`); consumers MAY ignore it.

| MSGID | Required | Optional |
| --- | --- | --- |
| `TABLE_DECLARE` | `id`, `label`, `schema` | `display_hint` |
| `TABLE_ROW` | `id`, `row_id`, `values` | |
| `TABLE_UPDATE` | `id`, `row_id`, `values` | |
| `TABLE_END` | `id` | |

```json
{"pri": 6, "msgid": "TABLE_DECLARE", "room": "snapshot", "id": "snaps", "label": "Snapshots", "schema": ["name", "files", "size", "date"], "msg": "Snapshots"}
{"pri": 6, "msgid": "TABLE_ROW", "room": "snapshot", "id": "snaps", "row_id": "s1", "values": {"name": "snap-001", "files": 42, "size": "1.2MB", "date": "2026-05-30"}, "msg": "snap-001  42 files  1.2MB  2026-05-30"}
{"pri": 6, "msgid": "TABLE_END", "room": "snapshot", "id": "snaps", "msg": "1 snapshot"}
```

---

## 8. GNU Flag Contract

### 8.1 Query Flags

Query flags produce data output and exit. Each response MUST be wrapped in `PAGE_BEGIN` / `PAGE_END`.

**`--help` / `-h`**

```text
PAGE_BEGIN (room: current, title: command name)
LIST_DECLARE (id: "help", ordered: false)
LIST_APPEND ×n (value: {command, description})
LIST_END
PAGE_END
```

**`--version`**

```text
PAGE_BEGIN (room: null, title: app name)
SCALAR_SET (id: "version", type: "string", value: semver)
PAGE_END
```

**`--status`**

```text
PAGE_BEGIN (room: current, title: context name)
SCALAR_SET ×n
PAGE_END
```

**`--list` / `-l`**

```text
PAGE_BEGIN (room: current, title: context name)
TABLE_DECLARE → TABLE_ROW ×n → TABLE_END   (items have named fields)
  OR
LIST_DECLARE → LIST_APPEND ×n → LIST_END   (items are scalar)
PAGE_END
```

### 8.2 Mode Flags

Mode flags adjust which events are emitted. They produce no events of their own. `--quiet` and `--verbose` are mutually exclusive; `--verbose` MUST take precedence.

| Flag | Effect |
| --- | --- |
| `--quiet` / `-q` | MUST suppress `PROCESS_LOG` and `pri ≥ 5` |
| `--verbose` / `-v` | MUST include `pri = 7` events |
| `--all` / `-a` | MUST expand scope of `LIST` and `TABLE` output |

### 8.3 Process Modifier Flags

Modifier flags annotate `PROCESS_*` events with additional fields. No new MSGIDs are emitted.

| Flag | Added field | Value |
| --- | --- | --- |
| `--dry-run` / `-n` | `dry_run` | `true` |
| `--recursive` / `-r` | `recursive` | `true` |
| `--force` / `-f` | `force` | `true` |

---

## 9. Page Template

Any room can be fully described by three flag calls. A consumer that makes all three has everything needed to render a complete page without app-specific code.

```text
ourapp [subcommand] --status   →  page chrome + stats
ourapp [subcommand] --list     →  content
ourapp [subcommand] --help     →  actions
```

**Slot map:**

| Slot | Flag | MSGID | GUI rendering |
| --- | --- | --- | --- |
| Page chrome | any | `PAGE_BEGIN` | title, subtitle, icon |
| Stats | `--status` | `SCALAR_SET` | stat cards |
| Content | `--list` | `TABLE` or `LIST` | grid, list |
| Actions | `--help` | `LIST` (id="help") | buttons, palette |
| Activity | any command | `PROCESS_*` | progress, spinner |

Each call is independent. A page MAY be built from a subset.

**Optional slots** (advisory, no new MSGIDs):

| Slot | Convention |
| --- | --- |
| Description | `SCALAR_SET` with `id="page.description"` |
| Chart | `TABLE_DECLARE` with `display_hint: "chart"` |
| Empty state | `SCALAR_SET` with `id="page.empty"` |
| Badge | `SCALAR_SET` with `type: "badge"` |

**Full page manifest example** (`ourapp snapshot`):

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": "📸", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "tracked", "label": "Tracked files", "value": 1042, "type": "number", "msg": "Tracked files: 1042"}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "last_snap", "label": "Last snapshot", "value": "2026-05-30T14:32:00Z", "type": "string", "msg": "Last snapshot: 2026-05-30T14:32:00Z"}
{"pri": 6, "msgid": "TABLE_DECLARE", "room": "snapshot", "id": "snaps", "label": "Snapshots", "schema": ["name", "files", "size", "date"], "msg": "Snapshots"}
{"pri": 6, "msgid": "TABLE_ROW", "room": "snapshot", "id": "snaps", "row_id": "s1", "values": {"name": "snap-001", "files": 42, "size": "1.2MB", "date": "2026-05-30"}, "msg": "snap-001  42 files  1.2MB  2026-05-30"}
{"pri": 6, "msgid": "TABLE_END", "room": "snapshot", "id": "snaps", "msg": "1 snapshot"}
{"pri": 6, "msgid": "LIST_DECLARE", "room": "snapshot", "id": "help", "label": "Commands", "ordered": false, "msg": "Commands"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "help", "item_id": "create", "value": {"command": "snapshot create", "description": "Take a new snapshot"}, "msg": "  create    Take a new snapshot"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "help", "item_id": "diff", "value": {"command": "snapshot diff", "description": "Compare two snapshots"}, "msg": "  diff      Compare two snapshots"}
{"pri": 6, "msgid": "LIST_END", "room": "snapshot", "id": "help", "msg": ""}
{"pri": 6, "msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

**CLI output** (msg fields only):

```text
=== Snapshots ===
Tracked files: 1042
Last snapshot: 2026-05-30T14:32:00Z
Snapshots
snap-001  42 files  1.2MB  2026-05-30
1 snapshot
Commands
  create    Take a new snapshot
  diff      Compare two snapshots
```

---

## 10. Auto-Translation Rules

A conforming consumer routes events using this table. No application knowledge is required.

| MSGID / condition | Slot | Notes |
| --- | --- | --- |
| `PAGE_BEGIN` | open page | set title, subtitle, icon |
| `SCALAR_SET` | stats area | stat card |
| `TABLE_*` | content area | table, grid, or chart |
| `LIST_*` where `id="help"` | actions area | buttons or command palette |
| `LIST_*` otherwise | content area | list |
| `PROCESS_*` | activity indicator | progress bar or spinner |
| `PAGE_END` | close page | finalise layout |
| `pri` 0–3 | error modal | blocking |
| `pri` 4 | warning banner | non-blocking |
| `pri` 5–6 | log area | append |
| `pri` 7 | suppressed | unless `--verbose` |

Unknown MSGIDs MUST be routed to the log area using `msg`. Unknown fields MUST be ignored.

---

## 11. Conformance

**Producer MUST:** emit NDJSON to stdout; include `pri`, `msgid`, `room`, `msg` in every event; ensure `msg` is a complete human-readable line; wrap every stream in `PAGE_BEGIN` / `PAGE_END`; derive `room` from the subcommand path (§6); use only MSGIDs defined in §7; implement `--help` and `--version` per §8.1.

**Producer SHOULD:** implement `--status`, `--list` (§8.1); implement `--quiet`, `--verbose` (§8.2); implement `--dry-run` (§8.3).

**Consumer MUST:** parse NDJSON line-by-line; route events per §10; render `msg` as fallback for unknown MSGIDs; ignore unknown MSGIDs and fields without error; map RFC 5424 severity per §4.2.

**Consumer SHOULD:** implement the three-flag protocol (§9); support optional slots (§9).

---

## 12. Security Considerations

**Injection.** String values are untrusted. Consumers MUST sanitise before rendering in HTML or injection-sensitive contexts.

**Denial of service.** Producers MAY emit unbounded events. Consumers SHOULD implement stream size limits.

**Sensitive data.** Producers MUST NOT include secrets, credentials, or PII in events.

**Dry run.** Consumers MUST NOT suppress `dry_run: true` annotations. Users MUST be able to distinguish dry-run output from real output.

---

## 13. References

### Normative

- **RFC 2119** — Key words for use in RFCs. Bradner, S. (1997).
- **RFC 5424** — The Syslog Protocol. Gerhards, R. (2009).
- **IEEE Std 1003.1-2024** — POSIX.1-2024, Issue 8.
- **GNU Coding Standards** — gnu.org/prep/standards
- **NDJSON** — ndjson.org

### Informative

- **LSP `$/progress`** — Language Server Protocol §3.16.1. Microsoft (2021).
- **Adaptive Cards** — adaptivecards.io
- **CloudEvents** — CNCF CloudEvents v1.0.2. cloudevents.io
- **TLDP Standard Options** — tldp.org/LDP/abs/html/standard-options.html
