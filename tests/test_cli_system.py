"""Integration tests for the ``prd system`` CLI subcommand group.

Exercises the full argparse -> load_operations -> run_system_operation chain
against fixture operations directories. Agent invocations are mocked so tests
don't spawn subprocesses.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from darkfactory.cli import main


# ---------- fixtures ----------


def _init_git_repo(path: Path) -> None:
    """Minimal git init so ``_find_repo_root`` can locate the tmp dir."""
    (path / ".git").mkdir(exist_ok=True)


def _write_operation(
    ops_dir: Path,
    name: str,
    *,
    description: str = "A fixture operation",
    creates_pr: bool = False,
    requires_clean_main: bool = True,
    accepts_target: bool = False,
    tasks_code: str = "tasks=[BuiltIn('_noop')]",
) -> Path:
    """Create a minimal operation.py under ``ops_dir/<name>/``."""
    op_dir = ops_dir / name
    op_dir.mkdir(parents=True, exist_ok=True)
    op_file = op_dir / "operation.py"
    op_file.write_text(
        f'''"""Fixture operation {name}."""
from darkfactory.system import SystemOperation
from darkfactory.workflow import BuiltIn

operation = SystemOperation(
    name={name!r},
    description={description!r},
    {tasks_code},
    creates_pr={creates_pr!r},
    requires_clean_main={requires_clean_main!r},
    accepts_target={accepts_target!r},
)
'''
    )
    return op_file


def _base_args(
    prd_dir: Path,
    ops_dir: Path,
    workflows_dir: Path | None = None,
) -> list[str]:
    """Build the common CLI prefix for system subcommand tests."""
    wf_dir = str(workflows_dir) if workflows_dir else str(prd_dir.parent / "workflows")
    return [
        "--prd-dir",
        str(prd_dir),
        "--workflows-dir",
        wf_dir,
        "--operations-dir",
        str(ops_dir),
        "system",
    ]


# ---------- prd system list ----------


def test_system_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    ops_dir.mkdir()

    exit_code = main(_base_args(prd_dir, ops_dir) + ["list"])
    assert exit_code == 0
    assert "no system operations" in capsys.readouterr().out


def test_system_list_shows_operations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    _write_operation(ops_dir, "audit", description="Audit the repo state")
    _write_operation(ops_dir, "reconcile", description="Reconcile PRD statuses")

    exit_code = main(_base_args(prd_dir, ops_dir) + ["list"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "audit" in out
    assert "Audit the repo state" in out
    assert "reconcile" in out
    assert "Reconcile PRD statuses" in out


def test_system_list_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    _write_operation(ops_dir, "audit", description="Audit the repo state")

    args = [
        "--prd-dir",
        str(prd_dir),
        "--workflows-dir",
        str(prd_dir.parent / "wf"),
        "--operations-dir",
        str(ops_dir),
        "--json",
        "system",
        "list",
    ]
    exit_code = main(args)
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["name"] == "audit"
    assert payload[0]["description"] == "Audit the repo state"


# ---------- prd system describe ----------


def test_system_describe_known_operation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    _write_operation(
        ops_dir,
        "reconcile-status",
        description="Reconcile PRD statuses",
        creates_pr=True,
    )

    exit_code = main(_base_args(prd_dir, ops_dir) + ["describe", "reconcile-status"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "reconcile-status" in out
    assert "Reconcile PRD statuses" in out
    assert "creates_pr" in out
    assert "requires_clean_main" in out
    assert "accepts_target" in out


def test_system_describe_unknown_operation(tmp_path: Path) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    ops_dir.mkdir()

    with pytest.raises(SystemExit) as exc:
        main(_base_args(prd_dir, ops_dir) + ["describe", "nonexistent"])
    assert exc.value.code != 0


def test_system_describe_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    _write_operation(
        ops_dir,
        "audit",
        description="Audit",
        accepts_target=True,
    )

    args = [
        "--prd-dir",
        str(prd_dir),
        "--workflows-dir",
        str(prd_dir.parent / "wf"),
        "--operations-dir",
        str(ops_dir),
        "--json",
        "system",
        "describe",
        "audit",
    ]
    exit_code = main(args)
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "audit"
    assert payload["accepts_target"] is True
    assert "tasks" in payload


# ---------- prd system run (dry-run) ----------


def test_system_run_dry_run_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd system run defaults to dry-run and prints report output."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    _write_operation(
        ops_dir,
        "audit",
        tasks_code="tasks=[ShellTask('check', cmd='echo hello')]",
    )
    # Patch the operation.py to use ShellTask
    (ops_dir / "audit" / "operation.py").write_text(
        '''"""Fixture audit operation."""
from darkfactory.system import SystemOperation
from darkfactory.workflow import ShellTask

operation = SystemOperation(
    name="audit",
    description="Audit the repo",
    tasks=[ShellTask("check", cmd="echo hello")],
)
'''
    )

    exit_code = main(_base_args(prd_dir, ops_dir) + ["run", "audit"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Dry-run" in out
    assert "audit" in out
    assert "shell" in out
    assert "dry-run" in out


def test_system_run_execute_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """prd system run --execute dispatches with dry_run=False."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    (ops_dir / "audit").mkdir(parents=True)
    (ops_dir / "audit" / "operation.py").write_text(
        '''"""Fixture audit operation."""
from darkfactory.system import SystemOperation
from darkfactory.workflow import ShellTask

operation = SystemOperation(
    name="audit",
    description="Audit the repo",
    tasks=[ShellTask("check", cmd="true")],
    requires_clean_main=False,
)
'''
    )

    # Patch filelock so lock acquisition doesn't fail in tmp env
    with patch("filelock.FileLock") as mock_lock_cls:
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        exit_code = main(_base_args(prd_dir, ops_dir) + ["run", "audit", "--execute"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Executing" in out
    assert "audit" in out


def test_system_run_builtin_failure_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failing task causes exit code 1."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    (ops_dir / "bad-op").mkdir(parents=True)
    (ops_dir / "bad-op" / "operation.py").write_text(
        '''"""Fixture bad operation."""
from darkfactory.system import SystemOperation
from darkfactory.workflow import ShellTask

operation = SystemOperation(
    name="bad-op",
    description="Always fails",
    tasks=[ShellTask("fail", cmd="false")],
    requires_clean_main=False,
)
'''
    )

    with patch("filelock.FileLock") as mock_lock_cls:
        mock_lock = MagicMock()
        mock_lock_cls.return_value = mock_lock
        exit_code = main(_base_args(prd_dir, ops_dir) + ["run", "bad-op", "--execute"])

    assert exit_code == 1


# ---------- AC-5: --target rejected when accepts_target=False ----------


def test_system_run_target_rejected(tmp_path: Path) -> None:
    """--target is rejected for operations with accepts_target=False."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    _write_operation(ops_dir, "audit", accepts_target=False)

    with pytest.raises(SystemExit) as exc:
        main(_base_args(prd_dir, ops_dir) + ["run", "audit", "--target", "PRD-001"])
    assert exc.value.code != 0


def test_system_run_target_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--target is allowed for operations with accepts_target=True."""
    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    (ops_dir / "plan-op").mkdir(parents=True)
    (ops_dir / "plan-op" / "operation.py").write_text(
        '''"""Fixture plan operation."""
from darkfactory.system import SystemOperation

operation = SystemOperation(
    name="plan-op",
    description="Plans something",
    tasks=[],
    accepts_target=True,
)
'''
    )

    exit_code = main(
        _base_args(prd_dir, ops_dir) + ["run", "plan-op", "--target", "PRD-001"]
    )
    assert exit_code == 0


# ---------- report and targets output ----------


def test_system_run_report_displayed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report lines accumulated by builtins are displayed after the run."""
    from darkfactory.system_runner import SYSTEM_BUILTINS
    from darkfactory.system import SystemContext

    _init_git_repo(tmp_path)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    ops_dir = tmp_path / "operations"
    (ops_dir / "reporter").mkdir(parents=True)
    (ops_dir / "reporter" / "operation.py").write_text(
        '''"""Fixture reporter operation."""
from darkfactory.system import SystemOperation
from darkfactory.workflow import BuiltIn

operation = SystemOperation(
    name="reporter",
    description="Adds to report",
    tasks=[BuiltIn("_test_report_builtin")],
)
'''
    )

    def report_builtin(ctx: SystemContext, **kwargs: object) -> None:
        ctx.report.append("found 3 items")

    SYSTEM_BUILTINS["_test_report_builtin"] = report_builtin
    try:
        exit_code = main(_base_args(prd_dir, ops_dir) + ["run", "reporter"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "found 3 items" in out
    finally:
        SYSTEM_BUILTINS.pop("_test_report_builtin", None)
