---
id: "PRD-231"
title: "Planning review workflow: extend partially-decomposed epics"
kind: task
status: done
priority: medium
effort: s
capability: complex
parent: null
depends_on:
  - "[[PRD-228-planning-workflow-initial]]"
blocks: []
impacts:
  - workflows/planning-review/workflow.py
  - workflows/planning-review/prompts/role.md
  - workflows/planning-review/prompts/review-guide.md
  - workflows/planning-review/prompts/task.md
  - src/darkfactory/containment.py
  - tests/test_planning_review_workflow.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-09'
tags:
  - harness
  - workflow
  - planning
  - review
  - feature
---

# Planning review workflow: extend partially-decomposed epics

## Summary

PRD-228 ships an initial planning workflow that decomposes **fully undecomposed** epics — epics with zero task descendants. But many real epics get decomposed iteratively: a first pass creates 4 children, then later we realize 2 more are needed; or scope grows; or the original decomposition missed a slice.

The initial planning workflow won't pick those up because its `applies_to` predicate explicitly requires **zero** task descendants. Running it on a partially-decomposed epic would just no-op (or worse, regenerate children that overlap with existing ones).

This PRD ships a **second planning workflow**, `planning-review`, that handles the partial-decomposition case. Different `applies_to` predicate (some-but-not-all-requirements-covered), different agent prompts (review-and-extend instead of decompose-from-scratch), but shares the same template (`PLANNING_TEMPLATE` from PRD-227 once that exists, or convention-based until then per PRD-228).

## Motivation

### What initial planning misses

`is_fully_decomposed(prd, prds)` from PRD-228 returns `True` if **any** descendant is `kind: task`. That binary check matches the initial-planning case ("decompose this epic from scratch") but creates a gap:

- Epic has 4 children, original author thought it was done → `is_fully_decomposed: True`
- Reviewer realizes one of the requirements has no implementing task → still `is_fully_decomposed: True`
- The initial planning workflow won't pick it up
- The user has to either decompose by hand OR delete a child to trick the predicate

That's a bad user experience and it leaves real gaps in the backlog.

### Why this is a separate workflow, not a flag on PRD-228

Two distinct shapes of work:

| | PRD-228 (initial planning) | This PRD (planning review) |
|---|---|---|
| **Input** | Epic with 0 children | Epic with N existing children |
| **Question to agent** | "Decompose this from scratch" | "Are these children complete? If not, what's missing?" |
| **Failure mode** | Bad first decomposition | Adds noise (duplicates), or misses real gaps |
| **Output** | N new children | 0 to M new children (might be empty if decomposition was already complete) |
| **Ideal sentinel** | `created: PRD-X.1, ...` | `created: PRD-X.5, PRD-X.6` OR `complete: no gaps found` |

These are different agent prompts and different success criteria. Cleaner as two workflows that share infrastructure than one workflow with a mode flag.

### Why this is also reusable

The "audit something against its stated intent and fill gaps" pattern shows up beyond planning:

- Audit ACs: read a PRD's acceptance criteria, check if the implementation actually covers each one
- Audit tests: check if every public function has test coverage
- Audit docs: check if every CLI subcommand has a doc entry

A `planning-review`-shaped workflow is the prototype for that family. Get the shape right here and other audits become trivial.

## Requirements

1. A new directory `workflows/planning-review/` with `workflow.py` + 3 prompt files (role, review-guide, task) + verify.md
2. The workflow's `applies_to` predicate matches:
   - `prd.kind in ("epic", "feature")`
   - `prd.status == "ready"` OR `prd.status == "in-progress"` (review can apply mid-flight)
   - `is_partially_decomposed(prd, prds)` — at least one task descendant exists AND the epic's requirements are not fully covered (see helper below)
3. Priority **6** — above default (0) and initial planning (5), so it wins for partial-decomposition cases. Initial planning still wins for zero-children cases because its predicate is more specific.
4. A new helper `containment.is_partially_decomposed(prd, prds)`:
   ```python
   def is_partially_decomposed(prd: PRD, prds: dict[str, PRD]) -> bool:
       """True if the PRD has at least one task descendant but is not
       considered 'complete' by some heuristic.

       The 'complete' check is intentionally heuristic — there's no
       deterministic way to know whether a decomposition covers an
       epic's requirements without semantic understanding. This helper
       returns True for any PRD that has children but might still need
       more, and lets the agent decide.

       Heuristic: True if has task descendants AND the parent has not
       been explicitly marked complete via a frontmatter flag
       `decomposition: complete`. False if the flag is set OR if there
       are zero task descendants (initial planning's territory).
       """
       descendants_list = descendants(prd.id, prds)
       has_tasks = any(d.kind == "task" for d in descendants_list)
       if not has_tasks:
           return False  # zero children — initial planning handles this
       fm = prd.raw_frontmatter or {}
       if fm.get("decomposition") == "complete":
           return False  # explicitly marked complete by author
       return True
   ```
