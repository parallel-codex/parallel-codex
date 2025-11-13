# MCP Server Concurrency Test

This folder contains a test script to verify that an MCP (Model Context Protocol) server can handle concurrent requests over STDIO.

## Purpose

This is a viability test to ensure that the project can properly handle concurrent requests to an MCP server before building the full implementation. The test verifies that:

1. An MCP server can be started via subprocess
2. Two concurrent JSON-RPC requests can be sent simultaneously
3. Both requests receive proper responses
4. The server correctly handles concurrent message processing

## Requirements

- Python 3.11+
- The `codex` CLI command must be available in your PATH (or specify a custom command)

## Usage

### Basic Usage

Run the test with the default `codex mcp-server` command:

```bash
python test_concurrent_mcp.py
```

### Custom Server Command

If your MCP server command is different, specify it as arguments:

```bash
python test_concurrent_mcp.py npx @modelcontextprotocol/inspector codex mcp-server
```

Or with a full path:

```bash
python test_concurrent_mcp.py /path/to/codex mcp-server
```

## How It Works

1. **Starts the MCP server** as a subprocess with stdin/stdout pipes
2. **Sends initialization** following the MCP protocol
3. **Sends two concurrent requests** using `asyncio.gather()` to ensure they're sent at nearly the same time
4. **Reads responses** asynchronously and matches them to the correct request IDs
5. **Verifies** that both requests succeeded and received proper responses

## Expected Output

On success, you should see:

```
============================================================
MCP Server Concurrency Test
============================================================
Starting MCP server: codex mcp-server

1. Sending initialize request...
   Initialize response: {...}

2. Sending two concurrent requests...

3. Received both responses in X.XXX seconds
   Response 1: {...}
   Response 2: {...}

✅ Request 1 succeeded
✅ Request 2 succeeded

============================================================
✅ Test PASSED: Both concurrent requests succeeded
```

## Notes

- The script uses JSON-RPC 2.0 protocol over newline-delimited JSON (NDJSON)
- Responses are matched to requests by their `id` field
- The test includes proper MCP protocol initialization before sending concurrent requests
- Error handling is included to catch and report any issues

## Modifications

Feel free to modify this script as needed for your specific testing requirements:

- Change the test methods (currently uses `tools/list`)
- Add more concurrent requests
- Modify timeout handling
- Add performance metrics
- Test different MCP protocol features

