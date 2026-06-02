# Structured CLI Output Protocol (SCOP)

**Version:** 0.1.2-draft
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

SCOP defines a wire format, event vocabulary, room model, GNU flag contracts, and page template. It does not define GUI rendering details, transport beyond stdout, authentication, or application business logic. The companion specification **SCOP-M** defines a declarative manifest format (`scop.toml`) for statically describing a SCOP application's rooms, commands, and input types.

SCOP is a composition, not a replacement:

| Layer         | Standard            | Role                    |
| ------------- | ------------------- | ----------------------- |
| Input         | POSIX.1 Ch.12 + GNU | flags, subcommands      |
| Envelope      | RFC 5424            | event fields, severity  |
| Serialisation | NDJSON              | wire format             |
| Output        | SCOP                | vocabulary + page model |

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

| Principle          | Rule                                                          |
| ------------------ | ------------------------------------------------------------- |
| CLI first          | `msg` MUST always be a complete, human-readable line          |
| Standard-grounded  | SCOP MUST NOT conflict with POSIX or GNU; it defers to them   |
| Data-typed         | MSGIDs name the data type, not the display form               |
| Rooms derived      | Room is always derived from the command path — never declared |
| Zero app knowledge | A consumer MUST build any page from the stream alone          |
| Additive           | Consumers MUST ignore unknown MSGIDs and fields               |

---

## 4. Foundation Standards

### 4.1 POSIX.1 and GNU

Applications SHOULD conform to POSIX.1 Utility Syntax Guidelines (Chapter 12): single-hyphen short options (`-f`), `--` to end option processing, operands following options. Applications SHOULD implement GNU standard flags with defined contracts; each flag's event contract is defined in §8. Flags marked † have no defined contract yet.

| Flag          | Short | Category |
| ------------- | ----- | -------- |
| `--help`      | `-h`  | query    |
| `--version`   |       | query    |
| `--list`      | `-l`  | query    |
| `--status`    |       | query    |
| `--all`       | `-a`  | mode     |
| `--quiet`     | `-q`  | mode     |
| `--verbose`   | `-v`  | mode     |
| `--dry-run`   | `-n`  | modifier |
| `--recursive` | `-r`  | modifier |
| `--force`     | `-f`  | modifier |
| `--output`    | `-o`  | other †  |

_† Contract not yet defined; see pending additions._

Inverse flags (`--no-quiet`, `--no-recursive`, etc.) SHOULD be supported where the positive flag is supported.

### 4.2 RFC 5424 Fields

Every SCOP event is a serialised RFC 5424 message.

**Required:**

| Field | Key     | Description                                  |
| ----- | ------- | -------------------------------------------- |
| PRI   | `pri`   | Facility (16) + severity, encoded as integer |
| MSGID | `msgid` | SCOP event type (§7)                         |
| MSG   | `msg`   | Complete, human-readable line                |

**Optional:** `ts` (ISO 8601 timestamp), `app` (application name), `pid` (process id).

#### Severity → GUI rendering

| Severity | Value | Rendering                        |
| -------- | ----- | -------------------------------- |
| EMERG    | 0     | error modal (blocking)           |
| ALERT    | 1     | error modal (blocking)           |
| CRIT     | 2     | error modal (blocking)           |
| ERR      | 3     | error modal (blocking)           |
| WARNING  | 4     | warning banner                   |
| NOTICE   | 5     | log line                         |
| INFO     | 6     | log line                         |
| DEBUG    | 7     | suppressed by default (see §8.2) |

---

## 5. Wire Format

Events are serialised as **NDJSON** — one complete JSON object per line, separated by `\n`. Each line MUST be independently parseable. Producers MUST write to stdout. Producers MUST encode all output as **UTF-8**.

Every event MUST contain `pri`, `msgid`, `room`, and `msg`. The `msg` field MUST be a complete standalone readable line — it MUST NOT require other fields to be meaningful, and MUST NOT verbatim duplicate them.

