---
id: PRD-632
title: Reorganize workflow and operation definitions into prd/ and project/ namespaces
kind: task
status: review
priority: medium
effort: l
capability: complex
parent: null
depends_on: []
blocks: []
impacts:
  - python/darkfactory/workflow/definitions/
  - python/darkfactory/loader.py
  - python/darkfactory/config/_paths.py
  - python/darkfactory/config/_init.py
  - python/darkfactory/system.py
  - python/darkfactory/cli/system.py
  - python/darkfactory/cli/_parser.py
  - python/darkfactory/cli/main.py
  - python/darkfactory/cli/discuss.py
  - python/darkfactory/runner.py
  - python/darkfactory/operations/system_builtins.py
  - python/darkfactory/operations/gather_prd_context.py
  - python/darkfactory/operations/discuss_prd.py
  - python/darkfactory/operations/commit_prd_changes.py
  - python/darkfactory/commands/discuss/operation.py
  - tests/test_cli_system.py
  - tests/test_system.py
  - tests/test_system_runner.py
  - tests/test_system_builtins.py
  - .darkfactory/operations/
workflow: task
assignee: null
reviewers: []
target_version: null
created: 2026-04-12
updated: '2026-04-12'
tags:
  - architecture
  - refactor
---

# Reorganize workflow and operation definitions into prd/ and project/ namespaces

## Summary

Move built-in project operations from `.darkfactory/operations/` into `python/darkfactory/workflow/definitions/project/` and nest the existing PRD workflows under `python/darkfactory/workflow/definitions/prd/`. This gives the definitions directory a clear two-namespace layout (`prd/` vs `project/`) instead of mixing PRD workflows at the top level while project operations live in an unrelated data directory.

## Motivation

Today the codebase has two kinds of task definitions that live in unrelated locations with different discovery mechanisms:

| Kind | Current location | Discovered by | Entry file |
|------|-----------------|---------------|------------|
| PRD workflows | `src/…/workflow/definitions/{name}/` | `load_workflows()` scanning for `workflow.py` | `workflow.py` |
| Project operations | `.darkfactory/operations/{name}/` | `load_operations()` scanning for `operation.py` | `operation.py` |

This creates several problems:

1. **Built-in project operations live in a data directory.** The three operations in `.darkfactory/operations/` (plan, audit-impacts, verify-merges) are first-party code that ships with the tool, yet they sit alongside user config and PRD data. They should be versioned with the package.

2. **No namespace separation in definitions/.** All six PRD workflows (default, extraction, planning, planning_review, rework, task) sit at the top level of `definitions/`. When project operations join them, the flat list becomes harder to navigate.

3. **Init doesn't scaffold the operations directory.** `prd init` creates `.darkfactory/workflows/` but not `.darkfactory/operations/`, and there's no mechanism to seed example operations for users to reference.

## Requirements

### Structural changes

1. **Create `definitions/prd/`** — Move all existing PRD workflow subdirectories into it:
   - `definitions/default/` → `definitions/prd/default/`
   - `definitions/extraction/` → `definitions/prd/extraction/`
   - `definitions/planning/` → `definitions/prd/planning/`
   - `definitions/planning_review/` → `definitions/prd/planning_review/`
   - `definitions/rework/` → `definitions/prd/rework/`
   - `definitions/task/` → `definitions/prd/task/`

2. **Create `definitions/project/`** — Move the three built-in project operations from `.darkfactory/operations/` into the package:
   - `.darkfactory/operations/plan/` → `definitions/project/plan/`
   - `.darkfactory/operations/audit-impacts/` → `definitions/project/audit-impacts/`
   - `.darkfactory/operations/verify-merges/` → `definitions/project/verify-merges/`
   
   The entry file stays `operation.py` (not renamed to `workflow.py`) since these are `ProjectOperation` instances, not `Workflow` instances.

3. **Add `definitions/prd/__init__.py` and `definitions/project/__init__.py`** as empty package markers. Update `definitions/__init__.py` to reflect the new structure.

### Loader changes

