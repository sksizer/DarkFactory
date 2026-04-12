"""Result types for GitHub CLI (gh) subprocess operations."""

from __future__ import annotations

from dataclasses import dataclass

from darkfactory.utils._result import Ok, Timeout

# Re-export for convenience.
Ok = Ok
Timeout = Timeout


@dataclass(frozen=True)
class GhErr:
    """Non-zero gh exit."""

    returncode: int
    stdout: str
    stderr: str
    cmd: list[str]


type GhResult[T] = Ok[T] | GhErr
type GhCheckResult = Ok[None] | GhErr | Timeout
