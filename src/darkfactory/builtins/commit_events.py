"""Built-in: commit_events — copy event log into the worktree and stage it (opt-in)."""

from __future__ import annotations

import logging
import shutil
import subprocess

from darkfactory.builtins._registry import builtin
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
        import tomllib

        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        # Prefer [workflow.events], fall back to [events]
        workflow_cfg = config.get("workflow", {})
        events_config = workflow_cfg.get("events", config.get("events", {}))
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

    if ctx.dry_run:
        ctx.logger.info("[dry-run] copy %s -> worktree && git add", src)
        return

    dest_dir = ctx.cwd / ".darkfactory" / "events"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.copy2(str(src), str(dest))
    subprocess.run(["git", "add", str(dest)], cwd=str(ctx.cwd), check=True)
    ctx.logger.info("commit_events: staged %s", dest.relative_to(ctx.cwd))
