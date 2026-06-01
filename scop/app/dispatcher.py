from __future__ import annotations

import asyncio

from scop.app.stream import StreamingResult
from scop.bases import BaseApp


class AppDispatcher:
    """Single public surface exported to cli.py."""

    def __init__(self, registry: dict[str, BaseApp]) -> None:
        self._registry = registry
        self._tasks: set[asyncio.Task] = set()

    @classmethod
    def default(cls) -> AppDispatcher:
        from scop.app.registry.root_app import RootApp
        from scop.app.registry.snap_app import SnapApp

        commands = {
            "snapshot": ("SnapApp", "Manage snapshots"),
        }

        registry: dict[str, BaseApp] = {
            "snapshot": SnapApp(),
        }
        descriptions = {k: v[1] for k, v in commands.items()}
        return cls({"": RootApp(descriptions), **registry})

    def dispatch(self, command: str, args: dict) -> StreamingResult:
        app = self._resolve(command)
        room = None if command == "" else command
        args["_room"] = room
        stream = StreamingResult()
        task = asyncio.create_task(app.run(args, stream))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return stream

    def _resolve(self, command: str) -> BaseApp:
        try:
            return self._registry[command]
        except KeyError:
            raise ValueError(f"Unknown command: {command!r}") from None
