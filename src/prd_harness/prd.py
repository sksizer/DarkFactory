"""PRD dataclass, frontmatter parser, and round-trip writer.

A PRD file is a Markdown document with a YAML frontmatter block delimited by
``---`` lines. We parse the frontmatter into a typed ``PRD`` dataclass while
preserving the body byte-for-byte and the frontmatter key order on round-trip.

ID schemes
----------

The harness supports both the legacy flat ID format (``PRD-070``) and the
hierarchical format (``PRD-4.1.1``). The parser accepts both. Sorting uses a
natural-sort key that splits on ``.`` and compares each component as an integer,
so ``PRD-1.2`` sorts before ``PRD-1.10``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Regex for matching either flat (PRD-070) or hierarchical (PRD-4.1.1) IDs.
PRD_ID_RE = re.compile(r"^PRD-\d+(?:\.\d+)*$")

# Regex for extracting an ID out of a wikilink: ``[[PRD-NNN-slug]]``.
WIKILINK_RE = re.compile(r"^\[\[(PRD-\d+(?:\.\d+)*)-[a-z0-9.-]+\]\]$")

# Regex for finding wikilinks anywhere in body text (non-anchored).
WIKILINK_BODY_RE = re.compile(r"\[\[(PRD-\d+(?:\.\d+)*)-[a-z0-9.-]+\]\]")

# Regex for the frontmatter block at the start of a file.
FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n(.*)\Z", re.DOTALL)


@dataclass
class PRD:
    """A parsed PRD file with typed frontmatter access."""

    id: str
    path: Path
    slug: str
    title: str
    kind: str
    status: str
    priority: str
    effort: str
    capability: str
    parent: str | None
    depends_on: list[str]
    blocks: list[str]
    impacts: list[str]
    workflow: str | None
    assignee: str | None
    reviewers: list[str]
    target_version: str | None
    created: date | str
    updated: date | str
    tags: list[str]
    raw_frontmatter: dict[str, Any]
    body: str


def parse_id_sort_key(prd_id: str) -> tuple[int, ...]:
    """Return a natural-sort key for a PRD id.

    ``"PRD-4.2.1.3"`` -> ``(4, 2, 1, 3)``. Used wherever the harness sorts PRDs
    so that ``PRD-1.2`` orders before ``PRD-1.10``.
    """
    numeric = prd_id.removeprefix("PRD-")
    return tuple(int(part) for part in numeric.split("."))


def parse_wikilink(value: str | None) -> str | None:
    """Extract the bare PRD id from a wikilink string.

    Returns ``None`` if ``value`` is falsy or doesn't match the expected
    ``[[PRD-NNN-slug]]`` shape. The id portion may be either flat
    (``PRD-070``) or hierarchical (``PRD-4.1.1``).
    """
    if not value:
        return None
    match = WIKILINK_RE.match(value.strip())
    if match:
        return match.group(1)
    return None


def parse_wikilinks(values: list[str] | None) -> list[str]:
    """Extract bare PRD ids from a list of wikilink strings.

    Skips any entries that don't match the wikilink shape (rather than failing
    loudly). The set of skipped entries is recoverable via ``validate``.
    """
    if not values:
        return []
    out: list[str] = []
    for v in values:
        parsed = parse_wikilink(v)
        if parsed:
            out.append(parsed)
    return out


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into ``(frontmatter dict, body string)``.

    Raises ``ValueError`` if no leading ``---`` block is present.
    """
    match = FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError("file does not start with a YAML frontmatter block")
    fm_text, body = match.group(1), match.group(2)
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter is not a mapping: {type(fm).__name__}")
    return fm, body


def _coerce_list(value: Any) -> list[str]:
    """Normalize a possibly-None YAML list field into a ``list[str]``."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _slug_from_filename(path: Path) -> str:
    """Extract the slug portion of a PRD filename: ``PRD-070-foo-bar.md`` -> ``foo-bar``."""
    stem = path.stem  # "PRD-070-foo-bar"
    # Drop the leading "PRD-{id}-" prefix; the id may contain dots.
    match = re.match(r"^(PRD-\d+(?:\.\d+)*)-(.+)$", stem)
    if not match:
        return stem
    return match.group(2)


def parse_prd(path: Path) -> PRD:
    """Parse a single PRD file from disk."""
    content = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(content)

    prd_id = str(fm.get("id", "")).strip()
    if not PRD_ID_RE.match(prd_id):
        raise ValueError(f"{path.name}: invalid id {prd_id!r}")

    return PRD(
        id=prd_id,
        path=path,
        slug=_slug_from_filename(path),
        title=str(fm.get("title", "")),
        kind=str(fm.get("kind", "")),
        status=str(fm.get("status", "")),
        priority=str(fm.get("priority", "")),
        effort=str(fm.get("effort", "m")),
        capability=str(fm.get("capability", "moderate")),
        parent=parse_wikilink(fm.get("parent")),
        depends_on=parse_wikilinks(_coerce_list(fm.get("depends_on"))),
        blocks=parse_wikilinks(_coerce_list(fm.get("blocks"))),
        impacts=_coerce_list(fm.get("impacts")),
        workflow=fm.get("workflow") if isinstance(fm.get("workflow"), str) else None,
        assignee=fm.get("assignee") if isinstance(fm.get("assignee"), str) else None,
        reviewers=_coerce_list(fm.get("reviewers")),
        target_version=fm.get("target_version") if isinstance(fm.get("target_version"), str) else None,
        created=fm.get("created", ""),
        updated=fm.get("updated", ""),
        tags=_coerce_list(fm.get("tags")),
        raw_frontmatter=fm,
        body=body,
    )


def load_all(prd_dir: Path) -> dict[str, PRD]:
    """Load every PRD file in ``prd_dir`` keyed by id.

    Skips ``_template.md`` and any non-PRD files. Raises ``ValueError`` on
    duplicate ids or unparseable files.
    """
    prds: dict[str, PRD] = {}
    for path in sorted(prd_dir.glob("PRD-*.md")):
        if path.name.startswith("_"):
            continue
        prd = parse_prd(path)
        if prd.id in prds:
            raise ValueError(f"duplicate PRD id {prd.id!r} in {path.name} and {prds[prd.id].path.name}")
        prds[prd.id] = prd
    return prds


def dump_frontmatter(fm: dict[str, Any]) -> str:
    """Serialize a frontmatter dict back to YAML preserving key order.

    Uses ``sort_keys=False`` and a custom representer for ``None`` so that
    ``parent: null`` round-trips cleanly.
    """
    return yaml.safe_dump(
        fm,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def write_frontmatter(prd: PRD, new_fm: dict[str, Any]) -> None:
    """Rewrite the frontmatter block of a PRD file in place.

    The body is preserved byte-for-byte. Updates ``prd.raw_frontmatter`` to
    reflect the written state.
    """
    new_text = f"---\n{dump_frontmatter(new_fm)}---\n{prd.body}"
    prd.path.write_text(new_text, encoding="utf-8")
    prd.raw_frontmatter = new_fm


def set_status(prd: PRD, new_status: str) -> None:
    """Update a PRD's status (and bump ``updated`` to today) in place."""
    fm = dict(prd.raw_frontmatter)  # shallow copy preserves key order in 3.7+
    fm["status"] = new_status
    fm["updated"] = date.today().isoformat()
    write_frontmatter(prd, fm)
    prd.status = new_status
    prd.updated = fm["updated"]
