---
id: PRD-543
title: Harden harness create_pr step — surface gh errors and refuse re-running merged PRDs
kind: feature
status: draft
priority: high
effort: s
capability: simple
parent:
depends_on:
  - "[[PRD-549-builtins-package-split]]"
blocks: []
impacts:
  - src/darkfactory/builtins.py
  - src/darkfactory/runner.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - reliability
---

# Harden harness create_pr step — surface gh errors and refuse re-running merged PRDs

## Summary

Two small but high-impact reliability fixes to the harness, both motivated by a concrete incident today:

- **(A) `create_pr` must surface the real `gh` stderr.** Today, when the `create_pr` builtin fails, the harness re-raises a `CalledProcessError` whose message is just the argv. The actual `gh` error text — the one line that would tell the user *why* — is captured by subprocess and thrown away. Every failure in this step is therefore equally opaque.
- **(B) The harness must refuse (or loudly warn and prompt) when a PRD is re-run after its branch has already been merged.** Re-running a merged PRD is almost always a user mistake: it re-runs the agent on top of a branch whose work is already in the target branch, re-does the implementation, and then fails confusingly at `create_pr` because GitHub sees either "no commits between base and head" or a stale cache of the just-merged PR.

## Motivation

### The incident

Earlier today, PRD-228 (`Initial planning workflow: decompose epics into child PRDs`) was run once, produced PR #21 against `main`, and was merged at 14:50:32. A short time later, the user re-ran the same PRD — same head branch `prd/PRD-228-planning-workflow-initial` — this time with `docs/prd-231-planning-review` as the base. Every workflow step succeeded through `push_branch`. Then `create_pr` failed with:

```
[builtin] create_pr — Command '['gh', 'pr', 'create', '--base', 'docs/prd-231-planning-review',
  '--title', 'PRD-228: Initial planning workflow: decompose epics into child PRDs',
  '--body-file', '/var/folders/.../tmpivbinxn1.md']' returned non-zero exit status 1.
```

That is the *entire* failure message surfaced to the user. There is no hint at which of the half-dozen plausible gh failure modes actually occurred:

- "a pull request for branch X already exists" (stale cache of the merged PR)
- "No commits between base and head" (if the re-done work produced an identical tree)
- auth / rate limit
- branch protection
- GitHub API 5xx

Debugging required the user to drop into a shell and re-run the exact `gh` invocation manually to see the real error. That workflow is broken — the harness already *has* the error text, it just discards it.

Furthermore, the deeper mistake was that the PRD should never have been re-run at all: its work was already merged. The harness had all the information to detect this (branch name → merged PR lookup via `gh`) but did not check, and instead did a full expensive agent run whose output was destined to be redundant at best and confusing at worst.

### Why this matters beyond one incident

- `create_pr` is the *last* step in most workflows. A failure here means the agent work has already been committed and pushed — the user is staring at a successful-but-unfinished run and has no signal about what to do next. Clarity here has outsized value.
- Re-running a merged PRD is a footgun that will keep happening. Branch names are stable, PRDs are reopened, workflows get iterated. Without a guard, every future recurrence will reproduce the same confusing failure mode.
- Both fixes are small, local to `builtins.py` / the create_pr helper, and require no architectural change.

## Requirements

### Functional

**(A) Surface gh stderr on failure**

1. The `create_pr` builtin must capture both stdout and stderr from the `gh pr create` subprocess.
2. On non-zero exit, the raised exception / reported failure must include:
   - The full argv (as today)
   - The exit code
   - The **complete stderr** from `gh`, verbatim
   - The stdout if non-empty (gh sometimes writes hint text there)
3. The failure message rendered in the workflow step output (the line starting with `✗ [builtin] create_pr —`) must include at minimum the first non-empty line of gh's stderr so the user sees the actual reason without needing to open logs.
4. The full captured output must also be written to the harness agent output log for the run so it is recoverable after the fact.
5. Apply the same treatment to `push_branch` and any other builtin that shells out to `gh` or `git` — stderr capture-and-surface should be the default for subprocess builtins, not a one-off for `create_pr`. (Implementation: a small `run_cli(argv, *, step_name) -> CompletedProcess` helper that all shell-out builtins share.)

