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


class CreateSnapshotService(Service):
    def __init__(self, port: SnapshotPort, room: str, dry_run: bool = False) -> None:
        self._port = port
        self._room = room
        self._dry_run = dry_run

    async def run(self, stream: StreamingResult) -> None:
        r = self._room
        dr = self._dry_run
        suffix = " (dry run)" if dr else ""

        begin: dict = {"id": "snap", "label": "Snapshotting"}
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
