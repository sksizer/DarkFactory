"""Tests for prompt template loading and variable substitution."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.model import load_all
from darkfactory.templates import (
    compose_prompt,
    load_prompt_files,
    substitute_placeholders,
)
from darkfactory.workflow import ExecutionContext, Workflow

from .conftest import write_prd


# ---------- load_prompt_files ----------


def test_load_single_prompt_file(tmp_path: Path) -> None:
    wf_dir = tmp_path / "default"
    wf_dir.mkdir()
    (wf_dir / "role.md").write_text("# Role\n\nYou are an agent.\n")

    content = load_prompt_files(wf_dir, ["role.md"])
    assert "# Role" in content
    assert "You are an agent." in content


def test_load_multiple_files_concatenated(tmp_path: Path) -> None:
    wf_dir = tmp_path / "default"
    wf_dir.mkdir()
    (wf_dir / "role.md").write_text("ROLE\n")
    (wf_dir / "task.md").write_text("TASK\n")

    content = load_prompt_files(wf_dir, ["role.md", "task.md"])
    # Blank line separator between files
    assert "ROLE\n\n\nTASK\n" in content or content == "ROLE\n\n\nTASK\n"
    assert content.index("ROLE") < content.index("TASK")


def test_load_files_from_subdirectory(tmp_path: Path) -> None:
    wf_dir = tmp_path / "default"
    (wf_dir / "prompts").mkdir(parents=True)
    (wf_dir / "prompts" / "role.md").write_text("nested\n")

    content = load_prompt_files(wf_dir, ["prompts/role.md"])
    assert "nested" in content


def test_load_missing_file_raises(tmp_path: Path) -> None:
    wf_dir = tmp_path / "default"
    wf_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="prompt file not found"):
        load_prompt_files(wf_dir, ["nonexistent.md"])


def test_load_missing_file_error_includes_workflow_name(tmp_path: Path) -> None:
    """The error message should name the workflow for fast debugging."""
    wf_dir = tmp_path / "ui-component"
    wf_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="ui-component"):
        load_prompt_files(wf_dir, ["missing.md"])


# ---------- substitute_placeholders ----------


def test_substitute_known_placeholder() -> None:
    result = substitute_placeholders("hello {{NAME}}", {"NAME": "world"})
    assert result == "hello world"


def test_substitute_multiple_placeholders() -> None:
    template = "PRD {{PRD_ID}}: {{PRD_TITLE}}"
    ctx = {"PRD_ID": "PRD-070", "PRD_TITLE": "Obsidian filter"}
    assert substitute_placeholders(template, ctx) == "PRD PRD-070: Obsidian filter"


def test_substitute_unknown_placeholders_left_unchanged() -> None:
    """Unknown placeholders survive intact so prompts can evolve incrementally."""
    template = "known: {{KNOWN}}, unknown: {{UNKNOWN}}"
    result = substitute_placeholders(template, {"KNOWN": "yes"})
    assert result == "known: yes, unknown: {{UNKNOWN}}"


def test_substitute_empty_context() -> None:
    """Empty context = no substitution, template unchanged."""
    template = "hello {{NAME}}"
    assert substitute_placeholders(template, {}) == "hello {{NAME}}"


def test_substitute_coerces_non_string_values() -> None:
    """Integers and Paths should work without caller ceremony."""
    template = "count: {{N}}, path: {{P}}"
    result = substitute_placeholders(template, {"N": 42, "P": Path("/tmp/foo")})
    assert "count: 42" in result
    assert "/tmp/foo" in result


def test_substitute_literal_single_braces_untouched() -> None:
    """Single-brace ``{ }`` should pass through — only ``{{ }}`` is a placeholder."""
    template = "a = { key: 'value' }"
    assert substitute_placeholders(template, {"KEY": "x"}) == template


def test_substitute_nested_braces_in_code_blocks() -> None:
    """Triple-plus braces inside prompts (code blocks) are fine."""
    template = "```js\nconst x = {{a: 1}};\n```"
    # {{a: 1}} doesn't match PLACEHOLDER_RE (has colon and space), left alone
    result = substitute_placeholders(template, {})
    assert result == template


# ---------- compose_prompt ----------


def _make_ctx(
    tmp_data_dir: Path, workflow_dir: Path
) -> tuple[Workflow, ExecutionContext]:
    """Build a workflow (with workflow_dir set) and a context for testing compose."""
    (tmp_data_dir / "prds").mkdir(exist_ok=True)
    write_prd(tmp_data_dir / "prds", "PRD-070", "test-task")
    prds = load_all(tmp_data_dir)
    wf = Workflow(name="default", workflow_dir=workflow_dir)
    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_data_dir,
        workflow=wf,
        base_ref="main",
        branch_name="prd/PRD-070-test-task",
        worktree_path=tmp_data_dir / ".worktrees" / "PRD-070-test-task",
    )
    return wf, ctx


def test_compose_prompt_substitutes_prd_fields(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "default" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "task.md").write_text(
        "Implement {{PRD_ID}}: {{PRD_TITLE}}\nBranch: {{BRANCH_NAME}}\n"
    )

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    wf, ctx = _make_ctx(prd_dir, tmp_path / "default")

    result = compose_prompt(wf, ["prompts/task.md"], ctx)
    assert "Implement PRD-070" in result
    assert "Test PRD" in result  # title from fixture
    assert "Branch: prd/PRD-070-test-task" in result


def test_compose_prompt_substitutes_worktree_path(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "default" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "task.md").write_text("cd {{WORKTREE_PATH}}\n")

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    wf, ctx = _make_ctx(prd_dir, tmp_path / "default")

    result = compose_prompt(wf, ["prompts/task.md"], ctx)
    assert "cd " in result
    assert str(ctx.worktree_path) in result


def test_compose_prompt_worktree_empty_when_unset(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "default" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "task.md").write_text("path=[{{WORKTREE_PATH}}]\n")

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    wf, ctx = _make_ctx(prd_dir, tmp_path / "default")
    ctx.worktree_path = None  # override to unset

    result = compose_prompt(wf, ["prompts/task.md"], ctx)
    assert "path=[]" in result


def test_compose_prompt_merges_extras(tmp_path: Path) -> None:
    """The extras dict (for things like CHECK_OUTPUT) is merged into context."""
    prompts_dir = tmp_path / "default" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "verify.md").write_text(
        "Check failed:\n{{CHECK_OUTPUT}}\nFor {{PRD_ID}}.\n"
    )

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    wf, ctx = _make_ctx(prd_dir, tmp_path / "default")

    result = compose_prompt(
        wf,
        ["prompts/verify.md"],
        ctx,
        extras={"CHECK_OUTPUT": "test_foo FAILED"},
    )
    assert "test_foo FAILED" in result
    assert "For PRD-070" in result


def test_compose_prompt_extras_override_defaults(tmp_path: Path) -> None:
    """Extras take precedence over the standard PRD-derived context values."""
    prompts_dir = tmp_path / "default" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "task.md").write_text("id={{PRD_ID}}\n")

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    wf, ctx = _make_ctx(prd_dir, tmp_path / "default")

    result = compose_prompt(wf, ["prompts/task.md"], ctx, extras={"PRD_ID": "OVERRIDE"})
    assert "id=OVERRIDE" in result


def test_compose_prompt_raises_when_workflow_dir_unset(tmp_path: Path) -> None:
    """A Workflow built by hand without workflow_dir can't compose prompts."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prds_dir = data_dir / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-070", "test")
    prds = load_all(data_dir)

    wf = Workflow(name="hand-built")  # workflow_dir is None
    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=data_dir,
        workflow=wf,
        base_ref="main",
        branch_name="prd/PRD-070-test",
    )
    with pytest.raises(ValueError, match="no workflow_dir"):
        compose_prompt(wf, ["prompts/task.md"], ctx)


def test_compose_prompt_concatenates_multiple(tmp_path: Path) -> None:
    """Multiple prompt files are concatenated with blank line separators."""
    prompts_dir = tmp_path / "default" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "role.md").write_text("# Role\nAgent.\n")
    (prompts_dir / "task.md").write_text("# Task\nImplement {{PRD_ID}}.\n")

    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    wf, ctx = _make_ctx(prd_dir, tmp_path / "default")

    result = compose_prompt(wf, ["prompts/role.md", "prompts/task.md"], ctx)
    assert "# Role" in result
    assert "# Task" in result
    assert "PRD-070" in result
    assert result.index("# Role") < result.index("# Task")
