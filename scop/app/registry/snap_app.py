from __future__ import annotations

from scop.models.bases import BaseApp
from scop.models.messages import MSGID, SyslogMessage
from scop.models.results import StreamingResult


class SnapApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        room = "snapshot"

        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PAGE_BEGIN, room=room,
            msg="=== Snapshot ===",
            data={"title": "Snapshot", "subtitle": "Take and manage snapshots"},
        ))

        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PROCESS_BEGIN, room=room,
            msg="Starting snapshot",
            data={"id": "snap", "label": "Snapshotting"},
        ))

        # TODO: inject and call ports here

        end = SyslogMessage(
            pri=6, msgid=MSGID.PROCESS_END, room=room,
            msg="Snapshot complete",
            data={"id": "snap", "ok": True},
        )
        stream.emit(end)
        stream.emit(SyslogMessage(
            pri=6, msgid=MSGID.PAGE_END, room=room, msg="",
        ))
        stream.resolve(ok=True, data=end)
