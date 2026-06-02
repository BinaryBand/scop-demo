from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.config_port import ConfigPort
from scop.ports.streaming_result import StreamingResult


class ConfigShowService(Service):
    def __init__(self, port: ConfigPort, room: str, key: str | None = None) -> None:
        self._port = port
        self._room = room
        self._key = key

    async def run(self, stream: StreamingResult) -> None:
        config = self._port.load()
        r = self._room
        snap = config.snapshot

        rows: list[tuple[str, str]] = [
            ("snapshot.store_dir", snap.store_dir),
            ("snapshot.objects_dir", snap.objects_dir),
            ("snapshot.skip_dirs", ", ".join(snap.skip_dirs)),
        ]

        if self._key is not None:
            rows = [(k, v) for k, v in rows if k == self._key]
            if not rows:
                stream.emit(
                    SyslogMessage(
                        pri=4,
                        msgid=MSGID.SCALAR_SET,
                        room=r,
                        msg=f"unknown key: {self._key!r}",
                        data={
                            "id": "error",
                            "label": "error",
                            "value": self._key,
                            "type": "string",
                        },
                    )
                )
                return

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TABLE_DECLARE,
                room=r,
                msg="Configuration",
                data={"id": "config", "label": "Configuration", "schema": ["key", "value"]},
            )
        )
        for key, value in rows:
            stream.emit(
                SyslogMessage(
                    pri=6,
                    msgid=MSGID.TABLE_ROW,
                    room=r,
                    msg=f"{key} = {value}",
                    data={"id": "config", "row_id": key, "values": {"key": key, "value": value}},
                )
            )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.TABLE_END,
                room=r,
                msg="",
                data={"id": "config"},
            )
        )