5. Tool allowlist same as PRD-228 (Read, Glob, Grep, Write, scoped Bash + git + prd validate). No `Edit` (parent updates use the same `Write`-the-whole-file workaround as PRD-228 until PRD-229 ships `set_blocks`).
6. Model pinned to `opus`.
7. Task list:
   - `ensure_worktree`
   - `set_status(in-progress)` + `commit("start review")`
   - `AgentTask` with the review prompts
   - `ShellTask("validate-children", cmd="uv run prd validate", on_failure="retry_agent")`
   - `set_status(review)` + `commit("planning review complete")`
   - `push_branch` + `create_pr`
8. Agent prompts include the new behavior:
   - Read the parent PRD end-to-end
   - **Read every existing child PRD** — this is the critical difference from PRD-228
   - Map the parent's requirements to existing children: which requirement is covered by which child?
   - Identify uncovered requirements
   - For each gap, create a new child PRD using the same conventions as PRD-228 (hierarchical IDs, parent wikilink, etc.)
   - Pick child IDs that don't collide with existing siblings: glob `prds/PRD-{parent_id}.*.md` and use the next unused index
   - Update the parent's `blocks:` field to include the new children alongside the existing ones
   - Run `prd validate` to catch issues
   - **Two valid sentinel paths**:
     - `PRD_EXECUTE_OK: {{PRD_ID}}` followed by `created: PRD-X.5, PRD-X.6` (gaps were filled)
     - `PRD_EXECUTE_OK: {{PRD_ID}}` followed by `complete: no gaps found` (decomposition was already complete)
9. Tests:
   - `is_partially_decomposed` returns true/false for the right cases
   - Workflow loads via `prd list-workflows`
   - `prd plan PRD-X` (a partially-decomposed epic) routes to planning-review with opus
   - `prd plan PRD-Y` (a fully-undecomposed epic) routes to initial planning, NOT planning-review
   - `prd plan PRD-Z` (an epic with `decomposition: complete` flag) routes to NEITHER planning workflow

## Technical Approach

### Workflow file

```python
# workflows/planning-review/workflow.py
from __future__ import annotations

from darkfactory.containment import is_partially_decomposed
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _is_review_candidate(prd, prds):  # type: ignore[no-untyped-def]
    return (
        prd.kind in ("epic", "feature")
        and prd.status in ("ready", "in-progress")
        and is_partially_decomposed(prd, prds)
    )


workflow = Workflow(
    name="planning-review",
    description=(
        "Review a partially-decomposed epic against its stated "
        "requirements and add new child PRDs for any uncovered slices. "
        "Pinned to opus. Same constraints as the initial planning "
        "workflow (PRD-228); writes only into prds/."
    ),
    applies_to=_is_review_candidate,
    priority=6,  # higher than initial planning (5), still loses to ui-component (10)
    tasks=[
        BuiltIn("ensure_worktree"),
        BuiltIn("set_status", kwargs={"to": "in-progress"}),
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start planning review"}),
        AgentTask(
            name="review-and-extend",
            prompts=[
                "prompts/role.md",
                "prompts/review-guide.md",
                "prompts/task.md",
            ],
            tools=[
                "Read", "Glob", "Grep", "Write",
                "Bash(uv run prd validate*)",
                "Bash(uv run prd:*)",
                "Bash(git add prds/:*)",
                "Bash(git status:*)",
                "Bash(git diff prds/:*)",
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
        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} planning review complete"}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
```

### Prompts

**`prompts/role.md`** — same role as initial planning (senior staff engineer, decomposition mode) but with the explicit "you are reviewing existing decomposition, not starting fresh" framing. Critical: the agent must read all existing children before deciding anything.

**`prompts/review-guide.md`** — the audit heuristics:

- Read every existing child PRD's `Summary` and `Requirements` sections
- Build a coverage matrix: for each requirement in the parent, which child(ren) implement it?
- Identify any requirement with no implementing child
- For each uncovered requirement, draft a new child PRD that fills the gap
- Don't create overlapping children — if a requirement is partially covered, the right answer might be to extend an existing child, not create a new one. But you don't have `Edit` access, so flag overlaps and prefer "create new" when in doubt
- If everything is covered, that's a valid result — emit `complete: no gaps found` and stop
- Children should follow the same conventions as the existing siblings (id format, frontmatter shape, body structure)

**`prompts/task.md`** — the actual task instructions:

1. Read `{{PRD_PATH}}` end-to-end
2. Glob `prds/PRD-{{PRD_ID_NUMBER}}.*.md` — list of existing children
3. Read each existing child end-to-end
4. Build a coverage map of parent requirements → child implementing them
5. Identify gaps
6. If no gaps:
   - Print "Decomposition complete — all N requirements covered by existing children"
   - Final lines:
     ```
     PRD_EXECUTE_OK: {{PRD_ID}}
     complete: no gaps found
     ```
7. If gaps exist:
   - For each gap, write a new child PRD file using `Write`
   - Pick the next unused sibling index by globbing
   - Update the parent's `blocks:` field to include both existing and new children
   - Run `uv run prd validate` and fix any issues
   - Print a summary: "Found X gaps, created Y new children"
   - Final lines:
     ```
     PRD_EXECUTE_OK: {{PRD_ID}}
     created: PRD-X.5, PRD-X.6, PRD-X.7
     ```

