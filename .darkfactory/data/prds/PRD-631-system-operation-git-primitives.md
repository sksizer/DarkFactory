---
id: PRD-631
title: System operation git primitives — worktree, commit, push, PR
kind: epic
status: draft
priority: high
effort: m
capability: moderate
parent: null
depends_on: []
blocks: []
impacts:
  - src/darkfactory/operations/system_builtins.py
workflow: null
assignee: null
reviewers: []
target_version: null
created: 2026-04-12
updated: 2026-04-12
tags:
  - system-operations
  - architecture
---

# System operation git primitives — worktree, commit, push, PR

## Summary

System operations (`prd system run`) currently cannot create worktrees, commit changes, push branches, or open PRs. The `SystemOperation` dataclass already declares `creates_pr`, `pr_title`, and `pr_body` fields, but no system-level builtins exist to fulfil them. This PRD adds the missing primitives so system operations can produce PRs just like per-PRD workflows.

## Motivation

Several planned system operations need to make changes and submit them for review:

- **Documentation audit/update** — read the site, compare against code, update docs, open a PR
- **Plan operation** (`.darkfactory/operations/plan/`) — already authored with `ensure_worktree`, `commit`, `push_branch`, `create_pr` tasks but **broken at runtime** because those names only exist in the workflow `BUILTINS` registry, not `SYSTEM_BUILTINS`
- **Bulk refactors** — reconcile status, normalize frontmatter, etc.

Without these primitives, any system operation that wants to produce a PR must hack around the limitation or be modelled as a per-PRD workflow with a synthetic PRD — neither is acceptable.

## Requirements

### Functional

1. **`system_ensure_worktree`** — Create a git worktree + branch for the operation. Branch naming convention: `system/{operation-name}` (or `system/{operation-name}-{target_prd}` when `accepts_target=True`). Must handle resume (branch already exists) and acquire advisory lock.
2. **`system_commit`** — Stage and commit changes in the operation's worktree. Accept `message` kwarg with `{target_prd}` placeholder support. Respect `dry_run`.
3. **`system_push_branch`** — Push the operation branch to origin. Respect `dry_run`.
4. **`system_create_pr`** — Open a PR using `ctx.operation.pr_title` and `ctx.operation.pr_body`, substituting `{target_prd}` and any other context placeholders. Set `ctx.pr_url`. Respect `dry_run`.
5. All four must be registered in `SYSTEM_BUILTINS` so the system runner can dispatch them.
6. All four must respect `ctx.dry_run` — log intent without side effects.
7. The existing `plan` operation must work end-to-end after this change (it already references these builtin names).

### Non-Functional

1. Reuse existing utility code (`utils/git/`, `utils/github/`) rather than duplicating subprocess calls.
2. Follow the same advisory-lock pattern as workflow `ensure_worktree` for concurrency safety.
3. Must not break existing system operations that don't use these new builtins.

## Technical Approach

The workflow builtins (`ensure_worktree`, `commit`, `push_branch`, `create_pr`) in the `operations/` package are tightly coupled to `ExecutionContext` — they read `ctx.prd`, `ctx.branch_name`, `ctx.worktree_path`, etc. The system equivalents will:

1. Derive branch name from `ctx.operation.name` + optional `ctx.target_prd` instead of `ctx.prd`
2. Store worktree path on `ctx` (likely via `PhaseState` or a new field on `SystemContext`)
3. Call the same underlying `utils/git/` and `utils/github/` functions
4. Be registered via the existing `@_register` decorator in `system_builtins.py`

A `SystemWorktreeState` dataclass (stored in `ctx.state` via `PhaseState`) could carry the branch name and worktree path between the four builtins.

## Acceptance Criteria

- [ ] AC-1: `prd system run plan --target PRD-X --execute` successfully creates worktree, commits, pushes, and opens PR
- [ ] AC-2: Dry-run mode logs intent for all four operations without side effects
- [ ] AC-3: Existing system operations (verify-merges, audit-impacts, discuss) remain unaffected
- [ ] AC-4: Advisory lock prevents concurrent system worktree operations

## Open Questions

- OPEN: Should the branch naming be `system/{op-name}` or something else? Need to avoid collisions with `prd/` branches.
- OPEN: Should `SystemContext` gain explicit `branch_name` and `worktree_path` fields, or should these be carried purely via `PhaseState`?
- OPEN: Should these builtins be named `system_ensure_worktree` (prefixed) or just `ensure_worktree` (same name, different registry)? Using the same names would let existing operation definitions (like `plan`) work without changes.

## References

- `src/darkfactory/operations/system_builtins.py` — where new builtins will be registered
- `src/darkfactory/system.py` — `SystemOperation` and `SystemContext` definitions
- `src/darkfactory/operations/ensure_worktree.py` — workflow-level equivalent to study
- `.darkfactory/operations/plan/operation.py` — broken operation that needs these primitives
