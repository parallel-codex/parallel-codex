from __future__ import annotations

from pathlib import Path

import pytest

from parallel_codex import cli


def parse_cli_args(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
    extra: list[str] | None = None,
):
    """Helper to construct parsed args for the simplified CLI."""

    if env_value is None:
        monkeypatch.delenv("PARALLEL_CODEX_REPO_ROOT", raising=False)
    else:
        monkeypatch.setenv("PARALLEL_CODEX_REPO_ROOT", env_value)

    parser = cli.build_parser()
    args = parser.parse_args(extra or [])
    assert args.command == "tui"
    return args


def test_tui_repo_default_uses_cwd_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """If PARALLEL_CODEX_REPO_ROOT is not set, default repo is the current directory."""

    args = parse_cli_args(monkeypatch, None)

    assert args.repo == Path(".")


def test_tui_repo_default_uses_env_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """If PARALLEL_CODEX_REPO_ROOT is set, it becomes the default repo path."""

    env_path = "/tmp/parallel-codex-repo"

    args = parse_cli_args(monkeypatch, env_path)

    assert args.repo == Path(env_path)


def test_tui_dev_log_panel_flag_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """The --dev-log-panel flag should be accepted and default to False."""

    args = parse_cli_args(monkeypatch, None)
    assert args.dev_log_panel is False

    parser = cli.build_parser()
    args_with_flag = parser.parse_args(["--dev-log-panel"])
    assert args_with_flag.command == "tui"
    assert args_with_flag.dev_log_panel is True


def test_explicit_command_argument_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    """The positional 'tui' argument is still allowed for backwards compatibility."""

    parser = cli.build_parser()
    args = parser.parse_args(["tui"])

    assert args.command == "tui"
