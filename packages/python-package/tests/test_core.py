"""Tests for the Parallel Codex core helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from parallel_codex.core import (
    BRANCH_METADATA,
    WorktreePlan,
    ensure_worktree,
    find_worktree,
    format_plan,
    list_worktrees,
    plan_worktree,
    prune_worktree,
)


@pytest.fixture()
def base_dir(tmp_path: Path) -> Path:
    target = tmp_path / "agents"
    target.mkdir()
    return target


def test_plan_worktree_creates_expected_plan(base_dir: Path) -> None:
    plan = plan_worktree(base_dir, "agent-a", "feature/awesome")
    assert plan == WorktreePlan(
        name="agent-a",
        branch="feature/awesome",
        path=base_dir / "agent-a",
    )


def test_format_plan(base_dir: Path) -> None:
    plan = plan_worktree(base_dir, "reviewer", "main")
    summary = format_plan(plan)
    assert str(plan.path) in summary
    assert "agent=reviewer" in summary
    assert "branch=main" in summary


def test_ensure_worktree_creates_metadata(base_dir: Path) -> None:
    plan = plan_worktree(base_dir, "lint", "lint-branch")
    ensure_worktree(plan)
    branch_file = plan.path / BRANCH_METADATA
    assert branch_file.exists()
    assert branch_file.read_text(encoding="utf-8").strip() == "lint-branch"


def test_list_worktrees_discovers_plans(base_dir: Path) -> None:
    plan_a = plan_worktree(base_dir, "alpha", "main")
    plan_b = plan_worktree(base_dir, "beta", "feature/beta")
    ensure_worktree(plan_a)
    ensure_worktree(plan_b)

    plans = list_worktrees(base_dir)
    assert [plan.name for plan in plans] == ["alpha", "beta"]


def test_find_worktree_returns_none_when_missing(base_dir: Path) -> None:
    assert find_worktree(base_dir, "ghost") is None


def test_find_worktree_returns_plan_when_present(base_dir: Path) -> None:
    plan = plan_worktree(base_dir, "alpha", "main")
    ensure_worktree(plan)
    found = find_worktree(base_dir, "alpha")
    assert found == plan


def test_prune_worktree_removes_metadata_only(base_dir: Path) -> None:
    plan = plan_worktree(base_dir, "agent", "branch")
    ensure_worktree(plan)
    prune_worktree(plan, remove_path=False)
    assert not (plan.path / BRANCH_METADATA).exists()
    assert plan.path.exists()


def test_prune_worktree_can_remove_directory(base_dir: Path) -> None:
    plan = plan_worktree(base_dir, "agent", "branch")
    ensure_worktree(plan)
    prune_worktree(plan, remove_path=True)
    assert not plan.path.exists()
