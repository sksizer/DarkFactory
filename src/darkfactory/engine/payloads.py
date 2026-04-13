"""Frozen dataclass bundles exchanged between tasks via PhaseState.

Each bundle is declared here rather than near its producing builtin to
avoid circular imports and to keep the ``engine`` package self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from darkfactory.model import PRD
    from darkfactory.utils.github.pr.comments import CommentFilters, ReviewThread
    from darkfactory.workflow._core import Workflow


# ---------- execution environment ----------


@dataclass(frozen=True)
class CodeEnv:
    """Execution environment — where code runs.

    Seeded by the runner at construction with ``cwd=repo_root``.
    Replaced by ``ensure_worktree`` with ``cwd=worktree_path``.

    Tasks that execute commands read ``ctx.state.get(CodeEnv).cwd``.
    """

    repo_root: Path
    cwd: Path


# ---------- run-mode payloads ----------


@dataclass(frozen=True)
class PrdWorkflowRun:
    """Identifies a PRD workflow run.

    Put by ``run_prd_workflow()`` at construction.
    """

    prd: "PRD"
    workflow: "Workflow"
    run_summary: str | None = None


@dataclass(frozen=True)
class ProjectRun:
    """Identifies a project workflow run.

    Put by ``run_project_workflow()`` at construction.
    ``prds`` is the full PRD lookup dict (read-only reference).
    ``targets`` is replaced by downstream tasks (e.g. system_check_merged).
    """

    workflow: "Workflow"
    prds: dict[str, "PRD"] = field(default_factory=dict)
    targets: tuple[str, ...] = ()
    target_prd: str | None = None


# ---------- git / worktree state ----------


@dataclass(frozen=True)
class WorktreeState:
    """Git worktree contract shared between ensure_worktree and downstream ops.

    Put by ``name_worktree`` (branch + base_ref only).
    Replaced by ``ensure_worktree`` (adds worktree_path).
    Read by ``commit``, ``push_branch``, ``create_pr``.
    """

    branch: str
    base_ref: str = "main"
    worktree_path: Path | None = None


@dataclass(frozen=True)
class PrRequest:
    """PR metadata for create_pr.

    Put by tasks that want to control PR title/body.
    Read by ``create_pr`` as an alternative to PRD-derived defaults.
    """

    title: str
    body: str


@dataclass(frozen=True)
class PrResult:
    """Result of PR creation.

    Put by ``create_pr`` on success.
    Read by the runner to populate ``RunResult.pr_url``.
    """

    url: str | None = None


# ---------- original payloads ----------


@dataclass(frozen=True)
class PrdContext:
    """Gathered PRD context for system operations (discuss, etc.).

    Produced by :func:`~darkfactory.operations.gather_prd_context.gather_prd_context`.
    Consumed by :func:`~darkfactory.operations.discuss_prd.discuss_prd`.
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

    Produced by :func:`~darkfactory.operations.system_builtins.system_load_prds_by_status`.
    Consumed by :func:`~darkfactory.operations.system_builtins.system_check_merged`.
    """

    prd_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReworkState:
    """Rework-specific inter-task state.

    Replaces the ``pr_number``, ``review_threads``, ``comment_filters``,
    and ``reply_to_comments`` fields that were bolted onto
    ``ExecutionContext``.

    Produced by :func:`~darkfactory.operations.resolve_rework_context.resolve_rework_context`
    or pre-populated by the CLI via ``phase_state_init``.
    """

    pr_number: int | None = None
    review_threads: list[ReviewThread] | None = None
    reply_to_comments: bool = False
    comment_filters: CommentFilters | None = None
