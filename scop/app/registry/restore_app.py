from __future__ import annotations

from scop.app.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.stream import IStream


class RestoreApp(BaseApp):
    async def run(self, args: dict, stream: IStream) -> None:
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room="restore",
                msg="=== Restore ===",
                data={"title": "Restore", "subtitle": "Restore a snapshot"},
            )
        )
        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room="restore", msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)
