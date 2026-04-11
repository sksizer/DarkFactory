---
id: PRD-617
title: sync worktree branch before rework
kind: task
status: review
priority: medium
effort: m
capability: simple
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/workflows/rework/workflow.py
  - src/darkfactory/builtins/
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-11
updated: '2026-04-11'
tags: []
---

# sync worktree branch before rework

## Summary

Add a pre-flight step that (1) fast-forwards the rework worktree's
branch to match its own origin, and (2) rebases the branch onto
`origin/main` so it incorporates mainline changes. This ensures
`push_branch` at the end of the workflow doesn't get rejected by a
diverged remote, and the PR branch isn't stale relative to main
when it comes time to merge.

## Motivation

**Observed failure** (PRD-616 rework, event log
`PRD-616-20260411T130733.jsonl`, 2026-04-11 13:13):

1. Agent ran fine, produced a valid `json-reply-notes` block with
   12+ replies to address.
2. Format / lint / test / typecheck all passed.
3. `commit` succeeded (SHA ae5b27a).
4. `push_branch` was rejected: `! [rejected] prd/PRD-616-...
   (fetch first)` — remote had commits the worktree didn't.
5. Runner halts on first failing task (`runner.py:242-245`
   `if not step.success: ... break`), so `reply_pr_comments` never
   ran. The agent's reply notes were discarded.

Root cause: rework assumes the worktree's local branch is
up-to-date with origin at the time the workflow starts. That's only
true if nothing has pushed to the branch since the worktree was
created. In practice that assumption breaks whenever:

- A previous rework cycle pushed commits that the local worktree
  hasn't fetched.
- `rework-watch` or another harness process pushed on the same
  branch.
- A human pushed a direct edit from another checkout.
- CI/bots (Copilot review, autofix tools) committed via the GitHub
  UI/API.

Any of these silently turn a rework run into wasted work: the
commit is created locally but the push fails, so the PR never gets
the fix *or* the reply notes.

**Second problem — stale relative to main**: even when the push
succeeds, the PR branch may be many commits behind main. The agent
works against outdated code, potentially re-introducing patterns
that main has already moved past, or creating merge conflicts that
block the PR from merging. Rebasing onto main before the agent
runs means the agent always sees the current state of the codebase.

Who benefits: anyone running `prd rework` on a PR that's been
touched by anything other than their own most recent rework, or
on a PR whose base branch has advanced since the branch was created.

## Requirements

### Functional

1. Before any rework task runs that could mutate files, the
   worktree's local branch is fast-forwarded to match
   `origin/<branch>`.
2. After fast-forwarding, the branch is rebased onto
   `origin/main` (or the configured base branch) so it
   incorporates mainline changes.
3. If the fast-forward is not possible (local has commits not on
   origin, or there is a merge conflict), the workflow halts loudly
   with a clear error naming the branch and suggesting manual
   intervention. No silent force-reset.
4. If the rebase onto main produces conflicts, the workflow halts
   loudly with a clear error listing the conflicting files and
   suggesting manual intervention. The rebase is aborted cleanly
   (`git rebase --abort`) so the worktree is left in its
   pre-rebase state.
5. The step runs inside the worktree (uses the worktree's HEAD and
   remotes, not the main repo root).
6. The step is visible in the event log as its own `task_start` /
   `task_finish` with enough detail to tell whether it was a no-op
   ("already up to date") or an actual fast-forward/rebase
   (source SHA → target SHA).
7. The step fails the run early — before the expensive agent
   invocation — so a diverged branch wastes minutes, not the full
   rework cycle.

### Non-Functional

1. Two targeted fetches: `git fetch origin <branch>` and
   `git fetch origin main` (not a full `git fetch --all`).
2. Both fetches use a configurable timeout (default 30s) to avoid
   blocking indefinitely on slow or unresponsive remotes.
3. No new dependencies; use the existing `git_ops` module /
   subprocess pattern the rest of the harness uses.
4. Must work in both the rework workflow and (eventually) any
   other workflow that runs against an existing worktree — design
   the builtin to be reusable.

## Technical Approach

Two separate builtins, each with a single responsibility. Shared
git plumbing (fetch + rev-list divergence check) lives in a small
helper both import.

