"""Built-in: check_clean_main — verify the main branch is clean before proceeding."""

from __future__ import annotations

from darkfactory.engine import CodeEnv
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import RunContext


@builtin("check_clean_main")
def check_clean_main(ctx: RunContext) -> None:
    """Verify the working tree on main is clean (no uncommitted changes).

    Placed at the start of project workflows that require a clean main
    before operating. Replaces the former ``requires_clean_main`` field
    on ``ProjectOperation``.
    """
    if _log_dry_run(ctx, "git diff --quiet HEAD"):
        return

    env = ctx.state.get(CodeEnv)
    match git_run("diff", "--quiet", "HEAD", cwd=env.repo_root):
        case Ok():
            ctx.logger.info("check_clean_main: main is clean")
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(
                f"main branch has uncommitted changes (git diff --quiet "
                f"exited {code}). Commit or stash before running this "
                f"operation.\n{err}"
            )