**(B) Refuse re-running merged PRDs**

1. At the start of a workflow run, the harness must check whether the PRD's head branch already has a **merged** PR on GitHub. The check is a single `gh pr list --head <branch> --state merged --json number,url,mergedAt,baseRefName --limit 1` call.
2. If a merged PR is found:
   - **Default behavior:** refuse to run the workflow. Exit with a clear message naming the merged PR number, URL, base branch, and merge timestamp. Suggest the user either (a) create a new PRD, (b) reopen with a new branch suffix, or (c) pass `--force` to override.
   - **`--force` flag:** override the check and proceed anyway. Logs a loud warning at the start of the run.
3. The check must also run before the `create_pr` step itself as a belt-and-braces safeguard — if a merged PR for the head branch appeared *during* the run (rare but possible with concurrent users), create_pr should short-circuit with a clear "already merged as #N" message rather than attempting and failing.
4. If the check cannot contact GitHub (network error, auth failure), the harness must **not** fail the run — it should log a warning and proceed. The check is a safety net, not a critical path.
5. The check is cheap (one API call) and must complete in under 2 seconds in the happy path; otherwise it is skipped with a warning.

### Non-Functional

1. Both changes are implemented in a single PR, since they address the same incident and touch overlapping code.
2. Unit tests cover: stderr capture on failure, stderr capture on success (should be silent), merged-PR detection positive case, merged-PR detection negative case, `--force` override, GitHub-unreachable fallthrough.
3. No change to happy-path output — users whose runs succeed should see exactly the same workflow output they see today.

## Technical Approach

### (A) Subprocess helper

- Add `src/darkfactory/_subprocess.py` (or fold into existing builtins module) exposing:
  ```python
  def run_cli(argv: list[str], *, step_name: str, cwd: Path | None = None) -> subprocess.CompletedProcess
  ```
- Runs the process with `capture_output=True, text=True`. On non-zero exit, raises a custom `BuiltinCommandError(step_name, argv, returncode, stdout, stderr)` whose `__str__` includes the first stderr line and whose full payload is dumped to the harness log.
- Update `create_pr`, `push_branch`, and any other `subprocess.run(["gh", ...])` / `subprocess.run(["git", ...])` sites in `builtins.py` to use this helper.

### (B) Merged-PR guard

- Add a new helper `check_prd_already_merged(prd, branch) -> MergedPRInfo | None` in `builtins.py` (or a new `gh.py`).
- Call it from the runner *before* the first mutating step (before `ensure_worktree` / `set_status` / `commit`).
- On hit: raise a `PRDAlreadyMergedError` (new exception) that the CLI formats into the refusal message. Do not touch worktree or PRD file.
- On miss or error: proceed normally.
- Add a `--force` flag to `prd run` that sets a `force: bool` on the run context; the guard consults it and logs a warning instead of raising.
- The same helper is called as an early check inside `create_pr`; if it suddenly hits there, raise a new `PRAlreadyMergedError` with the existing PR URL and mark the step as a non-failing **skipped** outcome (the work is already in the target branch — that is success, not failure).

## Acceptance Criteria

