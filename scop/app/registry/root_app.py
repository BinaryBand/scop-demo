from __future__ import annotations

from scop.models.bases import BaseApp
from scop.models.messages import MSGID, SyslogMessage
from scop.models.results import StreamingResult

_VERSION = "0.1.0"

_COMMANDS = [
    ("snapshot", "Manage and compare snapshots"),
]


class RootApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        room = None

        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PAGE_BEGIN, room=room,
            msg="=== scop ===",
            data={"title": "scop", "subtitle": "Structured CLI Output Protocol"},
        ))

        if args.get("version"):
            self._emit_version(stream)
        elif args.get("help"):
            self._emit_help(stream)
        else:
            self._emit_version(stream)
            self._emit_help(stream)

        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room=room, msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)

    def _emit_version(self, stream: StreamingResult) -> None:
        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.SCALAR_SET, room=None,
            msg=f"scop {_VERSION}",
            data={"id": "version", "label": "version", "value": _VERSION, "type": "string"},
        ))

    def _emit_help(self, stream: StreamingResult) -> None:
        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.LIST_DECLARE, room=None,
            msg="Commands",
            data={"id": "help", "label": "scop", "ordered": False},
        ))
        for cmd, desc in _COMMANDS:
            stream.emit(SyslogMessage(
                pri=6, msgid=MSGID.LIST_APPEND, room=None,
                msg=f"  {cmd:<12}{desc}",
                data={"id": "help", "item_id": cmd,
                      "value": {"command": cmd, "description": desc}},
            ))
        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.LIST_END, room=None, msg="",
            data={"id": "help"},
        ))
