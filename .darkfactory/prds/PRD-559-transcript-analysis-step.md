---
id: PRD-559
title: Add transcript analysis step that surfaces problems and recommendations from agent runs
kind: feature
status: review
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-559.1-finding-dataclass-detector-registry]]"
  - "[[PRD-559.2-initial-detectors]]"
  - "[[PRD-559.3-prompt-template-and-config]]"
  - "[[PRD-559.4-builtin-entry-point]]"
  - "[[PRD-559.5-workflow-integration]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-09'
tags:
  - workflow
  - builtins
  - analysis
  - retro
---

# Transcript analysis step

## Summary

Every workflow run produces a JSONL transcript at
`.harness-transcripts/{prd_id}.log` that `commit_transcript` then copies into
`.darkfactory/transcripts/{prd_id}-{ts}.log`. Today we never look at it
again. This PRD adds a reusable `analyze_transcript` builtin that runs near
the end of every workflow, scans the transcript for problem signals, hands
the filtered findings to an LLM for narrative recommendations, and writes
the result both as a committed analysis file alongside the transcript and
as an addendum to the existing `summarize_agent_run` summary that surfaces
on stdout and in the PR body.

The point is to build a feedback loop: each PRD run leaves behind a short
"retro" so we can spot prompt confusion, ambiguous PRDs, allowlist friction,
and other process bugs *before* they accumulate across dozens of runs.

## Motivation

- We have ~20 transcripts already and no signal extraction. Patterns like
  "the agent always tries to commit" or "PRD X needed three retries because
  the technical approach was wrong" are invisible.
- Most issues live in the transcript JSONL — tool denials, sentinel
  failures, retries, repeated identical edits, large rate-limit bursts. A
  cheap deterministic scan can flag them without an LLM call.
