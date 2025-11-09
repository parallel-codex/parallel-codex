# @parallel-codex/typescript-package

TypeScript utilities for coordinating Parallel Codex agents as they operate in parallel worktrees.

## Scripts

- `npm run build` – emit ESM and CJS bundles into `dist/`
- `npm test` – execute the Vitest suite
- `npm run lint` – lint the source files with ESLint

## Usage

```ts
import { greet } from '@parallel-codex/typescript-package';

console.log(greet('agent'));
```

## Publishing

Publishing relies on npm’s OIDC trusted publisher integration. The `prepublishOnly` script ensures the package is built prior to publication. Beta releases flow from the canonical `dev` branch before stable artifacts are published from `main`.
