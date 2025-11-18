from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import pytest

from parallel_codex.mcp_client import CodexEvent, CodexMCP, ensure_codex_present


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

    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader


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


