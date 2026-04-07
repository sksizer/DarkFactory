"""Declarative workflow definitions for the PRD harness.

A ``Workflow`` is a named, ordered list of ``Task`` s that implement one
kind of PRD. Three task types compose a workflow:

- :class:`BuiltIn` — reference a deterministic primitive by name. The
  set is fixed by the harness package (``builtins.py``): ``ensure_worktree``,
  ``set_status``, ``commit``, ``push_branch``, ``create_pr``, etc.
- :class:`AgentTask` — invoke Claude Code with composed prompts, a tool
  allowlist, and a model selection. This is the only task type where
  actual code gets written.
- :class:`ShellTask` — run a deterministic shell command inside the
  worktree. Used for verification (``just test``, ``pnpm storybook:build``)
  with an ``on_failure`` policy.

Workflows live in ``tools/prd-harness/workflows/<name>/workflow.py`` modules
that export a top-level ``workflow`` attribute. The loader discovers them
and the runner dispatches each task in order against an
:class:`ExecutionContext` that threads mutable state (worktree path, branch
name, agent output, PR URL, etc.) between tasks.

This module intentionally contains no I/O, no subprocess calls, and no
dependency on ``prd.py`` at import time. It's pure data — the shapes that
workflow authors and the runner both plug into.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

if TYPE_CHECKING:
    from .prd import PRD


# ---------- type aliases ----------


OnFailure = Literal["fail", "retry_agent", "ignore"]
"""Policy for a :class:`ShellTask` when the command exits non-zero.

- ``"fail"``: abort the workflow with an error (default).
- ``"retry_agent"``: re-invoke the preceding :class:`AgentTask` once with
  the verify prompts and the failed check output, then retry the shell
  task once. If it still fails, abort.
- ``"ignore"``: log the failure and continue with the next task. Useful
  for advisory checks that shouldn't block progress.
"""


Status = Literal[
    "draft", "ready", "in-progress", "review", "done", "blocked", "cancelled"
]
"""All PRD lifecycle statuses. Mirrors the enum in ``docs/prd/_schema.yaml``."""


AppliesToPredicate = Callable[["PRD", dict[str, "PRD"]], bool]
"""Two-argument predicate deciding whether a workflow applies to a PRD.

