"""Extraction workflow — for PRDs that operate on a separate target repo.

Used by the darkfactory extraction (PRD-500..505): the work happens in
a *different* repo on disk, so the pumice ``just test`` / ``just lint``
shell steps from the default workflow don't apply. The agent is
responsible for whatever verification matters in the target repo.

Predicate matches any PRD tagged ``extraction``. Priority 5 — above
default (0), below specialized workflows like ui-component (10).
"""

from __future__ import annotations

from darkfactory.workflow import AgentTask, BuiltIn, Workflow


def _is_extraction(prd, prds):  # type: ignore[no-untyped-def]
    return "extraction" in prd.tags


workflow = Workflow(
    name="extraction",
    description=(
        "Repo-extraction workflow — for PRDs whose work happens in a "
        "separate target repository (no pumice test/lint phase)."
    ),
    applies_to=_is_extraction,
    priority=5,
    tasks=[
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} start work"},
        ),
        AgentTask(
            name="implement",
            prompts=["prompts/role.md", "prompts/task.md"],
            tools=[
                "Read",
                "Edit",
                "Write",
                "Glob",
                "Grep",
                # Broad bash for filesystem + git + gh against the target repo
                "Bash",
            ],
            model_from_capability=True,
            retries=1,
            verify_prompts=["prompts/verify.md"],
        ),
        # No test/lint ShellTasks — the agent verifies in the target repo.
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} ready for review"},
        ),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
