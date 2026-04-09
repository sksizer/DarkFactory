"""Integration-test fixtures and helpers for the tests/ suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_builtin_workflows(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Point ``DARKFACTORY_BUILTINS_DIR`` at an empty dir by default.

    Most tests create fixture workflows in a tmp dir and don't expect
    the real bundled system workflows (``default``, ``extraction``,
    ``planning``) to appear alongside them — that would produce name
    collisions and spurious entries. A test that *does* want the real
    built-ins should request the ``real_builtin_workflows`` fixture,
    which removes this override.
    """
    if "real_builtin_workflows" in request.fixturenames:
        return
    empty = tmp_path_factory.mktemp("empty-builtins")
    monkeypatch.setenv("DARKFACTORY_BUILTINS_DIR", str(empty))


@pytest.fixture
def real_builtin_workflows() -> None:
    """Opt out of the default built-in isolation (see autouse fixture)."""
    return None


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
