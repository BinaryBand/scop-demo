from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable

from scop.bases import Port
from scop.models.snapshot import DiffRecord, SnapshotRecord, SnapshotStats


class SnapshotPort(Port):
    @abstractmethod
    def get_stats(self) -> SnapshotStats: ...

    @abstractmethod
    def list_snapshots(self, *, expand: bool = False) -> list[SnapshotRecord]: ...

    @abstractmethod
    def count_snapshot_files(self, *, path: str, recursive: bool) -> int: ...

    @abstractmethod
    def create_snapshot(
        self,
        *,
        path: str,
        dry_run: bool = False,
        recursive: bool = False,
        force: bool = False,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> SnapshotRecord: ...

    @abstractmethod
    def restore_snapshot(self, *, name: str, output: str) -> int: ...

    @abstractmethod
    def diff_snapshots(self, from_snap: str | None, to_snap: str | None) -> list[DiffRecord]: ...
