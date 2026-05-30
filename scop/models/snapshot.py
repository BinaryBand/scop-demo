from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotRecord:
    name: str
    files: int
    size: str
    date: str


@dataclass(frozen=True)
class DiffRecord:
    path: str
    status: str  # "added" | "removed" | "modified"


@dataclass(frozen=True)
class SnapshotStats:
    last_snap: str | None
    tracked: int
    changed: int
