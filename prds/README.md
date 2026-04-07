# Harness Dev PRDs

A parallel PRD set for tracking the harness's own development work. These PRDs use the same schema as `docs/prd/` but live here so they travel with the tool when it's extracted into a standalone repo.

Stored separately from the canonical project PRDs so:
- Harness development doesn't pollute the pumice project tracking
- When `tools/prd-harness/` is extracted, its work history comes along
- We can dogfood the harness against its own work as a rough prototype before wiring up the full workflow executor

## ID scheme

Dev PRDs use the `PRD-2NN` range to avoid collision with the canonical set (which currently tops out at PRD-110). When the harness is extracted, the numbers can be renumbered freely since nothing outside this directory references them.

## Running the harness against these

```bash
just prd-dev status
just prd-dev tree PRD-200
just prd-dev next --limit 5
```

The `prd-dev` justfile recipe forwards to the harness with `--prd-dir tools/prd-harness/dev-prds`.

## Using them to drive work

The current workflow is manual dogfooding — pick a PRD, implement it, flip its status from `ready` → `in-progress` → `review` by editing the frontmatter. Once the workflow executor (PRD-210/PRD-211) lands, we can automate this by running `just prd-dev run PRD-201 --execute` and letting the harness orchestrate.
