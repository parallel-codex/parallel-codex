from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pytest

from parallel_codex.commands import tui


def build_tui_args(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> Path:
    """Helper to construct parsed args for the tui subcommand."""

    if env_value is None:
        monkeypatch.delenv("PARALLEL_CODEX_REPO_ROOT", raising=False)
    else:
        monkeypatch.setenv("PARALLEL_CODEX_REPO_ROOT", env_value)

    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    tui.register(subparsers)

    args = parser.parse_args(["tui"])
    assert args.cmd == "tui"
    return args.repo


def test_tui_repo_default_uses_cwd_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """If PARALLEL_CODEX_REPO_ROOT is not set, default repo is the current directory."""

    repo = build_tui_args(monkeypatch, None)

    assert repo == Path(".")


def test_tui_repo_default_uses_env_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """If PARALLEL_CODEX_REPO_ROOT is set, it becomes the default repo path."""

    env_path = "/tmp/parallel-codex-repo"

    repo = build_tui_args(monkeypatch, env_path)

    assert repo == Path(env_path)


