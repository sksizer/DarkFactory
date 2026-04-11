"""Frontmatter read/write, file discovery, auto-migration, and archive logic."""

from __future__ import annotations

import re
import shutil
import sys
from collections import deque
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from darkfactory import __version__
from darkfactory.model._prd import (
    CANONICAL_SORTS,
    FRONTMATTER_RE,
    PRD,
    PRD_ID_RE,
    _yaml_item_repr,
    parse_wikilink,
    parse_wikilinks,
)
from darkfactory.timestamps import today_iso

CANONICAL_FIELD_ORDER: list[str] = [
    "id",
    "title",
    "kind",
    "status",
    "priority",
    "effort",
    "capability",
    "parent",
    "depends_on",
    "blocks",
    "impacts",
    "workflow",
    "assignee",
    "reviewers",
    "target_version",
    "created",
    "updated",
    "app_version",
    "tags",
]

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"done", "superseded", "cancelled", "archived"}
)

_YAML_KEYWORDS: frozenset[str] = frozenset(
    {
        "true",
        "false",
        "null",
        "yes",
        "no",
        "on",
        "off",
        "~",
        "True",
        "False",
        "Null",
        "Yes",
        "No",
        "On",
        "Off",
        "TRUE",
        "FALSE",
        "NULL",
        "YES",
        "NO",
        "ON",
        "OFF",
    }
)


def _needs_quoting(value: str) -> bool:
    """Return True if a YAML scalar value needs quoting."""
    if not value:
        return True
    if value in _YAML_KEYWORDS:
        return True
    if value[0] in "{[&*!|>%@`\"'#,?":
        return True
    if value[0].isdigit():
        return True
    if ": " in value or " #" in value:
        return True
    return False


def _format_scalar(value: object) -> str:
    """Format a single scalar value for YAML frontmatter."""
    if value is None:
        return "null"
    if isinstance(value, date) and not isinstance(value, str):
        return f"'{value.isoformat()}'"
    if isinstance(value, str):
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return f"'{value}'"
        if "[[" in value:
            return f'"{value}"'
        if _needs_quoting(value):
            return f'"{value}"'
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _serialize_frontmatter(fm: dict[str, Any]) -> str:
    """Deterministic frontmatter serializer with canonical field order."""
    lines: list[str] = []
    written: set[str] = set()

    for key in CANONICAL_FIELD_ORDER:
        if key not in fm:
            continue
        written.add(key)
        _serialize_field(lines, key, fm[key])

    for key in sorted(fm):
        if key in written:
            continue
        _serialize_field(lines, key, fm[key])

    return "\n".join(lines) + "\n"


def _serialize_field(lines: list[str], key: str, value: object) -> None:
    """Append serialized YAML lines for a single field."""
    if isinstance(value, list):
        if not value:
            lines.append(f"{key}: []")
        else:
            sort_fn = CANONICAL_SORTS.get(key)
            items = sorted(value, key=sort_fn) if sort_fn else list(value)
            lines.append(f"{key}:")
            for item in items:
                lines.append(f"  - {_format_scalar(item)}")
    else:
        lines.append(f"{key}: {_format_scalar(value)}")


