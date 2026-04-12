"""Frozen dataclass bundles exchanged between tasks via PhaseState.

Each bundle is declared here rather than near its producing builtin to
avoid circular imports and to keep the ``engine`` package self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from darkfactory.utils.github.pr.comments import CommentFilters, ReviewThread


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
    or pre-populated by the CLI via ``phase_state_init``.
    """

    pr_number: int | None = None
    review_threads: list[ReviewThread] | None = None
    reply_to_comments: bool = False
    comment_filters: CommentFilters | None = None
