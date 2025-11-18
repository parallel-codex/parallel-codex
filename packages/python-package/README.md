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
- `parallel-codex` – lower-level planner/list/prune for worktree metadata plus a TUI

Prerequisites:
- `git` and `tmux` on PATH. On Windows without tmux, `pcodex` auto-falls back to `wsl.exe -- tmux ...`.
- The `codex` command should be available if you use `--run-codex` or the TUI.
- Codex CLI must be logged in: run `echo $OPENAI_API_KEY | codex login --with-api-key` once before using the TUI.

On all platforms, the Codex CLI path is resolved once using your `PATH` and that full path is reused for subprocess calls.
This improves robustness on Windows (especially when shims/launchers are involved) and produces clearer errors if the
resolved `codex` binary cannot be executed or is not authenticated.

## Commands

- `uv sync` – install dependencies defined in `pyproject.toml`
- `uv build` – build a wheel and sdist using Hatchling
- `uv run pytest` – execute the test suite
- `uv run ruff check .` – lint the codebase
- `uv run mypy src/` – run type checking with MyPy

## Release Checklist

**Note:** This is the primary package. Publishing is fully implemented and working.

1. Update the `version` field in `pyproject.toml`.
2. Commit and push the changes.
3. Tag the commit with `py-vX.Y.Z` (or `vX.Y.Z`) and push the tag to trigger the GitHub Actions publish workflow.
4. Confirm the new release appears on [PyPI](https://pypi.org/project/parallel-codex/).

Once the core logic is complete, npm and Homebrew wrappers will be developed to provide alternative installation methods.

## CLI Usage (quickstart)

```bash
pcodex up reviewer main --run-codex --attach
pcodex switch reviewer
pcodex list
pcodex prune reviewer --kill-session --remove-dir
```

## CLI Usage (development, no install)

Run the CLIs without installing the package:

```bash
uv run src/main.py plan reviewer main --base-dir ./.agents
# or the single-file helper:
uv run src/parallel_codex/pcodex.py up reviewer main --run-codex --attach
```

The published CLIs expose sub-commands:

- `parallel-codex plan <agent> <branch>` – calculate (and optionally materialise) a worktree plan.
- `parallel-codex list` – list discovered plans inside a base directory.
- `parallel-codex prune <agent>` – remove stored metadata, with `--prune-dir` to delete the folder entirely.
- `parallel-codex tui` – launch a Textual TUI that drives multiple Codex sessions in parallel.
- `pcodex up <agent> <branch>` – ensure git worktree, ensure tmux session, optionally run `codex .`, and attach.
- `pcodex switch <agent>` – switch/attach to the tmux session.
- `pcodex list` – list worktrees and tmux session state.
- `pcodex prune <agent> [--kill-session] [--remove-dir]` – kill session and/or remove directory.

Each sub-command accepts `--base-dir` to target a custom location (defaults to `./.agents`).

### TUI usage

The TUI is aimed at running several Codex sessions in parallel, each in its own git worktree:

- One `codex mcp-server` subprocess is spawned and shared for all sessions.
- Each session gets its own branch and worktree under `./.agents/<session-name>`.
- Your IDE can open each worktree separately to compare changes across sessions.

Launch the TUI from the root of your git repo:

```bash
parallel-codex tui \
  --repo . \
  --agents-base ./.agents \
  --model gpt-5-codex \
  --sandbox workspace-write
```

Keyboard shortcuts:

- `Ctrl+N` – create a new session (up to three visible side by side; further sessions can be managed but are currently hidden from the main row).
- `Ctrl+Tab` – cycle focused session.
- `Ctrl+1/2/3` – focus one of the first three panes.
- `Ctrl+W` – close the focused session.
- `Esc` – focus the prompt input.

Per-session worktrees:

- For each new session `session-N`, the TUI creates or reuses a branch like `pcx/session-N` and a worktree under `./.agents/session-N`.
- Codex runs with `workspace_path` pointing at that worktree, so all file edits are isolated per session.
- You can manually mix changes between sessions later using normal git operations (e.g. `git merge pcx/session-1` from another branch).

## Library Usage

Import the helpers in automation scripts:

```python
from pathlib import Path
from parallel_codex import plan_worktree

plan = plan_worktree(Path("./agents"), "summariser", "feature/summary")
print(plan.path)
```

Or rely on the CLI for quick experiments:

```bash
uv run parallel-codex summariser feature/summary --base-dir ./agents
```

The CLI prints a single line summary describing the worktree location, agent name, and branch target.
