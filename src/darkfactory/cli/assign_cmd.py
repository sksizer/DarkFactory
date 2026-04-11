"""CLI subcommand: prd assign."""

from __future__ import annotations

import argparse

from darkfactory import assign
from darkfactory.cli._shared import _emit_json, _load, _load_workflows_or_fail
from darkfactory.model import parse_id_sort_key, set_workflow


def cmd_assign(args: argparse.Namespace) -> int:
    """Compute the workflow assignment for every PRD, optionally persist.

    Output is a table of ``PRD-id -> workflow-name``. With ``--write``,
    the resolved workflow name is persisted into each PRD's frontmatter
    (only for PRDs that don't already have an explicit workflow field —
    the command is idempotent on re-run).
    """
    prds = _load(args.data_dir)
    workflows = _load_workflows_or_fail(args.workflows_dir)

    if not workflows:
        if args.json:
            return _emit_json([])
        else:
            print(f"{'PRD':14} {'Workflow':20} Source")
            print("-" * 50)
        return 0

    try:
        assignments = assign.assign_all(prds, workflows)
    except KeyError as exc:
        raise SystemExit(str(exc))

    if args.json:
        return _emit_json(
            [
                {
                    "id": prd_id,
                    "workflow": wf.name,
                    "explicit": prds[prd_id].workflow is not None,
                }
                for prd_id, wf in sorted(
                    assignments.items(),
                    key=lambda kv: parse_id_sort_key(kv[0]),
                )
            ]
        )

    # Human-readable table. Show assignment origin in the `Source` column.
    print(f"{'PRD':14} {'Workflow':20} Source")
    print("-" * 50)
    for prd_id in sorted(assignments.keys(), key=parse_id_sort_key):
        wf = assignments[prd_id]
        source = "explicit" if prds[prd_id].workflow else "predicate"
        print(f"{prd_id:14} {wf.name:20} {source}")

    if args.write:
        written = 0
        for prd_id, wf in assignments.items():
            prd = prds[prd_id]
            if prd.workflow is None:
                set_workflow(prd, wf.name)
                written += 1
        print(f"\nPersisted {written} workflow assignments to frontmatter.")
    return 0
