from __future__ import annotations

from collections.abc import AsyncIterator

from scop.models.protocol import ResolvedResult, SyslogMessage
from scop.ports.runtime_port import RuntimePort
from scop.ports.stream_port import StreamPort


class StreamingResult(StreamPort):
    """Async event channel created by AppDispatcher and passed down to services."""

    def __init__(self, runtime: RuntimePort) -> None:
        self._runtime = runtime
        self._stream_id = runtime.new_stream()

    def emit(self, event: SyslogMessage) -> None:
        self._runtime.emit(self._stream_id, event)

    def resolve(self, ok: bool, data: SyslogMessage) -> None:
        self._runtime.resolve(self._stream_id, ok, data)

    @property
    def result(self) -> ResolvedResult | None:
        return self._runtime.result(self._stream_id)

    def __aiter__(self) -> AsyncIterator[SyslogMessage]:
        return self._runtime.iter_events(self._stream_id)
