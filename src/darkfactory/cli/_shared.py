"""Shared helpers and constants for the CLI package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from darkfactory import containment, graph
from darkfactory.git_ops import git_check, git_run
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
    """Load workflows from all layers via the cascade registry.

    Built-in (system) workflows ship inside the package and are always
    available. ``workflows_dir`` is the project-level layer
    (``<project>/.darkfactory/workflows/``); its parent is the
    ``.darkfactory/`` directory used as ``project_dir``.

    A :class:`~darkfactory.registry.WorkflowNameCollision` or
    :class:`~darkfactory.registry.InvalidWorkflow` error is fatal — the
    message is printed to stderr and the process exits with code 1.
    """
    from darkfactory.registry import (
        InvalidWorkflow,
        WorkflowNameCollision,
        build_workflow_registry,
    )

    darkfactory_dir = workflows_dir.parent
    try:
        return build_workflow_registry(darkfactory_dir)
    except WorkflowNameCollision as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except InvalidWorkflow as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


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


def _resolve_base_ref(explicit: str | None, repo_root: Path) -> str:
    """Determine the git base ref for a new workflow branch.

    Resolution order:

    1. ``explicit`` from ``--base`` (highest priority)
    2. ``DARKFACTORY_BASE_REF`` environment variable
    3. ``main`` if it exists locally
    4. ``master`` if it exists locally
    5. The remote's default branch via ``origin/HEAD``
    6. Last resort: ``main`` (callers will hit a real error later if it's
       missing too)

    The user's current branch is **not** consulted. PRDs are independent
    units of work and should base on the project's default branch unless
    the user says otherwise. Stacking onto a feature branch is the
    exception, not the rule, and requires an explicit ``--base`` flag.
    """
    if explicit:
        return explicit

    env_override = os.environ.get("DARKFACTORY_BASE_REF")
    if env_override:
        return env_override

    for candidate in ("main", "master"):
        if git_check(
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{candidate}",
            cwd=repo_root,
        ):
            return candidate

    # Try remote's default branch (e.g. for fresh clones with no local main)
    try:
        result = git_run(
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            cwd=repo_root,
        )
        # Output looks like "refs/remotes/origin/main"
        return result.stdout.strip().rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        pass

    return "main"


def _resolve_prd_or_exit(prd_id: str, prds: dict[str, PRD]) -> PRD:
    """Look up *prd_id* in *prds*, raising ``SystemExit`` if not found.

    Consolidates the 8 ``if args.prd_id not in prds: raise SystemExit(...)``
    sites across CLI commands so the error message is consistent and the
    literal string ``"unknown PRD id:"`` appears only here.
    """
    if prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {prd_id}")
    return prds[prd_id]


def _emit_json(payload: object) -> int:
    """Print *payload* as indented JSON and return 0.

    Collapses the repeated ``if args.json: print(json.dumps(payload, indent=2)); return 0``
    pattern across CLI commands.
    """
    print(json.dumps(payload, indent=2))
    return 0


_PRD_FIELDS_DEFAULT: tuple[str, ...] = (
    "id",
    "title",
    "priority",
    "effort",
    "capability",
    "kind",
    "status",
)


def _prd_to_dict(
    prd: PRD,
    fields: tuple[str, ...] = _PRD_FIELDS_DEFAULT,
) -> dict[str, object]:
    """Serialize *prd* to a dict with the requested fields.

    Replaces near-identical PRD-to-dict payloads scattered across ``next_cmd.py``,
    ``status.py``, and ``assign_cmd.py``.
    """
    return {f: getattr(prd, f) for f in fields}


def _format_prd_line(prd: PRD, fields: tuple[str, ...]) -> str:
    """Format a single-line PRD summary: ``{id:14} [{f1/f2/...}]  {title}``.

    Collapses the 5 sites that print this pattern with subtly different
    attribute selections (children.py, orphans.py, undecomposed.py,
    next_cmd.py, status.py).
    """
    attrs = "/".join(getattr(prd, f) for f in fields)
    return f"{prd.id:14} [{attrs}]  {prd.title}"


def _check_runnable(prd: PRD, prds: dict[str, PRD]) -> str | None:
    """Return an error string if the PRD can't be run, else None."""
    if prd.status == "done":
        return f"{prd.id} is already done"
    if prd.status == "cancelled":
        return f"{prd.id} is cancelled"
    if not graph.is_actionable(prd, prds):
        missing = graph.missing_deps(prd, prds)
        if missing:
            return f"{prd.id} depends on missing PRDs: {', '.join(missing)}"
        unfinished = [
            dep_id
            for dep_id in prd.depends_on
            if dep_id in prds and prds[dep_id].status != "done"
        ]
        if unfinished:
            return f"{prd.id} has unfinished dependencies: " + ", ".join(
                f"{d} ({prds[d].status})" for d in unfinished
            )
        return f"{prd.id} status is {prd.status!r}, not 'ready'"
    if not containment.is_runnable(prd, prds):
        return (
            f"{prd.id} is an epic/feature with children; "
            "use the planning workflow or run its task descendants instead"
        )
    return None
