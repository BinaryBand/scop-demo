from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class Port(ABC):
    """Marker base — every class in ports/ must subclass this."""


class Adapter(ABC):
    """Marker base — must declare port: ClassVar[type[Port]] to enable parity check."""

    port: ClassVar[type[Port]]


class Service(ABC):
    """Marker base — must implement run(stream: IStream); output flows through IStream events."""

    @abstractmethod
    async def run(self, stream) -> None: ...
