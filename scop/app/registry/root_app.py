# app/registry/root_app.py
from __future__ import annotations

from scop.app.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.stream import IStream

_VERSION = "0.1.0"


class RootApp(BaseApp):
    def __init__(self, commands: dict[str, str]) -> None:
        # commands: {name: description} — injected by dispatcher.default()
        self._commands = commands

    async def run(self, args: dict, stream: IStream) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room=None,
                msg="=== scop ===",
                data={"title": "scop", "subtitle": "Structured CLI Output Protocol"},
            )
        )
        if args.get("version"):
            self._emit_version(stream)
        elif args.get("help"):
            self._emit_help(stream)
        else:
            self._emit_version(stream)
            self._emit_help(stream)
        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room=None, msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)

    def _emit_version(self, stream: IStream) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.SCALAR_SET,
                room=None,
                msg=f"scop {_VERSION}",
                data={"id": "version", "label": "version", "value": _VERSION, "type": "string"},
            )
        )

    def _emit_help(self, stream: IStream) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_DECLARE,
                room=None,
                msg="Commands",
                data={"id": "help", "label": "scop", "ordered": False},
            )
        )
        for cmd, desc in self._commands.items():
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.LIST_APPEND,
                    room=None,
                    msg=f"  {cmd:<12}{desc}",
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
                room=None,
                msg="",
                data={"id": "help"},
            )
        )
