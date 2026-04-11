"""Built-in: commit — stage all changes and make a commit in the worktree."""

from __future__ import annotations

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _log_dry_run, _scan_for_forbidden_attribution
from darkfactory.event_log import emit_builtin_effect
from darkfactory.utils.git import git_check, git_run
from darkfactory.workflow import ExecutionContext


@builtin("commit")
def commit(ctx: ExecutionContext, *, message: str) -> None:
    """Stage all changes and make a commit inside the worktree.

    ``message`` is format-string expanded against the context so
    ``"chore(prd): {prd_id} start work"`` becomes
    ``"chore(prd): PRD-070 start work"``. On an empty diff, logs and
    returns without erroring — workflows can safely commit after each
    logical step without worrying about whether anything changed.
    """
    formatted = ctx.format_string(message)
    _scan_for_forbidden_attribution(
        formatted, source=f"commit message for {ctx.prd.id}"
    )

    if _log_dry_run(ctx, f"git add -A && git commit -m {formatted!r}"):
        return

    # Stage everything
    git_run("add", "-A", cwd=ctx.cwd)

    # Check if there's anything to commit
    if git_check("diff", "--cached", "--quiet", cwd=ctx.cwd):
        # No staged changes — skip gracefully.
        ctx.logger.info("commit skipped: no changes to commit")
        return

    # Commit
    commit_result = git_run("commit", "-m", formatted, cwd=ctx.cwd)

    # Extract the short SHA from git commit output.
    sha = ""
    for line in commit_result.stdout.splitlines():
        if line.strip():
            # git commit output starts with "[branch sha] message"
            parts = line.strip().split()
            if len(parts) >= 2:
                sha = parts[1].rstrip("]")
            break
    emit_builtin_effect(
        ctx, "commit", "commit", detail={"sha": sha, "message": formatted}
    )
