---
id: PRD-223
title: "System operations: reuse the workflow harness for non-PRD-bound tasks"
kind: epic
status: review
priority: medium
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-222-general-purpose-tool]]"
blocks:
  - "[[PRD-223.1-system-operation-core]]"
  - "[[PRD-223.2-system-cli]]"
  - "[[PRD-223.3-bulk-mutation-builtins]]"
  - "[[PRD-223.5-audit-impacts-operation]]"
  - "[[PRD-223.6-planning-as-system-op]]"
impacts: []
workflow:
target_version:
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - workflow
  - system
---

# System operations: reuse the workflow harness for non-PRD-bound tasks

## Summary

Today the harness only knows one shape of work: run one workflow against one specific PRD, in a worktree, ending in a PR. That's exactly right for *implementing* PRDs, but it leaves no place for **system-level operations** that touch many PRDs (or none) and don't fit the "one branch per PRD" lifecycle.

This PRD introduces a sibling concept — `SystemOperation` — that reuses the existing primitives (`AgentTask`, `ShellTask`, `BuiltIn`, capability→model mapping, sentinel parsing, retry logic) but runs against a different `ExecutionContext` shape: no specific target PRD, optionally read-only, with output that's either a report or a single batched PR rather than per-PRD branches.

The motivating example is **`reconcile-status`**: walk every PRD in `review` state, check git history to see if its implementing branch was merged to main, optionally have an agent verify the merge actually does what the PRD specified, then either flip those PRDs to `done` (in a single batched PR) or report what would change. This is the kind of meta-task that `prd run` can't model today.

## Motivation

### What's awkward about today's model

`Workflow` + `ExecutionContext` assume one PRD per execution:

- `ctx.prd: PRD` is a single value, not a set
- `ctx.worktree_path` is one branch named after that PRD
- `ctx.branch_name` is `prd/PRD-X-slug`
- The teardown phase commits, pushes, and opens a PR for that one PRD

That's correct for "implement PRD-X". It's wrong for:

- "**Reconcile statuses**": walk N PRDs, check N branches, mutate N status fields, output one PR
- "**Audit impacts**": walk all PRDs, check that declared impact paths exist on disk, produce a report
- "**Plan an epic**": walk one epic, create N child PRDs (this is the planning workflow from the original arch plan — same shape as system ops, not the same as default workflow)
- "**Decompose**" / "**summarize**" / "**lint-prds**" / "**find-orphans**": all read-only or read-then-batch-mutate

### What we want to keep reusing

The harness has built-up infrastructure that's valuable for system tasks too:

- **AgentTask** — invoke Claude Code with composed prompts and a tool allowlist
- **ShellTask** — run a deterministic command, with retry-on-failure semantics
- **BuiltIn** — registered helpers like `commit`, `push_branch`, `create_pr`
- **Capability → model mapping** — a system task can declare `complex` and get opus
- **Sentinel parsing** — agent reports back via `PRD_EXECUTE_OK`
- **Streaming output** — see what's happening in real time
- **Process locking** — prevent concurrent runs (PRD-217)

The right answer is "reuse all of this with a different context shape", not "build a parallel system".

## Design

### New concept: `SystemOperation`

```python
# src/darkfactory/system.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .workflow import Task


@dataclass
class SystemOperation:
    """A reusable harness pipeline that doesn't target a single PRD.

    Unlike a ``Workflow``, a SystemOperation:
    - Has no ``applies_to`` predicate — it's invoked by name via
      ``prd system <name>``
    - Receives a ``SystemContext`` instead of a per-PRD context
    - May mutate many PRDs in one run (or none)
    - Produces zero or one PRs at the end (deterministic batching, not
      per-PRD branches)
    """

    name: str
    description: str
    tasks: list[Task]
    requires_clean_main: bool = True  # safety: refuse if main has uncommitted changes
    creates_pr: bool = False           # if True, the operation ends in commit + push + PR
    pr_title: str | None = None        # template, e.g. "chore: reconcile PRD statuses"
    pr_body: str | None = None         # template
```

### New context: `SystemContext`

