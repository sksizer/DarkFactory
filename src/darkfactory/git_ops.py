"""Shared git subprocess helpers.

Three thin wrappers over ``subprocess.run(["git", ...])``:

- :func:`git_check` — silent returncode probe; returns ``True`` on exit 0.
- :func:`git_run` — runs git and raises :class:`subprocess.CalledProcessError`
  with full stdout/stderr on non-zero exit.
- :func:`git_probe` — timeout-bounded probe; returns ``False`` (and logs a
  warning) on timeout or any subprocess error.

All three accept positional ``*args`` (the arguments to pass after ``git``)
and a required keyword argument ``cwd`` (the working directory). Using ``cwd``
instead of ``git -C <dir>`` keeps commands shorter and avoids the implicit
"this is a git-C call" convention in each call site.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)


def git_check(*args: str, cwd: Path) -> bool:
    """Run ``git *args`` from ``cwd`` and return ``True`` if exit code is 0.

    Never raises. Stderr is suppressed — use this for silent probes like
    ``rev-parse --verify`` or ``diff --cached --quiet``.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def git_run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``git *args`` from ``cwd``, raising on non-zero exit.

    Raises :class:`subprocess.CalledProcessError` (with ``stdout`` and
    ``stderr`` populated) if git exits non-zero. Use this for operations
    that must succeed, such as ``git add``, ``git commit``, or
    ``git worktree add``.
    """
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def git_probe(*args: str, cwd: Path, timeout: int = 10) -> bool:
    """Run ``git *args`` from ``cwd`` with a timeout; return ``True`` on exit 0.

    Returns ``False`` and logs a warning if the command times out or raises
    any other exception.  Intended for network-touching operations like
    ``git ls-remote`` where a hung remote should not block the caller.
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
        _log.warning(
            "git %s timed out after %ds — skipping",
            " ".join(args),
            timeout,
        )
        return False
    except Exception as exc:
        _log.warning(
            "git %s failed (%s) — skipping",
            " ".join(args),
            exc,
        )
        return False
    return result.returncode == 0
