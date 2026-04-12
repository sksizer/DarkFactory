"""Project directory discovery for darkfactory.

Locates the ``.darkfactory/`` directory for a project using a walk-up
strategy.  The resolution order is:

1. ``--directory`` CLI flag (``cli_dir`` argument)
2. ``DARKFACTORY_DIR`` environment variable
3. Walk-up from ``cwd`` looking for a ``.darkfactory/`` directory
"""

from __future__ import annotations

import os
from pathlib import Path


def find_darkfactory_dir(start: Path) -> Path | None:
    """Walk up from start looking for a .darkfactory/ directory."""
    current = start.resolve()
    while True:
        candidate = current / ".darkfactory"
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def resolve_project_root(
    cli_dir: Path | None = None,
    cwd: Path | None = None,
) -> Path | None:
    """Resolve the .darkfactory directory.

    Priority: --directory CLI flag > DARKFACTORY_DIR env > walk-up from cwd.
    """
    if cli_dir is not None:
        df = cli_dir / ".darkfactory"
        return df if df.is_dir() else None

    env_dir = os.environ.get("DARKFACTORY_DIR")
    if env_dir:
        df = Path(env_dir) / ".darkfactory"
        return df if df.is_dir() else None

    return find_darkfactory_dir(cwd or Path.cwd())
