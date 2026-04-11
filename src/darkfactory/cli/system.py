"""CLI commands for the ``prd system`` subcommand group."""

from __future__ import annotations

import argparse

from darkfactory.loader import load_operations
from darkfactory.style import Element, Styler
from darkfactory.system import SystemContext
from darkfactory.system_runner import run_system_operation
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask, Task

from darkfactory.cli._shared import _emit_json, _find_repo_root, _load


def _describe_system_task(task: Task) -> str:
    """Produce a one-line description of a task for ``prd system describe``."""
    if isinstance(task, BuiltIn):
        kwargs_str = (
            " " + ", ".join(f"{k}={v!r}" for k, v in task.kwargs.items())
            if task.kwargs
            else ""
        )
        return f"builtin: {task.name}{kwargs_str}"
    if isinstance(task, AgentTask):
        prompts = ", ".join(task.prompts) or "(none)"
        model = task.model or "sonnet"
        return f"agent: {task.name} [model={model}, prompts={prompts}]"
    if isinstance(task, ShellTask):
        return f"shell: {task.name} ({task.on_failure}) -> {task.cmd}"
    return f"unknown: {type(task).__name__}"


def cmd_system_list(args: argparse.Namespace) -> int:
    """List all available system operations with name and description."""
    operations = load_operations(args.operations_dir)
    if not operations:
        print("(no system operations found)")
        return 0

    sorted_ops = sorted(operations.values(), key=lambda op: op.name)

    if args.json:
        return _emit_json(
            [
                {
                    "name": op.name,
                    "description": op.description,
                    "task_count": len(op.tasks),
                    "creates_pr": op.creates_pr,
                    "requires_clean_main": op.requires_clean_main,
                    "accepts_target": op.accepts_target,
                }
                for op in sorted_ops
            ]
        )

    for op in sorted_ops:
        print(f"{op.name:30} tasks={len(op.tasks)}")
        if op.description:
            for line in op.description.splitlines():
                print(f"  {line}")
        print()
    return 0


def cmd_system_describe(args: argparse.Namespace) -> int:
    """Show detailed metadata and task list for a system operation."""
    operations = load_operations(args.operations_dir)
    if args.name not in operations:
        raise SystemExit(f"unknown system operation: {args.name!r}")

    op = operations[args.name]

    if args.json:
        return _emit_json(
            {
                "name": op.name,
                "description": op.description,
                "requires_clean_main": op.requires_clean_main,
                "creates_pr": op.creates_pr,
                "pr_title": op.pr_title,
                "pr_body": op.pr_body,
                "accepts_target": op.accepts_target,
                "tasks": [_describe_system_task(t) for t in op.tasks],
            }
        )

    print(f"# {op.name}")
    print()
    if op.description:
        print(f"  {op.description}")
        print()
    print(f"  requires_clean_main: {op.requires_clean_main}")
    print(f"  creates_pr:          {op.creates_pr}")
    print(f"  accepts_target:      {op.accepts_target}")
    if op.pr_title:
        print(f"  pr_title:            {op.pr_title}")
    if op.pr_body:
        print(f"  pr_body:             {op.pr_body}")
    print()
    print(f"  tasks ({len(op.tasks)}):")
    for i, task in enumerate(op.tasks, start=1):
        print(f"    {i:>2}. {_describe_system_task(task)}")
    return 0


def cmd_system_run(args: argparse.Namespace) -> int:
    """Run a system operation. Dry-run by default; opt in with --execute."""
    operations = load_operations(args.operations_dir)
    if args.name not in operations:
        raise SystemExit(f"unknown system operation: {args.name!r}")

    operation = operations[args.name]

    # Validate --target against accepts_target.
    target_prd: str | None = getattr(args, "target", None)
    if target_prd is not None and not operation.accepts_target:
        raise SystemExit(
            f"operation {args.name!r} does not accept a --target (accepts_target=False)"
        )
    if target_prd is None and operation.accepts_target:
        raise SystemExit(
            f"operation {args.name!r} requires --target (accepts_target=True)"
        )

    repo_root = _find_repo_root(args.data_dir)
    dry_run = not getattr(args, "execute", False)
    model_override: str | None = getattr(args, "model", None)
    styler: Styler = args.styler

    # Acquire process lock when executing to prevent concurrent runs.
    lock = None
    if not dry_run:
        try:
            from filelock import FileLock

            lock_path = repo_root / ".harness-system.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = FileLock(str(lock_path))
            lock.acquire(timeout=0)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                f"cannot acquire system operation lock: {exc}\n"
                "Another system operation may be running. Delete "
                f"{repo_root / '.harness-system.lock'} if the previous run is dead."
            ) from None

    prds = _load(args.data_dir) if (args.data_dir / "prds").exists() else {}

    ctx = SystemContext(
        repo_root=repo_root,
        prds=prds,
        operation=operation,
        cwd=repo_root,
        dry_run=dry_run,
        target_prd=target_prd,
    )

    header_label = "Dry-run" if dry_run else "Executing"
    print(
        styler.render(
            Element.RUN_HEADER,
            f"# {header_label}: system operation {operation.name!r}",
        )
    )

    try:
        result = run_system_operation(operation, ctx, model_override=model_override)
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:  # noqa: BLE001
                pass

    print()
    print("  Steps:")
    for step in result.steps:
        step_elem = Element.RUN_SUCCESS if step.success else Element.RUN_FAILURE
        marker = "\u2713" if step.success else "\u2717"
        detail = f" \u2014 {step.detail}" if step.detail else ""
        print(
            f"    {styler.render(step_elem, marker)} [{step.kind}] {step.name}{detail}"
        )

    if ctx.report:
        print()
        print("  Report:")
        for line in ctx.report:
            print(f"    {line}")

    if ctx.targets:
        print()
        print(f"  Targets ({len(ctx.targets)}):")
        for t in ctx.targets:
            print(f"    {t}")

    print()
    if result.success:
        print(f"  Result: {styler.render(Element.RUN_SUCCESS, '\u2713 success')}")
        if result.pr_url:
            print(f"  PR:     {result.pr_url}")
        return 0
    else:
        print(
            f"  Result: {styler.render(Element.RUN_FAILURE, '\u2717 FAILED')} \u2014 {result.failure_reason}"
        )
        return 1
