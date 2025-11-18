"""Helpers for managing per-session git worktrees for Parallel Codex.

This module is deliberately separate from the CLI-oriented ``pcodex`` helper so
that the TUI can reuse the logic without depending on tmux or terminal UX.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class WorktreeError(RuntimeError):
    """Raised when a git worktree operation fails."""


@dataclass(slots=True)
class SessionWorktree:
    """Metadata describing a session-specific git worktree."""

    session_name: str
    branch_name: str
    path: Path


def format_session_branch(session_name: str) -> str:
    """Return a branch name for the given session.

    The naming scheme is intentionally simple and predictable so that users can
    interact with session branches directly via git.
    """

    return f"pcx/{session_name}"


def ensure_session_worktree(
    repo_root: Path,
    agents_base: Path,
    session_name: str,
    *,
    branch_name: Optional[str] = None,
) -> SessionWorktree:
    """Create or reuse a git worktree for a Codex session.

    Args:
        repo_root: Path to the main git repository root.
        agents_base: Base directory under which agent worktrees live.
        session_name: Identifier for this Codex session.
        branch_name: Optional explicit branch name. If omitted, a default
            derived from ``session_name`` is used.

    Returns:
        A :class:`SessionWorktree` describing the ensured worktree.

    Raises:
        WorktreeError: if git is missing, repo_root is not a git repo, or the
            worktree operation fails.
    """

    repo_root = repo_root.resolve()
    agents_base = agents_base.resolve()
    if not (repo_root / ".git").exists():
        raise WorktreeError(
            f"{repo_root} does not look like a git repository (no .git found). "
            "Ensure you are pointing at the root of your git repo (for example by "
            "running from the repo root, passing --repo, or setting "
            "PARALLEL_CODEX_REPO_ROOT)."
        )

    target_dir = agents_base / session_name
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    branch = branch_name or format_session_branch(session_name)

    # If the directory already exists, assume the worktree is already set up and
    # let git manage the details. This mirrors the behaviour of pcodex.ensure_worktree
    # which prefers idempotence over strict erroring.
    if not target_dir.exists():
        try:
            _run_git(
                [
                    "worktree",
                    "add",
                    "-B",
                    branch,
                    str(target_dir),
                ],
                cwd=repo_root,
            )
        except subprocess.CalledProcessError as exc:
            raise WorktreeError(
                f"Failed to create worktree for session '{session_name}' in {target_dir}: {exc}"
            ) from exc

    return SessionWorktree(session_name=session_name, branch_name=branch, path=target_dir)


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