- The judgment layer ("was the PRD ambiguous? did the agent fight the
  prompt?") is exactly the kind of thing an LLM is good at, but only if
  we filter first so we're not paying to re-parse 20k tokens of JSONL on
  every run.
- The optional output — a draft PRD capturing the recommended improvement
  — would let the harness feed itself: each run can leave behind a tiny
  improvement ticket for the next planning pass.

## Design

Two-stage analyzer:

1. **Stage 1 — deterministic scanner.** A pure-Python pass over the JSONL
   transcript that emits a list of `Finding` records. Each finding has a
   category, severity, short message, and (where applicable) a pointer to
   the transcript line. This is the filter step — cheap, deterministic,
   easy to test.
2. **Stage 2 — LLM narrative.** If the scanner finds anything above a
   noise threshold, hand the findings + a redacted slice of the transcript
   to a small agent invocation (Haiku) with a prompt that produces a short
   markdown retro: what went wrong, recommended fix, and an optional
   "would create PRD: ..." block.

### Stage 1 — extensible scanner

The scanner is a list of named detectors, each a small function
`(events: list[dict]) -> list[Finding]`. Detectors register via decorator
so adding a new check is one file:

```python
@detector("tool_denied")
def detect_tool_denied(events): ...
```

Initial detectors:

- `sentinel_failure` — final assistant message did not include
  `PRD_EXECUTE_OK` or returned `PRD_EXECUTE_FAILED`.
- `tool_denied` — JSONL events whose `type` indicates the harness blocked
  a tool call (e.g. `git commit` rejection).
- `retry_count` — count of harness-driven retries (transcript header
  records `task: implement-retry`; today max is 1, but the count is the
  signal).
- `repeated_edit` — same `Edit`/`Write` to the same file path back-to-back
  (sign the agent fought a lint or test).
- `large_thinking_burst` — single thinking block over N tokens (cheap
  proxy for "agent was confused").
- `forbidden_attribution_attempt` — same patterns as `lint_attribution`,
  but flagged advisory rather than fatal.
- `tool_overuse` — any tool count > configurable threshold (e.g. 50
  Read calls suggests poor scoping).

Future detectors (named here as scope markers, not for v1):

- `merge_conflict` — once the analyzer can run after `create_pr`, scrape
  PR check output for merge conflict signals.
- `flaky_test` — same test fails then passes within one run.

The detector registry should mirror the existing `BUILTINS` registry
shape so the extension pattern is familiar.

### Stage 2 — LLM narrative

Skip entirely if Stage 1 returns only `info`-severity findings. Default
threshold for firing Stage 2 is "any finding at `warning` severity or
above", configurable via `analysis.min_severity` in
`.darkfactory/config.toml`.

Otherwise, call `claude --print` (the same plumbing AgentTask uses) with:

- **Model selection — severity-tiered, config-driven.** Two config keys
  in `.darkfactory/config.toml`:
  - `analysis.model_default` (default: `haiku`) — used for runs whose
    highest finding severity is `warning`.
  - `analysis.model_severe` (default: `sonnet`) — used when any finding
    is `error` severity, so severe problems get a deeper read.
  Hardcoded fallback if neither key is set: Haiku for warnings, Sonnet
  for errors.
- Prompt: `prompts/analyze_transcript.md` placed adjacent to
  `analyze_transcript.py` under `src/darkfactory/builtins/` (colocated
  with the builtin code, not under a separate `prompts/` tree). This is
  the first builtin to ship with a prompt file; the convention going
  forward is "prompts live next to the code that loads them."
  Placeholders: `{{FINDINGS}}` and `{{TRANSCRIPT_EXCERPT}}`.
- Tools: read-only — `Read` only. The analyzer does not edit files; the
  builtin handles the file write itself.
- Output contract: markdown with a fixed shape (Summary / Findings /
  Recommendations / Suggested PRD). The builtin parses the "Suggested PRD"
  block but does not act on it for v1 (option C from the design
  discussion: leave the suggestion in the file, no auto-init).

### Outputs

- **Committed analysis file:** `.darkfactory/transcripts/{prd_id}-{ts}.analysis.md`
  alongside the transcript. Same staging path as `commit_transcript`.
- **PR body addendum:** appended to `ctx.run_summary` so the existing
  `create_pr` builtin picks it up. The addendum is short — title plus a
  bullet list of finding categories, with a pointer to the analysis file
  for detail. We do not dump the full retro into the PR body.
- **Stdout:** the existing `summarize_agent_run` already prints to stdout
  via `ctx.run_summary`. Appending here is enough.

### Failure mode

Analysis is advisory. If the transcript is missing, the scanner crashes,
or the agent invocation fails, log a warning and continue. Never fail the
workflow on analyzer error. Mirror the `commit_transcript` "no transcript
found, skip" pattern.

### Workflow integration

Add `BuiltIn("analyze_transcript")` to every workflow's task list,
positioned **after** `commit_transcript` (so the file exists in the
worktree) and **before** the final `commit` (so the analysis file lands
in the same commit as the transcript). For `default` that means inserting
between `commit_transcript` and `commit("ready for review")`.

Apply the same insertion to `planning` and `extraction` workflows.

## Target layout

```
src/darkfactory/builtins/
├── analyze_transcript.py            # builtin entry point + Finding dataclass
├── analyze_transcript_test.py
├── analyze_transcript_detectors.py  # detector registry + initial detectors
├── analyze_transcript_detectors_test.py
└── analyze_transcript_prompt.md     # Stage 2 prompt, adjacent to the code
```

The prompt file sits next to the builtin module rather than under a
sibling `prompts/` directory — this is the first builtin with a prompt
and the convention is "prompts live adjacent to the code that loads
them." `AgentTask` workflows still keep their `prompts/` subdirectory
because they have multiple composed prompts; this builtin has exactly
one.

## Acceptance criteria

- [ ] AC-1: `analyze_transcript` builtin is registered and callable from
      a workflow's task list.
- [ ] AC-2: Stage 1 scanner runs as pure Python with no subprocess or
      network calls. Unit-tested against fixture transcripts that exercise
      each initial detector.
- [ ] AC-3: Detector registry supports adding a new detector in one
      decorated function — demonstrated by the seven initial detectors
      and a test that registers a fake detector.
- [ ] AC-4: Stage 2 LLM call is skipped when no findings exceed the
      configured severity threshold (default: `warning`, set via
      `analysis.min_severity` in `.darkfactory/config.toml`). Verified by
      a test where the scanner returns only `info` findings and no
      `claude` subprocess fires.
- [ ] AC-4b: Stage 2 model is selected from config — `analysis.model_default`
      (default: `haiku`) for `warning`-severity runs, `analysis.model_severe`
      (default: `sonnet`) when any finding is `error` severity. Verified by
      tests that exercise both tiers.
- [ ] AC-5: When findings warrant Stage 2, the builtin writes
      `.darkfactory/transcripts/{prd_id}-{ts}.analysis.md` and stages it
      with `git add`.
- [ ] AC-6: `ctx.run_summary` is augmented with a short analysis section
      (title + finding-category bullets + pointer to the analysis file)
      so it surfaces in stdout and in the PR body via the existing
      `create_pr` builtin.
- [ ] AC-7: Missing transcript, scanner exception, or LLM-call failure
      all log a warning and return cleanly — the workflow does not fail.
- [ ] AC-8: The builtin is added to `default`, `planning`, and
      `extraction` workflows, positioned between `commit_transcript` and
      the final `commit`.
- [ ] AC-9: Dry-run mode logs what the builtin would do and does not
      invoke `claude` or write files.
- [ ] AC-10: `just test && just lint && just typecheck` clean.

## Open questions

- [ ] Transcript excerpt size — full transcript is often 20k+ tokens.
      Suggest: pass only the events tagged by Stage 1 findings plus their
      ±3 line neighbors, capped at ~4k tokens.
- [ ] When the analyzer is later moved to run *after* `create_pr` to pick
      up merge-conflict signals, where do the findings get written? PR
      comment? A second analysis file? Out of scope for v1.

## References

- `src/darkfactory/builtins/commit_transcript.py` — sibling builtin that
  this one runs after.
- `src/darkfactory/builtins/summarize_agent_run.py` — existing summary
  this builtin augments via `ctx.run_summary`.
- `src/darkfactory/builtins/_registry.py` — registry pattern to mirror
  for the detector registry.
- `src/darkfactory/workflows/default/workflow.py` — primary insertion
  site.
- `.darkfactory/transcripts/` — current corpus to use for fixture
  selection.
