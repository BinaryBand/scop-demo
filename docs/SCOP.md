# Structured CLI Output Protocol (SCOP)

**Version:** 0.1.0-draft  
**Status:** Draft Specification  
**License:** CC0 1.0 Universal (Public Domain)

---

## Abstract

The Structured CLI Output Protocol (SCOP) defines a machine-readable output format for command-line applications that is simultaneously human-readable as plain text and automatically translatable to graphical user interfaces. SCOP builds on three existing standards — POSIX.1 Utility Conventions, GNU Coding Standards, and RFC 5424 (Syslog) — and adds a structured event vocabulary, a room-based page model, and a three-flag protocol that together enable any conforming CLI application to be rendered as a GUI without application-specific code.

---

## Status of This Document

This is a draft specification. It is published for review and comment. Feedback is welcomed. The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

---

## Table of Contents

1. Introduction
2. Terminology
3. Design Principles
4. Foundation Standards
5. Wire Format
6. Room Model
7. Event Vocabulary
8. GNU Flag Contract
9. Page Template
10. Auto-Translation Rules
11. Conformance
12. Security Considerations
13. References

---

## 1. Introduction

### 1.1 Motivation

Command-line applications are the primary interface for developer tooling, system administration, and automation. Despite decades of convention, no formal standard defines what a CLI application should output or how that output should be structured for machine consumption.

As a result, every CLI-to-GUI bridge must be written per-application. Rich terminal UIs (TUIs), web dashboards, and mobile front-ends each require custom adapter code that duplicates effort and couples tightly to application internals.

SCOP addresses this by defining a structured output format that is:

- **CLI-first** — every event is readable as plain text without a renderer
- **Standard-grounded** — built on POSIX, GNU, and RFC 5424 rather than replacing them
- **Auto-translatable** — a conforming renderer can build a full GUI from any SCOP-compliant application without application-specific code

### 1.2 Scope

SCOP defines:

- A wire format for structured CLI output (NDJSON over RFC 5424)
- A vocabulary of typed events (MSGIDs)
- A room-based page model derived from the command path
- A standard flag contract mapping GNU flags to event contracts
- A page template protocol enabling automatic GUI construction

SCOP does not define:

- GUI rendering implementation details
- Transport beyond stdout/stderr
- Authentication or access control
- Application business logic

### 1.3 Relationship to Existing Standards

SCOP is a composition of existing standards, not a replacement:

```text
POSIX.1 Ch.12 + GNU Coding Standards  →  input contract (flags, subcommands)
RFC 5424 (Syslog)                      →  event envelope (fields, severity)
NDJSON                                 →  wire format (serialisation)
SCOP                                   →  event vocabulary + page model
```

---

## 2. Terminology

**Application** — a SCOP-conforming CLI program.

**Command** — an invocation of an application with a specific subcommand path and flags.

**Consumer** — software that reads a SCOP event stream and renders it (a TUI, web frontend, mobile app, or log aggregator).

**Event** — a single NDJSON line emitted by an application.

**MSGID** — a string identifier that classifies an event by its data type. Defined in Section 7.

**Room** — a named page context derived mechanically from the subcommand path. Defined in Section 6.

**Stream** — the ordered sequence of events emitted by a single command invocation.

**Page** — a logical unit of GUI display corresponding to one room, assembled from one or more streams.

**Producer** — a SCOP-conforming CLI application that emits events.

**Slot** — a named region in a GUI page layout. Events are routed to slots by MSGID family.

---

## 3. Design Principles

The following principles govern all design decisions in this specification:

1. **CLI first.** Every event MUST be readable as plain text without a renderer. The `msg` field is always a complete, human-readable line.
2. **Standard-grounded.** SCOP MUST NOT conflict with POSIX.1 Utility Conventions or GNU Coding Standards. Where SCOP and those standards overlap, SCOP defers to them.
3. **Data-typed, not display-typed.** MSGIDs identify the data type of an event, not its display form. A renderer decides how to display a `TABLE`; the application does not.
4. **Rooms are derived, not declared.** The room of an event is always derived from the command's subcommand path. No explicit room declaration MSGID exists.
5. **Zero application knowledge.** A conforming renderer MUST be able to build a complete GUI page from any SCOP-conforming application using only the event stream. No out-of-band schema or application-specific code is permitted.
6. **Additive extension.** New MSGIDs and optional fields MAY be added in future versions without breaking conforming consumers. Consumers MUST ignore unknown MSGIDs and unknown fields.

