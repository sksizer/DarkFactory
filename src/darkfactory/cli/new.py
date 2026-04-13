"""cmd_new — create a new draft PRD from a template."""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Mapping
from datetime import date
from darkfactory.model import PRD_ID_RE, dump_frontmatter, load_all
from darkfactory.utils.shell import run_foreground


def _slugify(title: str) -> str:
    """Convert a title to kebab-case slug."""
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug or "untitled"


def _next_flat_prd_id(prds: Mapping[str, object]) -> str:
    """Find the next unused flat PRD id (PRD-NNN) above the existing max."""
    flat_ids = [
        int(pid.removeprefix("PRD-")) for pid in prds if re.match(r"^PRD-\d+$", pid)
    ]
    next_n = (max(flat_ids) + 1) if flat_ids else 1
    return f"PRD-{next_n:03d}"


DRAFT_TEMPLATE_BODY = """# {title}

## Summary

<!-- 1-3 sentence elevator pitch. What does this deliver and why does it matter? -->

## Motivation

<!-- What problem does this solve? Who benefits? What happens if we don't build it? -->

## Requirements

### Functional

1. ...

### Non-Functional

1. ...

## Technical Approach

<!-- High-level design: affected modules, data flow, key libraries. -->

## Acceptance Criteria

- [ ] AC-1: ...

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

## References

<!-- ALWAYS use wikilinks to reference other PRDs. -->
"""


def cmd_new(args: argparse.Namespace) -> int:
    prds = load_all(args.data_dir) if (args.data_dir / "prds").exists() else {}

    # Pick ID
    if args.id:
        if not PRD_ID_RE.match(args.id):
            raise SystemExit(f"invalid PRD id: {args.id!r}")
        if args.id in prds:
            raise SystemExit(f"PRD id {args.id!r} already exists")
        new_id = args.id
    else:
        new_id = _next_flat_prd_id(prds)

    slug = _slugify(args.title)
    filename = f"{new_id}-{slug}.md"
    path = args.data_dir / "prds" / filename
    if path.exists():
        raise SystemExit(f"file already exists: {path}")

    today = date.today().isoformat()
    frontmatter = {
        "id": new_id,
        "title": args.title,
        "kind": args.kind,
        "status": "draft",
        "priority": args.priority,
        "effort": args.effort,
        "capability": args.capability,
        "parent": None,
        "depends_on": [],
        "blocks": [],
        "impacts": [],
        "workflow": None,
        "assignee": None,
        "reviewers": [],
        "target_version": None,
        "created": today,
        "updated": today,
        "tags": [],
    }

    body = DRAFT_TEMPLATE_BODY.format(title=args.title)
    content = f"---\n{dump_frontmatter(frontmatter)}---\n\n{body}"

    (args.data_dir / "prds").mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Created {path}")

    if args.open:
        editor = os.environ.get("EDITOR", "")
        if editor:
            run_foreground([editor, str(path)])

    if getattr(args, "discuss", False):
        from darkfactory.cli.discuss import launch_discuss_for_prd

        return launch_discuss_for_prd(new_id, args)

    return 0
