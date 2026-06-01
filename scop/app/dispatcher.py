from __future__ import annotations

from scop.adapters.runtime_adapter import RuntimeAdapter
from scop.app.registry.builder import build_default_registry
from scop.app.stream import StreamingResult
from scop.bases import BaseApp
from scop.ports.runtime_port import RuntimePort
from scop.ports.stream_port import StreamPort


class AppDispatcher:
    """Single public surface exported to cli.py."""

    def __init__(self, registry: dict[str, BaseApp], runtime: RuntimePort) -> None:
        self._registry = registry
        self._runtime = runtime

    @classmethod
    def default(cls) -> AppDispatcher:
        return cls(build_default_registry(), RuntimeAdapter())

    def dispatch(self, command: str, args: dict) -> StreamPort:
        app = self._resolve(command)
        room = None if command == "" else command
        args["_room"] = room
        stream = StreamingResult()
        self._runtime.spawn(app.run(args, stream))
        return stream

    def _resolve(self, command: str) -> BaseApp:
        try:
            return self._registry[command]
        except KeyError:
            raise ValueError(f"Unknown command: {command!r}") from None
