import subprocess
import json
import sys
import shutil
import os
import platform

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
            print("Warning: 'codex' not found via shutil.which(), but will try running it anyway.", file=sys.stderr)
            print("(Windows cmd.exe may be able to resolve it)", file=sys.stderr)
            server_command = ["codex", "mcp-server"]
        else:
            print("Error: 'codex' command not found in PATH.", file=sys.stderr)
            print("Please install codex or provide the command as arguments:", file=sys.stderr)
            print("  python mcp.py codex mcp-server", file=sys.stderr)
            print("  python mcp.py python -m codex mcp-server", file=sys.stderr)
            sys.exit(1)
    else:
        # Use the found path if available
        server_command = [codex_path, "mcp-server"]

try:
    # Start Codex MCP server as a subprocess
    print(f"Starting MCP server: {' '.join(server_command)}")
    
    # On Windows, if we couldn't find the command via shutil.which(),
    # use shell=True so cmd.exe can resolve batch files and PATH entries
    use_shell = is_windows and codex_path is None
    
    # When using shell=True on Windows, pass command as a string
    if use_shell:
        cmd = " ".join(server_command)
    else:
        cmd = server_command
    
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=use_shell
    )
except FileNotFoundError as e:
    print(f"Error: Could not start server process: {e}", file=sys.stderr)
    print(f"Command attempted: {' '.join(server_command)}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error starting server: {e}", file=sys.stderr)
    sys.exit(1)

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
            "clientInfo": {"name": "mcp-client", "version": "1.0.0"}
        }
    }
    init_json = json.dumps(init_request) + "\n"
    proc.stdin.write(init_json)
    proc.stdin.flush()
    
    # Read initialize response
    init_response_line = proc.stdout.readline()
    if not init_response_line:
        print("Error: No response from server", file=sys.stderr)
        sys.exit(1)
    
    init_response = json.loads(init_response_line.strip())
    print(f"Initialize response: {json.dumps(init_response, indent=2)}")
    
    # Send initialized notification
    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }
    proc.stdin.write(json.dumps(initialized_notification) + "\n")
    proc.stdin.flush()
    
    # Now send the tools/list request
    print("\nSending tools/list request...")
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    json_request = json.dumps(request) + "\n"  # MCP expects messages delimited by newlines
    
    # Send request to the server's stdin
    proc.stdin.write(json_request)
    proc.stdin.flush()
    
    # Read and print the response from stdout
    response_line = proc.stdout.readline()
    if not response_line:
        print("Error: No response from server", file=sys.stderr)
        # Check stderr for any error messages
        stderr_output = proc.stderr.read()
        if stderr_output:
            print(f"Server stderr: {stderr_output}", file=sys.stderr)
        sys.exit(1)
    
    response = json.loads(response_line.strip())
    print(f"\nResponse: {json.dumps(response, indent=2)}")
    
except json.JSONDecodeError as e:
    print(f"Error: Failed to parse JSON response: {e}", file=sys.stderr)
    # Try to read stderr for more info
    stderr_output = proc.stderr.read()
    if stderr_output:
        print(f"Server stderr: {stderr_output}", file=sys.stderr)
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
        proc.stdin.close()
    
    try:
        proc.terminate()
        # Wait up to 5 seconds for graceful shutdown
        try:
            proc.wait(timeout=5)
            print("✓ Server process terminated successfully")
        except subprocess.TimeoutExpired:
            # Force kill if it doesn't terminate gracefully
            print("⚠ Server didn't terminate gracefully, forcing kill...")
            proc.kill()
            proc.wait()
            print("✓ Server process killed")
    except ProcessLookupError:
        # Process already terminated
        print("✓ Server process already terminated")
    except Exception as e:
        print(f"⚠ Warning during cleanup: {e}", file=sys.stderr)
    
    # Print any remaining stderr output
    try:
        stderr_output = proc.stderr.read()
        if stderr_output:
            print(f"\nServer stderr output:\n{stderr_output}", file=sys.stderr)
    except Exception:
        pass
