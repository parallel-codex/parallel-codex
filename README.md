![Parallel Codex banner](assets/banner.png)

# Parallel Codex Monorepo

Parallel Codex is a developer-convenience CLI that spins up tmux-based workspaces, each anchored to an autonomous Codex coding agent. Every session owns its own Git worktree, letting multiple branches evolve in parallel while the CLI handles session lifecycle, context sharing, and pull-request orchestration. This repository hosts the TypeScript and Python toolkits plus the CI/CD automation that power those agents.

## CLI Overview

- Launches tmux sessions that are pre-wired with an agent process, terminals, and editor panes so you can jump straight into problem solving.
- Ensures each session runs inside its own Git worktree, keeping branches isolated and making it safe to experiment or open several PRs simultaneously.
- Offers workflow helpers to synchronize code, hand off tasks between agents, and surface status dashboards across your tmux windows.

## Installation

> The CLI is published for both Python- and Node.js-first workflows. Choose what fits best for your environment; all installs expose the same `parallel-codex` command.

- **uv**: `uv tool install parallel-codex`
- **pip**: `pip install parallel-codex`
- **npm**: `npm install -g @parallel-codex/typescript-package`
- **brew**: `to be implemented`

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
  - Python publishes on tags `py-v*` (and also plain `v*` semver tags) after the `packages/python-package` version is bumped.
  - TypeScript publishes on tags `ts-v*` (pre-releases use npm `beta`/`next` tags).

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

## Releasing the Python Package

1. Bump `version` in `packages/python-package/pyproject.toml`.
2. Commit the change (and any release notes if desired).
3. Push the commit, then tag it with either `py-vX.Y.Z` or `vX.Y.Z` and push the tag (e.g. `git tag py-v0.1.2 && git push origin py-v0.1.2`).
4. The `Deploy Python Package` workflow builds, tests, and publishes the artifacts to PyPI using trusted publishing. You can also trigger it manually via the “Deploy Python Package” workflow if you need a dry run or a re-publish.
5. Verify the release on [PyPI](https://pypi.org/project/parallel-codex/).

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
