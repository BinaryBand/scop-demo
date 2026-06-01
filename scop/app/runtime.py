from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Coroutine

from scop.models.protocol import SyslogMessage


class TaskRunner:
    """Tracks fire-and-forget app tasks so they remain referenced until done."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[object]] = set()

    def spawn(self, job: Coroutine[object, object, object]) -> asyncio.Task[object]:
        task = asyncio.create_task(job)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task


class StreamQueue:
    """Queue wrapper used by StreamingResult to emit and drain events."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[SyslogMessage | None] = asyncio.Queue()

    def emit(self, event: SyslogMessage) -> None:
        self._queue.put_nowait(event)

    def close(self) -> None:
        self._queue.put_nowait(None)

    async def drain(self) -> AsyncGenerator[SyslogMessage, None]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event