4. **Update `builtin_workflows_dir()`** — Point at `definitions/prd/` instead of `definitions/`. This is the only change needed since `load_workflows()` already scans subdirectories generically.

5. **Add `builtin_operations_dir()` and `user_operations_dir()`** — `builtin_operations_dir()` returns `definitions/project/`, mirroring the `DARKFACTORY_BUILTINS_DIR` override pattern. `user_operations_dir()` returns `~/.config/darkfactory/operations/` (via `user_config_dir()`), mirroring the existing `user_workflows_dir()` in `config/_paths.py`.

6. **Update `load_operations()` to scan three layers** — Operation discovery currently only scans `.darkfactory/operations/`. It should now scan three layers, matching the `load_workflows()` design:
   - **Built-in**: `definitions/project/` (shipped with the package)
   - **User**: `~/.config/darkfactory/operations/` (personal operations shared across projects)
   - **Project**: `.darkfactory/operations/` (project-specific, extends built-in and user layers)
   
   Name collisions across any layers raise `ValueError` (see Req 9). Missing layers are silently skipped (not an error).

### Init changes

7. **Add `.darkfactory/operations/` to `_REQUIRED_DIRS`** in `config/_init.py` so `prd init` scaffolds it.

8. **Seed a sample operation** — On init, write a `hello/operation.py` into `.darkfactory/operations/`. This is a real, loadable operation that shows up in `prd project list` so users can see the authoring format in action. Users delete or replace it when they're ready.

### Name collision policy

9. **Error on name collision** across any operation layers (built-in, user, project), matching the existing workflow loader policy (`ValueError`). If a user wants to replace a built-in, they must use a different name. This keeps behavior predictable and avoids silent shadowing bugs.

### Discovery path configuration

10. **Add `[paths]` to config** — `config.toml` gains explicit paths for project-level discovery directories:

    ```toml
    [paths]
    workflows = ".darkfactory/workflows"
    operations = ".darkfactory/operations"
    ```

    These replace the implicit path derivation in `cli/main.py`. The loader reads them from config; CLI flags still override.

### Execution context

11. **Operation shell tasks run with `operation_dir` as cwd** — When executing a `ShellTask` within a project operation, the working directory must be set to the operation's directory (`operation.operation_dir`). This lets operations reference sibling scripts with relative paths (e.g., `python check.py` instead of hardcoding an absolute path). This is a behavioral change required to make moved operations work correctly.

### Helper exports

12. **Add `get_builtin_operations()`** — Mirror `get_builtin_workflows()` in `definitions/__init__.py`. Returns `dict[str, ProjectOperation]` from the built-in project layer only.

### CLI subcommand rename

13. **Rename `prd system` → `prd project`** — The CLI subcommand name should match the new categorization. This touches:
    - **`cli/system.py` → `cli/project.py`** — Rename the module. Rename functions `cmd_system_list` → `cmd_project_list`, `cmd_system_describe` → `cmd_project_describe`, `cmd_system_run` → `cmd_project_run`, and the helper `_describe_system_task` → `_describe_project_task`.
    - **`cli/_parser.py`** — Update the subcommand registration: parser name `"system"` → `"project"`, help text `"Discover and run system operations"` → `"Discover and run project operations"`, imports from `cli.project` instead of `cli.system`, and the `--operations-dir` help text.
    - **`tests/test_cli_system.py` → `tests/test_cli_project.py`** — Rename the test file and update all internal references (`test_system_*` → `test_project_*`, `_base_args()` subcommand string).

### Type and module rename

