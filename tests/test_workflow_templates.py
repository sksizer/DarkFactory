"""Tests for WorkflowTemplate and TemplateViolation."""

from __future__ import annotations

from typing import Any

import pytest

from darkfactory.templates import TemplateViolation, WorkflowTemplate
from darkfactory.templates_builtin import REWORK_TEMPLATE, SYSTEM_OPERATION_TEMPLATE
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Task, Workflow


def _make_template(**kwargs: Any) -> WorkflowTemplate:
    """Build a WorkflowTemplate with sensible defaults."""
    defaults: dict[str, Any] = dict(
        name="test-template",
        description="A test template",
        open=[BuiltIn("ensure_worktree")],
        close=[BuiltIn("commit"), BuiltIn("push_branch")],
        middle_kinds=[AgentTask, ShellTask],
        middle_required={},
    )
    defaults.update(kwargs)
    return WorkflowTemplate(**defaults)


def _dummy_applies_to(prd: Any, prds: Any) -> bool:
    return True


# ---------- AC-1: task ordering ----------


def test_compose_task_order_is_open_middle_close() -> None:
    """compose() produces [*open, *middle, *close] task ordering."""
    open_task = BuiltIn("ensure_worktree")
    close_task = BuiltIn("push_branch")
    middle_task = AgentTask(name="implement")

    tmpl = WorkflowTemplate(
        name="ordered",
        description="ordering test",
        open=[open_task],
        close=[close_task],
        middle_kinds=[AgentTask],
    )
    wf = tmpl.compose(
        name="my-workflow",
        description="desc",
        applies_to=_dummy_applies_to,
        priority=5,
        middle=[middle_task],
    )

    assert wf.tasks == [open_task, middle_task, close_task]


def test_compose_multiple_open_and_close() -> None:
    """All open and close tasks appear in the correct order."""
    o1 = BuiltIn("ensure_worktree")
    o2 = BuiltIn("set_status")
    c1 = BuiltIn("commit")
    c2 = BuiltIn("push_branch")
    m1 = AgentTask(name="implement")
    m2 = ShellTask(name="test", cmd="just test")

    tmpl = WorkflowTemplate(
        name="multi",
        description="multi open/close",
        open=[o1, o2],
        close=[c1, c2],
        middle_kinds=[AgentTask, ShellTask],
    )
    wf = tmpl.compose(
        name="wf",
        description="",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[m1, m2],
    )

    assert wf.tasks == [o1, o2, m1, m2, c1, c2]


def test_compose_empty_middle_produces_open_plus_close() -> None:
    """Empty middle is valid when no kinds or requirements are enforced."""
    tmpl = WorkflowTemplate(
        name="empty-middle",
        description="",
        open=[BuiltIn("ensure_worktree")],
        close=[BuiltIn("push_branch")],
        middle_kinds=[],
        middle_required={},
    )
    wf = tmpl.compose(
        name="wf",
        description="",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[],
    )
    assert len(wf.tasks) == 2
    assert wf.tasks[0] == BuiltIn("ensure_worktree")
    assert wf.tasks[1] == BuiltIn("push_branch")


def test_compose_sets_workflow_fields() -> None:
    """Workflow name, description, applies_to, and priority come from compose args."""
    tmpl = _make_template()
    wf = tmpl.compose(
        name="specific-wf",
        description="my description",
        applies_to=_dummy_applies_to,
        priority=10,
        middle=[AgentTask(name="implement")],
    )
    assert wf.name == "specific-wf"
    assert wf.description == "my description"
    assert wf.applies_to is _dummy_applies_to
    assert wf.priority == 10


# ---------- AC-2: middle_kinds violation ----------


def test_compose_raises_for_disallowed_kind() -> None:
    """A task not in middle_kinds raises TemplateViolation."""
    tmpl = WorkflowTemplate(
        name="agent-only",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask],
    )
    shell_task = ShellTask(name="test", cmd="just test")
    with pytest.raises(TemplateViolation, match="not an allowed middle kind"):
        tmpl.compose(
            name="wf",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[shell_task],
        )


def test_compose_violation_message_names_allowed_kinds() -> None:
    """TemplateViolation message includes the allowed kind names."""
    tmpl = WorkflowTemplate(
        name="strict",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask],
    )
    with pytest.raises(TemplateViolation, match="AgentTask"):
        tmpl.compose(
            name="wf",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[ShellTask(name="s", cmd="x")],
        )


def test_compose_allows_all_listed_kinds() -> None:
    """Tasks that are instances of any listed kind are accepted."""
    tmpl = _make_template(middle_kinds=[AgentTask, ShellTask])
    wf = tmpl.compose(
        name="wf",
        description="",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[AgentTask(name="implement"), ShellTask(name="verify", cmd="just test")],
    )
    # _make_template: 1 open + 2 middle + 2 close = 5
    assert len(wf.tasks) == 5


# ---------- AC-3: middle_required violation ----------


def test_compose_raises_when_required_kind_too_few() -> None:
    """TemplateViolation raised when a required kind appears fewer than min times."""
    tmpl = WorkflowTemplate(
        name="needs-agent",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask, ShellTask],
        middle_required={AgentTask: (1, None)},
    )
    with pytest.raises(TemplateViolation, match="at least 1 AgentTask"):
        tmpl.compose(
            name="wf",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[ShellTask(name="test", cmd="just test")],
        )


def test_compose_raises_when_required_kind_too_many() -> None:
    """TemplateViolation raised when a required kind exceeds max count."""
    tmpl = WorkflowTemplate(
        name="max-one-agent",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask, ShellTask],
        middle_required={AgentTask: (0, 1)},
    )
    with pytest.raises(TemplateViolation, match="at most 1 AgentTask"):
        tmpl.compose(
            name="wf",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[AgentTask(name="a"), AgentTask(name="b")],
        )


def test_compose_raises_too_few_includes_count() -> None:
    """Violation message for too-few includes the actual count."""
    tmpl = WorkflowTemplate(
        name="t",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask],
        middle_required={AgentTask: (2, None)},
    )
    with pytest.raises(TemplateViolation, match="got 1"):
        tmpl.compose(
            name="wf",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[AgentTask(name="a")],
        )


def test_compose_at_exactly_min_succeeds() -> None:
    """Exactly meeting the minimum required count is valid."""
    tmpl = WorkflowTemplate(
        name="t",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask],
        middle_required={AgentTask: (1, None)},
    )
    wf = tmpl.compose(
        name="wf",
        description="",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[AgentTask(name="a")],
    )
    assert len(wf.tasks) == 1


def test_compose_at_exactly_max_succeeds() -> None:
    """Exactly meeting the maximum allowed count is valid."""
    tmpl = WorkflowTemplate(
        name="t",
        description="",
        open=[],
        close=[],
        middle_kinds=[AgentTask],
        middle_required={AgentTask: (0, 2)},
    )
    wf = tmpl.compose(
        name="wf",
        description="",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[AgentTask(name="a"), AgentTask(name="b")],
    )
    assert len(wf.tasks) == 2


# ---------- AC-4: template_name on composed workflow ----------


def test_compose_sets_template_name() -> None:
    """The composed Workflow has template_name matching the template's name."""
    tmpl = _make_template(name="my-template")
    wf = tmpl.compose(
        name="wf",
        description="",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[AgentTask(name="implement")],
    )
    assert wf.template_name == "my-template"


def test_compose_template_name_matches_template_name_field() -> None:
    """template_name always matches the WorkflowTemplate.name field."""
    for tname in ["prd-implementation", "rework", "planning"]:
        tmpl = _make_template(name=tname)
        wf = tmpl.compose(
            name="wf",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[AgentTask(name="implement")],
        )
        assert wf.template_name == tname


# ---------- AC-5: Workflow default template_name ----------


def test_workflow_template_name_defaults_to_none() -> None:
    """A Workflow constructed without template_name has template_name=None."""
    wf = Workflow(name="bare", tasks=[BuiltIn("ensure_worktree")])
    assert wf.template_name is None


def test_workflow_can_be_constructed_without_template_name() -> None:
    """Existing Workflow construction still works unchanged."""
    wf = Workflow(
        name="legacy",
        description="no template",
        tasks=[BuiltIn("ensure_worktree"), AgentTask(name="implement")],
        priority=1,
    )
    assert wf.template_name is None
    assert len(wf.tasks) == 2


# ---------- REWORK_TEMPLATE tests ----------


def test_rework_template_is_importable() -> None:
    """REWORK_TEMPLATE is importable from darkfactory.templates_builtin."""
    assert REWORK_TEMPLATE is not None
    assert isinstance(REWORK_TEMPLATE, WorkflowTemplate)
    assert REWORK_TEMPLATE.name == "rework"


def test_rework_template_open_includes_check_pr_exists_and_fetch_review_comments() -> (
    None
):
    """open list includes check_pr_exists and fetch_review_comments."""
    open_names = [t.name for t in REWORK_TEMPLATE.open]
    assert "check_pr_exists" in open_names
    assert "fetch_review_comments" in open_names


def test_rework_template_close_does_not_include_create_pr() -> None:
    """close list does NOT include create_pr."""
    close_names = [t.name for t in REWORK_TEMPLATE.close]
    assert "create_pr" not in close_names


def test_rework_template_close_includes_push_branch() -> None:
    """close list includes push_branch instead of create_pr."""
    close_names = [t.name for t in REWORK_TEMPLATE.close]
    assert "push_branch" in close_names


def test_rework_template_valid_composition() -> None:
    """Composing with an AgentTask produces correct task order."""
    agent = AgentTask(name="address-feedback")
    wf = REWORK_TEMPLATE.compose(
        name="rework-prd-123",
        description="Address review feedback",
        applies_to=lambda prd, prds: True,
        priority=5,
        middle=[agent],
    )
    open_names = [t.name for t in REWORK_TEMPLATE.open]
    close_names = [t.name for t in REWORK_TEMPLATE.close]
    task_list = wf.tasks
    # open tasks come first
    for i, name in enumerate(open_names):
        assert task_list[i].name == name
    # middle task is next
    assert task_list[len(open_names)] is agent
    # close tasks come last
    for i, name in enumerate(close_names):
        assert task_list[len(open_names) + 1 + i].name == name


def test_rework_template_missing_agent_task_raises() -> None:
    """Composing with no AgentTask raises TemplateViolation."""
    with pytest.raises(TemplateViolation, match="at least 1 AgentTask"):
        REWORK_TEMPLATE.compose(
            name="rework-wf",
            description="",
            applies_to=lambda prd, prds: True,
            priority=0,
            middle=[ShellTask(name="verify", cmd="just test")],
        )


def test_rework_template_empty_middle_raises() -> None:
    """Composing with empty middle raises TemplateViolation (needs AgentTask)."""
    with pytest.raises(TemplateViolation, match="at least 1 AgentTask"):
        REWORK_TEMPLATE.compose(
            name="rework-wf",
            description="",
            applies_to=lambda prd, prds: True,
            priority=0,
            middle=[],
        )


# ---------- SYSTEM_OPERATION_TEMPLATE ----------


def test_system_operation_template_is_importable() -> None:
    """SYSTEM_OPERATION_TEMPLATE is importable from darkfactory.templates_builtin."""
    assert SYSTEM_OPERATION_TEMPLATE is not None
    assert SYSTEM_OPERATION_TEMPLATE.name == "system-operation"


def test_system_operation_template_open_starts_with_acquire_lock() -> None:
    """The first open task is acquire_global_lock."""
    assert SYSTEM_OPERATION_TEMPLATE.open[0] == BuiltIn("acquire_global_lock")


def test_system_operation_template_close_ends_with_release_lock() -> None:
    """The last close task is release_global_lock."""
    assert SYSTEM_OPERATION_TEMPLATE.close[-1] == BuiltIn("release_global_lock")


def test_system_operation_template_compose_empty_middle_succeeds() -> None:
    """Composing with an empty middle is valid (no minimum count constraints)."""
    wf = SYSTEM_OPERATION_TEMPLATE.compose(
        name="sys-op",
        description="test run",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[],
    )
    # open(2) + middle(0) + close(3) = 5
    assert len(wf.tasks) == 5
    assert wf.tasks[0] == BuiltIn("acquire_global_lock")
    assert wf.tasks[-1] == BuiltIn("release_global_lock")


def test_system_operation_template_compose_valid_middle() -> None:
    """Valid composition produces [lock, log_start, *middle, report, log_end, unlock]."""
    shell = ShellTask(name="run-op", cmd="just operate")
    agent = AgentTask(name="agent-op")
    wf = SYSTEM_OPERATION_TEMPLATE.compose(
        name="sys-op",
        description="test run",
        applies_to=_dummy_applies_to,
        priority=0,
        middle=[shell, agent],
    )
    assert wf.tasks == [
        BuiltIn("acquire_global_lock"),
        BuiltIn("log_operation_start"),
        shell,
        agent,
        BuiltIn("write_report"),
        BuiltIn("log_operation_end"),
        BuiltIn("release_global_lock"),
    ]


def test_system_operation_template_disallows_unknown_kinds() -> None:
    """A task kind not in middle_kinds raises TemplateViolation."""

    class ForeignTask(Task):
        pass

    foreign = ForeignTask()
    with pytest.raises(TemplateViolation, match="not an allowed middle kind"):
        SYSTEM_OPERATION_TEMPLATE.compose(
            name="sys-op",
            description="",
            applies_to=_dummy_applies_to,
            priority=0,
            middle=[foreign],
        )
