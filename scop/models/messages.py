from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MSGID(StrEnum):
    TASK_BEGIN = "TASK_BEGIN"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_END = "TASK_END"
    TASK_LOG = "TASK_LOG"


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
