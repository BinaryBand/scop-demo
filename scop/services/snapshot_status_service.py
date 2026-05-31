from __future__ import annotations

from typing import TYPE_CHECKING

from scop.models.bases import Service
from scop.models.messages import MSGID, SyslogMessage

if TYPE_CHECKING:
    from scop.models.results import StreamingResult
    from scop.ports.snapshot_port import SnapshotPort


class SnapshotStatusService(Service):
    def __init__(self, port: SnapshotPort, room: str) -> None:
        self._port = port
        self._room = room

    async def run(self, stream: StreamingResult) -> None:
        stats = self._port.get_stats()
        r = self._room
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_LOG,
                room=r,
                msg=f"Last snapshot: {stats.last_snap or 'never'}",
                data={"id": r, "message": f"Last snapshot: {stats.last_snap or 'never'}"},
            )
        )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_LOG,
                room=r,
                msg=f"Tracked files: {stats.tracked}",
                data={"id": r, "message": f"Tracked files: {stats.tracked}"},
            )
        )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_LOG,
                room=r,
                msg=f"Changed since last snap: {stats.changed}",
                data={"id": r, "message": f"Changed since last snap: {stats.changed}"},
            )
        )
