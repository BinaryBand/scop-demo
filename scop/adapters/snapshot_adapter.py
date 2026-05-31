from __future__ import annotations

from typing import ClassVar

from scop.framework.bases import Adapter
from scop.models.snapshot import DiffRecord, SnapshotRecord, SnapshotStats
from scop.ports.snapshot_port import SnapshotPort


class SnapshotAdapter(Adapter, SnapshotPort):
    port: ClassVar[type[SnapshotPort]] = SnapshotPort

    def get_stats(self) -> SnapshotStats:
        return SnapshotStats(
            last_snap="2026-05-30T14:32:00Z",
            tracked=1042,
            changed=3,
        )

    def list_snapshots(self, *, expand: bool = False) -> list[SnapshotRecord]:
        snaps = [
            SnapshotRecord(name="snap-002", files=41, size="1.1 MB", date="2026-05-28"),
            SnapshotRecord(name="snap-001", files=42, size="1.2 MB", date="2026-05-30"),
        ]
        if expand:
            snaps.insert(
                0, SnapshotRecord(name="snap-000", files=40, size="1.0 MB", date="2026-05-20")
            )
        return snaps

    def create_snapshot(self, *, dry_run: bool = False) -> SnapshotRecord:
        # TODO: hash working tree, write snapshot file
        return SnapshotRecord(name="snap-003", files=45, size="1.3 MB", date="2026-05-30")

    def diff_snapshots(self, from_snap: str | None, to_snap: str | None) -> list[DiffRecord]:
        # TODO: load and compare snapshot manifests
        return [
            DiffRecord(path="README.md", status="modified"),
            DiffRecord(path="src/new_file.py", status="added"),
            DiffRecord(path="old/deleted.py", status="removed"),
        ]
