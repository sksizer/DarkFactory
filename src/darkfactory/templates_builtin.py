"""Built-in WorkflowTemplate instances bundled with the harness package.

Provides :data:`PRD_IMPLEMENTATION_TEMPLATE`, the standard PRD implementation
lifecycle with PRD-224 invariants enforced. Most workflows compose from this
template rather than building open/close lists from scratch.
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
