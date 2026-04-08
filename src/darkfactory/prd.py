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
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

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
        target_version=fm.get("target_version")
        if isinstance(fm.get("target_version"), str)
        else None,
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
            raise ValueError(
                f"duplicate PRD id {prd.id!r} in {path.name} and {prds[prd.id].path.name}"
            )
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

    NOTE: this re-serializes the entire frontmatter block, which means
    PyYAML's quoting style replaces whatever the author wrote (``"PRD-501"``
    becomes ``PRD-501``, etc.). For single-field updates that should leave
    every other field byte-for-byte identical, prefer
    :func:`update_frontmatter_field`.
    """
    new_text = f"---\n{dump_frontmatter(new_fm)}---\n{prd.body}"
    prd.path.write_text(new_text, encoding="utf-8")
    prd.raw_frontmatter = new_fm


def update_frontmatter_field_at(path: Path, updates: dict[str, str]) -> None:
    """Surgically rewrite specific frontmatter fields on disk.

    Only the lines matching ``^<field>:`` (where ``<field>`` is a key in
    ``updates``) inside the leading ``---...---`` block are replaced. Every
    other byte in the file — including quoting style on other fields, key
    order, blank lines, and the body — is preserved exactly.

    This is the byte-for-byte preservation contract documented in the
    harness design plan. Use it for any operation that mutates a known,
    existing scalar field (status, updated, workflow). For operations that
    add or remove fields, fall back to :func:`write_frontmatter`.

    Limitations:

    - Only works for fields whose value lives entirely on the line after
      the colon. Multi-line values (block scalars, nested mappings) are
      not handled.
    - The field must already exist in the frontmatter. To add a new field,
      use the full re-serialization path.
    - The new value is written verbatim — the caller is responsible for
      quoting it correctly if it needs quoting.

    Raises ``ValueError`` if the file has no leading frontmatter block, or
    if any field in ``updates`` is not present in the frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Locate the closing --- of the frontmatter block.
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{path}: no leading frontmatter block")
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"{path}: unterminated frontmatter block")

    remaining = set(updates)
    for i in range(1, end_idx):
        line = lines[i]
        for field in list(remaining):
            prefix = f"{field}:"
            if line.lstrip().startswith(prefix):
                # Preserve any leading indentation (rare in our PRDs but cheap to keep).
                indent = line[: len(line) - len(line.lstrip())]
                eol = "\r\n" if line.endswith("\r\n") else "\n"
                lines[i] = f"{indent}{field}: {updates[field]}{eol}"
                remaining.discard(field)
                break

    if remaining:
        raise ValueError(
            f"{path}: cannot update missing frontmatter field(s): {sorted(remaining)}"
        )

    path.write_text("".join(lines), encoding="utf-8")


def set_status(prd: PRD, new_status: str) -> None:
    """Update a PRD's status (and bump ``updated`` to today) in place.

    Uses surgical line-editing to preserve every other frontmatter field
    byte-for-byte. Mutates the file at ``prd.path`` — callers that need to
    target a copy of the file at a different path (e.g. inside a worktree)
    should use :func:`set_status_at` directly.
    """
    set_status_at(prd.path, new_status)
    prd.raw_frontmatter = dict(prd.raw_frontmatter)
    prd.raw_frontmatter["status"] = new_status
    prd.raw_frontmatter["updated"] = date.today().isoformat()
    prd.status = new_status
    prd.updated = prd.raw_frontmatter["updated"]


def set_status_at(path: Path, new_status: str) -> None:
    """Path-targeted variant of :func:`set_status`.

    Updates the ``status:`` and ``updated:`` fields in the frontmatter at
    ``path`` without touching any other field. This decoupling lets the
    harness builtin write to the worktree copy of a PRD while leaving the
    source repo's working tree clean (see PRD-213).
    """
    # Quote the date so PyYAML round-trips it as a string instead of
    # auto-coercing to a ``datetime.date`` object on the next parse.
    today = date.today().isoformat()
    update_frontmatter_field_at(
        path,
        {"status": new_status, "updated": f"'{today}'"},
    )


def _wikilink_sort_key(item: str) -> tuple[int, ...]:
    """Sort key for ``[[PRD-X-slug]]`` strings — extracts the ID and applies natural sort.

    Handles both quoted (``"[[PRD-NNN-slug]]"``) and unquoted (``[[PRD-NNN-slug]]``) forms.
    """
    inner = item.strip("[]")
    prd_id = "-".join(inner.split("-", 2)[:2])  # ["PRD", "4.2.1"]
    return parse_id_sort_key(prd_id)


#: Canonical sort key for each known list field.
CANONICAL_SORTS: dict[str, Callable[[str], Any]] = {
    "tags": str.casefold,
    "impacts": lambda s: s,
    "depends_on": _wikilink_sort_key,
    "blocks": _wikilink_sort_key,
}

