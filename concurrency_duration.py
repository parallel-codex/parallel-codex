import asyncio
import json
import shutil
import sys
import time


def build_server_command() -> list[str]:
    if len(sys.argv) > 1:
        return sys.argv[1:]
    cmd = shutil.which("codex")
    if not cmd:
        print(
            "Usage:\n  python mcp.py codex mcp-server\n  python mcp.py <custom command>",
            file=sys.stderr,
        )
        sys.exit(1)
    return [cmd, "mcp-server"]


async def start_server() -> asyncio.subprocess.Process:
    command = build_server_command()
    print(f"Launching MCP server: {' '.join(command)}")
    return await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def main() -> None:
    proc = await start_server()
    write_lock = asyncio.Lock()
    pending: dict[int, asyncio.Future] = {}

    async def read_loop() -> None:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line.decode().strip())
            except json.JSONDecodeError:
                decoded = line.decode(errors="replace").rstrip()
                if decoded:
                    print(f"[server stdout] {decoded}")
                continue
            msg_id = message.get("id")
            fut = pending.pop(msg_id, None)
            if fut and not fut.done():
                fut.set_result(message)

        for fut in pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("Server closed"))
        pending.clear()

    async def send_request(payload: dict) -> dict:
        msg_id = payload["id"]
        loop = asyncio.get_running_loop()
        pending[msg_id] = loop.create_future()
        data = json.dumps(payload) + "\n"
        assert proc.stdin is not None
        async with write_lock:
            proc.stdin.write(data.encode())
            await proc.stdin.drain()
        return await pending[msg_id]

    async def send_notification(payload: dict) -> None:
        data = json.dumps(payload) + "\n"
        assert proc.stdin is not None
        async with write_lock:
            proc.stdin.write(data.encode())
            await proc.stdin.drain()

    reader_task = asyncio.create_task(read_loop())

    try:
        await send_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-client", "version": "1.0.0"},
                },
            }
        )
        await send_notification(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )

        prompts = [
            "Codex MCP concurrency test prompt #1. There are other concurrent requests being made at this moment, please respond nothing but 'ok' to keep all responses the same duration.",
            "Codex MCP concurrency test prompt #2. There are other concurrent requests being made at this moment, please respond nothing but 'ok' to keep all responses the same duration.",
            "Codex MCP concurrency test prompt #3. There are other concurrent requests being made at this moment, please respond nothing but 'ok' to keep all responses the same duration.",
            "Codex MCP concurrency test prompt #4. There are other concurrent requests being made at this moment, please respond nothing but 'ok' to keep all responses the same duration.",
        ]
        base_id = 2
        requests = [
            {
                "jsonrpc": "2.0",
                "id": base_id + idx,
                "method": "tools/call",
                "params": {
                    "name": "codex",
                    "arguments": {"prompt": prompt, "sandbox": "read-only"},
                },
            }
            for idx, prompt in enumerate(prompts)
        ]

        async def timed_call(idx: int, request: dict) -> tuple[int, float, dict]:
            start = time.perf_counter()
            response = await send_request(request)
            duration = time.perf_counter() - start
            return idx, duration, response

        overall_start = time.perf_counter()
        results = await asyncio.gather(

            *(timed_call(idx + 1, req) for idx, req in enumerate(requests)),
            return_exceptions=False,
        )
        total = time.perf_counter() - overall_start

        print(f"All requests completed in {total:.2f}s")
        for idx, duration, response in sorted(results, key=lambda r: r[0]):
            status = "ok" if "error" not in response else response["error"].get(
                "message", "error"
            )
            print(f"  Request {idx}: {duration:.2f}s ({status})")
    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        await proc.wait()
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        if proc.stderr:
            stderr_output = await proc.stderr.read()
            if stderr_output:
                print(stderr_output.decode(errors="replace"), file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
