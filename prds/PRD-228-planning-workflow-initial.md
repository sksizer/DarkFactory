---
id: "PRD-228"
title: "Initial planning workflow: decompose epics into child PRDs"
kind: task
status: ready
priority: high
effort: m
capability: complex
parent: null
depends_on: []
blocks:
  - "[[PRD-229-planning-workflow-hardened]]"
impacts:
  - workflows/planning/workflow.py
  - workflows/planning/prompts/role.md
  - workflows/planning/prompts/decomposition-guide.md
  - workflows/planning/prompts/task.md
  - src/darkfactory/containment.py
  - src/darkfactory/cli.py
  - tests/test_planning_workflow.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - workflow
  - planning
---

# Initial planning workflow: decompose epics into child PRDs

## Summary

Ship a working **`planning`** workflow that decomposes an epic or feature PRD into a set of fine-grained task PRDs. Uses only the primitives that exist on main today — no template machinery, no forbidden-path enforcement, no new invariant infrastructure. The goal is to **get basic planning working ASAP** so the harness can decompose its own backlog (and any other PRD-driven project's epics).

Constraints come from convention in this PRD: tool allowlist scoping and prompt instructions tell the agent to only write into `prds/`. Hard enforcement (`forbidden_path_globs`, `verify_only_prds_changed`, template-level guarantees) lands later in **PRD-229** once **PRD-227** (template machinery) is in place.

## Motivation

darkfactory has 8 epics already (PRD-220, 222, 223, 224, 225, 226, 227, plus the original 500 series). Several are explicitly tagged for decomposition into children but none have been broken down beyond the rough sketch in their bodies. Doing that decomposition by hand for every epic is exactly the kind of work the harness was built to delegate.

A working planning workflow lets us:

- **Run `prd run PRD-222 --execute`** on the general-purpose-tool epic and get 6 child PRDs auto-created
- **Re-run on any epic** as the design firms up
- **Dogfood** the harness on the part of its lifecycle most prone to "I'll do it later" — planning
- **Validate** that the workflow harness model handles the meta-case of "decomposing a PRD" without special-casing it

The hard enforcement layer (PRD-229) is valuable but blocks on PRD-227 which is its own non-trivial epic. Shipping convention-based planning first means we get value in days, not weeks, and we have a real workflow to upgrade once the template infrastructure is ready.

## What's in scope (and what's not)

**In scope (PRD-228):**

- A new `workflows/planning/` directory with `workflow.py` + 3 prompt files
- An `applies_to` predicate that fires on `epic` or `feature` PRDs in `ready` status with no task children
- Tool allowlist constrained to `Read`, `Write`, `Glob`, `Grep`, scoped `Bash` calls
- Capability override: pinned to `opus` (decomposition is complex reasoning)
- A `ShellTask("validate-children", cmd="just prd validate", on_failure="retry_agent")` step that catches malformed children before sentinel
- A new `containment.is_fully_decomposed(prd, prds)` helper if it doesn't already exist (it's referenced in the original architecture plan but I should verify)
- Tests covering: applies_to predicate, planning workflow loads, dry-run plan output
- Manual end-to-end verification on a real epic (one of the 8 candidates above)

**Out of scope (deferred to PRD-229 + PRD-227):**

- Template-based invariant enforcement
- `forbidden_path_globs` at the template level
- `verify_only_prds_changed` BuiltIn (hard guarantee that the agent only touches `prds/`)
- Path-prefix enforcement that's stronger than the tool allowlist
- Any post-implementation lint/format/typecheck of the agent's output beyond `prd validate`

PRD-228 is **convention-based**: the prompts tell the agent to only create files in `prds/`, the tool allowlist makes that the easy path, and `prd validate` catches schema violations. PRD-229 layers hard enforcement on top.

## Requirements

