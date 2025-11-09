"""Command modules for the Parallel Codex CLI."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path


def add_common_arguments(parser: ArgumentParser) -> None:
    """Attach arguments shared by multiple subcommands."""

    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("./.agents"),
        help="Directory where agent worktrees are stored (default: ./.agents)",
    )


def register(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    """Import command modules and register their subparsers."""

    from . import list_worktrees, plan, prune

    plan.register(subparsers)
    list_worktrees.register(subparsers)
    prune.register(subparsers)
