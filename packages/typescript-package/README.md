# @parallel-codex/typescript-package

**Status: Wrapper design in progress**

This package will become the npm-facing wrapper for the Python `parallel-codex` CLI. Its role is to let Node.js users (`npm`, `npx`, `pnpm`, `yarn`) install and run the Parallel Codex tooling without thinking about Python packaging details.

## Wrapper Goals

- Ship a `parallel-codex` executable on the npm Registry that simply works on Node.js ≥ 20.
- Bootstrap or reuse a managed Python environment that contains the `parallel-codex` wheel matching this wrapper’s version.
- Forward CLI arguments verbatim to the Python implementation and stream stdout/stderr transparently.
- Expose a small JS API for embedding (`import { runCli } from '@parallel-codex/typescript-package'`) that mirrors the CLI behaviour.

## High-Level Architecture

1. **CLI shim (`bin/parallel-codex.js`)**  
   Registered in `package.json#bin`, resolves a Python runtime, and spawns `python -m parallel_codex.cli`.

2. **Bootstrap helper (`src/bootstrap.ts`)**  
   Lazily ensures a virtual environment under `~/.parallel-codex/python/<version>` using the system `python3` (≥ 3.11). Installs the pinned wheel via `pip install parallel-codex==<PY_VERSION>`.

3. **Version contract**  
   Wrapper version `X.Y.Z` depends on Python package `>=X.Y,<X.Y+1`. The list lives in `src/version-map.ts` so we can hotfix by republishing the JS package without touching Python.

4. **Execution layer (`src/run-cli.ts`)**  
   Uses `child_process.spawn` with `stdio: 'inherit'`, handles signals (`SIGINT`, `SIGTERM`), and exits with the Python process code.

5. **JIT download cache**  
   Wheels are cached in `~/.parallel-codex/cache/wheels/`. The bootstrapper skips re-downloads when the desired version already exists.

## CLI Behaviour

After publication, users will run:

```bash
npx @parallel-codex/typescript-package tui --dev-log-panel
# or
npm install -g @parallel-codex/typescript-package
parallel-codex tui
```

Runtime flow:

1. Resolve Python (checks `PARALLEL_CODEX_PYTHON`, then `python3`, then `py` on Windows).
2. Create or reuse the managed virtual environment.
3. Install/upgrade the `parallel-codex` wheel inside that environment if required.
4. Delegate execution to `parallel_codex.cli` with all original CLI flags.

Environment variables forwarded by default:

- `PARALLEL_CODEX_REPO_ROOT`
- `PARALLEL_CODEX_AGENTS_BASE`
- `OPENAI_API_KEY`
- Any `PARALLEL_CODEX_*` namespace variable

## JavaScript API

```ts
import { runCli } from '@parallel-codex/typescript-package';

await runCli({
  args: ['tui', '--dev-log-panel'],
  env: { PARALLEL_CODEX_REPO_ROOT: '/repo' },
  stdio: 'inherit',
});
```

`runCli` resolves Python the same way the executable does and returns the child process exit code. Callers can override the default cache directory or inject their own `pythonPath`.

## Planned Implementation Tasks

- [ ] Replace placeholder `greet` export with `runCli` plus helper utilities.
- [ ] Add `bin/parallel-codex.js` shim that wraps `runCli`.
- [ ] Implement bootstrapper with wheel download, integrity checks (SHA256), and semver guardrails.
- [ ] Write Vitest coverage for bootstrap edge cases (missing Python, corrupt wheel, upgrade path).
- [ ] Integrate Ruff-provided command list to ensure `--help` parity between Node and Python CLIs.

## Testing Strategy

- Unit tests (Vitest) for bootstrap resolver, wheel cache, and argument forwarding.
- Smoke tests invoked via `npm test:integration` that spin up a disposable temp directory, install the current wheel, and verify `parallel-codex tui --version`.
- CI matrix should run on macOS, Linux, and Windows with Python 3.11 and 3.12 available.

## Publishing Notes

- GitHub Actions workflow will publish on tags after the Python package is available on PyPI for the mapped version.
- `prepublishOnly` keeps emitting ESM/CJS bundles.
- Long term we will add a `postinstall` message guiding users when no suitable Python interpreter is detected (the install will still succeed; the CLI will emit a helpful error on first run).
