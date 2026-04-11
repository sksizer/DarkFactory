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
        from darkfactory.cli._shared import _find_repo_root

        try:
            _find_repo_root(cwd)
        except SystemExit:
            raise SystemExit(
                "error: current directory is not inside a git working tree."
            )
