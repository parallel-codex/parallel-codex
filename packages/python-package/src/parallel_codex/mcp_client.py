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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Optional

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


@dataclass(slots=True)
class CodexEvent:
    """A decoded event or response from the MCP server."""

    raw: Dict[str, Any]
    session_id: Optional[str] = None
    is_notification: bool = False


@dataclass(slots=True)
class PendingCall:
    """Book-keeping for an in-flight ``codex`` / ``codex-reply`` call."""

    request_id: int
    method_name: str
    session_hint: Optional[str]
    future: "asyncio.Future[Dict[str, Any]]"


class CodexMCP:
    """Async client for a single ``codex mcp-server`` subprocess."""

    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id: int = 1
        self._reader_task: Optional[asyncio.Task[None]] = None

        # Map request id -> PendingCall
        self._pending: Dict[int, PendingCall] = {}
        # session_id -> asyncio.Queue[CodexEvent]
        self._session_queues: Dict[str, "asyncio.Queue[CodexEvent]"] = {}
        # FIFO of codex calls that are waiting for their first session_configured
        self._sessionless_queue: Deque[PendingCall] = deque()
        # Global event stream for all notifications, regardless of session.
        self._global_events: "asyncio.Queue[CodexEvent]" = asyncio.Queue()

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

        LOG.info("Starting codex mcp-server")
        self._proc = await asyncio.create_subprocess_exec(
            codex_path,
            "mcp-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if self._proc.stdout is None or self._proc.stdin is None:
            raise RuntimeError("Failed to start codex mcp-server with stdio pipes.")

        # Start reader task that demultiplexes all responses and notifications.
        self._reader_task = asyncio.create_task(self._reader_loop(), name="codex-mcp-reader")

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
        except asyncio.TimeoutError:
            proc.kill()

        self._proc = None

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def call_codex(
        self,
        prompt: str,
        *,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Start a new Codex session via the ``codex`` MCP tool."""

        return await self._send_tool_call(
            name="codex",
            arguments={"prompt": prompt, "config": config or {}},
            session_hint=None,
        )

    async def reply(
        self,
        session_id: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """Send a follow-up instruction using the ``codex-reply`` tool."""

        return await self._send_tool_call(
            name="codex-reply",
            arguments={"prompt": prompt, "sessionId": session_id},
            session_hint=session_id,
        )

    def get_session_queue(self, session_id: str) -> "asyncio.Queue[CodexEvent]":
        """Return a queue that receives events for ``session_id``."""

        queue = self._session_queues.get(session_id)
        if queue is None:
            queue = asyncio.Queue()
            self._session_queues[session_id] = queue
        return queue

    def get_global_event_queue(self) -> "asyncio.Queue[CodexEvent]":
        """Return a queue that receives all notification events."""

        return self._global_events

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _send_tool_call(
        self,
        *,
        name: str,
        arguments: Dict[str, Any],
        session_hint: Optional[str],
    ) -> Dict[str, Any]:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("Codex MCP server is not running. Call start() first.")

        request_id = self._next_id
        self._next_id += 1

        request: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }

        future: "asyncio.Future[Dict[str, Any]]" = asyncio.get_running_loop().create_future()
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

        body = json.dumps(request, separators=(",", ":"))

        async with self._write_lock:
            LOG.debug("Sending request id=%s method=%s", request_id, name)
            self._proc.stdin.write((body + "\n").encode("utf-8"))
            await self._proc.stdin.drain()

        return await future

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

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        # Notifications have a "method" field and no "id".
        if "method" in message and "id" not in message:
            await self._handle_notification(message)
            return

        # Responses refer to an earlier request id.
        if "id" in message and "result" in message:
            request_id = message["id"]
            pending = self._pending.pop(request_id, None)
            if pending is None:
                LOG.warning("Received response for unknown id=%s", request_id)
                return

            if not pending.future.done():
                pending.future.set_result(message["result"])
            return

        # Errors or other messages.
        LOG.warning("Unhandled message from codex mcp-server: %s", message)

    async def _handle_notification(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params") or {}

        # Extract session id if present in known notification shapes.
        session_id: Optional[str] = None
        if method == "session_configured":
            msg = params.get("msg") or {}
            session_id = msg.get("session_id")
            if session_id is not None and self._sessionless_queue:
                pending = self._sessionless_queue.popleft()
                LOG.info(
                    "Associated session_id=%s with request id=%s",
                    session_id,
                    pending.request_id,
                )

        elif method == "notifications/progress":
            # Some progress messages might carry a session id depending on server implementation.
            msg = params.get("msg") or {}
            session_id = msg.get("session_id")

        event = CodexEvent(raw=message, session_id=session_id, is_notification=True)

        # Publish to the global event stream first so consumers can observe all activity.
        await self._global_events.put(event)

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


