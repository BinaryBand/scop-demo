from __future__ import annotations

from scop.adapters.snapshot_adapter import SnapshotAdapter
from scop.models.bases import BaseApp
from scop.models.messages import MSGID, SyslogMessage
from scop.models.results import StreamingResult
from scop.services.create_snapshot_service import CreateSnapshotService
from scop.services.diff_snapshots_service import DiffSnapshotsService
from scop.services.list_snapshots_service import ListSnapshotsService
from scop.services.snapshot_status_service import SnapshotStatusService

_COMMANDS = [
    ("snapshot create", "Take a new snapshot"),
    ("snapshot diff", "Compare two snapshots"),
    ("snapshot --list", "List all snapshots"),
    ("snapshot --status", "Show snapshot stats"),
]


class SnapApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        action = args.get("action")
        task_id = "snapshot/diff" if action == "diff" else "snapshot"
        title = "Diff" if action == "diff" else "Snapshots"

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_BEGIN,
                room=task_id,
                msg=f"=== {title} ===",
                data={"id": task_id, "title": title},
            )
        )

        port = SnapshotAdapter()

        if args.get("help"):
            self._emit_help(stream, task_id)
        elif action == "create":
            service: (
                CreateSnapshotService
                | DiffSnapshotsService
                | ListSnapshotsService
                | SnapshotStatusService
            )
            service = CreateSnapshotService(
                port=port, room=task_id, dry_run=args.get("dry_run", False)
            )
            await service.run(stream)
        elif action == "diff":
            service = DiffSnapshotsService(
                port=port,
                room=task_id,
                from_snap=args.get("from_snap"),
                to_snap=args.get("to_snap"),
            )
            await service.run(stream)
        elif args.get("list"):
            service = ListSnapshotsService(port=port, room=task_id, expand=args.get("all", False))
            await service.run(stream)
        else:
            service = SnapshotStatusService(port=port, room=task_id)
            await service.run(stream)

        end = SyslogMessage(
            pri=6,
            msgid=MSGID.TASK_END,
            room=task_id,
            msg="",
            data={"id": task_id, "ok": True},
        )
        stream.emit(end)
        stream.resolve(ok=True, data=end)

    def _emit_help(self, stream: StreamingResult, task_id: str) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_BEGIN,
                room=task_id,
                msg="Commands",
                data={"id": "help", "title": "snapshot"},
            )
        )
        for cmd, desc in _COMMANDS:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TASK_LOG,
                    room=task_id,
                    msg=f"  {cmd:<24}{desc}",
                    data={"id": "help", "message": f"{cmd}: {desc}"},
                )
            )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_END,
                room=task_id,
                msg="",
                data={"id": "help", "ok": True},
            )
        )
