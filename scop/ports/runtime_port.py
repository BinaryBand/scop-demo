from __future__ import annotations

from abc import abstractmethod
from collections.abc import Coroutine

from scop.bases import Port


class RuntimePort(Port):
    """Runtime execution and stream provisioning boundary for app orchestration."""

    @abstractmethod
    def spawn(self, job: Coroutine[object, object, object]) -> None: ...
