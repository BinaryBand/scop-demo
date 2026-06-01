from __future__ import annotations

import tomllib
from pathlib import Path

from scop.models.manifest import ScopManifest


def test_scop_toml_conforms_to_manifest_model() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "scop.toml"
    payload = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    ScopManifest.model_validate(payload)
