# Value vs. Effort — assessment summary (2026-04-11)

Scope: every non-closed PRD in `.darkfactory/data/prds/` except PRD-622 (merged)
and PRD-626 (handled separately). That's **87 PRDs** across 5 statuses:

| Status | Count | Notes |
|--------|-------|-------|
| draft | 73 | Core of the backlog — where most decisions live. |
| blocked | 4 | All four are quality follow-ups from prior PRs. |
| review | 5 | Close-out candidates. |
| ready | 3 | Runnable now (excluding PRD-626). |
| in-progress | 2 | Both are epics with only close-out tasks remaining. |

Method: read each PRD, cross-reference against current code state (surveyed
via a parallel exploration pass), and record `Value`, `Effort`, `Current
state`, `Gaps`, and `Recommendation` inline on each PRD. See `RUBRIC.md` for
the scales.

See `STATE-SURVEY.md` for the current-code snapshot this pass was built on.

---

## Headline findings

### 1. Four PRDs are already delivered — flip to `superseded` / `done`

| PRD | Why | Action |
|-----|-----|--------|
| **PRD-556** (cli modularization, `in-progress`) | The research survey confirms `src/darkfactory/cli.py` stub is gone and every command lives in its own submodule. PRD-556.18 is just a sanity-check pass. | Flip 556 epic to `done` once 556.18 lands. |
| **PRD-563** (drain-ready-queue, `in-progress`) | All 5 children are in `done`. The epic's in-progress status is purely stale. | Flip to `done`. |
| **PRD-559.4** (analyze_transcript builtin, `review`) | `src/darkfactory/builtins/analyze_transcript.py` exists and is imported in `builtins/__init__.py`. | Flip to `done`. |
| **PRD-559.5** (workflow integration, `ready`) | Research confirms `analyze_transcript` is wired into the planning workflow. Likely already applied to default + extraction too. | Verify all three, then flip to `done`. |

### 2. One PRD turned out to be moot during the review

| PRD | Why it's moot | Action |
|-----|---------------|--------|
| **PRD-601** (yaml date quoting, `blocked`) | PRD-622's deterministic serializer quotes the `created`/`updated` date fields by construction. Every PRD file in the repo is already quoted. | Supersede (drift, not a real gap). |

**Correction note:** An earlier version of this summary claimed PRD-600.1.2
(shell-escape `format_string`) was moot because `shell=True` was absent from
`src/`. That was a research-pass grep miss. `runner.py:593` and
`system_runner.py:367` both use `shell=True`, and `runner.py:472` interpolates
user-controlled PRD title into that command via `ctx.format_string(task.cmd)`.
The injection surface is real; PRD-600.1.2 stays in the Phase 1 safety batch.

### 3. PRD-621 is *partially* landed (not fully, despite status `ready`)

`src/darkfactory/utils/` exists as a flat-file package (`git.py`, `system.py`,
`terminal.py`, `secrets.py`, `tui.py`, `claude_code.py`). The target layout
from PRD-621 is a **package-per-domain** (`utils/git/`, `utils/github/`,
`utils/claude_code/`) plus `utils/shell.py` extraction. None of the package
nesting, the `utils/github/` split, or the `_run_shell_once` deduplication is
done. Effort dropped from `m` → `s` because the scaffolding is already there.

### 4. The true "do-now" quick wins

PRDs where value is clearly ≥4 *and* effort is `xs` or `s` given current code:

| PRD | Why it earns do-now |
|-----|---------------------|
| **PRD-543** (harness `create_pr` hardening) | `s` effort, prevents the exact "opaque `returned non-zero exit status 1`" failure that burns debugging sessions. Also adds the re-run-merged-PRD guard that saves a full agent run. |
| **PRD-554** (planning workflow prompt hardening) | `s` effort, directly fixes the 600-second timeout loop from 2026-04-08. Every planning run benefits. |
| **PRD-600.1.1** (reconcile crash recovery) | `xs` effort, closes a real data-loss path (repo stranded on wrong branch mid-reconcile). |
| **PRD-600.1.3** (remove `setattr` side channel) | `xs` effort, removes a type-safety bypass using already-existing typed field. |
| **PRD-600.1.4** (ruff in CI) | `xs` effort, single highest-impact DevOps change. Ruff is already in dev deps, just needs a CI step. |
| **PRD-600.2.3** (`--version` flag) | `xs` effort, bug-report ergonomics. One-line `argparse` change. |
| **PRD-600.2.5** (Python 3.13 matrix) | `xs` effort, ~4 YAML lines. |
| **PRD-600.3.5** (`cleanup --yes` flag) | `xs` effort, unblocks scripted cleanup. |
| **PRD-619** (decouple `reply_pr_comments` from push success) | `xs`–`s`, prevents silent loss of agent review replies. |

