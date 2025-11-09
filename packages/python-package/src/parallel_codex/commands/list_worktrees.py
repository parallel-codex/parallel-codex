"""`parallel-codex list` implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace, _SubParsersAction

from ..core import format_plan, list_worktrees
from . import add_common_arguments


def register(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "list",
        help="List discovered agent worktrees",
    )
    add_common_arguments(parser)
    parser.add_argument(
        "--agent",
        help="Filter results to a specific agent name",
    )
    parser.set_defaults(handler=execute)


def execute(args: Namespace) -> int:
    plans = list_worktrees(args.base_dir)
    if args.agent:
        plans = [plan for plan in plans if plan.name == args.agent]

    if not plans:
        print("No worktrees found.")
        return 0

    for plan in plans:
        print(format_plan(plan))
    return 0
