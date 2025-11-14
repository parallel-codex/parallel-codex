#!/usr/bin/env python3
"""
Helper script to check if any MCP server processes are running.
"""
import subprocess
import sys
import platform

def check_windows_processes():
    """Check for codex processes on Windows."""
    try:
        # Check for codex.exe
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:  # Header + processes
            print("Found codex.exe processes:")
            for line in lines[1:]:  # Skip header
                if line.strip():
                    print(f"  {line}")
            return True
        
        # Also check python processes that might be running codex
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        lines = result.stdout.strip().split('\n')
        python_procs = [line for line in lines[1:] if 'codex' in line.lower() or 'mcp' in line.lower()]
        if python_procs:
            print("Found Python processes that might be running codex:")
            for proc in python_procs:
                print(f"  {proc}")
            return True
        
        print("No codex or MCP-related processes found.")
        return False
        
    except Exception as e:
        print(f"Error checking processes: {e}", file=sys.stderr)
        return False

def check_unix_processes():
    """Check for codex processes on Unix-like systems."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        lines = result.stdout.split('\n')
        codex_procs = [line for line in lines if 'codex' in line.lower() and 'mcp' in line.lower()]
        
        if codex_procs:
            print("Found codex MCP processes:")
            for proc in codex_procs:
                print(f"  {proc}")
            return True
        
        print("No codex MCP processes found.")
        return False
        
    except Exception as e:
        print(f"Error checking processes: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    print("Checking for running MCP server processes...")
    print("=" * 60)
    
    is_windows = platform.system() == "Windows"
    
    if is_windows:
        found = check_windows_processes()
    else:
        found = check_unix_processes()
    
    print("=" * 60)
    
    if found:
        print("\nTo kill a process on Windows:")
        print("  taskkill /PID <pid> /F")
        print("  Or use Task Manager (Ctrl+Shift+Esc)")
        sys.exit(1)
    else:
        print("\n✓ No MCP server processes are running.")
        sys.exit(0)

