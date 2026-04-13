---
id: PRD-225
title: "Rework loop: feed PR review comments back to the agent"
kind: epic
status: done
priority: high
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-224-harness-invariants-honest-state]]"
blocks:
  - "[[PRD-225.1-rework-subcommand-skeleton]]"
  - "[[PRD-225.2-pull-pr-comments]]"
  - "[[PRD-225.3-rework-prompt-template]]"
  - "[[PRD-225.4-rework-workflow]]"
  - "[[PRD-225.5-auto-reply-comments]]"
  - "[[PRD-225.6-rework-watch-daemon]]"
  - "[[PRD-225.7-loop-detection]]"
impacts: []
workflow:
target_version:
created: 2026-04-08
updated: '2026-04-09'
tags:
  - harness
  - workflow
  - feedback
  - feature
---

# Rework loop: feed PR review comments back to the agent

## Summary

Today the harness is **one-shot per PR**: agent runs, opens a PR, the harness is done. There's no path for review feedback (PR comments, requested changes, code-review notes) to make its way back to the agent. The user has to manually copy comments into a fresh prompt and re-invoke, losing all the context that lived in the worktree.

This PRD adds a `prd rework <PRD-X>` subcommand that:

1. Resumes the existing worktree (kept around per PRD-224.4)
2. Pulls **all** unaddressed review comments from the PR via `gh pr view --json comments,reviews`
3. Composes them into a feedback prompt
4. Re-invokes the agent in the same worktree with the feedback as task input
5. Lets the agent address each comment and stage its changes
6. Commits + pushes the new changes (the existing PR auto-updates)
7. Optionally posts replies on the PR comments saying "addressed in commit X" or "I disagree, here's why"

This turns the PR conversation into the actual mechanism for iterating on a PRD instead of treating it as terminal output.

## Motivation

Today the loop looks like:

```
prd run PRD-X --execute  →  PR opens
[user reviews PR, leaves comments]
[user manually copies comments into a prompt]
[user runs claude code in the worktree manually]
[user manually commits + pushes]
[PR updates]
```

That breaks the harness's value proposition. The agent's first attempt landed in a worktree we already own, with full context, with retry infrastructure, with the prompt template machinery. Throwing it away just because the user wants to address feedback is wasteful.

The right loop is:

```
prd run PRD-X --execute  →  PR opens
[user reviews PR, leaves comments]
prd rework PRD-X --execute  →  PR updates
```

Same worktree, same branch, same agent context — just a new agent invocation with feedback as input.

## Decomposition (sketch — to be fleshed out)

### PRD-225.1 — `prd rework <PRD-X>` subcommand skeleton

Resumes the existing worktree, refuses if no worktree exists or if the PR is already merged. No comment processing yet — just verifies the resume path works and prints what it would do.

### PRD-225.2 — Pull all unaddressed PR comments via `gh`

Use `gh pr view <num> --json comments,reviews,reviewThreads --jq '...'` to fetch:

- **Issue comments** (general PR discussion)
- **Review comments** (line-anchored code review remarks)
- **Review summaries** (the body of approved/changes-requested reviews)
- **Resolved status** (so we can skip already-resolved threads)

Default: pull everything that hasn't been resolved AND was posted after the harness's last commit on the branch. Filter out comments by the harness bot itself to avoid feedback loops.

Optional flags:
- `--all` — include resolved threads too
- `--since <commit>` — only comments posted after a specific commit
- `--reviewer <user>` — only comments from a specific reviewer
- `--from-pr-comment <id>` — pull just one specific comment (escape hatch for "address only this one thing")

### PRD-225.3 — Compose feedback into agent task input

A new prompt template `prompts/rework.md` that the rework workflow uses instead of `task.md`. The composed prompt looks roughly:

```markdown
# Rework: address PR review feedback for {{PRD_ID}}

You have already implemented {{PRD_ID}} and opened a PR. The reviewer
has left comments. Your job now is to address each comment.

## Original PRD
{{PRD_PATH}}

## Your previous work
The git history on this branch shows what you committed. Use
`git log` and `git diff` to see what's already done.

## Review feedback to address

{% for thread in unresolved_threads %}
### Comment by {{ thread.author }} on {{ thread.path }}:{{ thread.line }}
> {{ thread.body }}
{% endfor %}

## Steps
1. Read each comment carefully
2. Decide for each: address it (edit code) OR push back (note in your reply)
3. Make the necessary edits
4. Run tests + format + typecheck (the workflow handles these too)
5. For each comment, prepare a one-line reply: "Addressed in commit X" or
   "Disagree because Y" or "Already addressed in commit Z (please re-review)"
6. Stage your changes — the harness commits and pushes

## Sentinel
Final line: PRD_EXECUTE_OK: {{PRD_ID}} (or PRD_EXECUTE_FAILED: <reason>)
```

### PRD-225.4 — Rework workflow definition

A new workflow `workflows/rework/workflow.py` (or as a special task list inside the default workflow) that:

