import asyncio
import contextlib
import subprocess
import json
import sys
import shutil
import os
import platform


async def main() -> None:
    # Determine the command to run
    # Allow override via command line arguments, or try to find 'codex' in PATH
    is_windows = platform.system() == "Windows"
    codex_path = None

    if len(sys.argv) > 1:
        server_command = sys.argv[1:]
    else:
        # On Windows, shutil.which() might not find batch files or commands
        # that are available in cmd.exe. Try multiple approaches.

        # First try standard which
        codex_path = shutil.which("codex")

        # On Windows, also try with common extensions
        if codex_path is None and is_windows:
            for ext in [".exe", ".cmd", ".bat"]:
                codex_path = shutil.which(f"codex{ext}")
                if codex_path:
                    break

        # If still not found, we'll try running it anyway with shell=True on Windows
        # since cmd.exe might be able to resolve it
        if codex_path is None:
            if is_windows:
                print(
                    "Warning: 'codex' not found via shutil.which(), "
                    "but will try running it anyway.",
                    file=sys.stderr,
                )
                print("(Windows cmd.exe may be able to resolve it)", file=sys.stderr)
                server_command = ["codex", "mcp-server"]
            else:
                print("Error: 'codex' command not found in PATH.", file=sys.stderr)
                print(
                    "Please install codex or provide the command as arguments:",
                    file=sys.stderr,
                )
                print("  python mcp.py codex mcp-server", file=sys.stderr)
                print("  python mcp.py python -m codex mcp-server", file=sys.stderr)
                sys.exit(1)
        else:
            # Use the found path if available
            server_command = [codex_path, "mcp-server"]

    # Start Codex MCP server as a subprocess
    print(f"Starting MCP server: {' '.join(server_command)}")

    # On Windows, if we couldn't find the command via shutil.which(),
    # use shell=True so cmd.exe can resolve batch files and PATH entries
    use_shell = is_windows and codex_path is None

    try:
        if use_shell:
            # When using shell=True on Windows, pass command as a string
            cmd = " ".join(server_command)
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *server_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
    except FileNotFoundError as e:
        print(f"Error: Could not start server process: {e}", file=sys.stderr)
        print(f"Command attempted: {' '.join(server_command)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)

    # Helper structures for JSON-RPC messaging
    write_lock = asyncio.Lock()
    pending_responses: dict[int, asyncio.Future] = {}

    async def read_loop() -> None:
        """Single reader loop to demultiplex responses by id.

        This avoids concurrent reads from the same StreamReader, which is what
        triggered the 'readuntil() called while another coroutine is already
        waiting for incoming data' error.
        """
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                # EOF - fail any pending requests
                for fut in list(pending_responses.values()):
                    if not fut.done():
                        fut.set_exception(RuntimeError("Server closed connection"))
                pending_responses.clear()
                break

            try:
                message = json.loads(line.decode().strip())
            except json.JSONDecodeError as e:
                print(
                    f"Warning: Failed to parse JSON from server: {e}; "
                    f"raw={line!r}",
                    file=sys.stderr,
                )
                continue

            msg_id = message.get("id")
            if msg_id is None:
                # Notification or message without id – just log it
                print(
                    f"Received message without id:\n"
                    f"{json.dumps(message, indent=2)}",
                    file=sys.stderr,
                )
                continue

            fut = pending_responses.pop(msg_id, None)
            if fut is not None and not fut.done():
                fut.set_result(message)
            else:
                print(
                    f"Warning: received response for unknown or already-handled "
                    f"id {msg_id}: {json.dumps(message, indent=2)}",
                    file=sys.stderr,
                )

    async def send_request(request: dict) -> dict:
        """Send a JSON-RPC request and await its response."""
        msg_id = request.get("id")
        if msg_id is None:
            raise ValueError("Request must include an 'id' field")

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        pending_responses[msg_id] = fut

        message = json.dumps(request) + "\n"
        # Ensure writes are not interleaved
        async with write_lock:
            assert proc.stdin is not None
            proc.stdin.write(message.encode())
            await proc.stdin.drain()

        return await fut

    # Start the single reader task that will demultiplex all responses
    reader_task = asyncio.create_task(read_loop())

    try:
        # MCP protocol requires initialization first
        print("Sending initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-client", "version": "1.0.0"},
            },
        }

        init_response = await send_request(init_request)
        print(f"Initialize response: {json.dumps(init_response, indent=2)}")

        # Send initialized notification (notification, so no response expected)
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        notification_message = json.dumps(initialized_notification) + "\n"
        async with write_lock:
            assert proc.stdin is not None
            proc.stdin.write(notification_message.encode())
            await proc.stdin.drain()

        # Now send two concurrent Codex tool calls using asyncio.gather.
        # These are \"real\" requests that may take some time to complete.
        print("\nSending two concurrent Codex tool calls...")
        request1 = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "codex",
                "arguments": {
                    # Minimal valid arguments based on the tools/list schema:
                    # prompt is required; sandbox is optional but useful.
                    "prompt": "First concurrent Codex MCP test prompt.",
                    "sandbox": "read-only",
                },
            },
        }
        request2 = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "codex",
                "arguments": {
                    "prompt": "Second concurrent Codex MCP test prompt.",
                    "sandbox": "read-only",
                },
            },
        }

        response1, response2 = await asyncio.gather(
            send_request(request1),
            send_request(request2),
        )

        responses = [response1, response2]
        success_count = sum(1 for r in responses if "error" not in r)
        error_count = len(responses) - success_count

        for i, r in enumerate(responses, start=1):
            if "error" in r:
                message = r["error"].get("message", "unknown error")
                print(f"Codex call {i} failed: {message}")
            else:
                print(f"Codex call {i} succeeded")

        print(
            f"\nConcurrent Codex calls summary: "
            f"{success_count} succeeded, {error_count} failed"
        )

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        # Try to read stderr for more info
        if proc.stderr:
            try:
                stderr_output = await proc.stderr.read()
                if stderr_output:
                    print(
                        f"Server stderr: {stderr_output.decode(errors='replace')}",
                        file=sys.stderr,
                    )
            except Exception:
                pass
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup - terminate the server process
        print("\nCleaning up: terminating MCP server process...")
        if proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass

        try:
            proc.terminate()
            # Wait up to 5 seconds for graceful shutdown
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
                print("✓ Server process terminated successfully")
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                print("⚠ Server didn't terminate gracefully, forcing kill...")
                proc.kill()
                await proc.wait()
                print("✓ Server process killed")
        except ProcessLookupError:
            # Process already terminated
            print("✓ Server process already terminated")
        except Exception as e:
            print(f"⚠ Warning during cleanup: {e}", file=sys.stderr)

        # Cancel the reader task if it's still running
        try:
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task
        except Exception:
            pass

        # Print any remaining stderr output
        if proc.stderr:
            try:
                stderr_output = await proc.stderr.read()
                if stderr_output:
                    print(
                        f"\nServer stderr output:\n"
                        f"{stderr_output.decode(errors='replace')}",
                        file=sys.stderr,
                    )
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
