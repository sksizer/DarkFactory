---
id: "PRD-216"
title: "Canonicalize PRD list fields to reduce diff churn"
kind: task
status: done
priority: medium
effort: s
capability: simple
parent: null
depends_on:
  - "[[PRD-214-frontmatter-roundtrip-drift]]"
blocks: []
impacts:
  - python/darkfactory/prd.py
  - python/darkfactory/cli.py
  - tests/test_prd.py
  - tests/test_cli_normalize.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - hygiene
---

# Canonicalize PRD list fields to reduce diff churn

## Summary

PRD frontmatter contains several list fields (`depends_on`, `blocks`, `tags`, `impacts`) that have no semantic ordering — they're set-like. When two different agents or workflow runs touch the same field they can produce the same logical content in different orders, causing spurious diffs and merge conflicts.

Add a canonical ordering for each list field and a helper that any harness-driven mutation goes through, so the on-disk representation is stable and deterministic. Leave manual edits alone unless the user opts into normalization.

## Motivation

Today, an agent that adds `PRD-072` to an epic's `blocks:` field can produce either:

```yaml
blocks:
  - "[[PRD-070]]"
  - "[[PRD-071]]"
  - "[[PRD-072]]"
```

or:

```yaml
blocks:
  - "[[PRD-072]]"
  - "[[PRD-070]]"
  - "[[PRD-071]]"
```

depending on what order it constructed the list. Both are equivalent, but the diff is noisy and a second run would re-shuffle it. Multiply by all the planning workflow runs and the dev-PRD directory accumulates churn that obscures real changes.

## Requirements

1. Each known list field has a documented canonical order:
   - `tags` — alphabetical (case-insensitive)
   - `impacts` — alphabetical by path string
   - `depends_on`, `blocks` — natural-sort by PRD ID (the same sort `prd status` uses), with the wikilink wrapping preserved
2. A helper `normalize_list_field_at(path, field, items)` accepts a list, applies the canonical sort for that field, and rewrites only the lines belonging to that field on disk — preserving everything else byte-for-byte (same invariant as `update_frontmatter_field_at`).
3. A subcommand `prd normalize [<PRD-ID> | --all]` runs the normalization across one or all PRDs as a one-shot cleanup. Reports how many files changed.
4. Manual single-line edits to other frontmatter fields are unaffected — the helper only touches the specified list field.
5. The helper is invoked from any harness builtin that mutates list fields (none today; future PRD-220 graph execution may introduce some).

## Technical Approach

### Sort keys

Reuse the existing sort key infrastructure:

```python
from .prd import parse_id_sort_key

CANONICAL_SORTS: dict[str, Callable[[str], object]] = {
    "tags": str.casefold,
    "impacts": lambda s: s,
    "depends_on": _wikilink_sort_key,
    "blocks": _wikilink_sort_key,
}


def _wikilink_sort_key(item: str) -> tuple[int, ...]:
    """Sort key for ``[[PRD-X-slug]]`` strings — extracts the ID and applies natural sort."""
    inner = item.strip("[]")
    prd_id = inner.split("-", 2)[:2]  # ["PRD", "4.2.1"]
    return parse_id_sort_key("-".join(prd_id))
```

### Surgical list-field rewrite

The list-field analogue of `update_frontmatter_field_at` needs to handle multi-line values. Algorithm:

1. Locate the field's header line (e.g. `^blocks:`).
2. Walk forward, consuming lines that match the YAML list-item indent pattern (`^  - ` or similar).
3. Replace the consumed range with the sorted items in the same indent style.
4. Leave the rest of the file alone.

Limitations: only works for block-style lists (`- item` on its own line), not flow-style (`[a, b]`). The harness's PRDs all use block style so this is fine.

### `prd normalize` subcommand

```
prd normalize PRD-070       # one PRD
prd normalize --all         # every PRD in the dir
prd normalize --all --check # exit non-zero if any would change
```

`--check` makes it CI-friendly.

## Acceptance Criteria

- [ ] AC-1: `normalize_list_field_at` sorts a `tags` field alphabetically and writes only the field's lines.
- [ ] AC-2: `normalize_list_field_at` sorts `blocks` by natural PRD ID order (`PRD-1.2` before `PRD-1.10`).
- [ ] AC-3: Other frontmatter fields and the body are byte-identical after normalization.
- [ ] AC-4: `prd normalize PRD-X` reports "no changes" when the file is already canonical.
- [ ] AC-5: `prd normalize --all --check` exits non-zero on at least one drifted file in a fixture set, and zero on a canonical set.
- [ ] AC-6: Test covers flow-style list rejection (raise a clear error rather than silently mangling).

## Open Questions

- [ ] Should `prd normalize` also touch the `body` (e.g. acceptance-criteria ordering)? Probably not — the body is the human's domain.
- [ ] Should the planning workflow auto-run normalize on every PRD it generates? Probably yes, as a final ShellTask.
- [ ] Wikilink slug extraction edge cases: does the sort key need the slug, or just the ID? Just the ID — natural sort uses `parse_id_sort_key`.

## References

- [[PRD-214-frontmatter-roundtrip-drift]] — same byte-preservation invariant
- [[PRD-220-graph-execution]] — first consumer that may need to mutate list fields