# ---- Frontmatter parsing ---------------------------------------------------


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into ``(frontmatter dict, body string)``."""
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
    """Extract the slug portion of a PRD filename."""
    stem = path.stem
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
        target_version=(
            fm.get("target_version")
            if isinstance(fm.get("target_version"), str)
            else None
        ),
        created=fm.get("created", ""),
        updated=fm.get("updated", ""),
        tags=_coerce_list(fm.get("tags")),
        raw_frontmatter=fm,
        body=body,
    )


# ---- Discovery -------------------------------------------------------------


def load_all(data_dir: Path, *, include_archived: bool = False) -> dict[str, PRD]:
    """Load every PRD file in ``data_dir/prds/`` keyed by id.

    When ``include_archived=True``, also scans ``data_dir/archive/``.
    """
    prds: dict[str, PRD] = {}

    prds_dir = data_dir / "prds"
    if prds_dir.exists():
        _discover_prds(prds_dir, prds)

    if include_archived:
        archive_dir = data_dir / "archive"
        if archive_dir.exists():
            _discover_prds(archive_dir, prds)

    return prds


def _discover_prds(directory: Path, prds: dict[str, PRD]) -> None:
    """Scan a directory for PRD files and add them to ``prds``."""
    for path in sorted(directory.glob("PRD-*.md")):
        if path.name.startswith("_"):
            continue
        prd = parse_prd(path)
        if prd.id in prds:
            raise ValueError(
                f"duplicate PRD id {prd.id!r} in {path.name} "
                f"and {prds[prd.id].path.name}"
            )
        prds[prd.id] = prd


def load_one(data_dir: Path, prd_id: str, *, include_archived: bool = True) -> PRD:
    """Find and load a single PRD by ID.

    Searches ``prds/`` first, then ``archive/`` (when include_archived=True).
    Raises ``KeyError`` if not found.
    """
    prds_dir = data_dir / "prds"
    if prds_dir.exists():
        for path in sorted(prds_dir.glob(f"{prd_id}-*.md")):
            return parse_prd(path)

    if include_archived:
        archive_dir = data_dir / "archive"
        if archive_dir.exists():
            for path in sorted(archive_dir.glob(f"{prd_id}-*.md")):
                return parse_prd(path)

    raise KeyError(f"PRD not found: {prd_id}")


# ---- Write path -------------------------------------------------------------


def dump_frontmatter(fm: dict[str, Any]) -> str:
    """Serialize a frontmatter dict to deterministic YAML."""
    return _serialize_frontmatter(fm)


def save(prd: PRD) -> None:
    """Write PRD to ``prd.path`` using deterministic serialization.

    Stamps ``app_version`` and ``updated`` on every write.
    """
    fm = dict(prd.raw_frontmatter)
    fm["app_version"] = __version__
    fm["updated"] = today_iso()
    prd.updated = fm["updated"]

    text = f"---\n{_serialize_frontmatter(fm)}---\n{prd.body}"
    prd.path.write_text(text, encoding="utf-8")
    prd.raw_frontmatter = fm


def set_status(prd: PRD, new_status: str) -> None:
    """Update a PRD's status and save via deterministic serialization."""
    prd.status = new_status
    prd.raw_frontmatter = dict(prd.raw_frontmatter)
    prd.raw_frontmatter["status"] = new_status
    save(prd)


def set_status_at(path: Path, new_status: str) -> None:
    """Path-targeted variant — surgical line-editing, no ``app_version`` stamp.

    Used for worktree copies where writes are ephemeral.
    """
    today = today_iso()
    update_frontmatter_field_at(
        path,
        {"status": new_status, "updated": f"'{today}'"},
    )


def set_workflow(prd: PRD, workflow_name: str | None) -> None:
    """Update a PRD's ``workflow`` field and save via deterministic serialization."""
    prd.workflow = workflow_name
    prd.raw_frontmatter = dict(prd.raw_frontmatter)
    prd.raw_frontmatter["workflow"] = workflow_name
    save(prd)


# ---- Surgical editing (byte-preserving) ------------------------------------


def update_frontmatter_field_at(path: Path, updates: dict[str, str]) -> None:
    """Surgically rewrite specific frontmatter fields on disk.

    Only the lines matching ``^<field>:`` inside the leading ``---...---``
    block are replaced. Every other byte is preserved exactly.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

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


def normalize_list_field_at(
    path: Path, field: str, items: list[str], *, write: bool = True
) -> bool:
    """Sort ``items`` canonically and surgically rewrite the field's lines on disk."""
    if field not in CANONICAL_SORTS:
        raise ValueError(
            f"unknown list field {field!r}; known: {sorted(CANONICAL_SORTS)}"
        )

    sort_key = CANONICAL_SORTS[field]
    sorted_items = sorted(items, key=sort_key)

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{path}: no leading frontmatter block")
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"{path}: unterminated frontmatter block")

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

    if rest.startswith("[") and rest.rstrip() not in ("[]", "[ ]"):
        raise ValueError(
            f"{path}: field {field!r} uses flow-style list syntax; "
            "normalize_list_field_at only supports block-style lists"
        )

    item_start = field_line_idx + 1
    item_end = item_start
    if not rest.startswith("["):
        while item_end < end_idx and lines[item_end].lstrip().startswith("- "):
            item_end += 1

    if item_start < item_end:
        first = lines[item_start]
        item_indent = first[: len(first) - len(first.lstrip())]
    else:
        item_indent = f"{indent}  "

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


# ---- Write helpers (kept for backwards compat) ------------------------------


def write_frontmatter(prd: PRD, new_fm: dict[str, Any]) -> None:
    """Rewrite the frontmatter block of a PRD file in place."""
    new_text = f"---\n{dump_frontmatter(new_fm)}---\n{prd.body}"
    prd.path.write_text(new_text, encoding="utf-8")
    prd.raw_frontmatter = new_fm


# ---- Archive ----------------------------------------------------------------


