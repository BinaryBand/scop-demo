from __future__ import annotations

from scop.bases import BaseApp


def build_default_registry() -> dict[str, BaseApp]:
    """Create the default command->app registry for AppDispatcher."""
    from scop.app.registry.root_app import RootApp
    from scop.app.registry.snap_app import SnapApp

    commands = {
        "snapshot": ("SnapApp", "Manage snapshots"),
    }

    registry: dict[str, BaseApp] = {
        "snapshot": SnapApp(),
    }
    descriptions = {key: value[1] for key, value in commands.items()}
    return {"": RootApp(descriptions), **registry}
