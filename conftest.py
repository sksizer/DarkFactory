"""Project-wide pytest fixtures available to both tests/ and colocated unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_prd_dir(tmp_path: Path) -> Path:
    """An empty temporary directory for PRD fixtures."""
    return tmp_path


def write_prd(
    dir_path: Path,
    prd_id: str,
    slug: str,
    *,
    title: str = "Test PRD",
    kind: str = "task",
    status: str = "ready",
    priority: str = "medium",
    effort: str = "s",
    capability: str = "simple",
    parent: str | None = None,
    depends_on: list[str] | None = None,
    blocks: list[str] | None = None,
    impacts: list[str] | None = None,
    workflow: str | None = None,
    body: str = "# Test\n\nBody content.\n",
) -> Path:
    """Write a minimal valid PRD file to ``dir_path`` and return its path."""
    fm_lines = [
        "---",
        f'id: "{prd_id}"',
        f'title: "{title}"',
        f"kind: {kind}",
        f"status: {status}",
        f"priority: {priority}",
        f"effort: {effort}",
        f"capability: {capability}",
    ]
    if parent:
        fm_lines.append(f'parent: "[[{parent}-stub]]"')
    else:
        fm_lines.append("parent: null")

    if depends_on:
        fm_lines.append("depends_on:")
        for dep in depends_on:
            fm_lines.append(f'  - "[[{dep}-stub]]"')
    else:
        fm_lines.append("depends_on: []")

    if blocks:
        fm_lines.append("blocks:")
        for blk in blocks:
            fm_lines.append(f'  - "[[{blk}-stub]]"')
    else:
        fm_lines.append("blocks: []")

    if impacts:
        fm_lines.append("impacts:")
        for imp in impacts:
            fm_lines.append(f"  - {imp}")
    else:
        fm_lines.append("impacts: []")

    if workflow:
        fm_lines.append(f"workflow: {workflow}")
    else:
        fm_lines.append("workflow: null")

    fm_lines.append("created: 2026-04-06")
    fm_lines.append("updated: 2026-04-06")
    fm_lines.append("tags: []")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(body)

    path = dir_path / f"{prd_id}-{slug}.md"
    path.write_text("\n".join(fm_lines), encoding="utf-8")
    return path
