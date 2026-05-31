from __future__ import annotations

from abc import abstractmethod

from scop.models.bases import Port
from scop.models.snapshot import DiffRecord, SnapshotRecord, SnapshotStats


class SnapshotPort(Port):
    @abstractmethod
    def get_stats(self) -> SnapshotStats: ...

    @abstractmethod
    def list_snapshots(self, *, expand: bool = False) -> list[SnapshotRecord]: ...

    @abstractmethod
    def create_snapshot(self, *, dry_run: bool = False) -> SnapshotRecord: ...

    @abstractmethod
    def diff_snapshots(self, from_snap: str | None, to_snap: str | None) -> list[DiffRecord]: ...
