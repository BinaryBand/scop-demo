from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.snapshot_port import SnapshotPort
from scop.ports.streaming_result import StreamingResult


class RestoreSnapshotService(Service):
    def __init__(self, port: SnapshotPort, room: str, name: str, output: str) -> None:
        self._port = port
        self._room = room
        self._name = name
        self._output = output

    async def run(self, stream: StreamingResult) -> None:
        r = self._room
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PROCESS_BEGIN,
                room=r,
                msg=f"Restoring {self._name} → {self._output}",
                data={"id": "restore", "label": f"Restoring {self._name}"},
            )
        )

        count = self._port.restore_snapshot(name=self._name, output=self._output)

        stream.emit(
            SyslogMessage(
                pri=7,
                msgid=MSGID.PROCESS_LOG,
                room=r,
                msg=f"wrote {count} files to {self._output}",
                data={"id": "restore", "message": f"wrote {count} files to {self._output}"},
            )
        )

        end: dict = {"id": "restore", "ok": True, "files": count, "output": self._output}
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PROCESS_END,
                room=r,
                msg=f"Restored {self._name} — {count} files written to {self._output}",
                data=end,
            )
        )
