from __future__ import annotations

from scop.models.bases import BaseApp
from scop.models.messages import MSGID, SyslogMessage
from scop.models.results import StreamingResult


class DiffApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        room = "diff"

        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PAGE_BEGIN, room=room,
            msg="=== Diff ===",
            data={"title": "Diff", "subtitle": "Compare two snapshots"},
        ))

        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PROCESS_BEGIN, room=room,
            msg="Starting diff",
            data={"id": "diff", "label": "Diffing"},
        ))

        # TODO: inject and call ports here

        end = SyslogMessage(
            pri=6, msgid=MSGID.PROCESS_END, room=room,
            msg="Diff complete",
            data={"id": "diff", "ok": True},
        )
        stream.emit(end)
        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PAGE_END, room=room, msg="",
        ))
        stream.resolve(ok=True, data=end)
