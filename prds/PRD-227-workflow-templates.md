---
id: PRD-227
title: "Workflow templates: enforced opening/closing with configurable middle"
kind: epic
status: ready
priority: high
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-224-harness-invariants-honest-state]]"
blocks: []
impacts: []
workflow: planning
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - workflow
  - architecture
---

# Workflow templates: enforced opening/closing with configurable middle

## Summary

Today the harness has two primitives at the workflow level: **`Workflow`** (a flat task list) and **`SystemOperation`** (its sibling for non-PRD-bound work). Both are fully composable — workflow authors arrange tasks however they want — which is great for flexibility but means **invariants can't be enforced**. Anyone can write a workflow that skips `summarize_agent_run`, forgets `commit_transcript`, or omits `create_pr`. There's no central place that says "every PRD-implementation workflow MUST have these steps in these positions."

This PRD adds a third primitive: **`WorkflowTemplate`**. A template defines:

- **Required opening tasks** that always run first, in order, with no way to skip
- **A customizable middle** where the workflow author plugs in the creative work (agent tasks, project-specific shell tasks, etc.)
- **Required closing tasks** that always run last, in order, with no way to skip

A concrete `Workflow` is then **composed** from a template + a middle. The template enforces invariants by construction; the middle stays flexible. Different projects can supply different middles to the same template — PRD implementation looks the same on every project even though the actual tests/lints/builds differ.

## Motivation

### What's missing today

PRD-224 introduces several invariants that need to hold for every PRD-implementation workflow:

- Worktree must be created and locked (PRD-217)
- Status must transition `ready → in-progress → review` (PRD-213/214)
- Agent transcripts must be committed (PRD-224.6)
- PR body must include the run summary (PRD-224.3)
- PR must be opened after the work is staged

In PRD-224 as currently drafted, these are enforced by **convention** — the default workflow happens to include them. But there's nothing stopping a workflow author from writing a custom workflow that omits any of them. The only enforcement is "we recommend you include these BuiltIns."

That's not enough for a tool that's supposed to give honest state. The whole point of the invariants is that they hold *always*, not "when the workflow author remembered to add them."

### What templates give us

A template **defines the contract**. A workflow **adopts** the contract by being built from the template. The runner can then assert "this Workflow is composed from a known template; the invariants the template enforces are guaranteed to hold."

```python
# darkfactory provides a template
PRD_IMPLEMENTATION_TEMPLATE = WorkflowTemplate(
    name="prd-implementation",
    description="Standard PRD implementation lifecycle with enforced invariants.",
    open=[
        BuiltIn("ensure_worktree"),       # PRD-217 lock + PRD-224.2 stale check
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"}),
    ],
    middle_kinds=[AgentTask, ShellTask],   # what tasks are allowed in the middle
    middle_required={
        # at least one AgentTask must be present
        AgentTask: (1, None),
        # at least one ShellTask for tests
        ShellTask: (1, None),
    },
    close=[
        BuiltIn("summarize_agent_run"),     # PRD-224.3
        BuiltIn("commit_transcript"),       # PRD-224.6
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} ready for review"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)


# A user composes a workflow from the template
workflow = PRD_IMPLEMENTATION_TEMPLATE.compose(
    name="default",
    description="General-purpose PRD implementation workflow.",
    applies_to=lambda prd, prds: True,
    priority=0,
    middle=[
        AgentTask(
            name="implement",
            prompts=["prompts/role.md", "prompts/task.md"],
            tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash(just:*)"],
            model_from_capability=True,
        ),
        ShellTask("test", cmd="just test", on_failure="retry_agent"),
        ShellTask("format", cmd="just format", on_failure="fail"),
        ShellTask("lint", cmd="just lint format-check", on_failure="retry_agent"),
        ShellTask("typecheck", cmd="just typecheck", on_failure="retry_agent"),
    ],
)
```

The user controls the middle. The template enforces the rest. **No way to skip the closing transcripts. No way to skip the summary. No way to skip the PR.**

### Why this is the right architectural answer

The earlier discussion in PRD-224 surfaced two tensions:

1. **Composable primitives are great for flexibility** — a workflow author can swap, skip, or reorder
2. **Hard-coded primitives are necessary for safety** — some checks (like the worktree lock) can't be bypassed without corrupting state

Templates resolve the tension. The same primitive (`commit_transcript`) is **composable in isolation** (any workflow can call it) but **enforced in position** when used inside a template (the PRD implementation template guarantees it runs after the agent and before the PR). Authors get flexibility within the middle and safety at the boundaries.

