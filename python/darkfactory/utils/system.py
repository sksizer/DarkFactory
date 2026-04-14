"""System-level utility checks."""

from __future__ import annotations

import shutil
from pathlib import Path


def check_prerequisites(cwd: Path, *, require_claude: bool = True) -> None:
    """Fail fast if required tools are missing or cwd is not a git repo."""
    if require_claude and shutil.which("claude") is None:
        raise SystemExit(
            "error: 'claude' is not on PATH. Install Claude Code to use 'prd discuss'."
        )
    if shutil.which("git") is None:
        raise SystemExit("error: 'git' is not on PATH.")
    if not (cwd / ".git").exists():
        # Walk up to check if we're inside a git worktree (avoids importing
        # from cli, which would be an inverted dependency).
        current = cwd.resolve()
        while current != current.parent:
            if (current / ".git").exists():
                break
            current = current.parent
        else:
            raise SystemExit(
                "error: current directory is not inside a git working tree."
            )
