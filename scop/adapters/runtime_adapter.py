from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Coroutine
from typing import ClassVar

from scop.bases import Adapter
from scop.models.protocol import ResolvedResult, SyslogMessage
from scop.ports.runtime_port import RuntimePort
from scop.ports.stream_port import StreamPort
from scop.ports.streaming_result import StreamingResult


class RuntimeAdapter(Adapter, RuntimePort):
    port: ClassVar[type[RuntimePort]] = RuntimePort

    def __init__(self, stream_factory: Callable[[RuntimeAdapter], StreamingResult]) -> None:
        self._stream_factory = stream_factory
        self._tasks: set[asyncio.Task[object]] = set()
        self._queues: dict[int, asyncio.Queue[SyslogMessage | None]] = {}
        self._results: dict[int, ResolvedResult | None] = {}
        self._next_stream_id = 0

    def create_stream(self) -> StreamingResult:
        return self._stream_factory(self)

    def new_stream(self) -> int:
        stream_id = self._next_stream_id
        self._next_stream_id += 1
        self._queues[stream_id] = asyncio.Queue()
        self._results[stream_id] = None
        return stream_id

    def emit(self, stream_id: int, event: SyslogMessage) -> None:
        self._queues[stream_id].put_nowait(event)

    def resolve(self, stream_id: int, ok: bool, data: SyslogMessage) -> None:
        self._results[stream_id] = ResolvedResult(ok=ok, data=data)
        self._queues[stream_id].put_nowait(None)

    def result(self, stream_id: int) -> ResolvedResult | None:
        return self._results.get(stream_id)

    def iter_events(self, stream_id: int) -> AsyncIterator[SyslogMessage]:
        return self._drain(stream_id)

    async def _drain(self, stream_id: int) -> AsyncGenerator[SyslogMessage, None]:
        queue = self._queues[stream_id]
        while True:
            event = await queue.get()
            if event is None:
                return
            yield event

    def spawn(self, job: Coroutine[object, object, object], stream: StreamPort) -> None:
        _ = stream
        task = asyncio.create_task(job)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
