"""Shared Result types for subprocess operations.

Provides generic success and timeout wrappers used by both
``utils/git/`` and ``utils/github/`` modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Successful subprocess operation result."""

    value: T
    stdout: str = ""


@dataclass(frozen=True)
class Timeout:
    """Timed-out subprocess operation."""

    cmd: list[str]
    timeout: int
