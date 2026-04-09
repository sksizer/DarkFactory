"""Built-in workflow templates for DarkFactory.

This module defines the canonical templates used by PRD workflows.
Templates are importable directly::

    from darkfactory.templates_builtin import PRD_IMPLEMENTATION_TEMPLATE, REWORK_TEMPLATE
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
