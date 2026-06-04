from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import IO

from scop.cli import DecodedArgv, decode_argv, dispatch_events, to_ndjson
from scop.ui import UIModel, UIPage


def _is_tty(f: IO[str]) -> bool:
    try:
        return os.isatty(f.fileno())
    except Exception:
        return False


def _help_argv(argv: list[str]) -> tuple[str, dict]:
    tokens = [t for t in argv if t and not t.startswith("-")]
    if not tokens:
        return "", {"help": True}
    args: dict = {"help": True}
    if len(tokens) >= 2:
        args["action"] = tokens[1]
    return tokens[0], args


def render_tty(page: UIPage | None, out: IO[str]) -> None:
    """Render the current page's slots to a terminal."""
    if page is None:
        return

    for sid, ev in page.scalars.items():
        label = str(ev.get("label") or sid)
        value = str(ev.get("value", ""))
        unit = str(ev.get("unit") or "")
        out.write(f"  {label:<22}{(value + ' ' + unit).rstrip()}\n")

    for entry in page.tables.values():
        decl = entry.get("declare", {})
        rows = entry.get("rows", [])
        schema = [str(c) for c in (decl.get("schema") or [])]
        if not schema or not rows:
            continue
        widths = {c: len(c) for c in schema}
        for row in rows:
            for c in schema:
                widths[c] = max(widths[c], len(str(row.get(c, ""))))
        out.write("  " + "  ".join(c.upper().ljust(widths[c]) for c in schema) + "\n")
        out.write("  " + "  ".join("-" * widths[c] for c in schema) + "\n")
        for row in rows:
            out.write("  " + "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in schema) + "\n")

    for lid, entry in page.lists.items():
        decl = entry.get("declare", {})
        label = str(decl.get("label") or lid)
        items = [x for x in entry.get("items", []) if isinstance(x, dict) and x.get("command")]
        if not items:
            continue
        out.write(f"\n{label.title()}:\n")
        width = max(len(str(x["command"]).split()[-1]) for x in items)
        for item in items:
            last = str(item["command"]).split()[-1].replace("-", " ").title()
            desc = str(item.get("description", ""))
            out.write(f"  {last.ljust(width)}  {desc}\n")


def _dispatch_and_render(decoded: DecodedArgv, out: IO[str]) -> int:
    events, ok = dispatch_events(decoded.command, decoded.args)
    if _is_tty(out):
        model = UIModel()
        model.ingest_many(events)
        render_tty(model.current_page(), out)
    else:
        out.write(to_ndjson(events))
    return 0 if ok else 1


def _main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])

    if any(a in {"-h", "--help"} for a in raw_argv):
        command, args = _help_argv(raw_argv)
        events, ok = dispatch_events(command, args)
        if _is_tty(sys.stdout):
            model = UIModel()
            model.ingest_many(events)
            render_tty(model.current_page(), sys.stdout)
        else:
            sys.stdout.write(to_ndjson(events))
        return 0 if ok else 1

    try:
        decoded = decode_argv(raw_argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if decoded.version:
        try:
            from importlib.metadata import version as _version

            sys.stdout.write(f"scop {_version('scop')}\n")
        except Exception:
            sys.stdout.write("scop (unknown version)\n")
        return 0

    if decoded.output_path is not None:
        with Path(decoded.output_path).open("w", encoding="utf-8") as f:
            return _dispatch_and_render(decoded, f)
    return _dispatch_and_render(decoded, sys.stdout)


def main() -> None:
    """Installed entry point: scop = 'scop.clig:main'"""
    try:
        sys.exit(_main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stderr.fileno())
        sys.exit(0)


__all__ = ["main"]


if __name__ == "__main__":
    main()
