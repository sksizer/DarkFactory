"""Integration-test fixtures and helpers for the tests/ suite."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple
from unittest.mock import MagicMock

import pytest

from conftest import write_prd as write_prd  # noqa: F401
from darkfactory.prd import PRD, load_all
from darkfactory.workflow import Workflow


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


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Return ``tmp_path`` after creating a minimal ``.git/`` directory.

    Allows ``_find_repo_root`` and similar git-root discovery helpers to
    resolve successfully without a real git repository.
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    return tmp_path


class CliProject(NamedTuple):
    """Paths for a minimal project layout used in CLI integration tests."""

    repo_root: Path
    prd_dir: Path
    workflows_dir: Path


@pytest.fixture
def cli_project(tmp_path: Path) -> CliProject:
    """Create a minimal project directory structure and return its paths.

    - ``repo_root`` — ``tmp_path`` with ``.git/`` created
    - ``prd_dir`` — ``tmp_path / "prds"`` (created)
    - ``workflows_dir`` — ``tmp_path / "workflows"`` (created)
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    return CliProject(
        repo_root=tmp_path,
        prd_dir=prd_dir,
        workflows_dir=workflows_dir,
    )


@pytest.fixture
def make_prd(tmp_path: Path) -> Callable[..., PRD]:
    """Return a factory that writes and loads a single PRD.

    The factory signature::

        make_prd(
            prd_id: str,
            slug: str,
            *,
            capability: str = "simple",
            kind: str = "task",
            status: str = "ready",
            priority: str = "medium",
            effort: str = "s",
            parent: str | None = None,
            depends_on: list[str] | None = None,
        ) -> PRD
    """
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir(exist_ok=True)

    def _factory(
        prd_id: str,
        slug: str,
        *,
        capability: str = "simple",
        kind: str = "task",
        status: str = "ready",
        priority: str = "medium",
        effort: str = "s",
        parent: str | None = None,
        depends_on: list[str] | None = None,
    ) -> PRD:
        write_prd(
            prd_dir,
            prd_id,
            slug,
            capability=capability,
            kind=kind,
            status=status,
            priority=priority,
            effort=effort,
            parent=parent,
            depends_on=depends_on,
        )
        prds = load_all(prd_dir)
        return prds[prd_id]

    return _factory


@pytest.fixture
def make_workflow(tmp_path: Path) -> Callable[..., Workflow]:
    """Return a factory that creates a ``Workflow`` instance in a temp dir.

    The factory signature::

        make_workflow(name: str = "test", *, with_prompts: bool = True) -> Workflow
    """

    def _factory(name: str = "test", *, with_prompts: bool = True) -> Workflow:
        wf_dir = tmp_path / "wf" / name
        wf_dir.mkdir(parents=True, exist_ok=True)
        if with_prompts:
            prompts_dir = wf_dir / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "role.md").write_text("# Role\n")
            (prompts_dir / "task.md").write_text("# Task\n{{PRD_ID}}\n")
            (prompts_dir / "verify.md").write_text("# Verify\nFix:\n{{CHECK_OUTPUT}}\n")
        return Workflow(
            name=name,
            applies_to=lambda prd, prds: True,
            tasks=[],
            workflow_dir=wf_dir if with_prompts else None,
        )

    return _factory


@pytest.fixture
def make_execution_context() -> Callable[..., MagicMock]:
    """Return a factory that creates a mock ``ExecutionContext``.

    The returned factory creates a ``MagicMock`` pre-populated with the
    fields most commonly accessed in workflow and builtin tests::

        make_execution_context(
            *,
            prd_id: str = "PRD-001",
            dry_run: bool = False,
            branch_name: str = "prd/PRD-001-stub",
            base_ref: str = "main",
            cwd: Path | None = None,
            repo_root: Path | None = None,
            worktree_path: Path | None = None,
        ) -> MagicMock
    """

    def _factory(
        *,
        prd_id: str = "PRD-001",
        dry_run: bool = False,
        branch_name: str = "prd/PRD-001-stub",
        base_ref: str = "main",
        cwd: Path | None = None,
        repo_root: Path | None = None,
        worktree_path: Path | None = None,
    ) -> MagicMock:
        ctx = MagicMock()
        ctx.dry_run = dry_run
        ctx.prd.id = prd_id
        ctx.branch_name = branch_name
        ctx.base_ref = base_ref
        ctx.cwd = cwd
        ctx.repo_root = repo_root
        ctx.worktree_path = worktree_path
        ctx.format_string.side_effect = lambda s: s
        return ctx

    return _factory
