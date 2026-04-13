---
id: "PRD-204"
title: "Workflow Assignment Logic"
kind: task
status: done
priority: high
effort: xs
capability: simple
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
blocks:
  - "[[PRD-206-list-workflows-assign-cli]]"
  - "[[PRD-210-runner]]"
impacts:
  - python/darkfactory/assign.py
  - tests/test_assign.py
workflow: null
target_version: null
created: 2026-04-07
updated: '2026-04-08'
tags:
  - harness
  - workflows
  - assignment
---

# Workflow Assignment Logic

## Summary

Pick which workflow applies to a given PRD. Resolution order: explicit frontmatter `workflow:` field (if set and exists) > highest-priority workflow whose `applies_to` returns true > `default` fallback.

## Requirements

1. `assign_workflow(prd, prds, workflows) -> Workflow` — returns the chosen workflow
2. Resolution priority (in order):
   - If `prd.workflow` is set and that workflow exists in `workflows`, return it
   - Otherwise, filter workflows where `applies_to(prd, prds)` is truthy; pick the highest `priority`, tiebreak alphabetically by name
   - Otherwise, return `workflows["default"]` if present
   - Otherwise, raise `KeyError`
3. Tolerate 1-arg `applies_to` lambdas (e.g. `lambda prd: ...`) via TypeError fallback
4. `assign_all(prds, workflows) -> dict[str, Workflow]` convenience helper for bulk assignment

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/assign.py`

```python
def assign_workflow(prd, prds, workflows):
    if prd.workflow and prd.workflow in workflows:
        return workflows[prd.workflow]
    matches = sorted(
        [w for w in workflows.values() if _matches(w, prd, prds)],
        key=lambda w: (-w.priority, w.name),
    )
    if matches:
        return matches[0]
    if "default" in workflows:
        return workflows["default"]
    raise KeyError(f"no workflow matches {prd.id}")

def _matches(workflow, prd, prds):
    try:
        return bool(workflow.applies_to(prd, prds))
    except TypeError:
        return bool(workflow.applies_to(prd))
```

**New file**: `tools/prd-harness/tests/test_assign.py`

- Explicit field wins
- Highest priority wins among applies_to matches
- Alphabetical tie-break on equal priority
- Default fallback
- `KeyError` when no match and no default
- 1-arg lambdas work

## Acceptance Criteria

- [ ] AC-1: Explicit `prd.workflow` beats predicate matching
- [ ] AC-2: Highest priority wins, alphabetical tiebreak
- [ ] AC-3: Default workflow is fallback
- [ ] AC-4: 1-arg and 2-arg `applies_to` both work
- [ ] AC-5: `assign_all` returns a dict of resolved assignments
- [ ] AC-6: `mypy --strict` passes
- [ ] AC-7: `pytest tests/test_assign.py` passes
