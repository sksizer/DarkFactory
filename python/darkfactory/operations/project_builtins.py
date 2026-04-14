"""Project-workflow builtins — bulk mutation, status helpers, and git operations.

These builtins operate on :class:`~darkfactory.workflow.RunContext` and are
registered in :data:`SYSTEM_BUILTINS`, a parallel registry that the project
workflow runner dispatches against.

Git operations (ensure_worktree, commit, push_branch, create_pr, name_worktree,
check_clean_main) are registered in both BUILTINS and SYSTEM_BUILTINS so they
work in both PRD workflow and project workflow modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from darkfactory import model as model_module
from darkfactory.graph import containment
from darkfactory.engine import CandidateList, ProjectRun
from darkfactory.utils.git import GitErr, Ok, Timeout, git_run
from darkfactory.model import compute_branch_name
from darkfactory.workflow import RunContext

SYSTEM_BUILTINS: dict[str, Callable[..., None]] = {}
"""Global registry mapping project builtin name to its implementing function.

Populated at import time via the :func:`_register` decorator.  The project
runner looks up names here when dispatching a :class:`~darkfactory.workflow.BuiltIn`
task inside a project workflow.
"""


def _register(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        if name in SYSTEM_BUILTINS:
            raise ValueError(f"duplicate system builtin registration for {name!r}")
        SYSTEM_BUILTINS[name] = fn
        return fn

    return decorator


@_register("set_status_bulk")
def set_status_bulk(ctx: RunContext, *, status: str) -> None:
    """Update the status field of every PRD id in targets.

    Reads targets and PRDs from the ``ProjectRun`` payload in ``ctx.state``.
    Respects ``ctx.dry_run``. Idempotent: PRDs already at ``status`` are skipped.
    """
    proj = ctx.state.get(ProjectRun)

    for prd_id in proj.targets:
        prd = proj.prds.get(prd_id)
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


@_register("project_load_review_prds")
def project_load_review_prds(ctx: RunContext) -> None:
    """Convenience wrapper: load PRDs with status ``"review"`` into candidates."""
    project_load_prds_by_status(ctx, status="review")


@_register("project_load_prds_by_status")
def project_load_prds_by_status(ctx: RunContext, *, status: str) -> None:
    """Filter PRDs by ``status`` and store matching ids in PhaseState.

    The result is stored as a :class:`CandidateList` in ``ctx.state``.
    Downstream tasks (e.g. :func:`system_check_merged`) read this to know
    which PRDs to examine.
    """
    proj = ctx.state.get(ProjectRun)
    candidates = [prd_id for prd_id, prd in proj.prds.items() if prd.status == status]
    ctx.state.put(CandidateList(prd_ids=candidates))
    ctx.logger.info(
        "project_load_prds_by_status: found %d PRD(s) with status=%r",
        len(candidates),
        status,
    )


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
        case GitErr() | Timeout():
            return False


def _is_merged_squash(repo_root: str, branch: str) -> bool:
    """Return True if any commit on main references ``branch`` in its message."""
    match git_run("log", "main", "--oneline", f"--grep={branch}", cwd=Path(repo_root)):
        case Ok(stdout=output):
            return bool(output.strip())
        case GitErr() | Timeout():
            return False


@_register("system_check_merged")
def system_check_merged(ctx: RunContext) -> None:
    """Check which candidate PRDs have had their branch merged to main.

    Reads ``CandidateList`` from ``ctx.state``. For each candidate, checks
    standard merge and squash-and-merge patterns.

    Replaces the ``ProjectRun`` payload with updated targets and appends
    lines to ``ctx.report``.
    """
    cl = ctx.state.get(CandidateList, CandidateList())
    candidates: list[str] = cl.prd_ids
    proj = ctx.state.get(ProjectRun)
    repo_root = str(ctx.repo_root)
    confirmed: list[str] = []

    for prd_id in candidates:
        prd = proj.prds.get(prd_id)
        if prd is None:
            ctx.report.append(f"{prd_id}: not found in loaded PRDs — skipped")
            continue

        branch = compute_branch_name(prd)

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

    # Replace ProjectRun with updated targets.
    ctx.state.put(
        ProjectRun(
            workflow=proj.workflow,
            prds=proj.prds,
            targets=tuple(confirmed),
            target_prd=proj.target_prd,
        )
    )


@_register("system_mark_done")
def system_mark_done(ctx: RunContext) -> None:
    """Set status to ``"done"`` for all PRDs in targets."""
    set_status_bulk(ctx, status="done")


_COMPLETED_STATUSES = {"done", "review"}


@_register("audit_impacts_check")
def audit_impacts_check(ctx: RunContext) -> None:
    """Walk all PRDs and verify that declared impact paths exist on disk.

    Severity depends on PRD status:

    - **done/review** PRDs: missing impacts are **errors**.
    - **ready/in_progress/draft** PRDs: missing impacts are **warnings**.

    Raises ``ValueError`` only when completed PRDs have missing impacts.
    """
    proj = ctx.state.get(ProjectRun)
    total_checked = 0
    errors: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}

    for prd_id, prd in sorted(proj.prds.items()):
        # Skip containers — their impacts are aggregated from descendants.
        if containment.children(prd_id, proj.prds):
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
                ctx.report.append(f"  {prd_id} [{proj.prds[prd_id].status}]: {path}")

    if warnings:
        ctx.report.append("WARNINGS — missing impacts on incomplete PRDs (expected):")
        for prd_id, paths in sorted(warnings.items()):
            for path in paths:
                ctx.report.append(f"  {prd_id} [{proj.prds[prd_id].status}]: {path}")

    if errors:
        raise ValueError(
            f"{total_errors} declared impact path(s) missing on completed PRDs"
        )


# Side-effect imports: each module's @_register decorator populates
# SYSTEM_BUILTINS at import time. E402 because they must follow the _register
# definition; F401 because the import is for its side effect, not its name.
import darkfactory.operations.gather_prd_context as _gather  # noqa: E402, F401
import darkfactory.operations.discuss_prd as _discuss  # noqa: E402, F401
import darkfactory.operations.commit_prd_changes as _commit  # noqa: E402, F401


# ---------- Register git operations in both registries ----------
# Git operations are already registered in BUILTINS via @builtin decorator.
# We also register them in SYSTEM_BUILTINS so project workflows can use them.


def _register_git_operations() -> None:
    """Copy git operations from BUILTINS to SYSTEM_BUILTINS."""
    from darkfactory.operations._registry import BUILTINS

    # Import all git operation modules to ensure they're registered in BUILTINS.
    import darkfactory.operations.ensure_worktree as _ew  # noqa: F811, F401
    import darkfactory.operations.commit as _cm  # noqa: F811, F401
    import darkfactory.operations.push_branch as _pb  # noqa: F811, F401
    import darkfactory.operations.create_pr as _cp  # noqa: F811, F401
    import darkfactory.operations.name_worktree as _nw  # noqa: F811, F401
    import darkfactory.operations.check_clean_main as _ccm  # noqa: F811, F401

    git_ops = [
        "ensure_worktree",
        "commit",
        "push_branch",
        "create_pr",
        "name_worktree",
        "check_clean_main",
    ]
    for name in git_ops:
        if name in BUILTINS and name not in SYSTEM_BUILTINS:
            SYSTEM_BUILTINS[name] = BUILTINS[name]


_register_git_operations()
