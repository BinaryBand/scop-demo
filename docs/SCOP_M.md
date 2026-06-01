# SCOP-M: Structured CLI Output Protocol — Manifest Format

**Version:** 0.1.1-draft  
**Status:** Draft Specification  
**License:** CC0 1.0 Universal (Public Domain)  
**Companion to:** SCOP v0.1.0-draft

---

## Abstract

SCOP-M defines a declarative file format for describing a SCOP-conforming CLI application. A single `scop.toml` file captures every room, command, parameter type, and output schema in one place. It is the static equivalent of calling `--help`, `--status`, and `--list` on every room simultaneously. GUI renderers consume it to scaffold a complete application shell without invoking the CLI; the SCOP NDJSON stream supplies the live data at runtime.

---

## Status of This Document

Draft specification, published for review and comment. The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY", and "OPTIONAL" are interpreted as described in RFC 2119.

---

## 1. Introduction

SCOP defines how a CLI application emits structured output at runtime. SCOP-M defines how the same application declares its structure statically. The two are complementary:

```text
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

---

## 4. Schema

### 4.1 `[app]` — Application metadata

REQUIRED. Appears exactly once.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | ✓ | Application name; used as the root room title |
| `version` | string | ✓ | Semver string |
| `description` | string | | Short description; used as the root room subtitle |
| `scop_version` | string | | SCOP spec version this manifest targets (e.g. `"0.1.0"`) |

```toml
[app]
name         = "scop"
version      = "0.1.0"
description  = "File and directory snapshotter"
scop_version = "0.1.0"
```

---

### 4.2 `[[room]]` — Page definition

OPTIONAL array. Each entry defines one room. The root room has `id = ""`.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | ✓ | Room path string matching SCOP §6 derivation. Use `""` for root |
| `title` | string | ✓ | Maps to `PAGE_BEGIN.title` |
| `subtitle` | string | | Maps to `PAGE_BEGIN.subtitle` |
| `icon` | string | | GitHub gemoji code (`:name:`). Maps to `PAGE_BEGIN.icon` |

```toml
[[room]]
id       = ""
title    = "scop"
subtitle = "File and directory snapshotter"
icon     = ":package:"

[[room]]
id       = "snapshot"
title    = "Snapshots"
subtitle = "Manage and compare snapshots"
icon     = ":camera_with_flash:"
```

---

### 4.3 `[[room.stat]]` — Status output schema

OPTIONAL array within a `[[room]]`. Declares the `SCALAR_SET` events emitted by `--status` for this room.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | ✓ | Maps to `SCALAR_SET.id` |
| `label` | string | ✓ | Maps to `SCALAR_SET.label` |
| `type` | string | ✓ | One of the types defined in §5 |
| `unit` | string | | Maps to `SCALAR_SET.unit` |

```toml
[[room]]
id = "snapshot"

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

### 4.4 `[room.list]` — List output schema

OPTIONAL table within a `[[room]]`. Declares the `TABLE_DECLARE.schema` emitted by `--list` for this room.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `schema` | string[] | ✓ | Ordered column names. Maps to `TABLE_DECLARE.schema` |
| `display_hint` | string | | Advisory rendering hint: `"table"`, `"chart"`, `"cards"` |

```toml
[[room]]
id = "snapshot"

  [room.list]
  schema       = ["name", "files", "size", "date"]
  display_hint = "table"
```

---

### 4.5 `[[room.command]]` — Command definition

OPTIONAL array within a `[[room]]`. Each entry declares one available command.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | ✓ | CLI token (e.g. `"snap"`, `"--list"`) |
| `description` | string | ✓ | Maps to `LIST_APPEND.value.description` in `--help` output |
| `navigates` | string | | Room `id` this command navigates to. Omit if it stays in the current room |

```toml
[[room]]
id = ""

  [[room.command]]
  name        = "snap"
  description = "Take a snapshot of a directory"
  navigates   = "snapshot"

  [[room.command]]
  name        = "diff"
  description = "Compare two snapshots"
  navigates   = "snapshot"
```

---

### 4.6 `[[room.command.param]]` — Parameter definition

OPTIONAL array within a `[[room.command]]`. Each entry declares one typed input.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | ✓ | Flag name (e.g. `"--path"`) or positional name (e.g. `"target"`) |
| `type` | string | ✓ | One of the types defined in §5 |
| `short` | string | | Single-character short flag (e.g. `"-p"`) |
| `description` | string | | Human-readable description of this parameter |
| `required` | boolean | | Default: `false` for flags, `true` for positional args |
| `default` | any | | Default value; type must match `type` |
| `pattern` | string | | Regex validation string. Valid for `string` and `path` types |
| `choices` | string[] | | Valid values. Required when `type = "choice"` |
| `min` | number | | Minimum value. Valid for `number` type |
| `max` | number | | Maximum value. Valid for `number` type |
| `format` | string | | Format hint. Valid for `datetime` and `duration` types |
| `min_length` | number | | Minimum length. Valid for `string` type |
| `max_length` | number | | Maximum length. Valid for `string` type |

