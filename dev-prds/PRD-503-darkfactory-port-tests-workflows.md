---
id: "PRD-503"
title: "Port tests and workflows to darkfactory"
kind: task
status: ready
priority: high
effort: s
capability: simple
parent: "[[PRD-500-darkfactory-migration]]"
depends_on:
  - "[[PRD-502-darkfactory-port-source]]"
blocks:
  - "[[PRD-504-darkfactory-cli-defaults]]"
impacts:
  - (darkfactory repo) tests/**
  - (darkfactory repo) workflows/**
workflow: null
target_version: null
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - migration
  - tests
---

# Port tests and workflows to darkfactory

## Summary

Copy the test suite and the `workflows/default/` directory into darkfactory, applying the same `prd_harness -> darkfactory` rename. After this PRD lands, the full test suite (~200 tests) runs green in darkfactory.

## Requirements

1. All test files from `tools/prd-harness/tests/` are copied to `darkfactory/tests/`:
   `conftest.py`, `__init__.py`, `test_prd.py`, `test_graph.py`, `test_containment.py`, `test_impacts.py`, `test_workflow.py`, `test_builtins.py`, `test_loader.py`, `test_assign.py`, `test_templates.py`, `test_invoke.py`, `test_runner.py`, `test_cli_workflows.py`, `test_cli_run.py`.
2. Every `from prd_harness.X import Y` in tests becomes `from darkfactory.X import Y`.
3. Every `from prd_harness import ...` becomes `from darkfactory import ...`.
4. `workflows/default/workflow.py` is copied to `darkfactory/workflows/default/workflow.py` and the imports `from prd_harness.workflow import ...` become `from darkfactory.workflow import ...`.
5. All three prompt files (`role.md`, `task.md`, `verify.md`) are copied verbatim — they don't reference the package name.
6. `uv run pytest` reports the same number of passing tests as the pumice-side harness (200+).
7. `uv run mypy src tests workflows` passes with `strict = true`.

## Technical Approach

Same mechanical copy + rename as PRD-502:

```bash
# Tests
mkdir -p ~/Developer/darkfactory/tests
cp tools/prd-harness/tests/*.py \
   ~/Developer/darkfactory/tests/

# Workflows
mkdir -p ~/Developer/darkfactory/workflows/default/prompts
cp tools/prd-harness/workflows/default/workflow.py \
   ~/Developer/darkfactory/workflows/default/workflow.py
cp tools/prd-harness/workflows/default/prompts/*.md \
   ~/Developer/darkfactory/workflows/default/prompts/

# Rename in tests and workflows
cd ~/Developer/darkfactory
python3 -c "
from pathlib import Path
for p in list(Path('tests').rglob('*.py')) + list(Path('workflows').rglob('*.py')):
    text = p.read_text()
    text = text.replace('from prd_harness', 'from darkfactory')
    text = text.replace('import prd_harness', 'import darkfactory')
    p.write_text(text)
"

grep -rn "prd_harness" tests/ workflows/ || echo "clean"
```

Then run the test suite:

```bash
uv run pytest          # expect 200+ pass
uv run mypy src tests workflows  # expect clean
```

The `conftest.py` uses relative imports from `.conftest` — those are unaffected (they refer to the tests package, not the source package).

## Acceptance Criteria

- [ ] AC-1: `tests/` has all 15 test files from the pumice harness.
- [ ] AC-2: `workflows/default/workflow.py` + 3 prompt files present.
- [ ] AC-3: `grep -rn "prd_harness" tests/ workflows/` returns no results.
- [ ] AC-4: `uv run pytest` passes (200+ tests).
- [ ] AC-5: `uv run mypy src tests workflows` passes with `strict = true`.

## References

- [[PRD-502-darkfactory-port-source]] — dependency
- [[PRD-504-darkfactory-cli-defaults]] — next step
