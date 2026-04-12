"""Git subprocess primitive — single gateway for all git calls.

:func:`git_run` runs git, never raises; returns ``Ok(None, stdout=...)``
on exit 0, ``GitErr`` on non-zero exit, ``Timeout`` when a timeout is
specified and exceeded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from darkfactory.utils._result import Timeout
from darkfactory.utils.git._types import (
    CheckResult,
    GitErr,
    Ok,
)


def git_run(
    *args: str, cwd: Path, timeout: int | None = None
) -> CheckResult:
    """Run ``git *args`` from ``cwd``; never raises.

    Returns ``Ok(None, stdout=...)`` on exit 0, ``GitErr`` on non-zero.
    When *timeout* is not ``None``, returns ``Timeout`` if the process
    exceeds the given number of seconds.
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
        return Timeout(["git", *args], timeout or 0)
    except Exception as exc:
        return GitErr(-1, "", str(exc), ["git", *args])
    if result.returncode != 0:
        return GitErr(result.returncode, result.stdout, result.stderr, ["git", *args])
    return Ok(None, stdout=result.stdout)
