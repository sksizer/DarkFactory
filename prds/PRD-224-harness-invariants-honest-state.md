---
id: "PRD-224"
title: "Harness invariants for honest state"
kind: epic
status: ready
priority: high
effort: m
capability: moderate
parent: null
depends_on: []
blocks: []
impacts: []  # epic — children declare their own
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
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

## Decomposition into 7 child PRDs

### PRD-224.1 — `prd validate` warns on review-but-branch-gone PRDs

**What:** Add a check in `prd validate` that scans every PRD with `status: review`, looks for the corresponding `prd/PRD-X-*` branch on `origin`, and warns if it's missing. If `git branch -r` doesn't show the branch, the PR has been merged-and-deleted (or never existed) — the PRD should be `done` (or back to `ready`), not `review`.

**Why:** Catches Mode 1 drift at the next `prd validate` invocation, which runs in CI and can be run manually.

**Effort:** xs. ~30 LOC plus a test.

**Impacts:**
- `src/darkfactory/cli.py` (validate command)
- `tests/test_cli_workflows.py`

### PRD-224.2 — `ensure_worktree` refuses to resume on stale state

**What:** Before taking the resume path, `ensure_worktree` checks two things:

1. Is there a PR for this branch, and is it merged or closed? Use `gh pr list --head <branch> --state all --json state,mergedAt`. If the PR is merged or closed → refuse with "PRD-X already had its PR resolved; run `prd cleanup PRD-X` to start fresh."
2. Has the local branch diverged from `origin/<branch>`? If origin has commits the local doesn't (someone force-pushed or rebased), warn loudly.

**Why:** Catches Mode 2 — the user (or harness retry) won't unknowingly pile commits on top of a branch whose PR is already done.

**Effort:** s. ~50 LOC plus tests for the gh-merged, gh-closed, and diverged-from-origin paths.

**Impacts:**
- `src/darkfactory/builtins.py` (ensure_worktree)
- `tests/test_builtins.py`

**Open question:** what if `gh` isn't installed or auth'd? Fallback: log a warning and proceed with the local-only check (branch existence). Don't hard-fail just because `gh` is missing — that breaks anyone who hasn't set it up.

### PRD-224.3 — `create_pr` includes tool-call summary in PR body

**What:** When the harness opens a PR, append a "Harness execution summary" section to the PR body:

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

**Why:** Catches the false-success case directly. If the summary shows "0 Edit/Write" for a PRD that was supposed to write code, the reviewer (and any AI assistant looking at the PR) immediately spots the problem. Today this requires grepping the transcript file.

**Effort:** s. The harness already has the `InvokeResult.stdout` with all the tool-call events parsed by `_summarize_stream_event`. Need a new helper that aggregates them into counts.

**Impacts:**
- `src/darkfactory/builtins.py` (create_pr)
- `src/darkfactory/runner.py` (capture summary on each agent invocation)
- `src/darkfactory/invoke.py` (expose tool-call counts in InvokeResult)
- `tests/test_builtins.py`

### PRD-224.4 — Worktree lifecycle: keep until merge, then remove

**What:** Three coordinated changes:

1. **Successful runs do NOT remove the worktree.** The worktree stays after `create_pr` so review feedback / rework can use it (see PRD-225).
2. **Add `prd cleanup [PRD-X | --merged | --all]` subcommand.** Removes worktree dir + deletes local branch. Refuses if local has unpushed commits unless `--force`. `--merged` removes everything for PRDs whose PR is merged. `--all` removes everything (with confirmation).
3. **`prd status` shows a hygiene line at the bottom** when there are stale worktrees: `"3 worktrees for merged PRDs (run `prd cleanup --merged` to remove)"`. This nudges the user without forcing action.

**Why:** Today every successful run leaves debris. Mode 2 (retries onto stale branches) is downstream of "the worktree is still there from the last attempt but the branch state is wrong". Explicit, opt-in cleanup with a visible nag is the right balance.

**Effort:** s+. New subcommand + status surface.

**Impacts:**
- `src/darkfactory/cli.py` (new cmd_cleanup, status hygiene line)
- `src/darkfactory/builtins.py` (cleanup_worktree builtin already exists from PRD-209)
- `tests/test_cli_cleanup.py` (new file)

**Critical constraint:** the cleanup must NOT remove a worktree whose PR is still open. That would break rework loops (PRD-225). The check is `gh pr list --head <branch> --json state` — only `merged` or `closed` qualifies for removal.

### PRD-224.5 — GitHub Action: flip review → done on PR merge

**What:** Add `.github/workflows/prd-status-on-merge.yml`:

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

**Why:** This is the **structural** fix for Mode 1 drift. Once merged, the action flips the status automatically — no manual cleanup, no `reconcile-status` operation needed for the happy path.

**Effort:** s. One YAML file + manual verification on a test PR.

**Impacts:**
- `.github/workflows/prd-status-on-merge.yml` (new file)
- README note about the action

**Open questions:**
- What about PRDs whose status field uses a different YAML quoting style than the sed pattern expects? PRD-214's `update_frontmatter_field_at` is the robust answer, but reimplementing it in bash would be ugly. Alternative: invoke `python -c "from darkfactory.prd import set_status_at; ..."` if darkfactory is pip-installable by then (PRD-222.5). Until then, the sed pattern is good enough — it's the same shape every other status mutation produces.
- What if the PRD file is missing on main (rare but possible)? Action exits 0 with a log message, no failure.

### PRD-224.7 — `prd reconcile` local command for status drift

**What:** A local CLI subcommand `prd reconcile [--execute] [--dry-run]` that does what PRD-224.5's GitHub Action does, but locally and on-demand. Uses `gh pr list --state merged --json headRefName,mergedAt,number` to find merged PRs whose head branch matches `prd/PRD-X-*`, finds the corresponding PRD file with `status: review`, and flips it to `done`.

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

### PRD-224.6 — Commit agent transcripts to `.darkfactory/transcripts/`

**What:** Move the transcript dump from `<worktree>/.harness-agent-output.log` to `.darkfactory/transcripts/PRD-X-{ISO8601}.log`. One file per agent invocation, timestamped, never overwritten. Committed automatically by the workflow as part of the "ready for review" step. Lands in main when the PR merges → permanent record.

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
- **PRD-222** (general-purpose tool) — provides `.darkfactory/` layout this PRD uses for transcripts
- **PRD-223** (system operations) — provides `reconcile-status` as the manual fallback for the auto-reconcile in 224.5
- **PRD-225** (rework loop) — builds on the worktree-stays-after-create_pr decision in 224.4
- **PRD-530** (CI setup) — separate concern; this PRD's GH action is per-PR, PRD-530 is per-branch CI

## References

- PR #18 — manual reconcile of PRD-216/217/218/510 status drift (the symptom)
- PRD-510 worktree post-mortem — false-success agent that emitted PRD_EXECUTE_OK after 0 Edits (the symptom for 224.3)
- [GitHub Actions: pull_request closed event](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request)