```json
{"pri": 6, "msgid": "PROCESS_BEGIN", "room": "snapshot", "id": "snap", "label": "Snapshotting ./docs", "total": 142, "msg": "Snapshotting ./docs (142 files)"}
{"pri": 6, "msgid": "PROCESS_UPDATE", "room": "snapshot", "id": "snap", "current": 71, "total": 142, "msg": "71 of 142: README.md"}
{"pri": 6, "msgid": "PROCESS_END", "room": "snapshot", "id": "snap", "ok": true, "msg": "Snapshot complete"}
```

---

## 6. Room Model

A **room** is derived mechanically from the subcommand path — it is never declared explicitly.

**Derivation rule:** `room = subcommand tokens joined by "/"`, excluding all flag tokens (`-f`, `--flag`) and all positional operand values. Only the structural subcommand path tokens are included — not the runtime values passed to those subcommands. Root room = `null`.

| Invocation                               | Room              |
| ---------------------------------------- | ----------------- |
| `ourapp`                                 | `null`            |
| `ourapp snapshot`                        | `"snapshot"`      |
| `ourapp snapshot diff`                   | `"snapshot/diff"` |
| `ourapp snapshot --list`                 | `"snapshot"`      |
| `ourapp snapshot diff snap-001 snap-002` | `"snapshot/diff"` |

The last example shows that positional operand values (`snap-001`, `snap-002`) are excluded. Room strings MUST be stable across versions. Changing a room string is a breaking change.

---

## 7. Event Vocabulary

All MSGIDs are grouped into families by data type. Consumers route events to GUI slots by family (§10).

### 7.1 PAGE — Page Frame

Every stream MUST begin with `PAGE_BEGIN` and end with `PAGE_END`. `PAGE_END.msg` SHOULD be empty. If stdout closes or the process exits before `PAGE_END` is received, consumers MUST synthesize a terminal error state from any partial content already received — consumers MUST NOT remain in an indeterminate loading state (see §11).

| MSGID        | Required        | Optional                     |
| ------------ | --------------- | ---------------------------- |
| `PAGE_BEGIN` | `room`, `title` | `subtitle`, `icon`, `intent` |
| `PAGE_END`   | `room`          |                              |

The `icon` field, when present, MUST be a GitHub gemoji code of the form `:name:` (e.g., `:camera_with_flash:`). Raw Unicode codepoints MUST NOT be used. CLI renderers print or ignore the string as-is; GUI renderers map it to an icon asset.

The `intent` field declares how the consumer MUST integrate this stream into the current view. If omitted, consumers MUST treat it as `"query"`.

| `intent` value | Consumer behaviour                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------- |
| `"query"`      | Build or replace the page view. All slots updated. Used for --status, --list, --help, navigation. |
| `"action"`     | An operation is running. Route PROCESS\_\* to activity slot only. All other slots remain intact.  |

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": ":camera_with_flash:", "intent": "query", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

### 7.2 PROCESS — Running Operation

Lifecycle: `PROCESS_BEGIN` → `PROCESS_UPDATE` ×n → `PROCESS_END`. Omit `total` when unknown; consumers SHOULD render an indeterminate indicator. `dry_run: true` MUST be present on all events when `--dry-run` is active.

| MSGID            | Required        | Optional                        |
| ---------------- | --------------- | ------------------------------- |
| `PROCESS_BEGIN`  | `id`, `label`   | `total`, `dry_run`, `recursive` |
| `PROCESS_UPDATE` | `id`, `current` | `total`, `label`                |
| `PROCESS_END`    | `id`, `ok`      | `dry_run`                       |
| `PROCESS_LOG`    | `id`            |                                 |

`PROCESS_LOG` carries its payload in `msg` only — no separate `message` field. `msg` is already globally required and serves as the log line directly.

```json
{"pri": 6, "msgid": "PROCESS_BEGIN", "room": "snapshot", "id": "snap", "label": "Hashing files", "total": 42, "msg": "Hashing files (42)"}
{"pri": 6, "msgid": "PROCESS_UPDATE", "room": "snapshot", "id": "snap", "current": 21, "total": 42, "msg": "21 of 42: intro.md"}
{"pri": 6, "msgid": "PROCESS_LOG", "room": "snapshot", "id": "snap", "msg": "snap: skipping binary file"}
{"pri": 6, "msgid": "PROCESS_END", "room": "snapshot", "id": "snap", "ok": true, "msg": "Hashing complete"}
```