```toml
[[room]]
id = "snapshot"

  [[room.command]]
  name        = "snap"
  description = "Take a new snapshot"

    [[room.command.param]]
    name     = "--path"
    short    = "-p"
    type     = "path"
    pattern  = "^/[^\\0]*$"
    required = false
    default  = "."

    [[room.command.param]]
    name     = "--date"
    short    = "-d"
    type     = "datetime"
    format   = "ISO 8601"
    required = false

    [[room.command.param]]
    name     = "--format"
    type     = "choice"
    choices  = ["json", "tar", "zip"]
    required = false
    default  = "json"

    [[room.command.param]]
    name     = "--dry-run"
    short    = "-n"
    type     = "boolean"
    required = false

    [[room.command.param]]
    name     = "--recursive"
    short    = "-r"
    type     = "boolean"
    required = false
```

---

## 5. Type System

The following types are built-in. Producers MUST use one of these values for `param.type` and `stat.type`.

| Type | GUI widget hint | Validation fields | JSON serialization |
| --- | --- | --- | --- |
| `string` | text input | `pattern`, `min_length`, `max_length` | JSON string |
| `number` | numeric input | `min`, `max` | JSON number |
| `boolean` | checkbox / toggle | — | JSON boolean |
| `path` | file / dir picker | `pattern` | JSON string |
| `datetime` | date-time picker | `format`, `min`, `max` | JSON string (ISO 8601) |
| `duration` | duration input | `format` | JSON string (ISO 8601, e.g. `"PT1M30S"`) |
| `bytes` | file size display | — | JSON integer (absolute byte count) |
| `choice` | select / dropdown | `choices` | JSON string; MUST be a member of `choices` |

---

## 6. Semantic Equivalence

A SCOP-M manifest MUST be semantically equivalent to the runtime discovery output. Specifically:

| Manifest field | Runtime equivalent |
| --- | --- |
| `room.title`, `room.subtitle`, `room.icon` | `PAGE_BEGIN` fields for that room |
| `room.stat.*` | `SCALAR_SET` events emitted by `ourapp [room] --status` |
| `room.list.schema` | `TABLE_DECLARE.schema` emitted by `ourapp [room] --list` |
| `room.command.name`, `.description` | `LIST_APPEND.value` fields in `ourapp [room] --help` |
| `room.command.param.*` | `LIST_APPEND.value.params` entries (SCOP §8.1 extension) |

A conformance test tool MAY verify equivalence by running the CLI and diffing its `--help` / `--status` / `--list` output against the manifest.

---

## 7. Complete Example

```toml
[app]
name         = "scop"
version      = "0.1.0"
description  = "File and directory snapshotter"
scop_version = "0.1.0"

# ── Root room ────────────────────────────────────────────────────────────────
[[room]]
id       = ""
title    = "scop"
subtitle = "File and directory snapshotter"
icon     = ":package:"

  [[room.command]]
  name        = "snap"
  description = "Take a snapshot of a directory"
  navigates   = "snapshot"

  [[room.command]]
  name        = "diff"
  description = "Compare two snapshots"
  navigates   = "snapshot"

  [[room.command]]
  name        = "status"
  description = "Show current snapshot state"
  navigates   = "snapshot"

  [[room.command]]
  name        = "log"
  description = "List all snapshots"
  navigates   = "snapshot"

  [[room.command]]
  name        = "restore"
  description = "Restore a snapshot"
  navigates   = "snapshot"

# ── Snapshot room ────────────────────────────────────────────────────────────
[[room]]
id       = "snapshot"
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
  name        = "snap"
  description = "Take a new snapshot"

    [[room.command.param]]
    name     = "--path"
    short    = "-p"
    type     = "path"
    pattern  = "^/[^\\0]*$"
    required = false
    default  = "."

    [[room.command.param]]
    name     = "--date"
    short    = "-d"
    type     = "datetime"
    required = false

    [[room.command.param]]
    name     = "--format"
    type     = "choice"
    choices  = ["json", "tar", "zip"]
    required = false
    default  = "json"

    [[room.command.param]]
    name     = "--dry-run"
    short    = "-n"
    type     = "boolean"
    required = false

    [[room.command.param]]
    name     = "--recursive"
    short    = "-r"
    type     = "boolean"
    required = false

  [[room.command]]
  name        = "diff"
  description = "Compare two snapshots"

    [[room.command.param]]
    name        = "a"
    type        = "string"
    required    = true
    description = "First snapshot name"

    [[room.command.param]]
    name        = "b"
    type        = "string"
    required    = true
    description = "Second snapshot name"

  [[room.command]]
  name        = "restore"
  description = "Restore a snapshot"

    [[room.command.param]]
    name     = "name"
    type     = "string"
    required = true

    [[room.command.param]]
    name     = "--dry-run"
    short    = "-n"
    type     = "boolean"
    required = false
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

**A conforming manifest SHOULD:**

7. Include a `[[room]]` entry for every room the application emits events in
8. Declare `[[room.stat]]` entries for every `SCALAR_SET` emitted by `--status`
9. Declare `[room.list]` for every room that emits `TABLE_DECLARE` via `--list`
10. Include `params` on every `[[room.command]]` that accepts arguments
11. Be kept semantically equivalent to runtime `--help` / `--status` / `--list` output (§6)

---

## 9. References

### Normative

- **SCOP v0.1.0-draft** — Structured CLI Output Protocol
- **TOML v1.0** — toml.io
- **RFC 2119** — Key words for use in RFCs. Bradner, S. (1997).
- **GitHub gemoji** — github.com/github/gemoji

### Informative

- **OpenAPI Specification** — openapi.org
- **JSON Schema** — json-schema.org
- **Cargo.toml reference** — doc.rust-lang.org/cargo/reference/manifest.html