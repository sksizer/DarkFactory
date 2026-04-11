---
id: PRD-556
title: Split src/darkfactory/cli.py into a package of per-subcommand modules with colocated tests
kind: epic
status: in-progress
priority: medium
effort: l
capability: moderate
parent:
depends_on:
  - "[[PRD-549-builtins-package-split]]"
blocks:
  - "[[PRD-556.1-scaffold-cli-package]]"
  - "[[PRD-556.2-move-new]]"
  - "[[PRD-556.3-move-status]]"
  - "[[PRD-556.4-move-cleanup]]"
  - "[[PRD-556.5-move-next]]"
  - "[[PRD-556.6-move-validate]]"
  - "[[PRD-556.7-move-tree]]"
  - "[[PRD-556.8-move-children]]"
  - "[[PRD-556.9-move-orphans]]"
  - "[[PRD-556.10-move-undecomposed]]"
  - "[[PRD-556.11-move-conflicts]]"
  - "[[PRD-556.12-move-list-workflows]]"
  - "[[PRD-556.13-move-assign]]"
  - "[[PRD-556.14-move-normalize]]"
  - "[[PRD-556.15-move-plan]]"
  - "[[PRD-556.16-move-run]]"
  - "[[PRD-556.17-move-reconcile]]"
  - "[[PRD-556.18-final-cleanup]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-09'
tags:
  - refactor
  - tests
  - organization
  - cli
---

# Split `src/darkfactory/cli.py` into a package of per-subcommand modules

## Summary

`src/darkfactory/cli.py` is 1423 lines and holds 14 subcommand implementations plus all the argparse wiring and a dozen shared helpers. It's by far the largest module in `src/darkfactory/` and growing — every new feature (PRD-220 alone added ~200 lines) makes it worse.

Apply the PRD-549 convention: turn `cli.py` into a package, one submodule per subcommand, colocated unit tests, shared helpers in `_shared.py`, argparse wiring in `_parser.py`. The public entry point stays `darkfactory.cli:main`.

## Motivation

Same pattern as PRD-549, same arguments:

- **Diff noise.** Touching `cmd_run` scrolls past `cmd_status`, `cmd_validate`, and every argparse subparser in the same file.
- **Discovery.** "Where is the logic for `prd next`?" — a grep, not a filename.
- **Import overhead.** Every subcommand's dependencies (impacts, graph, graph_execution, runner, loader, assign, containment, …) get pulled in on every `prd` invocation even when the user only ran `prd status`.
- **Growth trajectory.** Every feature adds or extends a subcommand. PRD-220 added ~200 lines to `cmd_run`. Future PRDs will keep adding.
- **Test colocation.** `tests/test_cli_run.py`, `tests/test_cli_workflows.py`, etc. are monoliths too. Colocating per-subcommand tests gives the same navigation win as PRD-549's builtins split.

This is an **epic**, decomposable into parallel children the same way PRD-549 was. Conflict structure is also similar: all children modify the shrinking `cli.py`, which stress-tests the merge/rebase machinery (PRD-545/PRD-552).

## Target layout

```
src/darkfactory/
├── cli/
│   ├── __init__.py              # re-exports main, build_parser
│   ├── _parser.py               # build_parser() — all argparse wiring
│   ├── _shared.py               # _find_repo_root, _load, _default_prd_dir, etc.
│   ├── _shared_test.py
│   ├── main.py                  # entry point: main(argv) -> int
│   ├── main_test.py
│   ├── new.py                   # cmd_new + _slugify + _next_flat_prd_id
│   ├── new_test.py
│   ├── status.py                # cmd_status
│   ├── status_test.py
│   ├── next_cmd.py              # cmd_next  (next is a keyword in some contexts — underscore it)
│   ├── next_cmd_test.py
│   ├── validate.py              # cmd_validate
│   ├── validate_test.py
│   ├── tree.py                  # cmd_tree + _format_tree_node + _print_tree
│   ├── tree_test.py
│   ├── children.py              # cmd_children
│   ├── children_test.py
│   ├── orphans.py               # cmd_orphans
│   ├── orphans_test.py
│   ├── undecomposed.py          # cmd_undecomposed
│   ├── undecomposed_test.py
│   ├── conflicts.py             # cmd_conflicts
│   ├── conflicts_test.py
│   ├── list_workflows.py        # cmd_list_workflows
│   ├── list_workflows_test.py
│   ├── assign_cmd.py            # cmd_assign  (avoid collision with assign module)
│   ├── assign_cmd_test.py
│   ├── normalize.py             # cmd_normalize + _normalize_prd
│   ├── normalize_test.py
│   ├── plan.py                  # cmd_plan + _describe_task + _resolve_base_ref + _check_runnable
│   ├── plan_test.py
│   ├── run.py                   # cmd_run + _is_graph_target + _cmd_run_graph + _print_run_event
│   └── run_test.py
```