### 7.3 SCALAR — Single Named Value

`type` MUST be one of: `number`, `string`, `boolean`, `duration`, `bytes`.

**Serialization of abstract types:**

- `bytes` — `value` MUST be a JSON integer representing the absolute byte count (e.g. `12582912`). The `unit` field SHOULD carry the display denomination (e.g. `"bytes"`, `"KB"`, `"MB"`); formatting is the consumer's responsibility.
- `duration` — `value` MUST be ISO 8601 duration string (e.g. PT1M30S). Raw integers MUST NOT be used — unit is ambiguous without the format.

| MSGID          | Required                       | Optional               |
| -------------- | ------------------------------ | ---------------------- |
| `SCALAR_SET`   | `id`, `label`, `value`, `type` | `unit`, `display_hint` |
| `SCALAR_CLEAR` | `id`                           |                        |

`display_hint` is OPTIONAL and advisory; consumers MAY ignore it. Defined values: `"badge"`. Producers MUST NOT use values not defined in this spec.

```json
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "tracked", "label": "Tracked files", "value": 1042, "type": "number", "unit": "files", "msg": "Tracked files: 1042 files"}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "index_size", "label": "Index size", "value": 12582912, "type": "bytes", "unit": "MB", "msg": "Index size: 12 MB"}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "elapsed", "label": "Elapsed", "value": "PT1M30S", "type": "duration", "msg": "Elapsed: 1m 30s"}
```

### 7.4 LIST — Sequence

`ordered: true` renders as numbered; `false` as bullets. `value` MAY be scalar or a JSON object.

| MSGID          | Required                 | Optional |
| -------------- | ------------------------ | -------- |
| `LIST_DECLARE` | `id`, `label`, `ordered` |          |
| `LIST_APPEND`  | `id`, `item_id`, `value` |          |
| `LIST_UPDATE`  | `id`, `item_id`, `value` |          |
| `LIST_REMOVE`  | `id`, `item_id`          |          |
| `LIST_END`     | `id`                     |          |

```json
{"pri": 6, "msgid": "LIST_DECLARE", "room": "snapshot", "id": "changes", "label": "Changed files", "ordered": false, "msg": "Changed files"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "changes", "item_id": "f1", "value": "docs/intro.md", "msg": "+ docs/intro.md"}
{"pri": 6, "msgid": "LIST_UPDATE", "room": "snapshot", "id": "changes", "item_id": "f1", "value": "docs/intro.md (modified)", "msg": "~ docs/intro.md (modified)"}
{"pri": 6, "msgid": "LIST_END", "room": "snapshot", "id": "changes", "msg": "1 changed file"}
```

### 7.5 TABLE — Relation

`schema` MUST be an ordered array of column names. `values` MUST be a JSON object keyed by column name. `display_hint` is OPTIONAL and advisory (`"table"`, `"chart"`, `"cards"`); consumers MAY ignore it.