Run these in a single batch — they're independent and total about one focused day.

### 5. The true "drop or drastically rescope" candidates

| PRD | Why | Recommendation |
|-----|-----|----------------|
| **PRD-226** (event-sourced status) | Deliberately deferred by its own author until PRD-224 has been in use "for a few weeks." The patch-based fixes it would replace are all landed; no user pain forcing the rewrite. | **defer** — revisit Q3 if drift still happens. |
| **PRD-609** (retry/recovery expansion) | Author flagged as "rough draft / braindump." No AC list. No concrete incident driving it. | **defer** — re-score after PRD-608 lands, keep as idea capture. |
| **PRD-610** (agent SDLC substitution) | Author self-flags as "not yet validated as valuable." Value: 2. | **defer** — do not schedule until at least one concrete failure demands it. |
| **PRD-611** (conditional SDLC checks) | Same posture. Value: 2. | **defer**. |
| **PRD-612** (agent-assisted detection) | Same posture. Small effort but no driving pain. | **defer**. |
| **PRD-613** (model fallback / multi-provider) | Interesting but value 2, effort m. Current hardcoded `CAPABILITY_MODELS` is working fine. Phase 1 (wire existing config) is a quick win worth pulling out; phases 2–3 are speculative. | **split** — pull Phase 1 to a separate xs/s PRD, defer phases 2–3. |

### 6. The concurrency / scheduling cluster needs one merged plan

Seven PRDs all sit in the same design space:

- **PRD-545** (harness-driven rebase + conflict resolution)
- **PRD-546** (impact declaration drift detection)
- **PRD-547** (cross-epic scheduler coordination)
- **PRD-550** (upstream impact propagation)
- **PRD-551** (parallel graph execution)
- **PRD-552** (merge-upstream task)
- **PRD-558** (auto-serialize sibling conflicts)

They overlap substantially on "use `impacts:` metadata to order or parallelize
execution" and each one touches `impacts.py`, `graph_execution.py`, and the
runner. None is independently coherent without knowing how the others land.

**Recommendation:** treat PRD-558 Option 1 (auto-inject phantom `depends_on`)
as the MVP that unblocks the 18-way PRD-556 fan-out without committing to any
of the larger pieces. Then re-plan the rest of the cluster in a single
cross-PRD design session once that lands — several of them can probably
supersede each other.

### 7. The onboarding/init cluster is another merge candidate

- **PRD-561** (skill to discuss/create PRDs)
- **PRD-562** (skill to triage drafts)
- **PRD-564** (interactive init with path overrides)
- **PRD-607** (work item discovery)
- **PRD-608** (toolchain setup wizard)

Each is standalone but they all touch `prd init` or adjacent surface. 564 and
608 in particular both want to own the init flow. **Recommendation:** if any
of them land, sequence 564 first (smallest scope, backfills the config shape
the others need), then 608, then 607. 561 and 562 are orthogonal Claude Code
skills that don't need to wait.

---

## Quick-reference: full PRD table

The full per-PRD table is in `TABLE.md`, sorted by `(value desc, effort asc)`.
Summary clusters with counts below.

