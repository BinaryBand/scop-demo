from __future__ import annotations

from typing import TYPE_CHECKING

from scop.models.bases import Service
from scop.models.messages import MSGID, SyslogMessage

if TYPE_CHECKING:
    from scop.models.results import StreamingResult
    from scop.ports.snapshot_port import SnapshotPort


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

    async def run(self, stream: StreamingResult) -> None:
        records = self._port.diff_snapshots(self._from, self._to)
        r = self._room
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_BEGIN,
                room=r,
                msg="Diff",
                data={"id": "diff", "title": "Diff"},
            )
        )
        for rec in records:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TASK_LOG,
                    room=r,
                    msg=f"{rec.status:<10}  {rec.path}",
                    data={"id": "diff", "message": f"{rec.status:<10}  {rec.path}"},
                )
            )
        n = len(records)
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_END,
                room=r,
                msg=f"{n} change{'s' if n != 1 else ''}",
                data={"id": "diff", "ok": True},
            )
        )