---

## 4. Foundation Standards

### 4.1 POSIX.1 Utility Conventions (IEEE Std 1003.1)

Applications SHOULD conform to POSIX.1 Utility Syntax Guidelines (Chapter 12) for argument parsing:

- Short options: single hyphen followed by one alphanumeric character (`-f`)
- Option arguments separated by whitespace or `=`
- `--` terminates option processing
- Operands (non-option arguments) follow options

### 4.2 GNU Coding Standards

Applications SHOULD implement the following GNU standard flags. Each flag's event contract is defined in Section 8.

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

### 4.3 RFC 5424 (Syslog Protocol)

Every SCOP event is a serialised RFC 5424 message. The following RFC 5424 fields are REQUIRED in every event:

| Field | NDJSON key | Description |
| --- | --- | --- |
| PRI | `pri` | Facility (16 = local use 0) + severity, encoded as integer |
| MSGID | `msgid` | SCOP event type identifier (see Section 7) |
| MSG | `msg` | Human-readable line (MUST be complete and self-contained) |

The following RFC 5424 fields are OPTIONAL:

| Field | NDJSON key | Description |
| --- | --- | --- |
| TIMESTAMP | `ts` | ISO 8601 timestamp |
| APP-NAME | `app` | Application name |
| PROCID | `pid` | Process identifier |

Severity values follow RFC 5424:

| Severity | Value | SCOP rendering |
| --- | --- | --- |
| EMERG | 0 | error modal |
| ALERT | 1 | error modal |
| CRIT | 2 | error modal |
| ERR | 3 | error modal |
| WARNING | 4 | warning banner |
| NOTICE | 5 | log line |
| INFO | 6 | log line |
| DEBUG | 7 | suppressed by default |

---

## 5. Wire Format

### 5.1 Serialisation

SCOP events are serialised as **NDJSON** (Newline Delimited JSON): one complete JSON object per line, separated by `\n`. Each line MUST be independently parseable.

Applications MUST write events to **stdout**.

### 5.2 Required Fields

Every SCOP event MUST contain:

```json
{
  "pri":   <integer>,
  "msgid": <string>,
  "room":  <string | null>,
  "msg":   <string>
}
```

- `pri` MUST be a valid RFC 5424 PRI value (integer 0–191)
- `msgid` MUST be a value defined in Section 7
- `room` MUST be the derived room string (Section 6) or `null` for root
- `msg` MUST be a complete, human-readable line readable without a renderer

### 5.3 The msg Field

The `msg` field is the plain-text fallback for every event. It MUST:

- Be a complete, standalone readable line
- Require no other fields to be meaningful
- Not duplicate verbatim content of other fields (summarise instead)

A conforming CLI application piped through `cat` or `grep` MUST produce human-readable output from `msg` fields alone.

### 5.4 Example

```json
{"pri": 6, "msgid": "PROCESS_BEGIN", "room": "snapshot", "id": "snap", "label": "Snapshotting ./docs", "total": 142, "msg": "Snapshotting ./docs (142 files)"}
{"pri": 6, "msgid": "PROCESS_UPDATE", "room": "snapshot", "id": "snap", "current": 71, "total": 142, "msg": "71 of 142: README.md"}
{"pri": 6, "msgid": "PROCESS_END", "room": "snapshot", "id": "snap", "ok": true, "msg": "Snapshot complete"}
```

---

## 6. Room Model

### 6.1 Definition

A **room** is a named page context. Rooms are derived mechanically from the subcommand path of a command invocation. They are never declared explicitly.

### 6.2 Derivation Rule

```text
room = subcommand tokens joined by "/"
```

Flag tokens (beginning with `-`) are excluded from room derivation.

| Invocation | Room |
| --- | --- |
| `ourapp` | `null` |
| `ourapp snapshot` | `"snapshot"` |
| `ourapp snapshot diff` | `"snapshot/diff"` |
| `ourapp snapshot --list` | `"snapshot"` |
| `ourapp --help` | `null` |

### 6.3 Root Room

The root room (`null`) corresponds to the application home screen. It is populated by calling the application with no subcommand.

### 6.4 Room Stability

