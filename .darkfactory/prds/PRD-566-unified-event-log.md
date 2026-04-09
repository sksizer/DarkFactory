---
id: PRD-566
title: Unified structured event log for harness execution
kind: feature
status: in-progress
priority: high
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/runner.py
  - src/darkfactory/graph_execution.py
  - src/darkfactory/invoke.py
  - src/darkfactory/builtins/commit_transcript.py
  - .darkfactory/events/
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: '2026-04-09'
tags:
  - harness
  - observability
  - diagnostics
---

# Unified structured event log for harness execution

## Summary

Replace the current agent-only transcript files with a unified JSONL event log that captures every meaningful harness event: DAG decisions, workflow task transitions, builtin side-effects, shell task output, and agent stream events. Every event carries flat correlation fields (`session_id`, `prd_id`, `scope`, `task`) so logs are self-describing and filterable without stateful parsing. One file per PRD execution attempt, stored at `.darkfactory/events/` in the repo root (gitignored by default, opt-in commit via config).

## Motivation

Today we have zero visibility into what the harness itself does. Agent transcripts capture Claude Code's stream-json output, but nothing records:

- Which workflow step failed and why
- Shell task output (test/lint failures)
- Builtin side-effects (status transitions, commit SHAs, worktree paths)
- Graph executor decisions (which PRD was picked, skipped, or blocked, and why)
- The final verdict that caused a PRD to be marked `blocked`

When PRD-565.1 and PRD-565.2 were marked `blocked` despite their agents succeeding, there was no way to determine which post-agent step failed without manually reproducing the run. The failure reason was computed, printed to stderr, and lost.

This is especially critical before parallel execution (PRD-551) lands — debugging interleaved parallel runs without structured logs would be nearly impossible.

## Requirements

### Event log format

1. Every event is a single JSON line with these standard envelope fields:
   - `ts` — ISO-8601 timestamp with millisecond precision
   - `session_id` — unique identifier for the CLI invocation (e.g. `s-20260409-140455-a3f2`)
   - `prd_id` — the PRD this event relates to (may be null for session-level events)
   - `scope` — one of `"session"`, `"dag"`, `"workflow"`, `"task"`
   - `type` — event type name (see event catalog below)

2. Events are append-only, written in real-time as execution proceeds. One file per PRD execution attempt. No separate session file — reconstruct session view by globbing files with the same `session_id`.

3. Agent stream-json events from Claude Code are wrapped in the standard envelope:
   ```jsonl
   {"ts": "...", "session_id": "...", "prd_id": "PRD-565.1", "scope": "task", "type": "agent_event", "task": "implement", "event": {<original stream-json object>}}
   ```

### Event catalog

#### Session scope

- `session_start` — CLI invocation begins. Fields: `command`, `args`, `strategy` (rooted/queue).
- `session_finish` — CLI invocation ends. Fields: `completed`, `failed`, `skipped` (counts).

#### DAG scope

- `prd_picked` — graph executor selected a PRD to run. Fields: `prd_id`, `base_ref`, `workflow`.
- `prd_skipped` — graph executor skipped a PRD. Fields: `prd_id`, `reason`.
- `prd_finished` — workflow completed for a PRD. Fields: `prd_id`, `success`, `failure_reason`, `pr_url`.
- `prd_blocked` — PRD marked as blocked after failure. Fields: `prd_id`, `reason`.

#### Workflow scope

- `workflow_start` — `run_workflow` begins. Fields: `prd_id`, `workflow`, `branch_name`, `worktree_path`.
- `task_start` — a workflow task begins. Fields: `task`, `kind` (builtin/shell/agent), plus kind-specific fields (`cmd` for shell, `model` for agent).
- `task_finish` — a workflow task ends. Fields: `task`, `kind`, `success`, `duration_ms`, `detail`.
- `workflow_finish` — `run_workflow` ends. Fields: `success`, `failure_reason`, `steps` (summary array).

#### Task scope

- `agent_event` — wrapped Claude Code stream-json event. Fields: `task`, `event` (original object).
- `shell_output` — stdout/stderr from a shell task. Fields: `task`, `stream` (stdout/stderr), `text`.
- `builtin_effect` — notable side-effect from a builtin. Fields: `task`, `effect` (e.g. `"set_status"`, `"commit"`, `"push"`), `detail` (e.g. `{"from": "ready", "to": "in-progress"}`, `{"sha": "abc123"}`).

### File organization

4. Event logs live at `<repo_root>/.darkfactory/events/{prd_id}-{timestamp}.jsonl`. This is outside all worktrees so files survive worktree cleanup.

5. `.darkfactory/events/` is gitignored by default. Transcripts may contain file contents, internal paths, credentials in environment output, or other sensitive data that should not land in an OSS repository.

6. For PRDs that are skipped before any workflow runs (e.g. "upstream blocked"), the graph executor still creates a minimal event file containing the `prd_skipped` event so the record exists.

7. Session-level events (`session_start`, `session_finish`) are written to every per-PRD file that participates in that session. This is mildly redundant but means any single file is self-contained — you can understand a PRD's execution without cross-referencing.

### Migration

8. The current `.harness-transcripts/` directory and its write path in `runner._run_agent` are replaced by the new event log writer. The directory can be removed after migration.

9. The `commit_transcript` builtin is renamed to `commit_events` and becomes opt-in via a config key (`[events] commit = true` in `.darkfactory/config.toml`). Default is false. When enabled, it copies the event log into the worktree for committing. When disabled (default), it is a no-op.

