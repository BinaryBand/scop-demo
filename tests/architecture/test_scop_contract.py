"""Contract tests asserting conformance to docs/SCOP.md.

This file is the single enforcement point for SCOP protocol rules that cannot
be expressed as static analysis rules. Each test cites the SCOP section it
covers so that the spec and the test stay coupled.
"""

import json
from typing import Any, cast

from scop.models.protocol import MSGID
from scop.utils.proc import run_resolved

# §7 — Event Vocabulary: the complete, fixed set of valid MSGIDs.
# Adding a value to MSGID without adding it here is a breaking protocol change.
_SCOP_MSGIDS: frozenset[str] = frozenset({
    # §7.1 PAGE — page frame (every stream MUST begin/end with these)
    "PAGE_BEGIN",
    "PAGE_END",
    # §7.2 PROCESS — running operation lifecycle
    "PROCESS_BEGIN",
    "PROCESS_UPDATE",
    "PROCESS_END",
    "PROCESS_LOG",
    # §7.3 SCALAR — single named value
    "SCALAR_SET",
    "SCALAR_CLEAR",
    # §7.4 LIST — ordered or unordered sequence
    "LIST_DECLARE",
    "LIST_APPEND",
    "LIST_UPDATE",
    "LIST_REMOVE",
    "LIST_END",
    # §7.5 TABLE — relation with named columns
    "TABLE_DECLARE",
    "TABLE_ROW",
    "TABLE_UPDATE",
    "TABLE_END",
})


def test_msgid_enum_matches_scop() -> None:
    """MSGID enum must contain exactly the values defined in SCOP.md §7.

    Any addition or removal is a breaking wire-format change and requires
    updating both this test and the spec.
    """
    assert set(MSGID) == _SCOP_MSGIDS, (
        f"Extra: {set(MSGID) - _SCOP_MSGIDS} | Missing: {_SCOP_MSGIDS - set(MSGID)}"
    )


def _run_cli(*argv: str) -> list[dict[str, object]]:
    proc = run_resolved(
        ["scop", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    events: list[dict[str, object]] = []
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        raw_event = json.loads(line)
        assert isinstance(raw_event, dict), "SCOP line must decode to a JSON object"
        events.append(cast(dict[str, object], raw_event))
    return events


def _help_items(*argv: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for event in _run_cli(*argv):
        if event.get("msgid") != "LIST_APPEND" or event.get("id") != "help":
            continue
        raw_value = event.get("value")
        assert isinstance(raw_value, dict), "help LIST_APPEND value must be an object"
        items.append(cast(dict[str, object], raw_value))
    assert items, f"expected help items from scop {' '.join(argv)}"
    return items


def test_help_items_follow_scop_schema() -> None:
    """SCOP §8.1 help entries use command/description/kind/params schema only."""
    argv_sets = [
        ("--help",),
        ("snapshot", "--help"),
        ("snapshot", "create", "--help"),
        ("snapshot", "diff", "--help"),
    ]
    legacy_keys = {"args", "optional_flags", "arguments", "options", "flags"}

    for argv in argv_sets:
        for item in _help_items(*argv):
            command = item.get("command")
            description = item.get("description")
            kind = item.get("kind", "action")

            assert isinstance(command, str) and command
            assert isinstance(description, str)
            assert kind in {"action", "group"}
            assert legacy_keys.isdisjoint(item.keys())

            if kind == "action":
                params = item.get("params")
                assert isinstance(params, list) and params, (
                    "action help entries must include non-empty params"
                )
                for raw_param in params:
                    assert isinstance(raw_param, dict), "param entry must be an object"
                    param = cast(dict[str, Any], raw_param)
                    name = param.get("name")
                    param_kind = param.get("kind")
                    assert isinstance(name, str) and name
                    assert param_kind in {"flag", "positional"}
