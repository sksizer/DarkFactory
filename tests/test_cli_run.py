"""Integration tests for `prd plan` and `prd run` CLI subcommands.

End-to-end tests that exercise the full argparse -> assign -> runner
chain against fixture PRD directories and workflow directories. The
actual agent invocation is mocked so tests don't spawn subprocesses.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from darkfactory.cli import _resolve_base_ref, main

from .conftest import write_prd


def _write_workflow_with_prompts(workflows_dir: Path, name: str = "default") -> None:
    """Create a minimal workflow with prompt files for end-to-end tests.

    The generated workflow's ``workflow.name`` matches the directory
    name, so callers can create multiple distinct workflows in the same
    directory without collision.
    """
    wf = workflows_dir / name
    (wf / "prompts").mkdir(parents=True)
    (wf / "prompts" / "role.md").write_text("# Role\n")
    (wf / "prompts" / "task.md").write_text("# Task\n{{PRD_ID}}\n")
    (wf / "prompts" / "verify.md").write_text("Fix:\n{{CHECK_OUTPUT}}\n")
    (wf / "workflow.py").write_text(
        f'''"""Fixture {name} workflow."""
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Workflow


def _applies(prd, prds):
    return True


workflow = Workflow(
    name="{name}",
    description="Test {name}",
    applies_to=_applies,
    priority=0,
    tasks=[
        BuiltIn("set_status", kwargs={{"to": "in-progress"}}),
        AgentTask(prompts=["prompts/role.md", "prompts/task.md"]),
        ShellTask("test", cmd="echo test"),
        BuiltIn("set_status", kwargs={{"to": "review"}}),
    ],
)
'''
    )


def _init_git_repo(path: Path) -> None:
    """Minimal git init so ``_find_repo_root`` can locate the tmp dir.

    The harness's CLI walks up from ``--prd-dir`` looking for ``.git``
    to use as the repo root; without this, plan/run commands raise
    ``SystemExit``. We use a bare `.git` directory rather than a full
    ``git init`` because none of the tests in this file actually need
    a functioning git repo — they mock subprocess calls where necessary.
    """
    (path / ".git").mkdir(exist_ok=True)


# ---------- plan ----------


def test_plan_shows_workflow_and_tasks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "my-task", capability="simple")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "plan",
            "PRD-070",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PRD-070" in out
    assert "default" in out
    assert "sonnet" in out  # simple capability -> sonnet
    # Task list rendered
    assert "set_status" in out
    assert "test" in out
    # Branch name
    assert "prd/PRD-070-my-task" in out


def test_plan_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task", capability="complex")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "--json",
            "plan",
            "PRD-070",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["prd"]["id"] == "PRD-070"
    assert payload["workflow"]["name"] == "default"
    assert payload["default_model"] == "opus"  # complex -> opus
    assert "tasks" in payload
    assert len(payload["tasks"]) == 4


def test_plan_flags_not_runnable_done_prd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "done-task", status="done")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "plan",
            "PRD-070",
        ]
    )
    out = capsys.readouterr().out
    assert "NOT RUNNABLE" in out
    assert "already done" in out


def test_plan_workflow_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--workflow pins an explicit workflow, bypassing assignment."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir, name="default")
    _write_workflow_with_prompts(workflows_dir, name="special")

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")

    main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "plan",
            "PRD-070",
            "--workflow",
            "special",
        ]
    )
    out = capsys.readouterr().out
    assert "special" in out


def test_plan_unknown_prd_errors(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "exists")

    with pytest.raises(SystemExit, match="unknown PRD"):
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(workflows_dir),
                "plan",
                "PRD-999",
            ]
        )


def test_plan_unknown_workflow_errors(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")

    with pytest.raises(SystemExit, match="unknown workflow"):
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(workflows_dir),
                "plan",
                "PRD-070",
                "--workflow",
                "nonexistent",
            ]
        )


# ---------- run (dry-run) ----------


def test_run_dry_run_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`prd run` without --execute is a dry-run and doesn't touch anything."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
            "PRD-070",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Dry-run" in out
    # All 4 tasks dispatched
    assert "set_status" in out
    assert "implement" in out
    assert "test" in out
    assert "✓ success" in out


def test_run_dry_run_no_subprocess(tmp_path: Path) -> None:
    """Dry-run shouldn't actually invoke subprocess at any point."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")

    with patch("subprocess.run") as mock_run:
        # Allow _resolve_base_ref to run git rev-parse (it's OK if it does)
        # but make it a no-op
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="main\n", stderr=""
        )
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(workflows_dir),
                "run",
                "PRD-070",
            ]
        )
        # _resolve_base_ref may have called it once; the dispatch loop
        # itself should not have.
        assert mock_run.call_count <= 1


