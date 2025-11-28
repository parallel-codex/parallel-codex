from __future__ import annotations

from pathlib import Path

import pytest

from parallel_codex.worktrees import SessionWorktree, WorktreeError, ensure_session_worktree


def init_git_repo(path: Path) -> None:
    from subprocess import run

    run(["git", "init"], cwd=path, check=True)
    run(["git", "config", "user.email", "you@example.com"], cwd=path, check=True)
    run(["git", "config", "user.name", "Your Name"], cwd=path, check=True)
    (path / "README.md").write_text("test\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=path, check=True)
    run(["git", "commit", "-m", "init"], cwd=path, check=True)


@pytest.mark.integration()
def test_ensure_session_worktree_creates_branch_and_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    agents_base = tmp_path / "agents"
    session_name = "session-1"

    worktree: SessionWorktree = ensure_session_worktree(
        repo_root=repo,
        agents_base=agents_base,
        session_name=session_name,
    )

    assert worktree.path.exists()
    assert worktree.path.name == session_name


def test_ensure_session_worktree_errors_when_not_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    agents_base = tmp_path / "agents"

    with pytest.raises(WorktreeError):
        ensure_session_worktree(
            repo_root=repo,
            agents_base=agents_base,
            session_name="s",
        )


