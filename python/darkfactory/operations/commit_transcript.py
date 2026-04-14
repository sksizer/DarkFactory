"""Built-in: commit_transcript — copy agent transcript into the worktree and stage it."""

from __future__ import annotations

import logging
import shutil

from darkfactory.engine import PrdWorkflowRun
from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.timestamps import now_filename_safe
from darkfactory.workflow import RunContext

_log = logging.getLogger(__name__)


@builtin("commit_transcript")
def commit_transcript(ctx: RunContext) -> None:
    """Copy agent transcript into the worktree and stage it."""
    prd_run = ctx.state.get(PrdWorkflowRun)
    prd_id = prd_run.prd.id

    src = ctx.repo_root / ".harness-transcripts" / f"{prd_id}.jsonl"
    if not src.exists():
        ctx.logger.info("commit_transcript: no transcript found; skipping")
        return

    if _log_dry_run(
        ctx,
        f"copy {src} -> {ctx.cwd / '.darkfactory' / 'transcripts' / prd_id}-*.jsonl && git add",
    ):
        return

    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now_filename_safe()
    dest = transcript_dir / f"{prd_id}-{timestamp}.jsonl"

    shutil.copy2(str(src), str(dest))

    match git_run("add", str(dest), cwd=ctx.cwd):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git add failed (exit {code}):\n{err}")
    ctx.logger.info("commit_transcript: staged %s", dest.relative_to(ctx.cwd))
