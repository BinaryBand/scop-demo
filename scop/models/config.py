from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_SKIP_DIRS: tuple[str, ...] = (
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
)


@dataclass(frozen=True)
class SnapshotConfig:
    store_dir: str = ".scop/snapshots"
    objects_dir: str = ".scop/objects"
    skip_dirs: tuple[str, ...] = _DEFAULT_SKIP_DIRS


@dataclass(frozen=True)
class AppConfig:
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
