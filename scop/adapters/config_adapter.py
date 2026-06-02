from __future__ import annotations

import tomllib
from pathlib import Path
from typing import ClassVar

from scop.bases import Adapter
from scop.models.config import AppConfig, SnapshotConfig
from scop.ports.config_port import ConfigPort

_CONFIG_PATH = Path("static") / "config.toml"

_EDITABLE: dict[str, tuple[str, str]] = {
    "snapshot.store_dir": ("snapshot", "store_dir"),
    "snapshot.objects_dir": ("snapshot", "objects_dir"),
    "snapshot.skip_dirs": ("snapshot", "skip_dirs"),
}


def _serialize(config: AppConfig) -> str:
    snap = config.snapshot
    dirs = "\n".join(f'    "{d}",' for d in snap.skip_dirs)
    return (
        "[snapshot]\n"
        f'store_dir = "{snap.store_dir}"\n'
        f'objects_dir = "{snap.objects_dir}"\n'
        f"skip_dirs = [\n{dirs}\n]\n"
    )


class ConfigAdapter(Adapter, ConfigPort):
    port: ClassVar[type[ConfigPort]] = ConfigPort

    def load(self) -> AppConfig:
        if not _CONFIG_PATH.exists():
            return AppConfig()
        with _CONFIG_PATH.open("rb") as fh:
            raw = tomllib.load(fh)
        snap_raw = raw.get("snapshot", {})
        defaults = SnapshotConfig()
        return AppConfig(
            snapshot=SnapshotConfig(
                store_dir=str(snap_raw.get("store_dir", defaults.store_dir)),
                objects_dir=str(snap_raw.get("objects_dir", defaults.objects_dir)),
                skip_dirs=tuple(snap_raw.get("skip_dirs", list(defaults.skip_dirs))),
            )
        )

    def set_value(self, key: str, value: str) -> AppConfig:
        if key not in _EDITABLE:
            known = ", ".join(sorted(_EDITABLE))
            raise ValueError(f"unknown config key {key!r}. Known keys: {known}")

        config = self.load()
        snap = config.snapshot

        if key == "snapshot.store_dir":
            snap = SnapshotConfig(
                store_dir=value, objects_dir=snap.objects_dir, skip_dirs=snap.skip_dirs
            )
        elif key == "snapshot.objects_dir":
            snap = SnapshotConfig(
                store_dir=snap.store_dir, objects_dir=value, skip_dirs=snap.skip_dirs
            )
        elif key == "snapshot.skip_dirs":
            skip = tuple(v.strip() for v in value.split(",") if v.strip())
            snap = SnapshotConfig(
                store_dir=snap.store_dir, objects_dir=snap.objects_dir, skip_dirs=skip
            )

        new_config = AppConfig(snapshot=snap)
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(_serialize(new_config), encoding="utf-8")
        return new_config
