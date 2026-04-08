---
id: "PRD-505"
title: "Verify darkfactory end-to-end and push first commit"
kind: task
status: done
priority: high
effort: xs
capability: simple
parent: "[[PRD-500-darkfactory-extraction]]"
depends_on:
  - "[[PRD-504-darkfactory-cli-defaults]]"
blocks:
  - "[[PRD-510-prd-new-subcommand]]"
  - "[[PRD-520-pumice-harness-cleanup]]"
impacts:
  - (darkfactory repo) all files
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - extraction
  - verification
---

# Verify darkfactory end-to-end and push first commit

## Summary

Final checkpoint before the extraction lands: run every check that matters, dogfood the CLI against the ported PRDs, and push the first commit to `main` on darkfactory. This PRD is the integration test for the whole PRD-500 epic.

## Requirements

1. Fresh clone test: remove any local state and re-clone darkfactory from scratch, then run the full verification sequence below.
2. `mise install` succeeds (python 3.12 + uv installed).
3. `uv sync` resolves and installs the package + dev dependencies.
4. `uv run pytest` reports all tests passing (target: 200+).
5. `uv run mypy src tests workflows` passes with `strict = true` and reports "Success: no issues".
6. `uv run prd status` reads the migrated dev-PRDs and prints sensible output.
7. `uv run prd tree PRD-200` shows the workflow execution layer tree.
8. `uv run prd list-workflows` shows `default` with priority 0.
9. `uv run prd plan PRD-201` prints an execution plan with the default workflow.
10. `uv run prd run PRD-500 --dry-run` (if the epic is at least loadable) completes without error.
11. First commit is pushed to `main` with a descriptive message.

## Technical Approach

```bash
# From a fresh clone
cd ~/Developer
rm -rf darkfactory-verify
gh repo clone sksizer/darkfactory darkfactory-verify
cd darkfactory-verify

# Copy over all the staged extraction content from the working repo
rsync -a --exclude='.git' ~/Developer/darkfactory/ ./

# Verify
mise install
uv sync
uv run pytest -q                    # expect 200+ pass
uv run mypy src tests workflows     # expect clean
uv run prd status                   # expect 12+ PRDs listed
uv run prd tree PRD-200             # expect full tree
uv run prd list-workflows           # expect default
uv run prd plan PRD-201             # expect plan output
```

If every step passes, commit + push:

```bash
cd ~/Developer/darkfactory
git add -A
git commit -m "$(cat <<'EOF'
feat: initial port of the PRD harness from pumice

Migrates tools/prd-harness/ out of sksizer/pumice into its own repo.
Package renamed from prd_harness to darkfactory; CLI defaults updated
for standalone operation (prds/ and workflows/ at repo root).

Full harness functionality (see pumice PRD-110 for original design):

- Layer 1: declarative workflow authoring (workflow.py)
- Layer 2: deterministic SDLC built-ins (builtins.py)
- Layer 3: runner + CLI subcommands (prd status / next / validate /
  tree / children / orphans / undecomposed / conflicts /
  list-workflows / assign / plan / run)

200+ tests pass, mypy --strict clean. Dogfooded against the migrated
dev-PRDs (PRD-200..211 workflow execution layer + PRD-500..505
extraction + PRD-510 prd new + PRD-520 pumice cleanup).
EOF
)"
git push origin main
```

## Acceptance Criteria

- [ ] AC-1: Fresh clone + mise install + uv sync all succeed.
- [ ] AC-2: `uv run pytest` passes (200+ tests).
- [ ] AC-3: `uv run mypy src tests workflows` reports "Success: no issues".
- [ ] AC-4: `uv run prd status` prints accurate counts from `prds/`.
- [ ] AC-5: `uv run prd tree PRD-200` shows the workflow execution layer tree.
- [ ] AC-6: `uv run prd list-workflows` shows default workflow.
- [ ] AC-7: `uv run prd plan PRD-201` prints a plan.
- [ ] AC-8: First commit pushed to github.com/sksizer/darkfactory/main.

## References

- [[PRD-504-darkfactory-cli-defaults]] — dependency
- [[PRD-510-prd-new-subcommand]] — follow-on feature
- [[PRD-520-pumice-harness-cleanup]] — follow-on pumice cleanup