10. PRD-559 (transcript analysis) should consume the new event format. The analyzer's input shape changes from raw agent stream-json to the unified log. This PRD does not implement that migration — PRD-559 should adapt its detectors to the new schema.

### Writer API

11. Introduce an `EventWriter` class that the runner and graph executor use:
    - `EventWriter(repo_root, session_id, prd_id)` — opens the file for append
    - `writer.emit(scope, type, **fields)` — appends one event line with envelope fields auto-populated
    - `writer.close()` — flushes and closes the file handle
    - Thread-safe for a single PRD (one writer per PRD, no cross-PRD contention)

12. The `EventWriter` is created by `run_workflow` and threaded through the execution context so builtins, shell tasks, and agent invocations can emit events. The graph executor creates writers for DAG-level events.

13. Agent stream events are emitted by `invoke_claude` via the writer rather than buffering to a separate transcript file. The existing real-time stderr streaming (styled output) is unchanged — the event log is a parallel write path, not a replacement for live output.

## Technical Approach

### EventWriter (new module: `src/darkfactory/event_log.py`)

```python
class EventWriter:
    def __init__(self, repo_root: Path, session_id: str, prd_id: str): ...
    def emit(self, scope: str, type: str, **fields) -> None: ...
    def close(self) -> None: ...
```

File path: `repo_root / ".darkfactory" / "events" / f"{prd_id}-{timestamp}.jsonl"`

Each `emit()` call writes one line: `json.dumps({"ts": now_iso(), "session_id": ..., "prd_id": ..., "scope": scope, "type": type, **fields}) + "\n"` and flushes.

### Integration points

**`runner.run_workflow`** — creates an `EventWriter`, stores it on `ExecutionContext`. Emits `workflow_start` at the top, `task_start`/`task_finish` around each `_dispatch` call, `workflow_finish` at the end.

**`runner._run_agent`** — passes the writer to `invoke_claude`. No longer writes to `.harness-transcripts/`.

**`runner._run_shell`** — captures stdout/stderr and emits `shell_output` events. Emits `task_finish` with exit code and truncated output.

**`invoke_claude`** — accepts an optional `EventWriter`. For each stream-json line parsed, emits an `agent_event` wrapping the original object. Existing stderr styling is unchanged.

**`graph_execution.execute_graph`** — accepts a `session_id` (generated at the CLI layer). For each PRD picked/skipped/blocked, creates a minimal `EventWriter` for that PRD and emits the DAG-level events.

**Builtins** — builtins that produce notable side-effects (`set_status`, `commit`, `push_branch`, `create_pr`) emit `builtin_effect` events via `ctx.event_writer`. Builtins without interesting side-effects (e.g. `summarize_agent_run`) don't need to emit.

### ExecutionContext changes

Add `event_writer: EventWriter | None` to `ExecutionContext`. The writer is `None` during dry-run and in tests that don't opt into event logging.

### .gitignore

Add `.darkfactory/events/` to the project `.gitignore`.

## Acceptance Criteria

- [ ] AC-1: Running `prd run PRD-X --execute` on a single PRD produces a `.darkfactory/events/PRD-X-{ts}.jsonl` file.
- [ ] AC-2: The event file contains `workflow_start`, `task_start`/`task_finish` for every workflow step, and `workflow_finish` events with correct `success` and `failure_reason` fields.
- [ ] AC-3: Agent stream-json events appear as `agent_event` entries with the original event preserved in the `event` field.
- [ ] AC-4: Shell task stdout/stderr appears in `shell_output` events. On failure, the `task_finish` event includes the exit code and truncated output in `detail`.
- [ ] AC-5: Builtin side-effects (`set_status`, `commit`, `push_branch`, `create_pr`) emit `builtin_effect` events with structured `detail`.
- [ ] AC-6: Graph execution (`prd run PRD-epic --execute`) produces one event file per PRD. DAG-level events (`prd_picked`, `prd_skipped`, `prd_blocked`) appear in the relevant PRD's file.
- [ ] AC-7: All files from a single CLI invocation share the same `session_id`. Running `jq -s '[.[] | select(.scope == "dag")]' .darkfactory/events/PRD-565.*` reconstructs the full DAG decision history.
- [ ] AC-8: `.darkfactory/events/` is listed in `.gitignore`.
- [ ] AC-9: The `commit_events` builtin is a no-op unless `[events] commit = true` is set in `.darkfactory/config.toml`.
- [ ] AC-10: `.harness-transcripts/` is no longer written to. Existing files are not deleted (manual cleanup).
- [ ] AC-11: `EventWriter.emit()` flushes after each write so events are visible immediately during long-running agent tasks.
- [ ] AC-12: Dry-run mode (`prd run PRD-X` without `--execute`) does not produce event files.
- [ ] AC-13: Existing tests pass without modification (event writer is `None` in test contexts that don't opt in).

## Notes

- JSONL is heavier than flat logs but enables rich post-mortem analysis with `jq`. The tradeoff is worth it — these files are diagnostic artifacts, not hot-path data.
- The flat-fields-everywhere design (no spans) is deliberate preparation for parallel execution (PRD-551). Every event is self-describing and can be written from any thread without coordinating open/close state.
- PRD-559 (transcript analysis) will need to adapt its detectors to consume `agent_event` wrappers instead of raw stream-json. That adaptation should be scoped as part of PRD-559, not this PRD.
- Session-level events are duplicated across per-PRD files. This is a small cost for the benefit of making each file fully self-contained.
