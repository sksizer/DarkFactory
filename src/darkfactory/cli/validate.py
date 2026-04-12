"""Validate command — check PRD graph integrity."""

from __future__ import annotations

import argparse
import sys

from darkfactory import checks, graph
from darkfactory.graph import containment, impacts
from darkfactory.cli._shared import _find_repo_root, _load


def cmd_validate(args: argparse.Namespace) -> int:
    prds = _load(args.data_dir)
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Filename ↔ id consistency
    for prd in prds.values():
        if not prd.path.name.startswith(f"{prd.id}-"):
            errors.append(f"{prd.path.name}: id {prd.id!r} does not match filename")

    # 2. Missing dep references
    for prd in prds.values():
        for dep_id in prd.depends_on:
            if dep_id not in prds:
                errors.append(f"{prd.id}: depends_on references unknown {dep_id}")
        for blk_id in prd.blocks:
            if blk_id not in prds:
                errors.append(f"{prd.id}: blocks references unknown {blk_id}")
        if prd.parent and prd.parent not in prds:
            errors.append(f"{prd.id}: parent references unknown {prd.parent}")

    # 3. Cycles in dependency DAG
    g = graph.build_graph(prds)
    cycles = graph.detect_cycles(g)
    for cycle in cycles:
        errors.append(f"dependency cycle: {' -> '.join(cycle)} -> {cycle[0]}")

    # 4. Containment tree cycles
    for prd in prds.values():
        seen = {prd.id}
        cur = prd
        while cur.parent:
            if cur.parent in seen:
                errors.append(f"{prd.id}: containment cycle via parent chain")
                break
            seen.add(cur.parent)
            nxt = prds.get(cur.parent)
            if nxt is None:
                break
            cur = nxt

    # 5. Container PRDs must have empty impacts.
    # The leaf-only rule (see impacts.py) gives us a single source of
    # truth: containers' effective impacts are computed from their
    # descendants, so declared impacts on a container would be a
    # divergent second source that could silently drift.
    for prd in prds.values():
        kids = containment.children(prd.id, prds)
        if kids and prd.impacts:
            errors.append(
                f"{prd.id}: container PRD (has {len(kids)} children) "
                f"must have impacts: [] — declared impacts on containers "
                f"create divergence with the computed descendant union "
                f"(got {prd.impacts!r})"
            )

    # 6. Impact overlap warnings (ready PRDs only).
    # Uses effective_impacts (aggregated for containers) and exempts
    # parent/child pairs (containment is not conflict).
    try:
        repo_root = _find_repo_root(args.data_dir)
        files = impacts.tracked_files(repo_root)
    except Exception:  # noqa: BLE001 — best-effort outside a git repo
        files = []

    if files:
        ready = [p for p in prds.values() if p.status == "ready"]
        for i, a in enumerate(ready):
            for b in ready[i + 1 :]:
                # Skip if there's an explicit dep relation in either direction.
                if b.id in a.depends_on or a.id in b.depends_on:
                    continue
                try:
                    overlap = impacts.impacts_overlap(a, b, files, prds)
                except ValueError:
                    # effective_impacts refused — already reported by the
                    # container-has-impacts check above. Skip silently
                    # here so we don't double-report.
                    continue
                if overlap:
                    warnings.append(
                        f"{a.id} and {b.id} have overlapping impacts "
                        f"({len(overlap)} files) but no explicit dependency"
                    )

    # 7. Undeclared impacts on leaves (informational)
    undeclared = [
        p.id
        for p in prds.values()
        if p.status == "ready"
        and not p.impacts
        and not containment.children(p.id, prds)  # leaves only
    ]
    if undeclared and args.verbose:
        warnings.append(
            f"{len(undeclared)} ready leaf PRDs have no declared impacts "
            "(undeclared = sequential)"
        )

    # 8. Review-status PRDs whose branch is gone from origin.
    try:
        repo_root = _find_repo_root(args.data_dir)
        git_state = checks.SubprocessGitState(str(repo_root))
        for issue in checks.validate_review_branches(prds, git_state):
            warnings.append(issue.message)
    except Exception:  # noqa: BLE001 — best-effort outside a git repo
        pass

    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    for warn in warnings:
        print(f"WARN:  {warn}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"OK: {len(prds)} PRDs valid ({len(warnings)} warning(s))")
    return 0
