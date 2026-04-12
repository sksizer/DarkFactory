"""Type-keyed inter-task state registry.

Replaces the untyped ``_shared_state`` dict and bolted-on context fields
with a registry where the **type** of each value is its unique key.
``mypy`` infers that ``state.get(PrdContext)`` returns ``PrdContext``,
not ``Any``.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast, overload

T = TypeVar("T")

# Sentinel for distinguishing "no default" from "default is None".
_SENTINEL = object()


class PhaseState:
    """Type-keyed registry for inter-task data bundles.

    Each bundle's **type** serves as its unique key. Storing a second
    value of the same type overwrites the first — there is at most one
    instance per type at any time.

    Usage::

        state = PhaseState()
        state.put(PrdContext(summary="...", body="..."))
        ctx = state.get(PrdContext)  # mypy infers PrdContext
    """

    _store: dict[type, Any]

    def __init__(self) -> None:
        self._store = {}

    def put(self, value: object) -> None:
        """Store ``value`` keyed by its runtime type."""
        self._store[type(value)] = value

    @overload
    def get(self, key: type[T]) -> T: ...

    @overload
    def get(self, key: type[T], default: T) -> T: ...

    def get(self, key: type[T], default: Any = _SENTINEL) -> T:
        """Retrieve the value for ``key``, or raise ``KeyError``.

        With a default, returns the default instead of raising.
        """
        if key in self._store:
            return cast(T, self._store[key])
        if default is not _SENTINEL:
            return cast(T, default)
        raise KeyError(f"PhaseState has no {key.__name__!r} entry")

    def has(self, key: type) -> bool:
        """Return True if ``key`` has been stored."""
        return key in self._store
