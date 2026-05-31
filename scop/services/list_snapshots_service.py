from __future__ import annotations

from typing import TYPE_CHECKING

from scop.models.bases import Service
from scop.models.messages import MSGID, SyslogMessage

if TYPE_CHECKING:
    from scop.models.results import StreamingResult
    from scop.ports.snapshot_port import SnapshotPort


class ListSnapshotsService(Service):
    def __init__(self, port: SnapshotPort, room: str, expand: bool = False) -> None:
        self._port = port
        self._room = room
        self._expand = expand

    async def run(self, stream: StreamingResult) -> None:
        snaps = self._port.list_snapshots(expand=self._expand)
        r = self._room
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_BEGIN,
                room=r,
                msg="Snapshots",
                data={"id": "snaps", "title": "Snapshots"},
            )
        )
        for snap in snaps:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TASK_LOG,
                    room=r,
                    msg=f"{snap.name:<12}  {snap.files} files  {snap.size}  {snap.date}",
                    data={
                        "id": "snaps",
                        "message": f"{snap.name:<12}  {snap.files} files  {snap.size}  {snap.date}",
                    },
                )
            )
        n = len(snaps)
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_END,
                room=r,
                msg=f"{n} snapshot{'s' if n != 1 else ''}",
                data={"id": "snaps", "ok": True},
            )
        )