Room strings MUST be stable across application versions. Changing a room string is a breaking change.

---

## 7. Event Vocabulary

All MSGIDs are grouped into families. Each family represents a data type. Consumers route events to GUI slots by family (Section 10).

### 7.1 PAGE — Page Frame

Every stream MUST begin with `PAGE_BEGIN` and end with `PAGE_END`.

| MSGID | Required fields | Optional fields |
| --- | --- | --- |
| `PAGE_BEGIN` | `room`, `title` | `subtitle`, `icon` |
| `PAGE_END` | `room` | |

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": "📸", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

`PAGE_END.msg` SHOULD be an empty string.

### 7.2 PROCESS — Running Operation

A running operation with countable state. Consumers MAY render as a progress bar, spinner, or counter. The lifecycle is: `PROCESS_BEGIN` → `PROCESS_UPDATE` ×n → `PROCESS_END`

| MSGID | Required fields | Optional fields |
| --- | --- | --- |
| `PROCESS_BEGIN` | `id`, `label` | `total`, `dry_run`, `recursive` |
| `PROCESS_UPDATE` | `id`, `current` | `total`, `label` |
| `PROCESS_END` | `id`, `ok` | `dry_run` |
| `PROCESS_LOG` | `id`, `message` | |

`total` is OPTIONAL in `PROCESS_BEGIN` — omit when the total is unknown. When omitted, consumers SHOULD render an indeterminate indicator.

`dry_run: true` MUST be present on all `PROCESS_*` events when `--dry-run` is active. No side effects MUST occur when `dry_run` is true.

### 7.3 SCALAR — Single Named Value

A single named value. Consumers MAY render as a stat card, badge, or inline label.

| MSGID | Required fields | Optional fields |
| --- | --- | --- |
| `SCALAR_SET` | `id`, `label`, `value`, `type` | `unit` |
| `SCALAR_CLEAR` | `id` | |

`type` MUST be one of: `number`, `string`, `boolean`, `duration`, `bytes`.

### 7.4 LIST — Sequence

An ordered or unordered sequence of items. Consumers MAY render as a bulleted list, numbered list, chip set, or command palette.

| MSGID | Required fields | Optional fields |
| --- | --- | --- |
| `LIST_DECLARE` | `id`, `label`, `ordered` | |
| `LIST_APPEND` | `id`, `item_id`, `value` | |
| `LIST_UPDATE` | `id`, `item_id`, `value` | |
| `LIST_REMOVE` | `id`, `item_id` | |
| `LIST_END` | `id` | |

`value` MAY be a scalar or a JSON object. When `value` is an object, consumers SHOULD render it as a labelled item with a description.

### 7.5 TABLE — Relation

A set of records with named columns. Consumers MAY render as a table, data grid, card list, or chart.

| MSGID | Required fields | Optional fields |
| --- | --- | --- |
| `TABLE_DECLARE` | `id`, `label`, `schema` | `display_hint` |
| `TABLE_ROW` | `id`, `row_id`, `values` | |
| `TABLE_UPDATE` | `id`, `row_id`, `values` | |
| `TABLE_END` | `id` | |

`schema` MUST be an ordered array of column name strings.
`values` MUST be a JSON object keyed by column name.
`display_hint` is OPTIONAL and advisory. Valid values: `"table"`,
`"chart"`, `"cards"`. Consumers MAY ignore it.

---

## 8. GNU Flag Contract

Each GNU standard flag has a defined event contract. Applications MUST emit the specified events when the flag is present.

### 8.1 Query Flags

Query flags produce data output and exit.

**`--help` / `-h`**

```text
PAGE_BEGIN (room: current, title: command name)
LIST_DECLARE (id: "help", label: "Commands", ordered: false)
LIST_APPEND ×n (item_id: command or flag, value: {command, description})
LIST_END (id: "help")
PAGE_END
```

**`--version`**

```text
PAGE_BEGIN (room: null, title: app name)
SCALAR_SET (id: "version", label: "version", value: semver, type: "string")
PAGE_END
```

**`--status`**

```text
PAGE_BEGIN (room: current, title: context name)
SCALAR_SET ×n (current application state values)
PAGE_END
```

**`--list` / `-l`**

```text
PAGE_BEGIN (room: current, title: context name)
TABLE_DECLARE → TABLE_ROW ×n → TABLE_END
  OR
LIST_DECLARE → LIST_APPEND ×n → LIST_END
PAGE_END
```

