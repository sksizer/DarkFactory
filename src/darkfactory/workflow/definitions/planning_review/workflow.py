"""Planning review workflow — review and extend partially-decomposed epics.

Matches epics and features that already have some task descendants but
have not been explicitly marked ``decomposition: complete``.  The agent
reads all existing children, maps them against the parent's requirements,
identifies gaps, and creates new child PRDs for any uncovered slices.

Priority 6 — above initial planning (5) so it wins for partial-
decomposition cases.  Initial planning still wins for zero-children
cases because its predicate is more specific.
"""

from __future__ import annotations

from darkfactory.graph import containment
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _is_review_candidate(prd, prds):  # type: ignore[no-untyped-def]
    """True for epics/features with existing children that might need more.

    Matches when the PRD has task descendants but has not been marked
    ``decomposition: complete``. Status can be ``ready`` or
    ``in-progress`` — review can apply mid-flight.
    """
    return (
        prd.kind in ("epic", "feature")
        and prd.status in ("ready", "in-progress")
        and containment.is_partially_decomposed(prd, prds)
    )


workflow = Workflow(
    name="planning-review",
    description=(
        "Review a partially-decomposed epic against its stated "
        "requirements and add new child PRDs for any uncovered slices. "
        "Pinned to opus. Same constraints as the initial planning "
        "workflow (PRD-228); writes only into .darkfactory/prds/."
    ),
    applies_to=_is_review_candidate,
    priority=6,  # higher than initial planning (5)
    tasks=[
        # ----- setup phase -----
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} start planning review"},
        ),
        # ----- agent review -----
        AgentTask(
            name="review-and-extend",
            prompts=[
                "prompts/role.md",
                "prompts/review-guide.md",
                "prompts/task.md",
            ],
            tools=[
                # Read existing PRDs
                "Read",
                "Glob",
                "Grep",
                # Create new PRD files and rewrite parent (no Edit — Write only)
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
        BuiltIn("commit_transcript"),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} planning review complete"},
        ),
        BuiltIn("lint_attribution"),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