| MSGID           | Required                 | Optional       |
| --------------- | ------------------------ | -------------- |
| `TABLE_DECLARE` | `id`, `label`, `schema`  | `display_hint` |
| `TABLE_ROW`     | `id`, `row_id`, `values` |                |
| `TABLE_UPDATE`  | `id`, `row_id`, `values` |                |
| `TABLE_END`     | `id`                     |                |

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
PAGE_BEGIN (room: current, title: command name, intent: "query")
LIST_DECLARE (id: "help", ordered: false)
LIST_APPEND ×n (value: help-item object — see schema below)
LIST_END
PAGE_END
```

**Help-item schema** — normative definition of `value` for every `LIST_APPEND` where `id = "help"`:

| Field         | Type   | Required    | Description                                                                                                                                                        |
| ------------- | ------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `command`     | string | ✓           | CLI token for this entry (e.g. `"snap"`)                                                                                                                           |
| `description` | string | ✓           | Human-readable description                                                                                                                                         |
| `kind`        | string |             | `"action"` (executable leaf) or `"group"` (navigates to subroom). Default: `"action"`                                                                              |
| `params`      | array  | Conditional | MUST be present and non-empty for `kind = "action"` entries that accept one or more inputs. MAY be omitted for `kind = "group"` entries or parameter-free actions. |

**Param object** (each element of `params`):

| Field         | Type    | Required | Description                                                       |
| ------------- | ------- | -------- | ----------------------------------------------------------------- |
| `name`        | string  | ✓        | Flag name (e.g. `"--path"`) or positional label (e.g. `"target"`) |
| `kind`        | string  | ✓        | `"flag"` or `"positional"`                                        |
| `type`        | string  |          | One of the types defined in SCOP-M §5. Default: `"string"`        |
| `short`       | string  |          | Short alias (e.g. `"-p"`). Valid for `kind = "flag"` only         |
| `metavar`     | string  |          | Placeholder in usage line (e.g. `"PATH"`, `"SNAPSHOT"`)           |
| `required`    | boolean |          | Default: `true` for positionals, `false` for flags                |
| `repeatable`  | boolean |          | Whether the param may appear multiple times. Default: `false`     |
| `description` | string  |          | Human-readable description                                        |

**Ordering within `params`:** positionals MUST precede flags. Among flags, required flags MUST precede optional. Within each group, alphabetical by `name`.

**Compatibility:** consumers MUST ignore unknown fields in help-item and param objects. Producers MAY extend with additional fields.

**Params enforcement:** for `kind = "action"` entries that accept inputs, `params` is not optional — omitting it means consumers cannot build forms, validate invocations, or auto-generate UI without falling back to custom code, which defeats the zero-app-knowledge guarantee.

```json
{"pri": 6, "msgid": "LIST_APPEND", "room": "snap", "id": "help",
 "item_id": "restore",
 "value": {
   "command": "restore",
   "description": "Navigate to restore options",
   "kind": "group"
 },
 "msg": "  restore  Navigate to restore options"}

{"pri": 6, "msgid": "LIST_APPEND", "room": "snap", "id": "help",
 "item_id": "snap",
 "value": {
   "command": "snap",
   "description": "Take a new snapshot",
   "kind": "action",
   "params": [
     {"name": "target",     "kind": "positional", "metavar": "DIR",      "required": true,  "description": "Directory to snapshot"},
     {"name": "--date",     "kind": "flag", "short": "-d", "metavar": "DATETIME", "required": false, "description": "Snapshot timestamp"},
     {"name": "--dry-run",  "kind": "flag", "short": "-n", "type": "boolean",     "required": false, "description": "Preview without writing"},
     {"name": "--format",   "kind": "flag",               "metavar": "FORMAT",   "required": false, "description": "Output format"},
     {"name": "--path",     "kind": "flag", "short": "-p", "metavar": "PATH",     "required": false, "description": "Override snapshot path"},
     {"name": "--recursive","kind": "flag", "short": "-r", "type": "boolean",     "required": false, "description": "Include subdirectories"}
   ]
 },
 "msg": "  snap     Take a new snapshot"}
```

**`--version`**

```text
PAGE_BEGIN (room: null, title: app name, intent: "query")
SCALAR_SET (id: "version", type: "string", value: semver)
PAGE_END
```

**`--status`**

```text
PAGE_BEGIN (room: current, title: context name, intent: "query")
SCALAR_SET ×n
PAGE_END
```

**`--list` / `-l`**

```text
PAGE_BEGIN (room: current, title: context name, intent: "query")
TABLE_DECLARE → TABLE_ROW ×n → TABLE_END   (items have named fields)
  OR
