---
id: "PRD-510"
title: "prd new subcommand for creating draft PRDs"
kind: task
status: review
priority: medium
effort: s
capability: simple
parent: null
depends_on:
  - "[[PRD-504-darkfactory-cli-defaults]]"  # both modify cli.py; must serialize
  - "[[PRD-505-darkfactory-verify-and-push]]"
blocks: []
impacts:
  - (darkfactory repo) src/darkfactory/cli.py
  - (darkfactory repo) tests/test_cli_new.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - cli
  - authoring
---

# prd new subcommand for creating draft PRDs

## Summary

Add a `prd new <title>` CLI subcommand that creates a new draft PRD from a built-in template. No dependencies, no workflow, just enough scaffolding for a human to start drafting. Auto-picks the next available PRD id and writes the file to the configured `--prd-dir`.

This was the original request from the user that motivated the extraction — "could we get a command to make a new draft PRD that matches the template but doesn't have any dependencies, for drafting?"

## Requirements

### Functional

1. Usage: `prd new "My Title" [--kind task] [--priority medium] [--effort m] [--capability moderate] [--id PRD-NNN]`
2. Positional `title` is required. All other fields are optional with sensible defaults.
3. `--id` explicitly sets the PRD id; if omitted, the command finds the next available flat numeric id (max existing flat id + 1).
4. The slug is derived from the title: lowercased, spaces → dashes, non-alphanumeric stripped.
5. The generated frontmatter matches the schema: `status: draft`, empty `depends_on`, empty `blocks`, empty `impacts`, `parent: null`, `workflow: null`, `created/updated` to today.
6. The body contains the standard sections (Summary, Motivation, Requirements, Technical Approach, Acceptance Criteria, Open Questions, References) as empty placeholders with HTML comments describing what goes in each.
7. The file is written to `<prd-dir>/PRD-<id>-<slug>.md`.
8. Refuses to overwrite an existing file — exits with an error.
9. Prints the created file path on success.
10. `--open` flag (optional): after writing, open the file in `$EDITOR` for immediate editing.

### Non-Functional

1. No dependency on any other command — `prd new` works even if there are zero existing PRDs.
2. Respects the global `--prd-dir` flag so the user can direct the new PRD into any directory.
3. Embedded template lives in `cli.py` (or a `templates.py` constant) — no external template file required.

## Technical Approach

**Modify**: `src/darkfactory/cli.py`

Add two helpers:

```python
import re

def _slugify(title: str) -> str:
    """Convert a title to kebab-case slug."""
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug or "untitled"


def _next_flat_prd_id(prds: dict[str, PRD]) -> str:
    """Find the next unused flat PRD id (PRD-NNN) above the existing max."""
    flat_ids = [
        int(pid.removeprefix("PRD-"))
        for pid in prds
        if re.match(r"^PRD-\d+$", pid)
    ]
    next_n = (max(flat_ids) + 1) if flat_ids else 1
    return f"PRD-{next_n:03d}"
```

Command implementation:

```python
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

"""


def cmd_new(args: argparse.Namespace) -> int:
    prds = load_all(args.prd_dir) if args.prd_dir.exists() else {}

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
    path = args.prd_dir / filename
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

    args.prd_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Created {path}")

    if args.open:
        editor = os.environ.get("EDITOR", "")
        if editor:
            subprocess.run([editor, str(path)], check=False)

    return 0
```

Register the subcommand in `build_parser()`:

```python
sub_new = sub.add_parser("new", help="Create a new draft PRD from a template")
sub_new.add_argument("title", help="PRD title (positional)")
sub_new.add_argument("--id", default=None, help="Explicit PRD id (default: next flat id)")
sub_new.add_argument("--kind", default="task", choices=["epic", "feature", "component", "task"])
sub_new.add_argument("--priority", default="medium", choices=["critical", "high", "medium", "low"])
sub_new.add_argument("--effort", default="m", choices=["xs", "s", "m", "l", "xl"])
sub_new.add_argument("--capability", default="moderate", choices=["trivial", "simple", "moderate", "complex"])
sub_new.add_argument("--open", action="store_true", help="Open the new file in $EDITOR after creation")
sub_new.set_defaults(func=cmd_new)
```

**New test file**: `tests/test_cli_new.py`

Tests:
- Basic usage creates a file with expected frontmatter
- Auto-picked id increments above the max
- Explicit `--id` wins
- Duplicate id raises
- Existing file raises
- Slugify handles punctuation / unicode / empty titles
- All enum flags validate via argparse `choices`

## Acceptance Criteria

- [ ] AC-1: `prd new "My feature"` creates `prds/PRD-NNN-my-feature.md`.
- [ ] AC-2: Auto-id picks the next number above the current max.
- [ ] AC-3: `--id PRD-500` pins the id; refused if it exists.
- [ ] AC-4: Generated frontmatter passes `prd validate`.
- [ ] AC-5: Generated body has all standard sections as empty placeholders.
- [ ] AC-6: `--open` launches $EDITOR on the new file.
- [ ] AC-7: Refuses to overwrite an existing file.
- [ ] AC-8: Tests in test_cli_new.py pass.

## References

- [[PRD-505-darkfactory-verify-and-push]] — dependency (needs darkfactory to exist first)
- `tools/prd-harness/src/prd_harness/cli.py` — CLI location in pumice (becomes `src/darkfactory/cli.py` post-extraction)