| Cluster | PRDs | Do-now | Defer/drop |
|---------|------|--------|------------|
| Already landed (flip status) | PRD-556, 559.4, 559.5, 563, 600.1.2, 601 | — | supersede all |
| Safety quick wins (PRD-600.1) | 600.1.1, 600.1.3, 600.1.4 (+ 600.1.2 moot) | 3 | — |
| Tooling quick wins (PRD-600.2) | 600.2.1–7 | 4 | 1 (600.2.4 superseded) |
| Operational quick wins (PRD-600.3) | 600.3.1–9 | 5 | — |
| Frontend optionality (PRD-600.4) | 600.4.1–4 | 0 | defer (depends on 556 which is ~done) |
| Workflow reliability (PRD-567) | 567.1–6 + 7 leaves | 4 | 2 |
| PR / reliability hardening | 543, 619 | 2 | — |
| Planning workflow | 229, 554 | 1 | 1 (229 blocked) |
| Scheduling/parallel cluster | 545, 546, 547, 550, 551, 552, 558 | 1 (558 only) | rest defer until re-planned |
| Modularization close-out | 556.18, 557, 605 | 1 (556.18) | 2 |
| Onboarding / init | 561, 562, 564, 607, 608 | 0 | sequence 564→608→607, 561/562 orthogonal |
| Sub-features of 608 | 610, 611, 612, 613 | 0 | 3 defer, 613 split |
| Standalone small tasks | 225.7, 540, 553, 570, 618 | 1 (570) | 2 |
| Event-sourced status | 226 | 0 | 1 defer |
| Retry/recovery | 609 | 0 | 1 defer |
| Docs | 602 | 1 | — |
| Analysis robustness | 603, 604 | 2 | — |
| Post-modularization cleanup | 605 | 1 | — |

---

## What I'd schedule first (5–10 focused days)

A concrete proposed sequence for the next sprint. Each block is independent
and can ship as its own PR unless noted.

### Block A — Supersede sweep (half-day)

Flip stale PRDs so the backlog matches reality:
- PRD-556 → `done` (gate on 556.18 landing)
- PRD-563 → `done`
- PRD-559.4 → `done`
- PRD-559.5 → `done` (after verifying default + extraction workflows also have analyze_transcript)
- PRD-600.1.2 → `superseded` (shell=True gone)
- PRD-601 → `superseded` (deterministic serializer already quotes dates)
- PRD-600.2.4 → `superseded` (hatch.version already single-sources)

### Block B — Safety quick wins (one day, one PR or four tiny PRs)

- PRD-600.1.1 reconcile crash recovery
- PRD-600.1.3 remove setattr side channel
- PRD-600.1.4 ruff in CI

### Block C — CI / tooling quick wins (one day)

- PRD-600.1.4 (already in Block B)
- PRD-600.2.1 configure ruff rules
- PRD-600.2.2 pytest-cov
- PRD-600.2.3 `--version` flag
- PRD-600.2.5 Python 3.13 matrix
- PRD-600.2.7 delete dead cli.py stub (already done — confirm)

### Block D — CLI ergonomics (one day)

- PRD-600.3.2 `validate --json`
- PRD-600.3.3 `tree --json`
- PRD-600.3.5 `cleanup --yes`
- PRD-600.3.6 help text examples (top 5 commands)
- PRD-600.3.7 `prd show` command

### Block E — Harness reliability (1–2 days)

- PRD-543 harden create_pr + refuse merged re-runs
- PRD-619 decouple reply_pr_comments from push success
- PRD-554 planning workflow prompt hardening
- PRD-567.1 worktree lifecycle resilience (pick the critical .1.1 + .1.2)
- PRD-567.2 permission hygiene (the two leaves)

### Block F — Modularization close-out (half-day)

- PRD-556.18 final cleanup
- PRD-605 post-modularization cleanup
- Merge SUPERSEDE sweep above

### Block G — Parallel-execution spike (2–3 days, research-level)

Pick one of:
- PRD-558 Option 1 (auto-serialize siblings) — MVP fan-out win, no other deps
- PRD-621 (utils refactor) — pure maintenance, unblocks 600.3.1 and 600.4 family

I'd go with PRD-558 if the next big epic is another 10-way fan-out; otherwise
PRD-621 gives more long-term leverage.

---

## Inputs to this assessment

- Every PRD markdown file under `.darkfactory/data/prds/PRD-*.md`
- The state survey in `STATE-SURVEY.md` (captured 2026-04-11 against
  `origin/main` at `b976797`)
- `RUBRIC.md` in this directory

## Disclaimer

This is a snapshot of current priority, not a contract. The bottom 20 PRDs in
the defer pile should be re-scored whenever anyone feels like picking them up
— the bar for "is this still worth tracking" is worth asking every few weeks.
