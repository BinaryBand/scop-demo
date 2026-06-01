from __future__ import annotations

from scop.app.bases import BaseApp
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.stream_port import StreamPort


class DiffApp(BaseApp):
    async def run(self, args: dict, stream: StreamPort) -> None:
        room = args.get("_room")
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room=room,
                msg="=== Diff ===",
                data={"title": "Diff", "subtitle": "Compare two snapshots"},
            )
        )
        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room=room, msg="")
        stream.emit(end)
        stream.resolve(ok=True, data=end)
