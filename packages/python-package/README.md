# parallel-codex

**Primary implementation** of Parallel Codex - Python toolkit for orchestrating Parallel Codex agents working in isolated Git worktrees.

**Current Status:** This package currently provides a **Textual TUI** for managing parallel agent sessions.

## Install

```bash
uv tool install parallel-codex
# or: pip install parallel-codex
```

This installs the `parallel-codex` CLI.

Prerequisites:
- The `codex` command must be available on your PATH.
- Codex CLI must be logged in: run `echo $OPENAI_API_KEY | codex login --with-api-key` once before using the TUI.

## TUI Usage

The TUI is the main entry point. It allows you to manage multiple Codex sessions, where each session operates on its own git worktree.

```bash
# Run the TUI
parallel-codex tui
```

### Development Mode

To see internal logs and debug information (MCP activity, stdout/stderr) inside the application:

```bash
parallel-codex tui --dev-log-panel
```

### TUI Features

- **Multiple Sessions:** Create and switch between up to three visible sessions (`Ctrl+N`, `Ctrl+Tab`).
- **Isolated Worktrees:** Each session creates a git worktree under `./.agents/<session-name>` and checks out a branch `pcx/<session-name>`.
- **Codex Integration:** Chats are sent to the `codex` MCP server, with file edits applied to the specific session's worktree.

## Development

From `packages/python-package`:

```bash
# Install dependencies
uv sync

# Run TUI from source
uv run src/main.py tui --dev-log-panel
```

Or from the repo root:

```bash
uv run --project packages/python-package python -m parallel_codex.cli tui --dev-log-panel
```

To configure the repository root used by the TUI when running from source:

```bash
export PARALLEL_CODEX_REPO_ROOT=/path/to/your/repo
```