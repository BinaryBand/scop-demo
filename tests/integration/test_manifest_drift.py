from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

from scop.utils.proc import run_resolved


def test_scop_toml_matches_generated_manifest() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "scop.toml"
    if not manifest_path.exists():
        return

    expected = manifest_path.read_text(encoding="utf-8")
    result = run_resolved(
        [
            "poetry",
            "run",
            "python",
            "scripts/generate.manifest.py",
            "--format",
            "toml",
            "--out",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(root),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    generated = result.stdout
    if generated != expected:
        diff = "\n".join(
            unified_diff(
                expected.splitlines(),
                generated.splitlines(),
                fromfile="scop.toml",
                tofile="generated",
                lineterm="",
            )
        )
        raise AssertionError(
            f"manifest drift detected between scop.toml and generated output\n{diff}"
        )
