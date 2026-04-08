---
id: "PRD-215"
title: "Branch-existence guard against concurrent PRD execution"
kind: task
status: in-progress
priority: medium
effort: xs
capability: simple
parent: null
depends_on:
  - "[[PRD-213-set-status-wrong-repo]]"
blocks: []
impacts:
  - tools/prd-harness/src/prd_harness/builtins.py
  - tools/prd-harness/src/prd_harness/runner.py
  - tools/prd-harness/tests/test_builtins.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-07'
tags:
  - harness
  - concurrency
---

# Branch-existence guard against concurrent PRD execution

## Summary

Two parallel `prd run PRD-XXX` invocations against the same PRD must not both succeed in creating worktrees, branches, and PRs. The existing `status: ready` field in the source PRD file cannot serve as the lock — under PRD-213's invariant, the source repo is never modified by `prd run`, so two runners both see `status: ready` and proceed.

The right lock is **branch existence**: if `prd/{PRD-ID}-{slug}` already exists locally or on `origin`, refuse the run with a clear message.

## Motivation

Without this guard, the failure mode is silent corruption: two runners create the same branch (the second `git worktree add -b` fails confusingly), or worse, two diverged copies of the work get pushed and one clobbers the other. The branch-name collision is also annoying when a previous run failed mid-way and left a stale branch behind — the user gets a cryptic git error instead of "branch already exists, run `prd cleanup PRD-XXX` to release."

## Requirements

1. Before creating a worktree, `ensure_worktree` checks for branch `prd/{prd_id}-{slug}`:
   - In the local repo (`git rev-parse --verify --quiet refs/heads/prd/...`)
   - On `origin` (`git ls-remote --exit-code origin refs/heads/prd/...`)
2. If found in either place AND the existing worktree directory does not exist on disk (i.e. it's stale or owned by another runner), refuse with a clear error message naming the conflict and suggesting `prd cleanup`.
3. If found AND the local worktree directory exists, treat it as a resume (current behavior — no change).
4. The remote check is best-effort: if `git ls-remote` fails (no network, no origin configured), log a warning and proceed with the local check only.
5. `prd cleanup PRD-XXX` (separate, smaller addition) deletes the local branch and worktree if both exist; refuses if the branch has unpushed commits unless `--force` is given.

## Technical Approach

Add a precheck to `ensure_worktree`:

```python
def _branch_exists_local(repo_root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _branch_exists_remote(repo_root: Path, branch: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False  # network issue, fall through
    return result.returncode == 0
```

In `ensure_worktree`:

```python
worktree_path = _worktree_target(ctx)
branch = ctx.branch_name

if worktree_path.exists():
    # Resume — already validated
    return resume_logic()

if _branch_exists_local(ctx.repo_root, branch) or _branch_exists_remote(ctx.repo_root, branch):
    raise RuntimeError(
        f"branch {branch!r} already exists but worktree {worktree_path} is gone. "
        f"Another runner may be working on this PRD, or a previous run left a stale "
        f"branch behind. Run `prd cleanup {ctx.prd.id}` to release it."
    )

# Safe to create
```

## Acceptance Criteria

- [ ] AC-1: Running `prd run PRD-XXX` twice in sequence (without cleanup between) errors on the second invocation with a clear message.
- [ ] AC-2: A fake remote branch (created via `git update-ref refs/remotes/origin/prd/PRD-XXX-...`) also triggers the guard.
- [ ] AC-3: Resuming an interrupted run (worktree dir exists, branch exists) works as before.
- [ ] AC-4: When `git ls-remote` times out, the guard falls back to local-only check and logs a warning.
- [ ] AC-5: A test stubs `subprocess.run` to simulate the branch-exists case and asserts the error.

## Open Questions

- [ ] Should `prd cleanup` be in this PRD or a separate one? Recommendation: separate (smaller, distinct surface area).
- [ ] Do we need a process-level lock too (e.g. flock on `.worktrees/PRD-XXX.lock`) for the case where two runners race between the check and `git worktree add`? Probably overkill for now — branch-existence check handles the common case.

## References

- [[PRD-213-set-status-wrong-repo]] — establishes the "source repo untouched" invariant that makes branch-existence the only viable lock
