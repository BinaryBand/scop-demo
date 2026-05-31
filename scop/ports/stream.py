from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from scop.models.protocol import SyslogMessage


class IStream(Protocol):
    """Stream interface services depend on — emit events, resolve when done."""

    def emit(self, event: SyslogMessage) -> None: ...
    def resolve(self, ok: bool, data: SyslogMessage) -> None: ...
    def __aiter__(self) -> AsyncIterator[SyslogMessage]: ...
