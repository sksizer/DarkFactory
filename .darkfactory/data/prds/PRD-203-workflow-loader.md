---
id: "PRD-203"
title: "Workflow Loader"
kind: task
status: done
priority: high
effort: s
capability: moderate
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
blocks:
  - "[[PRD-206-list-workflows-assign-cli]]"
impacts:
  - python/darkfactory/loader.py
  - tests/test_loader.py
workflow: null
target_version: null
created: 2026-04-07
updated: '2026-04-08'
tags:
  - harness
  - workflows
  - loader
---

# Workflow Loader

## Summary

Discover workflows by scanning `workflows/*/workflow.py` and dynamically importing each. Returns a dict keyed by workflow name. Sets `workflow.workflow_dir` so AgentTask prompts can be resolved relative to the workflow's directory.

## Requirements

1. `load_workflows(workflows_dir: Path) -> dict[str, Workflow]` — scan and import
2. Each subdirectory under `workflows_dir` that contains a `workflow.py` is imported
3. The module must export a top-level `workflow` attribute that is a `Workflow` instance
4. `workflow.workflow_dir` is set to the subdirectory path
5. Import errors in one workflow.py don't prevent other workflows from loading — log the error and continue
6. Duplicate workflow names (same `workflow.name` in two modules) raise `ValueError`
7. Works when `workflows_dir` doesn't exist (returns empty dict)

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/loader.py`

- Use `importlib.util.spec_from_file_location` + `module_from_spec` + `spec.loader.exec_module`
- Generate unique module names like `prd_harness_workflow_{subdir_name}` to avoid collisions
- Insert into `sys.modules` so the workflow's own imports resolve
- Validate the loaded object with `isinstance(wf, Workflow)`
- Use `logging.getLogger("prd_harness.loader")` for error reporting

**New file**: `tools/prd-harness/tests/test_loader.py`

- Fixture: create a tmp directory with a valid `workflow.py`; verify it's loaded
- Fixture: create a tmp directory with broken syntax; verify it logs and skips
- Fixture: two subdirs with the same `workflow.name`; verify `ValueError`
- Empty / nonexistent directory → empty dict

## Acceptance Criteria

- [ ] AC-1: `load_workflows(dir)` returns `{}` for empty/missing directory
- [ ] AC-2: Valid workflow files are imported and returned keyed by name
- [ ] AC-3: `workflow_dir` is set to the subdirectory path on each loaded workflow
- [ ] AC-4: Syntax errors in one workflow don't break others
- [ ] AC-5: Duplicate names raise `ValueError`
- [ ] AC-6: `mypy --strict` passes
- [ ] AC-7: `pytest tests/test_loader.py` passes
