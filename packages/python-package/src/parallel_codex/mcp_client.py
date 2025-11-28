"""Async Codex MCP client over JSON-RPC 2.0 on stdio.

This module is intentionally self-contained and does not depend on Textual.
The TUI layer should import :class:`CodexMCP` and drive it from an asyncio
event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

LOG = logging.getLogger(__name__)


def ensure_codex_present() -> str:
    """Return the path to the `codex` CLI, or raise if not found.

    The path is resolved from the PARALLEL_CODEX_CODEX_PATH environment
    variable if set, otherwise from the user's PATH.
    """

    override = os.environ.get("PARALLEL_CODEX_CODEX_PATH")
    if override:
        return override

    path = shutil.which("codex")
    if path is None:
        raise RuntimeError(
            "The 'codex' CLI was not found on PATH. "
            "Install Codex and ensure the 'codex' command is available."
        )
    return path


async def ensure_codex_logged_in() -> None:
    """Raise RuntimeError if the current user is not logged into Codex."""

    codex_path = ensure_codex_present()

    try:
        proc = await asyncio.create_subprocess_exec(
            codex_path,
            "login",
            "status",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "The 'codex' CLI could not be executed even though it was found on PATH.\n"
            f"Resolved path: {codex_path}\n"
            "Check that this file exists and is executable."
        ) from exc

    returncode = await proc.wait()
    if returncode != 0:
        raise RuntimeError(
            "Codex CLI is not authenticated. "
            "Run `echo $OPENAI_API_KEY | codex login --with-api-key` and then "
            "`codex login status`."
        )


class CodexEventType(str, Enum):
    """Categorization for MCP server events."""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    PROGRESS = "progress"
    LOGGING = "logging"
    ERROR = "error"


@dataclass(slots=True)
class CodexEvent:
    """A decoded event or response from the MCP server."""

    raw: dict[str, Any]
    session_id: str | None = None
    is_notification: bool = False
    event_type: CodexEventType = CodexEventType.NOTIFICATION
    related_request_id: str | None = None
    request_id: str | None = None
    timestamp: float = 0.0


@dataclass(slots=True)
class TrackedNotification:
    """Structured representation of an intermediate notification."""

    event_type: CodexEventType
    message: dict[str, Any]
    timestamp: float
    session_id: str | None = None
    related_request_id: str | None = None


@dataclass(slots=True)
class RequestTimeline:
    """Full lifecycle of a Codex MCP request."""

    request_id: str
    method: str | None = None
    params: dict[str, Any] | None = None
    sent_at: float | None = None
    response: dict[str, Any] | None = None
    completed_at: float | None = None
    status: str = "pending"
    session_id: str | None = None
    notifications: list[TrackedNotification] = field(default_factory=list)


class CodexEventTracker:
    """Track notifications and responses grouped by request id."""

    def __init__(self) -> None:
        self._timelines: dict[str, RequestTimeline] = {}

    # ------------------------------------------------------------------
    # Request lifecycle helpers
    # ------------------------------------------------------------------
    def _ensure_timeline(self, request_id: str) -> RequestTimeline:
        timeline = self._timelines.get(request_id)
        if timeline is None:
            timeline = RequestTimeline(request_id=request_id)
            self._timelines[request_id] = timeline
        return timeline

    def track_outgoing_request(
        self,
        request_id: str,
        *,
        method: str,
        params: dict[str, Any],
        session_hint: str | None,
        timestamp: float,
    ) -> None:
        timeline = self._ensure_timeline(request_id)
        timeline.method = method
        timeline.params = params
        timeline.sent_at = timestamp
        timeline.status = "pending"
        if session_hint:
            timeline.session_id = session_hint

    def set_session_id(self, request_id: str, session_id: str) -> None:
        timeline = self._ensure_timeline(request_id)
        timeline.session_id = session_id

    def track_notification(self, request_id: str, notification: TrackedNotification) -> None:
        timeline = self._ensure_timeline(request_id)
        timeline.notifications.append(notification)
        if notification.session_id and timeline.session_id is None:
            timeline.session_id = notification.session_id

    def track_response(
        self,
        request_id: str,
        *,
        message: dict[str, Any],
        timestamp: float,
        session_id: str | None = None,
    ) -> None:
        timeline = self._ensure_timeline(request_id)
        timeline.response = message
        timeline.completed_at = timestamp
        timeline.status = "complete"
        if session_id:
            timeline.session_id = session_id


    def get_request_timeline(self, request_id: str) -> RequestTimeline | None:
        return self._timelines.get(request_id)




@dataclass(slots=True)
class PendingCall:
    """Book-keeping for an in-flight ``codex`` / ``codex-reply`` call."""

    request_id: int
    method_name: str
    session_hint: str | None
    future: asyncio.Future[dict[str, Any]]


class CodexMCP:
    """Async client for a single ``codex mcp-server`` subprocess."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id: int = 1
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

        # Map request id -> PendingCall
        self._pending: dict[int, PendingCall] = {}
        # session_id -> asyncio.Queue[CodexEvent]
        self._session_queues: dict[str, asyncio.Queue[CodexEvent]] = {}
        # FIFO of codex calls that are waiting for their first session_configured
        self._sessionless_queue: deque[PendingCall] = deque()
        # Global event stream for all notifications, regardless of session.
        self._global_events: asyncio.Queue[CodexEvent] = asyncio.Queue()
        # Tracker for correlating intermediate notifications.
        self._event_tracker = CodexEventTracker()

        # Protect writes to stdin
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Start the ``codex mcp-server`` subprocess and reader task."""

        if self._proc is not None:
            return

        await ensure_codex_logged_in()
        codex_path = ensure_codex_present()

        # Enable the rmcp_client feature so that Codex emits rich MCP
        # notifications (progress, logging, etc.) over stdout. This mirrors
        # the recommended invocation:
        #   DEBUG=true LOG_LEVEL=debug codex --enable rmcp_client mcp-server
        cmd = [codex_path, "--enable", "rmcp_client", "mcp-server"]

        # Default the Codex subprocess to a verbose logging configuration
        # so that it actually emits progress/logging notifications. Users can
        # override these via their own environment if desired.
        env = os.environ.copy()
        env.setdefault("DEBUG", "true")
        env.setdefault("LOG_LEVEL", "debug")

        LOG.info("Starting codex mcp-server")
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        if self._proc.stdout is None or self._proc.stdin is None:
            raise RuntimeError("Failed to start codex mcp-server with stdio pipes.")

        # Start reader task that demultiplexes all responses and notifications.
        self._reader_task = asyncio.create_task(self._reader_loop(), name="codex-mcp-reader")
        # Drain stderr so that Codex debug logs do not block the subprocess.
        if self._proc.stderr is not None:
            self._stderr_task = asyncio.create_task(
                self._stderr_loop(),
                name="codex-mcp-stderr",
            )

    async def stop(self) -> None:
        """Terminate the subprocess and clean up tasks."""

        proc = self._proc
        if proc is None:
            return

        LOG.info("Stopping codex mcp-server")
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()

        self._proc = None

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def call_codex(
        self,
        prompt: str,
        *,
        config: dict[str, Any] | None = None,
    ) -> tuple[str, asyncio.Future[dict[str, Any]]]:
        """Start a new Codex session via the ``codex`` MCP tool.

        Returns:
            A tuple of (request_id, future). The future resolves to the result dict.
        """

        request_id, future, send = self._prepare_tool_call(
            name="codex",
            arguments={"prompt": prompt, "config": config or {}},
            session_hint=None,
        )
        await send()
        return request_id, future

    def prepare_codex_call(
        self,
        prompt: str,
        *,
        config: dict[str, Any] | None = None,
    ) -> tuple[str, asyncio.Future[dict[str, Any]], Callable[[], Any]]:
        """Prepare a new Codex session call without sending it yet.

        Returns:
            (request_id, future, send_awaitable)
        """
        return self._prepare_tool_call(
            name="codex",
            arguments={"prompt": prompt, "config": config or {}},
            session_hint=None,
        )

    async def reply(
        self,
        session_id: str,
        prompt: str,
    ) -> tuple[str, asyncio.Future[dict[str, Any]]]:
        """Send a follow-up instruction using the ``codex-reply`` tool.

        Returns:
            A tuple of (request_id, future). The future resolves to the result dict.
        """

        request_id, future, send = self._prepare_tool_call(
            name="codex-reply",
            arguments={"prompt": prompt, "sessionId": session_id},
            session_hint=session_id,
        )
        await send()
        return request_id, future

    def prepare_reply(
        self,
        session_id: str,
        prompt: str,
    ) -> tuple[str, asyncio.Future[dict[str, Any]], Callable[[], Any]]:
        """Prepare a reply call without sending it yet.

        Returns:
            (request_id, future, send_awaitable)
        """
        return self._prepare_tool_call(
            name="codex-reply",
            arguments={"prompt": prompt, "sessionId": session_id},
            session_hint=session_id,
        )

    def get_session_queue(self, session_id: str) -> asyncio.Queue[CodexEvent]:
        """Return a queue that receives events for ``session_id``."""

        queue = self._session_queues.get(session_id)
        if queue is None:
            queue = asyncio.Queue()
            self._session_queues[session_id] = queue
        return queue

    def get_global_event_queue(self) -> asyncio.Queue[CodexEvent]:
        """Return a queue that receives all notification events."""

        return self._global_events

    @property
    def event_tracker(self) -> CodexEventTracker:
        """Expose the shared event tracker for request timelines."""

        return self._event_tracker

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _stderr_loop(self) -> None:
        """Consume stderr from the Codex subprocess and forward to logging.

        The Codex MCP server uses stderr for debug and progress logs when
        DEBUG/LOG_LEVEL are set. If stderr is not drained, the pipe buffer can
        fill and block further protocol messages on stdout.
        """

        assert self._proc is not None
        assert self._proc.stderr is not None

        stream = self._proc.stderr
        while True:
            line = await stream.readline()
            if not line:
                return

            try:
                text = line.decode("utf-8", errors="replace").rstrip()
            except Exception:  # pragma: no cover - extremely defensive
                continue

            if text:
                LOG.debug("codex mcp-server stderr: %s", text)

    def _prepare_tool_call(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        session_hint: str | None,
    ) -> tuple[str, asyncio.Future[dict[str, Any]], Callable[[], Any]]:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("Codex MCP server is not running. Call start() first.")

        request_id = self._next_id
        self._next_id += 1

        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        pending = PendingCall(
            request_id=request_id,
            method_name=name,
            session_hint=session_hint,
            future=future,
        )
        self._pending[request_id] = pending
        if name == "codex":
            # We expect a session_configured notification once the session is ready.
            self._sessionless_queue.append(pending)

        timestamp = asyncio.get_running_loop().time()
        self._event_tracker.track_outgoing_request(
            str(request_id),
            method=name,
            params=request["params"],
            session_hint=session_hint,
            timestamp=timestamp,
        )

        body = json.dumps(request, separators=(",", ":"))

        async def send() -> None:
            # Re-check proc state in case it died since preparation
            if self._proc is None or self._proc.stdin is None:
                raise RuntimeError("Codex MCP server is not running.")

            async with self._write_lock:
                LOG.debug("Sending request id=%s method=%s", request_id, name)
                self._proc.stdin.write((body + "\n").encode("utf-8"))
                await self._proc.stdin.drain()

        return str(request_id), future, send

    async def _reader_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        stdout = self._proc.stdout
        while True:
            line = await stdout.readline()
            if not line:
                LOG.info("codex mcp-server closed stdout")
                # Fail all pending futures.
                exc = RuntimeError("codex mcp-server terminated unexpectedly")
                for pending in list(self._pending.values()):
                    if not pending.future.done():
                        pending.future.set_exception(exc)
                self._pending.clear()
                return

            text = line.decode("utf-8").strip()
            if not text:
                continue

            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                LOG.warning("Failed to decode JSON from codex mcp-server: %s", text)
                continue

            await self._handle_message(message)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        # Notifications have a "method" field and no "result"/"error" payload.
        # Some servers may still include an "id" for correlation, so we
        # classify based on the absence of result/error rather than id.
        if "method" in message and "result" not in message and "error" not in message:
            await self._handle_notification(message)
            return

        # Responses refer to an earlier request id.
        if "id" in message and ("result" in message or "error" in message):
            request_id = message["id"]
            pending = self._pending.pop(request_id, None)
            if pending is None:
                LOG.warning("Received response for unknown id=%s", request_id)
                return

            rid = str(request_id)
            timeline = self._event_tracker.get_request_timeline(rid)
            session_id = pending.session_hint
            if timeline is not None and timeline.session_id is not None:
                session_id = timeline.session_id

            timestamp = asyncio.get_running_loop().time()
            self._event_tracker.track_response(
                rid,
                message=message,
                timestamp=timestamp,
                session_id=session_id,
            )

            event = CodexEvent(
                raw=message,
                session_id=session_id,
                is_notification=False,
                event_type=CodexEventType.RESPONSE,
                related_request_id=rid,
                request_id=rid,
                timestamp=timestamp,
            )
            await self._global_events.put(event)

            if not pending.future.done():
                if "error" in message:
                    pending.future.set_exception(RuntimeError(str(message["error"])))
                else:
                    pending.future.set_result(message["result"])
            return

        # Errors or other messages.
        LOG.warning("Unhandled message from codex mcp-server: %s", message)

    async def _handle_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        payload = _flatten_notification_payload(params)
        related_request_id = _extract_related_request_id(message)

        # Extract session id if present in known notification shapes.
        session_id: str | None = payload.get("session_id")
        if method == "session_configured" and session_id is not None and self._sessionless_queue:
            # Try to match a pending session call by ID, falling back to FIFO if not possible.
            matched_pending: PendingCall | None = None

            if related_request_id is not None:
                for pending in self._sessionless_queue:
                    if str(pending.request_id) == related_request_id:
                        matched_pending = pending
                        break

            if matched_pending is None:
                # Fallback: assume strict ordering if no ID is available to correlate.
                matched_pending = self._sessionless_queue[0]

            if matched_pending:
                # Remove from the deque (safe since we have the object reference)
                try:
                    self._sessionless_queue.remove(matched_pending)
                except ValueError:
                    pass

                LOG.info(
                    "Associated session_id=%s with request id=%s",
                    session_id,
                    matched_pending.request_id,
                )
                matched_pending.session_hint = session_id
                self._event_tracker.set_session_id(str(matched_pending.request_id), session_id)

        event_type = _classify_event_type(method)
        timestamp = asyncio.get_running_loop().time()

        event = CodexEvent(
            raw=message,
            session_id=session_id,
            is_notification=True,
            event_type=event_type,
            related_request_id=related_request_id,
            timestamp=timestamp,
        )

        # Publish to the global event stream first so consumers can observe all activity.
        await self._global_events.put(event)

        if related_request_id is not None:
            tracked = TrackedNotification(
                event_type=event_type,
                message=message,
                timestamp=timestamp,
                session_id=session_id,
                related_request_id=related_request_id,
            )
            self._event_tracker.track_notification(related_request_id, tracked)

        if session_id:
            queue = self.get_session_queue(session_id)
            await queue.put(event)
        else:
            # No obvious session; keep the event only in the global stream.
            LOG.debug("Notification without session id: %s", message)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure basic logging to stderr for the MCP client."""

    if logging.getLogger().handlers:
        # Assume the application configured logging already.
        return

    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _classify_event_type(method: str | None) -> CodexEventType:
    if not method:
        return CodexEventType.NOTIFICATION

    lowered = method.lower()
    if "progress" in lowered:
        return CodexEventType.PROGRESS
    if "logging" in lowered:
        return CodexEventType.LOGGING
    if "error" in lowered:
        return CodexEventType.ERROR
    return CodexEventType.NOTIFICATION


def _flatten_notification_payload(params: dict[str, Any]) -> dict[str, Any]:
    payload = params or {}
    msg = payload.get("msg")
    if isinstance(msg, dict):
        return msg
    return payload


def _extract_related_request_id(message: dict[str, Any]) -> str | None:
    params = message.get("params") or {}

    # Check _meta for requestId (seen in new events.log format)
    meta = params.get("_meta")
    if isinstance(meta, dict):
        req_id = meta.get("requestId")
        if req_id is not None:
            return str(req_id)

    keys = ("related_request_id", "request_id")

    for key in keys:
        value = params.get(key)
        if value is not None:
            return str(value)

    msg = params.get("msg")
    if isinstance(msg, dict):
        for key in keys:
            value = msg.get(key)
            if value is not None:
                return str(value)

    return None
