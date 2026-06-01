from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Generic, TypeVar

T = TypeVar("T")


class AsyncQueueChannel(Generic[T]):
    """Small async queue channel with close sentinel semantics."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[T | None] = asyncio.Queue()

    def send(self, event: T) -> None:
        self._queue.put_nowait(event)

    def close(self) -> None:
        self._queue.put_nowait(None)

    def __aiter__(self) -> AsyncIterator[T]:
        return self._drain()

    async def _drain(self) -> AsyncGenerator[T, None]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event
