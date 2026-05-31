"""Contract tests asserting conformance to docs/SCOP.md.

This file is the single enforcement point for SCOP protocol rules that cannot
be expressed as static analysis rules. Each test cites the SCOP section it
covers so that the spec and the test stay coupled.
"""

from scop.models.protocol import MSGID

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


def test_msgid_enum_matches_scop_spec() -> None:
    """MSGID enum must contain exactly the values defined in SCOP.md §7.

    Any addition or removal is a breaking wire-format change and requires
    updating both this test and the spec.
    """
    assert set(MSGID) == _SCOP_MSGIDS, (
        f"Extra: {set(MSGID) - _SCOP_MSGIDS} | Missing: {_SCOP_MSGIDS - set(MSGID)}"
    )
