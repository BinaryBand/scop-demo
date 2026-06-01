from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.snapshot_port import SnapshotPort
from scop.ports.streaming_result import StreamingResult


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
                msgid=MSGID.TABLE_DECLARE,
                room=r,
                msg="Snapshots",
                data={
                    "id": "snaps",
                    "label": "Snapshots",
                    "schema": ["name", "files", "size", "date"],
                },
            )
        )
        for snap in snaps:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TABLE_ROW,
                    room=r,
                    msg=f"{snap.name:<12}  {snap.files} files  {snap.size}  {snap.date}",
                    data={
                        "id": "snaps",
                        "row_id": snap.name,
                        "values": {
                            "name": snap.name,
                            "files": snap.files,
                            "size": snap.size,
                            "date": snap.date,
                        },
                    },
                )
            )
        n = len(snaps)
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TABLE_END,
                room=r,
                msg=f"{n} snapshot{'s' if n != 1 else ''}",
                data={"id": "snaps"},
            )
        )
