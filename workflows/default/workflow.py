"""Default workflow — the catchall implementation recipe for any PRD.

Matches every PRD (``applies_to`` returns True, ``priority=0``), so
the assignment logic uses this workflow whenever no other workflow's
predicate fires and the PRD's frontmatter doesn't pin something
specific.

The task list is the canonical SDLC shape every implementation workflow
follows:

1. Create the worktree
2. Mark PRD in-progress + commit the status change
3. Invoke Claude Code to write the actual implementation
4. Run the project's test + lint commands (with retry-agent on failure)
5. Mark PRD review + commit the status change
6. Push the branch and open a PR

Specialized workflows (``ui-component``, ``planning``, etc.) will ship
as siblings of this directory with different prompts, task lists, and
predicates — but they all share this overall shape. Shared SDLC,
pluggable implementation.
"""

from __future__ import annotations

from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _applies_to_everything(prd, prds):  # type: ignore[no-untyped-def]
    """Catchall predicate — the default workflow matches every PRD.

    Kept as a module-level named function (not a lambda) so ``list-workflows``
    can describe it and mypy's strict mode doesn't complain about lambda
    type annotations.
    """
    return True


workflow = Workflow(
    name="default",
    description=(
        "General-purpose PRD implementation — the fallback workflow for "
        "any PRD that doesn't match a more specific predicate."
    ),
    applies_to=_applies_to_everything,
    priority=0,  # catchall: lowest priority
    tasks=[
        # ----- setup phase -----
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} start work"},
        ),
        # ----- agent implementation -----
        AgentTask(
            name="implement",
            prompts=["prompts/role.md", "prompts/task.md"],
            tools=[
                # Read/write code and search
                "Read",
                "Edit",
                "Write",
                "Glob",
                "Grep",
                # Build/test commands
                "Bash(cargo:*)",
                "Bash(pnpm:*)",
                "Bash(just:*)",
                # Git: the agent only stages and inspects. Commit, push, and
                # PR creation are owned by the harness builtins — see role.md.
                # Deliberately no Bash(git commit:*) so the agent can't bypass
                # the harness's commit step.
                "Bash(git add:*)",
                "Bash(git status:*)",
                "Bash(git diff:*)",
                "Bash(git log:*)",
            ],
            model_from_capability=True,
            retries=1,
            verify_prompts=["prompts/verify.md"],
        ),
        # ----- verification phase -----
        # test/lint failures trigger one retry_agent cycle each: the
        # runner composes the verify prompt with the failed output bound
        # to {{CHECK_OUTPUT}}, re-invokes the agent once, and re-runs
        # the failing check.
        ShellTask("test", cmd="just test", on_failure="retry_agent"),
        ShellTask("lint", cmd="just lint format-check", on_failure="retry_agent"),
        # ----- teardown phase -----
        # set_status BEFORE the final commit so the review-status change
        # lands in the commit that gets pushed. Doing set_status after
        # commit leaves the status mutation uncommitted and the pushed
        # branch (and merged PR) shows status: in-progress instead of
        # review.
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} ready for review"},
        ),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
