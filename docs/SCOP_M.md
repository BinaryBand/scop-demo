# SCOP-M: Structured CLI Output Protocol — Manifest Format

**Version:** 0.1.2-draft  
**Status:** Draft Specification  
**License:** CC0 1.0 Universal (Public Domain)  
**Companion to:** SCOP v0.1.2-draft

---

## Abstract

SCOP-M defines a declarative file format for describing a SCOP-conforming CLI application. A single `scop.toml` file captures every room, command, parameter type, and output schema in one place. It is the static equivalent of calling `--help`, `--status`, and `--list` on every room simultaneously. GUI renderers consume it to scaffold a complete application shell without invoking the CLI; the SCOP NDJSON stream supplies the live data at runtime.

---

## Status of This Document

Draft specification, published for review and comment. The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY", and "OPTIONAL" are interpreted as described in RFC 2119.

---

## 1. Introduction

SCOP defines how a CLI application emits structured output at runtime. SCOP-M defines how the same application declares its structure statically. The two are complementary:

```proto
scop.toml          ← static  (design time)   full structure declared
     ↕  semantically equivalent to
--help/--status/--list per room ← discovery  same structure, live
     ↕  dynamic data provided by
PROCESS_* / SCALAR_* / TABLE_* / LIST_* ← runtime  actual values
```

A SCOP-M file is OPTIONAL. A producer that does not supply one is still SCOP-conforming. A producer that does supply one MUST ensure the manifest remains semantically consistent with its runtime `--help`, `--status`, and `--list` output.

### 1.1 What SCOP-M enables

- **GUI scaffold** — a renderer reads `scop.toml` and builds the complete application shell before invoking a single command
- **Form rendering** — `param` definitions describe input widgets, validation, and defaults
- **Static validation** — the manifest can be linted against this spec before deployment
- **Code generation** — CLI stubs, documentation, and type bindings can be generated from the manifest
- **Discovery shortcut** — consumers MAY use the manifest in place of the three-flag discovery protocol (§9 of SCOP)

---

## 2. Terminology

**Manifest** — a `scop.toml` file conforming to this specification.  
**Room** — a page context; corresponds directly to SCOP room strings (§6 of SCOP).  
**Command** — an action available within a room; maps to a CLI subcommand or flag combination.  
**Param** — a typed, named input accepted by a command.  
**Stat** — a named scalar value emitted by `--status`; maps to a `SCALAR_SET` event.  
**List schema** — the column definition for `--list` output; maps to `TABLE_DECLARE.schema`.  
**Global param** — a param inherited by every command in every room.

---

## 3. File Format

