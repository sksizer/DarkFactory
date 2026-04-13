---
id: PRD-610
title: "Agent Substitution for SDLC Slots"
kind: feature
status: draft
priority: low
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-608-project-toolchain-setup]]"
blocks: []
impacts:
  - src/darkfactory/workflow.py
  - src/darkfactory/runner.py
  - src/darkfactory/templates_builtin.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - workflow
  - agent
  - sdlc-slots
  - feature
value: 2
---

# Agent Substitution for SDLC Slots

## Summary

Allow SDLC slots to optionally fall back to an agent-based task when no deterministic tool is configured. The workflow author opts in per-slot via `SdlcSlotTask(slot="lint", agent_substitute=True)`. When the slot is absent from config and substitution is enabled, an agent performs a "soft" version of that check instead of skipping or failing.

## Status

**Rough draft / idea capture.** Not yet validated as valuable. Needs discussion on whether agent-based substitutes provide enough signal to justify the cost.

## Concept

For projects that lack a specific tool (e.g., no linter configured), an agent could perform a degraded version of that check:
- No linter → agent reviews code for common issues
- No formatter → agent reviews for formatting consistency
- No type checker → agent reviews for type-safety concerns

This is lower confidence than a real tool but better than silently skipping the step entirely.

### Per-Slot Opt-In

Substitution is configured per-slot in the workflow template, not globally:
```python
SdlcSlotTask(slot="lint", critical=False, agent_substitute=True)
```

Interaction with config:
- Slot configured with command(s) → run commands (agent substitute never activates)
- Slot set to `false` → skip (user explicitly opted out, no substitute)
- Slot absent + `agent_substitute=True` → invoke agent substitute
- Slot absent + `agent_substitute=False` → normal behavior (skip or fail based on `critical`)

## Related Ideas: Standalone Agent Check Tasks

Beyond substitution for missing tools, there may be value in agent-based checks that don't have a deterministic equivalent:

### Code Review Agent
A local agent task that performs a focused code review on the diff before PR creation. Not a substitute for human review, but catches obvious issues:
- Unused imports/variables the linter might miss
- Logic errors in new code
- Missing error handling at system boundaries
- Inconsistencies with surrounding code patterns

### Idioms Agent
A local agent task that reviews code for language/framework idiom adherence:
- Python: are we using idiomatic patterns? (e.g., list comprehensions vs. loops, context managers, etc.)
- Framework-specific: are we following the project's established patterns?
- Could be informed by project-specific style guidelines in a config file

These could be standalone workflow steps rather than substitutes for missing slots — they provide value even when all deterministic tools are configured.

## Open Questions

- Is agent substitution valuable enough to justify the token cost? A linter runs in milliseconds; an agent review takes minutes and costs money.
- How do we measure the quality of agent-based checks vs. real tools?
- Should agent substitutes produce structured output (like lint violations) or freeform text?
- For the code-review and idioms agents: should these be built-in workflow steps or user-configurable?
- How do these interact with the retry system (PRD-609)?

## Acceptance Criteria

(To be defined after value is validated.)

## Assessment (2026-04-11)

- **Value**: 2/5 — the PRD author explicitly flags this as "not yet
  validated as valuable." The concrete example ("no linter configured
  → agent reviews code") is strictly worse than "no linter configured
  → be honest about it." Token cost dominates value.
- **Effort**: m — new `agent_substitute` flag on `SdlcSlotTask`, new
  workflow prompt bundle, new fallback path in the runner.
- **Current state**: greenfield. Blocked on PRD-608 which is itself
  deferred.
- **Gaps**: all of it.
- **Recommendation**: defer — drop if PRD-608 ships in a reduced scope
  that doesn't include substitution. Do not invest design effort
  here without first proving value on a single real adopter who
  wants it.
