# scop

**scop** is a reference implementation of the [Structured CLI Output Protocol (SCOP)](docs/SCOP.md). Every command emits NDJSON events that are human-readable as plain text and automatically translatable to a GUI without any application-specific renderer code.

---

## Installation

```sh
pip install -e ".[dev]"
```

---

## Commands

### Root

```sh
scop                  # version + command list
scop --version        # version only
scop --help           # command list only
```

### `snapshot`

```sh
scop snapshot                        # snapshot stats (last snap, tracked files, changes)
scop snapshot --status               # same as above
scop snapshot --list                 # list all snapshots as a table
scop snapshot --list --all           # include older snapshots
scop snapshot --help                 # available snapshot commands
```

### `snapshot create`

```sh
scop snapshot create                 # take a new snapshot
scop snapshot create --dry-run       # preview without writing
scop snapshot create --verbose       # include debug-level log events
```

### `snapshot diff`

```sh
scop snapshot diff                   # diff the two most recent snapshots
scop snapshot diff --from snap-001   # diff from a named snapshot
scop snapshot diff --to   snap-003   # diff to a named snapshot
```

---

## TUI how-to

`scop-tui` renders SCOP NDJSON streams using a Textual interface.

### Interactive mode (recommended)

Use `--cmd` so the TUI keeps keyboard input available:

```sh
scop-tui --cmd "scop snapshot --list"
```

### File-backed interactive mode

```sh
scop snapshot --list > events.ndjson
scop-tui --from events.ndjson
```

### Pipe mode (render-and-exit)

```sh
scop snapshot --list | scop-tui
```

In pipe mode, stdin carries the finite event stream, so the UI exits when EOF is reached.

### Key controls

- `q`: quit
- `Tab` / `Shift+Tab`: move focus between panes
- `Up` / `Down` or `j` / `k`: move table cursor

---

## Output format

Every invocation emits NDJSON — one JSON object per line — wrapped in a `PAGE_BEGIN` / `PAGE_END` pair:

```sh
scop snapshot --list
```

```json
{"pri": 6, "msgid": "PAGE_BEGIN", "room": "snapshot", "title": "Snapshots", "msg": "=== Snapshots ==="}
{"pri": 6, "msgid": "TABLE_DECLARE", "room": "snapshot", "id": "snaps", "schema": ["name", "files", "size", "date"], "msg": "Snapshots"}
{"pri": 6, "msgid": "TABLE_ROW", "room": "snapshot", "id": "snaps", "row_id": "snap-001", "values": {"name": "snap-001", "files": 42, "size": "1.2 MB", "date": "2026-05-30"}, "msg": "snap-001      42 files  1.2 MB  2026-05-30"}
{"pri": 6, "msgid": "TABLE_END", "room": "snapshot", "id": "snaps", "msg": "2 snapshots"}
{"pri": 6, "msgid": "PAGE_END", "room": "snapshot", "msg": ""}
```

Plain `cat` of stdout is always readable — the `msg` field is a complete human-readable line on every event.

---

## GUI (POC)

Run the plain localhost GUI:

```sh
scop-gui
```

The app starts a local web server at `http://127.0.0.1:8765/` and opens your browser automatically.

- The page is intentionally minimal and protocol-focused.
- Actions are auto-generated from SCOP `--help` events (`LIST_APPEND.value.command`).
- Clicking an action runs the corresponding SCOP command and renders the resulting page info.

Optional environment variables:

```sh
SCOP_GUI_HOST=127.0.0.1   # default host
SCOP_GUI_PORT=8765        # default port
SCOP_GUI_OPEN=0           # disable auto-open browser
```

---

## Mode flags

These work on any command:

| Flag | Short | Effect |
| --- | --- | --- |
| `--quiet` | `-q` | Suppress `PROCESS_LOG` and informational events |
| `--verbose` | `-v` | Include `DEBUG`-level log events |
| `--all` | `-a` | Expand `--list` / `--status` scope |

---

## Development

```sh
# Lint + format
ruff check scop
ruff format scop

# Type check
ty check

# Import layer contract
lint-imports

# Structural rules
ast-grep scan --error
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the dependency graph and toolchain rules, and [docs/SCOP.md](docs/SCOP.md) for the full protocol specification.
