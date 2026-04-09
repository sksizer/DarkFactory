from __future__ import annotations

import os
from pathlib import Path


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