def _check_archive_guardrails(
    prd: PRD, all_prds: dict[str, PRD]
) -> list[tuple[str, str]]:
    """BFS across all four axes to find non-terminal related PRDs."""
    children_of: dict[str, list[str]] = {}
    blocked_by: dict[str, list[str]] = {}

    for p in all_prds.values():
        if p.parent and p.parent in all_prds:
            children_of.setdefault(p.parent, []).append(p.id)
        for dep_id in p.depends_on:
            if dep_id in all_prds:
                blocked_by.setdefault(dep_id, []).append(p.id)

    visited: set[str] = set()
    queue: deque[str] = deque([prd.id])
    visited.add(prd.id)

    while queue:
        current_id = queue.popleft()
        current = all_prds.get(current_id)
        if current is None:
            continue

        if (
            current.parent
            and current.parent not in visited
            and current.parent in all_prds
        ):
            visited.add(current.parent)
            queue.append(current.parent)

        for child_id in children_of.get(current_id, []):
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)

        for dep_id in current.depends_on:
            if dep_id not in visited and dep_id in all_prds:
                visited.add(dep_id)
                queue.append(dep_id)

        for blocked_id in blocked_by.get(current_id, []):
            if blocked_id not in visited:
                visited.add(blocked_id)
                queue.append(blocked_id)

    blockers: list[tuple[str, str]] = []
    for pid in sorted(visited):
        if pid == prd.id:
            continue
        blocker = all_prds.get(pid)
        if blocker is not None and blocker.status not in TERMINAL_STATUSES:
            blockers.append((pid, blocker.status))
    return blockers


def archive(prd: PRD, data_dir: Path) -> PRD:
    """Move a terminal-state PRD to the archive directory.

    Guardrails: only PRDs in ``done``, ``superseded``, or ``cancelled``
    can be archived, and only when their full transitive dependency chain
    is also in a terminal state.
    """
    if prd.status not in ("done", "superseded", "cancelled"):
        raise ValueError(
            f"Cannot archive {prd.id}: status is {prd.status!r}, "
            f"must be done, superseded, or cancelled"
        )

    all_prds = load_all(data_dir, include_archived=True)
    blockers = _check_archive_guardrails(prd, all_prds)
    if blockers:
        lines = [f"Cannot archive {prd.id}: related PRDs are not in a terminal state:"]
        for pid, status in blockers:
            lines.append(f"  {pid}: {status}")
        raise ValueError("\n".join(lines))

    archive_dir = data_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / prd.path.name
    shutil.move(str(prd.path), str(dest))
    prd.path = dest
    prd.status = "archived"
    prd.raw_frontmatter = dict(prd.raw_frontmatter)
    prd.raw_frontmatter["status"] = "archived"
    save(prd)
    return prd


# ---- Auto-migration --------------------------------------------------------


def ensure_data_layout(darkfactory_dir: Path) -> None:
    """Detect legacy layout and migrate interactively.

    Legacy: ``.darkfactory/prds/`` exists, ``.darkfactory/data/prds/`` does not.
    New: ``.darkfactory/data/prds/`` and ``.darkfactory/data/archive/``.
    """
    legacy_prds = darkfactory_dir / "prds"
    new_data = darkfactory_dir / "data"
    new_prds = new_data / "prds"

    if not legacy_prds.exists() or new_prds.exists():
        return

    files = list(legacy_prds.iterdir())
    file_count = len(files)

    if not sys.stdin.isatty():
        print(
            f"Migration required: {file_count} file(s) in {legacy_prds} "
            f"need to move to {new_prds}.\n"
            f"Run `prd` interactively to complete the migration.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("DarkFactory data layout migration detected.")
    print(f"  {file_count} file(s) will move: {legacy_prds} -> {new_prds}")
    print(f"  New archive directory: {new_data / 'archive'}")
    response = input("Proceed? [y/N] ")
    if response.lower() not in ("y", "yes"):
        raise SystemExit("Migration cancelled.")

    new_data.mkdir(exist_ok=True)
    (new_data / "archive").mkdir(exist_ok=True)

    shutil.move(str(legacy_prds), str(new_prds))

    migrated = 0
    for path in sorted(new_prds.glob("PRD-*.md")):
        try:
            prd = parse_prd(path)
            prd.raw_frontmatter["app_version"] = __version__
            fm_text = _serialize_frontmatter(prd.raw_frontmatter)
            path.write_text(f"---\n{fm_text}---\n{prd.body}", encoding="utf-8")
            migrated += 1
        except Exception:  # noqa: BLE001
            pass

    print(
        f"Migration complete: {migrated} PRD(s) stamped with app_version {__version__}",
        file=sys.stderr,
    )
