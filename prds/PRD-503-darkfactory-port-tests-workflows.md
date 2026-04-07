---
id: "PRD-503"
title: "Port tests and workflows to darkfactory"
kind: task
status: ready
priority: high
effort: s
capability: simple
parent: "[[PRD-500-darkfactory-extraction]]"
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
  - extraction
  - tests
---

# Port tests and workflows to darkfactory

## Summary

Copy the test suite and **all** workflow directories (`default/`, `extraction/`, plus the `workflows/__init__.py` namespace marker and any per-workflow `__init__.py` files) into darkfactory, applying the same `prd_harness -> darkfactory` rename. After this PRD lands, the full test suite (218+ tests) runs green in darkfactory.

## Requirements

1. All test files from `tools/prd-harness/tests/` are copied to `darkfactory/tests/`:
   `conftest.py`, `__init__.py`, `test_prd.py`, `test_graph.py`, `test_containment.py`, `test_impacts.py`, `test_workflow.py`, `test_builtins.py`, `test_loader.py`, `test_assign.py`, `test_templates.py`, `test_invoke.py`, `test_runner.py`, `test_cli_workflows.py`, `test_cli_run.py`.
2. Every `from prd_harness.X import Y` in tests becomes `from darkfactory.X import Y`.
3. Every `from prd_harness import ...` becomes `from darkfactory import ...`.
4. **Every** workflow under `tools/prd-harness/workflows/` is copied to `darkfactory/workflows/`:
   - `default/workflow.py` + `default/prompts/{role,task,verify}.md`
   - `extraction/workflow.py` + `extraction/prompts/{role,task,verify}.md`
   - `workflows/__init__.py`, `workflows/default/__init__.py`, `workflows/extraction/__init__.py` (empty namespace markers required for mypy to distinguish duplicate `workflow` module names — see PRD-211/extraction-workflow lessons)
   - Any workflow added to the harness between now and when this PRD runs (do a fresh `ls workflows/` rather than hard-coding the list)
5. All workflow imports `from prd_harness.workflow import ...` become `from darkfactory.workflow import ...`.
6. All prompt files are copied verbatim — they don't reference the package name.
7. `uv run pytest` reports the same number of passing tests as the pumice-side harness (218+).
8. `uv run mypy src tests workflows` passes with `strict = true`.

## Technical Approach

Same mechanical copy + rename as PRD-502:

```bash
# Tests
mkdir -p ~/Developer/darkfactory/tests
cp tools/prd-harness/tests/*.py \
   ~/Developer/darkfactory/tests/

# Workflows — copy the entire tree (every workflow + __init__.py markers + prompts)
rm -rf ~/Developer/darkfactory/workflows
cp -R tools/prd-harness/workflows ~/Developer/darkfactory/workflows
# Strip the pycache that may have come along
find ~/Developer/darkfactory/workflows -name __pycache__ -type d -exec rm -rf {} +

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
- [ ] AC-2: `workflows/default/` and `workflows/extraction/` (and any other workflow present in pumice at port time) each have `workflow.py`, `__init__.py`, and `prompts/`.
- [ ] AC-3: `workflows/__init__.py` exists as a namespace marker.
- [ ] AC-4: `grep -rn "prd_harness" tests/ workflows/` returns no results.
- [ ] AC-5: `uv run prd list-workflows` shows every ported workflow.
- [ ] AC-6: `uv run pytest` passes (218+ tests).
- [ ] AC-7: `uv run mypy src tests workflows` passes with `strict = true`.

## References

- [[PRD-502-darkfactory-port-source]] — dependency
- [[PRD-504-darkfactory-cli-defaults]] — next step
