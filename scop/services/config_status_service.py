from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.config_port import ConfigPort
from scop.ports.streaming_result import StreamingResult


class ConfigStatusService(Service):
    def __init__(self, port: ConfigPort, room: str) -> None:
        self._port = port
        self._room = room

    async def run(self, stream: StreamingResult) -> None:
        config = self._port.load()
        r = self._room
        snap = config.snapshot

        scalars: list[tuple[str, str, str]] = [
            ("snapshot.store_dir", "Snapshot store", snap.store_dir),
            ("snapshot.objects_dir", "Object store", snap.objects_dir),
            ("snapshot.skip_dirs", "Skipped dirs", ", ".join(snap.skip_dirs)),
        ]

        for scalar_id, label, value in scalars:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.SCALAR_SET,
                    room=r,
                    msg=f"{label}: {value}",
                    data={"id": scalar_id, "label": label, "value": value, "type": "string"},
                )
            )
