#!/usr/bin/env python3
"""Verify that all merged PR merge commits are ancestors of main.

Exits 0 if all merged PRs are properly integrated.
Exits 1 if any merged PR's merge commit is not an ancestor of main,
printing a report of the affected PRs.

Requires: git, gh (GitHub CLI)
"""

from __future__ import annotations

import json
import subprocess
import sys


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def _is_ancestor(sha: str, branch: str = "main") -> bool:
    result = _run(["git", "merge-base", "--is-ancestor", sha, branch])
    return result.returncode == 0


def main() -> int:
    # Fetch all merged PRs via gh CLI
    result = _run([
        "gh", "pr", "list",
        "--state", "merged",
        "--limit", "200",
        "--json", "number,title,mergeCommit,mergedAt",
    ])
    if result.returncode != 0:
        print(f"ERROR: gh pr list failed: {result.stderr}", file=sys.stderr)
        return 1

    prs = json.loads(result.stdout)
    prs.sort(key=lambda p: p.get("mergedAt", ""))

    missing: list[dict[str, object]] = []
    ok_count = 0

    for pr in prs:
        sha = pr.get("mergeCommit", {}).get("oid", "")
        if not sha:
            continue
        if _is_ancestor(sha):
            ok_count += 1
        else:
            missing.append({
                "number": pr["number"],
                "title": pr["title"],
                "sha": sha[:7],
                "merged_at": pr.get("mergedAt", "unknown"),
            })

    # Report
    total = ok_count + len(missing)
    print(f"Verified {total} merged PRs: {ok_count} OK, {len(missing)} MISSING")
    print()

    if missing:
        print("MISSING — merge commit not an ancestor of main:")
        print()
        for m in missing:
            print(f"  PR #{m['number']} ({m['sha']}) {m['title']}")
            print(f"    merged: {m['merged_at']}")
        print()
        print(
            "These PRs show as merged on GitHub but their code may not be on main."
        )
        print(
            "Investigate each one: the merge commit may have been on a branch "
            "that was force-pushed or merged in a way that didn't reach main."
        )
        return 1

    print("All merged PR merge commits are ancestors of main.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
