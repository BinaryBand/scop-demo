from __future__ import annotations

from scop.bases import Service
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.config_port import ConfigPort
from scop.ports.streaming_result import StreamingResult


class ConfigSetService(Service):
    def __init__(self, port: ConfigPort, room: str, key: str, value: str) -> None:
        self._port = port
        self._room = room
        self._key = key
        self._value = value

    async def run(self, stream: StreamingResult) -> None:
        r = self._room
        try:
            self._port.set_value(self._key, self._value)
        except ValueError as exc:
            stream.emit(
                SyslogMessage(
                    pri=4,
                    msgid=MSGID.SCALAR_SET,
                    room=r,
                    msg=str(exc),
                    data={"id": "error", "label": "error", "value": str(exc), "type": "string"},
                )
            )
            return

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.SCALAR_SET,
                room=r,
                msg=f"{self._key} = {self._value}",
                data={"id": self._key, "label": self._key, "value": self._value, "type": "string"},
            )
        )
