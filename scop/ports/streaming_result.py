from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar

from scop.bases import Port
from scop.models.ndjson import NDJSONEvent
from scop.models.protocol import ResolvedResult, SyslogMessage
from scop.ports.stream_port import StreamPort


class _RuntimeStreamOps(Port):
    @abstractmethod
    def new_stream(self) -> int: ...

    @abstractmethod
    def emit(self, stream_id: int, event: SyslogMessage) -> None: ...

    @abstractmethod
    def resolve(self, stream_id: int, ok: bool, data: SyslogMessage) -> None: ...

    @abstractmethod
    def result(self, stream_id: int) -> ResolvedResult | None: ...

    @abstractmethod
    def iter_events(self, stream_id: int) -> AsyncIterator[SyslogMessage]: ...


class StreamingResult(StreamPort, Port):
    """Async event channel created by AppDispatcher and passed down to services."""

    _validate: ClassVar[bool] = False

    @classmethod
    def configure(cls, *, validate: bool) -> None:
        cls._validate = validate

    def __init__(self, runtime: _RuntimeStreamOps) -> None:
        self._runtime = runtime
        self._stream_id = runtime.new_stream()

    def emit(self, event: SyslogMessage) -> None:
        if StreamingResult._validate:
            NDJSONEvent.model_validate_json(event.to_ndjson())
        self._runtime.emit(self._stream_id, event)

    def resolve(self, ok: bool, data: SyslogMessage) -> None:
        self._runtime.resolve(self._stream_id, ok, data)

    @property
    def result(self) -> ResolvedResult | None:
        return self._runtime.result(self._stream_id)

    def __aiter__(self) -> AsyncIterator[SyslogMessage]:
        return self._runtime.iter_events(self._stream_id)
