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


def claude_print(
    prompt: str,
    *,
    model: str,
    cwd: Path,
    allowed_tools: list[str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run ``pnpm dlx @anthropic-ai/claude-code --print`` and return the result.

    Unlike :func:`spawn_claude` (interactive) this captures stdout/stderr
    and pipes *prompt* via stdin.
    """
    argv = [
        "pnpm",
        "dlx",
        "@anthropic-ai/claude-code",
        "--print",
        "--model",
        model,
    ]
    if allowed_tools:
        for tool in allowed_tools:
            argv.extend(["--allowed-tools", tool])
    return subprocess.run(
        argv,
        input=prompt,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=timeout,
    )
