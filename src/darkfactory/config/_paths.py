from __future__ import annotations

import os
from pathlib import Path

# Relative subdirectory names used by the harness.  Combine with a repo root or
# project root via ``repo_root / WORKTREES_SUBDIR`` etc.
WORKTREES_SUBDIR: str = ".worktrees"
DARKFACTORY_SUBDIR: str = ".darkfactory"
STATE_SUBDIR: str = ".darkfactory/state"
EVENTS_SUBDIR: str = ".darkfactory/events"
TRANSCRIPTS_SUBDIR: str = ".darkfactory/transcripts"


def user_config_dir() -> Path:
    """Return the user-level darkfactory config directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "darkfactory"


def user_config_file() -> Path | None:
    """Return path to user config.toml if it exists."""
    f = user_config_dir() / "config.toml"
    return f if f.is_file() else None


def user_workflows_dir() -> Path:
    """Return user workflows dir, creating if absent."""
    d = user_config_dir() / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_operations_dir() -> Path:
    """Return user operations dir, creating if absent."""
    d = user_config_dir() / "operations"
    d.mkdir(parents=True, exist_ok=True)
    return d
