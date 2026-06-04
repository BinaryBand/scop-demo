"""Linear UIModel contract tests.

Each function feeds SCOP events into UIModel.ingest and asserts on the
resulting page slots.  No rendering decisions are tested here — those belong
in clig.py.  The model only cares about: pages were created, scalars/lists/
tables landed in the right slots.
"""

from __future__ import annotations

from typing import Any

from scop.ui import UIModel, UIPage

# ── Helpers ───────────────────────────────────────────────────────────────────


def e(**kwargs: Any) -> dict[str, Any]:
    """Build a single event dict."""
    return {"pri": 6, **kwargs}


def feed(*events: dict[str, Any]) -> UIModel:
    m = UIModel()
    m.ingest_many(list(events))
    return m


# ── Page open / close ─────────────────────────────────────────────────────────


def test_page_begin_creates_page() -> None:
    m = feed(e(msgid="PAGE_BEGIN", id="p1", label="Page One"))
    assert "p1" in m.pages
    assert m.pages["p1"].title == "Page One"
    assert m.active_page == "p1"


def test_page_begin_without_label_uses_id_as_title() -> None:
    m = feed(e(msgid="PAGE_BEGIN", id="snapshot"))
    assert m.pages["snapshot"].title == "snapshot"


def test_duplicate_page_begin_is_ignored() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1", label="First"),
        e(msgid="SCALAR_SET", id="x", label="X", value="1"),
        e(msgid="PAGE_BEGIN", id="p1", label="Second"),
    )
    assert m.pages["p1"].title == "First"
    assert "x" in m.pages["p1"].scalars


def test_first_page_begin_sets_active_page() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="a"),
        e(msgid="PAGE_BEGIN", id="b"),
    )
    assert m.active_page == "a"


def test_events_before_any_page_begin_are_dropped() -> None:
    m = feed(e(msgid="SCALAR_SET", id="x", label="X", value="orphan"))
    assert m.current_page() is None


def test_page_end_does_not_wipe_page() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="v", value="42"),
        e(msgid="PAGE_END", id="p1"),
    )
    assert "v" in m.pages["p1"].scalars


def test_second_page_events_fed_alone_yield_only_that_page() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p2"),
        e(msgid="SCALAR_SET", id="new", label="New", value="here"),
        e(msgid="PAGE_END", id="p2"),
    )
    assert len(m.pages) == 1
    assert "new" in m.pages["p2"].scalars


# ── SCALAR_SET ────────────────────────────────────────────────────────────────


def test_scalar_stored_on_active_page() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="ver", label="Version", value="0.1.0"),
    )
    assert "ver" in m.pages["p1"].scalars
    assert m.pages["p1"].scalars["ver"]["value"] == "0.1.0"


def test_scalar_label_and_unit_preserved() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="sz", label="Size", value="1.2", unit="MB"),
    )
    ev = m.pages["p1"].scalars["sz"]
    assert ev["label"] == "Size"
    assert ev["unit"] == "MB"


def test_scalar_overwritten_by_same_id() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="x", value="1"),
        e(msgid="SCALAR_SET", id="x", value="2"),
    )
    assert m.pages["p1"].scalars["x"]["value"] == "2"


# ── LIST_DECLARE / LIST_APPEND ────────────────────────────────────────────────


def test_list_declare_creates_slot() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="LIST_DECLARE", id="cmds", label="Commands"),
        e(msgid="LIST_END", id="cmds"),
    )
    assert "cmds" in m.pages["p1"].lists
    assert m.pages["p1"].lists["cmds"]["declare"]["label"] == "Commands"


def test_list_append_stores_items_in_order() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="LIST_DECLARE", id="cmds", label="Commands"),
        e(msgid="LIST_APPEND", id="cmds", value={"command": "snapshot", "description": "Manage"}),
        e(msgid="LIST_APPEND", id="cmds", value={"command": "config", "description": "Config"}),
        e(msgid="LIST_END", id="cmds"),
    )
    items = m.pages["p1"].lists["cmds"]["items"]
    assert len(items) == 2
    assert items[0]["command"] == "snapshot"
    assert items[1]["command"] == "config"


def test_list_append_with_wrong_id_is_ignored() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="LIST_DECLARE", id="list-a"),
        e(msgid="LIST_APPEND", id="list-b", value={"command": "snapshot"}),
        e(msgid="LIST_END", id="list-a"),
    )
    assert m.pages["p1"].lists["list-a"]["items"] == []


def test_all_command_token_counts_land_in_list() -> None:
    """Single-token and multi-token commands both go into the list — no routing."""
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="LIST_DECLARE", id="acts"),
        e(msgid="LIST_APPEND", id="acts", value={"command": "snapshot", "description": "Nav"}),
        e(
            msgid="LIST_APPEND",
            id="acts",
            value={"command": "snapshot create", "description": "Action"},
        ),
        e(msgid="LIST_END", id="acts"),
    )
    assert len(m.pages["p1"].lists["acts"]["items"]) == 2


def test_list_items_with_params_stored_verbatim() -> None:
    """Params stored as-is; no is_form_param filtering in the model."""
    param = {"name": "path", "kind": "positional", "required": True}
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="LIST_DECLARE", id="acts"),
        e(msgid="LIST_APPEND", id="acts", value={"command": "snap", "params": [param]}),
        e(msgid="LIST_END", id="acts"),
    )
    item = m.pages["p1"].lists["acts"]["items"][0]
    assert item["params"][0]["name"] == "path"


# ── TABLE_DECLARE / TABLE_ROW ─────────────────────────────────────────────────


def test_table_declare_creates_slot() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="TABLE_DECLARE", id="snaps", schema=["id", "date"]),
        e(msgid="TABLE_END", id="snaps"),
    )
    assert "snaps" in m.pages["p1"].tables
    assert m.pages["p1"].tables["snaps"]["declare"]["schema"] == ["id", "date"]


def test_table_rows_appended_in_order() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="TABLE_DECLARE", id="t", schema=["id", "date"]),
        e(msgid="TABLE_ROW", id="t", values={"id": "s1", "date": "2026-01-01"}),
        e(msgid="TABLE_ROW", id="t", values={"id": "s2", "date": "2026-01-02"}),
        e(msgid="TABLE_END", id="t"),
    )
    rows = m.pages["p1"].tables["t"]["rows"]
    assert rows == [{"id": "s1", "date": "2026-01-01"}, {"id": "s2", "date": "2026-01-02"}]


def test_table_row_with_wrong_id_is_ignored() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="TABLE_DECLARE", id="t1", schema=["name"]),
        e(msgid="TABLE_ROW", id="t2", values={"name": "wrong"}),
        e(msgid="TABLE_END", id="t1"),
    )
    assert m.pages["p1"].tables["t1"]["rows"] == []


def test_empty_table_has_no_rows() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="TABLE_DECLARE", id="t", schema=["col"]),
        e(msgid="TABLE_END", id="t"),
    )
    assert m.pages["p1"].tables["t"]["rows"] == []


# ── current_page ──────────────────────────────────────────────────────────────


def test_current_page_returns_active_page() -> None:
    m = feed(
        e(msgid="PAGE_BEGIN", id="p1"),
        e(msgid="SCALAR_SET", id="x", value="1"),
    )
    page = m.current_page()
    assert isinstance(page, UIPage)
    assert page.key == "p1"
    assert "x" in page.scalars


def test_current_page_is_none_with_no_pages() -> None:
    assert UIModel().current_page() is None
