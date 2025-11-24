![Parallel Codex banner](assets/banner.png)

# Parallel Codex Monorepo

Parallel Codex is a developer-convenience CLI that spins up tmux-based workspaces, each anchored to an autonomous Codex coding agent. Every session owns its own Git worktree, letting multiple branches evolve in parallel while the CLI handles session lifecycle, context sharing, and pull-request orchestration.

## Project Status

**Current State:**
- ✅ Python package implementation (core worktree management)
- ✅ Python publishing pipeline (PyPI)
- 🚧 Core agent orchestration logic (in development)
- 📋 npm wrapper (planned)
- 📋 Homebrew package (planned)

This project is **Python-first**. The core implementation is being developed in Python, and once the main logic is complete, npm and Homebrew wrappers will be added to provide alternative installation methods.

## CLI Overview

- Launches tmux sessions that are pre-wired with an agent process, terminals, and editor panes so you can jump straight into problem solving.
- Ensures each session runs inside its own Git worktree, keeping branches isolated and making it safe to experiment or open several PRs simultaneously.
- Offers workflow helpers to synchronize code, hand off tasks between agents, and surface status dashboards across your tmux windows.

## Installation

**Currently Available:**
- **uv**: `uv tool install parallel-codex`
- **pip**: `pip install parallel-codex`

**Planned (not yet available):**
- **npm**: `npm install -g @parallel-codex/typescript-package` (wrapper coming soon)
- **brew**: `brew install parallel-codex` (Homebrew formula coming soon)

## Usage

Quickstart (minimal CLI):

```bash
# install (either works)
uv tool install parallel-codex
# or: pip install parallel-codex

# start an agent worktree + tmux, run codex, and attach
pcodex up reviewer main --run-codex --attach

# later, switch/attach to the session
pcodex switch reviewer

# list worktrees and tmux state
pcodex list

# prune resources
pcodex prune reviewer --kill-session --remove-dir
```

Prerequisites:
- `git` and `tmux` on PATH. On Windows without tmux, `pcodex` auto-falls back to `wsl.exe -- tmux ...`.
- The `codex` command should be available if you use `--run-codex`.

Dev without installing:
```bash
uv run packages/python-package/src/parallel_codex/pcodex.py up reviewer main --run-codex --attach
```

### Dev TUI (Python package)

To develop and run the Textual TUI from this monorepo without installing the package, configure the repo root via an
environment variable and use the Python package as the `uv` project:

```bash
# POSIX shells (macOS, Linux, WSL, Git Bash) – set once in your shell profile
export PARALLEL_CODEX_REPO_ROOT=/path/to/this/parallel-codex/checkout

# Then, from anywhere:
uv run --project packages/python-package python -m parallel_codex.cli tui
```

## With logging
```bash
set TEXTUAL_LOG=textual.log && uv run --project packages/python-package python -m parallel_codex.cli tui
```

On **Windows with cmd.exe**, use `set` instead of `export`:

```cmd
set PARALLEL_CODEX_REPO_ROOT=C:\path\to\this\parallel-codex\checkout
uv run --project packages\python-package python -m parallel_codex.cli tui
```

On **Windows with PowerShell**, use the `$env:` prefix:

```powershell
$env:PARALLEL_CODEX_REPO_ROOT = "C:\path\to\this\parallel-codex\checkout"
uv run --project packages\python-package python -m parallel_codex.cli tui
```

This keeps the TUI’s `--repo` pointing at your actual git root while `uv` still runs against the `packages/python-package`
project. See `packages/python-package/README.md` for more details on `PARALLEL_CODEX_REPO_ROOT` and the optional
`PARALLEL_CODEX_CODEX_PATH` override used to locate the `codex` CLI.

Advanced CLI (original):

Run `parallel-codex --help` after installation to explore planning/listing/pruning worktree metadata used by higher-level tooling.

## Repository Layout