LIST_DECLARE → LIST_APPEND ×n → LIST_END   (items are scalar)
PAGE_END
```

Use `TABLE` when items have two or more named fields (i.e. the producer would naturally model them as a struct or dict row); use `LIST` when items are scalars or single-value strings. When in doubt, `TABLE` with a single-column schema is valid.

### 8.2 Mode Flags

Mode flags adjust which events are emitted. They produce no events of their own. `--quiet` and `--verbose` are mutually exclusive; `--verbose` MUST take precedence.

| Flag               | Effect                                                                                                                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--quiet` / `-q`   | MUST suppress `PROCESS_LOG` and `PROCESS_UPDATE`. MUST NOT suppress `PAGE_BEGIN`, `PAGE_END`, `PROCESS_BEGIN`, `PROCESS_END`, `SCALAR_SET`, `LIST_*`, `TABLE_*`, or any event with `pri ≤ 4`. |
| `--verbose` / `-v` | MUST include `pri = 7` (DEBUG) events (suppressed by default; see §4.2)                                                                                                                       |
| `--all` / `-a`     | MUST expand scope of `LIST` and `TABLE` output                                                                                                                                                |

### 8.3 Process Modifier Flags

Modifier flags annotate `PROCESS_*` events with additional fields. No new MSGIDs are emitted.

| Flag                 | Added field | Value  |
| -------------------- | ----------- | ------ |
| `--dry-run` / `-n`   | `dry_run`   | `true` |
| `--recursive` / `-r` | `recursive` | `true` |
| `--force` / `-f`     | `force`     | `true` |

---

## 9. Page Template

A room that implements all three query flags can be fully described by those calls. A consumer that makes all three has everything needed to render a complete page without app-specific code.

```text
ourapp [subcommand] --status   →  page chrome + stats
ourapp [subcommand] --list     →  content
ourapp [subcommand] --help     →  actions
```

**Slot map:**

| Slot        | Flag        | MSGID                 | GUI rendering            |
| ----------- | ----------- | --------------------- | ------------------------ |
| Page chrome | any         | `PAGE_BEGIN`          | title, subtitle, icon    |
| Stats       | `--status`  | `SCALAR_SET`          | stat cards               |
| Content     | `--list`    | `TABLE_*` or `LIST_*` | grid, list               |
| Actions     | `--help`    | `LIST_*` (id="help")  | buttons, command palette |
| Activity    | any command | `PROCESS_*`           | progress, spinner        |

> **Routing note:** the `intent` field on `PAGE_BEGIN` — not the triggering flag — is the consumer's actual routing discriminant. `"query"` updates or replaces the page; `"action"` opens an activity overlay leaving all other slots intact. See §10 for the full routing table.

Each call is independent. A page MAY be built from a subset.

**Optional slots** (advisory, no new MSGIDs):

| Slot        | Convention                                   |
| ----------- | -------------------------------------------- |
| Description | `SCALAR_SET` with `id="page.description"`    |
| Chart       | `TABLE_DECLARE` with `display_hint: "chart"` |
| Empty state | `SCALAR_SET` with `id="page.empty"`          |
| Badge       | `SCALAR_SET` with `display_hint: "badge"`    |

**Full page manifest example** (`ourapp snapshot`) — help entries shown without `params` for brevity; conformance requires `params` for all `kind = "action"` entries that accept inputs (§8.1):

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": ":camera_with_flash:", "intent": "query", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "tracked", "label": "Tracked files", "value": 1042, "type": "number", "msg": "Tracked files: 1042"}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "last_snap", "label": "Last snapshot", "value": "2026-05-30T14:32:00Z", "type": "string", "msg": "Last snapshot: 2026-05-30T14:32:00Z"}
{"pri": 6, "msgid": "TABLE_DECLARE", "room": "snapshot", "id": "snaps", "label": "Snapshots", "schema": ["name", "files", "size", "date"], "msg": "Snapshots"}
{"pri": 6, "msgid": "TABLE_ROW", "room": "snapshot", "id": "snaps", "row_id": "s1", "values": {"name": "snap-001", "files": 42, "size": "1.2MB", "date": "2026-05-30"}, "msg": "snap-001  42 files  1.2MB  2026-05-30"}
{"pri": 6, "msgid": "TABLE_END", "room": "snapshot", "id": "snaps", "msg": "1 snapshot"}
{"pri": 6, "msgid": "LIST_DECLARE", "room": "snapshot", "id": "help", "label": "Commands", "ordered": false, "msg": "Commands"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "help", "item_id": "create", "value": {"command": "snapshot create", "description": "Take a new snapshot", "kind": "action"}, "msg": "  create    Take a new snapshot"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "help", "item_id": "diff", "value": {"command": "snapshot diff", "description": "Compare two snapshots", "kind": "action"}, "msg": "  diff      Compare two snapshots"}
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

