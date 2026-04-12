---
id: PRD-619
title: decouple reply_pr_comments from push success
kind: task
status: draft
priority: medium
effort: s
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - src/darkfactory/workflows/rework/workflow.py
  - src/darkfactory/runner.py
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-11'
updated: '2026-04-11'
tags: []
---

# decouple reply_pr_comments from push success

## Summary

Ensure `reply_pr_comments` runs even when `push_branch` fails, so
that agent-generated review replies are not silently discarded by
an unrelated push failure.

## Motivation

The rework workflow's task list is executed sequentially by the
runner (`runner.py:242-245`), which halts on the first failing
task. The current task order is roughly:

1. fetch_pr_comments
2. agent invocation
3. format / lint / test / typecheck
4. commit
5. push_branch
6. reply_pr_comments

If `push_branch` fails (network issue, auth problem, protected
branch rule, stale branch), the runner breaks out of the loop and
`reply_pr_comments` never executes. The agent's reply notes —
which may represent significant analysis work — are discarded.

PRD-617 addresses the most common cause (stale branch) by
fast-forwarding before the run. But push can fail for other
reasons: transient network errors, GitHub rate limits, branch
protection changes, etc. In those cases the reply notes are still
lost.

`reply_pr_comments` is a GitHub API operation that doesn't depend
on the push succeeding — the comments reference existing PR review
threads, not the newly pushed code. It should run regardless of
push outcome.

## Requirements

### Functional

1. `reply_pr_comments` executes even if `push_branch` fails.
2. If both `push_branch` and `reply_pr_comments` fail, both
   failures are reported clearly (not just the first one).
3. The overall workflow still reports failure if `push_branch`
   failed — we're not suppressing the error, just decoupling
   the downstream task.
4. Event log captures both task outcomes independently.

### Non-Functional

1. Minimal change to the runner — prefer workflow-level
   configuration over runner architecture changes.
2. The solution should be general enough to support other
   "run-even-on-failure" tasks in the future, but the
   implementation only needs to handle the rework case now.

## Technical Approach

Options to evaluate:

**Option A: Task-level `continue_on_upstream_failure` flag.**
Add an optional flag to `BuiltIn` / task definitions that tells
the runner "run this task even if a previous task failed." The
runner tracks failure state but continues executing flagged tasks.
`reply_pr_comments` gets this flag.

**Option B: Workflow-level `finally` block.**
Allow workflows to declare tasks that always run, similar to
try/finally. The runner executes the main task list, then
unconditionally runs the finally tasks. `reply_pr_comments` moves
to the finally block.

**Option C: Group tasks into phases.**
Group push_branch and reply_pr_comments as independent tasks that
both depend on commit, rather than reply depending on push.
Requires the runner to understand DAG dependencies rather than
linear execution.

Recommendation: Option A is simplest and sufficient. Option C is
more correct architecturally but is a larger change (see PRD-551
parallel graph execution).

## Acceptance Criteria

- [ ] AC-1: `reply_pr_comments` runs and posts replies even when
  `push_branch` fails.
- [ ] AC-2: Workflow overall status reflects the push failure.
- [ ] AC-3: Event log has independent task_start/task_finish
  entries for both push_branch and reply_pr_comments.
- [ ] AC-4: When both succeed, behavior is unchanged from today.

## Open Questions

- OPEN: Should this be Option A (task flag) or Option B (finally
  block)? Option A is simpler; Option B is more explicit about
  intent. Leaning toward A for now.
- OPEN: Are there other tasks in other workflows that would benefit
  from this pattern? If so, that might tip the scale toward Option
  B for clarity.

## References

- PRD-617: `fast_forward_branch` — addresses the root cause of
  the most common push failure.
- `src/darkfactory/runner.py:242-245`: halt-on-failure loop.
- `src/darkfactory/workflows/rework/workflow.py`: current task
  order.
- PRD-551: parallel graph execution — the full DAG-based
  approach that would subsume this fix.

## Assessment (2026-04-11)

- **Value**: 4/5 — the concrete failure is "agent analysis work
  silently discarded when push fails for an unrelated reason." Every
  rework session is exposed. A transient network hiccup throws away
  minutes of expensive agent work.
- **Effort**: xs — Option A is a new `continue_on_upstream_failure`
  flag on the task type + ~10 lines in the runner's halt-on-failure
  loop. Probably 1 hour of work including tests.
- **Current state**: greenfield. `runner.py:242-245` is a linear halt
  loop with no way to flag a task as "run anyway."
- **Gaps to fully implement**:
  - Add `continue_on_upstream_failure: bool = False` to `BuiltIn` /
    task dataclasses in `workflow.py`.
  - Runner: track a `failure_seen` flag; still execute tasks flagged
    with `continue_on_upstream_failure=True` regardless; report
    aggregate failure at the end.
  - Update `workflows/rework/workflow.py` to set the flag on
    `reply_pr_comments`.
  - Event log: ensure both tasks emit independent
    `task_start`/`task_finish` events.
- **Recommendation**: do-now — pairs naturally with PRD-543 as a
  single "rework reliability" PR. Don't wait for Option B
  (finally-block workflow syntax) — Option A is sufficient for the
  real case.
