"""Linear SCOP-event → PageView contract tests.

Each test function walks a specific event sequence top-to-bottom, feeding
NDJSON lines through parse_ndjson → build_page_view and asserting on the
resulting PageView.  The ordering is intentional: simple cases first,
composite cases last, so failures are easy to pinpoint.

Protocol terms used:
  open_page  = PAGE_BEGIN  (starts a blank slate)
  close_page = PAGE_END    (ends the current page; data is finalised)
"""

from __future__ import annotations

import json
from typing import Any

from scop.clig import (
    ListSection,
    PageView,
    ScalarItem,
    TableSection,
    build_page_view,
)
from scop.ui import parse_ndjson

# ── Helpers ───────────────────────────────────────────────────────────────────


def e(**kwargs: Any) -> str:
    """Serialise one NDJSON event line."""
    return json.dumps({"pri": 6, **kwargs})


def view(*lines: str, is_subpage: bool = False) -> PageView:
    """Parse the given NDJSON lines and return a PageView."""
    return build_page_view(parse_ndjson("\n".join(lines)), is_subpage=is_subpage)


# ── Page open / close ─────────────────────────────────────────────────────────


def test_open_page_alone_is_blank_slate():
    """PAGE_BEGIN with no events produces an entirely empty PageView."""
    v = view(e(msgid="PAGE_BEGIN", id="p1"))
    assert v.ctas == []
    assert v.nodes == []
    assert v.forms == []


def test_close_page_alone_is_blank_slate():
    """PAGE_END with no events produces an entirely empty PageView."""
    v = view(e(msgid="PAGE_END", id="p1"))
    assert v.ctas == []
    assert v.nodes == []
    assert v.forms == []


def test_open_then_close_with_no_data_is_blank():
    """A complete but empty page frame leaves the model blank."""
    v = view(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="PAGE_END", id="p1"),
    )
    assert v.ctas == [] and v.nodes == [] and v.forms == []


def test_second_open_page_starts_fresh():
    """
    build_page_view called on only the second page's events must not contain
    anything from the first page — simulating the close → open wipe.
    """
    page1 = [
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="old", label="Old", value="gone"),
        e(msgid="PAGE_END", id="p1"),
    ]
    page2 = [
        e(msgid="PAGE_BEGIN", id="p2"),
        e(msgid="SCALAR_SET", id="new", label="New", value="here"),
        e(msgid="PAGE_END", id="p2"),
    ]

    # page 2 events alone — fresh slate, only page 2 data
    v = view(*page2)
    assert len(v.nodes) == 1
    assert isinstance(v.nodes[0], ScalarItem)
    assert v.nodes[0].label == "New"

    # page 1 events alone — only page 1 data
    v1 = view(*page1)
    assert len(v1.nodes) == 1
    assert v1.nodes[0].label == "Old"  # ty:ignore[unresolved-attribute]


# ── SCALAR_SET ────────────────────────────────────────────────────────────────


def test_scalar_appears_in_nodes():
    v = view(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="ver", label="Version", value="0.1.0"),
    )
    assert len(v.nodes) == 1
    s = v.nodes[0]
    assert isinstance(s, ScalarItem)
    assert s.label == "Version"
    assert s.value == "0.1.0"
    assert s.unit == ""


def test_scalar_unit_is_preserved():
    v = view(e(msgid="SCALAR_SET", id="sz", label="Size", value="1.2", unit="MB"))
    s = v.nodes[0]
    assert isinstance(s, ScalarItem)
    assert s.unit == "MB"


def test_multiple_scalars_preserve_document_order():
    v = view(
        e(msgid="SCALAR_SET", id="a", label="A", value="1"),
        e(msgid="SCALAR_SET", id="b", label="B", value="2"),
        e(msgid="SCALAR_SET", id="c", label="C", value="3"),
    )
    labels = [n.label for n in v.nodes if isinstance(n, ScalarItem)]
    assert labels == ["A", "B", "C"]


# ── LIST_DECLARE ──────────────────────────────────────────────────────────────


def test_list_declare_produces_list_section():
    """A LIST_DECLARE with single-token commands adds a ListSection to nodes."""
    v = view(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="LIST_DECLARE", id="cmds", label="Commands"),
        e(
            msgid="LIST_APPEND",
            id="cmds",
            value={"command": "snapshot", "description": "Manage snapshots"},
        ),
        e(msgid="LIST_APPEND", id="cmds", value={"command": "config", "description": "App config"}),
        e(msgid="LIST_END", id="cmds"),
    )
    assert len(v.nodes) == 1
    node = v.nodes[0]
    assert isinstance(node, ListSection)
    assert node.label == "Commands"
    assert len(node.items) == 2
    assert node.items[0].label == "Snapshot"
    assert node.items[1].label == "Config"


def test_list_two_token_commands_become_ctas_not_list():
    """Items with 2+ non-flag tokens route to CTAs, not to nodes."""
    v = view(
        e(msgid="LIST_DECLARE", id="acts"),
        e(
            msgid="LIST_APPEND",
            id="acts",
            value={"command": "snapshot create", "description": "Take one"},
        ),
        e(
            msgid="LIST_APPEND",
            id="acts",
            value={"command": "snapshot restore", "description": "Restore"},
        ),
        e(msgid="LIST_END", id="acts"),
    )
    assert len(v.ctas) == 2
    assert v.nodes == []
    assert [a.label for a in v.ctas] == ["Create", "Restore"]


