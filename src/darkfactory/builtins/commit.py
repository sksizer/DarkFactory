"""Built-in: commit — stage all changes and make a commit in the worktree."""

from __future__ import annotations

import subprocess

from darkfactory.builtins._registry import builtin
from darkfactory.builtins._shared import _scan_for_forbidden_attribution
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

    if ctx.dry_run:
        ctx.logger.info("[dry-run] git add -A && git commit -m %r", formatted)
        return

    # Stage everything
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )

    # Check if there's anything to commit
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(ctx.cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if diff_result.returncode == 0:
        # No staged changes — skip gracefully.
        ctx.logger.info("commit skipped: no changes to commit")
        return

    # Commit
    subprocess.run(
        ["git", "commit", "-m", formatted],
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )
