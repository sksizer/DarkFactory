---
id: PRD-609
title: "Workflow Retry and Recovery Expansion"
kind: epic
status: draft
priority: low
effort: l
capability: complex
parent:
depends_on:
  - "[[PRD-608-project-toolchain-setup]]"
blocks: []
impacts:
  - python/darkfactory/runner.py
  - python/darkfactory/workflow.py
  - python/darkfactory/templates_builtin.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - workflow
  - retry
  - recovery
  - agent
  - feature
value: 2
---

# Workflow Retry and Recovery Expansion

## Summary

Expand DarkFactory's retry and recovery facility beyond the current single-retry-on-failure model. Allow richer step/DAG-level retry specification, configurable retry policies, and the ability to route failures back to specific earlier phases in multi-phase workflows.

## Status

**Rough draft / braindump.** Needs further discussion and design before implementation.

## Current State

The existing retry mechanism is limited:
- On deterministic (ShellTask) failure, the workflow retries by going back to the preceding agent task once
- No configuration of retry count, backoff, or which step to retry from
- No ability to specify "on failure of step X, go back to step Y" for complex workflows
- No distinction between transient failures (worth retrying) and permanent failures (don't waste time)

## Ideas and Requirements (Rough)

### Retry Configuration
- Per-task retry count (default: 1, configurable per task)
- Per-task retry policy: `retry_from` field specifying which task to resume from on failure
- Global workflow retry cap to prevent infinite loops

### DAG-Aware Recovery
- For complex multi-phase workflows with multiple agent phases, allow specifying which phase to return to on a downstream failure
- Example: phases A (plan) → B (implement) → C (lint) → D (test). If D fails, maybe retry from B (re-implement) rather than C (just re-lint)
- This implies the workflow DAG needs edges for failure paths, not just success paths

### Failure Classification
- Distinguish between types of failures:
  - **Agent failure** — agent couldn't complete the task (model error, timeout)
  - **Check failure** — deterministic check found issues (lint errors, test failures)
  - **Infrastructure failure** — transient issues (network, API rate limits)
- Different failure types may warrant different retry strategies

### Retry Context
- When retrying after a failure, the agent should receive context about what failed and why
- The failing step's output (error messages, test output, lint violations) should be passed to the retry agent
- Avoid the "do the same thing again" trap — the agent needs enough context to try a different approach

### Open Design Questions
- Should retry policies be defined in the workflow template or in config.toml?
- How does retry interact with the event log / transcript system?
- Should there be a "human in the loop" option where a failure pauses and asks the user before retrying?
- How do we prevent runaway retry loops from burning agent tokens?
- Should `SdlcSlotTask` failures (from PRD-608) use this same retry mechanism, or have their own simpler path?

## Acceptance Criteria

(To be defined after design discussion.)

## Open Questions

(Everything above is open — this is a braindump for future discussion.)

## Assessment (2026-04-11)

- **Value**: 2/5 — the PRD author self-flags this as "rough draft /
  braindump" with no AC list. The concrete pain is handled today by
  PRD-220's single-retry path; there's no incident driving the
  expansion beyond "what if."
- **Effort**: l (conjectural — no AC list means no real scope).
- **Current state**: greenfield. PRD-220's retry path exists; nothing
  from this PRD's expansion exists.
- **Gaps to fully implement**: design work itself is unfinished. The
  PRD is essentially an "ideas" document, not an implementation plan.
- **Recommendation**: defer — keep as idea capture, do not schedule
  until (a) PRD-608 lands so this PRD's `depends_on: PRD-608` becomes
  meaningful and (b) a real failure pattern emerges that PRD-220's
  single-retry doesn't handle. Consider downgrading to `kind: discuss`
  or "feature idea" to make clear this isn't an execution target.
