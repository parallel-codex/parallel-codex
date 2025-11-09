"""`parallel-codex plan` implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace, _SubParsersAction

from ..core import ensure_worktree, format_plan, plan_worktree
from . import add_common_arguments


def register(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "plan",
        help="Create or update the plan for a Codex agent worktree",
    )
    add_common_arguments(parser)
    parser.add_argument("agent", help="Agent identifier to plan")
    parser.add_argument("branch", help="Git branch the agent should track")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Materialise the plan by creating the worktree folder and metadata",
    )
    parser.set_defaults(handler=execute)


def execute(args: Namespace) -> int:
    plan = plan_worktree(args.base_dir, args.agent, args.branch)
    if args.ensure:
        ensure_worktree(plan)
    print(format_plan(plan))
    return 0
