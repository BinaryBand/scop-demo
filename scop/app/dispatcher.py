from __future__ import annotations

import asyncio

from scop.app.bases import BaseApp
from scop.app.stream import StreamingResult


class AppDispatcher:
    """Single public surface exported to cli.py."""

    def __init__(self, registry: dict[str, BaseApp]) -> None:
        self._registry = registry
        self._tasks: set[asyncio.Task] = set()

    @classmethod
    def default(cls) -> AppDispatcher:
        from scop.app.registry.diff_app import DiffApp
        from scop.app.registry.log_app import LogApp
        from scop.app.registry.restore_app import RestoreApp
        from scop.app.registry.root_app import RootApp
        from scop.app.registry.snap_app import SnapApp
        from scop.app.registry.status_app import StatusApp

        commands = {
            "snap": ("SnapApp", "Take a snapshot of a directory"),
            "diff": ("DiffApp", "Compare two snapshots"),
            "status": ("StatusApp", "Show current snapshot state"),
            "log": ("LogApp", "List all snapshots"),
            "restore": ("RestoreApp", "Restore a snapshot"),
        }

        registry: dict[str, BaseApp] = {
            "snap": SnapApp(),
            "diff": DiffApp(),
            "status": StatusApp(),
            "log": LogApp(),
            "restore": RestoreApp(),
        }
        descriptions = {k: v[1] for k, v in commands.items()}
        return cls({"": RootApp(descriptions), **registry})

    def dispatch(self, command: str, args: dict) -> StreamingResult:
        app = self._resolve(command)
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
