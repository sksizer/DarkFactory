---
id: PRD-554
title: Harden the planning workflow prompts for higher-quality PRD decomposition
kind: feature
status: draft
priority: high
effort: s
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-220-graph-execution]]"
impacts:
  - python/darkfactory/workflows/planning/prompts/decomposition-guide.md
  - python/darkfactory/workflows/planning/prompts/task.md
  - python/darkfactory/workflows/planning/prompts/role.md
  - python/darkfactory/workflows/planning/prompts/verify.md
  - python/darkfactory/workflows/planning/workflow.py
  - tests/test_planning_workflow.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-11'
tags:
  - workflows
  - planning
  - prompts
  - quality
---

# Harden the planning workflow prompts for higher-quality PRD decomposition

## Summary

The planning workflow (`python/darkfactory/workflows/planning/`) auto-decomposes a ready epic/feature into child task PRDs via an opus agent. A review against the PRD-220 graph executor's needs surfaced several gaps that will produce subtly-wrong children — broken `impacts:` fields, silently-dropped parent `blocks:` updates, dead template references, missing conflict warnings. A subsequent concrete failure (running the workflow against PRD-549 on 2026-04-08) exposed two more: the agent faithfully copies invalid PRD IDs out of a parent's body, and the role prompt doesn't enumerate what the tool allowlist actually permits — so the agent wastes its whole task budget discovering permissions live. This PRD tightens the prompts so decomposition output is executable without a human polish pass.

## Motivation

PRD-220 just landed sequential graph execution. The obvious first dogfood is `prd run PRD-549 --execute` — point it at a decomposable epic and let the harness do everything. But the planning workflow prompts were written before the graph executor existed, and they optimize for "produce readable PRD files" rather than "produce PRD files the executor can act on." Concrete examples:

1. **`impacts:` guidance is a single sentence.** PRD-220/PRD-546/PRD-550 all depend on `impacts` being accurate and specific. The current guide just says "list of file paths this task will modify" — that's it. An agent that guesses or uses wildcards will poison the conflict-detection and stale-flagging machinery downstream.

2. **Parent `blocks:` update is not verified.** The prompt instructs the agent to update the parent's `blocks:` wikilinks, but there's no post-run check. If the agent forgets or partially succeeds, `prd validate` passes (blocks is not required) and the children become orphans from the parent's perspective.

3. **Dead template reference.** `task.md` tells the agent to "Read `.darkfactory/data/prds/_template.md` if it exists" — it doesn't exist in this repo. The agent then falls back to guessing from a sibling, which is fine but leaves a stale instruction.

4. **No overlapping-impacts warning.** For an epic like PRD-549 (nine siblings all touching `builtins.py`), the children *will* conflict on execution. The agent should be told to flag this explicitly in the decomposition summary so humans can make the conflict-stress-vs-avoidance decision before the graph executor tries to run them.

5. **No hierarchical-ID collision handling.** The guide says "pick the next unused sibling index" but doesn't specify what to do if there's a gap (e.g. 549.1 and 549.3 exist — fill 549.2 or skip to 549.4?). Minor but real.

6. **No effort/capability calibration.** Defaults are "inherit from parent or medium." A complex epic's children legitimately vary — some are trivial file moves, some are real work. The guide should tell the agent to calibrate per-child, not blanket-inherit.

7. **No explicit "workflow: null" rationale.** The guide says to set `workflow: null` but doesn't say why (let assignment pick). A cautious agent might pin a workflow unnecessarily.

8. **Recursion depth ambiguity.** What if the parent has natural feature-sized seams — should the agent create `kind: feature` children (that themselves need decomposition later) or always flatten to `kind: task`? Current guide implies task-only but doesn't state it.

9. **ID format not enforced at the prompt level.** PRD IDs must match `^PRD-\d+(?:\.\d+)*$` — numeric only, no alphabetic suffixes. Nothing in the decomposition guide says this. When a parent PRD's body uses illegal IDs (e.g. the original `PRD-549.3a…3i`), the agent copies them verbatim and every validate step fails. On 2026-04-08 this burned the entire 600s agent budget: the agent correctly diagnosed the issue, then looped through 20+ delete/rename attempts because it had no delete permissions, and timed out without recovering.

