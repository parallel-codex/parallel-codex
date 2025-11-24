from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import pytest

from parallel_codex.mcp_client import (
    CodexEvent,
    CodexEventType,
    CodexMCP,
    PendingCall,
    ensure_codex_present,
)


class DummyStdout:
    """Fake stdout stream for driving the MCP reader loop."""

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[bytes]" = asyncio.Queue()

    async def readline(self) -> bytes:
        return await self._queue.get()

    async def push_json(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload).encode("utf-8") + b"\n"
        await self._queue.put(line)


class DummyProc:
    def __init__(self, stdout: DummyStdout) -> None:
        self.stdout = stdout


@pytest.mark.asyncio()
async def test_global_event_queue_receives_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexMCP()

    stdout = DummyStdout()
    # Patch the internal process to avoid actually spawning codex.
    client._proc = DummyProc(stdout)  # type: ignore[assignment]

    reader = asyncio.create_task(client._reader_loop())  # type: ignore[arg-type]

    payload = {
        "jsonrpc": "2.0",
        "method": "session_configured",
        "params": {
            "msg": {
                "type": "session_configured",
                "session_id": "abc-123",
            }
        },
    }
    await stdout.push_json(payload)
    # Terminate the reader loop.
    await stdout._queue.put(b"")

    event: CodexEvent = await asyncio.wait_for(client.get_global_event_queue().get(), timeout=1.0)
    assert event.session_id == "abc-123"
    assert event.event_type == CodexEventType.NOTIFICATION

    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio()
async def test_logging_notification_updates_tracker(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexMCP()

    stdout = DummyStdout()
    client._proc = DummyProc(stdout)  # type: ignore[assignment]
    reader = asyncio.create_task(client._reader_loop())  # type: ignore[arg-type]

    tracker = client.event_tracker
    tracker.track_outgoing_request(
        "req-1",
        method="codex",
        params={"name": "codex"},
        session_hint=None,
        timestamp=asyncio.get_running_loop().time(),
    )

    payload = {
        "jsonrpc": "2.0",
        "method": "notifications/logging/message",
        "params": {
            "related_request_id": "req-1",
            "level": "info",
            "data": "Starting...",
        },
    }
    await stdout.push_json(payload)
    await stdout._queue.put(b"")

    event: CodexEvent = await asyncio.wait_for(client.get_global_event_queue().get(), timeout=1.0)
    assert event.event_type == CodexEventType.LOGGING
    assert event.related_request_id == "req-1"

    notifications = tracker.get_intermediate_events("req-1")
    assert len(notifications) == 1
    assert notifications[0].event_type == CodexEventType.LOGGING

    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio()
async def test_responses_published_to_global_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexMCP()

    stdout = DummyStdout()
    client._proc = DummyProc(stdout)  # type: ignore[assignment]

    loop = asyncio.get_running_loop()
    future: "asyncio.Future[Dict[str, Any]]" = loop.create_future()
    client._pending[1] = PendingCall(
        request_id=1,
        method_name="codex",
        session_hint="session-123",
        future=future,
    )

    tracker = client.event_tracker
    tracker.track_outgoing_request(
        "1",
        method="codex",
        params={"name": "codex"},
        session_hint="session-123",
        timestamp=loop.time(),
    )

    reader = asyncio.create_task(client._reader_loop())  # type: ignore[arg-type]

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": "ok", "conversationId": "conv-1"},
    }
    await stdout.push_json(payload)
    await stdout._queue.put(b"")

    event: CodexEvent = await asyncio.wait_for(client.get_global_event_queue().get(), timeout=1.0)
    assert event.event_type == CodexEventType.RESPONSE
    assert event.request_id == "1"
    assert future.done()
    assert future.result() == payload["result"]

    timeline = tracker.get_request_timeline("1")
    assert timeline is not None
    assert timeline.response == payload
    assert tracker.conversation_map["conv-1"] == ["1"]

    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio()
