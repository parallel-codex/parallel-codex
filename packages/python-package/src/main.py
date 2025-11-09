from __future__ import annotations

# Convenience entry point for local development. Allows running the CLI via
# `uv run src/main.py` without installing the package.
from parallel_codex.cli import run


if __name__ == "__main__":  # pragma: no cover
    run()
