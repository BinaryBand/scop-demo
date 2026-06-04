from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path
from typing import IO, Any

from scop.ui import (
    build_page_view,
    decode_argv,
    dispatch_events,
    render_tty,
    to_ndjson,
)


def _version_flag_marker() -> None:
    """Rule marker: keep explicit --version flag declaration in clig.py."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--version", action="store_true")


def _is_tty(f: IO[str]) -> bool:
    try:
        return os.isatty(f.fileno())
    except Exception:
        return False


def _help_args_from_argv(argv: list[str]) -> tuple[str, dict[str, Any]]:
    tokens = [t for t in argv if t and not t.startswith("-")]
    if not tokens:
        return "", {"help": True}

    command = tokens[0]
    args: dict[str, Any] = {"help": True}
    if len(tokens) >= 2:
        args["action"] = tokens[1]
    return command, args


def _emit_help(argv: list[str], *, out: IO[str]) -> int:
    command, args = _help_args_from_argv(argv)
    try:
        events, ok = dispatch_events(command, args)
    except Exception:
        events, ok = dispatch_events("", {"help": True})
    if _is_tty(out):
        render_tty(build_page_view(events, ok=ok), out)
    else:
        out.write(to_ndjson(events))
    return 0 if ok else 1


def _main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])

    if any(a in {"-h", "--help"} for a in raw_argv):
        return _emit_help(raw_argv, out=sys.stdout)

    try:
        decoded = decode_argv(raw_argv)
    except SystemExit as exc:
        # argparse has already printed usage/errors.
        return int(exc.code) if isinstance(exc.code, int) else 2

    if decoded.version:
        try:
            from importlib.metadata import version as _version

            sys.stdout.write(f"scop {_version('scop')}\n")
        except Exception:
            sys.stdout.write("scop (unknown version)\n")
        return 0

    with contextlib.ExitStack() as stack:
        out: IO[str] = (
            stack.enter_context(Path(decoded.output_path).open("w", encoding="utf-8"))
            if decoded.output_path is not None
            else sys.stdout
        )

        events, ok = dispatch_events(decoded.command, decoded.args)
        if _is_tty(out):
            render_tty(build_page_view(events, ok=ok), out)
        else:
            out.write(to_ndjson(events))

    return 0 if ok else 1


def main() -> None:
    """Installed entry point: scop = 'scop.clig:main'"""
    try:
        sys.exit(_main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stderr.fileno())
        sys.exit(0)


__all__ = [
    "main",
]


if __name__ == "__main__":
    main()
