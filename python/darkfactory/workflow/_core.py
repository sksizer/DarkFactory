"""Declarative workflow definitions for the PRD harness.

A ``Workflow`` is a named, ordered list of ``Task`` s that implement one
kind of PRD or project operation. Three task types compose a workflow:

- :class:`BuiltIn` — reference a deterministic primitive by name. The
  set is fixed by the harness package (``builtins.py``): ``ensure_worktree``,
  ``set_status``, ``commit``, ``push_branch``, ``create_pr``, etc.
- :class:`AgentTask` — invoke Claude Code with composed prompts, a tool
  allowlist, and a model selection. This is the only task type where
  actual code gets written.
- :class:`ShellTask` — run a deterministic shell command inside the
  worktree. Used for verification (``just test``, ``pnpm storybook:build``)
  with an ``on_failure`` policy.

Workflows live in ``workflow/definitions/<type>/<name>/workflow.py`` modules
that export a top-level ``workflow`` attribute. The loader discovers them
and the runner dispatches each task in order against a
:class:`RunContext` that threads immutable PhaseState payloads between tasks.

This module intentionally contains no I/O, no subprocess calls, and no
dependency on ``prd.py`` at import time. It's pure data — the shapes that
workflow authors and the runner both plug into.
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

from ..engine import PhaseState
from ..engine.payloads import (
    CodeEnv,
    PrdWorkflowRun,
    ProjectRun,
    WorktreeState,
)
from ..utils.claude_code import EffortLevel

if TYPE_CHECKING:
    from filelock import FileLock

    from ..event_log import EventWriter
    from ..model import PRD


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
    "draft",
    "ready",
    "in-progress",
    "review",
    "done",
    "blocked",
    "cancelled",
    "superseded",
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

    name: str


@dataclass
class BuiltIn(Task):
    """Reference a deterministic primitive from the ``BUILTINS`` registry.

    The runner looks up ``name`` in the builtin registry and calls the
    registered function with ``(ctx, **kwargs)``. String values in
    ``kwargs`` are formatted via :meth:`RunContext.format_string` before
    the call, so workflow authors can use ``{prd_id}``-style placeholders.

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
       placeholders against the :class:`RunContext` via
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
    effort_level: EffortLevel | None = None


@dataclass
class ShellTask(Task):
    """Run a deterministic shell command inside the worktree.

    ``cmd`` is formatted via :meth:`RunContext.format_string` before
    execution (so ``{worktree}`` etc. placeholders are expanded) and runs
    with ``cwd`` from ``CodeEnv`` (the worktree path after ``ensure_worktree``).
    ``env`` is merged into the subprocess environment.

    :attr:`on_failure` controls the recovery path on non-zero exit. See
    the :data:`OnFailure` type alias for policy semantics.
    """

    name: str
    cmd: str
    on_failure: OnFailure = "fail"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class InteractiveTask(Task):
    """Launch an interactive Claude Code session that takes over the terminal.

    Unlike :class:`AgentTask` (headless, sentinel-parsed), an
    ``InteractiveTask`` calls :func:`~darkfactory.utils.claude_code.spawn_claude`
    which hands the terminal to the user. Used for discussion and
    critique phases where the agent and human collaborate interactively.
    """

    name: str = "interactive"
    prompt_file: str = ""
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    effort_level: EffortLevel | None = None


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
    """A named recipe for implementing one kind of PRD or project operation.

    Authored in ``workflow/definitions/<type>/<name>/workflow.py`` as a
    module-level ``workflow = Workflow(...)`` attribute. The loader
    discovers it, imports the module, and sets :attr:`workflow_dir` to
    the subdirectory path so AgentTask prompt paths resolve correctly.

    :attr:`priority` orders workflows during assignment: higher numbers
    win when multiple predicates match. ``default`` has priority 0 and
    acts as a catchall. Ties are broken alphabetically by name.

    Routing fields (:attr:`applies_to`, :attr:`priority`) are only used
    by PRD workflows. Project workflows ignore them.
    """

    name: str
    description: str = ""
    applies_to: AppliesToPredicate = field(default=_default_applies_to)
    priority: int = 0
    tasks: list[Task] = field(default_factory=list)
    workflow_dir: Path | None = None
    template_name: str | None = None


# ---------- RunContext ----------


@dataclass
class RunContext:
    """Unified context threaded through every task during a workflow run.

    Immutable harness concerns live here. All execution state lives in
    frozen PhaseState payloads, replaced (not mutated) as the run
    progresses. The one mutable field is :attr:`report`, an accumulator
    for project operations that build up output during execution.

    :attr:`dry_run` tells builtins, shell tasks, and the agent invoke to
    log what they WOULD do without actually invoking subprocesses, git,
    or gh.
    """

    dry_run: bool = True
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("darkfactory")
    )
    state: PhaseState = field(default_factory=PhaseState)
    event_writer: "EventWriter | None" = None
    report: list[str] = field(default_factory=list)
    _worktree_lock: "FileLock | None" = field(default=None, repr=False)

    @property
    def cwd(self) -> Path:
        """Current working directory from CodeEnv payload."""
        return self.state.get(CodeEnv).cwd

    @property
    def repo_root(self) -> Path:
        """Repository root from CodeEnv payload."""
        return self.state.get(CodeEnv).repo_root

    def format_string(self, template: str, *, shell_escape: bool = False) -> str:
        """Expand ``{placeholder}`` tokens against all payloads in state.

        Merges placeholders from all payloads present in state. No
        payload shares a placeholder name with another — each piece of
        data lives in exactly one payload type. Unknown placeholders
        pass through unchanged.

        Resolves from:
        - CodeEnv: ``{cwd}``, ``{repo_root}``
        - PrdWorkflowRun if present: ``{prd_id}``, ``{prd_title}``, ``{prd_slug}``
        - ProjectRun if present: ``{workflow_name}``, ``{target_count}``,
          ``{target_prd}``
        - WorktreeState if present: ``{branch}``, ``{base_ref}``, ``{worktree}``

        Args:
            template: The template string with ``{placeholder}`` tokens.
            shell_escape: When ``True``, each substituted value is passed
                through :func:`shlex.quote` before insertion.  Set this
                whenever the result will be executed by a shell (i.e. via
                ``run_shell``), so that PRD-controlled values cannot inject
                arbitrary shell commands.
        """
        replacements: dict[str, str] = {}

        if self.state.has(CodeEnv):
            env = self.state.get(CodeEnv)
            replacements["cwd"] = str(env.cwd)
            replacements["repo_root"] = str(env.repo_root)

        if self.state.has(PrdWorkflowRun):
            run = self.state.get(PrdWorkflowRun)
            replacements["prd_id"] = run.prd.id
            replacements["prd_title"] = run.prd.title
            replacements["prd_slug"] = run.prd.slug

        if self.state.has(ProjectRun):
            proj = self.state.get(ProjectRun)
            replacements["workflow_name"] = proj.workflow.name
            replacements["target_count"] = str(len(proj.targets))
            replacements["target_prd"] = proj.target_prd or ""

        if self.state.has(WorktreeState):
            wt = self.state.get(WorktreeState)
            replacements["branch"] = wt.branch
            replacements["base_ref"] = wt.base_ref
            replacements["worktree"] = str(wt.worktree_path) if wt.worktree_path else ""

        if shell_escape:
            replacements = {k: shlex.quote(v) for k, v in replacements.items()}

        # Replace known placeholders, leave unknown ones unchanged.
        result = template
        for key, value in replacements.items():
            result = result.replace("{" + key + "}", value)
        return result
