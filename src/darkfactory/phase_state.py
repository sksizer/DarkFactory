"""Type-keyed inter-task state registry.

Replaces the untyped ``_shared_state`` dict and bolted-on context fields
with a registry where the **type** of each value is its unique key.
``mypy`` infers that ``state.get(PrdContext)`` returns ``PrdContext``,
not ``Any``.

Data bundles (frozen dataclasses) are declared near their producing
builtins and stored here via :meth:`PhaseState.put`. Consumers pull
typed data via :meth:`PhaseState.get`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar, overload

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

    def get(self, key: type[T], default: Any = _SENTINEL) -> T:  # type: ignore[assignment]
        """Retrieve the value for ``key``, or raise ``KeyError``.

        With a default, returns the default instead of raising.
        """
        if key in self._store:
            return self._store[key]  # type: ignore[no-any-return]
        if default is not _SENTINEL:
            return default  # type: ignore[return-value]
        raise KeyError(f"PhaseState has no {key.__name__!r} entry")

    def has(self, key: type) -> bool:
        """Return True if ``key`` has been stored."""
        return key in self._store


# ---------- Data bundles ----------


@dataclass(frozen=True)
class PrdContext:
    """Gathered PRD context for system operations (discuss, etc.).

    Produced by :func:`~darkfactory.builtins.gather_prd_context.gather_prd_context`.
    Consumed by :func:`~darkfactory.builtins.discuss_prd.discuss_prd`.
    """

    summary: str
    body: str
    parent_ref: str | None = None
    dependency_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentResult:
    """Result of an agent invocation, stored in PhaseState after every run.

    Replaces the ``ctx.agent_output``, ``ctx.agent_success``,
    ``ctx.last_invoke_result``, ``ctx.model``, and ``ctx.invoke_count``
    fields that were bolted onto ``ExecutionContext``.
    """

    stdout: str
    stderr: str
    exit_code: int
    success: bool
    failure_reason: str | None = None
    tool_counts: dict[str, int] = field(default_factory=dict)
    sentinel: str | None = None
    model: str = "sonnet"
    invoke_count: int = 1


@dataclass(frozen=True)
class CandidateList:
    """List of candidate PRD IDs for system operations.

    Produced by :func:`~darkfactory.builtins.system_builtins.system_load_prds_by_status`.
    Consumed by :func:`~darkfactory.builtins.system_builtins.system_check_merged`.
    """

    prd_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReworkState:
    """Rework-specific inter-task state.

    Replaces the ``pr_number``, ``review_threads``, ``comment_filters``,
    and ``reply_to_comments`` fields that were bolted onto
    ``ExecutionContext``.

    Produced by :func:`~darkfactory.builtins.resolve_rework_context.resolve_rework_context`
    or pre-populated by the CLI via ``context_overrides``.
    """

    pr_number: int | None = None
    review_threads: "list[Any] | None" = None
    reply_to_comments: bool = False
    comment_filters: Any = None