### Builtin 1: `fast_forward_branch`

`src/darkfactory/builtins/fast_forward_branch.py`

Fast-forwards the worktree's local branch to match its own
`origin/<branch>`. Solves the "push rejected" problem.

Steps:
1. Resolve `ctx.cwd` (the worktree path) and `ctx.branch_name`.
   We trust `ctx.branch_name` as the source of truth — it is set
   by the CLI layer which owns the worktree lifecycle. We do NOT
   read HEAD from the worktree to cross-check; if someone manually
   switched branches in a harness-managed worktree, that's user
   error outside our contract.
2. Run `git fetch origin <branch>` in `cwd` (with a configurable
   timeout, default 30s, to avoid hanging on slow remotes).
   - If the remote ref does not exist (fetch exits non-zero with
     "couldn't find remote ref"), treat as already up-to-date:
     there is nothing on origin to sync to. This covers the case
     where a previous `push_branch` failed and the remote branch
     was never created.
   - Any other fetch failure → raise with the git stderr.
3. Check divergence with `git rev-list --left-right --count
   HEAD...origin/<branch>`.
   - If `origin/<branch>` ref doesn't exist locally (because
     step 2 treated a missing remote as up-to-date), skip
     divergence check — we're already up-to-date by definition.
   - `0 0` → already up-to-date, no-op, emit `builtin_effect`
     with `effect="sync"`, `result="up_to_date"`.
   - `0 N` (N>0) → local is strictly behind; fast-forward via
     `git merge --ff-only origin/<branch>`; emit `effect="sync"`,
     `result="fast_forward"`, `from_sha=<old>`, `to_sha=<new>`,
     `commits=N`.
   - `M 0` (M>0) → local has commits origin doesn't; **fail
     loudly** with a message describing the state: "local branch
     <branch> is M commits ahead of origin — this usually means
     a previous push failed; investigate and resolve manually."
   - `M N` (both>0) → genuine divergence; fail loudly with:
     "local branch <branch> has diverged from origin (M ahead,
     N behind) — investigate and resolve manually."
4. Raise on any other git subprocess failure.

### Builtin 2: `rebase_onto_main`

`src/darkfactory/builtins/rebase_onto_main.py`

Rebases the worktree's branch onto `origin/main` so the agent
works against current mainline code. Solves the "stale branch"
problem.

Steps:
1. Resolve `ctx.cwd` and determine the base branch (default
   `main`, configurable if needed later).
2. Run `git fetch origin main` in `cwd` (with configurable
   timeout, default 30s).
3. Check if already up-to-date via
   `git merge-base --is-ancestor origin/main HEAD`.
   - If yes → no-op, emit `builtin_effect` with
     `result="up_to_date"`.
   - If no → run `git rebase origin/main`.
     - On success: emit `builtin_effect` with
       `result="rebased"`, `from_sha=<old>`, `to_sha=<new>`,
       `onto_sha=<main_sha>`.
     - On conflict: run `git rebase --abort` to restore clean
       state, then fail loudly listing the conflicting files.
4. Raise on any git subprocess failure.

### Workflow change

Add both builtins as the first two tasks in
`src/darkfactory/workflows/rework/workflow.py`, before
`fetch_pr_comments`:

```python
BuiltIn("fast_forward_branch"),
BuiltIn("rebase_onto_main"),
```

Placing them first means divergence / staleness is caught before
the expensive agent invocation, not after. Note that
`fetch_pr_comments` (which follows) is a GitHub API call that
doesn't mutate the worktree — the ordering is about failing fast
on git state issues, not about protecting `fetch_pr_comments`.

### Tests

**`src/darkfactory/builtins/fast_forward_branch_test.py`:**
- happy path: behind-by-N → fast-forward succeeds, emits
  `builtin_effect` with `from`/`to` shas
- no-op: HEAD already at origin → emits `result: up_to_date`, no
  merge performed
- remote branch missing: fetch fails with "couldn't find remote
  ref" → treated as up-to-date, no divergence check
- local-ahead: unpushed local commit → raises with a message that
  mentions the branch and the ahead count
- true divergence: both ahead and behind → raises
- fetch failure (non-missing-ref): `git fetch` non-zero for other
  reasons (network, auth) → raises with git stderr
