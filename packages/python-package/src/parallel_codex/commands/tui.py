"""`parallel-codex tui` implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace, _SubParsersAction
from pathlib import Path

from ..tui.app import AppConfig, ParallelCodexApp


def register(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "tui",
        help="Launch the Parallel Codex Textual TUI",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to the main git repository (default: current directory)",
    )
    parser.add_argument(
        "--agents-base",
        type=Path,
        default=Path("./.agents"),
        help="Base directory for session worktrees (default: ./.agents)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-codex",
        help="Codex model to use (default: gpt-5-codex)",
    )
    parser.add_argument(
        "--sandbox",
        default="workspace-write",
        help="Codex sandbox mode (default: workspace-write)",
    )
    parser.set_defaults(handler=execute)


def execute(args: Namespace) -> int:
    """Launch the Textual TUI."""

    config = AppConfig(
        repo_root=args.repo,
        agents_base=args.agents_base,
        model=args.model,
        sandbox=args.sandbox,
    )
    app = ParallelCodexApp(config)
    app.run()
    return 0