def test_list_items_with_value_params_become_forms():
    """Items with a required positional or flag-with-metavar route to forms."""
    param = {"name": "path", "kind": "positional", "metavar": "PATH", "required": True}
    v = view(
        e(msgid="LIST_DECLARE", id="acts"),
        e(
            msgid="LIST_APPEND",
            id="acts",
            value={
                "command": "snapshot",
                "description": "Snap",
                "params": [param],
            },
        ),
        e(msgid="LIST_END", id="acts"),
    )
    assert len(v.forms) == 1
    assert v.forms[0].label == "Snapshot"
    assert len(v.forms[0].params) == 1
    assert v.forms[0].params[0].name == "path"


def test_list_append_with_wrong_id_is_ignored():
    """LIST_APPEND whose id doesn't match the open LIST_DECLARE is dropped."""
    v = view(
        e(msgid="LIST_DECLARE", id="list-a"),
        e(msgid="LIST_APPEND", id="list-b", value={"command": "snapshot", "description": "x"}),
        e(msgid="LIST_END", id="list-a"),
    )
    assert v.nodes == []


def test_list_subpage_routes_all_items_to_forms():
    """In subpage mode every list item becomes a form regardless of token count."""
    v = view(
        e(msgid="LIST_DECLARE", id="acts"),
        e(msgid="LIST_APPEND", id="acts", value={"command": "snapshot create", "description": "x"}),
        e(msgid="LIST_END", id="acts"),
        is_subpage=True,
    )
    assert len(v.forms) == 1
    assert v.ctas == []


# ── TABLE_DECLARE ─────────────────────────────────────────────────────────────


def test_table_produces_table_section():
    v = view(
        e(msgid="TABLE_DECLARE", id="snaps", schema=["id", "date"]),
        e(msgid="TABLE_ROW", id="snaps", values={"id": "s1", "date": "2026-01-01"}),
        e(msgid="TABLE_ROW", id="snaps", values={"id": "s2", "date": "2026-01-02"}),
        e(msgid="TABLE_END", id="snaps"),
    )
    assert len(v.nodes) == 1
    t = v.nodes[0]
    assert isinstance(t, TableSection)
    assert t.schema == ["id", "date"]
    assert t.rows == [
        {"id": "s1", "date": "2026-01-01"},
        {"id": "s2", "date": "2026-01-02"},
    ]


def test_table_row_with_wrong_id_is_ignored():
    v = view(
        e(msgid="TABLE_DECLARE", id="t1", schema=["name"]),
        e(msgid="TABLE_ROW", id="t2", values={"name": "wrong"}),
        e(msgid="TABLE_END", id="t1"),
    )
    t = v.nodes[0]
    assert isinstance(t, TableSection)
    assert t.rows == []


def test_empty_table_still_produces_table_section():
    v = view(
        e(msgid="TABLE_DECLARE", id="t", schema=["col"]),
        e(msgid="TABLE_END", id="t"),
    )
    assert isinstance(v.nodes[0], TableSection)
    assert v.nodes[0].rows == []


# ── Document ordering ─────────────────────────────────────────────────────────


def test_pending_scalars_flush_before_table():
    """Scalars buffered before a TABLE_DECLARE must appear before the table."""
    v = view(
        e(msgid="SCALAR_SET", id="x", label="X", value="1"),
        e(msgid="TABLE_DECLARE", id="t", schema=["col"]),
        e(msgid="TABLE_END", id="t"),
    )
    assert isinstance(v.nodes[0], ScalarItem)
    assert isinstance(v.nodes[1], TableSection)


def test_pending_scalars_flush_before_list():
    """Scalars buffered before a LIST_DECLARE must appear before the list."""
    v = view(
        e(msgid="SCALAR_SET", id="x", label="X", value="1"),
        e(msgid="LIST_DECLARE", id="l", label="Items"),
        e(msgid="LIST_APPEND", id="l", value={"command": "snapshot", "description": "x"}),
        e(msgid="LIST_END", id="l"),
    )
    assert isinstance(v.nodes[0], ScalarItem)
    assert isinstance(v.nodes[1], ListSection)


def test_scalar_table_list_interleaved_preserves_order():
    """Mixed event types land in nodes in the order they were emitted."""
    v = view(
        e(msgid="SCALAR_SET", id="a", label="A", value="1"),
        e(msgid="TABLE_DECLARE", id="t", schema=["col"]),
        e(msgid="TABLE_END", id="t"),
        e(msgid="SCALAR_SET", id="b", label="B", value="2"),
        e(msgid="LIST_DECLARE", id="l", label="L"),
        e(msgid="LIST_APPEND", id="l", value={"command": "snapshot", "description": "x"}),
        e(msgid="LIST_END", id="l"),
    )
    assert isinstance(v.nodes[0], ScalarItem)  # A
    assert isinstance(v.nodes[1], TableSection)
    assert isinstance(v.nodes[2], ScalarItem)  # B flushed before list
    assert isinstance(v.nodes[3], ListSection)
