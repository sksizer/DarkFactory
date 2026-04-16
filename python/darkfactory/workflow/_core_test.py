"""Unit tests for RunContext.format_string — focusing on shell_escape safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.operations._test_helpers import make_builtin_ctx, _make_test_prd
from darkfactory.engine import CodeEnv, PrdWorkflowRun
from darkfactory.workflow import RunContext, Workflow


# ---------------------------------------------------------------------------
# shell_escape=False (default) — values passed through verbatim
# ---------------------------------------------------------------------------


def test_format_string_default_no_escaping(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, prd_id="PRD-001")
    result = ctx.format_string("echo {prd_id}")
    assert result == "echo PRD-001"


def test_format_string_default_preserves_shell_metacharacters(tmp_path: Path) -> None:
    """Confirm the vulnerability is present without shell_escape (documents intent)."""
    prd = _make_test_prd(title="$(evil)")
    ctx = RunContext(dry_run=False, event_writer=None)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(PrdWorkflowRun(prd=prd, workflow=Workflow(name="t", tasks=[])))
    result = ctx.format_string("echo {prd_title}")
    # Without escaping the metacharacters remain, which is expected for non-shell use
    assert "$(evil)" in result


# ---------------------------------------------------------------------------
# shell_escape=True — values quoted so metacharacters cannot inject commands
# ---------------------------------------------------------------------------


def test_format_string_shell_escape_simple_value(tmp_path: Path) -> None:
    ctx = make_builtin_ctx(tmp_path, prd_id="PRD-042")
    result = ctx.format_string("git log --oneline {prd_id}", shell_escape=True)
    assert result == "git log --oneline 'PRD-042'"


def test_format_string_shell_escape_neutralises_subshell(tmp_path: Path) -> None:
    prd = _make_test_prd(title="$(rm -rf /)")
    ctx = RunContext(dry_run=False, event_writer=None)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(PrdWorkflowRun(prd=prd, workflow=Workflow(name="t", tasks=[])))
    result = ctx.format_string("echo {prd_title}", shell_escape=True)
    # The substituted value must be shell-quoted so $(...) cannot execute
    assert "$(rm -rf /)" not in result
    assert "rm -rf /" not in result.replace("'", "")


def test_format_string_shell_escape_neutralises_semicolon_injection(
    tmp_path: Path,
) -> None:
    prd = _make_test_prd(title="foo; rm -rf /")
    ctx = RunContext(dry_run=False, event_writer=None)
    ctx.state.put(CodeEnv(repo_root=tmp_path, cwd=tmp_path))
    ctx.state.put(PrdWorkflowRun(prd=prd, workflow=Workflow(name="t", tasks=[])))
    result = ctx.format_string("echo {prd_title}", shell_escape=True)
    # The semicolon must be quoted/escaped so it is treated as literal text
    import shlex

    tokens = shlex.split(result)
    # shlex.split should produce exactly two tokens: "echo" and the literal value
    assert tokens[0] == "echo"
    assert tokens[1] == "foo; rm -rf /"


def test_format_string_shell_escape_handles_spaces_in_paths(tmp_path: Path) -> None:
    spaced = tmp_path / "path with spaces"
    ctx = RunContext(dry_run=False, event_writer=None)
    ctx.state.put(CodeEnv(repo_root=spaced, cwd=spaced))
    result = ctx.format_string("ls {cwd}", shell_escape=True)
    import shlex

    tokens = shlex.split(result)
    assert tokens == ["ls", str(spaced)]
