---
id: "PRD-214"
title: "PRD frontmatter round-trip drops quotes and rewrites style"
kind: task
status: ready
priority: medium
effort: s
capability: moderate
parent: null
depends_on: []
blocks: []
impacts:
  - tools/prd-harness/src/prd_harness/prd.py
  - tools/prd-harness/tests/test_prd.py
workflow: null
target_version: null
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - bug
---

# PRD frontmatter round-trip drops quotes and rewrites style

## Summary

When a builtin (e.g. `set_status`) updates a single field in a PRD's frontmatter, the harness re-serializes the **entire** YAML block. PyYAML's `safe_dump` chooses its own quoting style, so:

- `id: "PRD-501"` becomes `id: PRD-501`
- `parent: "[[PRD-500-darkfactory-extraction]]"` becomes `parent: '[[PRD-500-darkfactory-extraction]]'`
- `blocks:` indentation may shift
- `status: ready` (the field actually being changed) becomes `status: in-progress`

The semantic change is correct, but every other field in the file shows up in `git diff` too. This pollutes review, makes the round-trip-preservation invariant from the design plan a lie, and means every harness-driven status transition triggers spurious diffs that obscure what actually changed.

## Motivation

A core design principle of the harness is that builtins mutate **only** the field they're modifying — `git diff` after `set_status` should show one or two lines, not the entire frontmatter block. Today this is broken.

This also matters for hand-edited PRDs: the author's preferred quoting style (the project uses double-quoted strings for `id` and wikilinks per the schema) should be preserved when the harness touches the file.

## Requirements

1. After `set_status` runs against a PRD, `git diff` shows only the `status:` line (and `updated:` if bumped).
2. Other fields' quoting style is preserved byte-for-byte.
3. Body content below the closing `---` is preserved byte-for-byte (this part already works).
4. The fix works for any single-field mutation — `set_status`, `touch_updated`, etc.

## Technical Approach

Two viable approaches:

### Option A: ruamel.yaml round-trip mode

Replace `pyyaml` with `ruamel.yaml` in round-trip mode (`YAML(typ="rt")`), which preserves comments, quoting style, and key order on re-serialize. This is the standard answer for frontmatter manipulation tools.

Cost: new dependency; slightly slower; mypy stubs.

### Option B: line-based surgical edit

Don't re-serialize at all. For single-field updates, use a regex or line-walker to find the `^<field>:` line in the frontmatter block and rewrite *only that line*. Leave the rest of the file alone.

```python
def update_frontmatter_field(path: Path, field: str, value: str) -> None:
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    in_fm = False
    for i, line in enumerate(lines):
        if line.strip() == "---":
            in_fm = not in_fm
            if not in_fm:
                break
            continue
        if in_fm and line.startswith(f"{field}:"):
            lines[i] = f"{field}: {value}\n"
            break
    path.write_text("".join(lines))
```

Cost: doesn't handle multi-line values; can't add a field that doesn't exist; quoting of the new value is the caller's problem.

For the harness's use cases (`set_status`, `touch_updated`), Option B is sufficient and avoids the new dependency. Recommend Option B.

## Acceptance Criteria

- [ ] AC-1: `set_status` followed by `git diff` shows only the changed field.
- [ ] AC-2: Test asserts byte-for-byte preservation of all unmodified frontmatter fields and body content across a round-trip.
- [ ] AC-3: Test covers the wikilink-quoting case (`parent`, `depends_on`, `blocks`).
- [ ] AC-4: Existing tests for `prd.parse` / `prd.load_all` continue to pass.

## References

- [[PRD-213-set-status-wrong-repo]] — discovered together
- The original architecture risks section in `.claude/plans/fizzy-herding-acorn.md` calls this out as "Frontmatter round-trip drift"