This is the **template method pattern** applied to workflows. The template defines the skeleton; subclasses (or in our case, composed workflows) fill in the variable parts.

### Other templates we'd want

- **`PRD_IMPLEMENTATION_TEMPLATE`** — what this PRD focuses on; the default + ui-component + similar workflows would all use it
- **`REWORK_TEMPLATE`** (PRD-225) — opens by checking PR exists + resuming worktree + fetching comments; closes by pushing to existing branch (no `create_pr`)
- **`SYSTEM_OPERATION_TEMPLATE`** — opens by acquiring a global lock; closes by logging + releasing
- **`PLANNING_TEMPLATE`** — opens by reading the parent epic; closes by validating the new child PRDs
- **`AUDIT_TEMPLATE`** — opens by snapshotting state; closes by writing a report file (no PR, no commits)

Each template has its own invariants. The closing tasks of `REWORK_TEMPLATE` would assert "the existing PR is still open" (vs `PRD_IMPLEMENTATION_TEMPLATE`'s "create a new PR"). Different shapes of work get different guarantees.

### Project-specific overrides

A project can supply its own template if the built-in one doesn't fit:

```python
# In a project's .darkfactory/templates/our-template.py
from darkfactory.templates import WorkflowTemplate, BuiltIn, AgentTask

OUR_TEMPLATE = WorkflowTemplate(
    name="our-template",
    open=[
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        # Project-specific opening: also create a Linear ticket
        BuiltIn("linear_create_subtask"),  # custom builtin from this project
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"}),
    ],
    close=[
        BuiltIn("summarize_agent_run"),
        BuiltIn("commit_transcript"),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} ready for review"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
        BuiltIn("linear_close_subtask"),  # also close the linear ticket
    ],
    ...
)
```

The project's template still has the invariants the user cares about (transcripts, summaries, status flips) — they just chose to add Linear ticket management around them. **Different projects, different opinions, same invariant guarantees.**

## Decomposition

### PRD-227.1 — Core `WorkflowTemplate` abstraction

The `WorkflowTemplate` dataclass + the `.compose()` method that produces a `Workflow`. The composed workflow's task list is `[*template.open, *middle, *template.close]`. The compose method validates the middle against `middle_kinds` and `middle_required` and raises on violations.

A composed workflow exposes a `.template_name` field so the runner can later assert "this workflow came from template X".

**Effort:** s. ~80 LOC + tests.

**Impacts:**
- `src/darkfactory/templates.py` (new module, distinct from the existing `templates.py` which handles prompts — may need a rename to avoid collision; recommendation: prompts module renamed to `prompts.py`, new module is `templates.py`)
- `src/darkfactory/workflow.py` (Workflow gains a `template_name: str | None` field)
- `tests/test_workflow_templates.py` (new file)

### PRD-227.2 — Provide `PRD_IMPLEMENTATION_TEMPLATE`

Bundle a built-in template that captures the current default workflow's shape with the PRD-224 invariants enforced:

- Open: `ensure_worktree`, `set_status(in-progress)`, `commit("start work")`
- Close: `summarize_agent_run`, `commit_transcript`, `set_status(review)`, `commit("ready for review")`, `push_branch`, `create_pr`
- Middle requires at least 1 AgentTask and at least 1 ShellTask

Document the template in the harness README so workflow authors know what they get for free.

**Effort:** xs. The template is mostly declarative; the BuiltIns it references either already exist or are introduced by PRD-224.

**Impacts:**
- `src/darkfactory/templates_builtin.py` (new module with the bundled templates)
- README

### PRD-227.3 — Migrate the default workflow to use `PRD_IMPLEMENTATION_TEMPLATE`

Rewrite `workflows/default/workflow.py` to call `PRD_IMPLEMENTATION_TEMPLATE.compose(...)` instead of declaring a flat `Workflow(tasks=[...])`. Same end behavior — the task list is identical — but now the workflow is **provably** template-conformant.

The runner can later check `workflow.template_name == "prd-implementation"` and surface that in `prd plan` output: `"workflow: default (template: prd-implementation)"`.

**Effort:** xs. Mechanical refactor.

**Impacts:**
- `workflows/default/workflow.py`
- `tests/test_loader.py`

### PRD-227.4 — Migrate the extraction workflow

Same exercise for `workflows/extraction/workflow.py`. Verifies the template works for non-default workflows. The extraction workflow may need its own variant of the template if the open/close differ enough — surfaces that question early.

**Effort:** xs.

### PRD-227.5 — `REWORK_TEMPLATE` (depends on PRD-225)

Define the rework template once PRD-225's manual rework command is in place. Open: check PR exists, resume worktree, fetch comments. Close: commit, push (no create_pr).

**Effort:** s.

### PRD-227.6 — `SYSTEM_OPERATION_TEMPLATE` (depends on PRD-223)

Define the system-op template once PRD-223 lands. Open: acquire global lock. Close: release lock, write report file.

**Effort:** s.

## Acceptance Criteria

- [ ] AC-1 (post 227.1): `WorkflowTemplate.compose(middle=[...])` produces a `Workflow` whose tasks are `[*open, *middle, *close]`.
- [ ] AC-2 (post 227.1): Composing with a middle that violates `middle_kinds` or `middle_required` raises `TemplateViolation` with a clear message.
- [ ] AC-3 (post 227.1): The composed workflow exposes `template_name` so the runner can assert / display it.
- [ ] AC-4 (post 227.2): `PRD_IMPLEMENTATION_TEMPLATE` exists, is importable, and has all the PRD-224 invariants in its `close` list.
- [ ] AC-5 (post 227.3): The default workflow uses the template; its task list is identical to before; all 200+ existing workflow tests pass.
- [ ] AC-6 (post 227.4): The extraction workflow either uses the same template or its own template; clear documentation explains why.
- [ ] AC-7: Workflow authors trying to write a "lean" workflow that skips invariants must consciously not use the template — there's no accidental path to omitting closing tasks.
- [ ] AC-8: `prd plan PRD-X` shows `workflow: default (template: prd-implementation)` so users see the template their work is running under.
- [ ] AC-9: Test coverage for: composing valid workflows, composing invalid workflows (violations), middle validation, template_name surfacing.

## Open Questions

- [ ] Should templates be **discoverable** like workflows (loaded from a directory) or **bundled** (importable Python modules)? Recommendation: bundled in the package, with the option to register custom templates from a project's `.darkfactory/templates/` directory.
- [ ] How should the runner enforce template conformance at run time? The `.compose()` method already validates at definition time; should the runner re-check before running? Recommendation: no — definition-time check is sufficient. Re-checking is paranoia.
- [ ] What if a workflow author wants to inject a step **between** open and middle, or middle and close? Allowed? Recommendation: not by default — the open/close boundaries are the contract. If you need extra steps in those positions, you write a custom template.
- [ ] Templates vs inheritance: should `WorkflowTemplate` itself be subclassable, with `PRD_IMPLEMENTATION_TEMPLATE` as a subclass? Recommendation: no — composition over inheritance. Templates are values, not classes.
- [ ] Does the rework template have a `middle_required` constraint of "at least one AgentTask"? Yes — running rework with no agent task makes no sense. The validation message can guide users.
- [ ] What does this mean for `Workflow` users that don't want a template? Recommendation: keep `Workflow(tasks=[...])` working as-is. Templates are an additional layer, not a forced one. Workflows that don't use a template just don't get template_name set, and `prd plan` shows them as `(no template)`.

## Relationship to other PRDs

- **PRD-224** — provides the BuiltIns this template bundles into its open/close lists. PRD-224 ships the primitives; this PRD organizes them into enforced sequences.
- **PRD-225** — needs `REWORK_TEMPLATE` (227.5) to enforce its own invariants
- **PRD-223** — needs `SYSTEM_OPERATION_TEMPLATE` (227.6)
- **PRD-222.6** — config support could let projects override the default template via `.darkfactory/config.toml`
- **PRD-226** — orthogonal; templates organize today's mutable status; derived status would change what the open/close steps look like but the template machinery itself is unaffected
- **`prd_harness/templates.py`** (existing prompts module) — name collision; will need a rename. Recommend `prompts.py` for the existing one.

## Why this is the right shape (summary)

Three layers, each with a clear responsibility:

| Layer | What it provides | Customizability |
|---|---|---|
| **Primitives** (`BuiltIn`, `AgentTask`, `ShellTask`) | Atomic units of work | Fully composable |
| **Templates** (`WorkflowTemplate`) | Required positions for invariants + a slot for the variable middle | Open/close fixed; middle shape constrained by kind/count |
| **Workflows** (`Workflow`, composed from a template) | A concrete pipeline ready to run | Middle is fully user-controlled |

Today darkfactory has the bottom layer and (most of) the top. This PRD adds the missing middle layer that connects them with **enforcement instead of convention**.
