"""Textual TUI for managing multiple Codex MCP sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Input, Static

from ..mcp_client import CodexEvent, CodexEventType, CodexMCP, configure_logging
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
        background: #050301;
    }

    #session-row {
        height: 1fr;
        padding: 0 1;
        background: #050301;
    }

    .session-pane {
        padding: 0 1 0 1;
        border: solid #2c1c0c;
        background: #080503;
        margin-right: 1;
    }

    .session-pane:last-child {
        margin-right: 0;
    }

    .session-pane--focused {
        border: solid #f28c28;
    }

    .session-messages {
        height: 1fr;
        padding: 0 1 0 1;
        border: solid #1a1007;
        background: #050301;
    }

    .message {
        padding: 0 1;
        margin-bottom: 1;
        border: solid #2c1c0c;
        background: #0d0804;
    }

    .message-user {
        border: solid #f28c28;
        background: #201105;
    }

    .message-assistant {
        border: solid #3a2610;
        background: #110804;
    }

    .message-event {
        border: dashed #3a2610;
        background: #0a0502;
        color: #d0b089;
    }

    .session-input {
        height: 3;
        border: solid #f28c28;
        padding: 0 1;
        margin: 0 1 1 1;
        background: #050301;
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
        return self._get_pane_by_name(focused.name)

    def _get_pane_by_name(self, name: str) -> Optional[SessionPane]:
        row = self.query_one(SessionRow)
        for pane in row.children:
            if isinstance(pane, SessionPane) and pane.id == name:
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
            self.log(
                f"MCP event: type={event.event_type} method={method!r} "
                f"is_notification={event.is_notification} raw={event.raw}"
            )

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
                continue

            if event.event_type == CodexEventType.PROGRESS:
                self.log(f"MCP progress event: {event.raw}")
                self._handle_progress_notification(event)
                continue

            if event.event_type == CodexEventType.LOGGING:
                self.log(f"MCP logging event: {event.raw}")
                self._handle_logging_notification(event)
                continue

            # Any other notification types are surfaced as generic events so that
            # intermediate activity is still visible in the UI and logs.
            if event.is_notification:
                self.log(f"MCP notification event (unhandled): {event.raw}")
                self._handle_generic_notification(event)
                continue

    def _pane_for_event(self, event: CodexEvent) -> Optional[SessionPane]:
        """Resolve which session pane should render a notification."""

        session_id = event.session_id
        if session_id is None and event.related_request_id is not None:
            timeline = self._mcp.event_tracker.get_request_timeline(event.related_request_id)
            if timeline is not None:
                session_id = timeline.session_id

        if session_id is None:
            sessions = self._sessions.all_sessions()
            if len(sessions) == 1:
                return self._get_pane_by_name(sessions[0].name)
            focused = self._get_focused_pane()
            if focused is not None:
                return focused
            if sessions:
                return self._get_pane_by_name(sessions[0].name)
            return None

        model = self._sessions.find_by_session_id(session_id)
        if model is None:
            return None

        return self._get_pane_by_name(model.name)

    def _notification_payload(self, event: CodexEvent) -> dict:
        params = event.raw.get("params") or {}
        msg = params.get("msg")
        if isinstance(msg, dict):
            return msg
        return params

    def _handle_progress_notification(self, event: CodexEvent) -> None:
        pane = self._pane_for_event(event)
        if pane is None:
            self.log(f"Discarding progress event; no pane available: {event.raw}")
            return

        payload = self._notification_payload(event)
        progress = payload.get("progress") or payload.get("current")
        total = payload.get("total") or payload.get("max")
        message = payload.get("message") or payload.get("data") or "Working..."

        pct = self._percent_complete(progress, total)
        safe_message = escape(str(message))
        pane.add_event_message(f"[bold yellow]PROGRESS[/] {pct}% {safe_message}")

    def _handle_logging_notification(self, event: CodexEvent) -> None:
        pane = self._pane_for_event(event)
        if pane is None:
            self.log(f"Discarding logging event; no pane available: {event.raw}")
            return

        payload = self._notification_payload(event)
        level = str(payload.get("level", "info")).upper()
        data = payload.get("data") or payload.get("message") or ""
        snippet = escape(self._truncate(str(data)))
        pane.add_event_message(f"[cyan]{level}[/] {snippet}")

    def _handle_generic_notification(self, event: CodexEvent) -> None:
        """Render generic MCP notifications that are not classified as progress/logging."""

        pane = self._pane_for_event(event)
        if pane is None:
            self.log(f"Discarding generic event; no pane available: {event.raw}")
            return

        payload = self._notification_payload(event)
        method = str(event.raw.get("method", "notification"))
        message = (
            payload.get("message")
            or payload.get("data")
            or payload.get("msg")
            or payload.get("text")
            or payload
        )
        snippet = escape(self._truncate(str(message)))
        pane.add_event_message(f"[magenta]{method}[/] {snippet}")

    @staticmethod
    def _percent_complete(progress: Optional[float], total: Optional[float]) -> int:
        try:
            progress_val = float(progress if progress is not None else 0)
            total_val = float(total) if total not in (None, 0) else None
        except (TypeError, ValueError):
            return 0

        if total_val is None:
            return int(progress_val)

        if total_val <= 0:
            return 0

        ratio = max(0.0, min(1.0, progress_val / total_val))
        return int(ratio * 100)

    @staticmethod
    def _truncate(value: str, limit: int = 96) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3].rstrip() + "..."