14. **Rename `SystemOperation` → `ProjectOperation` and `SystemContext` → `ProjectContext`** — Align the type names with the new categorization. This touches:
    - **`system.py` → `project.py`** — Rename the module. Rename the two dataclasses and update the module docstring. Logger default name changes from `"darkfactory.system"` to `"darkfactory.project"`.
    - **`runner.py`** — Rename `run_system_operation()` → `run_project_operation()` and `_system_compose_prompt()` → `_project_compose_prompt()`. Update all type annotations.
    - **`operations/system_builtins.py` → `operations/project_builtins.py`** — Rename the module. Update all `SystemContext` annotations to `ProjectContext`. Rename prefixed functions: `system_load_review_prds()` → `project_load_review_prds()`, `system_load_prds_by_status()` → `project_load_prds_by_status()`.
    - **All importers** (~20 files) — Update `from darkfactory.system import ...` → `from darkfactory.project import ...` across source and test files. Key files: `loader.py`, `cli/project.py`, `cli/discuss.py`, `operations/gather_prd_context.py`, `operations/discuss_prd.py`, `operations/commit_prd_changes.py`, `commands/discuss/operation.py`.
    - **Test files** — Rename `tests/test_system.py` → `tests/test_project.py`, `tests/test_system_runner.py` → `tests/test_project_runner.py`, `tests/test_system_builtins.py` → `tests/test_project_builtins.py`. Update all type references within.
    - **Operation definition files** — Update `from darkfactory.system import SystemOperation` → `from darkfactory.project import ProjectOperation` in all three built-in operations and the example seed template.

## Technical Approach

### File moves

Mostly `git mv` operations. The `verify-merges` operation is an exception: its `operation.py` contains a hardcoded shell path (`python .darkfactory/operations/verify-merges/check.py`). After the cwd change (Req 11), this becomes `python check.py` since shell tasks will execute relative to `operation_dir`.

### Loader refactor

`load_operations()` currently takes a single `operations_dir`. Expand it to accept optional layers, or add a wrapper `discover_operations()` that scans built-in, user, and project layers (matching the `load_workflows()` pattern).

```python
def builtin_operations_dir() -> Path:
    override = os.environ.get("DARKFACTORY_BUILTINS_OPERATIONS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "workflow" / "definitions" / "project"

def load_operations(
    operations_dir: Path | None = None,
    *,
    include_builtins: bool = True,
    include_user: bool = True,
) -> dict[str, ProjectOperation]:
    """Discover operations across built-in, user, and project layers."""
    ...
```

### Type and module rename

Mechanical find-and-replace across ~20 files. The renames are:

| Old | New |
|-----|-----|
| `system.py` (module) | `project.py` |
| `SystemOperation` | `ProjectOperation` |
| `SystemContext` | `ProjectContext` |
| `run_system_operation()` | `run_project_operation()` |
| `_system_compose_prompt()` | `_project_compose_prompt()` |
| `operations/system_builtins.py` | `operations/project_builtins.py` |
| `system_load_review_prds()` | `project_load_review_prds()` |
| `system_load_prds_by_status()` | `project_load_prds_by_status()` |
| `tests/test_system.py` | `tests/test_project.py` |
| `tests/test_system_runner.py` | `tests/test_project_runner.py` |
| `tests/test_system_builtins.py` | `tests/test_project_builtins.py` |

No field changes on the dataclasses — just the class names and the module they live in.

### Call site updates

- `cli/system.py` → `cli/project.py` — rename module, update `load_operations()` call to pass all three layers.
- `cli/main.py` derives `operations_dir` from implicit path — update to read from config `[paths]` first, then fall back to default.
- `cli/discuss.py` — update `SystemContext` → `ProjectContext` import and usage.
- `definitions/__init__.py` — add `get_builtin_operations()` alongside existing `get_builtin_workflows()`.
- `operations/` builtins — update all `SystemContext` type annotations to `ProjectContext`.
- `commands/discuss/operation.py` — update `SystemOperation` → `ProjectOperation` import.
- Any test that patches `load_operations` or references `.darkfactory/operations/` paths needs updating.
- The `DARKFACTORY_BUILTINS_DIR` env var override (used by tests) should remain functional. Add an analogous `DARKFACTORY_BUILTINS_OPERATIONS_DIR` or make the existing var scope both.

### Shell task cwd change

Project operation `ShellTask` execution currently inherits the process cwd (typically repo root). Update the runner to set `cwd=operation.operation_dir` when executing shell tasks within a project operation. This is required for `verify-merges` (and any future operation that references sibling files) to work after the move.

