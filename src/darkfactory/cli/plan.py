"""CLI subcommand: prd plan."""

from __future__ import annotations

import argparse

from darkfactory import assign
from darkfactory.cli._shared import (
    _check_runnable,
    _emit_json,
    _find_repo_root,
    _load,
    _load_workflows_or_fail,
    _resolve_base_ref,
    _resolve_prd_or_exit,
)
from darkfactory.invoke import capability_to_model
from darkfactory.model import PRD
from darkfactory.runner import _compute_branch_name, _pick_model
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Task


def _describe_task(task: Task, ctx_prd: PRD, model_override: str | None) -> str:
    """Produce a one-line human-readable description of a task for `prd plan`."""
    if isinstance(task, BuiltIn):
        kwargs_str = (
            " " + ", ".join(f"{k}={v!r}" for k, v in task.kwargs.items())
            if task.kwargs
            else ""
        )
        return f"builtin: {task.name}{kwargs_str}"
    if isinstance(task, AgentTask):
        model = _pick_model(task, ctx_prd, override=model_override)
        prompts = ", ".join(task.prompts) or "(none)"
        tools_count = len(task.tools)
        return (
            f"agent: {task.name} [model={model}, prompts={prompts}, "
            f"tools={tools_count}, retries={task.retries}]"
        )
    if isinstance(task, ShellTask):
        return f"shell: {task.name} ({task.on_failure}) -> {task.cmd}"
    return f"unknown task type: {type(task).__name__}"


def cmd_plan(args: argparse.Namespace) -> int:
    """Show the execution plan for a PRD without touching anything.

    Resolves the workflow, computes the branch name + base ref + model,
    and prints the ordered task list with descriptions. Uses git
    subprocess only for base-ref resolution; no agent invocation.
    """
    prds = _load(args.data_dir)
    prd = _resolve_prd_or_exit(args.prd_id, prds)

    workflows = _load_workflows_or_fail(args.workflows_dir)

    # Resolve workflow (respecting --workflow override).
    if args.workflow:
        if args.workflow not in workflows:
            raise SystemExit(f"unknown workflow: {args.workflow}")
        workflow = workflows[args.workflow]
    else:
        try:
            workflow = assign.assign_workflow(prd, prds, workflows)
        except KeyError as exc:
            raise SystemExit(str(exc))

    branch = _compute_branch_name(prd)
    repo_root = _find_repo_root(args.data_dir)
    base_ref = _resolve_base_ref(args.base, repo_root)

    # Note any runnability issues as warnings (plan still shows, but
    # the user gets a heads-up that `prd run --execute` would refuse).
    runnable_error = _check_runnable(prd, prds)

    if args.json:
        return _emit_json(
            {
                "prd": {
                    "id": prd.id,
                    "title": prd.title,
                    "kind": prd.kind,
                    "status": prd.status,
                    "capability": prd.capability,
                },
                "workflow": {
                    "name": workflow.name,
                    "description": workflow.description,
                    "priority": workflow.priority,
                },
                "branch": branch,
                "base_ref": base_ref,
                "default_model": capability_to_model(prd.capability),
                "tasks": [
                    _describe_task(task, prd, args.model) for task in workflow.tasks
                ],
                "runnable_error": runnable_error,
            }
        )

    print(f"# Plan for {prd.id}: {prd.title}")
    print()
    print(f"  kind:       {prd.kind}")
    print(f"  status:     {prd.status}")
    print(
        f"  capability: {prd.capability} -> default model {capability_to_model(prd.capability)}"
    )
    print()
    tmpl_tag = (
        f"template: {workflow.template_name}"
        if workflow.template_name
        else "no template"
    )
    print(f"  workflow:   {workflow.name} ({tmpl_tag})")
    if workflow.description:
        print(f"  — {workflow.description}")
    print()
    print(f"  branch:     {branch}")
    print(f"  base ref:   {base_ref}")
    print()
    print(f"  tasks ({len(workflow.tasks)}):")
    for i, task in enumerate(workflow.tasks, start=1):
        print(f"    {i:>2}. {_describe_task(task, prd, args.model)}")

    if runnable_error:
        print()
        print(f"  ⚠ NOT RUNNABLE: {runnable_error}")
        print("    (`prd run --execute` would refuse this PRD)")
    return 0