async def test_notifications_with_null_id_are_processed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexMCP()

    stdout = DummyStdout()
    client._proc = DummyProc(stdout)  # type: ignore[assignment]
    reader = asyncio.create_task(client._reader_loop())  # type: ignore[arg-type]

    payload = {
        "jsonrpc": "2.0",
        "id": None,
        "method": "notifications/progress",
        "params": {
            "related_request_id": "req-99",
            "progress": 10,
            "total": 100,
        },
    }
    await stdout.push_json(payload)
    await stdout._queue.put(b"")

    event: CodexEvent = await asyncio.wait_for(client.get_global_event_queue().get(), timeout=1.0)
    assert event.event_type == CodexEventType.PROGRESS
    assert event.related_request_id == "req-99"

    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio()
async def test_error_responses_reject_pending_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexMCP()

    stdout = DummyStdout()
    client._proc = DummyProc(stdout)  # type: ignore[assignment]

    loop = asyncio.get_running_loop()
    future: "asyncio.Future[Dict[str, Any]]" = loop.create_future()
    client._pending[42] = PendingCall(
        request_id=42,
        method_name="codex",
        session_hint=None,
        future=future,
    )

    reader = asyncio.create_task(client._reader_loop())  # type: ignore[arg-type]

    payload = {
        "jsonrpc": "2.0",
        "id": 42,
        "error": {"code": 500, "message": "internal"},
    }
    await stdout.push_json(payload)
    await stdout._queue.put(b"")

    with pytest.raises(RuntimeError):
        await asyncio.wait_for(future, timeout=1.0)

    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass


def test_ensure_codex_present_prefers_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """If PARALLEL_CODEX_CODEX_PATH is set, it should be returned directly."""

    monkeypatch.setenv("PARALLEL_CODEX_CODEX_PATH", "/custom/codex/path")

    path = ensure_codex_present()

    assert path == "/custom/codex/path"


def test_ensure_codex_present_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without PARALLEL_CODEX_CODEX_PATH, PATH resolution is used."""

    monkeypatch.delenv("PARALLEL_CODEX_CODEX_PATH", raising=False)
    calls: list[str] = []

    def fake_which(cmd: str) -> str | None:  # type: ignore[override]
        calls.append(cmd)
        return "/usr/local/bin/codex"

    monkeypatch.setattr("parallel_codex.mcp_client.shutil.which", fake_which)

    path = ensure_codex_present()

    assert path == "/usr/local/bin/codex"
    assert calls == ["codex"]


def test_ensure_codex_present_raises_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no env override and `codex` is not on PATH, a RuntimeError is raised."""

    monkeypatch.delenv("PARALLEL_CODEX_CODEX_PATH", raising=False)

    def fake_which(cmd: str) -> str | None:  # type: ignore[override]
        return None

    monkeypatch.setattr("parallel_codex.mcp_client.shutil.which", fake_which)

    with pytest.raises(RuntimeError):
        ensure_codex_present()


@pytest.mark.asyncio()
async def test_notifications_with_id_are_treated_as_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notifications that include a non-null id but no result/error are still notifications."""

    client = CodexMCP()

    stdout = DummyStdout()
    client._proc = DummyProc(stdout)  # type: ignore[assignment]
    reader = asyncio.create_task(client._reader_loop())  # type: ignore[arg-type]

    payload = {
        "jsonrpc": "2.0",
        "id": 123,
        "method": "notifications/progress",
        "params": {
            "related_request_id": "req-100",
            "progress": 5,
            "total": 10,
        },
    }
    await stdout.push_json(payload)
    await stdout._queue.put(b"")

    event: CodexEvent = await asyncio.wait_for(
        client.get_global_event_queue().get(), timeout=1.0
    )
    assert event.event_type == CodexEventType.PROGRESS
    assert event.related_request_id == "req-100"

    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass
