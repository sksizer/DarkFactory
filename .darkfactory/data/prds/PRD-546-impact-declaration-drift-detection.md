---
id: PRD-546
title: Detect drift between declared impacts and actual diff after PRD merges
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-545-harness-driven-rebase-and-conflict-resolution]]"
impacts:
  - src/darkfactory/impacts.py
  - src/darkfactory/runner.py
  - src/darkfactory/cli/**
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-11'
tags:
  - harness
  - reliability
  - scheduler
  - feature
---

# Detect drift between declared impacts and actual diff after PRD merges

## Summary

Every PRD declares an `impacts:` list of glob patterns describing the files it intends to change. The harness uses those globs as the source of truth for static conflict detection (`prd conflicts`) and — once PRD-545 lands — for *scheduling* parallel sibling execution. This means that **if a PRD lies about its impacts, the scheduler underestimates conflicts and parallel siblings collide unexpectedly at rebase time.** That is the soft underbelly of the whole impacts-driven scheduling approach.

This PRD adds a post-merge drift check: after a PRD's PR merges, the harness compares the declared `impacts:` globs against the actual file paths touched by the merge commit. Drift is reported, and configurable policies can warn, block future runs, or auto-update the frontmatter.

## Motivation

### Why declared impacts get out of sync

- PRDs are written before implementation. Authors guess at the file list. The agent then ranges wider than expected (touches a test file, adds an import to a shared header, refactors a helper) and the declared globs lag.
- Globs can be wrong by accident. A PRD says `impacts: src/darkfactory/runner.py` but the agent also touches `src/darkfactory/state.py`. Today nothing notices.
- Globs can be wrong by omission. A PRD says nothing in `impacts:` (empty list) and proceeds to rewrite ten files. Today nothing notices.
- PRD authors update the body of a PRD as scope grows but forget to update the frontmatter. Today nothing notices.

### Why this is load-bearing for PRD-545

PRD-545's scheduler infers "PRD-A and PRD-B will conflict" from the *intersection* of their declared `impacts:` globs. If either PRD's globs are incomplete, the intersection is empty, the scheduler decides they can run in parallel, and the harness happily produces two branches that conflict at merge time anyway. The auto-rebase + conflict-resolution machinery from PRD-545 will catch the collision after the fact, but the *whole point* of the scheduler was to avoid the collision in the first place. Drift makes the scheduler unreliable, which makes Phase 1 of PRD-545 worth less than it should be.

This is therefore tagged `blocks: [PRD-545]` — strictly speaking PRD-545 can ship without it, but it ships *worse* without it. Better to land 546 first or in parallel.

### Why post-merge rather than pre-merge

The drift check fundamentally needs the *actual* diff to compare against. The cleanest moment to compute that is the merge commit on `main` — that's exactly the diff the PRD landed. Pre-merge checks (e.g. on the open PR) are also valuable but come with caveats: the PR can be force-pushed, the diff can shift, the agent can rewrite history. Post-merge is final, deterministic, and easy to compute from `git show <merge-sha>`.

A pre-merge variant (run during the PR's CI pass) is worth a follow-up but is not in scope here.

## Requirements

### Functional

1. **Trigger.** After a PRD's PR merges into `main` (detected by the harness's existing merge-tracking, or by a manual `prd check-drift <PRD>` invocation), compute the drift check.
2. **Diff source.** The "actual files touched" set is the union of all file paths in the merge commit's diff against its parent on `main`. Excludes the PRD file itself (every PRD touches its own status), the harness output log, and any other files in a configurable ignore list (e.g. `.harness-agent-output.log`, `**/__pycache__/**`).
3. **Glob expansion.** The "declared files" set is computed by expanding each `impacts:` glob against the actual files-touched set. A glob "matches" if any actual file matches it. (We don't care about files the glob would have matched if they had existed — only whether each actual file is covered by some declared glob.)
4. **Drift detection.** A file is "drift" if it was actually touched but matches no declared glob. The drift report is the set of drifted files plus the PRD ID.
5. **Reporting.** Drift is logged at three levels:
   - **Per-PRD record.** Stored alongside the PRD's merge metadata so `prd show <PRD>` and `prd status` can surface it.
   - **Run summary.** When the harness finishes any run, it prints a summary of any drift detected during that run.
   - **History query.** `prd drift-report` lists all PRDs with declared-vs-actual drift over a configurable lookback window.
6. **Policies.** A project-level config option (in `.darkfactory/config.toml`, per PRD-222.6) selects the drift policy:
   - **`warn`** (default) — log drift, do not block anything.
   - **`block-future-runs`** — refuse to start new `prd run` invocations until the drifted PRD's frontmatter is updated or the drift is acknowledged.
   - **`auto-update`** — automatically rewrite the merged PRD's `impacts:` frontmatter to include the drifted files (with a chore commit on `main`) and continue.
7. **Manual recheck.** `prd check-drift <PRD>` recomputes drift on demand against the recorded merge commit, useful during development of this feature and for spot-checking.
8. **Acknowledgement.** `prd acknowledge-drift <PRD>` records that the user has seen the drift and either accepts it as-is or has updated the frontmatter. Clears the drift from `prd status` reporting until/unless drift is detected again on a future merge of the same PRD (e.g. if it gets reopened).
9. **PRD-545 integration.** The scheduler in PRD-545 must consult drift history when planning parallelism: if PRD-A has historical drift onto files outside its declared `impacts:`, treat those drifted files as part of A's effective impact set for scheduling purposes. (Open question — see below.)

### Non-functional

1. **Cheap.** The drift check is one `git show --name-only <merge-sha>` plus glob matching. Must complete in well under one second per PRD even on a large monorepo.
2. **Deterministic.** Same merge commit, same `impacts:` globs, same ignore list → same drift report.
3. **Honest.** Never silently auto-update without recording it in a clear chore commit (`chore(prd): auto-update PRD-X impacts after drift detected`) and never auto-update if the diff is empty (means we ran against the wrong commit).
4. **Failsafe.** If the merge SHA can't be resolved (deleted branch, force-pushed history), log a warning and skip — do not block the harness from continuing.

## Technical Approach

- **`src/darkfactory/drift.py`** (new module) exposing:
  - `compute_drift(prd, merge_sha, repo_root, ignore_globs) -> DriftReport`
  - `DriftReport` dataclass: `prd_id`, `merge_sha`, `declared_globs`, `actual_files`, `drifted_files`, `is_drift: bool`
- Integration with the post-merge hook in `runner.py` (or a new `cli/check_drift.py` subcommand `prd check-drift` that runs the same code).
- Drift history persisted under `.darkfactory/drift/` as one file per PRD merge (small JSON), so it survives across harness runs and can be queried by other features (notably PRD-545's scheduler).
- Project policy resolution goes through the cascade resolver from PRD-222.6 once that lands; until then, hardcode the default `warn` policy and accept a CLI override (`--drift-policy=warn|block|auto-update`).

## Acceptance Criteria

- [ ] **AC-1:** `prd check-drift <PRD>` against a known PRD with known declared impacts and known actual files produces a correct drift report (correct drifted-files set).
- [ ] **AC-2:** A PRD that declares `impacts: ['src/foo.py']` but whose merge actually touched `src/foo.py` AND `src/bar.py` is reported as drifted, with `src/bar.py` in the drifted-files set.
- [ ] **AC-3:** A PRD that declares `impacts: ['src/foo.py', 'src/bar.py']` and touched only `src/foo.py` is **not** reported as drifted (under-declaration is fine; only over-touching matters).
- [ ] **AC-4:** The PRD file itself, `.harness-agent-output.log`, and any other configured ignore-list files are excluded from the actual-files set.
- [ ] **AC-5:** Drift is checked automatically when a PR is detected as merged by the harness, without needing a manual command.
- [ ] **AC-6:** `prd status` surfaces any unacknowledged drift on PRDs in the project.
- [ ] **AC-7:** `prd acknowledge-drift <PRD>` clears the drift from status reporting; subsequent fresh drift on the same PRD is detected again.
- [ ] **AC-8:** The `auto-update` policy rewrites the merged PRD's `impacts:` frontmatter, commits the change as `chore(prd): auto-update PRD-X impacts after drift detected`, and pushes — never silently rewriting history.
- [ ] **AC-9:** The `block-future-runs` policy causes `prd run` to refuse to start when any PRD has unacknowledged drift; `--force` overrides with a loud warning.
- [ ] **AC-10:** Drift history is persisted under `.darkfactory/drift/` and survives across harness restarts.
- [ ] **AC-11 (PRD-545 integration):** When PRD-545's scheduler computes the conflict graph, it includes historical drifted files in each PRD's effective impact set, so previously-observed drift makes future scheduling more conservative.

## Open Questions

- [ ] **PRD-545 integration depth.** Does the scheduler treat *historical* drift as predictive (file X drifted last time, assume it'll drift again) or only as informational? Leaning toward predictive — better to over-serialize than under-serialize. AC-11 reflects the predictive interpretation.
- [ ] **Drift policy default.** `warn` is the safest default for adoption. But once the feature is bedded in, should the default flip to `block-future-runs` so drift is treated as a real bug? Defer the decision until we have a few weeks of drift data.
- [ ] **Ignore-list defaults.** The PRD file itself, harness logs, `__pycache__/`, lockfiles (`uv.lock`, `package-lock.json`)? Lockfiles are interesting — they're real diffs but not "PRD intent." Leaning toward including lockfiles in the default ignore list with a config knob to override.
- [ ] **Per-glob diagnostics.** When drift is reported, would users want to see *which* declared globs covered which files (and which globs matched nothing)? Useful for debugging, more output noise. Probably yes, behind a `--verbose` flag.
- [ ] **Reopened PRDs.** If a merged PRD is reopened (status flipped back from `merged` → `in-progress`) and re-merged later, the drift check fires again on the new merge commit. The previous drift record should be retained as history but the new merge generates a fresh report. Confirm.
- [ ] **Pre-merge variant.** Computing drift against the open PR's HEAD (instead of a merge commit) would let CI catch drift before merging. Useful but adds force-push complications. Defer to a follow-up PRD.

## References

- [[PRD-545-harness-driven-rebase-and-conflict-resolution]] — the consumer of this data; the scheduler's parallelism guarantees are only as good as the impacts declarations they're built on.
- `src/darkfactory/impacts.py` — current static conflict detector. Drift detection complements it: impacts.py predicts conflicts from declared globs; this PRD validates the declared globs against reality after the fact.
- `src/darkfactory/containment.py` — `effective_impacts` aggregation needs to be aware of drift records when computing scheduling impact sets.

## Assessment (2026-04-11)

- **Value**: 3/5 — drift detection is a quality signal, not a blocker.
  Its biggest payoff is as input to PRD-545's scheduler (Phase 1), and
  that scheduler isn't scheduled yet. Standalone, the value is "surface
  when PRDs lied about their impacts" — useful but not urgent.
- **Effort**: m — one focused module (`src/darkfactory/drift.py`),
  a CLI subcommand (`prd check-drift`), per-PRD record persistence, and
  integration with the existing post-merge hook. Most of the primitive
  pieces already exist (impacts globs, `git show --name-only`, etc.).
- **Current state**: greenfield. `src/darkfactory/drift.py` doesn't
  exist. `.darkfactory/drift/` isn't created. `prd check-drift` isn't
  a subcommand.
- **Gaps to fully implement**:
  - Implement `compute_drift(prd, merge_sha, repo_root, ignore_globs)`
    with the `DriftReport` dataclass.
  - Add `prd check-drift` CLI subcommand (`cli/check_drift.py`).
  - Persist records under `.darkfactory/drift/` or `.darkfactory/data/drift/`
    — decide placement alongside PRD-622's layout.
  - Wire into the post-merge detection path in `checks.py` /
    `cli/reconcile.py` so drift fires automatically.
  - Implement the `warn` policy only in v1 — defer `block-future-runs`
    and `auto-update` until real drift data is available.
- **Recommendation**: defer — do not schedule until PRD-545 Phase 1 is
  on a concrete timeline. The scheduler integration is the load-bearing
  consumer; without it, the drift records are a dashboard curiosity.
  When it does land, reuse its file-overlap plumbing rather than
  duplicating. Open question: record placement under `.darkfactory/`
  still needs resolving per the earlier PR #173 assessment notes.