- fetch timeout: fetch exceeds timeout → raises
- event writer is None: builtin still works, just skips emission

**`src/darkfactory/builtins/rebase_onto_main_test.py`:**
- happy path: branch behind main → rebase succeeds, emits
  `builtin_effect` with `from`/`to`/`onto` shas
- no-op: branch already contains main HEAD → emits
  `result: up_to_date`
- conflict: rebase produces conflicts → aborts rebase cleanly,
  raises with conflicting file list
- fetch main failure (network/auth): `git fetch origin main`
  non-zero → raises with git stderr
- fetch main timeout: fetch exceeds timeout → raises
- event writer is None: builtin still works, just skips emission

All tests mock `subprocess.run` against a fixture repo — no real
network.

## Acceptance Criteria

- [ ] AC-1: New builtin `fast_forward_branch` registered and
  importable; peer test file covers all ff cases + no-emitter.
- [ ] AC-2: New builtin `rebase_onto_main` registered and
  importable; peer test file covers all rebase cases + no-emitter.
- [ ] AC-3: `workflows/rework/workflow.py` has
  `BuiltIn("fast_forward_branch")` then `BuiltIn("rebase_onto_main")`
  as its first two tasks.
- [ ] AC-4: Running `prd rework PRD-X --execute` on a PR whose
  branch is *behind* origin fast-forwards the worktree, rebases
  onto main, continues normally, and the event log shows
  `task_start`/`task_finish` for both builtins plus their
  respective `builtin_effect` entries.
- [ ] AC-5: Running on a PR whose branch has *local commits not
  on origin* fails at `fast_forward_branch` before the agent runs,
  with an error message naming the branch and the ahead count.
- [ ] AC-6: Running on a PR that's already in sync with both its
  own origin and main emits `builtin_effect` entries with
  `result: up_to_date` and `rebase: up_to_date`.
- [ ] AC-7: Running on a PR whose branch conflicts with main
  fails at `rebase_onto_main`, aborts the rebase cleanly, leaves
  the worktree in its pre-rebase state, and fails with an error
  listing conflicting files.
- [ ] AC-8 (manual validation, not CI-automatable): Re-running the
  PRD-616 scenario (the one from the motivation) with this change
  in place: the rework workflow completes all tasks including
  `reply_pr_comments`, and the reply POSTs actually land on the
  PR (assuming PR #164's databaseId fix is in).

## Resolved Decisions

- **Two builtins, not one**: `fast_forward_branch` and
  `rebase_onto_main` are separate because they have different
  failure semantics (ff failure = "you have unpushed work" vs
  rebase conflict = "your changes clash with main"). Shared git
  plumbing extracted into a helper. A future interactive
  `sync_branch` builtin can handle non-ff cases if the need
  arises (see PRD-618).
- **Scope**: rework workflow only for now. The builtin is reusable
  by design; adding to other workflows is a one-line change later.
- **Local ahead of origin**: strict — fail loudly. The harness
  should never have unpushed local commits; that indicates a bug in
  a previous run. Making the human decide is correct per "hard
  failures over silent degradation."
- **`reply_pr_comments` skip on push failure**: out of scope.
  Tracked separately in PRD-619.
- **Network failure**: if `git fetch` fails due to network issues,
  display a clear error in the console. The task is event-logged
  (task_start/task_finish with failure detail) but the workflow
  halts — we can't fast-forward without a fetch.

## Open Questions

None remaining.

## References

- PRD #164 (merged): `fix(pr_comments): use REST databaseId for
  comment replies` — the reply code that was never exercised
  end-to-end because of this bug.
- Event log:
  `.darkfactory/events/PRD-616-20260411T130733.jsonl` — the
  specific run that surfaced the issue; shows the halt-after-push
  behavior.
- `src/darkfactory/runner.py:242-245` — the halt-on-failure loop
  exit that turns any mid-workflow failure into a silent skip of
  downstream tasks.
- `src/darkfactory/workflows/rework/workflow.py` — current task
  order.
- CLAUDE.md "Architectural Principles": parse at the boundary,
  hard failures over silent degradation — this PRD applies both.
