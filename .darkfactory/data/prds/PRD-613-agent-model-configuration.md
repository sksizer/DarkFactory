---
id: PRD-613
title: "Agent Model Configuration and Fallback"
kind: feature
status: draft
priority: low
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/invoke.py
  - src/darkfactory/runner.py
  - src/darkfactory/config.py
  - src/darkfactory/workflow.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - agent
  - configuration
  - model
  - feature
value: 2
---

# Agent Model Configuration and Fallback

## Summary

Make agent model selection fully configurable with progressive specification. Default to easy out-of-the-box behavior (current Claude capability tiers), but allow users to override the capability-to-model mapping, specify alternative providers, and set per-task model overrides — all through `config.toml`.

## Status

**Rough draft.** Partial infrastructure already exists (`ModelConfig`, `resolve_config()`) but is disconnected from the runner.

## Current State

DarkFactory has scaffolding for model configuration that was never wired up:

- `config.py` defines `ModelConfig` with capability tiers (trivial→haiku, simple→sonnet, moderate→sonnet, complex→opus)
- `resolve_config()` supports user/project config cascade + env vars
- `init.py` scaffolds a commented-out `[model]` section in `config.toml`
- **None of this is used.** The runner reads a hardcoded `CAPABILITY_MODELS` dict in `invoke.py`
- Agent invocation is Claude Code only — no support for other providers

## Goals

### Progressive specification
The configuration should work at multiple levels of effort:

**Level 0 — Zero config (current default):**
Works out of the box. Hardcoded capability tiers map to Claude models. No config needed.

**Level 1 — Remap tiers:**
User overrides which model handles each capability tier in `config.toml`:
```toml
[model]
trivial = "haiku"
simple = "sonnet"
moderate = "sonnet"
complex = "opus"
```

**Level 2 — Per-task overrides:**
Specific workflow tasks can pin a model, overriding the tier mapping:
```toml
[model]
simple = "sonnet"
complex = "opus"

[model.overrides]
# Task name or slot reference → model
"planning.decompose" = "opus"    # Always use opus for planning
"task.implement" = "sonnet"      # Sonnet is enough for leaf tasks
```

**Level 3 — Alternative providers:**
For simple tasks, use a cheaper or local model instead of Claude:
```toml
[model]
trivial = "local:ollama/codellama"
simple = "openai:gpt-4o-mini"
moderate = "sonnet"
complex = "opus"
```

### Requirements

1. **Wire up existing config.** Connect `ModelConfig` and `resolve_config()` to the runner's `_pick_model()` function. The hardcoded `CAPABILITY_MODELS` dict becomes the default when no config is present.

2. **Capability tier remapping.** `[model]` section in `config.toml` overrides the default tier→model mapping. Validated at config load time via Pydantic.

3. **Per-task overrides.** `[model.overrides]` allows pinning specific tasks to specific models. Task identity is `workflow_name.task_name` (or similar addressing scheme). Overrides take priority over tier mapping.

4. **Provider abstraction.** Model strings gain a provider prefix: `claude:opus`, `openai:gpt-4o`, `local:ollama/codellama`. Bare names (e.g., `"sonnet"`) are shorthand for `claude:sonnet` for backwards compatibility. The invocation layer routes to the correct subprocess/API based on provider.

5. **Fallback chain.** If the preferred model is unavailable (API error, rate limit, local model not running), fall back to the next tier up or down. Configurable:
```toml
[model]
fallback = "up"    # On failure, try next higher tier
# fallback = "down"  # Try next lower tier
# fallback = "none"  # Fail hard
```

6. **CLI override preserved.** `--model` flag continues to work and takes highest priority, overriding all config.

### Provider Support (Progressive)

**Phase 1:** Claude only (current). Wire up config, make tiers configurable. Provider prefix optional.

**Phase 2:** OpenAI-compatible providers. Support `openai:model-name` prefix. Invoke via a generic API client or CLI wrapper.

**Phase 3:** Local models. Support `local:provider/model` prefix for locally-running models (Ollama, llama.cpp, etc.). Requires a different invocation path than Claude Code subprocess.

## Design Considerations

### Invocation abstraction
Currently, all agent invocation goes through `invoke_claude()` which shells out to `claude` CLI. Supporting other providers requires either:
- A provider-agnostic invocation interface that `invoke_claude()` becomes one implementation of
- Or wrapping other providers behind a Claude-compatible CLI interface

The first approach is cleaner but more work. The second is a pragmatic shortcut for providers that support OpenAI-compatible APIs.

### Prompt compatibility
Different models may need different prompt formatting. A task prompt optimized for Claude may not work well with a local model. This is a real problem for Level 3 but can be deferred — start with the assumption that prompts are model-agnostic and address compatibility issues as they arise.

### Cost tracking
With multiple providers at different price points, cost tracking becomes more valuable. Not in scope for this PRD but worth noting as a future enhancement.

## Open Questions

- What's the task addressing scheme for per-task overrides? `workflow.task_name`? Index-based? Something else?
- Should fallback be automatic (transparent retry on different model) or prompted (ask user)?
- How do we handle capability differences between providers? An opus-tier task sent to a local model may produce poor results.
- Should there be a "dry-run" mode that shows which model each task would use without executing?
- How does this interact with the retry system (PRD-609)? Should a model failure trigger a retry on a different model?

## Acceptance Criteria

(To be defined. Phase 1 — wiring up existing config — could be a quick win.)

## Assessment (2026-04-11)

- **Value**: 3/5 for Phase 1 (wire up existing config) / 2/5 for
  Phases 2–3 (multi-provider). Phase 1 closes a real debt — the
  scaffolding in `config.py` + `resolve_config()` currently does
  nothing at runtime because `runner._pick_model` reads hardcoded
  `CAPABILITY_MODELS` from `invoke.py`. Phases 2–3 are speculative
  (no real pain around "I need a non-Claude model today").
- **Effort**: Phase 1 = xs–s. Phases 2+3 = l.
- **Current state**: scaffolded. Config infrastructure exists and is
  unwired. The PRD's "phased specification" accurately describes the
  gap.
- **Gaps to fully implement Phase 1**:
  - Import `config.model` in `runner._pick_model` or `invoke.py`.
  - Replace the hardcoded `CAPABILITY_MODELS` lookup with a lookup
    against `config.model.<tier>`.
  - Fall back to hardcoded defaults if config is absent.
  - Support `--model` CLI override (already there — verify).
  - Tests for config override, default fallback, CLI override
    precedence.
- **Recommendation**: split — carve off Phase 1 as a standalone xs/s
  PRD and do-next it. Defer phases 2–3 indefinitely, revisit only
  if a real non-Claude use case appears. As written, the PRD wastes
  the Phase 1 quick win by bundling it with the multi-provider
  infrastructure investigation.
