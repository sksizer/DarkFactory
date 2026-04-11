---
id: PRD-606
title: Allow task workflow agents to run git commit
kind: task
status: done
priority: high
effort: s
capability: simple
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/workflows/task/workflow.py
  - src/darkfactory/workflows/task/prompts/role.md
  - src/darkfactory/workflows/task/prompts/task.md
  - src/darkfactory/workflows/task/prompts/verify.md
workflow:
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - workflow
  - reliability
---

# Allow task workflow agents to run git commit

## Summary

The task workflow currently forbids the agent from running `git commit`.
This causes repeated failures when retry agents (spawned by
`on_failure="retry_agent"` shell tasks) fix an issue, stage it, but
cannot commit — the `git commit` command is denied by the permission
model, the agent exhausts its turns, and never emits the sentinel.
The PRD is then marked blocked even though the fix was correct.

Allowing the agent to commit lets it checkpoint work incrementally
during implementation and lets retry agents finalize their fixes. The
harness retains control of boundary commits (status transitions,
transcripts, PR creation) and can validate agent commits after the fact.

## Problem

Observed in PRD-556.8 (and reported as a recurring pattern):

1. `just typecheck` fails during the verification phase due to a
   pre-existing mypy error.
2. The retry agent correctly diagnoses and fixes the issue.
3. The retry agent stages the fix with `git add`.
4. The retry agent attempts `git commit` — denied 4 times.
5. The agent ends without emitting `PRD_EXECUTE_OK` or
   `PRD_EXECUTE_FAILED`.
6. The harness marks the PRD blocked with: `"retry agent failed: agent
   output contained no PRD_EXECUTE_OK or PRD_EXECUTE_FAILED sentinel"`.

Additionally, the verify prompt (`verify.md`) already instructs the
agent to "Stage and commit the fix" (step 4), contradicting the tool
allowlist that blocks `git commit`.

## Requirements

1. Add `Bash(git commit:*)` to the implement AgentTask's tool list in
   the task workflow.
2. Update `prompts/role.md` to remove the prohibition on `git commit`.
   Retain prohibitions on branching, pushing, and PR creation.
3. Update `prompts/task.md` to allow (but not require) incremental
   commits during implementation. The harness still makes the final
   boundary commits.
4. `prompts/verify.md` already instructs the agent to commit — no
   contradiction remains after requirements 1-2.
5. All existing tests pass.

## Technical Approach

### `src/darkfactory/workflows/task/workflow.py`

Add one line to the implement AgentTask tools list:

```python
tools=[
    # Read/write code and search
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    # Build/test commands
    "Bash(cargo:*)",
    "Bash(pnpm:*)",
    "Bash(just:*)",
    "Bash(uv:*)",
    # Git: the agent stages, inspects, and commits incremental work.
    # Branch creation, pushing, and PR creation are still owned by
    # the harness builtins.
    "Bash(git add:*)",
    "Bash(git rm:*)",
    "Bash(git commit:*)",
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
],
```

### `prompts/role.md`

Remove `git commit` from the "You MUST NOT" list. Keep branching,
pushing, and PR creation prohibited. Update the responsibilities
section to reflect that the agent may commit incrementally.

### `prompts/task.md`

Update step 4 ("Stage your changes") to allow optional commits. The
agent may commit after logical steps, but must still stage all final
changes. The harness makes additional boundary commits regardless.

## Acceptance Criteria

- [ ] AC-1: `Bash(git commit:*)` is in the implement AgentTask's tool list.
- [ ] AC-2: `role.md` no longer prohibits `git commit`. Branching, pushing, and PR prohibitions remain.
- [ ] AC-3: `task.md` allows incremental commits without requiring them.
- [ ] AC-4: No contradictions between prompt instructions and the tool allowlist.
- [ ] AC-5: All existing tests pass. `just test && just lint && just typecheck && just format-check` clean.