**`prompts/verify.md`** — for the retry-on-validate-failure path. Same shape as PRD-228's verify.md.

### `is_partially_decomposed` helper

Goes in `containment.py` next to the existing `is_fully_decomposed`. The "fully" function from PRD-228 returns true for any-task-descendant case; this new function distinguishes "has children but might need more" from "explicitly marked complete by author". The two functions are not opposites — they overlap, and the workflow predicates use them differently:

- `is_fully_decomposed`: any task descendant exists
- `is_partially_decomposed`: any task descendant exists AND not marked complete

A future PRD-229 (or its own follow-up) might add a smarter heuristic — e.g. running an LLM check that compares parent requirements to child summaries and computes a coverage percentage. For now the binary "marked complete or not" flag is sufficient.

### `decomposition: complete` frontmatter flag

A new optional frontmatter field on epic PRDs:

```yaml
decomposition: complete  # author asserts no more children needed
```

Absent → review workflow can target the epic. Set to `complete` → review workflow ignores it. The agent CAN set this flag in its sentinel run (after determining no gaps exist), via the same `Write` mechanism it uses for the parent's `blocks:` field.

Schema update: add `decomposition: enum [partial, complete]` as an optional field. PRD-228's prompts can also be updated to set `decomposition: partial` on the parent during initial decomposition (so it's clear the epic was generated with intent rather than just sitting empty). PRD-228 doesn't currently do this; this PRD doesn't strictly need 228 updated, but it's a nice consistency.

## Acceptance Criteria

- [ ] AC-1: `workflows/planning-review/` exists with workflow.py + 4 prompt files
- [ ] AC-2: `is_partially_decomposed` returns: false for zero-children, true for has-children-no-flag, false for `decomposition: complete`
- [ ] AC-3: `prd list-workflows` shows planning-review at priority 6
- [ ] AC-4: `prd plan PRD-X` for a partially-decomposed epic routes to planning-review with model: opus
- [ ] AC-5: `prd plan PRD-Y` for an undecomposed epic routes to initial planning (PRD-228), not planning-review
- [ ] AC-6: `prd plan PRD-Z` for an epic with `decomposition: complete` does NOT route to either planning workflow
- [ ] AC-7: Schema accepts the new optional `decomposition` field
- [ ] AC-8: Manual end-to-end on a real partially-decomposed epic — recommend trying it on PRD-222 or PRD-224 after their initial decomposition has landed
- [ ] AC-9: The agent successfully identifies "no gaps" when given a fully-decomposed epic and emits the `complete:` sentinel
- [ ] AC-10: The agent successfully creates new children when given an artificially-gapped epic

## Open Questions

- [ ] How does the agent decide what "covered" means? The strict reading is "the requirement is named verbatim somewhere in a child's body" but that's brittle. Looser readings ("the child's purpose addresses the requirement's intent") are subjective. Recommendation: leave it to the model — opus is sophisticated enough to make reasonable judgments, and the human review of the resulting PR catches over-creation
- [ ] What if a requirement is covered by something OUTSIDE the descendant tree (e.g. an unrelated PRD)? The audit can flag it as "covered by PRD-X (not a descendant)" in the summary but should not create a new child for it. The decomposition is "are MY children covering MY requirements", not "is anyone in the world doing this work"
- [ ] Should the `decomposition: complete` flag be a binary or have more nuance (`partial`, `complete`, `unsure`)? Recommendation: binary for now
- [ ] What about epics whose requirements are themselves vague? The agent should flag this in its summary ("requirement N is too abstract to verify coverage") rather than fabricating children. PRD authors can refine and re-run
- [ ] Should planning-review also be able to **remove** outdated children? E.g. if a child PRD references a deprecated approach, the review identifies it. **No** — out of scope. Removing PRDs is a destructive action that needs human judgment. Surface in the summary, don't act
- [ ] Does the planning-review workflow itself need its own template eventually (PRD-227)? Yes — same `PLANNING_TEMPLATE` should work for both initial and review workflows. The template doesn't care which planning sub-shape is running

## Relationship to other PRDs

- **Depends on PRD-228** — the initial planning workflow. This PRD reuses many of its conventions (tool allowlist, prompt structure, hierarchical IDs)
- **Sibling to PRD-229** — both improve on PRD-228; 229 adds hard enforcement, this adds the second mode of operation
- **Will eventually use PRD-227's `PLANNING_TEMPLATE`** — same template fits both planning workflows once it exists
- **Related to PRD-223** — system operations for audits. The `planning-review` shape ("audit something against its intent") could later become a generic `audit` operation type. For now keep it as a workflow since it targets a single PRD

## Why this is small

The workflow itself is ~80 LOC plus prompts. The main risk is the agent prompts (getting "review existing decomposition" right requires careful framing) but the infrastructure is the same as PRD-228. Effort: s. Capability: complex (the agent task is reasoning-heavy; opus is appropriate).