# ---------- run (execute path, with runnability gate) ----------


def test_run_execute_refuses_done_prd(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "done", status="done")

    with pytest.raises(SystemExit, match="already done"):
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(workflows_dir),
                "run",
                "PRD-070",
                "--execute",
            ]
        )


def test_run_execute_refuses_draft_prd(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "draft", status="draft")

    with pytest.raises(SystemExit, match="not 'ready'"):
        main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(workflows_dir),
                "run",
                "PRD-070",
                "--execute",
            ]
        )


def test_run_execute_with_unfinished_deps_walks_graph(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PRD-220: running a PRD with unfinished deps now walks the DAG.

    Under the pre-PRD-220 regime this raised a "cannot run: unfinished
    dependencies" SystemExit. With graph execution, the CLI instead
    routes through :mod:`darkfactory.graph_execution`, which walks the
    unmet-dep closure. In this fixture the upstream dep has no real
    workflow plumbing so its run fails inside the sandbox runner — we
    assert on the graph-execution code path being entered (non-zero exit
    + "Executing graph" header), not on the specific failure reason.
    """
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "dep", status="ready")
    write_prd(
        prd_dir,
        "PRD-071",
        "target",
        status="ready",
        depends_on=["PRD-070"],
    )

    rc = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
            "PRD-071",
            "--execute",
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Executing graph" in captured.out
    assert "PRD-070" in captured.out


def test_run_execute_exits_nonzero_on_workflow_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the runner returns failure, `prd run --execute` exits 1."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    # Write a workflow that will fail in its shell task
    wf = workflows_dir / "default"
    (wf / "prompts").mkdir(parents=True)
    (wf / "prompts" / "task.md").write_text("# Task\n")
    (wf / "workflow.py").write_text(
        '''"""Failing fixture workflow."""
from darkfactory.workflow import ShellTask, Workflow

workflow = Workflow(
    name="default",
    applies_to=lambda prd, prds: True,
    priority=0,
    tasks=[ShellTask("fail", cmd="false", on_failure="fail")],
)
'''
    )

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task", status="ready")

    with patch("darkfactory.cli._resolve_base_ref", return_value="main"):
        exit_code = main(
            [
                "--prd-dir",
                str(prd_dir),
                "--workflows-dir",
                str(workflows_dir),
                "run",
                "PRD-070",
                "--execute",
            ]
        )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAILED" in out


# ---------- _resolve_base_ref unit tests ----------


def test_resolve_base_ref_explicit_wins(tmp_path: Path) -> None:
    """Explicit --base flag has highest priority."""
    _init_git_repo(tmp_path)
    result = _resolve_base_ref("custom-branch", tmp_path)
    assert result == "custom-branch"


def test_resolve_base_ref_env_var_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DARKFACTORY_BASE_REF environment variable is used when no explicit arg."""
    _init_git_repo(tmp_path)
    monkeypatch.setenv("DARKFACTORY_BASE_REF", "staging")
    result = _resolve_base_ref(None, tmp_path)
    assert result == "staging"


def test_resolve_base_ref_defaults_to_main(tmp_path: Path) -> None:
    """Defaults to 'main' when it exists locally."""
    _init_git_repo(tmp_path)

    # Mock subprocess to say main exists but master doesn't
    def mock_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "refs/heads/main" in str(cmd):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    with patch("darkfactory.cli.subprocess.run", side_effect=mock_run):
        result = _resolve_base_ref(None, tmp_path)
        assert result == "main"


def test_resolve_base_ref_falls_back_to_master(tmp_path: Path) -> None:
    """Falls back to 'master' when 'main' doesn't exist locally."""
    _init_git_repo(tmp_path)

    # Mock subprocess to say master exists but main doesn't
    def mock_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "refs/heads/master" in str(cmd):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    with patch("darkfactory.cli.subprocess.run", side_effect=mock_run):
        result = _resolve_base_ref(None, tmp_path)
        assert result == "master"


def test_resolve_base_ref_falls_back_to_origin_head(tmp_path: Path) -> None:
    """Falls back to origin/HEAD when neither main nor master exist locally."""
    _init_git_repo(tmp_path)

    # Mock subprocess to check refs fail, but symbolic-ref succeeds
    def mock_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "symbolic-ref" in str(cmd):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="refs/remotes/origin/develop\n",
                stderr="",
            )
        # All branch checks fail
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    with patch("darkfactory.cli.subprocess.run", side_effect=mock_run):
        result = _resolve_base_ref(None, tmp_path)
        assert result == "develop"


