from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scop.models.manifest import ScopManifest

DEFAULT_OUT = "scop/models/schemas/scop.manifest.schema.json"


def _render_schema(*, pretty: bool) -> str:
    schema = ScopManifest.model_json_schema()
    if pretty:
        return json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return json.dumps(schema, separators=(",", ":"), sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/dump_manifest_schema.py",
        description="Dump ScopManifest JSON Schema.",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output schema path, or '-' for stdout.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print schema JSON.")
    ns = parser.parse_args(argv)

    output = _render_schema(pretty=ns.pretty)
    if ns.out == "-":
        sys.stdout.write(output)
        return 0

    out_path = Path(ns.out)
    out_path.write_text(output, encoding="utf-8")
    sys.stdout.write(f"wrote {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
