from __future__ import annotations

from scop.app.stream import StreamingResult
from scop.framework.bases import BaseApp
from scop.protocol.messages import MSGID, SyslogMessage


class DiffApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room="diff",
                msg="=== Diff ===",
                data={"title": "Diff", "subtitle": "Compare two snapshots"},
            )
        )
        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room="diff", msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)
