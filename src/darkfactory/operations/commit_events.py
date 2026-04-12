"""Built-in: commit_events — copy event log into the worktree and stage it (opt-in)."""

from __future__ import annotations

import logging
import shutil

from darkfactory.operations._registry import builtin
from darkfactory.operations._shared import _log_dry_run
from darkfactory.config import load_section
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.workflow import ExecutionContext

_log = logging.getLogger(__name__)


@builtin("commit_events")
def commit_events(ctx: ExecutionContext) -> None:
    """Copy the event log into the worktree and stage it.

    This builtin is a no-op unless event log committing is enabled in
    ``.darkfactory/config.toml``. Reads from ``[workflow.events] commit``
    first, falls back to ``[events] commit`` for backwards compatibility.

    Default is NOT to commit — event logs may contain sensitive data and
    are primarily diagnostic artifacts.
    """
    # Check config — opt-in only.
    config_path = ctx.repo_root / ".darkfactory" / "config.toml"
    if config_path.is_file():
        events_config = load_section(config_path, "events")
        if not events_config.get("commit", False):
            ctx.logger.info(
                "commit_events: disabled (workflow.events.commit != true); skipping"
            )
            return
    else:
        ctx.logger.info("commit_events: no config.toml found; skipping (default off)")
        return

    if ctx.event_writer is None:
        ctx.logger.info("commit_events: no event writer; skipping")
        return

    src = ctx.event_writer.path
    if not src.exists():
        ctx.logger.info("commit_events: no event file found; skipping")
        return

    if _log_dry_run(ctx, f"copy {src} -> worktree && git add"):
        return

    dest_dir = ctx.cwd / ".darkfactory" / "events"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.copy2(str(src), str(dest))
    match git_run("add", str(dest), cwd=ctx.cwd):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git add failed (exit {code}):\n{err}")
    ctx.logger.info("commit_events: staged %s", dest.relative_to(ctx.cwd))
