"""Tests for runner.run_project_operation and its dispatch helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from darkfactory.engine import CodeEnv, PrResult, ProjectRun
from darkfactory.operations.project_builtins import SYSTEM_BUILTINS
from darkfactory.runner import run_project_operation
from darkfactory.workflow import AgentTask, BuiltIn, RunContext, ShellTask, Workflow


# ---------- helpers ----------


def _make_operation(
    tasks: list[object],
    *,
    name: str = "test-op",
    operation_dir: Path | None = None,
) -> Workflow:
    return Workflow(
        name=name,
        description="test operation",
        tasks=tasks,  # type: ignore[arg-type]
        workflow_dir=operation_dir,
    )


def _make_ctx(
    tmp_path: Path, *, dry_run: bool = True, op: Workflow | None = None
) -> RunContext:
    operation = op or Workflow(name="test-op", description="test", tasks=[])
    ctx = RunContext(dry_run=dry_run)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(
        ProjectRun(
            workflow=operation,
            prds={},
            targets=(),
        )
    )
    return ctx


# ---------- empty task list ----------


def test_run_project_operation_empty_tasks(tmp_path: Path) -> None:
    operation = _make_operation([])
    ctx = _make_ctx(tmp_path, op=operation)
    result = run_project_operation(operation, ctx)
    assert result.success is True
    assert result.steps == []
    assert result.failure_reason is None


# ---------- BuiltIn dispatch ----------


def test_run_builtin_unknown_name(tmp_path: Path) -> None:
    operation = _make_operation([BuiltIn("nonexistent_project_builtin")])
    ctx = _make_ctx(tmp_path, op=operation)
    result = run_project_operation(operation, ctx)
    assert result.success is False
    assert "no builtin registered for" in (result.failure_reason or "")
    assert len(result.steps) == 1
    assert result.steps[0].kind == "builtin"
    assert result.steps[0].success is False


def test_run_builtin_registered(tmp_path: Path) -> None:
    called_with: list[object] = []

    def my_builtin(ctx: RunContext, **kwargs: object) -> None:
        called_with.append(ctx)

    SYSTEM_BUILTINS["_test_builtin_dispatch"] = my_builtin
    try:
        operation = _make_operation([BuiltIn("_test_builtin_dispatch")])
        ctx = _make_ctx(tmp_path, op=operation)
        result = run_project_operation(operation, ctx)
        assert result.success is True
        assert len(result.steps) == 1
        assert result.steps[0].kind == "builtin"
        assert result.steps[0].success is True
        assert called_with[0] is ctx
    finally:
        SYSTEM_BUILTINS.pop("_test_builtin_dispatch", None)


def test_run_builtin_kwargs_formatted(tmp_path: Path) -> None:
    received_kwargs: dict[str, object] = {}

    def my_builtin(ctx: RunContext, **kwargs: object) -> None:
        received_kwargs.update(kwargs)

    SYSTEM_BUILTINS["_test_builtin_kwargs"] = my_builtin
    try:
        operation = _make_operation(
            [BuiltIn("_test_builtin_kwargs", kwargs={"key": "{workflow_name}"})]
        )
        ctx = _make_ctx(tmp_path, op=operation)
        result = run_project_operation(operation, ctx)
        assert result.success is True
        assert received_kwargs["key"] == "test-op"
    finally:
        SYSTEM_BUILTINS.pop("_test_builtin_kwargs", None)


def test_run_builtin_raises_fails_step(tmp_path: Path) -> None:
    def bad_builtin(ctx: RunContext, **kwargs: object) -> None:
        raise RuntimeError("exploded")

    SYSTEM_BUILTINS["_test_builtin_raises"] = bad_builtin
    try:
        operation = _make_operation([BuiltIn("_test_builtin_raises")])
        ctx = _make_ctx(tmp_path, op=operation)
        result = run_project_operation(operation, ctx)
        assert result.success is False
        assert "exploded" in (result.failure_reason or "")
    finally:
        SYSTEM_BUILTINS.pop("_test_builtin_raises", None)


# ---------- ShellTask dispatch ----------


def test_run_shell_dry_run(tmp_path: Path) -> None:
    operation = _make_operation([ShellTask("echo-test", cmd="echo hello")])
    ctx = _make_ctx(tmp_path, dry_run=True, op=operation)
    result = run_project_operation(operation, ctx)
    assert result.success is True
    assert result.steps[0].kind == "shell"
    assert "dry-run" in result.steps[0].detail


def test_run_shell_success(tmp_path: Path) -> None:
    operation = _make_operation([ShellTask("true-cmd", cmd="true")])
    ctx = _make_ctx(tmp_path, dry_run=False, op=operation)
    result = run_project_operation(operation, ctx)
    assert result.success is True
    assert result.steps[0].kind == "shell"


def test_run_shell_failure(tmp_path: Path) -> None:
    operation = _make_operation([ShellTask("false-cmd", cmd="false")])
    ctx = _make_ctx(tmp_path, dry_run=False, op=operation)
    result = run_project_operation(operation, ctx)
    assert result.success is False
    assert result.steps[0].kind == "shell"
    assert result.steps[0].success is False


def test_run_shell_ignore_failure(tmp_path: Path) -> None:
    operation = _make_operation(
        [ShellTask("ignore-fail", cmd="false", on_failure="ignore")]
    )
    ctx = _make_ctx(tmp_path, dry_run=False, op=operation)
    result = run_project_operation(operation, ctx)
    assert result.success is True
    assert "ignored" in result.steps[0].detail


def test_run_shell_format_string_substituted(tmp_path: Path) -> None:
    """format_string is applied to the shell command before execution."""
    with patch("darkfactory.runner.run_shell") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        operation = _make_operation(
            [ShellTask("op-name-cmd", cmd="echo {workflow_name}")]
        )
        ctx = _make_ctx(tmp_path, dry_run=False, op=operation)
        result = run_project_operation(operation, ctx)

    assert result.success is True
    call_args = mock_run.call_args
    assert call_args[0][0] == "echo test-op"


# ---------- AgentTask dispatch ----------


def test_run_agent_dry_run(tmp_path: Path) -> None:
    """In dry-run mode, AgentTask succeeds without actually invoking Claude."""
    op_dir = tmp_path / "op"
    op_dir.mkdir()
    prompt_file = op_dir / "task.md"
    prompt_file.write_text("# Task\n")

    operation = _make_operation(
        [AgentTask(name="impl", prompts=["task.md"])],
        operation_dir=op_dir,
    )
    ctx = _make_ctx(tmp_path, dry_run=True, op=operation)

    with patch("darkfactory.runner.invoke_claude") as mock_invoke:
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.failure_reason = None
        mock_invoke.return_value = mock_result

        result = run_project_operation(operation, ctx)

    assert result.success is True
    assert result.steps[0].kind == "agent"
    # dry_run=True was forwarded to invoke_claude
    _, kwargs = mock_invoke.call_args
    assert kwargs.get("dry_run") is True


def test_run_agent_failure(tmp_path: Path) -> None:
    op_dir = tmp_path / "op"
    op_dir.mkdir()
    (op_dir / "task.md").write_text("# Task\n")

    operation = _make_operation(
        [AgentTask(name="impl", prompts=["task.md"])],
        operation_dir=op_dir,
    )
    ctx = _make_ctx(tmp_path, dry_run=False, op=operation)

    with patch("darkfactory.runner.invoke_claude") as mock_invoke:
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.failure_reason = "sentinel not found"
        mock_invoke.return_value = mock_result

        result = run_project_operation(operation, ctx)

    assert result.success is False
    assert result.steps[0].kind == "agent"
    assert result.steps[0].success is False


# ---------- task ordering and early stop ----------


def test_early_stop_on_failure(tmp_path: Path) -> None:
    """Runner halts after the first failing task."""
    called: list[str] = []

    def builtin_a(ctx: RunContext, **kwargs: object) -> None:
        called.append("a")

    def builtin_b(ctx: RunContext, **kwargs: object) -> None:
        called.append("b")
        raise RuntimeError("b failed")

    def builtin_c(ctx: RunContext, **kwargs: object) -> None:
        called.append("c")

    SYSTEM_BUILTINS["_test_early_stop_a"] = builtin_a
    SYSTEM_BUILTINS["_test_early_stop_b"] = builtin_b
    SYSTEM_BUILTINS["_test_early_stop_c"] = builtin_c
    try:
        operation = _make_operation(
            [
                BuiltIn("_test_early_stop_a"),
                BuiltIn("_test_early_stop_b"),
                BuiltIn("_test_early_stop_c"),
            ]
        )
        ctx = _make_ctx(tmp_path, op=operation)
        result = run_project_operation(operation, ctx)
        assert result.success is False
        assert called == ["a", "b"]
        assert len(result.steps) == 2
    finally:
        SYSTEM_BUILTINS.pop("_test_early_stop_a", None)
        SYSTEM_BUILTINS.pop("_test_early_stop_b", None)
        SYSTEM_BUILTINS.pop("_test_early_stop_c", None)


# ---------- pr_url propagated ----------


def test_pr_url_propagated(tmp_path: Path) -> None:
    def builtin_sets_pr(ctx: RunContext, **kwargs: object) -> None:
        ctx.state.put(PrResult(url="https://github.com/org/repo/pull/42"))

    SYSTEM_BUILTINS["_test_pr_url"] = builtin_sets_pr
    try:
        operation = _make_operation([BuiltIn("_test_pr_url")])
        ctx = _make_ctx(tmp_path, op=operation)
        result = run_project_operation(operation, ctx)
        assert result.pr_url == "https://github.com/org/repo/pull/42"
    finally:
        SYSTEM_BUILTINS.pop("_test_pr_url", None)
