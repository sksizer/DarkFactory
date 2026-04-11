---
id: PRD-548
title: lint_attribution builtin — reject Claude/Anthropic credit before push
kind: task
status: done
priority: high
effort: s
capability: trivial
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/builtins.py
  - tests/test_builtins.py
  - workflows/default/workflow.py
  - workflows/extraction/workflow.py
  - workflows/planning/workflow.py
workflow:
target_version:
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - policy
---

# `lint_attribution` builtin — reject Claude/Anthropic credit before push

## Summary

The project's global rule is: **never credit Claude or Anthropic in commit messages, PR bodies, or run summaries.** Default Claude Code commit flows tack on a `Co-Authored-By: Claude ...` trailer, and subagents have been observed to do the same inside `retry_agent` cycles. Today the harness has no enforcement — bad trailers reach `origin` and PRs before anyone notices.

This PRD adds a new builtin, `lint_attribution`, that scans:

1. Every commit message in `{base_ref}..HEAD` on the workflow branch
2. `ctx.run_summary` (which feeds the PR body)
3. Commit messages produced via the `commit` builtin (scanned inline at format time)
4. PR title and body produced via the `create_pr` builtin (scanned inline)

against a list of forbidden patterns (`Co-Authored-By: Claude`, `@anthropic.com`, `Generated with Claude Code`, `🤖 Generated with`). Any match raises `RuntimeError` with a message naming the offending artifact and pattern, so the workflow aborts before `push_branch` / `create_pr` run.

We deliberately **fail loudly** rather than silently stripping trailers — silent stripping masks the underlying agent misbehaviour we want to notice and fix.

## Motivation

Silent rule violations:

- `Co-Authored-By: Claude ...` trailers have appeared on recent harness-produced commits despite CLAUDE.md explicitly forbidding them
- Once a bad trailer lands on `origin`, rewriting history is expensive and the PR already advertises the credit
- The rule lives in `~/.claude/CLAUDE.md` which the harness-run subagent should respect, but doesn't consistently

A post-build, pre-push guard is the right place: it catches drift from any source (main agent, subagents, future workflow authors) without coupling to any particular agent's prompt.

## Acceptance criteria

- [x] New builtin `lint_attribution` registered in `src/darkfactory/builtins.py`
- [x] Scans every commit in `{base_ref}..HEAD` using `git log --format=%H%x00%B%x1e` (robust against newlines in commit bodies)
- [x] Scans `ctx.run_summary` when non-empty
- [x] `commit` builtin inline-scans the formatted commit message before writing
- [x] `create_pr` builtin inline-scans title and body before shelling out to `gh`
- [x] Forbidden patterns: `Co-Authored-By:\s*Claude`, `Co-Authored-By:.*@anthropic\.com`, `Generated with .{0,20}Claude Code`, `🤖 Generated with` (all case-insensitive)
- [x] On match, raises `RuntimeError` with a source label (e.g. `"commit abc123 on branch-name"`) and the matched substring
- [x] Dry-run path is a no-op with an info log
- [x] Wired into `default`, `extraction`, and `planning` workflows immediately before `push_branch`
- [x] Unit tests cover: clean input passes, each forbidden pattern fails, dry-run skip, commit-range scan via real git repo fixture

## Out of scope

- Auto-rewriting / stripping offending trailers (deliberately rejected — see Summary)
- Blocking at `commit` time in the agent itself (handled by CLAUDE.md; this is the net)
- Patterns beyond Claude/Anthropic attribution