Use `TABLE` when items have named fields. Use `LIST` when items are scalar.

### 8.2 Mode Flags

Mode flags adjust which events are emitted. They produce no events of their own.

| Flag | Effect on stream |
| --- | --- |
| `--quiet` / `-q` | MUST suppress `PROCESS_LOG`; MUST suppress `pri ≥ 5` (NOTICE) |
| `--verbose` / `-v` | MUST include `pri = 7` (DEBUG) `PROCESS_LOG` events |
| `--all` / `-a` | MUST expand the scope of `LIST` and `TABLE` output |

`--quiet` and `--verbose` are mutually exclusive. `--verbose` MUST take precedence if both are supplied.

### 8.3 Process Modifier Flags

Modifier flags annotate `PROCESS_*` events with additional fields.

| Flag | Added field | Value |
| --- | --- | --- |
| `--dry-run` / `-n` | `dry_run` | `true` |
| `--recursive` / `-r` | `recursive` | `true` |
| `--force` / `-f` | `force` | `true` |

---

## 9. Page Template

### 9.1 Overview

The Page Template defines a standard layout for GUI pages. Any room can be fully described using three flag calls: `--status`, `--list`, and `--help`. A consumer that makes these three calls has all the data it needs to render a complete page without application-specific code.

### 9.2 Slot Map

| Slot | Filled by | MSGID source | GUI rendering |
| --- | --- | --- | --- |
| Page chrome | `--status` or any call | `PAGE_BEGIN` | title, subtitle, icon |
| Stats | `--status` | `SCALAR_SET` | stat cards, key metrics |
| Content | `--list` | `TABLE` or `LIST` | data grid, list |
| Actions | `--help` | `LIST` (id="help") | buttons, command palette |
| Activity | any running command | `PROCESS_*` | progress bar, spinner |

### 9.3 The Three-Flag Protocol

A consumer SHOULD call these three commands to build any page:

```text
ourapp [subcommand] --status   →  page chrome + stats
ourapp [subcommand] --list     →  content
ourapp [subcommand] --help     →  actions
```

Each call is independent. A page MAY be built from a subset if the full set is not available.

### 9.4 Optional Slots

The following optional slots enrich GUI rendering without affecting CLI readability.

| Slot | How to fill | MSGID |
| --- | --- | --- |
| Page description | `SCALAR_SET` with `id="page.description"` | `SCALAR_SET` |
| Diagram / chart | `TABLE_DECLARE` with `display_hint: "chart"` | `TABLE_*` |
| Empty state | `SCALAR_SET` with `id="page.empty"` | `SCALAR_SET` |
| Badge | `SCALAR_SET` with `type: "badge"` | `SCALAR_SET` |

All optional slot conventions use reserved field values on existing MSGIDs. No new MSGIDs are introduced.

### 9.5 Example

