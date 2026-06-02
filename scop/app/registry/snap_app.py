from __future__ import annotations

from typing import Any, cast

from scop.adapters.config_adapter import ConfigAdapter
from scop.adapters.snapshot_adapter import SnapshotAdapter
from scop.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.streaming_result import StreamingResult
from scop.services.create_snapshot_service import CreateSnapshotService
from scop.services.diff_snapshots_service import DiffSnapshotsService
from scop.services.list_snapshots_service import ListSnapshotsService
from scop.services.restore_snapshot_service import RestoreSnapshotService
from scop.services.snapshot_status_service import SnapshotStatusService

_ROOT_HELP_ITEMS = [
    {
        "item_id": "snapshot create",
        "value": {
            "command": "snapshot create",
            "description": "Take a new snapshot",
            "kind": "action",
            "params": [
                {"name": "--dry-run", "kind": "flag", "short": "-n", "type": "boolean"},
                {
                    "name": "--force",
                    "kind": "flag",
                    "short": "-f",
                    "type": "boolean",
                },
                {
                    "name": "--output",
                    "kind": "flag",
                    "short": "-o",
                    "metavar": "FILE",
                },
                {
                    "name": "--quiet",
                    "kind": "flag",
                    "short": "-q",
                    "type": "boolean",
                },
                {
                    "name": "--recursive",
                    "kind": "flag",
                    "short": "-r",
                    "type": "boolean",
                },
                {
                    "name": "--verbose",
                    "kind": "flag",
                    "short": "-v",
                    "type": "boolean",
                },
            ],
        },
    },
    {
        "item_id": "snapshot restore",
        "value": {
            "command": "snapshot restore",
            "description": "Restore a snapshot to a directory",
            "kind": "action",
            "params": [
                {
                    "name": "name",
                    "kind": "positional",
                    "metavar": "SNAPSHOT_ID",
                    "select_from": "snapshot --list --all",
                },
                {
                    "name": "dest",
                    "kind": "positional",
                    "metavar": "OUTPUT_DIR",
                    "input_type": "path",
                    "required": False,
                },
                {"name": "--quiet", "kind": "flag", "short": "-q", "type": "boolean"},
                {"name": "--verbose", "kind": "flag", "short": "-v", "type": "boolean"},
            ],
        },
    },
    {
        "item_id": "snapshot diff",
        "value": {
            "command": "snapshot diff",
            "description": "Compare two snapshots",
            "kind": "action",
            "params": [
                {
                    "name": "--from",
                    "kind": "flag",
                    "metavar": "SNAPSHOT_ID",
                    "required": True,
                    "select_from": "snapshot --list --all",
                },
                {
                    "name": "--to",
                    "kind": "flag",
                    "metavar": "SNAPSHOT_ID",
                    "required": True,
                    "select_from": "snapshot --list --all",
                },
                {
                    "name": "--output",
                    "kind": "flag",
                    "short": "-o",
                    "metavar": "FILE",
                },
                {
                    "name": "--quiet",
                    "kind": "flag",
                    "short": "-q",
                    "type": "boolean",
                },
                {
                    "name": "--verbose",
                    "kind": "flag",
                    "short": "-v",
                    "type": "boolean",
                },
            ],
        },
    },
    {
        "item_id": "snapshot --list",
        "value": {
            "command": "snapshot --list",
            "description": "List all snapshots",
            "kind": "action",
            "params": [
                {
                    "name": "--all",
                    "kind": "flag",
                    "short": "-a",
                    "type": "boolean",
                },
                {
                    "name": "--output",
                    "kind": "flag",
                    "short": "-o",
                    "metavar": "FILE",
                },
                {
                    "name": "--quiet",
                    "kind": "flag",
                    "short": "-q",
                    "type": "boolean",
                },
                {
                    "name": "--verbose",
                    "kind": "flag",
                    "short": "-v",
                    "type": "boolean",
                },
            ],
        },
    },
    {
        "item_id": "snapshot --status",
        "value": {
            "command": "snapshot --status",
            "description": "Show snapshot stats",
            "kind": "action",
            "params": [
                {
                    "name": "--output",
                    "kind": "flag",
                    "short": "-o",
                    "metavar": "FILE",
                },
                {
                    "name": "--quiet",
                    "kind": "flag",
                    "short": "-q",
                    "type": "boolean",
                },
                {
                    "name": "--verbose",
                    "kind": "flag",
                    "short": "-v",
                    "type": "boolean",
                },
            ],
        },
    },
]

