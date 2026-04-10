"""Rework workflow — address PR review feedback for an existing PRD.

Invoked by ``prd rework PRD-X --execute``. Unlike the default workflow
this one:

- Does NOT create a new worktree (the worktree already exists).
- Does NOT update the PRD status (it stays in ``review``).
- Does NOT open a new PR (the PR already exists; push auto-updates it).

The task sequence:

1. Fetch unresolved PR review threads (no-op if pre-fetched by the CLI).
2. Invoke Claude Code with the review feedback in the prompt.
3. Run format / lint / typecheck / test to verify correctness.
4. Commit with the rework message.
5. Push to the existing branch so the PR auto-updates.
"""

from __future__ import annotations

from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow

workflow = Workflow(
    name="rework",
    description="Address PR review feedback for an existing PRD",
    tasks=[
        # Fetch unresolved review threads and store on ctx.review_threads.
        # When cmd_rework --execute pre-fetches them, this is a no-op.
        BuiltIn("fetch_pr_comments"),
        # Invoke the agent with the review feedback.
        AgentTask(
            name="agent",
            prompts=["prompts/role.md", "prompts/task.md"],
            tools=[
                "Read",
                "Edit",
                "Write",
                "Glob",
                "Grep",
                "Bash(cargo:*)",
                "Bash(pnpm:*)",
                "Bash(just:*)",
                "Bash(uv:*)",
                "Bash(git add:*)",
                "Bash(git status:*)",
                "Bash(git diff:*)",
                "Bash(git log:*)",
            ],
            model_from_capability=True,
            retries=1,
        ),
        # Verification steps — run after the agent finishes.
        ShellTask("format", cmd="uv run ruff format .", on_failure="fail"),
        ShellTask("lint", cmd="uv run ruff check --fix .", on_failure="fail"),
        # typecheck is advisory — failures are logged but don't block the commit.
        ShellTask("typecheck", cmd="uv run pyright", on_failure="ignore"),
        ShellTask("test", cmd="uv run pytest", on_failure="fail"),
        # Detect no-change loops before committing — warn or block.
        BuiltIn("check_rework_guard"),
        # Commit the agent's changes with the rework message.
        BuiltIn(
            "commit",
            kwargs={"message": "chore(prd): {prd_id} address review feedback"},
        ),
        # Push to the existing branch — the open PR auto-updates.
        BuiltIn("push_branch"),
        # Optionally post bot replies to addressed PR comment threads.
        # Only runs when --reply-to-comments is passed. Failures are
        # logged as warnings and do not fail the rework run.
        BuiltIn("reply_pr_comments"),
    ],
)
