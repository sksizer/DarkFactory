---
id: PRD-611
title: "Conditional SDLC Checks by File Path"
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
  - src/darkfactory/config.py
  - src/darkfactory/workflow.py
  - src/darkfactory/runner.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - configuration
  - sdlc-slots
  - workflow
value: 2
---

# Conditional SDLC Checks by File Path

## Summary

Extend the `[sdlc-slots]` config (PRD-608) with conditional rules that add extra check commands when changed files match glob patterns. Base slots always run; conditional rules are additive and fire based on the changeset, orthogonal to which workflow is active.

## Status

**Rough draft.** Starting point design captured. Needs further exploration of interaction with custom workflows and edge cases.

## Motivation

Projects often have heterogeneous toolchains within a single repo. A Python backend with a Vue frontend needs different checks depending on what changed. Today, workflows run the same checks regardless of which files were touched. This wastes time (running backend tests when only frontend files changed) and misses checks (not running Vue linting when `.vue` files are modified).

## Design

### Config Schema

```toml
[sdlc-slots]
lint = "ruff check ."
test = "pytest"
format = "ruff format --check ."

[[sdlc-slots.conditional]]
when = "*.vue"
lint = "eslint --ext .vue ."
test = "vitest run"

[[sdlc-slots.conditional]]
when = "src/darkfactory/builtins/**"
test = "pytest tests/test_builtins.py"

[[sdlc-slots.conditional]]
when = "migrations/**"
test = ["pytest tests/test_migrations.py", "alembic check"]
```

### Semantics

1. **Base slots always run.** The `[sdlc-slots]` section from PRD-608 is unchanged — those commands execute on every workflow run.
2. **Conditional rules are additive.** When a rule's `when` glob matches any file in the changeset, its slot commands are appended to the base slot's commands for that run. They do not replace the base.
3. **`when` is a glob pattern** matched against the set of changed files (from `git diff`). If any changed file matches the glob, the rule activates.
4. **Multiple rules can fire.** If both `*.vue` and `migrations/**` match, both sets of additional commands run.
5. **Slot commands within a rule follow the same format as base slots** — string for single command, list of strings for multiple.
6. **Orthogonal to workflows.** Conditional rules apply based on the changeset, regardless of which workflow is executing. The workflow defines the lifecycle; conditional rules define what checks run within that lifecycle.

### Changeset Detection

The changeset is determined by comparing the working branch to the base ref:
- `git diff --name-only <base_ref>...HEAD` for committed changes
- Plus `git diff --name-only` for uncommitted changes
- The `ExecutionContext` already tracks `base_ref` — this extends it with a `changed_files: set[str]` field

### Execution Order

For a given slot (e.g., `test`):
1. Run base slot command(s)
2. For each matching conditional rule (in config order), run its additional command(s)
3. All commands must pass — any failure follows the same critical/skip logic from PRD-608

## Complexity Risks

### Interaction with custom workflows
Custom workflows may define their own `ShellTask` or `SdlcSlotTask` steps. Conditional rules should only affect `SdlcSlotTask` resolution — they should not inject commands into explicit `ShellTask` steps. This keeps the boundary clean: workflows own the structure, config owns the slot content.

### Rule explosion
A project with many conditional rules could become hard to reason about. For v1, keep it simple:
- No rule priorities or ordering beyond config file order
- No negation patterns (e.g., "when NOT matching X")
- No rule-level slot overrides (only additive)
- No conditional rules that disable base slots

These can be added later if real usage demands them.

### Performance
Each conditional rule requires a glob match against the full changeset. For repos with large changesets or many rules, this could be slow. Likely not an issue in practice — glob matching is fast and most projects will have a handful of rules.

## Open Questions

- Should conditional rules support `prepare` and `build` slots, or only verification slots (`lint`, `format`, `test`, `typecheck`)?
- Should there be a way to run only the conditional checks (skip base) for performance? e.g., "I only changed Vue files, don't run the full pytest suite"
- How does this interact with the retry system (PRD-609)? If a conditional check fails, which agent phase gets the retry?
- Should `prd setup` (PRD-608) have the ability to detect and suggest conditional rules based on project structure?

## Acceptance Criteria

(To be defined after design solidifies.)
