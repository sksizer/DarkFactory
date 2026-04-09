"""Planning workflow — decompose epics and features into task PRDs.

Matches undecomposed epics and features (``kind`` is ``epic`` or
``feature``, ``status`` is ``ready``, no task-kind descendants).
Priority 5 — above default (0) so it wins for planning candidates,
below any highly-specialized workflow.

The agent is pinned to ``opus`` (decomposition is complex reasoning)
and constrained to a tool allowlist that only allows creating files
under ``.darkfactory/prds/``. Validates new children with ``prd validate`` before
the sentinel line.
"""

from __future__ import annotations

from darkfactory.containment import is_fully_decomposed
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _is_undecomposed_epic_or_feature(prd, prds):  # type: ignore[no-untyped-def]
    """True for epics/features in ready status with no task descendants.

    These are candidates for the planning workflow: they need to be
    broken down into fine-grained task PRDs before they can be
    implemented.
    """
    return (
        prd.kind in ("epic", "feature")
        and prd.status == "ready"
        and not is_fully_decomposed(prd, prds)
    )


workflow = Workflow(
    name="planning",
    description=(
        "Decompose an epic or feature PRD into fine-grained task PRDs. "
        "Pinned to opus; constrained tool allowlist that only allows "
        "creating files under .darkfactory/prds/. Validates new children with "
        "`prd validate` before sentinel."
    ),
    applies_to=_is_undecomposed_epic_or_feature,
    priority=5,
    tasks=[
        # ----- setup phase -----
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} start decomposition"},
        ),
        # ----- agent decomposition -----
        AgentTask(
            name="decompose",
            prompts=[
                "prompts/role.md",
                "prompts/decomposition-guide.md",
                "prompts/task.md",
            ],
            tools=[
                # Read existing PRDs + schema
                "Read",
                "Glob",
                "Grep",
                # Create new PRD files (and overwrite parent PRD with updated blocks)
                "Write",
                # Self-validate
                "Bash(uv run prd validate*)",
                "Bash(uv run prd:*)",
                # Stage changes (scoped to .darkfactory/prds/)
                "Bash(git add .darkfactory/prds/:*)",
                "Bash(git status:*)",
                "Bash(git diff .darkfactory/prds/:*)",
                # Inspect existing structure (read-only)
                "Bash(git log:*)",
            ],
            model="opus",
            model_from_capability=False,
            retries=1,
            verify_prompts=["prompts/verify.md"],
        ),
        # ----- validation phase -----
        ShellTask(
            "validate-children",
            cmd="uv run prd validate",
            on_failure="retry_agent",
        ),
        # ----- teardown phase -----
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} decomposed into tasks"},
        ),
        BuiltIn("lint_attribution"),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
