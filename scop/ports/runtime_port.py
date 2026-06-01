from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Coroutine

from scop.bases import Port
from scop.models.protocol import ResolvedResult, SyslogMessage


class RuntimePort(Port):
    """Runtime execution and stream provisioning boundary for app orchestration."""

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

    @abstractmethod
    def spawn(self, job: Coroutine[object, object, object]) -> None: ...