1. Skips `ensure_worktree`'s create path (worktree must already exist)
2. Skips `set_status` (already in `review`, stays there)
3. Skips the initial `commit` (no fresh status flip)
4. Runs the agent with `prompts/rework.md`
5. Runs test/format/lint/typecheck as usual
6. Commits with message `chore(prd): {prd_id} address review feedback`
7. Pushes (the existing PR auto-updates because we're pushing to the same branch)
8. Does NOT call `create_pr` (PR already exists)

### PRD-225.5 — Auto-post replies to addressed comments (optional)

After the agent finishes, post `gh pr comment` replies on each of the comments it claimed to address. The agent's per-comment reply notes are extracted from its output and posted with a `[harness] addressed in {commit_sha}` prefix so reviewers can distinguish bot replies from human ones.

This is optional because some users may prefer to review the new commits manually before declaring comments addressed. Make it `--reply-to-comments` opt-in.

### PRD-225.6 — Local polling rework daemon (auto, but on user hardware)

**What:** A long-running local process `prd rework-watch [--interval 60s]` that polls open PRs for new review comments and triggers `prd rework <PRD-X>` automatically when unaddressed feedback appears.

**Why polling instead of GH webhooks:** the user wants computation on their own hardware, not on GitHub Actions runners. A local poller:

- Runs the agent on the user's machine (full control over model, network, secrets)
- Doesn't require exposing a webhook endpoint
- Survives network blips (next poll catches up)
- Easy to pause/stop without messing with GH settings
- Handles air-gapped or VPN-restricted dev setups

**Polling logic:**

1. Every N seconds, list open PRs whose head branch matches `prd/PRD-*`
2. For each PR, fetch comments via `gh pr view`
3. Compare against the harness's last seen comment ID for that PR (stored in `.darkfactory/state/rework-watch.json`)
4. If new unresolved comments exist → invoke `prd rework PRD-X` in a subprocess
5. Update the last-seen pointer
6. Sleep, repeat

**Safety:**

- Refuse to start if the worktree for any active PR is missing (something else is going on)
- Maximum N rework cycles per PR per hour (default 3) to prevent thrashing on a hostile reviewer or an agent that can't stop revising
- Honor the same per-PRD process lock from PRD-217 so a manual `prd run` doesn't race with the watcher
- A `pause` file at `.darkfactory/state/rework-watch.pause` halts the watcher without stopping the process — useful when you want to manually iterate

**CLI:**

```
prd rework-watch                 # foreground, ctrl-C to stop
prd rework-watch --daemon        # background (writes PID file)
prd rework-watch --status        # show last poll time, queued PRDs
prd rework-watch --pause         # touch the pause file
prd rework-watch --resume        # remove the pause file
prd rework-watch --stop          # kill the daemon
```

**Effort:** m. New module + state file + signal handling. Test coverage needs a fake `gh pr view` and time-controlled polling loop.

**Impacts:**
- `src/darkfactory/cli.py` (new cmd_rework_watch)
- `src/darkfactory/rework_watch.py` (new module)
- `tests/test_rework_watch.py` (new file)
- `.darkfactory/state/` directory in the layout (PRD-222)

**Open questions:**
- Should the watcher invoke `prd rework` synchronously (block on each PR) or fan out to parallel subprocesses for independent PRDs? Recommendation: synchronous v1, parallel later.
- What happens when the watcher detects new comments but the agent is mid-implementation on something else? Recommendation: queue the rework and process when the lock is free.
- Cron alternative: should we ship a sample crontab entry instead of a daemon? Recommendation: ship the daemon since it has state, but document the cron pattern for users who prefer that.

This is a phase-2 piece of PRD-225 — it depends on 225.1-225.5 being solid first. Don't ship it before the manual `prd rework` command is well-tested.

### PRD-225.7 — Loop detection

A safety check: if the same `prd rework PRD-X` produces no changes (agent runs but stages nothing), flag it loudly. Possible causes: agent thinks the comments are already addressed, agent disagrees and pushed back in its sentinel, agent is confused. The harness should not silently no-op repeated rework attempts — that's how loops happen.

## Acceptance Criteria (to be refined when fleshing out children)

- [ ] AC-1: `prd rework PRD-X` resumes the existing worktree and refuses if it doesn't exist
- [ ] AC-2: Pulls all unresolved PR comments and surfaces them in the agent prompt
- [ ] AC-3: New commits land on the same branch and the existing PR auto-updates
- [ ] AC-4: Repeated `prd rework PRD-X` runs that produce no changes are flagged as a potential loop
- [ ] AC-5: Optional `--reply-to-comments` flag posts addressed-comment replies on the PR

## Open Questions

- [ ] Should the rework workflow share a config with the original (model, retries) or have its own? Recommendation: share, but allow override via `--model` and `--retries`.
- [ ] What happens if the reviewer pushes a commit themselves while the agent is reworking? Race condition — the rebase / merge would conflict. Recommendation: detect by checking `git fetch && git rev-list HEAD..origin/<branch>` before invoking the agent; if origin is ahead, refuse and tell the user to pull first.
- [ ] How do we track which comments have been "addressed" across multiple rework runs? Recommendation: use the PR's resolved-thread state on GitHub. The agent (or `--reply-to-comments`) marks threads resolved.
- [ ] Should the feedback prompt include the comment thread context (replies + reactions) or just the original comment? Recommendation: include the whole thread so the agent sees what's already been said.
- [ ] What about review comments that ask for design changes that affect the PRD itself (e.g. "this scope is too big, split it")? Out of scope for the agent — this PRD only handles tactical rework. Architectural rework requires a human to update the PRD doc first.

## Relationship to other PRDs

- **PRD-224.4** — keeps the worktree alive after `create_pr` so this PRD has something to resume
- **PRD-218** — streaming + transcripts mean rework runs are also visible and recorded
- **PRD-223** — system operations could later add `prd system run rework-all` that loops over all PRs needing rework
- **PRD-220** — graph execution + rework together would let "review feedback for one PRD triggers rework on its dependents" eventually

## References

- [`gh pr view --json comments`](https://cli.github.com/manual/gh_pr_view) — the data source
- PRD-510 false-success run — would have benefited from "rework based on PR feedback" if a reviewer had caught it
