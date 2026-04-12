"""Shell command runner shared by workflow and system runners."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_shell(
    cmd: str,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a shell command once and return the completed-process result."""
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
