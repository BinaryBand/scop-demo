from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator

from scop.bases import Port
from scop.models.protocol import SyslogMessage


class StreamPort(Port):
    """Port interface — emit events and resolve the result channel."""

    @abstractmethod
    def emit(self, event: SyslogMessage) -> None: ...

    @abstractmethod
    def resolve(self, ok: bool, data: SyslogMessage) -> None: ...

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[SyslogMessage]: ...
