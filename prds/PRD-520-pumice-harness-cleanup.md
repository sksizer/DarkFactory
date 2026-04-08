---
id: "PRD-520"
title: "Pumice cleanup — remove tools/prd-harness/"
kind: task
status: done
priority: medium
effort: s
capability: simple
parent: null
depends_on:
  - "[[PRD-505-darkfactory-verify-and-push]]"
blocks: []
impacts:
  - tools/prd-harness/**
  - scripts/prd
  - justfile
  - Makefile
  - mise.toml
  - .gitignore
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - pumice
  - cleanup
  - extraction
---

# Pumice cleanup — remove tools/prd-harness/

## Summary

Once darkfactory is live and verified (PRD-505 done), remove the harness code from pumice to avoid dual maintenance. This is a pumice-side PR, separate from the darkfactory extraction. The cleanup touches the harness directory, the convenience scripts/recipes, and the mise.toml entries that were added for the harness's Python toolchain.

## Requirements

1. `tools/prd-harness/` directory is removed entirely.
2. `scripts/prd` wrapper script is removed.
3. `justfile`: `prd` and `prd-dev` recipes are removed.
4. `Makefile`: `prd` target is removed; `prd` is dropped from `.PHONY` and from the help text.
5. `mise.toml`: `python = "3.12"` and `uv = "latest"` entries are removed (assuming nothing else in pumice uses them).
6. `.gitignore`: harness-specific Python entries (`.venv/`, `.mypy_cache/`, `.pytest_cache/`, `tools/prd-harness/**/.obsidian/`) are removed or left alone if they remain useful (the `__pycache__/`/`*.pyc` entries can stay; they're harmless).
7. `docs/prd/PRD-110-prd-harness.md` — decision: leave in place as historical design doc, OR move to darkfactory/docs/. Default: leave it; cross-link to darkfactory in a note.
8. The pumice repo's test suite + CI still pass after removal.
9. No references to `prd_harness` or `tools/prd-harness/` remain in pumice source/docs, except optionally in PRD-110 (as a historical pointer).

## Technical Approach

```bash
# Run from pumice repo root
cd /Users/sksizer2/Developer/pumice
git checkout -b chore/remove-harness

# Delete the harness package
git rm -r tools/prd-harness/

# Delete the wrapper
git rm scripts/prd

# Edit justfile — remove the two recipes
# Edit Makefile — remove the prd target + help line + .PHONY entry
# Edit mise.toml — remove python and uv lines
# Edit .gitignore — remove harness Python entries if they'll no longer be needed

# Verify nothing else references the harness
grep -r "prd_harness" . --exclude-dir=.git --exclude-dir=.worktrees || echo "clean"
grep -r "tools/prd-harness" . --exclude-dir=.git --exclude-dir=.worktrees || echo "clean"

# Run the existing pumice checks
pnpm frontend:lint
pnpm frontend:typecheck
cd src-tauri && cargo clippy -- -D warnings
cd src-tauri && cargo test

# Commit + PR
git add -A
git commit -m "chore: remove tools/prd-harness/ (migrated to darkfactory)"
gh pr create --base main --title "chore: remove tools/prd-harness/ after darkfactory extraction" ...
```

Optional: update `docs/prd/PRD-110-prd-harness.md` with a note at the top:

> **Status note (2026-04-08)**: This PRD remains here as the original design document for the PRD harness. The implementation has since been extracted to its own repository at [github.com/sksizer/darkfactory](https://github.com/sksizer/darkfactory). Further development happens there.

## Acceptance Criteria

- [ ] AC-1: `tools/prd-harness/` is deleted.
- [ ] AC-2: `scripts/prd` is deleted.
- [ ] AC-3: `justfile` no longer has `prd` or `prd-dev` recipes.
- [ ] AC-4: `Makefile` no longer has the `prd` target.
- [ ] AC-5: `mise.toml` no longer pins python/uv.
- [ ] AC-6: `grep -r "prd_harness" .` in pumice (excluding `.git`/`.worktrees`) returns no results.
- [ ] AC-7: Pumice's `pnpm frontend:test` and `cargo test` still pass.
- [ ] AC-8: A PR targeting pumice `main` is opened with the removal and successfully merges.

## Open Questions

- [x] **RESOLVED**: Keep PRD-110 in pumice as a historical design doc, with a note pointing to darkfactory for the live code.

## References

- [[PRD-505-darkfactory-verify-and-push]] — dependency (darkfactory must be live first)
- `docs/prd/PRD-110-prd-harness.md` — the original pumice-side harness spec