- [ ] AC-1: When `gh pr create` fails, the workflow step output includes gh's actual error message (first non-empty stderr line at minimum).
- [ ] AC-2: When `gh pr create` fails, the harness agent output log contains the full captured stderr verbatim.
- [ ] AC-3: `create_pr`, `push_branch`, and every other builtin that shells out go through a single `run_cli` helper that captures both streams.
- [ ] AC-4: Running `prd run <PRD>` on a PRD whose head branch already has a merged PR refuses to start, prints the merged PR number, URL, base, and merge time, and exits non-zero without touching the worktree or PRD frontmatter.
- [ ] AC-5: Running `prd run --force <PRD>` in the same situation proceeds, after logging a loud warning identifying the merged PR.
- [ ] AC-6: If GitHub is unreachable when the guard runs, the workflow logs a warning and continues (does not fail the run).
- [ ] AC-7: The `create_pr` step itself short-circuits with a clear "already merged as #N" success (not failure) if the branch became merged during the run.
- [ ] AC-8: Unit tests cover all the above paths using mocked subprocess / `gh` responses.
- [ ] AC-9: Happy-path workflow output is byte-identical to the previous version (no new noise on successful runs).

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- OPEN: Should the guard also fire on **closed** (not merged) PRs for the same head branch? Leaning no — a closed unmerged PR means the user abandoned it, re-running is legitimate. Only a *merged* PR means the work is already landed.
- OPEN: Should `--force` still run the merged-PR guard and *just* demote the refusal to a warning, or skip the check entirely? Leaning demote-to-warning so the user still sees which PR it collided with.
- OPEN: Should the refusal message offer to auto-suffix the branch (e.g. `prd/PRD-228-planning-workflow-initial.2`) and retry, or is that too magical for a first pass? Leaning toward printing the exact command rather than doing it.
- DEFERRED: Full subprocess-builtin refactor beyond `create_pr` / `push_branch`. Scope this PRD to those two plus whatever is trivially adjacent; leave the rest for a follow-up cleanup.

## References

- Incident today, 2026-04-08: PRD-228 was merged via PR #21 against `main` at 14:50:32. A subsequent re-run of the same PRD against base `docs/prd-231-planning-review` completed all steps through `push_branch` and then failed at `create_pr` with `returned non-zero exit status 1` — no error text. Manual re-invocation of the same `gh pr create` argv succeeded as PR #23, indicating the original failure was either transient or a gh-side cache artifact of the just-merged PR #21. Either way, the user had no way to diagnose it from the harness output alone, and the deeper issue was that the re-run should never have been started.
- Related: PRD-542 (effort-based agent timeouts) — another reliability improvement to the harness motivated by the same class of "the run completed but the harness reported failure" problem.

## Assessment (2026-04-11)

- **Value**: 4/5 — two concrete incidents worth of pain, both high-signal.
  (A) Opaque `gh` failures are currently the most common "the run almost
  worked, now what?" moment; (B) re-running a merged PRD is a pattern
  the harness should block by default, not produce confusing CI noise.
- **Effort**: s — `builtins/create_pr.py` and `builtins/push_branch.py`
  already exist as their own files post-PRD-549. The PR proposes a small
  shared `run_cli` helper plus a `check_prd_already_merged` guard. No new
  architecture.
- **Current state**: greenfield. `create_pr.py` currently re-raises
  `CalledProcessError` with argv only; there is no `_gh_check_merged`
  helper and no `--force` flag on `prd run`.
- **Gaps to fully implement**:
  - Add `run_cli` (or inline in `create_pr.py` / `push_branch.py`)
    capturing stdout + stderr and rendering the first stderr line
    verbatim in the failure message.
  - Add `check_prd_already_merged(prd, branch)` using
    `gh pr list --head <branch> --state merged --json ... --limit 1`.
    Call it from `runner.run_workflow` start-of-run and again inside
    `create_pr` as a belt-and-suspenders check.
  - Add `--force` to `prd run` in `cli/run.py`, plumb through
    `ExecutionContext` (or the workflow kwargs).
  - Unit tests for: stderr capture, merged-PR hit, merged-PR miss,
    GitHub unreachable → warn-and-continue, `--force` override.
- **Recommendation**: do-now — highest value-per-effort in the standalone
  batch. Can land as a single PR paired with PRD-619 (which is a related
  runner fix in the same area). Do not block on PRD-621 / utils refactor;
  the `run_cli` helper can live in `builtins/_shared.py` for now.