Public API preservation: `from darkfactory.cli import main` must keep working. `darkfactory.cli.__init__` re-exports it.

## Decomposition DAG

Same pattern as PRD-549:

- **A** — pytest config + colocated-test scaffolding. Already done by PRD-549.1; this PRD inherits whatever that lands.
- **B** — scaffold the `cli/` package: create `__init__.py`, move `_parser.py`, move `_shared.py`, move `main.py`. Empty functional change. Every existing import still resolves via re-exports.
- **C1…C14** — one child PRD per subcommand, each moving `cmd_<name>` + its exclusively-used helpers into its own submodule with a colocated `*_test.py`. Parallel.
- **D** — final cleanup: delete `cli.py` if it remains, confirm `cli/` is the single source of truth.

**DAG conflict note:** Same as PRD-549 — all children chip away at the shrinking `cli.py`. Same recommendation: accept the conflict, let the harness handle rebases via PRD-545/PRD-552 once they land, otherwise serialize the children.

## Shared helpers

- `_find_repo_root`, `_load`, `_default_prd_dir`, `_default_workflows_dir`, `_load_workflows_or_fail`, `_action_sort_key`, `_slugify` → `cli/_shared.py`.
- `_describe_task`, `_resolve_base_ref`, `_check_runnable` → stay with `plan.py` and `run.py` as needed (both use them — promote to `_shared.py` if both genuinely need them).

## Acceptance criteria

- [ ] AC-1: `src/darkfactory/cli/` exists as a package, `__init__.py` re-exports `main` and `build_parser`.
- [ ] AC-2: Every `cmd_<name>` function lives in its own submodule with a colocated `*_test.py`.
- [ ] AC-3: `build_parser()` lives in `cli/_parser.py` and is the single source of subcommand wiring.
- [ ] AC-4: `uv run prd <subcommand>` behavior is identical for every subcommand — no regressions.
- [ ] AC-5: All existing tests pass. Colocated tests cover the non-trivial branches of each subcommand.
- [ ] AC-6: `darkfactory.cli.cli` (the old module path) is no longer referenced; old imports have been migrated.
- [ ] AC-7: `just test && just lint && just typecheck && just format-check` clean at every child PRD merge.
- [ ] AC-8: Public API is unchanged — `from darkfactory.cli import main` still works.

## Open questions

- [ ] Does `tests/test_cli_run.py` get split into colocated tests under `src/darkfactory/cli/run_test.py`, or stay as an integration test file? Recommend: move the unit-y tests (args parsing, routing) to colocated; keep end-to-end happy-paths in `tests/`.
- [ ] `_parser.py` size. If `build_parser()` is still 200+ lines after the move, consider per-subcommand parser fragments that each module registers itself. Optional v2 cleanup.
- [ ] Interaction with PRD-549 — if 549 lands first and establishes the colocated-test convention, this PRD is cheaper. Ordering matters.

## References

- [[PRD-549-builtins-package-split]] — the template this epic follows.
- [[PRD-545-harness-driven-rebase-and-conflict-resolution]] — conflict handling across parallel children.
- [[PRD-552-merge-upstream-task]] — same.
- [[PRD-557-modularize-runner]] — sibling modularization.
- Current `src/darkfactory/cli.py` — 1423 lines, 14 subcommand implementations.
