from __future__ import annotations

import asyncio

from scop.app.registry.diff_app import DiffApp
from scop.app.registry.snap_app import SnapApp
from scop.models.bases import BaseApp
from scop.models.results import StreamingResult


class AppDispatcher:
    """Single public surface exported to cli.py.

    Constructs concrete apps, creates the StreamingResult, and fires the
    app task concurrently so the caller can iterate events while work runs.
    """

    def __init__(self) -> None:
        self._registry: dict[str, BaseApp] = {
            "snap": SnapApp(),
            "diff": DiffApp(),
        }

    async def dispatch(self, command: str, args: dict) -> StreamingResult:
        app = self._resolve(command)
        stream = StreamingResult()
        asyncio.create_task(app.run(args, stream))
        return stream

    def _resolve(self, command: str) -> BaseApp:
        try:
            return self._registry[command]
        except KeyError:
            raise ValueError(f"Unknown command: {command!r}")
