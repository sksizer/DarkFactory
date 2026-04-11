"""Project-wide pytest fixtures available to both tests/ and colocated unit tests."""

from __future__ import annotations

import subprocess as sp
from pathlib import Path

import pytest

from darkfactory.model import PRD
from darkfactory.system import SystemContext, SystemOperation


def init_git_repo(path: Path) -> None:
    """Initialize a git repo with dummy user config for testing."""
    sp.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    sp.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )
    sp.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """A temporary data directory with prds/ and archive/ subdirectories."""
    (tmp_path / "prds").mkdir()
    (tmp_path / "archive").mkdir()
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


def make_system_op(
    name: str = "test-op",
    description: str = "test",
    operation_dir: Path | None = None,
) -> SystemOperation:
    """Create a SystemOperation for testing."""
    return SystemOperation(
        name=name,
        description=description,
        tasks=[],
        operation_dir=operation_dir,
    )


def make_system_ctx(
    tmp_path: Path,
    prds: dict[str, PRD] | None = None,
    target_prd: str | None = None,
    operation: SystemOperation | None = None,
) -> SystemContext:
    """Create a SystemContext for testing."""
    return SystemContext(
        repo_root=tmp_path,
        prds=prds or {},
        operation=operation or make_system_op(),
        cwd=tmp_path,
        dry_run=False,
        target_prd=target_prd,
    )


def setup_repo_with_prd(tmp_path: Path) -> tuple[Path, dict[str, PRD]]:
    """Create git repo, write a PRD, commit it, load PRDs, then dirty the file."""
    from darkfactory.model import load_all

    init_git_repo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    (data_dir / "archive").mkdir()
    prd_path = write_prd(prds_dir, "PRD-070", "test-prd")

    prds = load_all(data_dir)

    sp.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    sp.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    content = prd_path.read_text(encoding="utf-8")
    prd_path.write_text(content + "\n<!-- modified -->\n", encoding="utf-8")

    return prd_path, prds
