---
id: PRD-612
title: "Agent-Assisted Toolchain Detection"
kind: feature
status: draft
priority: low
effort: s
capability: moderate
parent:
depends_on:
  - "[[PRD-608-project-toolchain-setup]]"
blocks: []
impacts:
  - python/darkfactory/toolchain/__init__.py
  - python/darkfactory/cli/setup.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - toolchain
  - agent
  - onboarding
  - feature
value: 2
---

# Agent-Assisted Toolchain Detection

## Summary

Add an optional agent-based detection step to the `prd setup` wizard (PRD-608) that searches the codebase to determine SDLC slot commands. Can run upfront as an alternative to deterministic-only detection, or at the end to fill in slots the static detectors missed.

## Status

**Rough draft.** Straightforward extension of PRD-608's detection engine.

## Concept

The deterministic detection engine (PRD-608) works well for conventional projects — standard file names, standard tool configs. But some projects have unusual structures, custom scripts, or tools the static detectors don't know about. An agent can read the codebase and figure out what commands to run.

### Two Entry Points

**Upfront (opt-in):** User chooses agent-assisted detection instead of or in addition to deterministic detection at the start of setup.

```
$ prd setup
  Detection mode:
    [d] Deterministic only (fast, conventional projects)
    [a] Agent-assisted (searches codebase, slower but thorough)
    [b] Both (deterministic first, agent fills gaps)
```

**Gap-filling (prompted):** After deterministic detection, if any standard slots are unresolved, the wizard offers to run the agent to try to fill them.

```
  Detected:
    Lint:       ruff check .
    Test:       pytest
    Format:     (not detected)
    Typecheck:  (not detected)

  2 slots unresolved. Run agent detection to find them? [y/N]
```

### What the Agent Does

1. Reads project manifest files, scripts, CI configs, and READMEs
2. Searches for commands that look like they fulfill standard SDLC slots
3. Returns a mapping of slot names to suggested commands with confidence and reasoning
4. Results are presented to the user for confirmation — never written to config automatically

### Agent Output Format

The agent should return structured output (not freeform text) so the wizard can integrate results into the normal flow:

```
slot: format
command: "black --check ."
confidence: high
reasoning: "Found black in dev dependencies (pyproject.toml) and .pre-commit-config.yaml runs black"

slot: typecheck
command: "pyright"
confidence: medium
reasoning: "pyrightconfig.json exists but no explicit typecheck script found"
```

## Open Questions

- Should the agent have access to the deterministic detection results as context? (Probably yes — avoids re-discovering what static detection already found.)
- How do we scope the agent's search? Full codebase is expensive. Maybe limit to config files, scripts, CI, and top-level docs.
- Should agent suggestions carry lower default confidence in the wizard UI (e.g., marked with a warning)?

## Acceptance Criteria

(To be defined after PRD-608 is implemented.)

## Assessment (2026-04-11)

- **Value**: 2/5 — useful only when the deterministic detection
  engine from PRD-608 misses something. PRD-608 isn't scheduled;
  this is speculative scaffolding for speculative scaffolding.
- **Effort**: s — relatively small given PRD-608's detector registry.
- **Current state**: greenfield.
- **Gaps**: all of it.
- **Recommendation**: defer — only schedule if PRD-608 lands AND a
  real project produces an unresolved-slot case that static
  detection can't handle.
