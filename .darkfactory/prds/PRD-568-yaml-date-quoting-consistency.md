---
id: PRD-568
title: "Fix inconsistent YAML date quoting in frontmatter round-trips"
kind: task
status: draft
priority: high
effort: s
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/prd.py
  - tests/test_prd.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: '2026-04-10'
tags:
  - bug
  - frontmatter
  - round-trip
---

# Fix inconsistent YAML date quoting in frontmatter round-trips

## Summary

PRD `created` and `updated` date fields flip between quoted (`'2026-04-09'`) and unquoted (`2026-04-09`) representations across different write paths, producing phantom diffs. The root cause is a type mismatch in PyYAML's round-trip: `safe_load` coerces bare `YYYY-MM-DD` strings into `datetime.date` objects, but `safe_dump` serializes `date` objects unquoted and `str` objects quoted. Two write paths in `prd.py` produce different representations for the same field.

## Motivation

Every `set_workflow`, `normalize_list_field_at`, or `write_frontmatter` call can flip date quoting, producing `git diff` noise that obscures the actual change. PRD-214 solved the general round-trip problem by introducing `update_frontmatter_field_at` for surgical edits, but the date quoting issue persists in the full-reserialization path (`write_frontmatter` -> `dump_frontmatter` -> `yaml.safe_dump`).

## Root cause

Three interacting problems:

### 1. PyYAML type coercion on load

`yaml.safe_load` converts bare `YYYY-MM-DD` to `datetime.date` objects:

```python
yaml.safe_load("created: 2026-04-09")   # → {'created': datetime.date(2026, 4, 9)}
yaml.safe_load("created: '2026-04-09'") # → {'created': '2026-04-09'}
```

`parse_prd()` at `prd.py:171` stores whatever `safe_load` returns:
```python
created=fm.get("created", ""),  # date object if unquoted, str if quoted
```

The `raw_frontmatter` dict carries the same mixed types.

### 2. Inconsistent update paths set dates as strings

`set_status_at()` at `prd.py:316-319` deliberately wraps dates in quotes to survive round-trip:
```python
today = date.today().isoformat()
update_frontmatter_field_at(path, {"status": new_status, "updated": f"'{today}'"})
```

But `set_workflow()` at `prd.py:486` sets the date as a bare string:
```python
fm["updated"] = date.today().isoformat()  # str, not date
```

### 3. safe_dump serializes mixed types differently

When `write_frontmatter()` calls `dump_frontmatter()` -> `yaml.safe_dump()`:
- `created` (still a `datetime.date` from load) → dumps unquoted: `created: 2026-04-09`
- `updated` (now a `str` from the update) → dumps quoted: `updated: '2026-04-09'`

Result: the same file has inconsistent quoting for date fields.

## Technical approach

**Normalize dates to strings in `raw_frontmatter` at parse time**, so `dump_frontmatter` always sees consistent types.

### Change 1: Normalize dates in `parse_prd()`

At `prd.py:171-172`, convert any `datetime.date` values to ISO strings:

```python
created=_str_date(fm.get("created", "")),
updated=_str_date(fm.get("updated", "")),
```

With a helper:
```python
def _str_date(val: Any) -> str:
    """Normalize a date-like YAML value to an ISO string."""
    if isinstance(val, date):
        return val.isoformat()
    return str(val) if val else ""
```

### Change 2: Normalize dates in `raw_frontmatter`

Also normalize `raw_frontmatter` so that `write_frontmatter()` -> `dump_frontmatter()` sees strings:

After `fm = _split_frontmatter(content)[0]` in `parse_prd()`, normalize date fields:

```python
for date_field in ("created", "updated"):
    if isinstance(fm.get(date_field), date):
        fm[date_field] = fm[date_field].isoformat()
```

This ensures `raw_frontmatter` always has strings, so `yaml.safe_dump` produces consistent quoting.

### Change 3: Choose a canonical quoting style

With dates always stored as strings, `yaml.safe_dump` will always quote them (`'2026-04-09'`) because `YYYY-MM-DD` strings look like dates to PyYAML and it quotes to prevent re-coercion. This is the correct behavior -- quoted dates survive load/dump round-trips without type mutation.

Alternatively, register a custom representer for date-like strings to force unquoted output. But **quoted is safer** because it prevents the original problem (PyYAML treating bare dates as `datetime.date` on the next load).

### Change 4: Align `set_status_at` embedded quoting

`set_status_at()` at line 319 writes `f"'{today}'"` which embeds literal quotes in the field value. After this fix, the surgical path and the full-reserialize path will both produce `updated: '2026-04-10'`. Verify this is consistent; if `dump_frontmatter` now produces `updated: '2026-04-10'` (safe_dump's own quoting), then `set_status_at` should write just `today` (without the manual `f"'{today}'"` wrapper), letting PyYAML's load/dump cycle handle quoting naturally.

Review `set_status_at` line 319 and remove the manual quote wrapping if it's now redundant.

## Acceptance criteria

- [ ] AC-1: `created` and `updated` use consistent quoting after any write operation (`set_status`, `set_workflow`, `write_frontmatter`, `normalize_list_field_at`)
- [ ] AC-2: A `write_frontmatter` round-trip does not change date field quoting: if the file had `created: '2026-04-09'`, it stays `created: '2026-04-09'`
- [ ] AC-3: `set_status_at` and `set_workflow` produce identical quoting for `updated`
- [ ] AC-4: `raw_frontmatter` date fields are always `str`, never `datetime.date`
- [ ] AC-5: Existing tests in `tests/test_prd.py` pass (update any that assert on specific quoting)
- [ ] AC-6: New test: parse a PRD with unquoted dates, call `write_frontmatter`, verify dates are consistently quoted
- [ ] AC-7: New test: parse a PRD with quoted dates, call `write_frontmatter`, verify no change

## References

- [[PRD-214-frontmatter-roundtrip-drift]] -- original fix that introduced `update_frontmatter_field_at`; this PRD addresses the remaining date-specific gap
