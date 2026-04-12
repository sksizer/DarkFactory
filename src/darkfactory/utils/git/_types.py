"""Result types for git subprocess operations.

Provides a uniform error shape for all git calls, enabling structural
pattern matching at call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Successful git operation result."""

    value: T
    stdout: str = ""


@dataclass(frozen=True)
class GitErr:
    """Non-zero git exit."""

    returncode: int
    stdout: str
    stderr: str
    cmd: list[str]


@dataclass(frozen=True)
class GitTimeout:
    """Timed-out git probe."""

    cmd: list[str]
    timeout: int


type GitResult[T] = Ok[T] | GitErr
type CheckResult = GitResult[None]
type ProbeResult = GitResult[None] | GitTimeout
