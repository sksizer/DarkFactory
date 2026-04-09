from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

DetectorFunc = Callable[[list[dict[str, object]]], list["Finding"]]
"""Signature every detector shares: takes a list of transcript event dicts, returns findings."""

DETECTORS: dict[str, DetectorFunc] = {}
"""Global registry mapping detector name to its implementing function.

Populated via the :func:`detector` decorator. Starts empty at import time;
detectors register themselves when their module is imported.
"""


@dataclass(frozen=True)
class Finding:
    """A single issue or observation produced by a detector."""

    category: str
    severity: Literal["info", "warning", "error"]
    message: str
    line: int | None = None


def detector(name: str) -> Callable[[DetectorFunc], DetectorFunc]:
    """Decorator that registers a function in :data:`DETECTORS`.

    Rejects duplicate registrations with ``ValueError`` to catch typos
    and accidental overrides during development.
    """

    def wrapper(func: DetectorFunc) -> DetectorFunc:
        if name in DETECTORS:
            raise ValueError(f"Duplicate detector: {name!r}")
        DETECTORS[name] = func
        return func

    return wrapper
