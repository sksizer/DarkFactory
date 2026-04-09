"""Built-in WorkflowTemplate instances bundled with the harness package.

Provides :data:`PRD_IMPLEMENTATION_TEMPLATE`, the standard PRD implementation
lifecycle with PRD-224 invariants enforced, and :data:`SYSTEM_OPERATION_TEMPLATE`,
the system operation lifecycle (lock, execute, report, unlock). Most workflows
compose from these templates rather than building open/close lists from scratch.
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
        BuiltIn("summarize_agent_run"),
        BuiltIn("commit_transcript"),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} ready for review"}),
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
