![Parallel Codex banner](assets/banner.png)

# Parallel Codex Monorepo

Parallel Codex is a developer-convenience CLI for orchestrating autonomous Codex coding agents.

## Project Status

**Current State:**
- ✅ Python package (Textual TUI)
- ✅ Python publishing pipeline (PyPI)
- 🚧 Core agent orchestration logic (in development)

## Installation

```bash
uv tool install parallel-codex
# or: pip install parallel-codex
```

## Usage

The primary interface is the Textual TUI.

```bash
# Launch the TUI
parallel-codex tui

# Launch with dev logs visible
parallel-codex tui --dev-log-panel
```

The TUI allows you to spin up multiple agent sessions, each anchored to its own isolated Git worktree.

## Repository Layout

```
.
├── .github/workflows/      # CI/CD pipelines
├── packages/
│   ├── python-package/     # Core Python implementation (TUI)
│   └── typescript-package/ # (Placeholder)
└── README.md
```

## Development

1. **Install dependencies:**
   ```bash
   uv sync --project packages/python-package
   ```

2. **Run TUI from source:**
   ```bash
   uv run --project packages/python-package python -m parallel_codex.cli tui --dev-log-panel
   ```

3. **Run tests:**
   ```bash
   uv run --project packages/python-package pytest
   ```

## Releasing

1. Bump version in `packages/python-package/pyproject.toml`.
2. Commit and tag (e.g., `v1.0.2`).
3. Push the tag. GitHub Actions will build and publish to PyPI.