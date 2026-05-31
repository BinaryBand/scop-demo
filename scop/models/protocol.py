from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MSGID(StrEnum):
    # PAGE family — §7.1
    PAGE_BEGIN = "PAGE_BEGIN"
    PAGE_END = "PAGE_END"
    # PROCESS family — §7.2
    PROCESS_BEGIN = "PROCESS_BEGIN"
    PROCESS_UPDATE = "PROCESS_UPDATE"
    PROCESS_END = "PROCESS_END"
    PROCESS_LOG = "PROCESS_LOG"
    # SCALAR family — §7.3
    SCALAR_SET = "SCALAR_SET"
    SCALAR_CLEAR = "SCALAR_CLEAR"
    # LIST family — §7.4
    LIST_DECLARE = "LIST_DECLARE"
    LIST_APPEND = "LIST_APPEND"
    LIST_UPDATE = "LIST_UPDATE"
    LIST_REMOVE = "LIST_REMOVE"
    LIST_END = "LIST_END"
    # TABLE family — §7.5
    TABLE_DECLARE = "TABLE_DECLARE"
    TABLE_ROW = "TABLE_ROW"
    TABLE_UPDATE = "TABLE_UPDATE"
    TABLE_END = "TABLE_END"


@dataclass(frozen=True)
class SyslogMessage:
    """RFC 5424 event envelope serialised as NDJSON."""

    pri: int
    msgid: MSGID
    room: str | None
    msg: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_ndjson(self) -> str:
        payload: dict[str, Any] = {
            "pri": self.pri,
            "msgid": self.msgid,
            "room": self.room,
            "msg": self.msg,
        }
        payload.update(self.data)
        return json.dumps(payload)


@dataclass(frozen=True)
class ResolvedResult:
    ok: bool
    data: SyslogMessage  # must be a PAGE_END message (SCOP §11)