```python
# src/darkfactory/system.py (continued)

@dataclass
class SystemContext:
    """ExecutionContext for system operations.

    Differs from the per-PRD ExecutionContext:
    - No single ``prd`` field — instead ``prds`` is the full set
    - No ``worktree_path`` — system ops run in the source repo (or in
      a single dedicated worktree for ops with ``creates_pr=True``)
    - ``targets`` is a derived field operations populate during their
      run, listing which PRDs they touched
    """

    repo_root: Path
    prds: dict[str, PRD]
    operation: SystemOperation
    cwd: Path
    dry_run: bool = True
    logger: logging.Logger = field(...)
    # Output channels
    targets: list[str] = field(default_factory=list)  # PRDs the op touched
    report: list[str] = field(default_factory=list)   # human-readable output lines
    pr_url: str | None = None
    # Side channels for tasks
    _shared_state: dict[str, Any] = field(default_factory=dict)
```

### CLI surface

```
prd system list                       # show available operations
prd system describe <name>            # show description + task list
prd system run <name> [--execute]     # dry-run by default; --execute to mutate
```

System ops are NOT in `prd next` / `prd plan` / `prd run` — those are PRD-bound. Keeps the user's mental model clean: "PRDs are work I'm doing, system ops are things I'm doing TO the PRD set."

### How tasks adapt

- **AgentTask** works as-is — it composes a prompt and runs an agent. The prompts can read from `ctx.prds` instead of `ctx.prd`.
- **ShellTask** works as-is — it's just a subprocess.
- **BuiltIn** works with mild adaptation — most builtins (`commit`, `push_branch`, `create_pr`) operate on `ctx.cwd`, which is well-defined for system ops. `set_status` would need a per-PRD variant or be invoked once per target.
- **New BuiltIn**: `set_status_bulk(targets: list[str], to: Status)` for the reconcile case.

### How operations are loaded

