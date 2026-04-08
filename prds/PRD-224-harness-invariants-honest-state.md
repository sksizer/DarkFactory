---
id: PRD-224
title: Harness invariants for honest state
kind: epic
status: in-progress
priority: high
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts: []
workflow: planning
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - invariants
  - hygiene
---

# Harness invariants for honest state

## Summary

Three failure modes hit during the first dogfood week of darkfactory all share the same root cause: **the harness produces representations of state that drift from reality, with no enforcement that they stay in sync.** Symptoms:

1. **Status drift after merge** — PRDs sit in `status: review` after their PRs merge to main because nothing flips them to `done`.
2. **Stale worktrees + ghost retries** — `prd run` retries layer commits onto a worktree branch that no longer matches the eventually-merged PR; `git diff main..HEAD` lies about what shipped.
3. **Mental-model drift looking at the wrong branch** — operators (and AI assistants helping them) check the worktree to understand "what did the agent do" and find stale or partial state instead of the true PR content.

These all point at one missing principle: **the harness should make divergence between intent and reality loud, fast, and recoverable.**

This epic adds 6 invariants that catch each drift mode at the moment it appears, plus structural fixes that prevent some classes of drift from happening at all.

## Motivation

Examples from the live record:

- **PRD-216, 217, 218, 510 all sat in `review` status for hours after their PRs merged.** Manual cleanup (PR #18) flipped them. Nothing in the tooling caught it.
- **PRD-510 worktree had 5 commits across 3 retries.** None of them matched what shipped via PR #17. An AI assistant trying to diagnose state read the worktree, concluded "no implementation", and spent unnecessary cycles building the wrong mental model.
- **Agent transcripts live and die inside the worktree.** When the worktree gets removed, the post-mortem record is gone forever. There is no way to ask "what did the agent actually do to ship this PRD?" once the dust settles.

These aren't bugs in any single piece of code — they're missing invariants. The harness has plenty of state, but no checks that the state is honest.

## Architectural preference: composable primitives over hard-coded behavior

Where possible, each invariant in this epic ships as a **reusable primitive** — a `BuiltIn`, a `SystemOperation`, or a public check function — rather than as hard-coded logic baked into a single call site. The goals:

- **Customizability**: workflow authors can compose the same primitive into different task lists, skip ones they don't want, and add new ones without forking the harness.
- **Reuse across contexts**: a check or summary that's useful in `prd run` is usually also useful in `prd rework` (PRD-225) and in system operations (PRD-223). One primitive, many call sites.
- **Testability**: small functions are easier to test in isolation than embedded checks.

Two categories of work in this epic:

1. **Composable primitives** (preferred whenever possible):
   - `BuiltIn`s — invoked from a workflow's task list
   - `SystemOperation`s — invoked via `prd system run <name>`
   - Public check functions — called from CLI commands or other primitives
2. **Safety contracts at the primitive level** (only when correctness requires it):
   - Hard-coded guards inside existing primitives (e.g. `ensure_worktree`'s stale-state check) where bypassing the check would silently corrupt state. These can't be composed away because they're enforcing correctness, not policy.

Each child below is tagged `[primitive]` or `[safety contract]` so the architectural shape is explicit.

## Decomposition into 7 child PRDs

### PRD-224.1 — Public check function: `validate_review_branches` `[primitive]`

**What:** Extract a public check function `darkfactory.checks.validate_review_branches(prds, git_state) -> list[Issue]` that returns a list of "PRD is in review but its branch is gone from origin" issues. `prd validate` calls it and surfaces the issues as warnings. `SystemOperation`s (PRD-223) and other check pipelines can call the same function for their own purposes.

The function takes injected dependencies (`prds` dict, `git_state` adapter) so it's testable without a real repo.

**Why composable, not hard-coded:** other harness commands and operations need this same check — `prd reconcile` (224.7) uses it to find candidates, `prd cleanup` (224.4) uses it to know which worktrees are safe to remove, `prd status --verbose` could use it to flag drift in the listing. Hiding the logic inside `cmd_validate` would force every caller to re-implement it.

**Effort:** xs. ~50 LOC: the check function (~30) + the validate-command wiring (~10) + tests (~10).

**Impacts:**
- `src/darkfactory/checks.py` (new module with the function)
- `src/darkfactory/cli.py` (validate command calls it)
- `tests/test_checks.py` (new file)

### PRD-224.2 — `ensure_worktree` refuses to resume on stale state `[safety contract]`

**What:** Before taking the resume path, `ensure_worktree` checks two things:

1. Is there a PR for this branch, and is it merged or closed? Use `gh pr list --head <branch> --state all --json state,mergedAt`. If the PR is merged or closed → refuse with "PRD-X already had its PR resolved; run `prd cleanup PRD-X` to start fresh."
2. Has the local branch diverged from `origin/<branch>`? If origin has commits the local doesn't (someone force-pushed or rebased), warn loudly.

**Why hard-coded, not composable:** this is a **safety contract**. Bypassing the check means silently piling commits onto a stale branch whose PR is already done — exactly the Mode 2 corruption we're trying to prevent. A workflow author shouldn't be able to compose this away by using a different task list, the same way they can't compose away PRD-217's process lock. It belongs inside the primitive.

The actual *check logic* is still extracted into a function (`darkfactory.checks.is_resume_safe(branch, repo_root) -> ResumeStatus`) so that `prd cleanup`, `prd reconcile`, and tests can call the same logic. The `ensure_worktree` BuiltIn calls it and raises on a non-safe result.

**Effort:** s. ~50 LOC plus tests for the gh-merged, gh-closed, and diverged-from-origin paths.

**Impacts:**
- `src/darkfactory/checks.py` (`is_resume_safe` function)
- `src/darkfactory/builtins.py` (`ensure_worktree` calls it)
- `tests/test_builtins.py`, `tests/test_checks.py`

**Open question:** what if `gh` isn't installed or auth'd? Fallback: log a warning and proceed with the local-only check (branch existence). Don't hard-fail just because `gh` is missing — that breaks anyone who hasn't set it up.

### PRD-224.3 — `summarize_agent_run` BuiltIn + run-summary surface in `create_pr` `[primitive]`

**What:** Two pieces:

1. **New `summarize_agent_run` BuiltIn** that reads the most recent `InvokeResult` off the context, aggregates tool-call counts, and writes the summary into a known field on the context (`ctx.run_summary`). Workflow authors compose this into their task list wherever they want a snapshot — typically just before `create_pr`.

2. **`create_pr` BuiltIn looks at `ctx.run_summary`** and appends it to the PR body if present. If absent (because the workflow didn't include `summarize_agent_run`), the PR body looks the same as today. **Composable both ways**: skip the summary, customize it, run multiple summary steps for multi-agent workflows.

The summary content is the same as before:

```markdown
## Harness execution summary

- **Workflow:** default (priority 0)
- **Model:** claude-sonnet-4-6
- **Agent invocations:** 1 implement (success after 0 retries)
- **Tools used:** Read ×12, Edit ×8, Write ×2, Bash ×5, Glob ×3, Grep ×4
- **Tests:** ✓ 246 passed
- **Lint:** ✓ ruff check, ruff format, mypy strict
- **Sentinel:** PRD_EXECUTE_OK: PRD-X
- **Transcript:** [`.darkfactory/transcripts/PRD-X-2026-04-08T12-34-56.log`](...)
```

**Why composable, not hard-coded into `create_pr`:** rework workflows (PRD-225) want a different summary shape ("addressed N of M comments"). System operations (PRD-223) want their own. Forcing every PR creation to use the same summary block would either bloat `create_pr` with knobs or force everyone to fork it. A separate BuiltIn that produces a summary string keeps the contract clean: "if there's a summary on the context, render it."

**Why:** Catches the false-success case directly. If the summary shows "0 Edit/Write" for a PRD that was supposed to write code, the reviewer immediately spots the problem. Today this requires grepping the transcript file.

**Effort:** s. The harness already has `InvokeResult.stdout` parsed by `_summarize_stream_event`. Need a count aggregator + the new BuiltIn + minor `create_pr` change.

**Impacts:**
- `src/darkfactory/builtins.py` (new `summarize_agent_run`, modified `create_pr`)
- `src/darkfactory/invoke.py` (expose tool-call counts in `InvokeResult`)
- `src/darkfactory/workflow.py` (`ExecutionContext.run_summary` field)
- `workflows/default/workflow.py` (insert `summarize_agent_run` before `create_pr`)
- `tests/test_builtins.py`

### PRD-224.4 — Worktree lifecycle: `prd cleanup` subcommand + `prd status` hygiene line `[CLI surface]`

**What:** Three coordinated changes:

1. **Successful runs do NOT remove the worktree.** The default workflow's task list already lacks `cleanup_worktree` after `create_pr` — confirm and document. The worktree stays so review feedback / rework can use it (see PRD-225). **No code change** for this part — it's a workflow-composition decision, not a code path.

2. **`prd cleanup [PRD-X | --merged | --all]` subcommand.** Removes worktree dir + deletes local branch. Refuses if local has unpushed commits unless `--force`. `--merged` removes everything for PRDs whose PR is merged. `--all` removes everything (with confirmation). Internally uses the existing `cleanup_worktree` BuiltIn from PRD-209 plus the `is_resume_safe` check from 224.2 (inverted: "is_safe_to_remove").

3. **`prd status` shows a hygiene line at the bottom** when there are stale worktrees: `"3 worktrees for merged PRDs (run `prd cleanup --merged` to remove)"`. Nudges without forcing action.

**Why CLI surface and not BuiltIn / SystemOperation:** `prd cleanup` is **user-initiated maintenance**, not a step in a workflow run. It's appropriate to live as a CLI command. The *underlying logic* (which worktrees are stale, can-remove check) lives in `darkfactory.checks` so other tools can call it.

**Effort:** s+. New subcommand + status surface.

**Impacts:**
- `src/darkfactory/cli.py` (new `cmd_cleanup`, `cmd_status` hygiene line)
- `src/darkfactory/checks.py` (new `find_stale_worktrees`, `is_safe_to_remove`)
- `tests/test_cli_cleanup.py` (new file)

**Critical constraint:** the cleanup must NOT remove a worktree whose PR is still open. That would break rework loops (PRD-225). The check is `gh pr list --head <branch> --json state` — only `merged` or `closed` qualifies for removal.

### PRD-224.5 — GitHub Action: flip review → done on PR merge `[CI config]`

**What:** Add `.github/workflows/prd-status-on-merge.yml`. The action is a thin wrapper that invokes `darkfactory.cli reconcile --execute --commit-to-main` (the same primitive used by 224.7's local command). The action's only job is the trigger — all the actual logic lives in the primitive.

```yaml
name: Reconcile PRD status on merge
on:
  pull_request:
    types: [closed]
    branches: [main]
jobs:
  flip-status:
    if: github.event.pull_request.merged == true && startsWith(github.event.pull_request.head.ref, 'prd/PRD-')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0
      - name: Flip status to done
        run: |
          # Extract PRD-X from branch name
          BRANCH="${{ github.event.pull_request.head.ref }}"
          PRD_ID=$(echo "$BRANCH" | sed -E 's|^prd/(PRD-[0-9.]+).*|\1|')
          # Find the PRD file
          FILE=$(ls prds/${PRD_ID}-*.md 2>/dev/null || true)
          if [ -z "$FILE" ]; then
            echo "No PRD file matching $PRD_ID — skipping"
            exit 0
          fi
          # Surgical sed: only the status line
          sed -i 's|^status: review$|status: done|' "$FILE"
          sed -i "s|^updated: .*|updated: '$(date -u +%Y-%m-%d)'|" "$FILE"
          # Commit if changed
          if ! git diff --quiet "$FILE"; then
            git config user.name "darkfactory-bot"
            git config user.email "darkfactory-bot@users.noreply.github.com"
            git add "$FILE"
            git commit -m "chore(prd): mark $PRD_ID done (auto-reconciled by merge action) [skip ci]"
            git push
          fi
```

**Why GH Action and not BuiltIn / SystemOperation:** the action runs in response to a GitHub event (PR merge), not as part of any darkfactory invocation. It can't be "composed away" because it doesn't exist inside any workflow. It just listens for the event and dispatches the same primitive a local user would.

**Why:** This is the **structural** fix for Mode 1 drift. Once merged, the action flips the status automatically — no manual cleanup, no `reconcile-status` operation needed for the happy path.

**Effort:** s. One YAML file + manual verification on a test PR.

**Impacts:**
- `.github/workflows/prd-status-on-merge.yml` (new file)
- README note about the action

**Open questions:**
- What about PRDs whose status field uses a different YAML quoting style than the sed pattern expects? PRD-214's `update_frontmatter_field_at` is the robust answer, but reimplementing it in bash would be ugly. Alternative: invoke `python -c "from darkfactory.prd import set_status_at; ..."` if darkfactory is pip-installable by then (PRD-222.5). Until then, the sed pattern is good enough — it's the same shape every other status mutation produces.
- What if the PRD file is missing on main (rare but possible)? Action exits 0 with a log message, no failure.

### PRD-224.7 — `reconcile-status` SystemOperation + `prd reconcile` CLI wrapper `[primitive + CLI]`

**Note:** this child supersedes and absorbs **PRD-223.4** (`reconcile-status` SystemOperation). They were drafted as separate items but are the same thing — track here, remove from PRD-223 to avoid duplication.

**What:** A `SystemOperation` named `reconcile-status` (PRD-223 abstraction) that does the actual work, plus a thin CLI wrapper `prd reconcile` for users who don't want to type `prd system run reconcile-status`. The GitHub Action in 224.5 also calls into this primitive. Uses `gh pr list --state merged --json headRefName,mergedAt,number` to find merged PRs whose head branch matches `prd/PRD-X-*`, finds the corresponding PRD file with `status: review`, and flips it to `done`.

**The key behavior decision:** for trivial status-only changes, **commit directly to main** rather than opening a fresh PR for each one. Status flips are mechanical, single-line, no logic — going through review for each is overkill. The commit message format makes the auto-reconcile origin obvious:

```
chore(prd): mark PRD-X done (auto-reconciled from merged PR #N)

[skip ci]
```

**Workflow:**

```
prd reconcile           # dry-run by default — print what would change
prd reconcile --execute # flip statuses, commit to main, push
```

**Why this exists alongside PRD-224.5:**

- **224.5 (GH Action)** handles the happy path automatically — fires the moment a PR merges, no human action needed.
- **224.7 (local reconcile)** is the catch-up tool for cases the action missed: PRs merged before the action existed, branches that didn't follow the `prd/PRD-X-*` convention, action failures, repos where the action isn't enabled. It's also the right tool for the "I just pulled main and want to make sure everything's tidy" workflow.

The user explicitly wanted compute on local hardware where possible, so the local command is the primary path; the GH Action is the convenience layer on top.

**Effort:** s. Reuses the same pattern PR #18's manual sed command did, but properly via `update_frontmatter_field_at`.

**Impacts:**
- `src/darkfactory/cli.py` (new cmd_reconcile)
- `tests/test_cli_reconcile.py` (new file)

**Open questions:**
- Should reconcile also clean up local worktrees as a side effect, or stay focused on status updates? Recommendation: stay focused — `prd cleanup` (224.4) is the worktree-removal tool. They can be chained: `prd reconcile && prd cleanup --merged`.
- What if multiple PRDs need reconciling? Batch them in a single commit titled "chore(prd): reconcile N merged PRD statuses".
- Direct-to-main without a PR is unusual — should it require `--commit-to-main` opt-in? Recommendation: yes, default to creating a PR (matches the rest of the harness's safety norms), with `--commit-to-main` as an explicit shortcut for the trivial-status-only path.

### PRD-224.6 — `commit_transcript` BuiltIn + `.darkfactory/transcripts/` layout `[primitive]`

**What:** A new BuiltIn `commit_transcript` that workflow authors compose into their task list. It moves the transcript dump from `<worktree>/.harness-agent-output.log` (the temporary location written by `runner.py` today) to `.darkfactory/transcripts/PRD-X-{ISO8601}.log` (a tracked location), then stages it. The next `commit` BuiltIn picks it up and commits with the rest of the work.

The default workflow is updated to insert `commit_transcript` before the final `commit`. Custom workflows can skip it if they don't want transcript persistence — but **the long-term enforcement story** is via PRD-227's workflow templates: a template's `close` list includes `commit_transcript` so it can't be accidentally omitted.

**Why composable, not hard-coded into the runner:** the runner's job is to dispatch tasks; persisting their output is workflow policy, not runner machinery. Some workflows (e.g. local exploratory ones) might not want transcripts. The BuiltIn approach respects that; PRD-227's templates enforce it for workflows that need the guarantee.

One file per agent invocation, timestamped, never overwritten. Lands in main when the PR merges → permanent record.

**Why:** When debugging "why did the agent claim success without writing files" or "why did this PRD take 9 retries", the only honest source of truth is the agent's own transcript. Today it's ephemeral — once the worktree is gone the evidence is gone. Committing it makes every PRD's execution history available retroactively.

**Effort:** s.

**Impacts:**
- `src/darkfactory/runner.py` (transcript path + multi-file)
- `src/darkfactory/workflow.py` (commit step picks up the transcript dir)
- `.gitignore` — make sure `.darkfactory/transcripts/` is NOT excluded
- `.gitattributes` — mark `*.log` under transcripts as `linguist-generated=true` so GitHub collapses them in PR views

**Notes:**
- Bloat: ~100KB per transcript × ~100 PRDs/year ≈ 10MB/year. Acceptable for now; refine later if needed.
- Security: transcripts may contain file contents the agent read. Don't commit transcripts if they contain secrets. Add a basic `prd validate --check-transcripts` later that scans for token-shaped strings.
- Layout assumes PRD-222.1 (`.darkfactory/` discovery) is in place. Until then, use `<repo_root>/.darkfactory/transcripts/` directly with manual creation.

## Acceptance Criteria

- [ ] AC-1 (post 224.1): `prd validate` exits with a warning when a PRD is `review` but its branch is gone from origin.
- [ ] AC-2 (post 224.2): `prd run PRD-X` refuses to resume if the corresponding PR is merged or closed; clear error tells the user to run `prd cleanup PRD-X`.
- [ ] AC-3 (post 224.3): A PR opened by the harness has a "Harness execution summary" section with tool-call counts, model, sentinel, and transcript link.
- [ ] AC-4 (post 224.4): `prd cleanup PRD-X` removes the worktree dir and the local branch when the PR is merged; refuses when the PR is still open.
- [ ] AC-5 (post 224.4): `prd status` shows a hygiene line listing how many merged-PRD worktrees are still on disk.
- [ ] AC-6 (post 224.5): A test PR for a `prd/PRD-test-` branch, when merged, triggers the GitHub Action and lands a follow-up commit on main flipping the PRD's status to `done`.
- [ ] AC-7 (post 224.6): An agent invocation creates a file at `.darkfactory/transcripts/PRD-X-{timestamp}.log`, the file is committed by the harness's commit step, and it lands in main when the PR merges.
- [ ] AC-8 (post 224.7): `prd reconcile` (dry-run) lists merged-but-not-flipped PRDs; `--execute` updates them; `--commit-to-main` skips the PR step for trivial status flips.
- [ ] AC-9: All 7 children pass `prd validate`, `pytest`, and `mypy --strict` independently.
- [ ] AC-10: Running PRD-224 itself through the harness completes without manual rescue.

## Open Questions

- [ ] Should the GH action in 224.5 also flip statuses for non-prd/* branches that happen to mention a PRD ID in the commit? Probably not — too much rope. Stick to the prd/PRD-X-* convention.
- [ ] The hygiene line in 224.4 — should it be on every `prd status` call (slightly noisy) or only when count > 0? Recommendation: only when count > 0.
- [ ] Should `prd cleanup` auto-prompt on regular `prd status` if there's stale state, like git's "you have stash entries"? Recommendation: no — surface in the hygiene line, don't interrupt.

## Relationship to other PRDs

- **PRD-213** (set_status writes to worktree) — established the invariant this PRD enforces with checks
- **PRD-217** (process lock) — covers the "two runners on the same PRD" race; this PRD covers the "one runner on a stale branch" race
- **PRD-227** (workflow templates) — **the long-term enforcement layer**. PRD-224 ships the primitives (BuiltIns, check functions, CLI commands); PRD-227 wraps them in templates that guarantee composition order. Together they give "composable primitives + enforced positions" — flexibility within the middle, safety at the boundaries. Ship 224 first so the primitives exist; 227 organizes them.
- **PRD-222** (general-purpose tool) — provides `.darkfactory/` layout this PRD uses for transcripts
- **PRD-223** (system operations) — provides `reconcile-status` as the manual fallback for the auto-reconcile in 224.5
- **PRD-225** (rework loop) — builds on the worktree-stays-after-create_pr decision in 224.4
- **PRD-530** (CI setup) — separate concern; this PRD's GH action is per-PR, PRD-530 is per-branch CI

## References

- PR #18 — manual reconcile of PRD-216/217/218/510 status drift (the symptom)
- PRD-510 worktree post-mortem — false-success agent that emitted PRD_EXECUTE_OK after 0 Edits (the symptom for 224.3)
- [GitHub Actions: pull_request closed event](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request)
