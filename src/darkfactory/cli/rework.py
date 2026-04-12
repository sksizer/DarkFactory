"""CLI subcommand: rework — address PR review feedback for a PRD."""

from __future__ import annotations

import argparse

from darkfactory.event_log import generate_session_id
from darkfactory.loader import load_workflows
from darkfactory.phase_state import ReworkState
from darkfactory.pr_comments import CommentFilters
from darkfactory.rework_context import (
    ReworkContext,
    ReworkError,
    discover_rework_context,
)
from darkfactory.runner import run_workflow

from darkfactory.cli._shared import (
    _find_repo_root,
    _load,
    _resolve_base_ref,
    _resolve_prd_or_exit,
)


def cmd_rework(args: argparse.Namespace) -> int:
    """Rework a PRD by addressing PR review feedback.

    Resolves the PRD, checks it's in ``review``, then delegates all
    worktree/PR/guard/comment discovery to
    :func:`~darkfactory.rework_context.discover_rework_context`. That
    same discovery module is what the ``resolve_rework_context``
    builtin calls when the workflow runs outside the CLI, so the two
    paths cannot drift apart.

    Without ``--execute``, prints a dry-run summary and exits.
    With ``--execute`` and any unresolved threads, invokes the rework
    workflow, seeding the ExecutionContext's PhaseState with the
    already-discovered state so the builtin at position 0 is a no-op.
    """
    prds = _load(args.data_dir)
    prd = _resolve_prd_or_exit(args.prd_id, prds)

    if prd.status != "review":
        raise SystemExit(f"ERROR: {prd.id} is in '{prd.status}', not 'review'")

    repo_root = _find_repo_root(args.data_dir)

    filters = CommentFilters(
        include_resolved=args.all,
        since_commit=args.since,
        reviewer=args.reviewer,
        single_comment_id=args.from_pr_comment,
    )

    try:
        discovered = discover_rework_context(
            prd,
            repo_root,
            comment_filters=filters,
            reply_to_comments=args.reply_to_comments,
        )
    except ReworkError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    if not args.execute:
        _print_dry_run_summary(prd.id, discovered)
        return 0

    if not discovered.review_threads:
        print(f"No unaddressed comments found for {prd.id}")
        return 0

    workflows = load_workflows()
    rework_wf = workflows.get("rework")
    if rework_wf is None:
        raise SystemExit("ERROR: rework workflow not found in built-in workflows")

    base_ref = _resolve_base_ref(None, repo_root)
    session = generate_session_id()

    rework_state = ReworkState(
        pr_number=discovered.pr_number,
        review_threads=discovered.review_threads,
        comment_filters=discovered.comment_filters,
        reply_to_comments=discovered.reply_to_comments,
    )

    result = run_workflow(
        prd,
        rework_wf,
        repo_root,
        base_ref,
        dry_run=False,
        session_id=session,
        context_overrides={
            "worktree_path": discovered.worktree_path,
            "cwd": discovered.worktree_path,
        },
        phase_state_init=[rework_state],
    )
    return 0 if result.success else 1


def _print_dry_run_summary(prd_id: str, discovered: ReworkContext) -> None:
    """Print the human-readable dry-run summary for ``prd rework PRD-X``."""
    print(f"Would rework {prd_id}")
    print(f"  Worktree: {discovered.worktree_path}")
    print(f"  PR: #{discovered.pr_number}")
    print(f"  Branch: {discovered.branch_name}")
    print(f"  Comments: {len(discovered.review_threads)}")
