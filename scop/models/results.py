from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

from scop.models.messages import SyslogMessage


@dataclass(frozen=True)
class ResolvedResult:
    ok: bool
    data: SyslogMessage  # must be a TASK_END message


class StreamingResult:
    """Async event channel created by AppDispatcher and passed down to services."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[SyslogMessage | None] = asyncio.Queue()
        self._resolved: ResolvedResult | None = None

    def emit(self, event: SyslogMessage) -> None:
        self._queue.put_nowait(event)

    def resolve(self, ok: bool, data: SyslogMessage) -> None:
        self._resolved = ResolvedResult(ok=ok, data=data)
        self._queue.put_nowait(None)

    @property
    def result(self) -> ResolvedResult | None:
        return self._resolved

    async def __aiter__(self) -> AsyncIterator[SyslogMessage]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event
