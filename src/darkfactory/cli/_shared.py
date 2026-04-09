"""Shared helpers and constants for the CLI package."""

from __future__ import annotations

from pathlib import Path

from darkfactory.loader import load_workflows
from darkfactory.prd import PRD, load_all, parse_id_sort_key
from darkfactory.workflow import Workflow

# Priority/effort orderings used for sorting actionable lists.
PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
EFFORT_ORDER: dict[str, int] = {"xs": 0, "s": 1, "m": 2, "l": 3, "xl": 4}
CAPABILITY_ORDER: dict[str, int] = {
    "trivial": 0,
    "simple": 1,
    "moderate": 2,
    "complex": 3,
}


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until a ``.git`` directory is found.

    Used for git-specific operations (worktrees, tracked files, branches).
    Project discovery uses ``resolve_project_root`` from ``discovery`` instead.
    """
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise SystemExit(f"could not locate git repo root from {start}")


def _load_workflows_or_fail(workflows_dir: Path) -> dict[str, Workflow]:
    """Load built-in and project-level workflows.

    Built-in (system) workflows ship inside the package and are always
    available. ``workflows_dir`` is the optional project-level layer
    (``<project>/.darkfactory/workflows/``); if it doesn't exist we just
    return the built-ins.
    """
    return load_workflows(workflows_dir if workflows_dir.exists() else None)


def _action_sort_key(prd: PRD) -> tuple[int, int, tuple[int, ...]]:
    """Sort key for actionable lists: priority, effort, natural id."""
    return (
        PRIORITY_ORDER.get(prd.priority, 99),
        EFFORT_ORDER.get(prd.effort, 99),
        parse_id_sort_key(prd.id),
    )


def _load(prd_dir: Path) -> dict[str, PRD]:
    if not prd_dir.exists():
        raise SystemExit(f"PRD directory not found: {prd_dir}")
    return load_all(prd_dir)
