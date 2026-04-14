"""Built-in: commit — stage all changes and make a commit in the worktree."""

from __future__ import annotations

from darkfactory.engine import CodeEnv
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run, _scan_for_forbidden_attribution
from darkfactory.event_log import emit_builtin_effect
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import RunContext


@builtin("commit")
def commit(ctx: RunContext, *, message: str) -> None:
    """Stage all changes and make a commit inside the worktree.

    ``message`` is format-string expanded against the context so
    ``"chore(prd): {prd_id} start work"`` becomes
    ``"chore(prd): PRD-070 start work"``. On an empty diff, logs and
    returns without erroring — workflows can safely commit after each
    logical step without worrying about whether anything changed.
    """
    formatted = ctx.format_string(message)
    _scan_for_forbidden_attribution(formatted, source="commit message")

    if _log_dry_run(ctx, f"git add -A && git commit -m {formatted!r}"):
        return

    env = ctx.state.get(CodeEnv)

    # Stage everything
    match git_run("add", "-A", cwd=env.cwd):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git add -A failed (exit {code}):\n{err}")

    # Check if there's anything to commit
    match git_run("diff", "--cached", "--quiet", cwd=env.cwd):
        case Ok():
            # No staged changes — skip gracefully.
            ctx.logger.info("commit skipped: no changes to commit")
            return
        case GitErr():
            pass  # There are staged changes — proceed to commit.

    # Commit
    match git_run("commit", "-m", formatted, cwd=env.cwd):
        case Ok(stdout=output):
            # Extract the short SHA from git commit output.
            sha = ""
            for line in output.splitlines():
                if line.strip():
                    # git commit output starts with "[branch sha] message"
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        sha = parts[1].rstrip("]")
                    break
            emit_builtin_effect(
                ctx, "commit", "commit", detail={"sha": sha, "message": formatted}
            )
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git commit failed (exit {code}):\n{err}")
