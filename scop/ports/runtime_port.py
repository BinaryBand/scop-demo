from __future__ import annotations

from abc import abstractmethod
from collections.abc import Coroutine

from scop.bases import Port
from scop.ports.stream_port import StreamPort


class RuntimePort(Port):
    """Runtime execution and stream provisioning boundary for app orchestration."""

    @abstractmethod
    def create_stream(self) -> StreamPort: ...

    @abstractmethod
    def spawn(self, job: Coroutine[object, object, object], stream: StreamPort) -> None: ...
