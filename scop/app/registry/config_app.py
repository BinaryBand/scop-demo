from __future__ import annotations

from typing import Any, cast

from scop.adapters.config_adapter import ConfigAdapter
from scop.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.streaming_result import StreamingResult
from scop.services.config_set_service import ConfigSetService
from scop.services.config_show_service import ConfigShowService

_HELP_ITEMS = [
    {
        "item_id": "config get",
        "value": {
            "command": "config get",
            "description": "Show a config value",
            "kind": "action",
            "params": [
                {"name": "key", "kind": "positional", "metavar": "KEY"},
                {"name": "--quiet", "kind": "flag", "short": "-q", "type": "boolean"},
            ],
        },
    },
    {
        "item_id": "config set",
        "value": {
            "command": "config set",
            "description": "Update a config value",
            "kind": "action",
            "params": [
                {"name": "key", "kind": "positional", "metavar": "KEY"},
                {"name": "value", "kind": "positional", "metavar": "VALUE"},
                {"name": "--quiet", "kind": "flag", "short": "-q", "type": "boolean"},
            ],
        },
    },
]


class ConfigApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        action = args.get("action")
        room = "config"

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room=room,
                msg="=== Config ===",
                data={"title": "Config", "subtitle": "Application configuration"},
            )
        )

        port = ConfigAdapter()

        if args.get("help"):
            self._emit_help(stream, room)
        elif action == "get":
            key = args.get("key")
            service: ConfigShowService | ConfigSetService = ConfigShowService(
                port=port, room=room, key=str(key) if key else None
            )
            await service.run(stream)
        elif action == "set":
            raw_key = args.get("key")
            raw_val = args.get("value")
            if not raw_key or not raw_val:
                missing = "key" if not raw_key else "value"
                stream.emit(
                    SyslogMessage(
                        pri=3,
                        msgid=MSGID.PAGE_END,
                        room=room,
                        msg=f"error: {missing} argument is required",
                        data={},
                    )
                )
                stream.resolve(
                    ok=False,
                    data=SyslogMessage(pri=3, msgid=MSGID.PAGE_END, room=room, msg="", data={}),
                )
                return
            service = ConfigSetService(port=port, room=room, key=str(raw_key), value=str(raw_val))
            await service.run(stream)
        else:
            service = ConfigShowService(port=port, room=room)
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
                data={"id": "help", "label": "config", "ordered": False},
            )
        )
        for item in _HELP_ITEMS:
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
                    data={"id": "help", "item_id": item["item_id"], "value": value},
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
