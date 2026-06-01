from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from scop.bases import Adapter
from scop.models.snapshot import DiffRecord, SnapshotRecord, SnapshotStats
from scop.ports.snapshot_port import SnapshotPort

_STORE = Path(".scop") / "snapshots"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} TB"


def _next_name() -> str:
    if not _STORE.exists():
        return "snap-001"
    existing = sorted(_STORE.glob("snap-*.json"))
    if not existing:
        return "snap-001"
    n = int(existing[-1].stem.split("-")[1]) + 1
    return f"snap-{n:03d}"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_tree(root: Path, *, recursive: bool) -> dict[str, dict]:
    pattern = "**/*" if recursive else "*"
    result: dict[str, dict] = {}
    for p in sorted(root.glob(pattern)):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        rel = str(p.relative_to(root))
        size = p.stat().st_size
        result[rel] = {"hash": _hash_file(p), "size": size}
    return result


def _load(name: str) -> dict:
    return json.loads((_STORE / f"{name}.json").read_text(encoding="utf-8"))


class SnapshotAdapter(Adapter, SnapshotPort):
    port: ClassVar[type[SnapshotPort]] = SnapshotPort

    def get_stats(self) -> SnapshotStats:
        if not _STORE.exists():
            return SnapshotStats(last_snap=None, tracked=0, changed=0)
        snaps = sorted(_STORE.glob("snap-*.json"))
        if not snaps:
            return SnapshotStats(last_snap=None, tracked=0, changed=0)
        manifest = _load(snaps[-1].stem)
        saved: dict[str, dict] = manifest["files"]
        current = _scan_tree(Path.cwd(), recursive=True)
        changed = sum(
            1 for path, info in saved.items() if current.get(path, {}).get("hash") != info["hash"]
        )
        return SnapshotStats(
            last_snap=manifest["created"],
            tracked=len(saved),
            changed=changed,
        )

    def list_snapshots(self, *, expand: bool = False) -> list[SnapshotRecord]:
        if not _STORE.exists():
            return []
        paths = sorted(_STORE.glob("snap-*.json"))
        if not expand:
            paths = paths[-10:]
        records = []
        for p in paths:
            data = _load(p.stem)
            files: dict[str, dict] = data["files"]
            total = sum(f["size"] for f in files.values())
            records.append(
                SnapshotRecord(
                    name=data["name"],
                    files=len(files),
                    size=_fmt_size(total),
                    date=data["created"][:10],
                )
            )
        return records

    def create_snapshot(
        self, *, path: str, dry_run: bool = False, recursive: bool = False, force: bool = False
    ) -> SnapshotRecord:
        root = Path(path).resolve()
        files = _scan_tree(root, recursive=recursive)

        if not force and _STORE.exists():
            snaps = sorted(_STORE.glob("snap-*.json"))
            if snaps:
                last = _load(snaps[-1].stem)
                if last["files"] == files:
                    raise RuntimeError("no changes since last snapshot — use --force to override")

        name = _next_name()
        total = sum(f["size"] for f in files.values())
        now = datetime.now(UTC).isoformat(timespec="seconds")

        if not dry_run:
            _STORE.mkdir(parents=True, exist_ok=True)
            (_STORE / f"{name}.json").write_text(
                json.dumps({"name": name, "created": now, "files": files}, indent=2),
                encoding="utf-8",
            )

        return SnapshotRecord(
            name=name,
            files=len(files),
            size=_fmt_size(total),
            date=now[:10],
        )

    def diff_snapshots(self, from_snap: str | None, to_snap: str | None) -> list[DiffRecord]:
        from_files: dict[str, dict] = _load(from_snap)["files"] if from_snap else {}
        to_files: dict[str, dict] = _load(to_snap)["files"] if to_snap else {}
        result: list[DiffRecord] = []
        for path in sorted(set(from_files) | set(to_files)):
            if path not in from_files:
                result.append(DiffRecord(path=path, status="added"))
            elif path not in to_files:
                result.append(DiffRecord(path=path, status="removed"))
            elif from_files[path]["hash"] != to_files[path]["hash"]:
                result.append(DiffRecord(path=path, status="modified"))
        return result
