from __future__ import annotations

from scop.app.registry.builder import build_default_registry
from scop.app.runtime import TaskRunner
from scop.app.stream import StreamingResult
from scop.bases import BaseApp


class AppDispatcher:
    """Single public surface exported to cli.py."""

    def __init__(self, registry: dict[str, BaseApp]) -> None:
        self._registry = registry
        self._runner = TaskRunner()

    @classmethod
    def default(cls) -> AppDispatcher:
        return cls(build_default_registry())

    def dispatch(self, command: str, args: dict) -> StreamingResult:
        app = self._resolve(command)
        room = None if command == "" else command
        args["_room"] = room
        stream = StreamingResult()
        self._runner.spawn(app.run(args, stream))
        return stream

    def _resolve(self, command: str) -> BaseApp:
        try:
            return self._registry[command]
        except KeyError:
            raise ValueError(f"Unknown command: {command!r}") from None
