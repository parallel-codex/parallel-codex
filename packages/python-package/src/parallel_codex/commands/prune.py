"""`parallel-codex prune` implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace, _SubParsersAction

from ..core import find_worktree, prune_worktree
from . import add_common_arguments


def register(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "prune",
        help="Remove plan metadata (and optionally the worktree directory)",
    )
    add_common_arguments(parser)
    parser.add_argument("agent", help="Agent identifier to prune")
    parser.add_argument(
        "--prune-dir",
        action="store_true",
        help="Delete the worktree directory in addition to metadata",
    )
    parser.set_defaults(handler=execute)


def execute(args: Namespace) -> int:
    plan = find_worktree(args.base_dir, args.agent)
    if plan is None:
        print(f"No plan found for agent '{args.agent}'.")
        return 1

    prune_worktree(plan, remove_path=args.prune_dir)
    print(f"Pruned plan for agent '{args.agent}'.")
    return 0