```
.
├── .github/
│   ├── actions/
│   │   ├── build-python/
│   │   └── build-ts/
│   └── workflows/
│       ├── ci.yml
│       ├── create-release-pr.yml
│       ├── deploy-python.yml
│       ├── deploy-ts.yml
│       └── release.yml
├── package.json                    # npm workspace root (for future npm wrapper)
├── packages/
│   ├── python-package/            # Primary implementation (Python)
│   └── typescript-package/        # Future npm wrapper (placeholder)
├── pyproject.toml
├── uv.lock
└── README.md
```

**Note:** The TypeScript package currently contains placeholder code. It will be developed into an npm wrapper once the core Python logic is complete.

## Tooling Overview

- **Python 3.11+ & uv** for `packages/python-package` (primary implementation)
- **Node.js & npm workspaces** for `packages/typescript-package` (future npm wrapper)
- **Pytest / Ruff** for Python tests and linting
- **Vitest / ESLint** for TypeScript tests and linting (when wrapper is implemented)
- **GitHub Actions** workflows for CI, deployments, and automated release PRs
  - Python publishes on tags `py-v*` (and also plain `v*` semver tags) after the `packages/python-package` version is bumped.
  - TypeScript publishing will be enabled once the npm wrapper is implemented.

## Branch Strategy

- `dev` is the canonical development branch. All feature work merges here first, kicking off the staging builds defined in the GitHub Actions deployment pipeline configs.
- `main` tracks production-ready releases. Release PRs flow from `dev` into `main`, which triggers the publish jobs.

## Getting Started

1. Install dependencies:
   - `uv sync packages/python-package` to install Python dependencies
   - `npm install` at the repository root (optional, for future npm wrapper development)
2. Build packages:
   - `uv build packages/python-package` (Python package)
   - `npm run build --workspace @parallel-codex/typescript-package` (TypeScript wrapper - placeholder)
3. Run tests:
   - `uv run --project packages/python-package pytest` (Python tests)
   - `npm test --workspace @parallel-codex/typescript-package` (TypeScript tests - placeholder)
4. Explore the Python CLI locally:
   - `uv run packages/python-package/src/main.py --help`
   - `uv run packages/python-package/src/main.py plan reviewer main`
   - Or use the single-file helper: `uv run packages/python-package/src/parallel_codex/pcodex.py up reviewer main --run-codex --attach`

**Note:** The TypeScript package is currently a placeholder. Focus development on the Python package until the core logic is complete.

## Releasing the Python Package

**Currently Available:** Only Python package publishing is implemented.

1. Bump `version` in `packages/python-package/pyproject.toml`.
2. Commit the change (and any release notes if desired).
3. Push the commit, then tag it with either `py-vX.Y.Z` or `vX.Y.Z` and push the tag (e.g. `git tag py-v0.1.2 && git push origin py-v0.1.2`).
4. The `Deploy Python Package` workflow builds, tests, and publishes the artifacts to PyPI using trusted publishing. You can also trigger it manually via the "Deploy Python Package" workflow if you need a dry run or a re-publish.
5. Verify the release on [PyPI](https://pypi.org/project/parallel-codex/).

**Future:** npm and Homebrew publishing will be added once the npm wrapper and Homebrew formula are implemented.

### Single-file helper (pcodex)

For a zero-dependency experience, a one-file helper lives inside the Python package and is exposed as `pcodex`:

```bash
# Ensure worktree + tmux, run codex, and attach (installed)
pcodex up reviewer main --run-codex --attach

# Or run without installing (dev)
uv run packages/python-package/src/parallel_codex/pcodex.py up reviewer main --run-codex --attach

# Switch/attach later
pcodex switch reviewer

# List known worktrees and tmux state
pcodex list

# Prune (kill tmux + remove dir)
pcodex prune reviewer --kill-session --remove-dir
```

Notes:
- Requires `git` and `tmux` on PATH. On Windows without tmux, it falls back to `wsl.exe -- tmux ...`.
- Worktrees live under `./.agents/<agent>` by default; override with `--base-dir`.