1. A new directory `workflows/planning/` with the standard four files: `workflow.py`, `prompts/role.md`, `prompts/decomposition-guide.md`, `prompts/task.md`.
2. The workflow's `applies_to` predicate matches:
   - `prd.kind in ("epic", "feature")`
   - `prd.status == "ready"`
   - `not is_fully_decomposed(prd, prds)` (no descendant PRDs of `kind: task` exist)
3. Priority **5** — above default (0), below ui-component (10) so it wins for undecomposed epics but loses if a more specific workflow matches.
4. Model pinned to `opus` via `model="opus", model_from_capability=False`.
5. Tool allowlist:
   - `Read`, `Glob`, `Grep` — to read existing PRDs and the schema
   - `Write` — to create new PRD files
   - `Bash(uv run prd validate*)` — to self-check
   - `Bash(git add prds/:*)`, `Bash(git status:*)`, `Bash(git diff prds/:*)` — staging only the prds dir
   - **No** `Edit` — agent should create new files, not modify source code (the parent epic's `blocks:` field is the one exception; the prompts will instruct the agent to use `Write` to overwrite the parent file with the updated frontmatter)
   - **No** unscoped `Bash(*)` — anything not on this list should not be reachable
6. The workflow's `tasks` list:
   - `ensure_worktree`
   - `set_status(in-progress)` + `commit("start work")`
   - `AgentTask` (with planning prompts and the tool allowlist above)
   - `ShellTask("validate-children", cmd="uv run prd validate", on_failure="retry_agent")`
   - `summarize_agent_run` (already an existing builtin or added by PRD-224.3 if that lands first; otherwise this PRD's planning workflow can skip it for now)
   - `set_status(review)` + `commit("ready for review")`
   - `push_branch` + `create_pr`
7. The agent prompts instruct it to:
   - Read the parent PRD end-to-end including ACs
   - Read `prds/_template.md` if it exists, else infer the format from any existing `kind: task` PRD in the directory
   - Glob `prds/PRD-*.md` to see existing PRDs and pick non-conflicting IDs (e.g. children of `PRD-222` get `PRD-222.1`, `PRD-222.2`, ...)
   - Create one new PRD file per task with valid frontmatter (id, title, kind=task, status=ready, parent set to the wikilink of the epic, etc.)
   - Update the parent PRD's `blocks:` field to include the new wikilinks
   - Run `uv run prd validate` and fix any errors
   - Print a summary of created PRDs + the dependency graph
   - Emit `PRD_EXECUTE_OK: {parent_prd_id}` as the final line
8. Tests:
   - The `is_fully_decomposed` helper exists and behaves correctly
   - The planning workflow loads via `prd list-workflows`
   - The applies_to predicate returns true for an undecomposed epic and false for a fully-decomposed one
   - `prd plan PRD-222` (an undecomposed epic) routes to the planning workflow with opus
   - `prd plan PRD-001` or any leaf task does NOT route to planning
9. Manual verification (after the code lands but before the PRD itself is marked done):
   - Pick one real undecomposed epic — recommend **PRD-222** (general-purpose tool) since its decomposition is already sketched in the body
   - Run `prd run PRD-222 --execute`
   - Verify the agent creates child PRDs that pass `prd validate`
   - Inspect the generated PRDs by hand for sanity
   - Mark PRD-228 done after successful manual verification

## Technical Approach

### Workflow file

```python
# workflows/planning/workflow.py
from __future__ import annotations

from darkfactory.containment import is_fully_decomposed
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _is_undecomposed_epic_or_feature(prd, prds):  # type: ignore[no-untyped-def]
    return (
        prd.kind in ("epic", "feature")
        and prd.status == "ready"
        and not is_fully_decomposed(prd, prds)
    )


workflow = Workflow(
    name="planning",
    description=(
        "Decompose an epic or feature PRD into fine-grained task PRDs. "
        "Pinned to opus; constrained tool allowlist that only allows "
        "creating files under prds/. Validates new children with "
        "`prd validate` before sentinel."
    ),
    applies_to=_is_undecomposed_epic_or_feature,
    priority=5,
    tasks=[
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start decomposition"}),
        AgentTask(
            name="decompose",
            prompts=[
                "prompts/role.md",
                "prompts/decomposition-guide.md",
                "prompts/task.md",
            ],
            tools=[
                # Read existing PRDs + schema
                "Read",
                "Glob",
                "Grep",
                # Create new PRD files (and overwrite parent PRD with updated blocks)
                "Write",
                # Self-validate
                "Bash(uv run prd validate*)",
                "Bash(uv run prd:*)",
                # Stage changes (scoped to prds/)
                "Bash(git add prds/:*)",
                "Bash(git status:*)",
                "Bash(git diff prds/:*)",
                # Inspect existing structure (read-only)
                "Bash(git log:*)",
            ],
            model="opus",
            model_from_capability=False,
            retries=1,
            verify_prompts=["prompts/verify.md"],
        ),
        ShellTask(
            "validate-children",
            cmd="uv run prd validate",
            on_failure="retry_agent",
        ),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} decomposed into tasks"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
```

### `is_fully_decomposed` helper

If not already in `containment.py` from earlier work:

```python
# src/darkfactory/containment.py

def is_fully_decomposed(prd: PRD, prds: dict[str, PRD]) -> bool:
    """True if the PRD has at least one task-kind descendant.

    An epic or feature is considered decomposed once any descendant PRD
    has kind=task. Containers without task descendants are pre-planning
    candidates that the planning workflow can target.
    """
    return any(d.kind == "task" for d in descendants(prd.id, prds))
```

### Prompts

**`prompts/role.md`** — short, focused role definition for a senior staff engineer in decomposition mode. Critical instructions:

- Your job is decomposition, not implementation
- Output is new PRD files, not source code
- Do NOT touch any file outside `prds/`
- Do NOT run tests, lint, or build commands
- Validate your work with `prd validate` before declaring done

**`prompts/decomposition-guide.md`** — the heuristics for good decomposition:

- Decompose along natural interface boundaries
- Each task should be 1-4 hours of solo-implementable work
- Backend before frontend, pure functions before commands before UI
- Use the parent PRD's existing structure as ground truth
- Sibling tasks should be ordered such that earlier tasks unblock later ones
- Set `parent` on every new task; set `depends_on` between siblings where order matters
- Use hierarchical IDs: children of `PRD-X` get `PRD-X.1`, `PRD-X.2`, etc.
- Pick the next unused sibling index by globbing `prds/PRD-{parent_id}.*.md`
- Update the parent PRD's `blocks:` field to include all new children
- Each new task PRD must have: valid frontmatter, Summary, Requirements, Technical Approach (with file paths), Acceptance Criteria

**`prompts/task.md`** — the actual task instructions, with placeholders for `{{PRD_ID}}`, `{{PRD_PATH}}`, etc. Steps:

1. Read `{{PRD_PATH}}` end-to-end
2. Read `prds/_template.md` (if exists) and an existing well-formed task PRD as a reference
3. Glob `prds/PRD-*.md` to see what exists
4. Identify the natural decomposition seams
5. Plan the dependency graph
6. Write each new PRD file with `Write`
7. Update the parent's `blocks:` field with `Write` (overwrite preserves byte-for-byte if you read it first and only change the one field)
8. Run `uv run prd validate` and fix any errors
9. Print a summary
10. Final line: `PRD_EXECUTE_OK: {{PRD_ID}}`

**`prompts/verify.md`** (used on retry after `validate-children` fails) — instructs the agent to read the validate error output, fix the broken PRDs, and re-emit the sentinel.

## Acceptance Criteria

- [ ] AC-1: `workflows/planning/` directory exists with workflow.py + 3 prompt files (+verify.md)
- [ ] AC-2: `prd list-workflows` shows the planning workflow at priority 5
- [ ] AC-3: `prd plan PRD-222` (an undecomposed epic) routes to the planning workflow with `model: opus`
- [ ] AC-4: `prd plan PRD-001` (a leaf task) does NOT route to the planning workflow
- [ ] AC-5: `is_fully_decomposed` returns true for an epic with at least one task descendant and false otherwise
- [ ] AC-6: `prd run PRD-222 --execute` (manual end-to-end) creates valid child PRDs that pass `prd validate`
- [ ] AC-7: The generated children have correct `parent` wikilinks pointing back to PRD-222
- [ ] AC-8: PRD-222's `blocks:` field after the run includes all new children
- [ ] AC-9: All existing pytest passes (no regressions); new tests for the planning workflow pass

## Open Questions

- [ ] What's the right way for the agent to update the parent epic's `blocks:` field? Options: (a) `Write` the whole file (loses byte-for-byte preservation if there are quoting differences), (b) call into `update_frontmatter_field_at` somehow (but the agent doesn't have a Python REPL), (c) instruct the agent to use `Edit` *just for this one operation* and re-add `Edit` to the allowlist. **Recommendation**: (c) for now — pragmatic, well-scoped. PRD-229 will tighten this with `forbidden_path_globs`.
- [ ] Should the workflow re-run `prd validate` against the parent PRD (not just the children) to make sure the updated `blocks:` field is well-formed? Yes — `prd validate` already validates the whole set, so a single run covers it.
- [ ] What about epics that are already partially decomposed (some children exist, more are needed)? The current `is_fully_decomposed` check returns true if *any* task descendant exists, which means partially-decomposed epics won't be picked up. **Recommendation**: leave that nuance for later; the immediate need is "decompose epics that have zero children".
- [ ] How does the planning workflow interact with the process lock from PRD-217? Standard — same per-PRD lock applies. Two `prd run PRD-222` invocations can't race.
- [ ] Should there be a `--dry-run` mode that has the agent describe its plan without writing files? Yes, the existing `--dry-run` flag works because the agent task in dry-run mode just logs what it would do. No special handling needed.
- [ ] What model retries on this workflow? `retries=1` matches the default. Decomposition is expensive enough that more retries are unlikely to help.

## Relationship to other PRDs

- **Blocks PRD-229** — the hardened planning workflow that uses `PLANNING_TEMPLATE` from PRD-227
- **Depends on** the original `is_fully_decomposed` helper in `containment.py` (referenced from earlier architecture work — verify it exists or add it)
- **Related to** PRD-223.6 which originally proposed re-casting planning as a SystemOperation. Decision: keep planning as a `Workflow` (matches the existing architecture); SystemOperation is for the multi-PRD-target case, not "one epic in, many children out". Update PRD-223.6 to note this.
- **Will be retrofitted by** PRD-229 once PRD-227 ships templates and `forbidden_path_globs` enforcement
- **Mentioned in** the original architecture plan from PR #51 — captures most of those design decisions

## Why this ships before PRD-227

- **Concrete value early** — every epic in the backlog can be decomposed once this lands, without waiting for the template machinery
- **Real dogfood target** — running planning on real epics is the best way to validate that the harness model holds for non-trivial agent work
- **Informs PRD-227** — actual usage of the planning workflow surfaces what PRD-229's hard enforcement actually needs to constrain
- **Small scope** — the workflow itself is ~80 LOC + prompts; the constraints in 229 are layered on later without rework

## Why we'll re-do parts of this in PRD-229

- The tool allowlist scoping is honor-system; PRD-229's `forbidden_path_globs` makes it actual enforcement
- The `Edit` exception for the parent PRD's `blocks:` field is a leak; PRD-229 closes it via a `set_blocks` BuiltIn that the workflow can call instead of giving the agent `Edit`
- The workflow body should ultimately compose from `PLANNING_TEMPLATE` (PRD-227) so the open/close invariants are guaranteed, not conventional
- `verify_only_prds_changed` BuiltIn (PRD-229) catches "agent wrote files outside prds/" before the PR opens — currently relies on tool allowlist alone
