from __future__ import annotations

from scop.app.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.stream import IStream


class DiffApp(BaseApp):
    async def run(self, args: dict, stream: IStream) -> None:
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
