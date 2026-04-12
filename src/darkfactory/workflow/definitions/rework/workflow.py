"""Rework workflow — address PR review feedback for an existing PRD.

Invoked by ``prd rework PRD-X --execute``. Unlike the default workflow
this one:

- Does NOT create a new worktree (the worktree already exists).
- Does NOT update the PRD status (it stays in ``review``).
- Does NOT open a new PR (the PR already exists; push auto-updates it).

The task sequence:

1. Resolve the rework context: worktree, open PR, guard state,
   unresolved review threads. No-op when the CLI pre-discovered.
2. Fast-forward and rebase the worktree branch so the agent works
   against current mainline code.
3. Invoke Claude Code with the review feedback in the prompt.
4. Run format / lint / typecheck / test to verify correctness.
5. Commit with the rework message.
6. Push to the existing branch so the PR auto-updates.
7. Optionally post reply notes on addressed PR comment threads.
"""

from __future__ import annotations

from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow

workflow = Workflow(
    name="rework",
    description="Address PR review feedback for an existing PRD",
    tasks=[
        # Discover the worktree, PR, guard state, and unresolved review
        # threads.  When the CLI has pre-populated these on the context
        # (the common ``prd rework --execute`` path), this is a no-op
        # and returns immediately without re-querying gh/git.
        BuiltIn("resolve_rework_context"),
        # Sync the worktree branch with origin before any mutation.
        # Fast-forwards local to match origin/<branch> so push_branch won't
        # be rejected; then rebases onto origin/main so the agent works
        # against current mainline code.  Both steps fail early (before the
        # expensive agent invocation) if the branch is diverged or conflicted.
        BuiltIn("fast_forward_branch"),
        BuiltIn("rebase_onto_main"),
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
                "Bash(git rm:*)",
                "Bash(git mv:*)",
            ],
            model_from_capability=True,
            retries=1,
            # Rework responds to review feedback — the agent needs to
            # hold the original intent AND the reviewer's objections in
            # mind simultaneously, so we request Claude Code's highest
            # adaptive-reasoning budget. Note: ``max`` is Opus 4.6 only,
            # so rework PRDs should be tagged ``capability: complex`` to
            # route to opus.
            effort_level="max",
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
