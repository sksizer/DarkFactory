"""Built-in: commit_transcript — copy agent transcript into the worktree and stage it."""

from __future__ import annotations

import logging
import shutil

from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.timestamps import now_filename_safe
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("commit_transcript")
def commit_transcript(ctx: ExecutionContext) -> None:
    """Copy agent transcript into the worktree and stage it.

    Source: ``<repo_root>/.harness-transcripts/{prd_id}.jsonl`` written by the
    runner after each agent invocation (outside any worktree — see
    ``runner._run_agent``). Destination inside the worktree:
    ``.darkfactory/transcripts/{prd_id}-{timestamp}.jsonl``.

    The runner writes transcripts *outside* every worktree so ``git add -A``
    can never accidentally sweep them. This builtin is the one place that
    opts the transcript *into* the worktree — workflows that want the
    transcript committed alongside the PRD work must include this builtin
    explicitly. Workflows that omit it leave the transcript at the repo-root
    path where it survives as a local-only diagnostic.

    Timestamps use the wall-clock at the time this builtin runs, which is
    unique enough for sequential runs. If no transcript exists (dry-run,
    or the runner didn't produce one), this is a no-op.
    """
    src = ctx.repo_root / ".harness-transcripts" / f"{ctx.prd.id}.jsonl"
    if not src.exists():
        ctx.logger.info("commit_transcript: no transcript found; skipping")
        return

    if _log_dry_run(
        ctx,
        f"copy {src} -> {ctx.cwd / '.darkfactory' / 'transcripts' / ctx.prd.id}-*.jsonl && git add",
    ):
        return

    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now_filename_safe()
    dest = transcript_dir / f"{ctx.prd.id}-{timestamp}.jsonl"

    # Copy (not move) so the repo-root transcript persists as a local-only
    # diagnostic even after this builtin runs. If the same PRD is re-run,
    # the runner overwrites the source file anyway.
    shutil.copy2(str(src), str(dest))

    match git_run("add", str(dest), cwd=ctx.cwd):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git add failed (exit {code}):\n{err}")
    ctx.logger.info("commit_transcript: staged %s", dest.relative_to(ctx.cwd))
