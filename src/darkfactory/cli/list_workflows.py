"""List-workflows command — display all loaded workflows."""

from __future__ import annotations

import argparse
import json

from darkfactory.cli._shared import _load_workflows_or_fail


def cmd_list_workflows(args: argparse.Namespace) -> int:
    """List all loaded workflows with priority and description."""
    workflows = _load_workflows_or_fail(args.workflows_dir)
    if not workflows:
        print("(no workflows loaded)")
        return 0

    # Sort by descending priority then alphabetically for stable display.
    sorted_wfs = sorted(
        workflows.values(),
        key=lambda w: (-w.priority, w.name),
    )

    if args.json:
        payload = [
            {
                "name": w.name,
                "priority": w.priority,
                "description": w.description,
                "task_count": len(w.tasks),
                "workflow_dir": str(w.workflow_dir) if w.workflow_dir else None,
            }
            for w in sorted_wfs
        ]
        print(json.dumps(payload, indent=2))
        return 0

    for w in sorted_wfs:
        # Header line: name, priority, task count
        print(f"{w.name:20} priority={w.priority:<3} tasks={len(w.tasks)}")
        if w.description:
            # Indent description under the header
            for line in w.description.splitlines():
                print(f"  {line}")
        print()
    return 0