Full page manifest for `ourapp snapshot`:

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "subtitle": "Manage and compare snapshots", "icon": "📸", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "last_snap", "label": "Last snapshot", "value": "2026-05-30T14:32:00Z", "type": "string", "msg": "Last snapshot: 2026-05-30T14:32:00Z"}
{"pri": 6, "msgid": "SCALAR_SET", "room": "snapshot", "id": "tracked", "label": "Tracked files", "value": 1042, "type": "number", "msg": "Tracked files: 1042"}
{"pri": 6, "msgid": "TABLE_DECLARE", "room": "snapshot", "id": "snaps", "label": "Snapshots", "schema": ["name", "files", "size", "date"], "msg": "Snapshots"}
{"pri": 6, "msgid": "TABLE_ROW", "room": "snapshot", "id": "snaps", "row_id": "s1", "values": {"name": "snap-001", "files": 42, "size": "1.2MB", "date": "2026-05-30"}, "msg": "snap-001  42 files  1.2MB  2026-05-30"}
{"pri": 6, "msgid": "TABLE_END", "room": "snapshot", "id": "snaps", "msg": "1 snapshot"}
{"pri": 6, "msgid": "LIST_DECLARE", "room": "snapshot", "id": "help", "label": "Commands", "ordered": false, "msg": "Commands"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "help", "item_id": "create", "value": {"command": "snapshot create", "description": "Take a new snapshot"}, "msg": "  create    Take a new snapshot"}
{"pri": 6, "msgid": "LIST_APPEND", "room": "snapshot", "id": "help", "item_id": "diff", "value": {"command": "snapshot diff", "description": "Compare two snapshots"}, "msg": "  diff      Compare two snapshots"}
{"pri": 6, "msgid": "LIST_END", "room": "snapshot", "id": "help", "msg": ""}
{"pri": 6, "msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

---

## 10. Auto-Translation Rules

A conforming consumer routes events to GUI slots using this lookup table. No application knowledge is required.

| MSGID family | GUI slot | Notes |
| --- | --- | --- |
| `PAGE_BEGIN` | open page | set title, subtitle, icon |
| `SCALAR_SET` | stats area | render as stat card |
| `TABLE_*` | content area | render as table, grid, or chart |
| `LIST_*` where `id="help"` | actions area | render as buttons or command palette |
| `LIST_*` otherwise | content area | render as list |
| `PROCESS_*` | activity indicator | render as progress bar or spinner |
| `PAGE_END` | close page | finalise layout |
| `pri` 0–3 | error modal | display blocking error |
| `pri` 4 | warning banner | display non-blocking warning |
| `pri` 5–6 | log area | append to log |
| `pri` 7 | suppressed | hidden unless `--verbose` |

Unknown MSGIDs MUST be routed to the log area using the `msg` field. Unknown fields MUST be ignored.

---

## 11. Conformance

### 11.1 Producer Conformance (CLI Application)

A SCOP-conforming producer MUST:

1. Emit NDJSON to stdout, one event per line
2. Include `pri`, `msgid`, `room`, and `msg` in every event
3. Ensure `msg` is a complete, human-readable line
4. Wrap every stream in `PAGE_BEGIN` / `PAGE_END`
5. Derive `room` from the subcommand path per Section 6
6. Use only MSGIDs defined in Section 7
7. Implement `--help` per the contract in Section 8.1
8. Implement `--version` per the contract in Section 8.1

A SCOP-conforming producer SHOULD:

1. Implement `--status` per the contract in Section 8.1
2. Implement `--list` per the contract in Section 8.1
3. Implement `--quiet` and `--verbose` per Section 8.2
4. Implement `--dry-run` per Section 8.3

### 11.2 Consumer Conformance (GUI Renderer)

A SCOP-conforming consumer MUST:

1. Parse NDJSON line-by-line
2. Route events to slots per Section 10
3. Render the `msg` field as a fallback for unknown MSGIDs
4. Ignore unknown MSGIDs without error
5. Ignore unknown fields without error
6. Map RFC 5424 severity to the display rules in Section 4.3

A SCOP-conforming consumer SHOULD:

1. Implement the three-flag protocol per Section 9.3
2. Support the optional slots defined in Section 9.4

---

## 12. Security Considerations

**Injection.** The `msg` field and all string values are untrusted input. Consumers MUST sanitise values before rendering in HTML or other injection-sensitive contexts.

**Denial of service.** A malicious producer MAY emit an unbounded number of events. Consumers SHOULD implement stream size limits.

**Sensitive data.** Applications MUST NOT include secrets, credentials, or personally identifiable information in SCOP events. The `crypto` utility family MUST NOT emit key material.

**Dry run.** Consumers MUST NOT suppress `dry_run: true` annotations. Users MUST be able to distinguish dry-run output from real output.

---

## 13. References

### Normative References

- **RFC 2119** — Key words for use in RFCs to Indicate Requirement Levels. Bradner, S. (1997).
- **RFC 5424** — The Syslog Protocol. Gerhards, R. (2009).
- **IEEE Std 1003.1-2024** — POSIX.1-2024 Base Specifications, Issue 8.
- **GNU Coding Standards** — Stallman, R. et al. gnu.org/prep/standards
- **NDJSON** — Newline Delimited JSON. ndjson.org

### Informative References

- **LSP `$/progress`** — Language Server Protocol Specification, §3.16.1. Microsoft (2021).
- **Adaptive Cards** — Microsoft Adaptive Cards Specification. adaptivecards.io
- **CloudEvents** — CNCF CloudEvents Specification v1.0.2. cloudevents.io
- **TLDP Standard Options** — Standard Command-Line Options. tldp.org/LDP/abs/html/standard-options.html
