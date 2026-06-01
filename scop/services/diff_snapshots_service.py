from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.snapshot_port import SnapshotPort
from scop.ports.stream_port import StreamPort


class DiffSnapshotsService(Service):
    def __init__(
        self,
        port: SnapshotPort,
        room: str,
        from_snap: str | None = None,
        to_snap: str | None = None,
    ) -> None:
        self._port = port
        self._room = room
        self._from = from_snap
        self._to = to_snap

    async def run(self, stream: StreamPort) -> None:
        records = self._port.diff_snapshots(self._from, self._to)
        r = self._room
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TABLE_DECLARE,
                room=r,
                msg="Diff",
                data={"id": "diff", "label": "Diff", "schema": ["path", "status"]},
            )
        )
        for rec in records:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TABLE_ROW,
                    room=r,
                    msg=f"{rec.status:<10}  {rec.path}",
                    data={
                        "id": "diff",
                        "row_id": rec.path,
                        "values": {"path": rec.path, "status": rec.status},
                    },
                )
            )
        n = len(records)
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TABLE_END,
                room=r,
                msg=f"{n} change{'s' if n != 1 else ''}",
                data={"id": "diff"},
            )
        )
