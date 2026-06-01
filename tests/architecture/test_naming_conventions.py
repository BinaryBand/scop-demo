"""Contract tests for architecture rules 3 and 4: naming and port parity.

Rule 3 — one class per role file; class name must match the filename stem.
Rule 4 — every adapter must declare `port` whose type matches the adapter stem.

Both rules are partially enforced by ast-grep (suffix + marker base), but
ast-grep has no filename access so stem-parity cannot be checked there.
These tests fill that gap.
"""

from __future__ import annotations

from pathlib import Path

from scop.utils.code import class_var_annotation_names, top_level_class_names

ROOT = Path(__file__).resolve().parents[2]
SCOP = ROOT / "scop"


def _snake_to_pascal(s: str) -> str:
    return "".join(word.capitalize() for word in s.split("_"))


def _role_files(layer: str, suffix: str) -> list[Path]:
    return sorted((SCOP / layer).glob(f"**/*_{suffix}.py"))


class TestRule3StemParity:
    """Each role file defines exactly one class whose name equals stem → PascalCase."""

    def _check_layer(self, layer: str, suffix: str) -> None:
        violations: dict[str, str] = {}
        for path in _role_files(layer, suffix):
            stem = path.stem  # e.g. "snapshot_adapter"
            expected = _snake_to_pascal(stem)  # e.g. "SnapshotAdapter"
            classes = [c for c in top_level_class_names(path) if not c.startswith("_")]
            if classes != [expected]:
                violations[path.name] = f"expected [{expected}], got {classes}"
        assert not violations, violations

    def test_adapters(self) -> None:
        self._check_layer("adapters", "adapter")

    def test_services(self) -> None:
        self._check_layer("services", "service")

    def test_ports(self) -> None:
        self._check_layer("ports", "port")

    def test_apps(self) -> None:
        self._check_layer("app", "app")


class TestRule4PortTypeParity:
    """Each adapter's `port` ClassVar type must match the adapter's own filename stem."""

    def test_adapter_port_type_matches_stem(self) -> None:
        violations: dict[str, str] = {}
        for path in _role_files("adapters", "adapter"):
            stem = path.stem  # e.g. "snapshot_adapter"
            base = stem[: -len("_adapter")]  # e.g. "snapshot"
            expected_port = _snake_to_pascal(base) + "Port"  # e.g. "SnapshotPort"

            classes = [c for c in top_level_class_names(path) if not c.startswith("_")]
            if not classes:
                continue
            class_name = classes[0]
            port_types = class_var_annotation_names(path, class_name, "port")
            if expected_port not in port_types:
                violations[path.name] = f"expected port type '{expected_port}', found {port_types}"
        assert not violations, violations
