"""CLI subcommand: prd plan."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from darkfactory import assign, containment, graph
from darkfactory.cli._shared import (
    _find_repo_root,
    _load,
    _load_workflows_or_fail,
)
from darkfactory.invoke import capability_to_model
from darkfactory.prd import PRD
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


def _resolve_base_ref(explicit: str | None, repo_root: Path) -> str:
    """Determine the git base ref for a new workflow branch.

    Resolution order:

    1. ``explicit`` from ``--base`` (highest priority)
    2. ``DARKFACTORY_BASE_REF`` environment variable
    3. ``main`` if it exists locally
    4. ``master`` if it exists locally
    5. The remote's default branch via ``origin/HEAD``
    6. Last resort: ``main`` (callers will hit a real error later if it's
       missing too)

    The user's current branch is **not** consulted. PRDs are independent
    units of work and should base on the project's default branch unless
    the user says otherwise. Stacking onto a feature branch is the
    exception, not the rule, and requires an explicit ``--base`` flag.
    """
    if explicit:
        return explicit

    env_override = os.environ.get("DARKFACTORY_BASE_REF")
    if env_override:
        return env_override

    for candidate in ("main", "master"):
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "rev-parse",
                "--verify",
                "--quiet",
                f"refs/heads/{candidate}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return candidate

    # Try remote's default branch (e.g. for fresh clones with no local main)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        # Output looks like "refs/remotes/origin/main"
        return result.stdout.strip().rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        pass

    return "main"


def _check_runnable(prd: PRD, prds: dict[str, PRD]) -> str | None:
    """Return an error string if the PRD can't be run, else None."""
    if prd.status == "done":
        return f"{prd.id} is already done"
    if prd.status == "cancelled":
        return f"{prd.id} is cancelled"
    if not graph.is_actionable(prd, prds):
        missing = graph.missing_deps(prd, prds)
        if missing:
            return f"{prd.id} depends on missing PRDs: {', '.join(missing)}"
        unfinished = [
            dep_id
            for dep_id in prd.depends_on
            if dep_id in prds and prds[dep_id].status != "done"
        ]
        if unfinished:
            return f"{prd.id} has unfinished dependencies: " + ", ".join(
                f"{d} ({prds[d].status})" for d in unfinished
            )
        return f"{prd.id} status is {prd.status!r}, not 'ready'"
    if not containment.is_runnable(prd, prds):
        return (
            f"{prd.id} is an epic/feature with children; "
            "use the planning workflow or run its task descendants instead"
        )
    return None


def cmd_plan(args: argparse.Namespace) -> int:
    """Show the execution plan for a PRD without touching anything.

    Resolves the workflow, computes the branch name + base ref + model,
    and prints the ordered task list with descriptions. Uses git
    subprocess only for base-ref resolution; no agent invocation.
    """
    prds = _load(args.prd_dir)
    if args.prd_id not in prds:
        raise SystemExit(f"unknown PRD id: {args.prd_id}")
    prd = prds[args.prd_id]

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
    repo_root = _find_repo_root(args.prd_dir)
    base_ref = _resolve_base_ref(args.base, repo_root)

    # Note any runnability issues as warnings (plan still shows, but
    # the user gets a heads-up that `prd run --execute` would refuse).
    runnable_error = _check_runnable(prd, prds)

    if args.json:
        payload: dict[str, object] = {
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
            "tasks": [_describe_task(task, prd, args.model) for task in workflow.tasks],
            "runnable_error": runnable_error,
        }
        print(json.dumps(payload, indent=2))
        return 0

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
