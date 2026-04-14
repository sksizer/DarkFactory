"""Built-in: lint_attribution — reject commits that credit Claude/Anthropic."""

from __future__ import annotations

import logging

from darkfactory.engine import PrdWorkflowRun, WorktreeState
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run, _scan_for_forbidden_attribution
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import RunContext

_log = logging.getLogger(__name__)


@builtin("lint_attribution")
def lint_attribution(ctx: RunContext) -> None:
    """Fail if any commit on the branch or the run summary credits Claude/Anthropic."""
    if _log_dry_run(ctx, "lint_attribution: skipped"):
        return

    prd_run = ctx.state.get(PrdWorkflowRun)
    wt = ctx.state.get(WorktreeState)

    _scan_for_forbidden_attribution(
        prd_run.run_summary or "", source=f"run summary for {prd_run.prd.id}"
    )

    match git_run(
        "log",
        f"{wt.base_ref}..HEAD",
        "--format=%H%x00%B%x1e",
        cwd=ctx.cwd,
    ):
        case Ok(stdout=output):
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git log failed (exit {code}):\n{err}")

    for entry in output.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        sha, _, body = entry.partition("\x00")
        _scan_for_forbidden_attribution(
            body, source=f"commit {sha[:12]} on {wt.branch}"
        )

    ctx.logger.info("lint_attribution: clean")
