# Repository Guidelines

## Project Structure & Module Organization

**Note:** This is a Python-first project. The core implementation lives in `packages/python-package/`. The TypeScript package is currently a placeholder that will become an npm wrapper once the core logic is complete.

The root is an npm workspace (`package.json`) that orchestrates packages under `packages/`. 
- **Python package** (`packages/python-package/`): Primary implementation containing core logic, CLI tools, and worktree management. Code resides in `src/`, with tests in `tests/`.
- **TypeScript package** (`packages/typescript-package/`): Currently a placeholder. Future npm wrapper for the Python CLI. Sources live in `src/`, with distribution artifacts generated in `dist/`.

Shared documentation goes in `README.md` files colocated with each package; assets belong in `assets/`.

## Build, Test, and Development Commands

**Focus:** Primary development should be on the Python package. TypeScript package is placeholder infrastructure.

- `npm install` – bootstrap all workspaces (optional for TypeScript wrapper development).
- `npm run build` – compile every workspace (`tsc` for TypeScript placeholder, `uv build` for Python).
- `npm run test` – execute workspace test suites (`vitest` for TypeScript placeholder, `pytest` via `uv run` for Python).
- `npm run lint` – run linting across workspaces (`eslint` for TypeScript placeholder, `ruff` for Python).

**Python-specific commands** (primary development):
- `uv sync packages/python-package` – install Python dependencies
- `uv build packages/python-package` – build Python package
- `uv run --project packages/python-package pytest` – run Python tests
- `uv run --project packages/python-package ruff check .` – lint Python code

**TypeScript-specific commands** (placeholder/future wrapper):
- `npm run build` / `npm test` within `packages/typescript-package` – placeholder infrastructure

## Coding Style & Naming Conventions

**Python (primary):** Follow Ruff's defaults (PEP 8 with modern conventions); prefer snake_case for functions and modules. Keep files under `src/`, use explicit exports, and maintain clear module boundaries.

**TypeScript (future wrapper):** When implementing the npm wrapper, follow ESLint defaults with TypeScript-specific rules; keep files under `src/`, use explicit exports, and prefer camelCase for functions and PascalCase for types.

Maintain module boundaries: shared helpers stay within their package and are exposed through the primary entry file.

## Testing Guidelines

**Python (primary):** Tests live in `packages/python-package/tests/` and rely on pytest. Add regression coverage for new features. Ensure `uv run --project packages/python-package pytest` succeeds before opening a PR.

**TypeScript (future wrapper):** When implementing the npm wrapper, tests will use Vitest; mirror source structure under `src/__tests__` or inline `*.test.ts`.

Where feasible, include integration-style tests that exercise package APIs consumed by agents. Focus testing efforts on the Python implementation first.

## Commit & Pull Request Guidelines

Write concise, imperative commit subjects (e.g., `Add dev deploy workflow guard`). Group unrelated work into separate commits. 

**Before raising a PR:**
- Run Python build, test, and lint commands locally (`uv build`, `uv run pytest`, `uv run ruff check`)
- If touching TypeScript placeholder code, ensure `npm run build` and `npm test` still pass
- Ensure `npm run test` succeeds (runs both Python and TypeScript tests)

PR descriptions should summarize the change, call out risk areas, and link issues or Changesets when relevant. Include screenshots or terminal output only when they clarify behavior. Keep PRs focused; use draft PRs for early feedback.

**Development Priority:** Focus PRs on Python implementation first. TypeScript wrapper development should wait until core Python logic is complete.

## Security & Configuration Tips

Secrets are environment-scoped in GitHub Actions (e.g., `NPM_PUBLISH_TOKEN` for future npm publishing, PyPI trusted publishing for Python). Ensure workflows targeting `production` or `development` environments have the necessary secrets configured. 

**Currently Active:**
- Python package publishing to PyPI (trusted publishing)

**Future:**
- npm publishing (when wrapper is implemented)
- Homebrew formula publishing

Never commit `.npmrc`, `.env`, or credentials—use GitHub environments and repository secrets instead.
