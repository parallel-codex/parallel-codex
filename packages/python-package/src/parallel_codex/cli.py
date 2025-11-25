"""Command-line entry point for launching the Parallel Codex TUI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .tui.app import AppConfig, ParallelCodexApp


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for launching the TUI."""

    def _default_repo() -> Path:
        env_value = os.environ.get("PARALLEL_CODEX_REPO_ROOT")
        return Path(env_value) if env_value else Path(".")

    parser = argparse.ArgumentParser(
        prog="parallel-codex",
        description="Launch the Parallel Codex Textual TUI",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"parallel-codex {__version__}",
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="tui",
        choices=("tui",),
        help="Optional command selector (only 'tui' is available).",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=_default_repo(),
        help=(
            "Path to the main git repository "
            "(default: current directory or $PARALLEL_CODEX_REPO_ROOT)"
        ),
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
    parser.add_argument(
        "--dev-log-panel",
        action="store_true",
        help="Show the live developer log panel inside the TUI",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run the TUI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "tui":  # pragma: no cover - enforced by argparse choices
        parser.error(f"Unsupported command: {args.command}")

    config = AppConfig(
        repo_root=args.repo,
        agents_base=args.agents_base,
        model=args.model,
        sandbox=args.sandbox,
        show_log_panel=args.dev_log_panel,
    )
    app = ParallelCodexApp(config)
    app.run()
    return 0


def run(argv: list[str] | None = None) -> None:
    """Execute the CLI and exit the current process."""

    sys.exit(main(argv))


if __name__ == "__main__":  # pragma: no cover
    run()
