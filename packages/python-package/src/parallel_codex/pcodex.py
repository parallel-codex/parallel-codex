#!/usr/bin/env python3
"""
pcodex - ultra-minimal cross-platform CLI to manage agent worktrees + tmux sessions.

Commands:
  up <agent> <branch>      Ensure git worktree and tmux session;
                           optionally run `codex .` and attach/switch.
  switch <agent>           Switch/attach to tmux session.
  list                     List worktrees and tmux session status.
  prune <agent>            Optionally kill tmux session and/or remove the worktree directory.

Requires: git, tmux (or WSL with tmux installed).
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from pathlib import Path

BRANCH_METADATA = ".parallel-codex-branch"
DEFAULT_BASE_DIR = Path("./.agents")
SESSION_PREFIX = "pcx-"


def _supports_ansi() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("PCX_NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


ANSI = {
    "reset": "\x1b[0m",
    "green": "\x1b[32m",
    "red": "\x1b[31m",
    "cyan": "\x1b[36m",
    "dim": "\x1b[2m",
}
USE_ANSI = _supports_ansi()


def _c(code: str, text: str) -> str:
    if not USE_ANSI:
        return text
    return f"{ANSI.get(code, '')}{text}{ANSI['reset']}"


class Spinner:
    def __init__(self, message: str, done_text: str | None = None):
        self.message = message
        self.done_text = done_text or message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __enter__(self):
        if not sys.stdout.isatty():
            print(f"{self.message} …", flush=True)
            return self
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = self._frames[i % len(self._frames)]
            line = f"{_c('cyan', frame)} {_c('dim', self.message)}"
            print(f"\r{line}", end="", flush=True)
            time.sleep(0.08)
            i += 1

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        if sys.stdout.isatty():
            print("\r", end="")
        if exc is None:
            print(f"{_c('green', '✔')} {self.done_text}")
        else:
            print(f"{_c('red', '✖')} {self.done_text}")
        return False


def run(
    cmd: Iterable[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    kwargs = {
        "check": check,
        "cwd": str(cwd) if cwd else None,
        "env": env or os.environ.copy(),
        "text": True,
    }
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    return subprocess.run(list(cmd), **kwargs)  # type: ignore[arg-type]


def which(name: str) -> str | None:
    return shutil.which(name)


class Tmux:
    def __init__(self, prefix: list[str], path_mapper):
        self.prefix = prefix
        self.path_mapper = path_mapper

    def _cmd(self, *args: str) -> list[str]:
        return [*self.prefix, *args]

    def has_session(self, name: str) -> bool:
        proc = run(self._cmd("has-session", "-t", name), check=False, capture=True)
        return proc.returncode == 0

    def new_session(self, name: str, cwd: Path) -> None:
        run(self._cmd("new-session", "-ds", name, "-c", self.path_mapper(cwd)))

    def send_keys(self, name: str, command: str) -> None:
        run(self._cmd("send-keys", "-t", name, command, "C-m"))

    def switch_or_attach(self, name: str) -> None:
        inside_tmux = bool(os.environ.get("TMUX"))
        if inside_tmux:
            run(self._cmd("switch-client", "-t", name), check=False)
        else:
            run(self._cmd("attach", "-t", name), check=False)

    def kill_session(self, name: str) -> None:
        run(self._cmd("kill-session", "-t", name), check=False)


def _windows_wsl_path(path: Path) -> str:
    wsl = which("wsl.exe")
    if wsl:
        try:
            proc = run([wsl, "wslpath", "-a", str(path)], capture=True)
            return proc.stdout.strip()
        except Exception:
            pass
    p = str(path)
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest if rest.startswith('/') else '/' + rest}"
    return p.replace("\\", "/")


def tmux_strategy(*, prefer_wsl: bool = False) -> Tmux:
    is_windows = os.name == "nt"
    native_tmux = which("tmux")
    wsl = which("wsl.exe")
    if prefer_wsl and is_windows and wsl:
        return Tmux(prefix=[wsl, "--", "tmux"], path_mapper=_windows_wsl_path)
    if native_tmux:
        return Tmux(prefix=[native_tmux], path_mapper=lambda p: str(p))
    if is_windows:
        if wsl:
            return Tmux(prefix=[wsl, "--", "tmux"], path_mapper=_windows_wsl_path)
    return Tmux(prefix=["tmux"], path_mapper=lambda p: str(p))


def ensure_worktree(repo: Path, base_dir: Path, agent: str, branch: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    worktree = base_dir / agent
    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        run(["git", "-C", str(repo), "worktree", "add", "-B", branch, str(worktree)], check=True)
    except subprocess.CalledProcessError:
        pass
    try:
        (worktree / BRANCH_METADATA).write_text(f"{branch}\n", encoding="utf-8")
    except Exception:
        pass
    return worktree


def read_branch_file(worktree: Path) -> str | None:
    meta = worktree / BRANCH_METADATA
    if meta.exists():
        raw = meta.read_text(encoding="utf-8").strip()
        return raw or None
    return None


def cmd_up(args: argparse.Namespace) -> int:
    tmux = tmux_strategy(prefer_wsl=bool(getattr(args, "wsl", False)))
    session = SESSION_PREFIX + args.agent
    repo = Path(args.repo).resolve()
    base_dir = Path(args.base_dir).resolve()

    with Spinner(
        f"Ensuring worktree for agent '{args.agent}' on '{args.branch}'",
        "Worktree ensured",
    ):
        worktree = ensure_worktree(repo, base_dir, args.agent, args.branch)

    # If we're about to create the session for the first time, try to prepare
    # the Python environment so jumping into the session is ready to go.
    needs_session = not tmux.has_session(session)
    if needs_session and bool(getattr(args, "prep_env", False)):
        # Detect if tmux will run under WSL so we prep the env in the same OS.
        is_wsl_tmux = bool(
            tmux.prefix
            and os.path.basename(tmux.prefix[0]).lower().startswith("wsl")
        )
        if is_wsl_tmux:
            wsl = tmux.prefix[0]
            wsl_worktree = _windows_wsl_path(worktree)
            # Check if uv exists inside WSL
            uv_present = (
                run(
                    [wsl, "--", "bash", "-lc", "command -v uv >/dev/null 2>&1"],
                    check=False,
                ).returncode
                == 0
            )
            if uv_present:
                with Spinner(
                    "Preparing Python env in WSL (uv sync + install -e)",
                    "Python env ready",
                ):
                    commands = [
                        f"cd {shlex.quote(wsl_worktree)}",
                        "uv sync --project packages/python-package",
                        (
                            "uv run --project packages/python-package python -m pip install -e "
                            "packages/python-package"
                        ),
                    ]
                    cmd = " && ".join(commands)
                    run([wsl, "--", "bash", "-lc", cmd], check=False)
            else:
                print(_c("dim", "Tip: 'uv' not found in WSL; skipping dependency sync/install."))
        else:
            uv = which("uv")
            if uv:
                with Spinner(
                    "Preparing Python env (uv sync + install -e)",
                    "Python env ready",
                ):
                    # Best-effort; do not fail the whole command if these error
                    run(
                        [uv, "sync", "--project", "packages/python-package"],
                        check=False,
                        cwd=worktree,
                    )
                    run(
                        [
                            uv,
                            "run",
                            "--project",
                            "packages/python-package",
                            "python",
                            "-m",
                            "pip",
                            "install",
                            "-e",
                            "packages/python-package",
                        ],
                        check=False,
                        cwd=worktree,
                    )
            else:
                print(_c("dim", "Tip: 'uv' not found on PATH; skipping dependency sync/install."))

    with Spinner(f"Ensuring tmux session '{session}'", "Tmux session ready"):
        if needs_session:
            tmux.new_session(session, worktree)
        if args.run_codex:
            tmux.send_keys(session, "codex .")

    if args.attach:
        tmux.switch_or_attach(session)
    else:
        print(f"{_c('dim', 'Tip:')} run with --attach to switch/attach to the session.")
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    tmux = tmux_strategy(prefer_wsl=bool(getattr(args, "wsl", False)))
    session = SESSION_PREFIX + args.agent
    if not tmux.has_session(session):
        print(_c("red", f"Session '{session}' not found."), file=sys.stderr)
        return 1
    tmux.switch_or_attach(session)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    tmux = tmux_strategy(prefer_wsl=bool(getattr(args, "wsl", False)))
    base_dir = Path(args.base_dir).resolve()
    if not base_dir.exists():
        print("No worktrees found.")
        return 0
    any_printed = False
    for child in sorted(base_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        agent = child.name
        session = SESSION_PREFIX + agent
        branch = read_branch_file(child) or "?"
        tmux_up = "up" if tmux.has_session(session) else "down"
        print(f"agent={agent} branch={branch} path={child} tmux={tmux_up}")
        any_printed = True
    if not any_printed:
        print("No worktrees found.")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    tmux = tmux_strategy(prefer_wsl=bool(getattr(args, "wsl", False)))
    base_dir = Path(args.base_dir).resolve()
    worktree = base_dir / args.agent
    session = SESSION_PREFIX + args.agent
    if args.kill_session:
        with Spinner(f"Killing tmux session '{session}'", "Tmux session handled"):
            tmux.kill_session(session)
    if args.remove_dir and worktree.exists():
        with Spinner(f"Removing worktree directory '{worktree}'", "Worktree directory handled"):
            shutil.rmtree(worktree, ignore_errors=True)
    print(f"Pruned '{args.agent}'.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pcodex", description="Parallel Codex single-file CLI")
    p.add_argument(
        "--base-dir",
        default=str(DEFAULT_BASE_DIR),
        help="Directory for agent worktrees (default: ./.agents)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="Ensure worktree + tmux; optionally run codex and attach")
    up.add_argument("agent")
    up.add_argument("branch")
    up.add_argument("--repo", default=".", help="Path to git repo (default: .)")
    up.add_argument(
        "--attach",
        action="store_true",
        help="Switch/attach to the tmux session after setup",
    )
    up.add_argument("--run-codex", action="store_true", help="Send 'codex .' into the tmux session")
    up.add_argument(
        "--prep-env",
        action="store_true",
        help="Before creating the session, run 'uv sync' and install the package in editable mode",
    )
    up.add_argument(
        "--wsl",
        action="store_true",
        help="Force tmux to run via WSL on Windows and run commands inside WSL",
    )
    up.set_defaults(handler=cmd_up)

    sw = sub.add_parser("switch", help="Switch/attach to an existing tmux session")
    sw.add_argument("agent")
    sw.add_argument(
        "--wsl",
        action="store_true",
        help="Use WSL tmux session (Windows)",
    )
    sw.set_defaults(handler=cmd_switch)

    ls = sub.add_parser("list", help="List known agent worktrees and tmux state")
    ls.add_argument(
        "--wsl",
        action="store_true",
        help="Use WSL tmux instance to query session state (Windows)",
    )
    ls.set_defaults(handler=cmd_list)

    pr = sub.add_parser("prune", help="Kill tmux and/or remove a worktree directory")
    pr.add_argument("agent")
    pr.add_argument(
        "--kill-session",
        action="store_true",
        help="Kill the tmux session for the agent",
    )
    pr.add_argument("--remove-dir", action="store_true", help="Delete the agent worktree directory")
    pr.add_argument(
        "--wsl",
        action="store_true",
        help="Target a WSL tmux session (Windows)",
    )
    pr.set_defaults(handler=cmd_prune)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.error("No handler.")
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())