def test_resolve_base_ref_last_resort_main(tmp_path: Path) -> None:
    """Last resort fallback is 'main' when all else fails."""
    _init_git_repo(tmp_path)

    # Mock subprocess so all calls return failure
    def mock_run_all_fail(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        # For check=True calls (symbolic-ref), raise exception
        if "symbolic-ref" in str(cmd):
            raise subprocess.CalledProcessError(1, cmd)
        # For other calls, return failure status
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    with patch("darkfactory.cli.subprocess.run", side_effect=mock_run_all_fail):
        result = _resolve_base_ref(None, tmp_path)
        assert result == "main"


def test_resolve_base_ref_explicit_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit --base flag overrides environment variable."""
    _init_git_repo(tmp_path)
    monkeypatch.setenv("DARKFACTORY_BASE_REF", "staging")
    result = _resolve_base_ref("explicit-branch", tmp_path)
    assert result == "explicit-branch"


# ---------- run --all (queue mode) ----------


def test_run_all_mutual_exclusivity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-3: --all and a PRD ID are mutually exclusive."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
            "PRD-070",
            "--all",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "mutually exclusive" in err


def test_run_no_args_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """AC-4: `prd run` with no PRD ID and no --all exits with a clear message."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "PRD ID" in err or "--all" in err


def test_run_all_dry_run_shows_queue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-1: `prd run --all` in dry-run prints the ordered ready queue."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "first", priority="high")
    write_prd(prd_dir, "PRD-002", "second", priority="medium")
    write_prd(prd_dir, "PRD-003", "done-skip", status="done")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
            "--all",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "--all" in out or "queue" in out.lower()
    assert "PRD-001" in out
    assert "PRD-002" in out
    # Done PRDs should not appear in the queue
    assert "PRD-003" not in out


def test_run_all_dry_run_filters(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-5: --priority, --tag, and --exclude are passed through to the queue."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "high-pri", priority="high")
    write_prd(prd_dir, "PRD-002", "low-pri", priority="low")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
            "--all",
            "--priority",
            "high",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PRD-001" in out
    assert "PRD-002" not in out


def test_run_all_dry_run_exclude(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-5: --exclude filters out specific PRD IDs."""
    _init_git_repo(tmp_path)
    workflows_dir = tmp_path / "workflows"
    _write_workflow_with_prompts(workflows_dir)

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-001", "keep")
    write_prd(prd_dir, "PRD-002", "exclude-me")

    exit_code = main(
        [
            "--prd-dir",
            str(prd_dir),
            "--workflows-dir",
            str(workflows_dir),
            "run",
            "--all",
            "--exclude",
            "PRD-002",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PRD-001" in out
    assert "PRD-002" not in out