_CREATE_HELP_ITEMS = [
    {
        "item_id": "snapshot create",
        "value": {
            "command": "snapshot create",
            "description": "Take a new snapshot",
            "kind": "action",
            "params": [
                {"name": "--dry-run", "kind": "flag", "short": "-n", "type": "boolean"},
                {
                    "name": "--force",
                    "kind": "flag",
                    "short": "-f",
                    "type": "boolean",
                },
                {
                    "name": "--help",
                    "kind": "flag",
                    "short": "-h",
                    "type": "boolean",
                },
                {
                    "name": "--output",
                    "kind": "flag",
                    "short": "-o",
                    "metavar": "FILE",
                },
                {
                    "name": "--quiet",
                    "kind": "flag",
                    "short": "-q",
                    "type": "boolean",
                },
                {
                    "name": "--recursive",
                    "kind": "flag",
                    "short": "-r",
                    "type": "boolean",
                },
                {
                    "name": "--verbose",
                    "kind": "flag",
                    "short": "-v",
                    "type": "boolean",
                },
            ],
        },
    }
]

_DIFF_HELP_ITEMS = [
    {
        "item_id": "snapshot diff",
        "value": {
            "command": "snapshot diff",
            "description": "Compare two snapshots",
            "kind": "action",
            "params": [
                {
                    "name": "--from",
                    "kind": "flag",
                    "metavar": "SNAPSHOT_ID",
                    "required": True,
                    "select_from": "snapshot --list --all",
                },
                {
                    "name": "--to",
                    "kind": "flag",
                    "metavar": "SNAPSHOT_ID",
                    "required": True,
                    "select_from": "snapshot --list --all",
                },
                {
                    "name": "--help",
                    "kind": "flag",
                    "short": "-h",
                    "type": "boolean",
                },
                {
                    "name": "--output",
                    "kind": "flag",
                    "short": "-o",
                    "metavar": "FILE",
                },
                {
                    "name": "--quiet",
                    "kind": "flag",
                    "short": "-q",
                    "type": "boolean",
                },
                {
                    "name": "--verbose",
                    "kind": "flag",
                    "short": "-v",
                    "type": "boolean",
                },
            ],
        },
    }
]

_RESTORE_HELP_ITEMS = [
    {
        "item_id": "snapshot restore",
        "value": {
            "command": "snapshot restore",
            "description": "Restore a snapshot to a directory",
            "kind": "action",
            "params": [
                {
                    "name": "name",
                    "kind": "positional",
                    "metavar": "SNAPSHOT_ID",
                    "select_from": "snapshot --list --all",
                },
                {
                    "name": "dest",
                    "kind": "positional",
                    "metavar": "OUTPUT_DIR",
                    "input_type": "path",
                    "required": False,
                },
                {"name": "--help", "kind": "flag", "short": "-h", "type": "boolean"},
                {"name": "--quiet", "kind": "flag", "short": "-q", "type": "boolean"},
                {"name": "--verbose", "kind": "flag", "short": "-v", "type": "boolean"},
            ],
        },
    }
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
            self._emit_help(stream, room, action=action)
        elif action == "create":
            service: (
                CreateSnapshotService
                | DiffSnapshotsService
                | ListSnapshotsService
                | RestoreSnapshotService
                | SnapshotStatusService
            )
            raw_path = args.get("path") or ConfigAdapter().load().snapshot.target_dir
            service = CreateSnapshotService(
                port=port,
                room=room,
                path=str(raw_path),
                dry_run=args.get("dry_run", False),
                recursive=args.get("recursive", False),
                force=args.get("force", False),
            )
            await service.run(stream)
        elif action == "restore":
            raw_name = args.get("name")
            raw_output = args.get("dest") or ConfigAdapter().load().snapshot.target_dir
            if not raw_name:
                stream.emit(
                    SyslogMessage(
                        pri=3,
                        msgid=MSGID.PAGE_END,
                        room=room,
                        msg="error: name argument is required",
                        data={},
                    )
                )
                stream.resolve(
                    ok=False,
                    data=SyslogMessage(pri=3, msgid=MSGID.PAGE_END, room=room, msg="", data={}),
                )
                return
            service = RestoreSnapshotService(
                port=port,
                room=room,
                name=str(raw_name),
                output=str(raw_output),
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

    def _emit_help(self, stream: StreamingResult, room: str, *, action: str | None) -> None:
        if action == "create":
            label = "snapshot create"
            items = _CREATE_HELP_ITEMS
        elif action == "restore":
            label = "snapshot restore"
            items = _RESTORE_HELP_ITEMS
        elif action == "diff":
            label = "snapshot diff"
            items = _DIFF_HELP_ITEMS
        else:
            label = "snapshot"
            items = _ROOT_HELP_ITEMS

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_DECLARE,
                room=room,
                msg="Commands",
                data={"id": "help", "label": label, "ordered": False},
            )
        )
        for item in items:
            raw_value = item["value"]
            if not isinstance(raw_value, dict):
                continue
            value = cast(dict[str, Any], raw_value)
            command = value.get("command", "")
            description = value.get("description", "")
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.LIST_APPEND,
                    room=room,
                    msg=f"  {command:<24}{description}",
                    data={
                        "id": "help",
                        "item_id": item["item_id"],
                        "value": value,
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