#: Fields whose items need YAML double-quoting (they contain ``[`` which is special).
_WIKILINK_FIELDS: frozenset[str] = frozenset({"depends_on", "blocks"})


def _yaml_item_repr(field: str, value: str) -> str:
    """Return the YAML scalar representation for a list item value.

    Wikilink fields use double-quoting because ``[`` is a special character in YAML.
    Other fields (tags, impacts) are written unquoted.
    """
    if field in _WIKILINK_FIELDS:
        return f'"{value}"'
    return value


def normalize_list_field_at(
    path: Path, field: str, items: list[str], *, write: bool = True
) -> bool:
    """Sort ``items`` canonically and surgically rewrite the field's lines on disk.

    Only the YAML list lines for ``field`` are replaced — every other byte in the
    file (other frontmatter fields, their quoting style, key order, blank lines,
    and the body) is preserved exactly. This is the same byte-preservation
    invariant as :func:`update_frontmatter_field_at`.

    Parameters
    ----------
    path:
        Path to the PRD file.
    field:
        Name of the list field to normalize (must be a key in :data:`CANONICAL_SORTS`).
    items:
        The list of values to sort and write.  For ``depends_on`` / ``blocks``
        these are the raw wikilink strings (e.g. ``"[[PRD-214-frontmatter-roundtrip-drift]]"``
        as returned by PyYAML — without outer YAML quoting).  For ``tags`` /
        ``impacts`` they are plain strings.
    write:
        If ``False``, compute and return whether the file *would* change without
        writing to disk.  Defaults to ``True``.

    Returns
    -------
    bool
        ``True`` if the file was changed (or would be changed when ``write=False``),
        ``False`` if it was already canonical.

    Raises
    ------
    ValueError
        If ``field`` is not a known list field, the file has no frontmatter, the
        field is absent from the frontmatter, or the field uses flow-style list
        syntax (``[a, b]``) with non-empty content.
    """
    if field not in CANONICAL_SORTS:
        raise ValueError(
            f"unknown list field {field!r}; known: {sorted(CANONICAL_SORTS)}"
        )

    sort_key = CANONICAL_SORTS[field]
    sorted_items = sorted(items, key=sort_key)

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Locate frontmatter boundaries.
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{path}: no leading frontmatter block")
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"{path}: unterminated frontmatter block")

    # Find the field header line inside the frontmatter block.
    field_line_idx: int | None = None
    for i in range(1, end_idx):
        if lines[i].lstrip().startswith(f"{field}:"):
            field_line_idx = i
            break
    if field_line_idx is None:
        raise ValueError(f"{path}: field {field!r} not found in frontmatter")

    field_line = lines[field_line_idx]
    indent = field_line[: len(field_line) - len(field_line.lstrip())]
    eol = "\r\n" if field_line.endswith("\r\n") else "\n"
    rest = field_line.lstrip()[len(f"{field}:") :].strip()

    # Detect non-empty flow-style list: ``field: [a, b]``.
    if rest.startswith("[") and rest.rstrip() not in ("[]", "[ ]"):
        raise ValueError(
            f"{path}: field {field!r} uses flow-style list syntax; "
            "normalize_list_field_at only supports block-style lists"
        )

    # Collect existing block-style item lines (``  - value``).
    item_start = field_line_idx + 1
    item_end = item_start
    if not rest.startswith("["):
        while item_end < end_idx and lines[item_end].lstrip().startswith("- "):
            item_end += 1

    # Determine item indentation (preserve existing or default to two spaces).
    if item_start < item_end:
        first = lines[item_start]
        item_indent = first[: len(first) - len(first.lstrip())]
    else:
        item_indent = f"{indent}  "

    # Build replacement lines.
    if not sorted_items:
        new_header = f"{indent}{field}: []{eol}"
        new_item_lines: list[str] = []
    else:
        new_header = f"{indent}{field}:{eol}"
        new_item_lines = [
            f"{item_indent}- {_yaml_item_repr(field, item)}{eol}"
            for item in sorted_items
        ]

    new_lines = (
        lines[:field_line_idx] + [new_header] + new_item_lines + lines[item_end:]
    )
    new_text = "".join(new_lines)

    if new_text == text:
        return False
    if write:
        path.write_text(new_text, encoding="utf-8")
    return True


def set_workflow(prd: PRD, workflow_name: str | None) -> None:
    """Update a PRD's ``workflow`` frontmatter field in place.

    Used by the ``prd assign --write`` CLI command to persist resolved
    workflow assignments. Also bumps ``updated`` to today so tooling
    that tracks "recently modified" picks it up.

    Passing ``None`` clears the field (resets to predicate-based
    routing). Passing a name pins that workflow explicitly.
    """
    fm = dict(prd.raw_frontmatter)
    fm["workflow"] = workflow_name
    fm["updated"] = date.today().isoformat()
    write_frontmatter(prd, fm)
    prd.workflow = workflow_name
    prd.updated = fm["updated"]
