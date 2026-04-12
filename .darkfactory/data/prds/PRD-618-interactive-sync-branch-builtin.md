---
id: PRD-618
title: interactive sync_branch builtin
kind: task
status: draft
priority: low
effort: m
capability: simple
parent: null
depends_on:
  - PRD-617
blocks: []
impacts:
  - src/darkfactory/builtins/
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-11'
updated: '2026-04-11'
tags: []
---

# interactive sync_branch builtin

## Summary

Create a `sync_branch` builtin that handles non-fast-forward
scenarios interactively — rebase, merge, or force-reset — as a
complement to the strict `fast_forward_branch` builtin (PRD-617).

## Motivation

PRD-617 introduces `fast_forward_branch`, which deliberately fails
loudly when the local branch has diverged from origin (local ahead,
or both ahead and behind). This is the correct default for
automated workflows where silent data loss is worse than halting.

However, in interactive or semi-interactive usage (e.g., a human
running `prd rework` after manually editing files in the worktree),
the user may *want* the harness to help resolve the divergence
rather than just refusing to proceed. A `sync_branch` builtin
would offer guided resolution: rebase onto origin, merge, or
force-reset to origin (with confirmation).

This PRD is deferred until we see whether `fast_forward_branch`'s
strict failure mode causes frequent friction in practice.

## Requirements

### Functional

1. `sync_branch` handles all states that `fast_forward_branch`
   handles (up-to-date, behind, ahead, diverged), but instead of
   failing on ahead/diverged, offers resolution options.
2. When local is ahead of origin: offer to push the local commits
   first, then proceed.
3. When diverged (both ahead and behind): offer rebase onto
   origin, merge, or abort. Never force-reset without explicit
   confirmation.
4. All resolution actions are event-logged with full detail
   (strategy chosen, SHAs before/after).
5. In non-interactive mode (e.g., `--execute` without a TTY),
   falls back to `fast_forward_branch` behavior (fail on
   non-ff cases).

### Non-Functional

1. Reuses `fast_forward_branch` for the common ff-only path —
   no code duplication.
2. No new dependencies beyond what the harness already uses.

## Acceptance Criteria

- [ ] AC-1: `sync_branch` builtin registered and importable.
- [ ] AC-2: Up-to-date and behind-origin cases behave identically
  to `fast_forward_branch`.
- [ ] AC-3: Ahead-of-origin case offers push option in interactive
  mode, fails in non-interactive mode.
- [ ] AC-4: Diverged case offers rebase/merge/abort in interactive
  mode, fails in non-interactive mode.
- [ ] AC-5: All resolution paths are event-logged.

## References

- PRD-617: `fast_forward_branch` builtin (prerequisite).

## Assessment (2026-04-11)

- **Value**: 2/5 — speculative. The PRD itself says "deferred until we
  see whether `fast_forward_branch`'s strict failure mode causes
  frequent friction in practice." No incident driving it yet.
- **Effort**: m as scoped — interactive prompts, rebase/merge/force-reset
  paths, event logging, non-TTY fallback. But it's largely composition
  of already-existing primitives.
- **Current state**: greenfield. `fast_forward_branch` exists
  (`builtins/fast_forward_branch.py`), `sync_branch` does not.
- **Gaps**: the whole PRD.
- **Recommendation**: defer — keep the PRD as a design-in-waiting.
  Only schedule after at least three documented incidents where
  `fast_forward_branch`'s strict failure caused user friction.
