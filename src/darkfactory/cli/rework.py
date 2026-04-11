"""CLI subcommand: rework — address PR review feedback for a PRD."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from darkfactory.event_log import generate_session_id
from darkfactory.loader import load_workflows
from darkfactory.pr_comments import CommentFilters, fetch_pr_comments
from darkfactory.rework_guard import ReworkGuard
from darkfactory.runner import _compute_branch_name, run_workflow
from darkfactory.worktree_utils import find_worktree_for_prd

from darkfactory.cli._shared import (
    _find_repo_root,
    _load,
    _resolve_base_ref,
    _resolve_prd_or_exit,
)


def find_worktree(prd_id: str, repo_root: Path) -> Path | None:
    """Find the worktree path for the given PRD id.

    Delegates to :func:`~darkfactory.worktree_utils.find_worktree_for_prd`.
    Kept for backward compatibility with any callers outside this module.
    """
    return find_worktree_for_prd(prd_id, repo_root)


def find_open_pr(branch_name: str, repo_root: Path) -> int | None:
    """Find the PR number for an open PR on the given branch."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch_name,
                "--state",
                "open",
                "--json",
                "number",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return None
        prs: list[dict[str, Any]] = json.loads(result.stdout)
        if prs:
            return int(prs[0]["number"])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        pass
    return None


def cmd_rework(args: argparse.Namespace) -> int:
    """Rework a PRD by addressing PR review feedback."""
    prds = _load(args.prd_dir)
    prd_id = args.prd_id
    prd = _resolve_prd_or_exit(prd_id, prds)

    if prd.status != "review":
        raise SystemExit(f"ERROR: {prd_id} is in '{prd.status}', not 'review'")

    repo_root = _find_repo_root(args.prd_dir)

    worktree_path = find_worktree(prd_id, repo_root)
    if worktree_path is None:
        raise SystemExit(
            f"ERROR: No worktree found for {prd_id}. Run 'prd run {prd_id}' first."
        )

    branch_name = _compute_branch_name(prd)
    pr_number = find_open_pr(branch_name, repo_root)
    if pr_number is None:
        raise SystemExit(f"ERROR: No open PR found for {prd_id}")

    if not args.execute:
        print(f"Would rework {prd_id}")
        print(f"  Worktree: {worktree_path}")
        print(f"  PR: #{pr_number}")
        print(f"  Branch: {branch_name}")
        return 0

    # Refuse to run if the guard has blocked this PRD due to loop detection.
    guard = ReworkGuard(repo_root)
    if guard.is_blocked(prd_id):
        raise SystemExit(
            f"ERROR: {prd_id} is blocked by the rework loop guard after "
            f"{guard.get_consecutive_no_change(prd_id)} consecutive no-change "
            f"rework cycle(s). Manual intervention required: remove the entry "
            f"from {guard.state_file} to unblock."
        )

    # Build comment filters from CLI args and fetch unresolved threads.
    filters = CommentFilters(
        include_resolved=args.all,
        since_commit=args.since,
        reviewer=args.reviewer,
        single_comment_id=args.from_pr_comment,
    )
    threads = fetch_pr_comments(pr_number, filters=filters)
    if not threads:
        print(f"No unaddressed comments found for {prd_id}")
        return 0

    # Load the rework workflow from the built-in workflows directory.
    workflows = load_workflows()
    rework_wf = workflows.get("rework")
    if rework_wf is None:
        raise SystemExit("ERROR: rework workflow not found in built-in workflows")

    base_ref = _resolve_base_ref(None, repo_root)
    session = generate_session_id()
    result = run_workflow(
        prd,
        rework_wf,
        repo_root,
        base_ref,
        dry_run=False,
        session_id=session,
        initial_worktree_path=worktree_path,
        initial_pr_number=pr_number,
        initial_review_threads=threads,
        initial_reply_to_comments=args.reply_to_comments,
    )
    return 0 if result.success else 1
