from __future__ import annotations

from scop.app.bases import BaseApp
from scop.app.stream import StreamingResult
from scop.models.protocol import MSGID, SyslogMessage


class LogApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room="log",
                msg="=== Log ===",
                data={"title": "Log", "subtitle": "List all snapshots"},
            )
        )
        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room="log", msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)
