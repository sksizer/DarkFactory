"""Task workflow — implementation recipe for task-kind PRDs.

Matches PRDs with ``kind == "task"`` and ``status == "ready"``.
Priority 3 — above default (0) so it wins for task PRDs, below
planning (5).

Compared to the default workflow, the task workflow grants wider
tool permissions appropriate for implementation work: ``git rm``
for file deletions, broader build tool access, etc. The prompt
set is the same as default for now but can be tailored.
"""

from __future__ import annotations

from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _is_ready_task(prd, prds):  # type: ignore[no-untyped-def]
    """True for task PRDs in ready status.

    These are the leaf-level implementation units that need to be
    coded, tested, and shipped.
    """
    return prd.kind == "task" and prd.status == "ready"


workflow = Workflow(
    name="task",
    description=(
        "Implementation workflow for task-kind PRDs. Wider tool "
        "permissions than default — includes git rm, broader shell access."
    ),
    applies_to=_is_ready_task,
    priority=3,
    tasks=[
        # ----- setup phase -----
        BuiltIn("ensure_worktree"),
        BuiltIn("fast_forward_branch"),
        BuiltIn("rebase_onto_main"),
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
                "Bash(uv:*)",
                # Git: the agent stages, inspects, and commits incremental work.
                # Branch creation, pushing, and PR creation are still owned by
                # the harness builtins.
                "Bash(git add:*)",
                "Bash(git rm:*)",
                "Bash(git commit:*)",
                "Bash(git status:*)",
                "Bash(git diff:*)",
                "Bash(git log:*)",
                "Bash(python -m)",
            ],
            model_from_capability=True,
            retries=1,
            verify_prompts=["prompts/verify.md"],
        ),
        # ----- verification phase -----
        ShellTask("test", cmd="just test", on_failure="retry_agent"),
        ShellTask("format", cmd="just format", on_failure="fail"),
        ShellTask("lint", cmd="just lint format-check", on_failure="retry_agent"),
        ShellTask("typecheck", cmd="just typecheck", on_failure="retry_agent"),
        # ----- teardown phase -----
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit_transcript"),
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} ready for review"},
        ),
        BuiltIn("summarize_agent_run"),
        BuiltIn("lint_attribution"),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
