# Repository Guidelines

## Project Structure & Module Organization
The root is an npm workspace (`package.json`) that orchestrates packages under `packages/`. TypeScript sources live in `packages/typescript-package/src/`, with distribution artifacts generated in `dist/`. Python code resides in `packages/python-package/src/`, with tests in `packages/python-package/tests/`. Shared documentation goes in `README.md` files colocated with each package; assets belong in `assets/`.

## Build, Test, and Development Commands
- `npm install` – bootstrap all workspaces.
- `npm run build` – compile every workspace (`tsc` for TypeScript, `uv build` for Python).
- `npm run test` – execute workspace test suites (`vitest` for TypeScript, `pytest` via `uv run` for Python).
- `npm run lint` – run linting across workspaces (`eslint` and `ruff`).
- Package-specific: `npm run build` / `npm test` within `packages/typescript-package`, and `uv run pytest` or `uv run ruff check .` inside `packages/python-package`.

## Coding Style & Naming Conventions
TypeScript follows ESLint defaults with TypeScript-specific rules; keep files under `src/`, use explicit exports, and prefer camelCase for functions and PascalCase for types. Python code targets Ruff’s defaults (PEP 8 with modern conventions); prefer snake_case for functions and modules. Maintain module boundaries: shared helpers stay within their package and are exposed through the primary entry file.

## Testing Guidelines
TypeScript tests use Vitest; mirror source structure under `src/__tests__` or inline `*.test.ts`. Python tests live in `packages/python-package/tests/` and rely on pytest. Add regression coverage for new features, and ensure `npm run test` succeeds before opening a PR. Where feasible, include integration-style tests that exercise package APIs consumed by agents.

## Commit & Pull Request Guidelines
Write concise, imperative commit subjects (e.g., `Add dev deploy workflow guard`). Group unrelated work into separate commits. Before raising a PR, run build, test, and lint commands locally. PR descriptions should summarize the change, call out risk areas, and link issues or Changesets when relevant. Include screenshots or terminal output only when they clarify behavior. Keep PRs focused; use draft PRs for early feedback.

## Security & Configuration Tips
Secrets are environment-scoped in GitHub Actions (e.g., `NPM_PUBLISH_TOKEN`). Ensure workflows targeting `production` or `development` environments have the necessary secrets configured. Never commit `.npmrc`, `.env`, or credentials—use GitHub environments and repository secrets instead.
