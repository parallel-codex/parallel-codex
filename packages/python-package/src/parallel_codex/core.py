"""Core functionality for orchestrating Parallel Codex agents."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

BRANCH_METADATA = ".parallel-codex-branch"


@dataclass(slots=True)
class WorktreePlan:
    """Describes the desired state for an agent worktree."""

    name: str
    branch: str
    path: Path


def plan_worktree(base_dir: Path, agent_name: str, branch: str) -> WorktreePlan:
    """Create a worktree plan rooted within ``base_dir``.

    Args:
        base_dir: Root directory containing agent worktrees.
        agent_name: Identifier for the Codex agent.
        branch: Target git branch for the worktree.

    Returns:
        A :class:`WorktreePlan` describing the desired worktree placement.
    """

    worktree_path = base_dir / agent_name
    return WorktreePlan(name=agent_name, branch=branch, path=worktree_path)


def format_plan(plan: WorktreePlan) -> str:
    """Render a human-friendly summary of a worktree plan."""

    return f"agent={plan.name} branch={plan.branch} path={plan.path}"


def ensure_worktree(plan: WorktreePlan) -> None:
    """Materialise metadata for a planned worktree."""

    plan.path.mkdir(parents=True, exist_ok=True)
    (plan.path / BRANCH_METADATA).write_text(f"{plan.branch}\n", encoding="utf-8")


def list_worktrees(base_dir: Path) -> list[WorktreePlan]:
    """Enumerate worktree plans stored under ``base_dir``."""

    if not base_dir.exists():
        return []

    plans: list[WorktreePlan] = []
    for candidate in base_dir.iterdir():
        if not candidate.is_dir():
            continue

        branch = _load_branch(candidate)
        if branch is None:
            continue
        plans.append(WorktreePlan(name=candidate.name, branch=branch, path=candidate))

    return sorted(plans, key=lambda plan: plan.name)


def find_worktree(base_dir: Path, agent_name: str) -> WorktreePlan | None:
    """Return the stored worktree plan for ``agent_name`` if present."""

    candidate = base_dir / agent_name
    branch = _load_branch(candidate)
    if branch is None:
        return None
    return WorktreePlan(name=agent_name, branch=branch, path=candidate)


def prune_worktree(plan: WorktreePlan, *, remove_path: bool = False) -> None:
    """Remove stored metadata (and optionally the directory) for a plan."""

    branch_file = plan.path / BRANCH_METADATA
    if branch_file.exists():
        branch_file.unlink()

    if remove_path and plan.path.exists():
        shutil.rmtree(plan.path)


def _load_branch(path: Path) -> str | None:
    branch_file = path / BRANCH_METADATA
    if not branch_file.exists():
        return None
    raw = branch_file.read_text(encoding="utf-8").strip()
    return raw or None
