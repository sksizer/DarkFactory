"""Git subprocess primitives — single gateway for all git calls.

Two thin wrappers over ``subprocess.run(["git", ...])``:

- :func:`git_run` — runs git, never raises; returns ``Ok(None, stdout=...)``
  on exit 0, ``GitErr`` on non-zero exit.
- :func:`git_probe` — timeout-bounded variant; returns ``Ok(None)``,
  ``GitErr``, or ``GitTimeout``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from darkfactory.utils.git._types import CheckResult, GitErr, GitTimeout, Ok, ProbeResult


def git_run(*args: str, cwd: Path) -> CheckResult:
    """Run ``git *args`` from ``cwd``; never raises.

    Returns ``Ok(None, stdout=...)`` on exit 0, ``GitErr`` on non-zero.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return GitErr(result.returncode, result.stdout, result.stderr, ["git", *args])
    return Ok(None, stdout=result.stdout)


def git_probe(*args: str, cwd: Path, timeout: int = 10) -> ProbeResult:
    """Run ``git *args`` from ``cwd`` with a timeout; never raises.

    Returns ``Ok(None)``, ``GitErr``, or ``GitTimeout``.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return GitTimeout(["git", *args], timeout)
    except Exception as exc:
        return GitErr(-1, "", str(exc), ["git", *args])
    if result.returncode != 0:
        return GitErr(result.returncode, result.stdout, result.stderr, ["git", *args])
    return Ok(None, stdout=result.stdout)