| MSGID / condition                                    | Slot                  | Notes                                                                 |
| ---------------------------------------------------- | --------------------- | --------------------------------------------------------------------- |
| `PAGE_BEGIN` where `intent: "query"`, same room      | update page           | merge slot content; existing slots not covered by this stream persist |
| `PAGE_BEGIN` where `intent: "query"`, different room | replace page          | navigate to new room; all slots replaced                              |
| `PAGE_BEGIN` where `intent: "action"`                | open activity overlay | activity slot only; all other slots unchanged                         |
| `SCALAR_SET`                                         | stats area            | stat card                                                             |
| `TABLE_*`                                            | content area          | table, grid, or chart                                                 |
| `LIST_*` where `id="help"`                           | actions area          | buttons or command palette                                            |
| `LIST_*` otherwise                                   | content area          | list                                                                  |
| `PROCESS_*`                                          | activity indicator    | progress bar or spinner                                               |
| `PAGE_END` where `intent: "query"`                   | end of stream         | slot update complete; page remains visible                            |
| `PAGE_END` where `intent: "action"`                  | end of stream         | close activity overlay                                                |
| `pri` 0–3                                            | error modal           | blocking                                                              |
| `pri` 4                                              | warning banner        | non-blocking                                                          |
| `pri` 5–6                                            | log area              | append                                                                |
| `pri` 7                                              | suppressed            | see §8.2                                                              |

Unknown MSGIDs MUST be routed to the log area using `msg`. Unknown fields MUST be ignored.

Consumers MUST maintain independent slot state per `id` for `PROCESS_*` events. A room MAY contain multiple concurrent processes with distinct `id` values active simultaneously; consumers MUST NOT assume a 1:1 mapping between a room and an active process.

---

## 11. Conformance

**Producer MUST:** emit NDJSON to stdout; include `pri`, `msgid`, `room`, `msg` in every event; ensure `msg` is a complete human-readable line; wrap every stream in `PAGE_BEGIN` / `PAGE_END`; derive `room` from the subcommand path (§6); use only MSGIDs defined in §7; implement `--help`, `--version`, `--status`, and `--list` per §8.1; emit a well-formed empty page (`PAGE_BEGIN` + `SCALAR_SET` with `id="page.empty"` + `PAGE_END`) when a room has no data for `--status` or `--list`, rather than exiting with a non-zero status; encode all output as UTF-8.

**Producer SHOULD:** implement `--quiet`, `--verbose` (§8.2); implement `--dry-run` (§8.3); include `intent` on every `PAGE_BEGIN` — `"query"` for discovery flag streams (`--help`, `--status`, `--list`), `"action"` for command execution streams; design rooms such that `--status` and `--list` are invocable without positional arguments; NOT encode runtime entity identifiers in their room path; entity context is a runtime parameter, not a room identifier.

**Consumer MUST:** parse NDJSON line-by-line; route events per §10 using the `intent` field on `PAGE_BEGIN`; render `msg` as fallback for unknown MSGIDs; ignore unknown MSGIDs and fields without error; map RFC 5424 severity per §4.2; synthesize a terminal error state using any partial content received if stdout closes or the process exits before `PAGE_END` — MUST NOT remain in an indeterminate loading state; NOT suppress `dry_run: true` annotations; sanitize string values before rendering in HTML or injection-sensitive contexts.

**Consumer SHOULD:** implement the three-flag protocol (§9); support optional slots (§9); implement stream size limits.

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

- **SCOP-M v0.1.2-draft** — SCOP Manifest Format (companion specification)
- **LSP `$/progress`** — Language Server Protocol §3.16.1. Microsoft (2021).
- **Adaptive Cards** — adaptivecards.io
- **CloudEvents** — CNCF CloudEvents v1.0.2. cloudevents.io
- **TLDP Standard Options** — tldp.org/LDP/abs/html/standard-options.html
- **GitHub gemoji** — github.com/github/gemoji (icon field encoding standard)
