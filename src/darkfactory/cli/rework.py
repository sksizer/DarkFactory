"""CLI subcommand: rework — address PR review feedback for a PRD."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from darkfactory.runner import _compute_branch_name

from darkfactory.cli._shared import (
    _find_repo_root,
    _load,
)


def find_worktree(prd_id: str, repo_root: Path) -> Path | None:
    """Find the worktree path for the given PRD id using git worktree list."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return None
    except FileNotFoundError:
        return None

    current_path: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree ") :]
        elif line.startswith("branch "):
            branch_ref = line[len("branch ") :]
            branch = branch_ref.removeprefix("refs/heads/")
            if re.match(rf"^prd/{re.escape(prd_id)}-", branch):
                return Path(current_path) if current_path else None
    return None


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
    if prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {prd_id}")
    prd = prds[prd_id]

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

    # Set up execution context for the rework workflow (PRD-225.4)
    return 0
