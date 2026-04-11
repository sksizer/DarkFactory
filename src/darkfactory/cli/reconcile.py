"""Reconcile command — flip merged PRDs from review → done."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from darkfactory.cli._shared import _find_repo_root
from darkfactory.git_ops import git_check, git_run
from darkfactory.model import update_frontmatter_field_at


def _get_merged_prd_prs() -> list[dict[str, Any]]:
    """Return merged PRs whose head branch matches ``prd/PRD-*``."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--json",
            "headRefName,mergedAt,mergeCommit,number",
            "--limit",
            "200",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"gh pr list failed: {result.stderr.strip()}")
    prs: list[dict[str, Any]] = json.loads(result.stdout)
    return [pr for pr in prs if re.match(r"^prd/PRD-", pr["headRefName"])]


def _find_prd_file_for_branch(branch_name: str, prd_dir: Path) -> Path | None:
    """Return the PRD file for a branch like ``prd/PRD-224.7-reconcile-status``."""
    m = re.match(r"^prd/(PRD-[\d.]+)", branch_name)
    if not m:
        return None
    prd_id = m.group(1)
    for f in sorted(prd_dir.glob(f"{prd_id}-*.md")):
        return f
    return None


def _get_prd_status(path: Path) -> str | None:
    """Read the ``status`` field from a PRD file's frontmatter."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^status:\s*(.+)$", line)
        if m:
            return m.group(1).strip().strip("\"'")
    return None


def _extract_prd_id_from_path(prd_file: Path) -> str:
    """Extract the PRD ID (e.g. ``PRD-224.7``) from a filename."""
    m = re.match(r"^(PRD-[\d.]+)-", prd_file.name)
    return m.group(1) if m else prd_file.stem


def _merge_commit_is_ancestor(pr: dict[str, Any], repo_root: Path) -> bool:
    """Check whether the PR's merge commit is reachable from HEAD.

    Returns True if the merge commit is an ancestor of HEAD (changes are
    present), False if it is missing (changes may have been clobbered).
    When the merge commit SHA is unavailable, returns False (suspicious).
    """
    merge_commit = pr.get("mergeCommit") or {}
    sha = merge_commit.get("oid")
    if not sha:
        return False  # can't verify — treat as suspicious
    return git_check("merge-base", "--is-ancestor", sha, "HEAD", cwd=repo_root)


def _build_reconcile_commit_msg(
    candidates: list[tuple[Path, dict[str, Any]]],
) -> str:
    """Build the commit message for a reconcile operation."""
    if len(candidates) == 1:
        prd_file, pr = candidates[0]
        prd_id = _extract_prd_id_from_path(prd_file)
        return (
            f"chore(prd): mark {prd_id} done "
            f"(auto-reconciled from merged PR #{pr['number']}) [skip ci]"
        )
    return f"chore(prd): reconcile {len(candidates)} merged PRD statuses [skip ci]"


def _commit_to_main(
    candidates: list[tuple[Path, dict[str, Any]]],
    repo_root: Path,
) -> None:
    """Stage changed PRD files and commit directly to main."""
    files = [str(c[0]) for c in candidates]
    git_run("add", *files, cwd=repo_root)
    msg = _build_reconcile_commit_msg(candidates)
    git_run("commit", "-m", msg, cwd=repo_root)


def _create_reconcile_pr(
    candidates: list[tuple[Path, dict[str, Any]]],
    repo_root: Path,
) -> None:
    """Create a PR with the reconciled status changes."""
    branch = f"prd/reconcile-status-{date.today().strftime('%Y%m%d')}"
    # Delete stale branch from a previous run, if any.
    git_check("branch", "-D", branch, cwd=repo_root)
    git_run("checkout", "-b", branch, cwd=repo_root)
    files = [str(c[0]) for c in candidates]
    git_run("add", *files, cwd=repo_root)
    msg = _build_reconcile_commit_msg(candidates)
    git_run("commit", "-m", msg, cwd=repo_root)
    git_run("push", "-u", "origin", branch, cwd=repo_root)
    subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            msg,
            "--body",
            "Auto-reconciled by `prd reconcile`",
        ],
        check=True,
    )


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Find merged-but-not-flipped PRDs and reconcile their status."""
    prds_dir = args.data_dir / "prds"

    # 1. Get merged PRs with prd/* branches.
    merged_prs = _get_merged_prd_prs()

    # 2. Find corresponding PRD files still in 'review'.
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for pr in merged_prs:
        prd_file = _find_prd_file_for_branch(pr["headRefName"], prds_dir)
        if prd_file is None:
            continue
        if _get_prd_status(prd_file) == "review":
            candidates.append((prd_file, pr))

    if not candidates:
        print("All PRD statuses are up to date.")
        return 0

    # 2b. Verify merge commits are reachable from HEAD.
    repo_root = _find_repo_root(args.data_dir)
    verified: list[tuple[Path, dict[str, Any]]] = []
    clobbered: list[tuple[Path, dict[str, Any]]] = []
    for prd_file, pr in candidates:
        if _merge_commit_is_ancestor(pr, repo_root):
            verified.append((prd_file, pr))
        else:
            clobbered.append((prd_file, pr))

    if clobbered:
        print("WARNING: The following PRDs were merged but their merge commits")
        print("are NOT reachable from HEAD — changes may have been clobbered:\n")
        for prd_file, pr in clobbered:
            prd_id = _extract_prd_id_from_path(prd_file)
            sha = (pr.get("mergeCommit") or {}).get("oid", "???")[:10]
            print(
                f"  {prd_id}: PR #{pr['number']} merge commit {sha} missing from HEAD"
            )
        print()

    candidates = verified

    if not candidates:
        print("No PRDs to reconcile (all candidates have missing merge commits).")
        return 0

    # 3. Print what would change (dry-run).
    for prd_file, pr in candidates:
        prd_id = _extract_prd_id_from_path(prd_file)
        print(f"  {prd_id}: review -> done (from merged PR #{pr['number']})")

    if not args.execute:
        print("\nDry run. Use --execute to apply changes.")
        return 0

    # 4. Apply changes.
    today = date.today().isoformat()
    for prd_file, _pr in candidates:
        update_frontmatter_field_at(
            prd_file, {"status": "done", "updated": f"'{today}'"}
        )

    # 5. Commit.
    if args.commit_to_main:
        _commit_to_main(candidates, repo_root)
    else:
        _create_reconcile_pr(candidates, repo_root)

    return 0
