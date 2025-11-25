# parallel-codex

**Primary implementation** of Parallel Codex - Python toolkit for orchestrating Parallel Codex agents working in isolated Git worktrees. This package contains the core logic and CLI tools for managing agent worktrees, tmux sessions, a Textual TUI, and Codex agent orchestration.

**Status:** Core worktree management is implemented. Agent orchestration logic is in development. This is the main package that will be wrapped by npm and Homebrew in the future.

## Install

```bash
uv tool install parallel-codex
# or: pip install parallel-codex
```

You’ll get two CLIs:
- `pcodex` – minimal, cross‑platform helper that manages git worktrees + tmux and can run `codex .`
- `parallel-codex` – launches the Textual TUI (pass `--dev-log-panel` during development to mirror logs in-app)

Prerequisites:
- `git` and `tmux` on PATH. On Windows without tmux, `pcodex` auto-falls back to `wsl.exe -- tmux ...`.
- The `codex` command should be available if you use `--run-codex` or the TUI.
- Codex CLI must be logged in: run `echo $OPENAI_API_KEY | codex login --with-api-key` once before using the TUI.

On all platforms, the Codex CLI path is resolved once (from `PARALLEL_CODEX_CODEX_PATH` if set, otherwise from your
`PATH`) and that full path is reused for subprocess calls. This improves robustness on Windows (especially when
shims/launchers are involved) and produces clearer errors if the resolved `codex` binary cannot be executed or is not
authenticated. For unusual setups (for example, npm-style shims on Windows), you can point directly at the Codex
binary via `PARALLEL_CODEX_CODEX_PATH`:

```bash
# POSIX shells (macOS, Linux, WSL, Git Bash)
export PARALLEL_CODEX_CODEX_PATH=/full/path/to/codex
# Windows (cmd.exe)
set PARALLEL_CODEX_CODEX_PATH=C:\Users\you\AppData\Roaming\npm\codex.CMD
# Windows (PowerShell)
$env:PARALLEL_CODEX_CODEX_PATH="C:\Users\you\AppData\Roaming\npm\codex.CMD"
```

## Development commands

From `packages/python-package`, common development commands are:

- `uv sync` – install dependencies
- `uv run pytest` – run tests
- `uv run ruff check .` – lint the codebase
- `uv run mypy src/` – type-check the code

## CLI Usage (quickstart)

```bash
pcodex up reviewer main --run-codex --attach
pcodex switch reviewer
pcodex list
pcodex prune reviewer --kill-session --remove-dir
```

## CLI Usage (development, no install)

Development now revolves exclusively around the TUI. Keep a dev log panel open at all times so you can see every `logging`
call and stdout/stderr line inside the in-app widget.

### Default dev loop (from `packages/python-package`)

```bash
cd packages/python-package
uv run src/main.py tui --dev-log-panel
```

The positional `tui` argument is optional, but it remains supported so existing scripts keep working. Passing
`--dev-log-panel` enables the scrolling log widget so any `logging.getLogger(__name__).info(...)` (or prints) appear
without tailing a file.

On **Windows with cmd.exe**:

```cmd
cd C:\path\to\parallel-codex\packages\python-package
uv run python src\main.py tui --dev-log-panel
```

### Default dev loop from the repo root (`uv --project`)

When you prefer to stay at the monorepo root, pin `uv` to the Python package and run:

```bash
uv run --project packages/python-package python -m parallel_codex.cli tui --dev-log-panel
```

On **Windows with cmd.exe**:

```cmd
cd C:\path\to\parallel-codex
uv run --project packages\python-package python -m parallel_codex.cli tui --dev-log-panel
```

These invocations respect `PARALLEL_CODEX_REPO_ROOT` for pointing the TUI at a repo outside your current directory.

Published CLIs:

- `parallel-codex [tui] [--dev-log-panel] ...` – launch the Textual TUI (only supported command).
- `pcodex up <agent> <branch>` – ensure git worktree, ensure tmux session, optionally run `codex .`, and attach.
- `pcodex switch <agent>` – switch/attach to the tmux session.
- `pcodex list` – list worktrees and tmux session state.
- `pcodex prune <agent> [--kill-session] [--remove-dir]` – kill session and/or remove directory.

### TUI usage

The TUI is aimed at running several Codex sessions in parallel, each in its own git worktree:

- One `codex mcp-server` subprocess is spawned and shared for all sessions.
- Each session gets its own branch and worktree under `./.agents/<session-name>`.
- Your IDE can open each worktree separately to compare changes across sessions.

Launch the TUI from the root of your git repo (add `--dev-log-panel` during development to surface logs inside the widget):

```bash
parallel-codex tui \
  --repo . \
  --agents-base ./.agents \
  --model gpt-5-codex \
  --sandbox workspace-write \
  --dev-log-panel
```

Keyboard shortcuts:

- `Ctrl+N` – create a new session (up to three visible side by side; further sessions can be managed but are currently hidden from the main row).
- `Ctrl+Tab` – cycle focused session (and move the caret to that session's input).
- `Ctrl+W` – close the focused session.
- `Esc` – focus the input of the currently focused session.

Per-session worktrees:

- For each new session `session-N`, the TUI creates or reuses a branch like `pcx/session-N` and a worktree under `./.agents/session-N`.
- Codex runs with `workspace_path` pointing at that worktree, so all file edits are isolated per session.
- You can manually mix changes between sessions later using normal git operations (e.g. `git merge pcx/session-1` from another branch).

#### Env-based TUI defaults

By default, `parallel-codex tui` assumes that `--repo` points at the current working directory. For development
workflows where the Python package lives inside a larger git repo, you can use `PARALLEL_CODEX_REPO_ROOT` to point the
TUI at the real git root without changing your CWD:

```bash
# POSIX shells (macOS, Linux, WSL, Git Bash)
export PARALLEL_CODEX_REPO_ROOT=/path/to/your/parallel-codex
parallel-codex tui
```

When running the TUI via `uv run` inside this repository, this allows you to keep `--project` pointing at the
`packages/python-package` subdirectory while still using the top-level git repo as the TUI repo root:

```bash
# Recommended on Windows/monorepo setups (POSIX example shown here):
export PARALLEL_CODEX_REPO_ROOT=/path/to/your/parallel-codex
uv run --project packages/python-package python -m parallel_codex.cli tui
```

On **Windows with cmd.exe**, use `set` instead of `export`:

```cmd
REM Recommended first step when developing on Windows in this repo:
set PARALLEL_CODEX_REPO_ROOT=C:\path\to\your\parallel-codex
uv run --project packages\python-package python -m parallel_codex.cli tui
```

On **Windows with PowerShell**, use the `$env:` prefix:

```powershell
$env:PARALLEL_CODEX_REPO_ROOT = "C:\path\to\your\parallel-codex"
uv run --project packages\python-package python -m parallel_codex.cli tui
```

#### Logging via the dev panel

The `--dev-log-panel` flag is now the default development mode. It wires Python's standard `logging` module plus
stdout/stderr directly into the in-app widget, so you can emit diagnostics without hunting for files.

```python
import logging

LOG = logging.getLogger(__name__)
LOG.info("Bootstrapping repo sync for %s", repo_root)
```

Anything logged this way (or printed) scrolls live in the dev panel, which makes it the preferred way to surface debug
information while iterating on agents.
