from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator

from scop.models.protocol import ResolvedResult, SyslogMessage


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

    def __aiter__(self) -> AsyncIterator[SyslogMessage]:
        return self._drain()

    async def _drain(self) -> AsyncGenerator[SyslogMessage, None]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event
