---
id: "PRD-212"
title: "Containment-aware impact overlap detection"
kind: task
status: done
priority: high
effort: s
capability: moderate
parent: null
depends_on: []
blocks: []
impacts:
  - python/darkfactory/impacts.py
  - python/darkfactory/cli.py
  - tests/test_impacts.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - impacts
  - validation
---

# Containment-aware impact overlap detection

## Summary

Two related improvements to the impact-overlap system, discovered while dogfooding PRD-500 (darkfactory migration):

1. **Parent/child overlaps are exempt from conflict warnings.** When PRD-A contains PRD-B via the containment tree, an impact overlap between them is definitional — the parent, by definition, encompasses its children. Warning about it is noise.

2. **Container PRDs don't declare `impacts` — the validator enforces empty, and `effective_impacts()` aggregates from descendants.** Allowing both a declared list on a container AND children with their own declared impacts creates two sources of truth that can silently drift. The rule is one-way: leaves declare, containers inherit.

## Motivation

While drafting PRD-500 (the darkfactory migration epic), the validator flagged two overlap warnings:

- PRD-500's broad `impacts: [tools/prd-harness/**]` overlapped with every child PRD — a false positive, because PRD-500 *contains* those children by design.
- The workaround was to set `impacts: []` on PRD-500, which silenced the warning but for the wrong reason (the validator thinks "undeclared impacts are unknown, can't compare") rather than the right reason ("this is a container, its impact is the union of its children's").

Both issues become more urgent once we start drafting epics systematically:

- Authors will keep hitting the "empty impacts on containers" footgun
- Queries like `prd conflicts PRD-500` will return "no conflicts" because the epic has nothing declared, even though its children collectively touch many files
- Two sibling tasks under the same epic can't both impact the same file without an explicit `depends_on` — which is correct and must keep working

The fix is structural: containers don't declare impacts, containers' effective impacts are computed from their descendants, and parent/child relationships are exempt from overlap checks.

## Design

### Rule 1: Containers must have empty `impacts`

**Definition**: A PRD is a *container* if it has at least one child via the `parent` field (i.e. `containment.children(prd.id, prds)` is non-empty). A PRD is a *leaf* otherwise.

**Rule**: Leaf PRDs declare their `impacts`. Container PRDs MUST have `impacts: []`. This is enforced by `prd validate` as a hard error.

**Rationale**: Two sources of truth diverge. If an epic declares `impacts: [A]` and its children declare `impacts: [B, C]`, what's the epic's effective impact? If we pick one rule (e.g. "declared wins"), the other is silently ignored and can become wrong. If we require both to agree, the validator has to enforce it anyway — so just remove the option.

**What about containers that genuinely touch files?** If an epic really needs to modify, say, a top-level README as part of the work, that work is its own leaf task under the epic. The clean model is "only leaves do code work; containers organize leaves."

### Rule 2: `effective_impacts()` aggregates descendants for containers

New helper in `impacts.py`:

```python
def effective_impacts(prd: PRD, prds: dict[str, PRD]) -> list[str]:
    """Return the effective impact patterns for a PRD.

    Leaves: their declared ``prd.impacts``.
    Containers: the union of all descendants' declared impacts, sorted.

    Raises ``ValueError`` if a container PRD has non-empty declared
    impacts — that's a tree-consistency violation and should have been
    caught by ``validate``.
    """
    kids = containment.children(prd.id, prds)
    if not kids:
        return list(prd.impacts)

    if prd.impacts:
        raise ValueError(
            f"{prd.id} is a container (has children) but declares impacts. "
            "Containers must have impacts: []; their impact set is computed "
            "from descendants."
        )

    aggregated: set[str] = set()
    for descendant in containment.descendants(prd.id, prds):
        # Only include direct-declared impacts from descendants that are
        # themselves leaves. (Intermediate containers contribute via their
        # own descendants in the same walk.)
        if not containment.children(descendant.id, prds):
            aggregated.update(descendant.impacts)
    return sorted(aggregated)
```

### Rule 3: Parent/child overlaps are exempt

Modify `impacts_overlap()` to take the PRD set and skip when one PRD is a descendant of the other:

```python
def impacts_overlap(
    a: PRD, b: PRD, files: list[str], prds: dict[str, PRD]
) -> set[str]:
    """Files both PRDs would touch.

    Returns an empty set when one PRD contains the other via the
    containment tree — parent/child overlaps are expected, not
    conflicts.
    """
    # Parent/child exemption
    b_ancestors = {anc.id for anc in containment.ancestors(b.id, prds)}
    if a.id in b_ancestors:
        return set()
    a_ancestors = {anc.id for anc in containment.ancestors(a.id, prds)}
    if b.id in a_ancestors:
        return set()

    a_impacts = effective_impacts(a, prds)
    b_impacts = effective_impacts(b, prds)
    if not a_impacts or not b_impacts:
        return set()
    return expand_impacts(a_impacts, files) & expand_impacts(b_impacts, files)
```

