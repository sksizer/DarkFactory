"""Claude Code subprocess helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

EffortLevel = Literal["low", "medium", "high", "max"]
"""Claude Code adaptive-reasoning effort levels.

Mirrors the values accepted by the ``claude --effort`` CLI flag (see
https://code.claude.com/docs/en/model-config#adjust-effort-level).
``max`` is Opus 4.6 only and session-scoped — passing it to a model that
doesn't support it will surface as a Claude Code error at invocation
time, which matches this project's "hard failures over silent
degradation" principle.
"""


def spawn_claude(
    prompt: str,
    cwd: Path,
    *,
    effort_level: EffortLevel | None = None,
) -> int:
    """Spawn an interactive Claude Code session. Returns the exit code."""
    argv: list[str] = ["claude"]
    if effort_level is not None:
        argv.extend(["--effort", effort_level])
    argv.append(prompt)

    result = subprocess.run(
        argv,
        cwd=str(cwd),
        check=False,
    )
    return result.returncode
