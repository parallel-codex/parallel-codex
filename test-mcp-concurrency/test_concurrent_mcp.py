"""
Test script for verifying local concurrency in STDIO between a client and an MCP server.

This script tests that an MCP server can handle two concurrent requests properly
by sending them at nearly the same time and verifying both responses are received.
"""

import asyncio
import json
import sys
from typing import Any


class MCPClient:
    """Simple MCP client for testing concurrent requests over stdio."""

    def __init__(self, proc: asyncio.subprocess.Process):
        self.proc = proc
        self.pending_requests: dict[int, asyncio.Future] = {}
        self.request_id_counter = 0

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        self.request_id_counter += 1
        request_id = self.request_id_counter

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        # Create a future to hold the response
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self.pending_requests[request_id] = future

        # Send request
        request_line = json.dumps(request) + "\n"
        self.proc.stdin.write(request_line.encode())
        await self.proc.stdin.drain()

        # Wait for response
        return await future

    async def read_responses(self) -> None:
        """Continuously read responses from stdout and match them to pending requests."""
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    response = json.loads(line_str)
                    request_id = response.get("id")
                    if request_id in self.pending_requests:
                        future = self.pending_requests.pop(request_id)
                        if not future.done():
                            future.set_result(response)
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON response: {line_str}", file=sys.stderr)
                    print(f"Error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error reading responses: {e}", file=sys.stderr)
            # Cancel all pending requests
            for future in self.pending_requests.values():
                if not future.done():
                    future.cancel()
            raise


async def test_concurrent_requests(server_command: list[str]) -> bool:
    """
    Test that the MCP server can handle two concurrent requests.

    Returns True if both requests succeeded, False otherwise.
    """
    print(f"Starting MCP server: {' '.join(server_command)}")
    proc = await asyncio.create_subprocess_exec(
        *server_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    client = MCPClient(proc)

    # Start the response reader task
    reader_task = asyncio.create_task(client.read_responses())

    try:
        # Send initialization request first (MCP protocol requirement)
        print("\n1. Sending initialize request...")
        init_response = await client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        )
        print(f"   Initialize response: {json.dumps(init_response, indent=2)}")

        # Send initialized notification
        init_notification = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        proc.stdin.write((json.dumps(init_notification) + "\n").encode())
        await proc.stdin.drain()

        # Wait a bit for server to be ready
        await asyncio.sleep(5)

        # Send two concurrent requests
        print("\n2. Sending two concurrent requests...")
        start_time = asyncio.get_event_loop().time()

        # Use gather to send both requests concurrently
        response1_task = asyncio.create_task(client.send_request("tools/list", {}))
        response2_task = asyncio.create_task(client.send_request("tools/list", {}))

        response1, response2 = await asyncio.gather(response1_task, response2_task)

        end_time = asyncio.get_event_loop().time()
        elapsed = end_time - start_time

        print(f"\n3. Received both responses in {elapsed:.3f} seconds")
        print(f"   Response 1: {json.dumps(response1, indent=2)}")
        print(f"   Response 2: {json.dumps(response2, indent=2)}")

        # Verify both responses are valid
        success = True
        if "error" in response1:
            print("\n❌ Request 1 failed:", response1.get("error"), file=sys.stderr)
            success = False
        else:
            print("\n✅ Request 1 succeeded")

        if "error" in response2:
            print("❌ Request 2 failed:", response2.get("error"), file=sys.stderr)
            success = False
        else:
            print("✅ Request 2 succeeded")

        # Verify both responses have different IDs
        if response1.get("id") == response2.get("id"):
            print("⚠️  Warning: Both responses have the same ID", file=sys.stderr)

        return success

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Cleanup
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass

        proc.terminate()
        await proc.wait()

        # Read any remaining stderr output
        stderr_output = await proc.stderr.read()
        if stderr_output:
            print(f"\nServer stderr output:\n{stderr_output.decode()}", file=sys.stderr)


async def main():
    """Main entry point."""
    # Default to 'codex mcp-server', but allow override via command line
    if len(sys.argv) > 1:
        server_command = sys.argv[1:]
    else:
        server_command = ["codex", "mcp-server"]

    print("=" * 60)
    print("MCP Server Concurrency Test")
    print("=" * 60)

    success = await test_concurrent_requests(server_command)

    print("\n" + "=" * 60)
    if success:
        print("✅ Test PASSED: Both concurrent requests succeeded")
        sys.exit(0)
    else:
        print("❌ Test FAILED: One or more requests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

