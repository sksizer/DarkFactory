"""Shared rework discovery: worktree, PR, guard state, comment threads.

Single source of truth for the pre-conditions a rework cycle needs:

- An existing worktree for the PRD.
- An open PR on the PRD's branch.
- A non-blocked :class:`~darkfactory.rework.guard.ReworkGuard` state.
- The current unresolved review threads, filtered per CLI flags.

Used by both ``cli/rework.py`` (for dry-run summaries and execute-mode
plumbing) and ``builtins/resolve_rework_context.py`` (which runs the
same discovery from inside the workflow when the CLI hasn't already
done it). Keeping the logic in one module prevents the two call sites
from drifting apart — the earlier shape of ``cmd_rework`` bypassed the
workflow entirely and applied filter logic only in the CLI path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from darkfactory.utils import Ok
from darkfactory.utils.github import gh_json
from darkfactory.utils.github.pr.comments import CommentFilters, ReviewThread
from darkfactory.utils.github.pr.comments import fetch_pr_comments as _fetch_pr_comments
from darkfactory.model import PRD, compute_branch_name
from darkfactory.rework.guard import ReworkGuard
from darkfactory.utils.git.worktree import find_worktree_for_prd

_log = logging.getLogger(__name__)


class ReworkError(Exception):
    """Pre-flight failure for a rework cycle.

    Raised when the discovery step cannot satisfy the rework pre-conditions:
    missing worktree, no open PR, or the loop guard has blocked the PRD.
    The CLI converts these to a ``SystemExit`` with the human-readable
    message; the builtin wraps them in a ``RuntimeError`` so the runner
    records a failed step.
    """


@dataclass
class ReworkContext:
    """Resolved rework pre-conditions for a PRD.

    Populated by :func:`discover_rework_context` and consumed by both
    ``cmd_rework`` (to render the dry-run summary and seed the
    ExecutionContext for the executor) and ``resolve_rework_context``
    (the builtin that runs when the CLI has not pre-discovered).
    """

    worktree_path: Path
    pr_number: int
    branch_name: str
    review_threads: list[ReviewThread]
    comment_filters: CommentFilters
    reply_to_comments: bool


def find_open_pr(branch_name: str, repo_root: Path) -> int | None:
    """Return the number of the open PR for ``branch_name``, or ``None``.

    Shells out to ``gh pr list`` with ``--state open``. Any ``gh``
    failure (missing binary, non-zero exit, unparseable JSON) is
    swallowed and returns ``None`` — the caller treats that as "no
    open PR" and raises :class:`ReworkError` with the PRD id in the
    message.
    """
    match gh_json(
        "pr", "list",
        "--head", branch_name,
        "--state", "open",
        "--json", "number",
        cwd=repo_root,
    ):
        case Ok(value=prs) if prs:
            try:
                return int(prs[0]["number"])
            except (KeyError, IndexError, ValueError, TypeError):
                return None
        case _:
            return None


def discover_rework_context(
    prd: PRD,
    repo_root: Path,
    *,
    comment_filters: CommentFilters,
    reply_to_comments: bool,
    fetch_comments: bool = True,
) -> ReworkContext:
    """Discover the rework pre-conditions for ``prd``.

    Raises :class:`ReworkError` when any pre-condition fails:

    - No worktree is registered for the PRD.
    - No open PR exists for the PRD's branch.
    - :class:`ReworkGuard` has blocked the PRD after repeated no-change cycles.

    When ``fetch_comments`` is ``True`` (default), fetches and filters
    the current unresolved review threads via ``gh``. Callers that only
    need worktree/PR discovery (e.g. a lightweight status command) can
    pass ``False`` to skip the GraphQL round-trip.
    """
    worktree_path = find_worktree_for_prd(prd.id, repo_root)
    if worktree_path is None:
        raise ReworkError(
            f"No worktree found for {prd.id}. Run 'prd run {prd.id}' first."
        )

    branch_name = compute_branch_name(prd)
    pr_number = find_open_pr(branch_name, repo_root)
    if pr_number is None:
        raise ReworkError(f"No open PR found for {prd.id}")

    guard = ReworkGuard(repo_root)
    if guard.is_blocked(prd.id):
        consecutive = guard.get_consecutive_no_change(prd.id)
        raise ReworkError(
            f"{prd.id} is blocked by the rework loop guard after "
            f"{consecutive} consecutive no-change rework cycle(s). "
            f"Manual intervention required: remove the entry from "
            f"{guard.state_file} to unblock."
        )

    threads: list[ReviewThread] = []
    if fetch_comments:
        threads = _fetch_pr_comments(pr_number, filters=comment_filters)

    _log.info(
        "discover_rework_context: %s → worktree=%s, PR=#%d, threads=%d",
        prd.id,
        worktree_path,
        pr_number,
        len(threads),
    )

    return ReworkContext(
        worktree_path=worktree_path,
        pr_number=pr_number,
        branch_name=branch_name,
        review_threads=threads,
        comment_filters=comment_filters,
        reply_to_comments=reply_to_comments,
    )
