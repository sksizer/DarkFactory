"""System-operation builtins — bulk mutation and status helpers.

These builtins operate on :class:`~darkfactory.system.SystemContext` rather
than the per-PRD :class:`~darkfactory.workflow.ExecutionContext` used by
workflow builtins.  They are registered in :data:`SYSTEM_BUILTINS`, a
parallel registry that the system runner dispatches against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from darkfactory import containment, model as model_module
from darkfactory.utils.git import GitErr, Ok, git_run
from darkfactory.model import compute_branch_name
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

        model_module.set_status(prd, status)
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


_branch_name = compute_branch_name


def _is_merged_standard(repo_root: str, branch: str) -> bool:
    """Return True if ``branch`` (local or remote) is listed in ``git branch --merged main``."""
    cwd = Path(repo_root)
    # Check local branch merged into main
    match git_run("branch", "--merged", "main", "--list", branch, cwd=cwd):
        case Ok(stdout=output) if output.strip():
            return True
        case _:
            pass
    # Check remote branch
    match git_run(
        "branch", "-r", "--merged", "main", "--list", f"origin/{branch}", cwd=cwd
    ):
        case Ok(stdout=output):
            return bool(output.strip())
        case GitErr():
            return False


def _is_merged_squash(repo_root: str, branch: str) -> bool:
    """Return True if any commit on main references ``branch`` in its message.

    GitHub's squash-and-merge includes the branch name in the commit message
    (e.g. ``"Fix stuff (#42)"`` with the branch name in the PR body / title).
    A more reliable signal is the ``prd/PRD-X-slug`` pattern that GitHub
    appends to squash-merge commit messages when auto-generated.
    """
    match git_run("log", "main", "--oneline", f"--grep={branch}", cwd=Path(repo_root)):
        case Ok(stdout=output):
            return bool(output.strip())
        case GitErr():
            return False


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


_COMPLETED_STATUSES = {"done", "review"}


@_register("audit_impacts_check")
def audit_impacts_check(ctx: SystemContext) -> None:
    """Walk all PRDs and verify that declared impact paths exist on disk.

    Severity depends on PRD status:

    - **done/review** PRDs: missing impacts are **errors** — the work is
      complete, so every declared file should exist.
    - **ready/in_progress/draft** PRDs: missing impacts are **warnings** —
      the PRD hasn't been implemented yet, so files it plans to create
      won't exist.

    Raises ``ValueError`` only when completed PRDs have missing impacts
    (causing the runner to return a non-zero exit status, useful for CI).

    This builtin is intentionally read-only — it never modifies PRD files.
    The ``ctx.dry_run`` flag is ignored because no mutations are performed.
    """
    total_checked = 0
    errors: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}

    for prd_id, prd in sorted(ctx.prds.items()):
        # Skip containers — their impacts are aggregated from descendants.
        # Each leaf is checked individually by its own status.
        if containment.children(prd_id, ctx.prds):
            continue
        if not prd.impacts:
            continue
        is_completed = prd.status in _COMPLETED_STATUSES
        for path in prd.impacts:
            total_checked += 1
            full_path = ctx.repo_root / path
            if not full_path.exists():
                if is_completed:
                    errors.setdefault(prd_id, []).append(path)
                else:
                    warnings.setdefault(prd_id, []).append(path)
            else:
                ctx.logger.debug("audit_impacts_check: %s OK  %s", prd_id, path)

    total_errors = sum(len(v) for v in errors.values())
    total_warnings = sum(len(v) for v in warnings.values())
    ctx.report.append(
        f"audit-impacts: {total_checked} path(s) checked, "
        f"{total_errors} error(s), {total_warnings} warning(s)"
    )

    if errors:
        ctx.report.append("ERRORS — missing impacts on completed PRDs:")
        for prd_id, paths in sorted(errors.items()):
            for path in paths:
                ctx.report.append(f"  {prd_id} [{ctx.prds[prd_id].status}]: {path}")

    if warnings:
        ctx.report.append("WARNINGS — missing impacts on incomplete PRDs (expected):")
        for prd_id, paths in sorted(warnings.items()):
            for path in paths:
                ctx.report.append(f"  {prd_id} [{ctx.prds[prd_id].status}]: {path}")

    if errors:
        raise ValueError(
            f"{total_errors} declared impact path(s) missing on completed PRDs"
        )


# Side-effect imports: each module's @_register decorator populates
# SYSTEM_BUILTINS at import time. E402 because they must follow the _register
# definition; F401 because the import is for its side effect, not its name.
import darkfactory.builtins.gather_prd_context as _gather  # noqa: E402, F401
import darkfactory.builtins.discuss_prd as _discuss  # noqa: E402, F401
import darkfactory.builtins.commit_prd_changes as _commit  # noqa: E402, F401
