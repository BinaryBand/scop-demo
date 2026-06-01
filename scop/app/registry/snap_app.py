from __future__ import annotations

from scop.adapters.snapshot_adapter import SnapshotAdapter
from scop.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.streaming_result import StreamingResult
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
        base_room_raw = args.get("_room")
        base_room = base_room_raw if isinstance(base_room_raw, str) else "snapshot"
        room = f"{base_room}/diff" if action == "diff" and base_room else base_room
        title = "Diff" if action == "diff" else "Snapshots"
        subtitle = "Compare snapshots" if action == "diff" else "Manage and compare snapshots"

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room=room,
                msg=f"=== {title} ===",
                data={"title": title, "subtitle": subtitle},
            )
        )

        port = SnapshotAdapter()

        if args.get("help"):
            self._emit_help(stream, room)
        elif action == "create":
            service: (
                CreateSnapshotService
                | DiffSnapshotsService
                | ListSnapshotsService
                | SnapshotStatusService
            )
            service = CreateSnapshotService(
                port=port,
                room=room,
                dry_run=args.get("dry_run", False),
                recursive=args.get("recursive", False),
                force=args.get("force", False),
            )
            await service.run(stream)
        elif action == "diff":
            service = DiffSnapshotsService(
                port=port,
                room=room,
                from_snap=args.get("from_snap"),
                to_snap=args.get("to_snap"),
            )
            await service.run(stream)
        elif args.get("list"):
            service = ListSnapshotsService(port=port, room=room, expand=args.get("all", False))
            await service.run(stream)
        else:
            service = SnapshotStatusService(port=port, room=room)
            await service.run(stream)

        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room=room, msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)

    def _emit_help(self, stream: StreamingResult, room: str) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_DECLARE,
                room=room,
                msg="Commands",
                data={"id": "help", "label": "snapshot", "ordered": False},
            )
        )
        for cmd, desc in _COMMANDS:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.LIST_APPEND,
                    room=room,
                    msg=f"  {cmd:<24}{desc}",
                    data={
                        "id": "help",
                        "item_id": cmd,
                        "value": {"command": cmd, "description": desc},
                    },
                )
            )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_END,
                room=room,
                msg="",
                data={"id": "help"},
            )
        )
