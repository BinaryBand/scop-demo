from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from scop.bases import Adapter
from scop.models.snapshot import DiffRecord, SnapshotRecord, SnapshotStats
from scop.ports.snapshot_port import SnapshotPort

_STORE = Path("downloads") / "snapshots"
_OBJECTS = Path("downloads") / "objects"  # content-addressable blob store


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


def _scan_files(root: Path, *, recursive: bool) -> Iterator[tuple[str, Path, str, int]]:
    """Yield (rel_path, abs_path, sha256_hex, size_bytes) for each tracked file."""
    pattern = "**/*" if recursive else "*"
    for p in sorted(root.glob(pattern)):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        rel = str(p.relative_to(root))
        yield rel, p, _hash_file(p), p.stat().st_size


def _scan_tree(root: Path, *, recursive: bool) -> dict[str, dict]:
    """Return {rel_path: {hash, size}} — thin wrapper over _scan_files."""
    return {
        rel: {"hash": digest, "size": size}
        for rel, _, digest, size in _scan_files(root, recursive=recursive)
    }


# ── Object store ──────────────────────────────────────────────────────────────
# Stage 2 extension points:
#   _object_path  — add pack-file fallback lookup here
#   _write_object — add zlib compression / deltification here


def _object_path(digest: str) -> Path:
    """Loose object path for a blob (git-style two-char prefix sharding)."""
    return _OBJECTS / digest[:2] / digest[2:]


def _write_object(digest: str, source: Path) -> None:
    """Store source content under its hash. No-op if the object already exists."""
    dest = _object_path(digest)
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


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

    def count_snapshot_files(self, *, path: str, recursive: bool) -> int:
        root = Path(path).resolve()
        pattern = "**/*" if recursive else "*"
        return sum(
            1
            for p in root.glob(pattern)
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts)
        )

    def create_snapshot(
        self,
        *,
        path: str,
        dry_run: bool = False,
        recursive: bool = False,
        force: bool = False,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> SnapshotRecord:
        root = Path(path).resolve()

        # Collect entries lazily so on_progress fires incrementally during listing,
        # not only after the entire tree has been materialised by sorted().
        entries: list[tuple[str, Path]] = []
        pattern = "**/*" if recursive else "*"
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            if any(part.startswith(".") for part in p.relative_to(root).parts):
                continue
            entries.append((str(p.relative_to(root)), p))
            if on_progress and len(entries) % 100 == 0:
                on_progress(len(entries), 0)  # total=0 → listing phase

        entries.sort()  # stable sort after collection for a consistent manifest
        file_total = len(entries)
        if on_progress:
            on_progress(0, file_total)  # total known — switch to determinate

        scanned: list[tuple[str, Path, str, int]] = []
        files: dict[str, dict] = {}
        for i, (rel, p) in enumerate(entries):
            digest = _hash_file(p)
            size = p.stat().st_size
            files[rel] = {"hash": digest, "size": size}
            scanned.append((rel, p, digest, size))
            if on_progress:
                on_progress(i + 1, file_total)

        # Guard before writing anything — manifest is the authoritative record.
        if not force and _STORE.exists():
            snaps = sorted(_STORE.glob("snap-*.json"))
            if snaps and _load(snaps[-1].stem)["files"] == files:
                raise RuntimeError("no changes since last snapshot — use --force to override")

        name = _next_name()
        total = sum(f["size"] for f in files.values())
        now = datetime.now(UTC).isoformat(timespec="seconds")

        if not dry_run:
            # Write objects first; only commit the manifest once all blobs are safe.
            for _, abs_path, digest, _ in scanned:
                _write_object(digest, abs_path)
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

    def restore_snapshot(self, *, name: str, output: str) -> int:
        manifest = _load(name)
        root = Path(output).resolve()
        count = 0
        for rel, info in manifest["files"].items():
            src = _object_path(info["hash"])
            if not src.exists():
                raise FileNotFoundError(
                    f"object {info['hash'][:12]}… missing for {rel!r} "
                    f"— was this snapshot created before the object store was introduced?"
                )
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            count += 1
        return count

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