10. **Role prompt doesn't enumerate the tool allowlist.** When the agent needs a tool it doesn't have, it discovers this by trying and getting blocked — often 10-20 attempts before giving up. The role prompt should say explicitly: "you have Read/Glob/Grep/Write plus these specific Bash commands. You do NOT have Edit, rm, mv, git rm, git clean. If you need one of those, emit `PRD_EXECUTE_FAILED` with a clear reason." Self-discovery of permissions burns the entire task budget. See `docs/agent-verification-model.md` for why the fix is *not* to grant more permissions.

## Requirements

Each improvement below is a prompt edit + (where applicable) a verification step in the workflow itself.

### Prompt edits

1. **`decomposition-guide.md` — `impacts:` section.**
   - Add: "impacts must be **exact file paths**, no wildcards, no globs. Only list files you will definitely modify. Err on the side of fewer files, not more."
   - Add: "Cross-reference against the parent PRD's Technical Approach — every file mentioned there should be assignable to exactly one child (or declared as a shared/modified-by-all surface)."
   - Add: "If two or more siblings will modify the same file, flag this explicitly in your final summary as 'overlap: FILE touched by CHILD-IDS'. The graph executor will refuse to run them in parallel; the human needs to know."

2. **`decomposition-guide.md` — ID collision + gaps.**
   - Add: "If you see a gap in sibling IDs (e.g. 549.1 and 549.3 exist but not 549.2), **fill the gap**. Never skip unused indices."

3. **`decomposition-guide.md` — effort/capability.**
   - Rewrite: "Inherit from parent or use medium" → "Calibrate per-child. A pure file-move task is probably `effort: xs, capability: trivial`. A task that introduces new logic is `effort: m, capability: moderate` or higher. Do not blanket-inherit from the parent."

4. **`decomposition-guide.md` — `workflow: null`.**
   - Add rationale: "Always `workflow: null`. The assignment logic picks the right workflow at run time based on kind/status/predicates. Pinning a workflow here locks out improvements."

5. **`decomposition-guide.md` — recursion depth.**
   - Add: "Always create `kind: task` children, never `kind: feature`. If a seam feels feature-sized, split it into multiple tasks rather than creating a feature that will need its own planning run."

5a. **`decomposition-guide.md` — ID format (NEW).**
    - Add a prominent section: "PRD IDs must match `^PRD-\d+(?:\.\d+)*$` — numeric components separated by dots. **Never use alphabetic suffixes** like `PRD-549.3a`, `PRD-549.3b`. If the parent PRD's body specifies alphabetic IDs, that parent has a bug — use sequential numeric IDs (549.3, 549.4, 549.5, …) and note the discrepancy in your decomposition summary so the human can fix the parent."
    - Add: "Run `uv run prd validate` **after creating the first file** to catch ID format mistakes early. Do not create all N files before validating."

5b. **`role.md` — explicit allowlist enumeration (NEW).**
    - Add a section listing what tools the planning agent has, and equally important, what it does **not** have: "You have Read, Glob, Grep, Write (scoped to `.darkfactory/data/prds/`), and these Bash commands: `uv run prd validate`, `uv run prd *`, `git add .darkfactory/data/prds/`, `git status`, `git diff .darkfactory/data/prds/`, `git log`. You do **not** have: Edit, rm, mv, git rm, git clean, git mv, or any way to delete or rename files. If your task requires deletion or rename, emit `PRD_EXECUTE_FAILED: need <operation> on <files>` immediately — do not try alternative Bash commands to work around it."
    - Add pointer to `docs/agent-verification-model.md` explaining why the architectural choice is "no permission grants; verify from the harness."

6. **`task.md` — template reference.**
   - Remove the "Read `.darkfactory/data/prds/_template.md` if it exists" line, or add the template file for real (`.darkfactory/data/prds/_template.md`) and point at it. Recommendation: **add the template file** — a canonical exemplar is more robust than "find a good one."

7. **`task.md` — summary format.**
   - Rewrite step 10 ("Report") to require a structured summary:
     ```
     Children created: N
       - PRD-X.1 [effort/capability]: one-line purpose
       - PRD-X.2 [effort/capability]: one-line purpose
     Dependencies: CHILD -> DEPS, ...
     Impact overlaps: FILE touched by [CHILD-IDS], ...
     Parent blocks updated: yes/no
     ```
   This makes the output parseable for a future automated verification step.

### Workflow verification additions

8. **New verification shell task after `validate-children`**: `uv run prd children {prd_id}` and assert the count matches the number of files the agent created. Catches the "parent `blocks:` silently not updated" case.

9. **New verification shell task**: `just test-planning-verifier` or an inline check that runs `uv run prd conflicts PRD-<id>` and echoes any overlaps to stdout — not as a failure, but as visible output the human will see in the workflow run summary.