### Init seeding

Add a minimal sample operation template:

```python
# .darkfactory/operations/hello/operation.py
"""Sample project operation — delete or replace this directory with your own.

Project operations run across the whole repository (not per-PRD).
Run with: prd project run hello
"""

from darkfactory.project import ProjectOperation
from darkfactory.workflow import ShellTask

operation = ProjectOperation(
    name="hello",
    description="Sample operation — replace with your own.",
    tasks=[
        ShellTask("greet", cmd="echo 'Hello from darkfactory operations'", on_failure="fail"),
    ],
)
```

This is a real loadable operation visible in `prd project list`. Users delete or replace it when ready.

## Out of scope

- Renaming `operation.py` → `workflow.py` or unifying `ProjectOperation` and `Workflow` into a single type. PRD-631's context unification (`RunContext`) may make this natural as a follow-on, but it's a separate architectural decision.
- Changing the `ProjectOperation` or `ProjectContext` dataclass field shapes (fields stay the same, only names change).

## Acceptance Criteria

- [ ] AC-1: `python/darkfactory/workflow/definitions/prd/` contains all 6 PRD workflows, discoverable by `load_workflows()`.
- [ ] AC-2: `python/darkfactory/workflow/definitions/project/` contains the 3 built-in project operations (plan, audit-impacts, verify-merges), discoverable by `load_operations()`.
- [ ] AC-3: `.darkfactory/operations/` is scaffolded by `prd init` and seeded with a `hello/` operation visible in `prd project list`.
- [ ] AC-4: Name collision across any operation layers (built-in, user, project) raises `ValueError`.
- [ ] AC-5: `prd project list` shows operations from all three layers (built-in, user, project).
- [ ] AC-6: `prd project run plan --target PRD-X` works with the operation at its new location.
- [ ] AC-7: All existing tests pass. `uv run pytest && uv run ruff check && uv run mypy src tests` clean.
- [ ] AC-8: The import hygiene test (`test_import_hygiene.py`) passes — no new cross-package private imports.
- [ ] AC-9: `config.toml` `[paths]` section controls project-level discovery directories for workflows and operations.
- [ ] AC-10: `verify-merges` operation works at its new location — `check.py` is invoked via relative path from `operation_dir` cwd.
- [ ] AC-11: `get_builtin_operations()` is exported from `definitions/__init__.py` and returns the 3 built-in project operations.
- [ ] AC-12: `prd project list`, `prd project describe`, and `prd project run` work as the renamed CLI subcommand. `prd system` is no longer recognized.
- [ ] AC-13: `SystemOperation` → `ProjectOperation` and `SystemContext` → `ProjectContext` renamed throughout. `from darkfactory.project import ProjectOperation` is the canonical import. No references to the old `darkfactory.system` module remain in source or tests.
- [ ] AC-14: `run_system_operation()` → `run_project_operation()` renamed in `runner.py`. All call sites updated.
- [ ] AC-15: `user_operations_dir()` exists in `config/_paths.py`. Operations in `~/.config/darkfactory/operations/` are discovered by `load_operations()` and visible in `prd project list`.

## Resolved Questions

- RESOLVED: Name collisions between built-in and project operations raise `ValueError` (same as workflows). Consistent, predictable, no silent shadowing.
- RESOLVED: Seed operation uses `hello/` directory name. Avoids reserving a generic name like `example` that could collide with future built-ins.
- RESOLVED: Keep `Workflow` and `ProjectOperation` as separate types in this PRD. PRD-631 is converging their execution contexts; type unification (single base type) is a natural follow-on but out of scope here.
- RESOLVED: Rename `SystemOperation` → `ProjectOperation`, `SystemContext` → `ProjectContext`, and the `system.py` module → `project.py` to align types with the new categorization. ~20 files impacted by import updates.
- RESOLVED: Shell tasks in project operations execute with `operation_dir` as cwd, enabling relative paths to sibling scripts.
