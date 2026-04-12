"""Result types for git subprocess operations.

Provides a uniform error shape for all git calls, enabling structural
pattern matching at call sites.
"""

from __future__ import annotations

from dataclasses import dataclass

from darkfactory.utils._result import Ok, Timeout

# Re-export so existing callers can still import from here.
Ok = Ok
Timeout = Timeout


@dataclass(frozen=True)
class GitErr:
    """Non-zero git exit."""

    returncode: int
    stdout: str
    stderr: str
    cmd: list[str]


type GitResult[T] = Ok[T] | GitErr
type CheckResult = Ok[None] | GitErr | Timeout