SCOP-M manifests are written in **TOML** (Tom's Obvious Minimal Language). The canonical filename is `scop.toml`, placed at the repository root alongside `pyproject.toml` or `Cargo.toml`.

Producers MAY embed the manifest under `[tool.scop]` in an existing `pyproject.toml` rather than using a standalone file.

```toml
# pyproject.toml — embedded form
[tool.scop.app]
name    = "myapp"
version = "0.1.0"
```

```toml
# scop.toml — standalone form (preferred)
[app]
name    = "myapp"
version = "0.1.0"
```

The standalone form is used throughout this specification.

> **TOML ordering rule:** TOML attaches key-value pairs to the most recently declared
> array-of-tables header. All keys for a `[[room.command]]` MUST be declared before
> any nested `[[room.command.param]]` blocks. Keys written after a nested block are
> silently attached to that block, not to the parent command.
>
> ```toml
> [[room.command]]
> name        = "diff"   # ✓ declared before params
> description = "Compare two snapshots"
>
>   [[room.command.param]]
>   name = "a"
>   type = "string"
>
> # timeout = 30  ← WRONG: attached to param "a", not the command
> ```

---

## 4. Schema

### 4.1 `[app]` — Application metadata

REQUIRED. Appears exactly once.

| Key            | Type   | Required | Description                                              |
| -------------- | ------ | -------- | -------------------------------------------------------- |
| `name`         | string | ✓        | Application name; used as the root room title            |
| `version`      | string | ✓        | Semver string                                            |
| `description`  | string |          | Short description; used as the root room subtitle        |
| `scop_version` | string |          | SCOP spec version this manifest targets (e.g. `"0.1.0"`) |

```toml
[app]
name         = "scop"
version      = "0.1.0"
description  = "File and directory snapshotter"
scop_version = "0.1.2-draft"
```

---

### 4.2 `[[app.global_param]]` — Global parameter

OPTIONAL array within `[app]`. Params defined here are implicitly inherited by every command in every room. Identical to `[[room.command.param]]` in structure (§4.7). Use for universal flags such as `--verbose`, `--quiet`, and `--dry-run` to avoid repetition.

A command-level `[[room.command.param]]` with the same `name` as a global param overrides the global definition for that command only.

```toml
[[app.global_param]]
name     = "--verbose"
short    = "-v"
kind     = "flag"
type     = "boolean"
required = false

[[app.global_param]]
name     = "--quiet"
short    = "-q"
kind     = "flag"
type     = "boolean"
required = false

[[app.global_param]]
name     = "--dry-run"
short    = "-n"
kind     = "flag"
type     = "boolean"
required = false
```

---

### 4.3 `[[room]]` — Page definition

OPTIONAL array. Each entry defines one room. The root room has `id = ""`. Room `id` values MUST match the string produced by SCOP §6 room derivation — i.e. the subcommand tokens that invoke the room, joined by `"/"`.

| Key        | Type   | Required | Description                                                     |
| ---------- | ------ | -------- | --------------------------------------------------------------- |
| `id`       | string | ✓        | Room path string matching SCOP §6 derivation. Use `""` for root |
| `title`    | string | ✓        | Maps to `PAGE_BEGIN.title`                                      |
| `subtitle` | string |          | Maps to `PAGE_BEGIN.subtitle`                                   |
| `icon`     | string |          | GitHub gemoji code (`:name:`). Maps to `PAGE_BEGIN.icon`        |

```toml
[[room]]
id       = ""
title    = "scop"
subtitle = "File and directory snapshotter"
icon     = ":package:"

[[room]]
id       = "snap"
title    = "Snapshots"
subtitle = "Manage and compare snapshots"
icon     = ":camera_with_flash:"
```

---

### 4.4 `[[room.stat]]` — Status output schema

OPTIONAL array within a `[[room]]`. Declares the `SCALAR_SET` events emitted by `--status` for this room.

| Key     | Type   | Required | Description                    |
| ------- | ------ | -------- | ------------------------------ |
| `id`    | string | ✓        | Maps to `SCALAR_SET.id`        |
| `label` | string | ✓        | Maps to `SCALAR_SET.label`     |
| `type`  | string | ✓        | One of the types defined in §5 |
| `unit`  | string |          | Maps to `SCALAR_SET.unit`      |

```toml
[[room]]
id = "snap"

  [[room.stat]]
  id    = "tracked"
  label = "Tracked files"
  type  = "number"
  unit  = "files"

  [[room.stat]]
  id    = "last_snap"
  label = "Last snapshot"
  type  = "datetime"
```

---

### 4.5 `[room.list]` — List output schema

OPTIONAL table within a `[[room]]`. Declares the `TABLE_DECLARE.schema` emitted by `--list` for this room.

| Key            | Type     | Required | Description                                              |
| -------------- | -------- | -------- | -------------------------------------------------------- |
| `schema`       | string[] | ✓        | Ordered column names. Maps to `TABLE_DECLARE.schema`     |
| `display_hint` | string   |          | Advisory rendering hint: `"table"`, `"chart"`, `"cards"` |

```toml
[[room]]
id = "snap"

  [room.list]
  schema       = ["name", "files", "size", "date"]
  display_hint = "table"
```

---

### 4.6 `[[room.command]]` — Command definition

OPTIONAL array within a `[[room]]`. Each entry declares one available command.

The `name` field is the display label shown in the GUI. The `exec` field is the CLI token actually invoked. When `name` and `exec` differ — or when a display label contains spaces or mixed case — `exec` MUST be provided. This decouples the GUI label from the CLI invocation and prevents the room routing collision described in §3.

| Key           | Type   | Required | Description                                                                                                                                               |
| ------------- | ------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`        | string | ✓        | Display label shown in GUI and `--help` output                                                                                                            |
| `exec`        | string |          | CLI token to invoke. Defaults to `name` if omitted. MUST be provided when `name` differs from the CLI token                                               |
| `description` | string | ✓        | Maps to `LIST_APPEND.value.description` in `--help` output                                                                                                |
| `kind`        | string |          | `"action"` (executes in the current room) or `"group"` (navigates to a subroom). Default: `"action"`. Maps to `LIST_APPEND.value.kind` in `--help` output |
| `navigates`   | string |          | Room `id` this command navigates to after execution. MUST match SCOP §6 room derivation. Omit if the command stays in the current room                    |

> **Routing rule:** `navigates` MUST equal the room `id` that SCOP will derive at runtime from the invocation. For `ourapp snap [args]`, SCOP derives room `"snap"`, so `navigates = "snap"`. Setting `navigates` to an undeclared room `id` is a conformance violation.

```toml
[[room]]
id = ""

  [[room.command]]
  name        = "Snapshot"
  exec        = "snap"
  description = "Take a snapshot of a directory"
  navigates   = "snap"

  [[room.command]]
  name        = "Diff"
  exec        = "diff"
  description = "Compare two snapshots"
  navigates   = "diff"
```

---

### 4.7 `[[room.command.param]]` — Parameter definition

OPTIONAL array within a `[[room.command]]`. Each entry declares one typed input. All keys MUST be declared before any nested blocks (see §3 TOML ordering rule).

The `kind` field MUST be provided. Inferring parameter kind from the presence of a leading hyphen is fragile and not supported — non-standard single-dash long flags and symbol-prefixed positionals cannot be inferred reliably.

| Key           | Type     | Required | Description                                                               |
| ------------- | -------- | -------- | ------------------------------------------------------------------------- |
| `name`        | string   | ✓        | Flag name (e.g. `"--path"`) or positional label (e.g. `"target"`)         |
| `kind`        | string   | ✓        | `"flag"` or `"positional"`. Determines CLI assembly syntax                |
| `type`        | string   | ✓        | One of the types defined in §5                                            |
| `short`       | string   |          | Single-character short flag (e.g. `"-p"`). Valid for `kind = "flag"` only |
| `metavar`     | string   |          | Placeholder shown in usage line (e.g. `"PATH"`, `"SNAPSHOT"`)             |
| `description` | string   |          | Human-readable description of this parameter                              |
| `required`    | boolean  |          | Default: `false` for `"flag"`, `true` for `"positional"`                  |
| `repeatable`  | boolean  |          | Whether the param may appear multiple times. Default: `false`             |
| `default`     | any      |          | Default value; type must match `type`                                     |
| `pattern`     | string   |          | Regex validation. Valid for `string` and `path` types                     |
| `choices`     | string[] |          | Valid values. Required when `type = "choice"`                             |
| `min`         | number   |          | Minimum value. Valid for `number` type                                    |
| `max`         | number   |          | Maximum value. Valid for `number` type                                    |
| `format`      | string   |          | Format hint. Valid for `datetime` and `duration` types                    |
| `min_length`  | number   |          | Minimum length. Valid for `string` type                                   |
| `max_length`  | number   |          | Maximum length. Valid for `string` type                                   |

```toml
[[room]]
id = "snap"

  [[room.command]]
  name        = "New Snapshot"
  exec        = "snap"
  description = "Take a new snapshot"

    [[room.command.param]]
    name        = "target"
    kind        = "positional"
    type        = "path"
    metavar     = "DIR"
    required    = true
    description = "Directory to snapshot"

    [[room.command.param]]
    name        = "--date"
    kind        = "flag"
    short       = "-d"
    type        = "datetime"
    metavar     = "DATETIME"
    required    = false
    description = "Snapshot timestamp"

    [[room.command.param]]
    name        = "--format"
    kind        = "flag"
    type        = "choice"
    metavar     = "FORMAT"
    choices     = ["json", "tar", "zip"]
    required    = false
    default     = "json"
    description = "Output format"
```

---

## 5. Type System

The following types are built-in. Producers MUST use one of these values for `param.type` and `stat.type`.

The **SCOP wire type** column shows the `SCALAR_SET.type` value emitted at runtime. Types that are manifest-level annotations over `string` (e.g. `path`, `datetime`, `choice`) are transmitted as `string` on the wire; the manifest type is metadata for input validation and GUI widget selection only.

| Type       | GUI widget hint   | Validation fields                     | JSON serialization                         | SCOP wire type |
| ---------- | ----------------- | ------------------------------------- | ------------------------------------------ | -------------- |
| `string`   | text input        | `pattern`, `min_length`, `max_length` | JSON string                                | `string`       |
| `number`   | numeric input     | `min`, `max`                          | JSON number                                | `number`       |
| `boolean`  | checkbox / toggle | —                                     | JSON boolean                               | `boolean`      |
| `path`     | file / dir picker | `pattern`                             | JSON string                                | `string`       |
| `datetime` | date-time picker  | `format`, `min`, `max`                | JSON string (ISO 8601)                     | `string`       |
| `duration` | duration input    | `format`                              | JSON string (ISO 8601, e.g. `"PT1M30S"`)   | `duration`     |
| `bytes`    | file size display | —                                     | JSON integer (absolute byte count)         | `bytes`        |
| `choice`   | select / dropdown | `choices`                             | JSON string; MUST be a member of `choices` | `string`       |

---

## 6. Semantic Equivalence

A SCOP-M manifest MUST be semantically equivalent to the runtime discovery output. Specifically:

| Manifest field                               | Runtime equivalent                                                             |
| -------------------------------------------- | ------------------------------------------------------------------------------ |
| `room.title`, `room.subtitle`, `room.icon`   | `PAGE_BEGIN` fields for that room                                              |
| `room.stat.*`                                | `SCALAR_SET` events emitted by `ourapp [room] --status`                        |
| `room.list.schema`                           | `TABLE_DECLARE.schema` emitted by `ourapp [room] --list`                       |
| `room.command.exec`, `.description`, `.kind` | `LIST_APPEND.value.command`, `.description`, `.kind` in `ourapp [room] --help` |
| `room.command.param.*`                       | `LIST_APPEND.value.params` entries (SCOP §8.1 help-item schema)                |
| `app.global_param.*`                         | Inherited `params` entries on every command                                    |

A conformance test tool MAY verify equivalence by running the CLI and diffing its `--help` / `--status` / `--list` output against the manifest.

---

## 7. Complete Example

```toml
[app]
name         = "scop"
version      = "0.1.0"
description  = "File and directory snapshotter"
scop_version = "0.1.0"

# ── Global params — inherited by every command ───────────────────────────────
[[app.global_param]]
name     = "--verbose"
kind     = "flag"
short    = "-v"
type     = "boolean"
required = false

[[app.global_param]]
name     = "--quiet"
kind     = "flag"
short    = "-q"
type     = "boolean"
required = false

[[app.global_param]]
name     = "--dry-run"
kind     = "flag"
short    = "-n"
type     = "boolean"
required = false

# ── Root room ────────────────────────────────────────────────────────────────
[[room]]
id       = ""
title    = "scop"
subtitle = "File and directory snapshotter"
icon     = ":package:"

  [[room.command]]
  name        = "Snapshot"
  exec        = "snap"
  description = "Take a snapshot of a directory"
  navigates   = "snap"

  [[room.command]]
  name        = "Diff"
  exec        = "diff"
  description = "Compare two snapshots"
  navigates   = "diff"

  [[room.command]]
  name        = "Restore"
  exec        = "restore"
  description = "Restore a snapshot"
  navigates   = "restore"

  [[room.command]]
  name        = "Log"
  exec        = "log"
  description = "List all snapshots"
  navigates   = "log"

# ── Log room ─────────────────────────────────────────────────────────────────
[[room]]
id       = "log"
title    = "Log"
subtitle = "Snapshot history"
icon     = ":scroll:"

  [room.list]
  schema = ["name", "files", "size", "date"]

# ── Snap room ────────────────────────────────────────────────────────────────
[[room]]
id       = "snap"
title    = "Snapshots"
subtitle = "Manage and compare snapshots"
icon     = ":camera_with_flash:"

  [[room.stat]]
  id    = "tracked"
  label = "Tracked files"
  type  = "number"
  unit  = "files"

  [[room.stat]]
  id    = "last_snap"
  label = "Last snapshot"
  type  = "datetime"

  [[room.stat]]
  id    = "changed"
  label = "Changed since last snap"
  type  = "number"
  unit  = "files"

  [room.list]
  schema = ["name", "files", "size", "date"]

  [[room.command]]
  name        = "New Snapshot"
  exec        = "snap"
  description = "Take a new snapshot"

    [[room.command.param]]
    name     = "--path"
    kind     = "flag"
    short    = "-p"
    type     = "path"
    pattern  = "^/[^\\0]*$"
    required = false
    default  = "."

    [[room.command.param]]
    name     = "--date"
    kind     = "flag"
    short    = "-d"
    type     = "datetime"
    required = false

    [[room.command.param]]
    name     = "--format"
    kind     = "flag"
    type     = "choice"
    choices  = ["json", "tar", "zip"]
    required = false
    default  = "json"

    [[room.command.param]]
    name     = "--recursive"
    kind     = "flag"
    short    = "-r"
    type     = "boolean"
    required = false

# ── Diff room ────────────────────────────────────────────────────────────────
[[room]]
id       = "diff"
title    = "Diff"
subtitle = "Compare two snapshots"
icon     = ":left_right_arrow:"

  [[room.command]]
  name        = "Compare"
  exec        = "diff"
  description = "Compare two snapshots"

    [[room.command.param]]
    name        = "a"
    kind        = "positional"
    type        = "string"
    required    = true
    description = "First snapshot name"

    [[room.command.param]]
    name        = "b"
    kind        = "positional"
    type        = "string"
    required    = true
    description = "Second snapshot name"

# ── Restore room ─────────────────────────────────────────────────────────────
[[room]]
id       = "restore"
title    = "Restore"
subtitle = "Restore a snapshot to disk"
icon     = ":floppy_disk:"

  [[room.command]]
  name        = "Restore Snapshot"
  exec        = "restore"
  description = "Restore a snapshot"

    [[room.command.param]]
    name        = "name"
    kind        = "positional"
    type        = "string"
    required    = true
    description = "Snapshot name to restore"
```

---

## 8. Conformance

**A conforming manifest MUST:**

1. Be valid TOML
2. Include a `[app]` section with `name` and `version`
3. Use only type values defined in §5
4. Provide `choices` when `type = "choice"`
5. Use GitHub gemoji codes (`:name:`) for all `icon` fields
6. Use room `id` values consistent with SCOP §6 room derivation
7. Provide `kind` on every `[[room.command.param]]`
8. Provide `exec` when `name` differs from the CLI token
9. Include `params` on every `[[room.command]]` with `kind = "action"` that accepts one or more inputs

**A conforming manifest SHOULD:**

1. Include a `[[room]]` entry for every room the application emits events in
2. Declare `[[room.stat]]` entries for every `SCALAR_SET` emitted by `--status`
3. Declare `[room.list]` for every room that emits `TABLE_DECLARE` via `--list`
4. Declare universal flags in `[[app.global_param]]` rather than repeating them per command
5. Be kept semantically equivalent to runtime `--help` / `--status` / `--list` output (§6)

---

## 9. References

### Normative

- **SCOP v0.1.2-draft** — Structured CLI Output Protocol
- **TOML v1.0** — toml.io
- **RFC 2119** — Key words for use in RFCs. Bradner, S. (1997).
- **GitHub gemoji** — github.com/github/gemoji

### Informative

- **OpenAPI Specification** — openapi.org
- **JSON Schema** — json-schema.org
- **Cargo.toml reference** — doc.rust-lang.org/cargo/reference/manifest.html
