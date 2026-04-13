---
id: PRD-542
title: Scale agent task timeouts by estimated effort
kind: feature
status: done
priority: medium
effort: s
capability: simple
parent:
depends_on: []
blocks:
  - "[[PRD-542.1-timeout-resolution-module]]"
  - "[[PRD-542.2-integrate-timeout-into-runner]]"
  - "[[PRD-542.3-graceful-timeout-handling]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-09'
tags:
  - harness
  - feature
---

# Scale agent task timeouts by estimated effort

## Summary

The harness currently enforces a single hard timeout (600s) on every agent task invocation regardless of the work it represents. This causes false-negative timeouts on legitimately longer runs — PRD-541 (effort: m) finished its agent loop successfully in ~770s but was killed and reported as `failure_reason: timeout after 600s`, throwing away a completed `result` event the harness had already received. We should scale the timeout from the PRD's `effort` (and optionally `capability`) field so small work fails fast and larger work has room to breathe.

## Motivation

- **False failures destroy completed work.** PRD-541's agent loop finished successfully, but the harness wrapper killed it before the post-run bookkeeping could land. The implementation had to be recovered manually from the worktree.
- **One-size-fits-all is wrong in both directions.** 600s is too long for a trivial `effort: xs` task that hung (we want fast failure) and too short for an `effort: l` epic. A single number cannot serve both.
- **The information already exists.** Every PRD declares `effort` (xs/s/m/l/xl) and `capability` (simple/moderate/complex). The harness can read these without any new user input.

## Requirements

### Functional

1. **Effort → timeout mapping** with sensible defaults, e.g.:
   - `xs` → 5 min
   - `s`  → 10 min
   - `m`  → 20 min
   - `l`  → 40 min
   - `xl` → 75 min
   (Exact numbers TBD; tune from real run data.)
2. **Capability multiplier** (optional, applied on top): `simple` ×1.0, `moderate` ×1.25, `complex` ×1.5.
3. **Per-PRD override:** a PRD may set `timeout_minutes:` in frontmatter to override the computed value entirely. Useful escape hatch.
4. **Global config override:** the timeout table lives in config (likely `.darkfactory/config.toml`) so users can tune without editing code.
5. **CLI override:** `--timeout <minutes>` flag on `prd run` wins over everything else.
6. **Logging:** when a task starts, log the resolved timeout and where it came from (default / capability-adjusted / PRD frontmatter / CLI flag) so failures are diagnosable.
7. **Graceful timeout handling:** if the agent process *has* already emitted a terminal `result` event when the timeout fires, treat the run as complete rather than failed. (The PRD-541 incident is exactly this case.)

### Non-Functional

1. Mapping logic lives in one small module so it can be unit-tested with table-driven tests.
2. No network or external state; pure function of PRD frontmatter + config.

## Technical Approach

- Add `darkfactory/timeouts.py` (or fold into existing config module) exposing `resolve_timeout(prd, config, cli_override) -> int` returning seconds.
- Resolution order (highest wins): CLI flag > PRD frontmatter `timeout_minutes` > config table lookup by effort × capability multiplier > built-in defaults.
- Wherever the harness currently passes `timeout=600000` to its agent invocation, replace with the resolved value.
- In the timeout handler, before marking the run as failed, scan the captured stdout for a terminal `{"type":"result", ...}` line. If present, prefer its `is_error`/`subtype` over the timeout verdict.

## Acceptance Criteria

- [ ] AC-1: Timeout for an agent task is computed from the PRD's `effort` and `capability` fields, not hardcoded.
- [ ] AC-2: PRD frontmatter `timeout_minutes:` overrides the computed value.
- [ ] AC-3: `prd run --timeout N` overrides everything.
- [ ] AC-4: Default mapping table is configurable via `.darkfactory/config.toml`.
- [ ] AC-5: When a task starts, the resolved timeout and its source are logged.
- [ ] AC-6: If the agent emitted a terminal `result` event before the timeout fires, the run is reported as success/failure based on that event, not as a timeout.
- [ ] AC-7: Unit tests cover every effort value, capability multiplier, frontmatter override, and CLI override path.

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- OPEN: Exact default minute values per effort tier — start with the proposal above and tune from observed run data.
- OPEN: Should `xl` even have a ceiling, or should very large work be uncapped (rely on user Ctrl-C)?
- OPEN: Should the harness emit a warning when a run finishes within 10% of its timeout, as a "you should bump this" signal?
- DEFERRED: Adaptive learning — recording actual durations per PRD and auto-tuning the table.

## References

- Incident: PRD-541 agent loop completed in ~770s but was killed at 600s; staged work was recovered manually. See `.harness-agent-output.log` from that run for the terminal `result` event that was discarded.
