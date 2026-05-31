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
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_BEGIN,
                room=None,
                msg="=== scop ===",
                data={"id": "scop", "title": "scop"},
            )
        )

        if args.get("version"):
            self._emit_version(stream)
        elif args.get("help"):
            self._emit_help(stream)
        else:
            self._emit_version(stream)
            self._emit_help(stream)

        end = SyslogMessage(
            pri=6,
            msgid=MSGID.TASK_END,
            room=None,
            msg="",
            data={"id": "scop", "ok": True},
        )
        stream.emit(end)
        stream.resolve(ok=True, data=end)

    def _emit_version(self, stream: StreamingResult) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_LOG,
                room=None,
                msg=f"scop {_VERSION}",
                data={"id": "scop", "message": f"scop {_VERSION}"},
            )
        )

    def _emit_help(self, stream: StreamingResult) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_BEGIN,
                room=None,
                msg="Commands",
                data={"id": "help", "title": "scop"},
            )
        )
        for cmd, desc in _COMMANDS:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TASK_LOG,
                    room=None,
                    msg=f"  {cmd:<12}{desc}",
                    data={"id": "help", "message": f"{cmd}: {desc}"},
                )
            )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TASK_END,
                room=None,
                msg="",
                data={"id": "help", "ok": True},
            )
        )