Same loader pattern as workflows. Operations live under `.darkfactory/operations/` in the target project (PRD-222's convention — this PRD depends on 222 landing first specifically to avoid a migration step later):

```
.darkfactory/operations/
├── reconcile-status/
│   ├── operation.py        # exposes `operation = SystemOperation(...)`
│   └── prompts/
│       └── verify-merge.md
├── audit-impacts/
│   └── operation.py
└── lint-prds/
    └── operation.py
```

`loader.py` gains a `load_operations(operations_dir)` function symmetric to `load_workflows`.

### Worked example: `reconcile-status`

```python
# operations/reconcile-status/operation.py

from darkfactory.system import SystemOperation
from darkfactory.workflow import BuiltIn, AgentTask, ShellTask

operation = SystemOperation(
    name="reconcile-status",
    description=(
        "Walk every PRD in `review` state, check git history for the "
        "merge of its implementing branch into main, and mark merged "
        "PRDs as `done`. Optionally has an agent verify the merge "
        "matches the PRD's intent before marking."
    ),
    creates_pr=True,
    pr_title="chore: reconcile PRD statuses for merged work",
    pr_body=(
        "Auto-generated by `prd system run reconcile-status`. "
        "Marks PRDs as done where their implementing branch has been "
        "merged to main.\n\n"
        "Touched PRDs:\n{targets}"
    ),
    tasks=[
        # Phase 1: deterministic git scan
        BuiltIn("system_load_review_prds"),  # populates ctx._shared_state['candidates']
        BuiltIn("system_check_merged"),       # for each candidate, git log --grep <branch>
        # Phase 2: optional agent verification
        AgentTask(
            name="verify-merges",
            prompts=["prompts/verify-merge.md"],
            tools=["Read", "Glob", "Grep", "Bash(git log:*)", "Bash(git show:*)"],
            model_from_capability=False,
            model="sonnet",
            retries=0,
        ),
        # Phase 3: deterministic mutation
        BuiltIn("system_mark_done"),  # mutates the source repo's PRD files
        # Phase 4: standard teardown
        BuiltIn("commit", kwargs={"message": "chore: reconcile PRD statuses"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
```

The deterministic builtins (`system_load_review_prds`, `system_check_merged`, `system_mark_done`) do most of the work. The agent task is optional belt-and-suspenders — it reads each candidate's merged commit and confirms the changes match the PRD's acceptance criteria, raising on a mismatch.

### Variations on the same operation

- `prd system run reconcile-status` (default `--dry-run`): prints a report of which PRDs would be marked done
- `prd system run reconcile-status --execute`: actually creates the PR
- `prd system run reconcile-status --no-agent`: skip the agent verify step entirely (deterministic only)

## Proposed decomposition (child PRDs)

This is an epic. Suggested breakdown:

- **PRD-223.1 — Core abstraction**: `SystemOperation`, `SystemContext`, `system.py` module, loader extension
- **PRD-223.2 — `prd system` CLI subcommand**: `list`, `describe`, `run`
- **PRD-223.3 — Bulk-mutation builtins**: `set_status_bulk` and any other shared system builtins
- **~~PRD-223.4 — `reconcile-status` operation~~**: **moved to [[PRD-224-harness-invariants-honest-state]] child 224.7**. Same item from two angles; track once, not twice.
- **PRD-223.5 — `audit-impacts` operation**: read-only report of declared-vs-actual file paths
- **PRD-223.6 — Planning workflow as system operation**: re-cast the planning workflow (from the original architecture plan) as a SystemOperation since it's the same shape — operates on one PRD as input, creates many as output

## Acceptance Criteria

- [ ] AC-1 (post 223.1+223.2): `prd system list` shows `reconcile-status` and any other registered ops
- [ ] AC-2 (post 223.3+223.4): `prd system run reconcile-status` (dry-run) prints "would mark PRD-X, PRD-Y as done" without modifying anything
- [ ] AC-3 (post 223.4): `prd system run reconcile-status --execute` opens a PR titled "chore: reconcile PRD statuses for merged work" with the status flips
- [ ] AC-4: The reconcile operation correctly identifies PRDs whose branches were merged via squash-and-merge (the most common case)
- [ ] AC-5: Reconcile is idempotent — re-running on a fully-reconciled set produces no PR
- [ ] AC-6: `prd system run audit-impacts` lists declared impacts that don't correspond to existing files (catches the kind of PRD-paths drift PR #6 fixed)
- [ ] AC-7: System operations reuse the existing capability→model mapping, sentinel parsing, streaming output, and process lock (PRD-217) — no parallel infrastructure
- [ ] AC-8: Tests cover: load_operations discovery, system_check_merged with squash and merge-commit shapes, reconcile dry-run vs execute, idempotency

## Open Questions

- [x] ~~Should system ops live at `operations/` repo root or `.darkfactory/operations/`?~~ Resolved: `.darkfactory/operations/`. This PRD depends on PRD-222 so the convention is in place before any operation code lands — no repo-root staging, no migration.
- [ ] Should reconcile mutate the source repo directly (violates PRD-213 invariant) or use a one-off worktree branch like `system/reconcile-2026-04-08`? Recommendation: dedicated worktree with branch + PR — preserves the invariant and matches how other batched changes get reviewed.
- [ ] How does the agent verify-merge step decide "merge matches the PRD's intent"? The simplest: read the PRD's Acceptance Criteria, read the merge commit's diff, sentinel `MATCH` or `MISMATCH: <reason>`. More sophisticated approaches (read tests, run them, etc.) belong in a separate operation.
- [ ] Do we want a `prd system schedule <name>` later for cron-like recurring operations (e.g. nightly reconcile)? Recommendation: out of scope for this epic.
- [ ] What does the planning workflow (PRD-220 prerequisite from the original arch plan) look like once it's a SystemOperation? It takes one PRD as input rather than zero or many — does that break the abstraction? Recommendation: SystemOperation accepts an optional `target_prd: str | None` argument that operations can declare via `accepts_target=True`. Then planning is `prd system run plan PRD-X --execute`.

## References

- [[PRD-220-graph-execution]] — separate from this; graph execution is about running many PRDs in topological order, system ops are about the harness doing meta-work on the PRD set
- [[PRD-217-process-lock-active-worktrees]] — system ops should respect the same lock primitive
- [[PRD-222-general-purpose-tool]] — system ops will live under `.darkfactory/operations/` once that lands
- Original architecture plan's "planning workflow" concept — a natural fit for SystemOperation