Takes the target PRD plus the full PRD set so predicates that need
sibling or ancestor context (e.g. ``planning`` checking
``is_fully_decomposed``) can reach for it. Simple predicates like
``lambda prd, prds: "ui" in prd.tags`` ignore the second argument.
"""


# ---------- Task hierarchy ----------


class Task:
    """Marker base class for all task types.

    Deliberately not a ``@dataclass`` — subclasses define their own fields
    and don't share any, so dataclass inheritance would add complexity with
    no benefit. The class exists purely for ``isinstance()`` dispatch in
    the runner's task loop.
    """


@dataclass
class BuiltIn(Task):
    """Reference a deterministic primitive from the ``BUILTINS`` registry.

    The runner looks up ``name`` in ``prd_harness.builtins.BUILTINS`` and
    calls the registered function with ``(ctx, **kwargs)``. String values
    in ``kwargs`` are formatted via :meth:`ExecutionContext.format_string`
    before the call, so workflow authors can use ``{prd_id}``-style
    placeholders.

    Example::

        BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"})

    The runner resolves ``{prd_id}`` at execution time; the workflow
    definition stays free of runtime state.
    """

    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask(Task):
    """Invoke Claude Code with composed prompts and a restricted tool allowlist.

    The runner (see ``runner.py``) performs these steps:

    1. Read each path in :attr:`prompts` relative to the workflow's
       directory (set by the loader) and concatenate the file contents.
    2. Substitute ``{{PRD_ID}}``/``{{PRD_TITLE}}``/``{{PRD_PATH}}``/etc.
       placeholders against the :class:`ExecutionContext` via
       ``templates.substitute_placeholders``.
    3. Pick a model: :attr:`model` if explicitly set, else map from
       ``ctx.prd.capability`` when :attr:`model_from_capability` is
       true, else fall back to sonnet.
    4. Pipe the composed prompt to ``claude --print`` via subprocess with
       ``--allowed-tools`` set to :attr:`tools`.
    5. Parse stdout for :attr:`sentinel_success` or :attr:`sentinel_failure`
       to decide whether the task succeeded. The agent is contracted to
       emit one of these as its final line.

    When a subsequent :class:`ShellTask` fails with
    ``on_failure="retry_agent"``, the runner re-invokes this AgentTask
    with :attr:`verify_prompts` prepended to the prompt list and
    ``{{CHECK_OUTPUT}}`` bound to the failed stdout/stderr — at most
    :attr:`retries` times.
    """

    name: str = "implement"
    prompts: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    model_from_capability: bool = True
    retries: int = 1
    verify_prompts: list[str] = field(default_factory=list)
    sentinel_success: str = "PRD_EXECUTE_OK"
    sentinel_failure: str = "PRD_EXECUTE_FAILED"


@dataclass
class ShellTask(Task):
    """Run a deterministic shell command inside the worktree.

    ``cmd`` is formatted via :meth:`ExecutionContext.format_string` before
    execution (so ``{worktree}`` etc. placeholders are expanded) and runs
    with ``cwd=ctx.cwd`` (the worktree path after ``ensure_worktree``).
    ``env`` is merged into the subprocess environment.

    :attr:`on_failure` controls the recovery path on non-zero exit. See
    the :data:`OnFailure` type alias for policy semantics.
    """

    name: str
    cmd: str
    on_failure: OnFailure = "fail"
    env: dict[str, str] = field(default_factory=dict)


# ---------- Workflow ----------


def _default_applies_to(prd: "PRD", prds: dict[str, "PRD"]) -> bool:
    """Default ``applies_to`` predicate — matches nothing.

    Concrete workflows override this in their ``workflow.py`` module.
    Kept as a module-level function rather than a lambda so mypy and
    pickling (if ever needed) both behave.
    """
    return False


@dataclass
class Workflow:
    """A named recipe for implementing one kind of PRD.

    Authored in ``tools/prd-harness/workflows/<name>/workflow.py`` as a
    module-level ``workflow = Workflow(...)`` attribute. The loader
    discovers it, imports the module, and sets :attr:`workflow_dir` to
    the subdirectory path so AgentTask prompt paths resolve correctly.

    :attr:`priority` orders workflows during assignment: higher numbers
    win when multiple predicates match. ``default`` has priority 0 and
    acts as a catchall. Ties are broken alphabetically by name.
    """

    name: str
    description: str = ""
    applies_to: AppliesToPredicate = field(default=_default_applies_to)
    priority: int = 0
    tasks: list[Task] = field(default_factory=list)
    workflow_dir: Path | None = None


# ---------- ExecutionContext ----------


@dataclass
class ExecutionContext:
    """State threaded through every task during a workflow run.

    Tasks mutate this object in place as the workflow progresses:

    - ``ensure_worktree`` sets :attr:`worktree_path` and :attr:`cwd`
    - The agent invoke populates :attr:`agent_output` and
      :attr:`agent_success`
    - ``create_pr`` sets :attr:`pr_url`

    The runner creates one context at the start of ``run_workflow`` and
    passes it to each task in order. Tasks read from it (for formatting
    commit messages, composing prompts, etc.) and write to it (to record
    side effects for downstream tasks or the CLI to surface).

    :attr:`dry_run` tells builtins, shell tasks, and the agent invoke to
    log what they WOULD do without actually invoking subprocesses, git,
    or gh. Drives the ``prd plan`` output.
    """

    prd: "PRD"
    repo_root: Path
    workflow: Workflow
    base_ref: str
    branch_name: str
    worktree_path: Path | None = None
    cwd: Path = field(default_factory=Path.cwd)
    agent_output: str | None = None
    agent_success: bool = False
    pr_url: str | None = None
    dry_run: bool = True
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("prd_harness")
    )

    def format_string(self, template: str) -> str:
        """Expand ``{placeholder}`` tokens against context state.

        Supported placeholders:

        - ``{prd_id}`` — the PRD's id (e.g. ``PRD-070``)
        - ``{prd_title}`` — the PRD's title
        - ``{prd_slug}`` — the slug portion of the PRD filename
        - ``{branch}`` — the current branch name
        - ``{base_ref}`` — the base ref the branch was created from
        - ``{worktree}`` — the worktree path as a string, or ``""`` if
          the worktree hasn't been created yet

        Unknown placeholders raise ``KeyError`` (intentionally strict —
        workflow authors should catch typos early). Contrast with the
        agent prompt templater in ``templates.py``, which leaves unknown
        placeholders unchanged to allow incremental template evolution.
        """
        return template.format(
            prd_id=self.prd.id,
            prd_title=self.prd.title,
            prd_slug=self.prd.slug,
            branch=self.branch_name,
            base_ref=self.base_ref,
            worktree=str(self.worktree_path) if self.worktree_path else "",
        )
