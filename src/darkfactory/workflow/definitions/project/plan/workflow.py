"""Plan project workflow — decompose an epic or feature PRD into child task PRDs.

Invoked via ``prd project run plan --target PRD-X --execute``.

Unlike the planning *workflow* (which is triggered automatically during DAG
execution for undecomposed PRDs), this *project workflow* is driven
explicitly from the CLI. It creates its own branch and worktree, runs an
agent to produce child PRDs, validates them, then commits, pushes, and
opens a PR.

The original planning workflow is preserved and continues to operate
unchanged for inline planning during DAG-based execution.
"""

from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow

workflow = Workflow(
    name="plan",
    description=(
        "Decompose an epic or feature PRD into implementable child task PRDs. "
        "Takes a single target PRD as input, produces N child PRDs as output."
    ),
    tasks=[
        BuiltIn("name_worktree", kwargs={"branch": "project/plan/{target_prd}"}),
        BuiltIn("ensure_worktree"),
        AgentTask(
            name="decompose",
            prompts=["prompts/decompose.md"],
            tools=["Read", "Write", "Glob", "Grep", "Bash(uv run prd validate:*)"],
            model="opus",
            model_from_capability=False,
            retries=1,
            verify_prompts=[],
            sentinel_success="PRD_EXECUTE_OK",
            sentinel_failure="PRD_EXECUTE_FAILED",
        ),
        ShellTask(
            name="validate",
            cmd="uv run prd validate",
            on_failure="retry_agent",
        ),
        BuiltIn("commit", kwargs={"message": "chore(prd): {target_prd} decomposition"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
