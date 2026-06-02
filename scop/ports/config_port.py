from __future__ import annotations

from abc import abstractmethod

from scop.bases import Port
from scop.models.config import AppConfig


class ConfigPort(Port):
    @abstractmethod
    def load(self) -> AppConfig: ...

    @abstractmethod
    def set_value(self, key: str, value: str) -> AppConfig: ...