`find_conflicts` and `prd validate` automatically benefit because they both call `impacts_overlap` underneath.

### Validator changes

In `cmd_validate` (cli.py), add a new hard-error check:

```python
# Rule: containers cannot declare impacts
for prd in prds.values():
    kids = containment.children(prd.id, prds)
    if kids and prd.impacts:
        errors.append(
            f"{prd.id}: container PRD (has {len(kids)} children) "
            f"must have impacts: [], got {prd.impacts!r}"
        )
```

## Effect on existing behavior

- `PRD-500` (the migration epic) works correctly: empty `impacts: []`, and `prd conflicts PRD-500` now returns the aggregate of 501-505's files.
- `PRD-200` (workflow execution layer epic) same: the PRDs I already wrote with `impacts: []` on containers keep working because they comply with the new rule.
- Sibling tasks under the same epic still get conflict warnings correctly when they touch the same files without a direct `depends_on` — that case isn't parent/child, it's sibling/sibling.
- Two unrelated epics whose descendants happen to overlap still get flagged — cross-tree conflicts are real conflicts.

## Requirements

### Functional

1. Add `effective_impacts(prd, prds)` to `impacts.py` — leaf returns declared, container returns aggregated union.
2. Raise `ValueError` if a container PRD has non-empty declared impacts when `effective_impacts` is called (belt + suspenders; the validator should catch it first).
3. Update `impacts_overlap()` signature to take the PRD set and exempt parent/child pairs.
4. Update `find_conflicts()` to pass the PRD set through.
5. Add a validator check that hard-errors when a container has non-empty impacts.
6. Update the `cmd_conflicts` CLI output to use `effective_impacts` so `prd conflicts PRD-500` shows aggregated files for epics.

### Non-Functional

1. All existing tests continue to pass (202 currently).
2. `mypy --strict` clean.
3. New tests cover: parent/child exemption, effective_impacts on leaf (returns declared), effective_impacts on container (returns aggregated), validator rejects container with impacts, sibling overlap still warns.

## Technical Approach

**Files to modify**:

- `tools/prd-harness/src/prd_harness/impacts.py`:
  - Add `effective_impacts()` helper
  - Update `impacts_overlap()` signature: add `prds: dict[str, PRD]` parameter
  - Update `find_conflicts()` to call the new signature and use effective impacts
  - Add imports from `containment`
- `tools/prd-harness/src/prd_harness/cli.py`:
  - `cmd_validate`: add the container-has-impacts error check
  - `cmd_conflicts`: use `effective_impacts(prd, prds)` instead of `prd.impacts` for the "no declared impacts" early return check
  - Update `impacts.impacts_overlap` call sites to pass `prds`
- `tools/prd-harness/tests/test_impacts.py`:
  - Add tests for `effective_impacts` (leaf, container, container-with-declared raises, nested containers aggregate correctly)
  - Add tests for the parent/child exemption in `impacts_overlap`
- `tools/prd-harness/tests/test_cli_workflows.py` (or a new fixture):
  - Update any test that constructs `impacts_overlap` calls with the old 3-arg signature

## Acceptance Criteria

- [ ] AC-1: `effective_impacts(leaf_prd, prds)` returns the leaf's declared impacts.
- [ ] AC-2: `effective_impacts(epic_prd, prds)` returns the union of all descendant leaves' impacts, sorted.
- [ ] AC-3: `effective_impacts(container_with_declared_impacts, prds)` raises `ValueError`.
- [ ] AC-4: `impacts_overlap(parent, child, files, prds)` returns `set()` regardless of actual file overlap.
- [ ] AC-5: `impacts_overlap(sibling1, sibling2, files, prds)` still returns the intersection — siblings must still be warned about.
- [ ] AC-6: `prd validate` emits a hard error when a container has non-empty `impacts`.
- [ ] AC-7: `prd conflicts PRD-500` returns the aggregated file set for the epic, not an empty result.
- [ ] AC-8: All 202 existing tests still pass.
- [ ] AC-9: `mypy --strict` clean across src + tests + workflows.

## Open Questions

- [ ] **OPEN**: Should `effective_impacts` also support a PRD with NO parent and NO children (a lone root)? Currently treated as a leaf (returns declared). That's consistent but worth confirming.
- [x] **RESOLVED**: Declared vs aggregated precedence. Answer: containers can't declare, full stop. No ambiguity, enforced by the validator. (This was the concern that motivated the PRD.)
- [ ] **DEFERRED**: Surfacing container impact aggregation in `prd plan` output — show "this workflow run would touch N files across M PRDs" for context. Nice-to-have, not required for the core fix.

## References

- [[PRD-500-darkfactory-migration]] — surfaced this issue during dogfooding
- [[PRD-002-data-persistence]] — earlier design note on impacts (pre-containment awareness)
- `tools/prd-harness/src/prd_harness/impacts.py` — implementation target
- `tools/prd-harness/src/prd_harness/containment.py` — already has `ancestors` / `descendants` / `children` helpers
