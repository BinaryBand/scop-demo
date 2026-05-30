from __future__ import annotations

import asyncio

from scop.app.registry.root_app import RootApp
from scop.app.registry.snap_app import SnapApp
from scop.models.bases import BaseApp
from scop.models.results import StreamingResult


class AppDispatcher:
    """Single public surface exported to cli.py.

    Creates the StreamingResult and fires the app task concurrently so the
    caller can iterate events while work runs.
    """

    def __init__(self) -> None:
        self._registry: dict[str | None, BaseApp] = {
            None: RootApp(),
            "snapshot": SnapApp(),
        }

    async def dispatch(self, command: str | None, args: dict) -> StreamingResult:
        app = self._resolve(command)
        stream = StreamingResult()
        asyncio.create_task(app.run(args, stream))
        return stream

    def _resolve(self, command: str | None) -> BaseApp:
        try:
            return self._registry[command]
        except KeyError:
            raise ValueError(f"Unknown command: {command!r}") from None
