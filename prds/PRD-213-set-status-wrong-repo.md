---
id: "PRD-213"
title: "set_status writes to source repo instead of worktree"
kind: task
status: done
priority: high
effort: xs
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - tools/prd-harness/src/prd_harness/builtins.py
  - tools/prd-harness/tests/test_builtins.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - bug
---

# set_status writes to source repo instead of worktree

## Summary

When the harness runs a workflow, the `set_status` builtin modifies the PRD frontmatter file in the **source repo** (where `prd run` was invoked) instead of the **worktree copy**. The corresponding `commit` builtin then has nothing to commit in the worktree, so the status transition is silently lost from the PR while leaving an uncommitted change in the source checkout.

Discovered during the first live run of PRD-501 against the `extraction` workflow: `~/Developer/pumice/tools/prd-harness/dev-prds/PRD-501-...md` showed `status: in-progress` in the source repo's working tree, while the worktree copy still said `status: ready`.

## Motivation

The whole point of using worktrees is isolation. Establish the invariant:

> **`prd run` never modifies the source repository's working tree. Period.**

Status transitions live on the PRD's worktree branch and only reach the source repo via PR merge — that's the human-controlled checkpoint. Today the harness violates this on the very first `set_status` call: the source checkout ends up with a stray uncommitted modification, and the worktree branch never receives the status-transition commit it was supposed to.

This invariant also clarifies the role of the `status` field in concurrency: it's a **human signal**, not a mutex. Two parallel `prd run` invocations against the same PRD don't race on the file's `status: ready` line — they race on branch existence (see PRD-215 for the branch-existence concurrency guard).

## Requirements

1. `set_status` mutates the PRD file inside `ctx.worktree_path`, never `ctx.repo_root`.
2. After ANY workflow step, `git status` in the source repo shows zero modifications attributable to the harness.
3. The worktree branch HEAD contains the status-transition commit after the setup phase.
4. The same invariant applies to every other builtin that touches files: `commit`, `set_workflow`, `touch_updated`, etc. — they all operate on `ctx.worktree_path` derivatives.
5. Existing tests continue to pass; new tests assert the source repo is untouched after a full workflow run.

## Technical Approach

Inspect `builtins.py::set_status`. It almost certainly resolves the PRD path via `ctx.prd.path`, which is the absolute path the PRD was loaded from at CLI invocation time — i.e. the source repo. The fix is to rewrite that path relative to `ctx.worktree_path`:

```python
relative = ctx.prd.path.relative_to(ctx.repo_root)
target = ctx.worktree_path / relative
```

Same applies to `commit`'s `git add` step — it should `git add` the worktree-relative path, not the source-repo path.

A related concern: the YAML round-trip is also dropping quotes (`"PRD-501"` → `PRD-501`). That's a separate frontmatter-preservation bug — see PRD-214.

## Acceptance Criteria

- [ ] AC-1: After `prd run --execute` against a leaf PRD, `git status` in the source repo is clean (no modifications, no untracked files attributable to the harness).
- [ ] AC-2: The worktree branch has the status-transition commit at HEAD after the setup phase, and it contains exactly the changed `status:` line plus the bumped `updated:` line — nothing else.
- [ ] AC-3: A test simulates a worktree+source layout and asserts only the worktree file changes.
- [ ] AC-4: The invariant is documented in the harness README and `builtins.py` module docstring.

## References

- [[PRD-214-frontmatter-roundtrip-drift]] — needed so AC-2 (one-line diff) is achievable
- [[PRD-215-prd-concurrency-guard]] — the real concurrency mechanism (branch existence), since `status:` field is no longer the lock
