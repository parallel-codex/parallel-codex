# Parallel Codex Monorepo

Parallel Codex is a developer-convenience CLI that spins up tmux-based workspaces, each anchored to an autonomous Codex coding agent. Every session owns its own Git worktree, letting multiple branches evolve in parallel while the CLI handles session lifecycle, context sharing, and pull-request orchestration. This repository hosts the TypeScript and Python toolkits plus the CI/CD automation that power those agents.

## CLI Overview

- Launches tmux sessions that are pre-wired with an agent process, terminals, and editor panes so you can jump straight into problem solving.
- Ensures each session runs inside its own Git worktree, keeping branches isolated and making it safe to experiment or open several PRs simultaneously.
- Offers workflow helpers to synchronize code, hand off tasks between agents, and surface status dashboards across your tmux windows.

## Installation

> The CLI is published for both Python- and Node.js-first workflows. Choose what fits best for your environment; all installs expose the same `parallel-codex` command.

- **uv**: `uv tool install parallel-codex-python`
- **pip**: `pip install parallel-codex-python`
- **npm**: `npm install -g @parallel-codex/typescript-package`

## Usage

Run `parallel-codex --help` after installation to explore session lifecycle commands, tmux layout presets, and multi-worktree automation features. The CLI guides you through creating agents, attaching them to new or existing branches, and managing concurrent work safely.

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
├── package.json
├── packages/
│   ├── python-package/
│   └── typescript-package/
├── pyproject.toml
├── uv.lock
└── README.md
```

## Tooling Overview

- **Node.js & npm workspaces** for `packages/typescript-package`
- **Python 3.11 & uv workspaces** for `packages/python-package`
- **Vitest / ESLint** for TypeScript tests and linting
- **Pytest / Ruff** for Python tests and linting
- **GitHub Actions** workflows for CI, deployments, and automated release PRs

## Branch Strategy

- `dev` is the canonical development branch. All feature work merges here first, kicking off the staging builds defined in the GitHub Actions deployment pipeline configs.
- `main` tracks production-ready releases. Release PRs flow from `dev` into `main`, which triggers the publish jobs.

## Getting Started

1. Install dependencies:
   - `npm install` at the repository root to bootstrap the workspaces
   - `uv sync packages/python-package` to install Python dependencies
2. Build packages:
   - `npm run build --workspace @parallel-codex/typescript-package`
   - `uv build packages/python-package`
3. Run tests:
   - `npm test --workspace @parallel-codex/typescript-package`
   - `uv run --project packages/python-package pytest`
4. Explore the Python CLI locally with `uv run packages/python-package/src/main.py --help` or invoke individual commands such as `uv run packages/python-package/src/main.py plan reviewer main`.

Configure npm and PyPI as trusted OIDC publishers for this repository before running deployments. The TypeScript workflow ships beta-tagged prereleases from `dev` and stable releases from `main`.
