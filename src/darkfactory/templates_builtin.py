"""Built-in workflow templates for DarkFactory.

Provides :data:`PRD_IMPLEMENTATION_TEMPLATE`, the standard PRD implementation
lifecycle with PRD-224 invariants enforced. Most workflows compose from this
template rather than building open/close lists from scratch.

Also provides :data:`EXTRACTION_TEMPLATE` for workflows that operate on a
separate target repository (no pumice test/lint shell steps). It differs from
:data:`PRD_IMPLEMENTATION_TEMPLATE` in two ways:

1. **Middle**: only :class:`AgentTask` is allowed -- no :class:`ShellTask` is
   required because the agent verifies in the target repo directly.
2. **Close**: omits ``summarize_agent_run`` and ``commit_transcript`` (no
   pumice transcript to record), adds ``lint_attribution`` before pushing,
   and commits the review message before updating the status (matching the
   pre-existing extraction convention).
"""

from __future__ import annotations

from .templates import WorkflowTemplate
from .workflow import AgentTask, BuiltIn, ShellTask

PRD_IMPLEMENTATION_TEMPLATE = WorkflowTemplate(
    name="prd-implementation",
    description="Standard PRD implementation lifecycle with enforced invariants.",
    open=[
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"}),
    ],
    middle_kinds=[AgentTask, ShellTask],
    middle_required={
        AgentTask: (1, None),
        ShellTask: (1, None),
    },
    close=[
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit_events"),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} ready for review"}),
        BuiltIn("summarize_agent_run"),
        BuiltIn("lint_attribution"),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)

# Extraction workflows run against a separate target repository, so there are
# no pumice shell steps and no pumice transcript to summarize. The close
# sequence commits first (capturing the agent's work in the worktree), then
# marks the status, then runs lint_attribution before pushing.
EXTRACTION_TEMPLATE = WorkflowTemplate(
    name="extraction",
    description=(
        "Extraction workflow lifecycle for PRDs whose implementation targets "
        "a separate repository. No ShellTask required; no transcript capture."
    ),
    open=[
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"}),
    ],
    # Only AgentTask is allowed in the middle — no ShellTask, because the agent
    # runs verification directly in the target repo rather than via pumice.
    middle_kinds=[AgentTask],
    middle_required={
        AgentTask: (1, None),
    },
    close=[
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} ready for review"}),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("lint_attribution"),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)

SYSTEM_OPERATION_TEMPLATE = WorkflowTemplate(
    name="system-operation",
    description="System operation lifecycle: lock, execute, report, unlock.",
    open=[
        BuiltIn("acquire_global_lock"),
        BuiltIn("log_operation_start"),
    ],
    middle_kinds=[AgentTask, ShellTask],
    middle_required={},
    close=[
        BuiltIn("write_report"),
        BuiltIn("log_operation_end"),
        BuiltIn("release_global_lock"),
    ],
)

REWORK_TEMPLATE = WorkflowTemplate(
    name="rework",
    description="Rework lifecycle: resume existing PR, address feedback, push updates.",
    open=[
        BuiltIn("check_pr_exists"),
        BuiltIn("resume_worktree"),
        BuiltIn("fetch_review_comments"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
    ],
    middle_kinds=[AgentTask, ShellTask],
    middle_required={
        AgentTask: (1, None),
    },
    close=[
        BuiltIn("summarize_agent_run"),
        BuiltIn("commit_transcript"),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn(
            "commit", kwargs={"message": "chore(prd): {prd_id} address review feedback"}
        ),
        BuiltIn("push_branch"),
    ],
)
