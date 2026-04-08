---
id: "PRD-201"
title: "Workflow Dataclasses"
kind: task
status: done
priority: high
effort: s
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on: []
blocks:
  - "[[PRD-202-builtins-registry-stubs]]"
  - "[[PRD-203-workflow-loader]]"
  - "[[PRD-204-assignment-logic]]"
  - "[[PRD-207-prompt-templates]]"
  - "[[PRD-208-agent-invoke]]"
  - "[[PRD-210-runner]]"
impacts:
  - src/darkfactory/workflow.py
  - tests/test_workflow.py
workflow: null
target_version: null
created: 2026-04-07
updated: '2026-04-08'
tags:
  - harness
  - workflows
---

# Workflow Dataclasses

## Summary

Define the declarative types that workflow authors compose: `Task`, `BuiltIn`, `AgentTask`, `ShellTask`, `Workflow`, and `ExecutionContext`. Pure data — no behavior, no I/O. Foundational for everything downstream.

## Requirements

1. `Task` marker base class + three concrete subclasses: `BuiltIn(name, kwargs)`, `AgentTask(prompts, tools, model, retries, verify_prompts, sentinel_success, sentinel_failure, ...)`, `ShellTask(name, cmd, on_failure, env)`
2. `Workflow(name, description, applies_to, priority, tasks, workflow_dir)` — the top-level record
3. `ExecutionContext(prd, repo_root, workflow, base_ref, branch_name, worktree_path, cwd, agent_output, agent_success, pr_url, dry_run, logger)` — state threaded through task execution
4. `ExecutionContext.format_string(template)` — expands `{prd_id}`, `{prd_title}`, `{prd_slug}`, `{branch}`, `{base_ref}`, `{worktree}` placeholders
5. Type alias `AppliesToPredicate = Callable[[PRD, dict[str, PRD]], bool]` (two-argument signature for predicates that need the full PRD set)
6. Fully type-annotated; passes `mypy --strict`

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/workflow.py`

- `from __future__ import annotations` at the top
- `TYPE_CHECKING` import for `PRD` to avoid circular dependency with `prd.py`
- `Task` is a plain class (not dataclass) so subclass dataclasses don't inherit fields
- Each subclass uses `@dataclass` with `field(default_factory=list)` for mutable defaults
- `Workflow.applies_to` default is a module-level function `_default_applies_to(prd, prds) -> False` (not a lambda, for mypy clarity)
- `ExecutionContext.logger` uses `field(default_factory=lambda: logging.getLogger("prd_harness"))`

**New file**: `tools/prd-harness/tests/test_workflow.py`

Test that each dataclass constructs with defaults and with all fields set; verify `format_string` handles all placeholders.

## Acceptance Criteria

- [ ] AC-1: All six classes defined with the listed fields
- [ ] AC-2: `from prd_harness.workflow import Workflow, BuiltIn, AgentTask, ShellTask, ExecutionContext` works
- [ ] AC-3: `Workflow("default", tasks=[BuiltIn("foo")])` constructs successfully
- [ ] AC-4: `ExecutionContext(...).format_string("hello {prd_id}")` returns expanded string
- [ ] AC-5: `uv run mypy src/prd_harness/workflow.py` passes with zero errors
- [ ] AC-6: `uv run pytest tests/test_workflow.py` passes (at least 6 tests)
