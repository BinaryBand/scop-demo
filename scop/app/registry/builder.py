from __future__ import annotations

from scop.bases import BaseApp
from scop.ports.runtime_port import RuntimePort


def build_default_registry() -> dict[str, BaseApp]:
    """Create the default command->app registry for AppDispatcher."""
    from scop.app.registry.config_app import ConfigApp
    from scop.app.registry.root_app import RootApp
    from scop.app.registry.snap_app import SnapApp

    commands = {
        "snapshot": ("SnapApp", "Manage snapshots"),
        "config": ("ConfigApp", "Application configuration"),
    }

    registry: dict[str, BaseApp] = {
        "snapshot": SnapApp(),
        "config": ConfigApp(),
    }
    descriptions = {key: value[1] for key, value in commands.items()}
    return {"": RootApp(descriptions), **registry}


def build_default_runtime() -> RuntimePort:
    """Create the default runtime implementation for AppDispatcher."""
    from scop.adapters.runtime_adapter import RuntimeAdapter
    from scop.ports.streaming_result import StreamingResult

    return RuntimeAdapter(StreamingResult)