### Test coverage

10. **`tests/test_planning_workflow.py` additions**:
    - Assert the workflow includes the new post-decomposition verification task.
    - Snapshot-test the prompt files' critical directives so future drift is caught.

## Acceptance criteria

- [ ] AC-1: `decomposition-guide.md` explicitly constrains `impacts:` to exact paths, no globs, and mandates overlap disclosure in the summary.
- [ ] AC-2: `decomposition-guide.md` specifies gap-filling ID behavior, per-child effort/capability calibration, `workflow: null` rationale, and task-only recursion.
- [ ] AC-3: `task.md` either uses a real `.darkfactory/data/prds/_template.md` or removes the dead reference. If added, `_template.md` is a canonical task exemplar.
- [ ] AC-4: `task.md` requires a structured decomposition summary with children, dependencies, overlaps, and parent-blocks status.
- [ ] AC-5: The workflow runs a post-decomposition check that the parent's `blocks:` actually lists the new children. Mismatch fails the workflow.
- [ ] AC-6: Tests cover the new verification task and snapshot the prompt directives.
- [ ] AC-7: Running `prd run PRD-549 --execute` (as a live smoke test) produces children whose `impacts:` are executable by the PRD-220 graph executor without manual fixup.
- [ ] AC-8: `decomposition-guide.md` explicitly forbids alphabetic PRD IDs and instructs the agent to validate after the first file, not after all files.
- [ ] AC-9: `role.md` enumerates the tool allowlist and explicitly names tools the agent does NOT have, with instructions to emit `PRD_EXECUTE_FAILED` rather than probe for alternatives.
- [ ] AC-10: Running the hardened workflow against a parent PRD with deliberately-malformed IDs produces an immediate `PRD_EXECUTE_FAILED` rather than a 600s timeout.

## Open questions

- [ ] Do we want a hard failure on impact-overlap, or just a warning? Recommend warning — PRD-549 explicitly *wants* overlap to stress-test future PRD-551/PRD-552.
- [ ] Should a failed parent-`blocks:` verification auto-retry the agent, or fail loud? Recommend retry (`on_failure="retry_agent"`) consistent with `validate-children`.
- [ ] Should we add a `.darkfactory/data/prds/_template.md` as part of this PRD, or split into a sub-PRD? Probably inline — it's tightly coupled.

## References

- `python/darkfactory/workflows/planning/prompts/` — current state.
- `docs/agent-verification-model.md` — architectural preference that shaped requirements 5b and AC-9 (no permission grants; verify from the harness).
- [[PRD-220-graph-execution]] — the consumer of decomposition output.
- [[PRD-546-impact-declaration-drift-detection]] — needs accurate `impacts:`.
- [[PRD-550-upstream-impact-propagation]] — same.
- [[PRD-549-builtins-package-split]] — worked example and source of the 2026-04-08 failed-run incident.

## Assessment (2026-04-11)

- **Value**: 4/5 — the incident this PRD fixes (600-second agent timeout
  while looping on an unobtainable permission) wasn't a one-off. Every
  future planning run benefits from the tool-allowlist enumeration alone.
- **Effort**: s — it's a prompt file edit plus a post-run verification
  shell task. No new abstractions, no runner changes.
- **Current state**: greenfield on the specific fixes. The planning
  workflow in `workflows/planning/` exists but the `decomposition-guide.md`,
  `role.md`, and `task.md` files don't yet enumerate the permissions,
  forbid alphabetic IDs, or enforce the structured summary format.
- **Gaps to fully implement**:
  - Prompt edits in `workflows/planning/prompts/decomposition-guide.md`
    (impacts, IDs, effort/capability, `workflow: null`, recursion depth).
  - `role.md` — enumerate allowed + disallowed tools verbatim, with
    the "emit `PRD_EXECUTE_FAILED` rather than probe" instruction.
  - `task.md` — structured summary format (children, deps, overlaps,
    parent-blocks status). Remove dead `_template.md` reference, or
    add a real template file.
  - Add the post-decomposition verification shell task
    (`uv run prd children {prd_id}` count-match).
  - Snapshot tests for the prompt directives.
- **Recommendation**: do-now — bundle with PRD-567.2 (agent permission
  hygiene) as a single "planning loop reliability" PR. PRD-229 is the
  hard-enforcement successor to this PRD and depends on the PRD-227
  template system; prefer shipping this soft-enforcement version first
  regardless of whether 229 ever lands.
