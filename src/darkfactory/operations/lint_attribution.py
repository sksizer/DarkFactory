"""Built-in: lint_attribution — reject commits that credit Claude/Anthropic."""

from __future__ import annotations

import logging

from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run, _scan_for_forbidden_attribution
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("lint_attribution")
def lint_attribution(ctx: ExecutionContext) -> None:
    """Fail if any commit on the branch or the run summary credits Claude/Anthropic.

    Scans:

    - Every commit message in ``{base_ref}..HEAD`` on the current branch
    - ``ctx.run_summary`` (which feeds the PR body)

    Intended to run after the agent + verification phases and before
    ``push_branch`` / ``create_pr``, so violations abort the workflow
    before anything lands on the remote or in a PR. Dry-run is a no-op
    because there are no real commits to scan.
    """
    if _log_dry_run(ctx, "lint_attribution: skipped"):
        return

    _scan_for_forbidden_attribution(
        ctx.run_summary or "", source=f"run summary for {ctx.prd.id}"
    )

    match git_run(
        "log",
        f"{ctx.base_ref}..HEAD",
        "--format=%H%x00%B%x1e",
        cwd=ctx.cwd,
    ):
        case Ok(stdout=output):
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git log failed (exit {code}):\n{err}")
    # Record separator \x1e between commits; field separator \x00 between
    # sha and body. Keeps us robust against newlines in commit messages.
    for entry in output.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        sha, _, body = entry.partition("\x00")
        _scan_for_forbidden_attribution(
            body, source=f"commit {sha[:12]} on {ctx.branch_name}"
        )

    ctx.logger.info("lint_attribution: clean")
