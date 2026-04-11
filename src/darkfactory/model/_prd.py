"""PRD dataclass and domain helpers (wikilink parsing, sort helpers, regex constants)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

PRD_ID_RE = re.compile(r"^PRD-\d+(?:\.\d+)*$")

WIKILINK_RE = re.compile(r"^\[\[(PRD-\d+(?:\.\d+)*)-[a-z0-9.-]+\]\]$")

WIKILINK_BODY_RE = re.compile(r"\[\[(PRD-\d+(?:\.\d+)*)-[a-z0-9.-]+\]\]")

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


def compute_branch_name(prd: PRD) -> str:
    """Return the git branch name for a PRD: ``prd/{id}-{slug}``."""
    return f"prd/{prd.id}-{prd.slug}"


def parse_id_sort_key(prd_id: str) -> tuple[int, ...]:
    """Return a natural-sort key for a PRD id.

    ``"PRD-4.2.1.3"`` -> ``(4, 2, 1, 3)``.
    """
    numeric = prd_id.removeprefix("PRD-")
    return tuple(int(part) for part in numeric.split("."))


def parse_wikilink(value: str | None) -> str | None:
    """Extract the bare PRD id from a wikilink string."""
    if not value:
        return None
    match = WIKILINK_RE.match(value.strip())
    if match:
        return match.group(1)
    return None


def parse_wikilinks(values: list[str] | None) -> list[str]:
    """Extract bare PRD ids from a list of wikilink strings."""
    if not values:
        return []
    out: list[str] = []
    for v in values:
        parsed = parse_wikilink(v)
        if parsed:
            out.append(parsed)
    return out


def _wikilink_sort_key(item: str) -> tuple[int, ...]:
    """Sort key for ``[[PRD-X-slug]]`` strings."""
    inner = item.strip("[]")
    prd_id = "-".join(inner.split("-", 2)[:2])
    return parse_id_sort_key(prd_id)


CANONICAL_SORTS: dict[str, Callable[[str], Any]] = {
    "tags": str.casefold,
    "impacts": lambda s: s,
    "depends_on": _wikilink_sort_key,
    "blocks": _wikilink_sort_key,
}

_WIKILINK_FIELDS: frozenset[str] = frozenset({"depends_on", "blocks"})


def _yaml_item_repr(field: str, value: str) -> str:
    """Return the YAML scalar representation for a list item value."""
    if field in _WIKILINK_FIELDS:
        return f'"{value}"'
    return value
