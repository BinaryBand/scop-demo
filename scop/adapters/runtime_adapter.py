from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import ClassVar

from scop.bases import Adapter
from scop.ports.runtime_port import RuntimePort


class RuntimeAdapter(Adapter, RuntimePort):
    port: ClassVar[type[RuntimePort]] = RuntimePort

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[object]] = set()

    def spawn(self, job: Coroutine[object, object, object]) -> None:
        task = asyncio.create_task(job)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
