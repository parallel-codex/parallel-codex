# parallel-codex-python

Python helpers for orchestrating Parallel Codex agents working in isolated Git worktrees. The toolkit offers a typed core module and a small CLI for planning agent worktrees that the TypeScript layer can execute.

## Commands

- `uv sync` – install dependencies defined in `pyproject.toml`
- `uv build` – build a wheel and sdist using Hatchling
- `uv run pytest` – execute the test suite
- `uv run ruff check .` – lint the codebase
- `uv run mypy src/` – run type checking with MyPy

## CLI Usage

During development you can run the CLI without installing the package:

```bash
uv run src/main.py plan reviewer main --base-dir ./.agents
```

The published CLI exposes a few sub-commands:

- `parallel-codex plan <agent> <branch>` – calculate (and optionally materialise) a worktree plan.
- `parallel-codex list` – list discovered plans inside a base directory.
- `parallel-codex prune <agent>` – remove stored metadata, with `--prune-dir` to delete the folder entirely.

Each sub-command accepts `--base-dir` to target a custom location (defaults to `./.agents`).

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
