"""Cleanup command — remove worktrees for completed PRDs."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from darkfactory import checks
from darkfactory.checks import StaleWorktree, find_stale_worktrees, is_safe_to_remove
from darkfactory.cli._shared import _find_repo_root
from darkfactory.git_ops import git_check, git_run
from darkfactory.utils.git.worktree import (
    find_orphaned_branches,
    find_stale_worktree_for_prd,
    remove_worktree,
)


def _remove_worktree(worktree: StaleWorktree, repo_root: Path) -> None:
    """Remove a worktree directory and delete the local branch."""
    remove_worktree(worktree, repo_root)


def _find_worktree_for_prd(prd_id: str, repo_root: Path) -> StaleWorktree | None:
    """Find the worktree entry for the given PRD id, regardless of PR state."""
    return find_stale_worktree_for_prd(prd_id, repo_root)


def _find_orphaned_branch(prd_id: str, repo_root: Path) -> str | None:
    """Find a local branch for *prd_id* when the worktree dir is gone."""
    branches = find_orphaned_branches(prd_id, repo_root)
    return branches[0] if branches else None


def _orphaned_branch_commit_count(
    branch: str, repo_root: Path, base: str = "main"
) -> int:
    """Count commits on *branch* ahead of *base*."""
    try:
        result = git_run("rev-list", "--count", f"{base}..{branch}", cwd=repo_root)
        return int(result.stdout.strip() or "0")
    except subprocess.CalledProcessError:
        return 0


def _cleanup_single(prd_id: str, force: bool, repo_root: Path) -> int:
    worktree = _find_worktree_for_prd(prd_id, repo_root)
    if worktree is None:
        # Worktree dir is gone — check for an orphaned branch.
        orphaned = _find_orphaned_branch(prd_id, repo_root)
        if orphaned is None:
            print(f"No worktree or orphaned branch found for {prd_id}")
            return 1
        ahead = _orphaned_branch_commit_count(orphaned, repo_root)
        if ahead > 0 and not force:
            print(
                f"Orphaned branch '{orphaned}' has {ahead} commit(s) "
                f"not on main. Use --force to delete it."
            )
            return 1
        # Prune any stale git worktree bookkeeping for the missing directory.
        git_check("worktree", "prune", cwd=repo_root)
        git_run("branch", "-D", orphaned, cwd=repo_root)
        label = f"orphaned branch '{orphaned}'"
        if ahead > 0:
            label += f" ({ahead} commit(s) ahead of main)"
        print(f"Removed {label} for {prd_id}")
        return 0
    status = is_safe_to_remove(worktree, force=force)
    if not status.safe:
        print(f"Cannot remove {prd_id}: {status.reason}")
        return 1
    _remove_worktree(worktree, repo_root)
    print(f"Removed worktree and branch for {prd_id}")
    return 0


def _cleanup_merged(force: bool, repo_root: Path) -> int:
    stale = find_stale_worktrees(repo_root)
    if not stale:
        print("No stale worktrees found")
        return 0
    removed = 0
    skipped = 0
    for worktree in stale:
        status = is_safe_to_remove(worktree, force=force)
        if not status.safe:
            print(f"Skipping {worktree.prd_id}: {status.reason}")
            skipped += 1
            continue
        _remove_worktree(worktree, repo_root)
        print(f"Removed {worktree.prd_id}")
        removed += 1
    print(f"Removed {removed}, skipped {skipped}")
    return 0 if skipped == 0 else 1


def _cleanup_all(force: bool, repo_root: Path) -> int:
    worktrees_dir = repo_root / ".worktrees"
    if not worktrees_dir.exists():
        print("No .worktrees directory found")
        return 0

    all_worktrees: list[StaleWorktree] = []
    for entry in sorted(worktrees_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        m = re.match(r"^(PRD-[\d.]+)", name)
        if not m:
            continue
        prd_id = m.group(1)
        branch = f"prd/{name}"
        pr_state = checks._get_pr_state(branch, repo_root)
        all_worktrees.append(
            StaleWorktree(
                prd_id=prd_id,
                branch=branch,
                worktree_path=entry,
                pr_state=pr_state,
            )
        )

    if not all_worktrees:
        print("No worktrees found")
        return 0

    open_prs = [w for w in all_worktrees if w.pr_state == "OPEN"]
    if open_prs:
        print(f"Warning: {len(open_prs)} worktree(s) have open PRs:")
        for w in open_prs:
            print(f"  {w.prd_id} ({w.branch})")

    confirm = (
        input(f"Remove all {len(all_worktrees)} worktree(s)? [y/N] ").strip().lower()
    )
    if confirm not in ("y", "yes"):
        print("Aborted")
        return 1

    removed = 0
    skipped = 0
    for worktree in all_worktrees:
        status = is_safe_to_remove(worktree, force=force)
        if not status.safe:
            print(f"Skipping {worktree.prd_id}: {status.reason}")
            skipped += 1
            continue
        _remove_worktree(worktree, repo_root)
        print(f"Removed {worktree.prd_id}")
        removed += 1
    print(f"Removed {removed}, skipped {skipped}")
    return 0 if skipped == 0 else 1


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Remove worktrees for completed PRDs."""
    repo_root = _find_repo_root(args.data_dir)
    prd_id: str | None = getattr(args, "prd_id", None)
    merged: bool = getattr(args, "merged", False)
    all_: bool = getattr(args, "all_", False)
    force: bool = getattr(args, "force", False)

    if prd_id:
        return _cleanup_single(prd_id, force, repo_root)
    elif merged:
        return _cleanup_merged(force, repo_root)
    elif all_:
        return _cleanup_all(force, repo_root)
    else:
        print("Specify PRD-X, --merged, or --all")
        return 1
