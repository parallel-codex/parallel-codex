# @parallel-codex/typescript-package

**Status: Placeholder / Future npm wrapper**

This package is currently a placeholder. It will be developed into an npm wrapper for the Python `parallel-codex` package once the core Python logic is complete.

## Current State

- Contains placeholder code (greet function)
- Build infrastructure is set up
- Publishing workflows exist but are not active
- **Not ready for use** - focus development on `packages/python-package` first

## Future Plans

Once the Python implementation is complete, this package will:
- Provide an npm-based installation method (`npm install -g @parallel-codex/typescript-package`)
- Wrap the Python CLI to provide a Node.js-friendly interface
- Enable Homebrew package distribution

## Scripts

- `npm run build` – emit ESM and CJS bundles into `dist/` (placeholder)
- `npm test` – execute the Vitest suite (placeholder tests)
- `npm run lint` – lint the source files with ESLint

## Publishing

Publishing infrastructure exists but is not active. Once the wrapper is implemented, publishing will rely on npm's OIDC trusted publisher integration. Beta releases will flow from the canonical `dev` branch before stable artifacts are published from `main`.
