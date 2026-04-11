"""Claude Code interactive session helper."""

from __future__ import annotations

import subprocess
from pathlib import Path


def spawn_claude(prompt: str, cwd: Path) -> int:
    """Spawn an interactive Claude Code session. Returns the exit code."""
    result = subprocess.run(
        ["claude", prompt],
        cwd=str(cwd),
        check=False,
    )
    return result.returncode
