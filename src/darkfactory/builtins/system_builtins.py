"""System-operation builtins — bulk mutation and status helpers.

These builtins operate on :class:`~darkfactory.system.SystemContext` rather
than the per-PRD :class:`~darkfactory.workflow.ExecutionContext` used by
workflow builtins.  They are registered in :data:`SYSTEM_BUILTINS`, a
parallel registry that the system runner dispatches against.
"""

from __future__ import annotations

import subprocess
from typing import Callable

from darkfactory import prd as prd_module
from darkfactory.system import SystemContext

SYSTEM_BUILTINS: dict[str, Callable[..., None]] = {}
"""Global registry mapping system builtin name to its implementing function.

Populated at import time via the :func:`_register` decorator.  The system
runner looks up names here when dispatching a :class:`~darkfactory.workflow.BuiltIn`
task inside a :class:`~darkfactory.system.SystemOperation`.
"""


def _register(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        if name in SYSTEM_BUILTINS:
            raise ValueError(f"duplicate system builtin registration for {name!r}")
        SYSTEM_BUILTINS[name] = fn
        return fn

    return decorator


@_register("set_status_bulk")
def set_status_bulk(ctx: SystemContext, *, status: str) -> None:
    """Update the status field of every PRD id in ``ctx.targets``.

    Respects ``ctx.dry_run`` — in dry-run mode the function logs what would
    change without writing to disk.  Idempotent: PRDs whose status is already
    ``status`` are skipped silently.
    """
    for prd_id in ctx.targets:
        prd = ctx.prds.get(prd_id)
        if prd is None:
            ctx.logger.warning(
                "set_status_bulk: %s not found in loaded PRDs, skipping", prd_id
            )
            continue

        if prd.status == status:
            ctx.logger.debug(
                "set_status_bulk: %s already has status %r, skipping", prd_id, status
            )
            continue

        if ctx.dry_run:
            ctx.logger.info(
                "[dry-run] set status of %s: %s -> %s (path=%s)",
                prd_id,
                prd.status,
                status,
                prd.path,
            )
            continue

        prd_module.set_status(prd, status)
        ctx.logger.info("set_status_bulk: %s -> %s", prd_id, status)


@_register("system_load_review_prds")
def system_load_review_prds(ctx: SystemContext) -> None:
    """Convenience wrapper: load PRDs with status ``"review"`` into candidates."""
    system_load_prds_by_status(ctx, status="review")


@_register("system_load_prds_by_status")
def system_load_prds_by_status(ctx: SystemContext, *, status: str) -> None:
    """Filter ``ctx.prds`` by ``status`` and store matching ids in shared state.

    The result is stored at ``ctx._shared_state['candidates']`` as a list of
    PRD id strings.  Downstream tasks (e.g. :func:`system_check_merged`) read
    this key to know which PRDs to examine.
    """
    candidates = [prd_id for prd_id, prd in ctx.prds.items() if prd.status == status]
    ctx._shared_state["candidates"] = candidates
    ctx.logger.info(
        "system_load_prds_by_status: found %d PRD(s) with status=%r",
        len(candidates),
        status,
    )


def _branch_name(prd: prd_module.PRD) -> str:
    """Return the expected branch name for a PRD: ``prd/{id}-{slug}``."""
    return f"prd/{prd.id}-{prd.slug}"


def _is_merged_standard(repo_root: str, branch: str) -> bool:
    """Return True if ``branch`` (local or remote) is listed in ``git branch --merged main``."""
    # Check local branch merged into main
    result = subprocess.run(
        ["git", "branch", "--merged", "main", "--list", branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return True
    # Check remote branch
    result = subprocess.run(
        ["git", "branch", "-r", "--merged", "main", "--list", f"origin/{branch}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _is_merged_squash(repo_root: str, branch: str) -> bool:
    """Return True if any commit on main references ``branch`` in its message.

    GitHub's squash-and-merge includes the branch name in the commit message
    (e.g. ``"Fix stuff (#42)"`` with the branch name in the PR body / title).
    A more reliable signal is the ``prd/PRD-X-slug`` pattern that GitHub
    appends to squash-merge commit messages when auto-generated.
    """
    result = subprocess.run(
        ["git", "log", "main", "--oneline", f"--grep={branch}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


@_register("system_check_merged")
def system_check_merged(ctx: SystemContext) -> None:
    """Check which candidate PRDs have had their branch merged to main.

    Reads ``ctx._shared_state['candidates']`` (populated by
    :func:`system_load_prds_by_status`).  For each candidate, checks:

    1. Standard merge commit — branch appears in ``git branch --merged main``.
    2. Squash-and-merge — branch name appears in ``git log main``.

    Populates ``ctx.targets`` with the ids of confirmed-merged PRDs and
    appends human-readable lines to ``ctx.report``.
    """
    candidates: list[str] = ctx._shared_state.get("candidates", [])
    repo_root = str(ctx.repo_root)
    confirmed: list[str] = []

    for prd_id in candidates:
        prd = ctx.prds.get(prd_id)
        if prd is None:
            ctx.report.append(f"{prd_id}: not found in loaded PRDs — skipped")
            continue

        branch = _branch_name(prd)

        if ctx.dry_run:
            ctx.logger.info(
                "[dry-run] would check merged status for %s (branch=%s)", prd_id, branch
            )
            ctx.report.append(f"{prd_id}: [dry-run] would check branch {branch}")
            continue

        if _is_merged_standard(repo_root, branch):
            confirmed.append(prd_id)
            ctx.report.append(f"{prd_id}: merged (standard merge, branch={branch})")
        elif _is_merged_squash(repo_root, branch):
            confirmed.append(prd_id)
            ctx.report.append(f"{prd_id}: merged (squash-and-merge, branch={branch})")
        else:
            ctx.report.append(f"{prd_id}: not merged (branch={branch})")

    ctx.targets = confirmed


@_register("system_mark_done")
def system_mark_done(ctx: SystemContext) -> None:
    """Set status to ``"done"`` for all PRDs in ``ctx.targets``."""
    set_status_bulk(ctx, status="done")


@_register("audit_impacts_check")
def audit_impacts_check(ctx: SystemContext) -> None:
    """Walk all PRDs and verify that every declared impact path exists on disk.

    For each PRD in ``ctx.prds``, iterates ``prd.impacts`` and checks whether
    the path exists relative to ``ctx.repo_root``.  Appends human-readable
    lines to ``ctx.report`` and raises ``ValueError`` if any paths are
    missing (causing the runner to return a non-zero exit status, useful for
    CI).

    This builtin is intentionally read-only — it never modifies PRD files.
    The ``ctx.dry_run`` flag is ignored because no mutations are performed.
    """
    total_checked = 0
    missing: dict[str, list[str]] = {}

    for prd_id, prd in sorted(ctx.prds.items()):
        if not prd.impacts:
            continue
        for path in prd.impacts:
            total_checked += 1
            full_path = ctx.repo_root / path
            if not full_path.exists():
                missing.setdefault(prd_id, []).append(path)
            else:
                ctx.logger.debug("audit_impacts_check: %s OK  %s", prd_id, path)

    total_missing = sum(len(v) for v in missing.values())
    ctx.report.append(
        f"audit-impacts: {total_checked} path(s) checked, {total_missing} missing"
    )

    if missing:
        ctx.report.append("Missing impact paths by PRD:")
        for prd_id, paths in sorted(missing.items()):
            for path in paths:
                ctx.report.append(f"  {prd_id}: {path}")
        raise ValueError(
            f"{total_missing} declared impact path(s) do not exist on disk"
        )
