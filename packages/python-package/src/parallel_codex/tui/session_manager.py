"""In-memory session registry for the Parallel Codex TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SessionModel:
    """Represents a logical Codex session in the TUI."""

    # Human-friendly label shown in the UI (e.g., "Session 1").
    name: str
    # Codex session_id once configured; None until the first reply.
    session_id: str | None = None
    # Branch and workspace for this session's git worktree.
    branch_name: str | None = None
    workspace_path: Path | None = None


class SessionManager:
    """Tracks TUI sessions, their layout slots, and mapping to Codex ids."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionModel] = {}
        self._session_order: list[str] = []
        self._focused: str | None = None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_session(self, name: str) -> SessionModel:
        model = SessionModel(name=name)
        self._sessions[name] = model
        self._session_order.append(name)
        if self._focused is None:
            self._focused = name
        return model

    def close_session(self, name: str) -> None:
        self._sessions.pop(name, None)
        if name in self._session_order:
            self._session_order.remove(name)
        if self._focused == name:
            self._focused = self._session_order[0] if self._session_order else None

    def get(self, name: str) -> SessionModel | None:
        return self._sessions.get(name)

    def all_sessions(self) -> list[SessionModel]:
        return [self._sessions[n] for n in self._session_order]

    # ------------------------------------------------------------------
    # Focus & mapping
    # ------------------------------------------------------------------
    def focus(self, name: str) -> None:
        if name in self._sessions:
            self._focused = name

    def focus_by_index(self, index: int) -> None:
        if 0 <= index < len(self._session_order):
            self._focused = self._session_order[index]

    def cycle_focus(self, *, forward: bool = True) -> None:
        if not self._session_order or self._focused is None:
            return
        current_idx = self._session_order.index(self._focused)
        if forward:
            new_idx = (current_idx + 1) % len(self._session_order)
        else:
            new_idx = (current_idx - 1) % len(self._session_order)
        self._focused = self._session_order[new_idx]

    @property
    def focused(self) -> SessionModel | None:
        if self._focused is None:
            return None
        return self._sessions.get(self._focused)

    def find_by_session_id(self, session_id: str) -> SessionModel | None:
        for model in self._sessions.values():
            if model.session_id == session_id:
                return model
        return None



