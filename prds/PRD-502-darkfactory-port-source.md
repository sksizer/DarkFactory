---
id: "PRD-502"
title: "Port source code with prd_harness -> darkfactory rename"
kind: task
status: ready
priority: high
effort: s
capability: simple
parent: "[[PRD-500-darkfactory-extraction]]"
depends_on:
  - "[[PRD-501-darkfactory-scaffold]]"
blocks:
  - "[[PRD-503-darkfactory-port-tests-workflows]]"
  - "[[PRD-504-darkfactory-cli-defaults]]"
impacts:
  - (darkfactory repo) src/darkfactory/**
workflow: null
target_version: null
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - extraction
  - rename
---

# Port source code with prd_harness -> darkfactory rename

## Summary

Copy every file from `tools/prd-harness/src/prd_harness/` into `darkfactory/src/darkfactory/` and rename all internal `prd_harness` references to `darkfactory`. Mechanical find-and-replace across imports, type hints, log names, and `__name__` references.

## Requirements

1. All 13 Python files from `src/prd_harness/` are copied to `src/darkfactory/`:
   `__init__.py`, `__main__.py`, `cli.py`, `prd.py`, `graph.py`, `containment.py`, `impacts.py`, `workflow.py`, `builtins.py`, `runner.py`, `invoke.py`, `assign.py`, `loader.py`, `templates.py`.
2. All `from prd_harness.X import Y` and `from .X import Y` relative imports still resolve after rename.
3. All `from prd_harness import ...` full imports become `from darkfactory import ...`.
4. Logger name `"prd_harness"` → `"darkfactory"` (affects the default logger in `workflow.ExecutionContext` and the `"prd_harness.loader"` child logger).
5. Synthetic module names in `loader.py` (`_prd_harness_workflow_<name>`) become `_darkfactory_workflow_<name>`.
6. The package still exposes the same public API — no functions are renamed, only the package namespace.

## Technical Approach

The mechanical steps:

```bash
# Copy source tree
mkdir -p ~/Developer/darkfactory/src/darkfactory
cp tools/prd-harness/src/prd_harness/*.py \
   ~/Developer/darkfactory/src/darkfactory/

# Find-and-replace within darkfactory/src/darkfactory/
# Using find + sed (or a Python one-liner for safety):
cd ~/Developer/darkfactory
python3 -c "
import re
from pathlib import Path
for p in Path('src/darkfactory').rglob('*.py'):
    text = p.read_text()
    # Package-qualified imports
    text = text.replace('from prd_harness', 'from darkfactory')
    text = text.replace('import prd_harness', 'import darkfactory')
    # Logger names
    text = text.replace('getLogger(\"prd_harness\")', 'getLogger(\"darkfactory\")')
    text = text.replace('\"prd_harness.', '\"darkfactory.')
    # Synthetic module names in loader
    text = text.replace('_prd_harness_workflow_', '_darkfactory_workflow_')
    p.write_text(text)
"
```

Verification:

```bash
cd ~/Developer/darkfactory
grep -rn "prd_harness" src/ || echo "clean"
```

Should print `clean` — no references should remain.

Then:

```bash
uv sync
uv run python -c "import darkfactory; from darkfactory.workflow import Workflow; print('ok')"
```

Should print `ok` if the package imports cleanly.

## Acceptance Criteria

- [ ] AC-1: `src/darkfactory/` contains all 13 source files.
- [ ] AC-2: `grep -rn "prd_harness" src/` returns no results.
- [ ] AC-3: `uv run python -c "import darkfactory"` succeeds.
- [ ] AC-4: `uv run python -c "from darkfactory.workflow import Workflow, BuiltIn, AgentTask, ShellTask"` succeeds.
- [ ] AC-5: `uv run mypy src/darkfactory` passes with `strict = true` (tests come in PRD-503).

## References

- [[PRD-501-darkfactory-scaffold]] — dependency
- [[PRD-503-darkfactory-port-tests-workflows]] — next step
