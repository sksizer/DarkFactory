"""Shared shell command runner."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_shell_once(
    cmd: str,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a shell command once and return the completed-process result.

    Merges ``env`` on top of ``os.environ`` so callers can inject
    task-specific variables without dropping system defaults.
    """
    full_env = dict(os.environ)
    full_env.update(env)

    return subprocess.run(
        cmd,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )
