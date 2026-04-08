---
id: "PRD-221"
title: "Workflow owns format + typecheck so agents don't loop on them"
kind: task
status: ready
priority: high
effort: xs
capability: simple
parent: null
depends_on: []
blocks: []
impacts:
  - justfile
  - workflows/default/workflow.py
  - workflows/default/prompts/task.md
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - workflow
  - dx
---

# Workflow owns format + typecheck so agents don't loop on them

## Summary

Two consecutive dogfood runs (PRD-216 and PRD-218) hit the 600s agent timeout *after* the agent had correctly implemented the task. Root cause in both cases: the agent got stuck in an iterative verification loop trying to satisfy mechanical checks (ruff format, mypy) that don't require creative reasoning to fix. Each iteration cycle is slow (30s+), and 20 iterations can eat the whole budget.

The fix is to **move mechanical checks into the workflow itself** so the harness runs them, the agent never sees them, and the agent's only job is implementation correctness. Specifically:

1. Add a `just format` recipe (the auto-fix variant) and a `just typecheck` recipe.
2. Insert a `format` ShellTask into the default workflow that runs `just format` BEFORE the lint check (so drift is fixed automatically).
3. Insert a `typecheck` ShellTask that runs `just typecheck` AFTER the lint check.
4. Update `task.md` to tell the agent "don't run format/typecheck — the harness handles them; just make sure tests pass and the code is logically correct."

The net effect: the agent implements, the harness auto-formats + type-checks, and the agent is only asked to re-engage if something fundamental broke (tests failing, real mypy errors the agent introduced, etc.).

## Motivation

### What we observed

| | PRD-216 | PRD-218 |
|---|---|---|
| Agent implemented correctly | ✓ | ✓ |
| Tests passing | ✓ | ✓ |
| Ruff check | ✓ | ✓ |
| Ruff format-check | ✗ (drift) → eventually ✓ | ✓ (converged) |
| Mypy strict | n/a (not in workflow) | ✗ (1 untyped test helper) |
| **Final result** | 600s timeout, work staged | 600s timeout, work staged |

Both runs made it past the creative work and then spun until the deadline on mechanical cleanup. Neither agent was actually stuck in a reasoning dead-end — they were running `just lint format-check` → editing → re-running, over and over, because:

- `format-check` is a *check*, not a *fix*. The agent can't call `ruff format` directly (not in its tool allowlist) so it hand-edits files to match ruff's output, which is a slow, error-prone way to do what ruff would do in 50ms.
- Mypy errors on new test helpers are a predictable class of issue the agent can fix but takes several iterations to converge on (add annotation → re-run → mypy points at the next thing → re-run → …).

### Why move these into the workflow

**Format is mechanical.** There is exactly one correct output for any given input file. Having a reasoning model iterate on "apply ruff's opinions" is a category error — it's the thing computers are for. The workflow should call `ruff format` as a deterministic step, not ask the agent to mimic it.

**Typecheck is mostly mechanical.** The interesting typecheck failures (actual type bugs) *should* surface to the agent — those represent real logic errors. The uninteresting ones (forgot to annotate a new test helper) are the majority and can be auto-fixed by the agent or just surfaced as a clear error message on the retry. Running mypy in the workflow means failures surface uniformly and the agent sees them at the right time.

### Why this unblocks dogfood

Once this lands, the agent's verification loop has three possible outcomes:

1. **Tests pass + no mypy errors.** Done. Harness commits, pushes, PRs.
2. **Tests fail.** Retry with the agent. This is a real logic issue worth reasoning about.
3. **Mypy fails.** Retry with the agent, with a clear error message. Usually a one-edit fix.

The "spin on format" outcome disappears entirely.

## Requirements

1. `justfile` gains a `format` recipe: `uv run ruff format src tests workflows`.
2. `justfile` gains a `typecheck` recipe: `uv run mypy src tests workflows`. (This recipe already exists in the darkfactory justfile — verify and keep.)
3. Default workflow inserts a `ShellTask("format", cmd="just format", on_failure="fail")` between the `test` and `lint` steps. `on_failure="fail"` because ruff format can't fail in practice — if it does, something is deeply wrong.
4. Default workflow inserts a `ShellTask("typecheck", cmd="just typecheck", on_failure="retry_agent")` after `lint`. Retry-agent because real mypy failures are worth having the agent fix.
5. The existing `lint` step stays — it runs `ruff check` (the non-format lint rules) and `format-check` as a sanity check. After `just format` ran, `format-check` should always pass, making it a no-op guard.
6. `workflows/default/prompts/task.md` updates its "step 3 run tests and lint" section to tell the agent:
   - Run `just test` to confirm tests pass
   - **Do NOT run format-check, ruff format, or mypy.** The harness handles these.
   - If the harness comes back to you with a mypy failure, fix just that one issue.
7. All 246 existing tests continue to pass.

## Technical Approach

### `justfile` additions

```
format:
    uv run ruff format src tests workflows

typecheck:
    uv run mypy src tests workflows
```

The typecheck recipe may already exist; if so, leave it alone.

### Workflow changes

`workflows/default/workflow.py`:

```python
# ----- verification phase -----
ShellTask("test", cmd="just test", on_failure="retry_agent"),
ShellTask("format", cmd="just format", on_failure="fail"),           # NEW
ShellTask("lint", cmd="just lint format-check", on_failure="retry_agent"),
ShellTask("typecheck", cmd="just typecheck", on_failure="retry_agent"),  # NEW
# ----- teardown phase -----
BuiltIn("set_status", kwargs={"to": "review"}),
BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} ready for review"}),
...
```

Note the order: `test → format → lint → typecheck`. Format runs before lint so lint never sees format drift. Typecheck runs last so any test-file type issues introduced by the agent's edits to tests get caught in the same pass as other type issues.

### `task.md` changes

Replace the current step 3 ("Run tests and lint") with:

```markdown
### 3. Run tests

Run the tests to make sure your changes don't break anything:

\`\`\`bash
just test
\`\`\`

Fix any failing tests. If tests that were passing before start failing, you
broke something — investigate and fix, don't paper over.

**Do not run these tools yourself:**
- \`ruff format\` or \`just format-check\` — the harness auto-formats after
  you finish, so formatting drift is not your concern.
- \`mypy\` or \`just typecheck\` — the harness runs mypy after formatting. If
  mypy flags a real type bug, the harness will bring you back with the error
  message; fix that one thing and return.

The harness handles format and typecheck deterministically so you can focus
on logic correctness.
```

### Rollout

- Merge PR #10 (PRD-218 streaming) first so the next run actually shows progress.
- Then implement this PRD (PRD-221) either manually or via the harness. It's a 4-line justfile + ~6-line workflow change + prompt rewrite. Trivially small.
- Run PRD-216's own helper (`prd normalize --all`) as a bonus sanity pass since that lands in the same window.

## Acceptance Criteria

- [ ] AC-1: `just format` recipe exists and runs `uv run ruff format src tests workflows`.
- [ ] AC-2: `just typecheck` recipe exists and runs `uv run mypy src tests workflows`.
- [ ] AC-3: Default workflow task list contains `ShellTask("format", ...)` between `test` and `lint`.
- [ ] AC-4: Default workflow task list contains `ShellTask("typecheck", ...)` after `lint`.
- [ ] AC-5: `prd plan PRD-X` on any ready PRD shows the expanded task list including format and typecheck steps.
- [ ] AC-6: `task.md` tells the agent not to run format, format-check, or mypy itself.
- [ ] AC-7: A dogfood run of any small PRD (e.g. re-running PRD-221 itself once it's drafted as a verification target, or the next queued PRD) completes without hitting the agent timeout because the verification phase is now deterministic.
- [ ] AC-8: Running this PRD through the harness is the real AC — the fix is validated by its own first clean run.

## Open Questions

- [ ] Should `typecheck` be `on_failure="retry_agent"` or `on_failure="fail"`? If we trust the agent to fix its own type errors, retry_agent. If we want type errors to be a hard stop (forcing a human to intervene), fail. Recommendation: retry_agent for now — the most common case is "agent forgot a type annotation on a new test helper", which is fixable.
- [ ] Should the agent still READ mypy output during implementation, even if it doesn't RUN mypy? Arguably yes, so they catch their own type mistakes early. But adding `Bash(mypy:*)` to the tool allowlist re-opens the loop we're closing. Recommendation: don't add mypy to the allowlist; rely on the workflow step.
- [ ] Should we add a `just check` meta-recipe that runs test + format + lint + typecheck in sequence, for local human use? Nice to have, out of scope here.

## References

- PRD-216 timeout post-mortem: `src/darkfactory/prd.py` + `cli.py` done, stuck on format drift in tests
- PRD-218 timeout post-mortem: `src/darkfactory/invoke.py` + tests done, stuck on one mypy type annotation
- [[PRD-218-stream-agent-output]] — streaming helps diagnose the loop; this PRD prevents it
- Workflow architecture: `workflows/default/workflow.py` tasks list
