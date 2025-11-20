"""Textual TUI for managing multiple Codex MCP sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Input, Static

from ..mcp_client import CodexEvent, CodexMCP, configure_logging
from ..worktrees import SessionWorktree, ensure_session_worktree
from .session_manager import SessionManager
from .widgets import SessionPane, SessionRow


@dataclass(slots=True)
class AppConfig:
    repo_root: Path
    agents_base: Path
    model: str = "gpt-5-codex"
    sandbox: str = "workspace-write"


class ParallelCodexApp(App[None]):
    """Main Textual application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #session-row {
        height: 1fr;
    }

    .session-input {
        height: 3;
        border: none;
        padding: 0 1;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+tab", "cycle_session", "Next session"),
        Binding("ctrl+w", "close_session", "Close session"),
        Binding("escape", "focus_input", "Focus input"),
    ]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._sessions = SessionManager()
        self._mcp = CodexMCP()
        self._session_counter = 0
        self._event_tasks: list[asyncio.Task[None]] = []
        self._waiting_for_session_id: "asyncio.Queue" = asyncio.Queue()

    # ------------------------------------------------------------------
    # Textual lifecycle
    # ------------------------------------------------------------------
    async def on_mount(self) -> None:
        configure_logging()
        await self._mcp.start()
        # Start a task to route MCP notifications into the UI.
        events_task = asyncio.create_task(self._event_router(), name="codex-event-router")
        self._event_tasks.append(events_task)
        # Start with a single session by default.
        await self._ensure_session()

    async def on_shutdown(self) -> None:
        for task in self._event_tasks:
            task.cancel()
        await self._mcp.stop()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield SessionRow()
        yield Footer()

    # ------------------------------------------------------------------
    # Session management helpers
    # ------------------------------------------------------------------
    async def _ensure_session(self) -> SessionPane:
        """Create a new logical session and associated UI pane."""

        self._session_counter += 1
        session_name = f"session-{self._session_counter}"
        model = self._sessions.create_session(session_name)

        # Ensure git worktree for this session.
        worktree: SessionWorktree = ensure_session_worktree(
            repo_root=self._config.repo_root,
            agents_base=self._config.agents_base,
            session_name=session_name,
        )
        model.branch_name = worktree.branch_name
        model.workspace_path = worktree.path

        row = self.query_one(SessionRow)
        pane = SessionPane(session_name)
        row.mount(pane)

        # Ensure we don't exceed three panes; overflow sessions can be added as tabs later.
        children = list(row.children)
        if len(children) > 3:
            # For now, simply hide additional panes from view.
            for extra in children[3:]:
                extra.display = False

        self._sessions.focus(session_name)
        self._update_focus_visuals()
        return pane

    def _get_focused_pane(self) -> Optional[SessionPane]:
        focused = self._sessions.focused
        if focused is None:
            return None
        row = self.query_one(SessionRow)
        for pane in row.children:
            if isinstance(pane, SessionPane) and pane.id == focused.name:
                return pane
        return None

    def _update_focus_visuals(self) -> None:
        row = self.query_one(SessionRow)
        focused = self._sessions.focused
        for pane in row.children:
            if isinstance(pane, SessionPane):
                pane.is_focused = focused is not None and pane.id == focused.name

    # ------------------------------------------------------------------
    # Actions / key bindings
    # ------------------------------------------------------------------
    async def action_new_session(self) -> None:
        await self._ensure_session()
        self._focus_current_input()

    def action_cycle_session(self) -> None:
        self._sessions.cycle_focus(forward=True)
        self._update_focus_visuals()
        self._focus_current_input()

    def action_focus_session_1(self) -> None:
        self._sessions.focus_by_index(0)
        self._update_focus_visuals()
        self._focus_current_input()

    def action_focus_session_2(self) -> None:
        self._sessions.focus_by_index(1)
        self._update_focus_visuals()
        self._focus_current_input()

    def action_focus_session_3(self) -> None:
        self._sessions.focus_by_index(2)
        self._update_focus_visuals()
        self._focus_current_input()

    def action_close_session(self) -> None:
        focused = self._sessions.focused
        if focused is None:
            return
        row = self.query_one(SessionRow)
        pane = self._get_focused_pane()
        if pane is not None:
            pane.remove()
        self._sessions.close_session(focused.name)
        self._update_focus_visuals()
        self._focus_current_input()

    def _focus_current_input(self) -> None:
        pane = self._get_focused_pane()
        if pane is not None:
            pane.focus_input()

    def action_focus_input(self) -> None:
        self._focus_current_input()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    @on(Input.Submitted)
    async def _on_prompt_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""

        pane = event.input.query_ancestor(SessionPane)
        if pane is None:
            return

        # Ensure session focus follows the pane where input occurred.
        if pane.id is not None:
            self._sessions.focus(pane.id)
            self._update_focus_visuals()

        pane.add_user_message(prompt)

        model = self._sessions.focused
        if model is None:
            return

        if model.session_id is None:
            # Start a new Codex session.
            config = {
                "model": self._config.model,
                "workspace_path": str(model.workspace_path) if model.workspace_path else None,
                "sandbox": self._config.sandbox,
            }
            # Record that this model is waiting on a session_configured event.
            await self._waiting_for_session_id.put(model)
            task = asyncio.create_task(self._run_codex_call(model, pane, prompt, config))
        else:
            task = asyncio.create_task(self._run_codex_reply(model, pane, prompt))

        self._event_tasks.append(task)

    async def _run_codex_call(
        self,
        model,
        pane: SessionPane,
        prompt: str,
        config: dict,
    ) -> None:
        result = await self._mcp.call_codex(prompt, config=config)
        # The final result is expected to contain the assistant message; we treat it as markdown.
        text = result.get("content") or str(result)
        pane.add_markdown_message(text)

        # Session id will be bound asynchronously by the event router.

    async def _run_codex_reply(
        self,
        model,
        pane: SessionPane,
        prompt: str,
    ) -> None:
        assert model.session_id is not None
        result = await self._mcp.reply(model.session_id, prompt)
        text = result.get("content") or str(result)
        pane.add_markdown_message(text)

    # ------------------------------------------------------------------
    # MCP event routing
    # ------------------------------------------------------------------
    async def _event_router(self) -> None:
        """Background task that consumes MCP notifications and updates the UI."""

        queue = self._mcp.get_global_event_queue()
        while True:
            event: CodexEvent = await queue.get()
            method = event.raw.get("method")

            if method == "session_configured":
                session_id = event.session_id
                if session_id is None:
                    continue
                # Assign this session id to the next model waiting for one.
                try:
                    model = self._waiting_for_session_id.get_nowait()
                except asyncio.QueueEmpty:
                    continue
                model.session_id = session_id
                self.log(f"Session configured: {model.name} -> {session_id}")

            # Progress and other notifications can be surfaced later.
