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
                msgid=MSGID.SCALAR_SET,
                room=r,
                msg=f"Last snapshot: {stats.last_snap or 'never'}",
                data={
                    "id": "last_snap",
                    "label": "Last snapshot",
                    "value": stats.last_snap or "never",
                    "type": "string",
                },
            )
        )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.SCALAR_SET,
                room=r,
                msg=f"Tracked files: {stats.tracked}",
                data={
                    "id": "tracked",
                    "label": "Tracked files",
                    "value": stats.tracked,
                    "type": "number",
                },
            )
        )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.SCALAR_SET,
                room=r,
                msg=f"Changed since last snap: {stats.changed}",
                data={
                    "id": "changed",
                    "label": "Changed since last snap",
                    "value": stats.changed,
                    "type": "number",
                },
            )
        )
