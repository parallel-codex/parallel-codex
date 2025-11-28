"""Textual TUI for managing multiple Codex MCP sessions."""

from __future__ import annotations

import asyncio
import io
import logging
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Input, Log

from ..mcp_client import CodexEvent, CodexEventType, CodexMCP, configure_logging
from ..worktrees import SessionWorktree, ensure_session_worktree
from .session_manager import SessionManager
from .widgets import SessionPane, SessionRow

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class AppConfig:
    repo_root: Path
    agents_base: Path
    model: str = "gpt-5-codex"
    sandbox: str = "workspace-write"
    show_log_panel: bool = False


class _TextualLogHandler(logging.Handler):
    """Logging handler that forwards records into a Textual Log widget."""

    def __init__(self, app: ParallelCodexApp) -> None:
        super().__init__()
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - extremely defensive
            return
        self._app._submit_dev_log_line(message)


class _TextualStreamTap(io.TextIOBase):
    """Mirror stdout/stderr writes into the in-app log panel."""

    def __init__(
        self,
        app: ParallelCodexApp,
        stream: TextIO | None,
        *,
        label: str,
    ) -> None:
        super().__init__()
        self._app = app
        self._stream = stream
        self._label = label
        self._buffer: str = ""

    def write(self, data: str) -> int:  # type: ignore[override]
        if not data:
            return 0
        if self._stream is not None:
            self._stream.write(data)

        text = data.replace("\r\n", "\n").replace("\r", "\n")
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(line)
        return len(data)

    def flush(self) -> None:  # type: ignore[override]
        if self._stream is not None:
            self._stream.flush()
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""

    @property
    def encoding(self) -> str:  # pragma: no cover - passthrough
        if self._stream is not None and getattr(self._stream, "encoding", None):
            return self._stream.encoding  # type: ignore[return-value]
        return "utf-8"

    def fileno(self) -> int:  # pragma: no cover - passthrough
        if self._stream is not None and hasattr(self._stream, "fileno"):
            return self._stream.fileno()  # type: ignore[return-value]
        raise OSError("Stream has no file descriptor")

    def isatty(self) -> bool:  # pragma: no cover - passthrough
        if self._stream is not None and hasattr(self._stream, "isatty"):
            return self._stream.isatty()
        return False

    def _emit(self, line: str) -> None:
        if not line:
            return

        message = f"[{self._label}] {line}"
        self._app._submit_dev_log_line(message)


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

    #dev-log {
        height: 8;
        border: solid #2c1c0c;
        background: #050301;
        margin: 0 1 1 1;
        padding: 0 1;
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
        self._request_to_model: dict[str, Any] = {}
        self._log_handler: _TextualLogHandler | None = None
        self._stdout_tap: _TextualStreamTap | None = None
        self._stderr_tap: _TextualStreamTap | None = None
        self._original_stdout: TextIO | None = None
        self._original_stderr: TextIO | None = None
        self._dev_log_widget: Log | None = None
        self._dev_log_buffer: deque[str] = deque(maxlen=2000)

    # ------------------------------------------------------------------
    # Textual lifecycle
    # ------------------------------------------------------------------
    async def on_mount(self) -> None:
        configure_logging()
        # Optionally mirror Python logs into the in-app dev log panel.
        if self._config.show_log_panel:
            self._enable_dev_console()
        await self._mcp.start()
        # Start a task to route MCP notifications into the UI.
        events_task = asyncio.create_task(self._event_router(), name="codex-event-router")
        self._event_tasks.append(events_task)
        # Start with a single session by default.
        await self._ensure_session()

    async def on_ready(self) -> None:
        if not self._config.show_log_panel:
            return
        try:
            self._dev_log_widget = self.query_one("#dev-log", Log)
        except NoMatches:
            self._dev_log_widget = None
        else:
            self._flush_dev_log_buffer()

    async def on_shutdown(self) -> None:
        for task in self._event_tasks:
            task.cancel()
        await self._mcp.stop()

        if self._config.show_log_panel:
            self._disable_dev_console()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield SessionRow()
            if self._config.show_log_panel:
                log_widget = Log(id="dev-log")
                log_widget.border_title = "Logs"
                yield log_widget
        yield Footer()

    def _attach_log_handler(self) -> None:
        """Attach a single shared handler that writes into the dev Log widget."""

        if self._log_handler is not None:
            return

        handler = _TextualLogHandler(self)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        self._log_handler = handler

    def _enable_dev_console(self) -> None:
        logging.getLogger().setLevel(logging.DEBUG)
        self._attach_log_handler()
        self._redirect_standard_streams()
        self._write_dev_log_line("[dev] Log console capturing logging + stdout/stderr")

    def _disable_dev_console(self) -> None:
        self._restore_standard_streams()
        if self._log_handler is not None:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._log_handler)
            self._log_handler = None

    def _redirect_standard_streams(self) -> None:
        if self._stdout_tap is not None or self._stderr_tap is not None:
            return

        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._stdout_tap = _TextualStreamTap(self, self._original_stdout, label="stdout")
        self._stderr_tap = _TextualStreamTap(self, self._original_stderr, label="stderr")
        sys.stdout = self._stdout_tap  # type: ignore[assignment]
        sys.stderr = self._stderr_tap  # type: ignore[assignment]

    def _restore_standard_streams(self) -> None:
        if self._stdout_tap is not None:
            self._stdout_tap.flush()

        if self._stderr_tap is not None:
            self._stderr_tap.flush()

        if self._original_stdout is not None:
            sys.stdout = self._original_stdout  # type: ignore[assignment]
            self._original_stdout = None

        if self._original_stderr is not None:
            sys.stderr = self._original_stderr  # type: ignore[assignment]
            self._original_stderr = None

        self._stdout_tap = None
        self._stderr_tap = None

    def _submit_dev_log_line(self, line: str) -> None:
        if not self._config.show_log_panel:
            return

        def _deliver() -> None:
            self._write_dev_log_line(line)

        try:
            self.call_from_thread(_deliver)
        except RuntimeError:
            self._dev_log_buffer.append(line)

    def _write_dev_log_line(self, line: str) -> None:
        if not line:
            return
        widget = self._dev_log_widget
        if widget is None:
            self._dev_log_buffer.append(line)
            return
        widget.write_line(line)

    def _flush_dev_log_buffer(self) -> None:
        widget = self._dev_log_widget
        if widget is None:
            return
        while self._dev_log_buffer:
            widget.write_line(self._dev_log_buffer.popleft())

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
        LOG.info(
            "Session %s ready (branch=%s, workspace=%s)",
            session_name,
            worktree.branch_name,
            worktree.path,
        )

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

    def _get_focused_pane(self) -> SessionPane | None:
        focused = self._sessions.focused
        if focused is None:
            return None
        return self._get_pane_by_name(focused.name)

    def _get_pane_by_name(self, name: str) -> SessionPane | None:
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
        pane.start_processing()
        pane_identifier = pane.id or "<unknown>"
        LOG.info("Prompt submitted in %s: %s", pane_identifier, self._truncate(prompt))

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
        request_id, future, send = self._mcp.prepare_codex_call(prompt, config=config)

        # Track the model by request_id so we can route session_configured events.
        # We must register this BEFORE sending to avoid a race where events arrive
        # before registration.
        self._request_to_model[request_id] = model

        try:
            await send()
            result = await future
            # Pass raw content list; pane.finish_processing will normalize it.
            content = result.get("content") or result
            pane.finish_processing(content)
        finally:
            self._request_to_model.pop(request_id, None)

        # Session id will be bound asynchronously by the event router.

    async def _run_codex_reply(
        self,
        model,
        pane: SessionPane,
        prompt: str,
    ) -> None:
        assert model.session_id is not None
        request_id, future, send = self._mcp.prepare_reply(model.session_id, prompt)

        # Track pending request so fallback logic in _pane_for_event can find it
        self._request_to_model[request_id] = model

        try:
            await send()
            result = await future
            content = result.get("content") or result
            pane.finish_processing(content)
        finally:
            self._request_to_model.pop(request_id, None)

    # ------------------------------------------------------------------
    # MCP event routing
    # ------------------------------------------------------------------
    async def _event_router(self) -> None:
        """Background task that consumes MCP notifications and updates the UI."""

        queue = self._mcp.get_global_event_queue()
        while True:
            event: CodexEvent = await queue.get()
            method = event.raw.get("method")
            LOG.debug(
                f"MCP event: type={event.event_type} method={method!r} "
                f"is_notification={event.is_notification} raw={event.raw}"
            )

            if method == "session_configured":
                session_id = event.session_id
                request_id = event.related_request_id

                if session_id and request_id:
                    model = self._request_to_model.get(request_id)
                    if model:
                        model.session_id = session_id
                        LOG.info(
                            "Session configured: %s -> %s (req=%s)",
                            model.name,
                            session_id,
                            request_id,
                        )
                continue

            if event.event_type == CodexEventType.PROGRESS:
                LOG.debug("MCP progress event: %s", event.raw)
                self._handle_progress_notification(event)
                continue

            if event.event_type == CodexEventType.LOGGING:
                LOG.debug("MCP logging event: %s", event.raw)
                self._handle_logging_notification(event)
                continue

            # Any other notification types are surfaced as generic events so that
            # intermediate activity is still visible in the UI and logs.
            if event.is_notification:
                # LOG.debug("MCP notification event (unhandled): %s", event.raw)
                self._handle_generic_notification(event)
                continue

    def _pane_for_event(self, event: CodexEvent) -> SessionPane | None:
        """Resolve which session pane should render a notification."""

        session_id = event.session_id

        # If no explicit session ID, try to infer from timeline or pending request.
        if session_id is None and event.related_request_id is not None:
            timeline = self._mcp.event_tracker.get_request_timeline(event.related_request_id)
            if timeline is not None:
                session_id = timeline.session_id

            # Fallback: check if we have a pending request for this model
            if session_id is None:
                model = self._request_to_model.get(event.related_request_id)
                if model:
                    return self._get_pane_by_name(model.name)

        if session_id is None:
            sessions = self._sessions.all_sessions()
            if len(sessions) == 1:
                return self._get_pane_by_name(sessions[0].name)
            # Dangerous fallback to focused pane removed to avoid concurrency issues.
            # If we can't map the event to a specific session, it's safer to drop it
            # than to display it in the wrong session.
            return None

        model = self._sessions.find_by_session_id(session_id)
        if model is None:
            # Fallback: check pending requests again if session ID didn't resolve to a model yet
            # (though normally session_configured should have updated the model)
            if event.related_request_id:
                model = self._request_to_model.get(event.related_request_id)

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
            LOG.debug("Discarding progress event; no pane available: %s", event.raw)
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
            LOG.debug("Discarding logging event; no pane available: %s", event.raw)
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
            LOG.debug("Discarding generic event; no pane available: %s", event.raw)
            return

        payload = self._notification_payload(event)
        msg_type = payload.get("type")

        # Specific event handling for Codex rich events
        # We use item_completed because item_started often lacks the summary_text
        # info we need for the title.
        if msg_type == "item_completed":
            item = payload.get("item", {})
            if item.get("type") == "Reasoning":
                summary = item.get("summary_text")
                if summary and isinstance(summary, list):
                    # Clean up markdown bold markers if present for the title
                    title_text = "".join(summary).strip().replace("**", "")
                    pane.log_processing_event("", title=title_text)
            return

        if msg_type == "reasoning_content_delta":
            delta = payload.get("delta")
            if delta:
                pane.update_reasoning(str(delta))
            return

        if msg_type == "exec_command_begin":
            cmd = payload.get("command")
            if isinstance(cmd, list):
                cmd = " ".join(cmd)
            pane.log_processing_event(f"[bold]Running:[/bold] {cmd}\n", title=f"Running '{cmd}'")
            return

        if msg_type == "exec_command_output_delta":
            chunk = payload.get("chunk")
            import base64
            if chunk:
                try:
                    decoded = base64.b64decode(chunk).decode("utf-8", errors="replace")
                    pane.log_processing_event(decoded)
                except Exception:
                    pane.log_processing_event(str(chunk))
            return

        if msg_type == "exec_command_end":
            pane.log_processing_event("\n[bold]Command finished.[/bold]\n", title="Processing...")
            return

        if msg_type in ("agent_message_delta", "agent_message_content_delta"):
            delta = payload.get("delta")
            if delta:
                pane.stream_assistant_chunk(str(delta))
            return

        # Fallback: Ignore other events to prevent log noise as per user request.
        return

    @staticmethod
    def _percent_complete(progress: float | None, total: float | None) -> int:
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
