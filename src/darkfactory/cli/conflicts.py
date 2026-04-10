"""CLI subcommand: prd conflicts."""

from __future__ import annotations

import argparse
import json

from darkfactory import containment, impacts
from darkfactory.cli._shared import _find_repo_root, _load


def cmd_conflicts(args: argparse.Namespace) -> int:
    prds = _load(args.prd_dir)
    if args.prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {args.prd_id}")
    prd = prds[args.prd_id]
    repo_root = _find_repo_root(args.prd_dir)
    conflicts = impacts.find_conflicts(prd, prds, repo_root)

    # Use effective_impacts so containers show their aggregated view
    # (union of descendants) rather than an empty declared list.
    try:
        effective = impacts.effective_impacts(prd, prds)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if args.json:
        print(
            json.dumps(
                {
                    "id": prd.id,
                    "effective_impacts": effective,
                    "conflicts": [
                        {"id": other_id, "files": sorted(files)}
                        for other_id, files in conflicts
                    ],
                },
                indent=2,
            )
        )
        return 0

    if not effective:
        kids = containment.children(prd.id, prds)
        if kids:
            print(
                f"{prd.id} is a container with {len(kids)} children that "
                "have no declared impacts yet"
            )
        else:
            print(f"{prd.id} has no declared impacts; cannot compute overlaps")
        return 0
    if not conflicts:
        print(f"{prd.id} has no impact conflicts with other PRDs")
        print(f"  (effective impact set: {len(effective)} pattern(s))")
        return 0

    print(f"{prd.id} conflicts:")
    for other_id, files in conflicts:
        print(f"  {other_id}:")
        for f in sorted(files):
            print(f"    {f}")
    return 0
