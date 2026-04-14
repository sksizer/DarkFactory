"""GitHub CLI (gh) subprocess primitives — single gateway for all gh calls.

Two thin wrappers over ``subprocess.run(["gh", ...])``:

- :func:`gh_run` — runs gh, never raises; returns ``Ok(None, stdout=...)``
  on exit 0, ``GhErr`` on non-zero exit, ``Timeout`` on timeout.
- :func:`gh_json` — same as ``gh_run`` but parses stdout as JSON on success.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from darkfactory.utils._result import Ok, Timeout
from darkfactory.utils.github._types import GhCheckResult, GhErr, GhResult


def gh_run(*args: str, cwd: Path, timeout: int | None = None) -> GhCheckResult:
    """Run ``gh *args`` from ``cwd``; never raises.

    Returns ``Ok(None, stdout=...)`` on exit 0, ``GhErr`` on non-zero,
    ``Timeout`` on timeout.
    """
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Timeout(["gh", *args], timeout or 0)
    except Exception as exc:
        return GhErr(-1, "", str(exc), ["gh", *args])
    if result.returncode != 0:
        return GhErr(result.returncode, result.stdout, result.stderr, ["gh", *args])
    return Ok(None, stdout=result.stdout)


def gh_json(
    *args: str, cwd: Path, timeout: int | None = None
) -> GhResult[Any] | Timeout:
    """Run ``gh *args`` from ``cwd``, parse stdout as JSON on success.

    Returns ``Ok(parsed, stdout=raw)`` on exit 0 with valid JSON,
    ``GhErr`` on non-zero exit, ``Timeout`` on timeout.
    """
    match gh_run(*args, cwd=cwd, timeout=timeout):
        case Ok(stdout=raw):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return GhErr(-1, raw, "invalid JSON in stdout", ["gh", *args])
            return Ok(parsed, stdout=raw)
        case GhErr() as err:
            return err
        case Timeout() as t:
            return t
