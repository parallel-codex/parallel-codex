"""Command-line interface entry point for the Parallel Codex toolkit."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from . import __version__
from .commands import register as register_commands


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""

    parser = argparse.ArgumentParser(
        prog="parallel-codex",
        description="Utilities for orchestrating Parallel Codex agents",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"parallel-codex {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    register_commands(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Return an exit code after executing the requested subcommand."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[..., int] | None = getattr(args, "handler", None)
    if handler is None:
        parser.error("No handler registered for command.")
    return handler(args)


def run(argv: list[str] | None = None) -> None:
    """Execute the CLI and exit the current process."""

    sys.exit(main(argv))


if __name__ == "__main__":  # pragma: no cover
    run()
