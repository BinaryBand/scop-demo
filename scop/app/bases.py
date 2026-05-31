from __future__ import annotations

from abc import ABC, abstractmethod


class BaseApp(ABC):
    """Marker base — concrete apps live in app/registry/ and implement run()."""

    @abstractmethod
    async def run(self, args: dict, stream) -> None: ...
