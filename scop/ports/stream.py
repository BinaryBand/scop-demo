from __future__ import annotations

from typing import AsyncIterator, Protocol

from scop.protocol.messages import SyslogMessage


class IStream(Protocol):
    """Stream interface services depend on — emit events, resolve when done."""

    def emit(self, event: SyslogMessage) -> None: ...
    def resolve(self, ok: bool, data: SyslogMessage) -> None: ...
    def __aiter__(self) -> AsyncIterator[SyslogMessage]: ...
