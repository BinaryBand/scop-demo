from __future__ import annotations

from collections.abc import AsyncIterator

from scop.models.protocol import ResolvedResult, SyslogMessage
from scop.ports.stream_port import StreamPort
from scop.utils.concurrent import AsyncQueueChannel


class StreamingResult(StreamPort):
    """Async event channel created by AppDispatcher and passed down to services."""

    def __init__(self) -> None:
        self._channel: AsyncQueueChannel[SyslogMessage] = AsyncQueueChannel()
        self._resolved: ResolvedResult | None = None

    def emit(self, event: SyslogMessage) -> None:
        self._channel.send(event)

    def resolve(self, ok: bool, data: SyslogMessage) -> None:
        self._resolved = ResolvedResult(ok=ok, data=data)
        self._channel.close()

    @property
    def result(self) -> ResolvedResult | None:
        return self._resolved

    def __aiter__(self) -> AsyncIterator[SyslogMessage]:
        return self._channel.__aiter__()
