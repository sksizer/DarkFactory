"""Tests for the rework prompt rendering module.

Covers ``render_rework_feedback`` and its integration with the
``templates.py`` placeholder substitution system.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from darkfactory.utils.github.pr.comments import ReviewComment, ReviewThread
from darkfactory.rework.prompt import render_rework_feedback
from darkfactory.templates import compose_prompt, substitute_placeholders
from darkfactory.workflow import ExecutionContext, Workflow


# ---------- helpers ----------


def _thread(
    *,
    author: str = "alice",
    path: str | None = "src/foo.py",
    line: int | None = 42,
    body: str = "Please add a docstring.",
    replies: list[ReviewComment] | None = None,
    is_resolved: bool = False,
) -> ReviewThread:
    return ReviewThread(
        thread_id="t-1",
        author=author,
        path=path,
        line=line,
        body=body,
        posted_at="2026-04-07T10:00:00Z",
        is_resolved=is_resolved,
        replies=replies or [],
        review_state=None,
    )


# ---------- single thread ----------


def test_single_thread_produces_expected_markdown() -> None:
    threads = [_thread()]
    result = render_rework_feedback(threads)

    assert "### Comment by alice on `src/foo.py`:42" in result
    assert "> Please add a docstring." in result
    assert "---" in result


def test_single_thread_no_replies_section() -> None:
    threads = [_thread(replies=[])]
    result = render_rework_feedback(threads)

    assert "**Thread replies:**" not in result


# ---------- multiple threads ----------


def test_multiple_threads_all_appear() -> None:
    threads = [
        _thread(author="alice", body="First comment"),
        ReviewThread(
            thread_id="t-2",
            author="bob",
            path="src/bar.py",
            line=10,
            body="Second comment",
            posted_at="2026-04-07T11:00:00Z",
            is_resolved=False,
            replies=[],
            review_state=None,
        ),
    ]
    result = render_rework_feedback(threads)

    assert "alice" in result
    assert "First comment" in result
    assert "bob" in result
    assert "Second comment" in result


def test_multiple_threads_with_replies() -> None:
    reply = ReviewComment(
        author="bob", body="Working on it.", posted_at="2026-04-07T11:00:00Z"
    )
    threads = [
        _thread(author="alice", body="Needs a docstring.", replies=[reply]),
        ReviewThread(
            thread_id="t-2",
            author="carol",
            path="src/bar.py",
            line=5,
            body="Missing test coverage.",
            posted_at="2026-04-07T12:00:00Z",
            is_resolved=False,
            replies=[],
            review_state=None,
        ),
    ]
    result = render_rework_feedback(threads)

    assert "**Thread replies:**" in result
    assert "> **bob:** Working on it." in result
    assert "carol" in result
    assert "Missing test coverage." in result


# ---------- issue-level comment (no path/line) ----------


def test_issue_level_comment_no_path() -> None:
    """Issue-level comments (path=None, line=None) should render without location."""
    threads = [_thread(path=None, line=None, body="General feedback here.")]
    result = render_rework_feedback(threads)

    assert "### Comment by alice" in result
    assert "on `" not in result
    assert "General feedback here." in result


def test_path_without_line() -> None:
    """A comment with a path but no line number should not include ':None'."""
    threads = [_thread(path="src/foo.py", line=None, body="Check this file.")]
    result = render_rework_feedback(threads)

    assert "on `src/foo.py`" in result
    assert "None" not in result


# ---------- multiline body ----------


def test_multiline_body_fully_blockquoted() -> None:
    """Every line of a multiline body should be blockquoted."""
    body = "First line\nSecond line\nThird line"
    threads = [_thread(body=body)]
    result = render_rework_feedback(threads)

    assert "> First line" in result
    assert "> Second line" in result
    assert "> Third line" in result
    # No unquoted body lines
    for line in result.splitlines():
        if "First line" in line or "Second line" in line or "Third line" in line:
            assert line.startswith(">"), f"Unquoted body line: {line!r}"


def test_multiline_reply_fully_blockquoted() -> None:
    """Every line of a multiline reply body should be blockquoted."""
    reply = ReviewComment(
        author="bob",
        body="Line one\nLine two",
        posted_at="2026-04-07T11:00:00Z",
    )
    threads = [_thread(body="Original.", replies=[reply])]
    result = render_rework_feedback(threads)

    assert "> **bob:** Line one" in result
    assert "> Line two" in result


# ---------- empty thread list ----------


def test_empty_threads_returns_no_feedback_message() -> None:
    result = render_rework_feedback([])
    assert result == "No feedback to address."


# ---------- template variable substitution ----------


def test_task_template_substitutes_prd_id_and_prd_path(tmp_path: Path) -> None:
    """PRD_ID and PRD_PATH placeholders in task.md are substituted correctly."""
    template = (
        "# Rework for {{PRD_ID}}\n\nPRD at `{{PRD_PATH}}`.\n\n{{REWORK_FEEDBACK}}"
    )
    feedback = render_rework_feedback([_thread()])
    result = substitute_placeholders(
        template,
        {
            "PRD_ID": "PRD-225",
            "PRD_PATH": "/prds/PRD-225-some-task.md",
            "REWORK_FEEDBACK": feedback,
        },
    )

    assert "PRD-225" in result
    assert "/prds/PRD-225-some-task.md" in result
    assert "alice" in result


def test_rework_feedback_inserted_via_extras(tmp_path: Path) -> None:
    """render_rework_feedback output slots into compose_prompt via extras."""
    prompts_dir = tmp_path / "rework" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "task.md").write_text("Rework {{PRD_ID}}\n\n{{REWORK_FEEDBACK}}\n")

    wf = Workflow(name="rework", workflow_dir=tmp_path / "rework")
    feedback = render_rework_feedback([_thread(body="Fix the typo.")])

    # Minimal fake ExecutionContext attributes via a simple object
    from types import SimpleNamespace

    from darkfactory.engine import PhaseState

    prd = SimpleNamespace(
        id="PRD-225",
        title="Rework feedback loop",
        path=Path("/prds/PRD-225.md"),
        slug="rework-feedback-loop",
    )
    ctx = SimpleNamespace(
        prd=prd,
        branch_name="prd/PRD-225-rework",
        base_ref="main",
        worktree_path=None,
        state=PhaseState(),
    )

    result = compose_prompt(
        wf,
        ["prompts/task.md"],
        cast(ExecutionContext, ctx),
        extras={"REWORK_FEEDBACK": feedback},
    )

    assert "PRD-225" in result
    assert "Fix the typo." in result


# ---------- role.md contains sentinel contract ----------


def test_role_md_contains_sentinel_contract() -> None:
    """The role.md template must include the sentinel contract."""
    role_path = (
        Path(__file__).parent.parent
        / "src"
        / "darkfactory"
        / "workflows"
        / "rework"
        / "prompts"
        / "role.md"
    )
    content = role_path.read_text(encoding="utf-8")

    assert "PRD_EXECUTE_OK" in content
    assert "PRD_EXECUTE_FAILED" in content
    assert "{{PRD_ID}}" in content
