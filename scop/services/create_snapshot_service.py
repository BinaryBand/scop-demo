from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.snapshot_port import SnapshotPort
from scop.ports.streaming_result import StreamingResult


class CreateSnapshotService(Service):
    def __init__(self, port: SnapshotPort, room: str, dry_run: bool = False) -> None:
        self._port = port
        self._room = room
        self._dry_run = dry_run

    async def run(self, stream: StreamingResult) -> None:
        r = self._room
        dr = self._dry_run
        suffix = " (dry run)" if dr else ""

        begin: dict = {"id": "snap", "label": f"Snapshotting{suffix}"}
        if dr:
            begin["dry_run"] = True
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PROCESS_BEGIN,
                room=r,
                msg=f"Starting snapshot{suffix}",
                data=begin,
            )
        )

        snap = self._port.create_snapshot(dry_run=dr)

        end: dict = {"id": "snap", "ok": True}
        if dr:
            end["dry_run"] = True
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PROCESS_END,
                room=r,
                msg=f"Snapshot complete{suffix} — {snap.name} ({snap.files} files, {snap.size})",
                data=end,
            )
        )
