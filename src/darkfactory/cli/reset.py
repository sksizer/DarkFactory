"""Reset command — undo all outstanding work on a PRD and return it to ready."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from filelock import FileLock, Timeout

from darkfactory.cli._shared import _find_repo_root
from darkfactory.event_log import EventWriter, generate_session_id
from darkfactory.git_ops import git_check, git_run
from darkfactory.model import TERMINAL_STATUSES, load_one, set_status
from darkfactory.rework_guard import ReworkGuard
from darkfactory.worktree_utils import (
    find_orphaned_branches,
    find_stale_worktree_for_prd,
)


@dataclass
class _ArtifactSummary:
    """Collected artifact state for a PRD reset."""

    prd_id: str
    worktree_path: Path | None = None
    worktree_branch: str | None = None
    local_branches: list[str] = field(default_factory=list)
    remote_branches: list[str] = field(default_factory=list)
    open_pr_numbers: list[int] = field(default_factory=list)
    has_rework_guard: bool = False
    current_status: str = ""
    lock_file: Path | None = None

    @property
    def has_artifacts(self) -> bool:
        return bool(
            self.worktree_path
            or self.local_branches
            or self.remote_branches
            or self.open_pr_numbers
            or self.has_rework_guard
            or self.current_status not in ("draft", "ready")
        )


def _discover_artifacts(
    prd_id: str, current_status: str, repo_root: Path
) -> _ArtifactSummary:
    """Probe for all artifact types associated with a PRD."""
    summary = _ArtifactSummary(prd_id=prd_id, current_status=current_status)

    # Worktree
    stale = find_stale_worktree_for_prd(prd_id, repo_root)
    if stale is not None:
        summary.worktree_path = stale.worktree_path
        summary.worktree_branch = stale.branch

    # Local branches (glob match)
    summary.local_branches = find_orphaned_branches(prd_id, repo_root)

    # Remote branches
    try:
        result = git_run(
            "branch", "-r", "--list", f"origin/prd/{prd_id}-*", cwd=repo_root
        )
        for line in result.stdout.splitlines():
            branch = line.strip()
            if branch:
                summary.remote_branches.append(branch)
    except subprocess.CalledProcessError:
        pass

    # Open PRs — search across all matching branches
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--json",
                "number,headRefName",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            prs: list[dict[str, object]] = json.loads(result.stdout)
            for pr in prs:
                head = str(pr.get("headRefName", ""))
                if head.startswith(f"prd/{prd_id}-"):
                    pr_number = pr["number"]
                    if isinstance(pr_number, (int, str)):
                        summary.open_pr_numbers.append(int(pr_number))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        pass

    # Rework guard
    guard = ReworkGuard(repo_root)
    summary.has_rework_guard = guard.is_blocked(prd_id) or (
        guard.get_consecutive_no_change(prd_id) > 0
    )

    # Lock file
    lock_path = repo_root / ".worktrees" / f"{prd_id}.lock"
    if lock_path.exists():
        summary.lock_file = lock_path

    return summary


def _print_summary(summary: _ArtifactSummary) -> None:
    """Print the artifact summary table."""
    print(f"Artifacts for {summary.prd_id}:")
    print(f"  Status:         {summary.current_status}")

    if summary.worktree_path:
        print(f"  Worktree:       {summary.worktree_path}")
    else:
        print("  Worktree:       (none)")

    if summary.local_branches:
        for b in summary.local_branches:
            print(f"  Local branch:   {b}")
    else:
        print("  Local branches: (none)")

    if summary.remote_branches:
        for b in summary.remote_branches:
            print(f"  Remote branch:  {b}")
    else:
        print("  Remote branches: (none)")

    if summary.open_pr_numbers:
        for pr_num in summary.open_pr_numbers:
            print(f"  Open PR:        #{pr_num}")
    else:
        print("  Open PRs:       (none)")

    if summary.has_rework_guard:
        print("  Rework guard:   blocked/active")
    else:
        print("  Rework guard:   (none)")

    if summary.lock_file:
        print(f"  Lock file:      {summary.lock_file}")
    else:
        print("  Lock file:      (none)")


def _execute_reset(
    summary: _ArtifactSummary, repo_root: Path, data_dir: Path
) -> tuple[list[str], list[str]]:
    """Execute the reset teardown in dependency order. Returns (cleaned, skipped)."""
    cleaned: list[str] = []
    skipped: list[str] = []

    # 6a. Close all open PRs
    for pr_num in summary.open_pr_numbers:
        try:
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "close",
                    str(pr_num),
                    "--comment",
                    "Closed by `prd reset`.",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            cleaned.append(f"closed PR #{pr_num}")
            print(f"  Closed PR #{pr_num}")
        except subprocess.CalledProcessError:
            skipped.append(f"PR #{pr_num} (close failed)")
            print(f"  Skipped PR #{pr_num} (close failed)")

    # 6b. Remove worktree
    if summary.worktree_path:
        try:
            git_run(
                "worktree",
                "remove",
                "--force",
                str(summary.worktree_path),
                cwd=repo_root,
            )
            git_check("worktree", "prune", cwd=repo_root)
            cleaned.append(f"removed worktree {summary.worktree_path}")
            print(f"  Removed worktree {summary.worktree_path}")
        except subprocess.CalledProcessError:
            skipped.append(f"worktree {summary.worktree_path} (remove failed)")
            print("  Skipped worktree removal (failed)")
    else:
        # Still prune to clean stale metadata
        git_check("worktree", "prune", cwd=repo_root)

    # 6c. Release and remove lock file
    if summary.lock_file and summary.lock_file.exists():
        try:
            summary.lock_file.unlink()
            cleaned.append(f"removed lock file {summary.lock_file}")
            print(f"  Removed lock file {summary.lock_file}")
        except OSError:
            skipped.append(f"lock file {summary.lock_file}")

    # 6d. Delete local branches
    for branch in summary.local_branches:
        try:
            git_run("branch", "-D", branch, cwd=repo_root)
            cleaned.append(f"deleted local branch {branch}")
            print(f"  Deleted local branch {branch}")
        except subprocess.CalledProcessError:
            skipped.append(f"local branch {branch}")
            print(f"  Skipped local branch {branch} (delete failed)")

    # 6e. Delete remote branches
    for remote_branch in summary.remote_branches:
        # remote_branch looks like "origin/prd/PRD-XXX-slug"
        ref = remote_branch.removeprefix("origin/")
        try:
            git_run("push", "origin", "--delete", ref, cwd=repo_root)
            cleaned.append(f"deleted remote branch {ref}")
            print(f"  Deleted remote branch {ref}")
        except subprocess.CalledProcessError:
            skipped.append(f"remote branch {ref}")
            print(f"  Skipped remote branch {ref} (delete failed)")

    # 6f. Remove rework guard entry
    if summary.has_rework_guard:
        guard = ReworkGuard(repo_root)
        guard.reset(summary.prd_id)
        cleaned.append("cleared rework guard")
        print("  Cleared rework guard")

    # 6g. Reset status to ready (only for active states)
    if summary.current_status not in ("draft", "ready"):
        try:
            prd = load_one(data_dir, summary.prd_id)
            set_status(prd, "ready")
            cleaned.append(f"status {summary.current_status} -> ready")
            print(f"  Status: {summary.current_status} -> ready")
        except (KeyError, OSError) as exc:
            skipped.append(f"status reset ({exc})")
            print(f"  Skipped status reset ({exc})")

    return cleaned, skipped


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset outstanding work on a PRD."""
    repo_root = _find_repo_root(args.data_dir)
    prd_id: str = args.prd_id
    execute: bool = getattr(args, "execute", False)
    yes: bool = getattr(args, "yes", False)

    # Load the PRD
    try:
        prd = load_one(args.data_dir, prd_id)
    except KeyError:
        print(f"unknown PRD id: {prd_id}", file=sys.stderr)
        return 1

    # FR-4: Status guard — reject terminal states
    if prd.status in TERMINAL_STATUSES:
        print(
            f"Cannot reset {prd_id}: status is {prd.status!r} (terminal state).",
            file=sys.stderr,
        )
        return 1

    # FR-4: Warn for draft/ready
    if prd.status in ("draft", "ready"):
        print(
            f"Warning: {prd_id} is in {prd.status!r} status — "
            f"no workflow has run. Probing for orphaned artifacts."
        )

    # Discovery phase
    summary = _discover_artifacts(prd_id, prd.status, repo_root)

    # Print summary
    _print_summary(summary)

    if not summary.has_artifacts:
        print(f"\nNothing to reset for {prd_id}.")
        return 0

    # Dry-run default
    if not execute:
        print("\nDry run. Use --execute to perform the reset.")
        return 0

    # FR-5: Concurrency check — acquire lock non-blocking
    lock_path = repo_root / ".worktrees" / f"{prd_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print(
            f"Cannot reset {prd_id}: a workflow is currently running "
            f"(lock held at {lock_path}). Stop the running process first.",
            file=sys.stderr,
        )
        return 1

    try:
        # FR-3: Confirmation prompt
        if not yes:
            confirm = input(f"Reset {prd_id}? All artifacts will be removed. [y/N] ")
            if confirm.strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return 1

        print(f"\nResetting {prd_id}...")
        cleaned, skipped = _execute_reset(summary, repo_root, args.data_dir)

        # 6h. Emit event
        session_id = generate_session_id()
        writer = EventWriter(repo_root, session_id, prd_id)
        try:
            writer.emit(
                "cli",
                "prd_reset",
                cleaned=cleaned,
                skipped=skipped,
            )
        finally:
            writer.close()

        # Summary
        print(
            f"\nReset complete: {len(cleaned)} artifact(s) cleaned, "
            f"{len(skipped)} skipped."
        )
    finally:
        # Release the lock we acquired; the lock file itself may have been
        # deleted by _execute_reset (step 6c), which is fine.
        try:
            lock.release()
        except OSError:
            pass

    return 0
