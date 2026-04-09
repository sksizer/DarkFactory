"""Prompt file loading, variable substitution, and WorkflowTemplate abstraction.

When the runner executes an :class:`~darkfactory.workflow.AgentTask`,
it needs to build the prompt the Claude Code subprocess will receive.
That involves three steps:

1. **Load** each file listed in ``AgentTask.prompts``, resolved
   relative to the workflow's directory.
2. **Concatenate** them with blank-line separators, preserving order.
3. **Substitute** ``{{PLACEHOLDER}}``-style tokens with values from
   the current :class:`~darkfactory.workflow.ExecutionContext`.

The placeholder syntax (``{{UPPERCASE_NAME}}``) is deliberately distinct
from Python's ``str.format`` ``{lowercase}`` style used by
``ExecutionContext.format_string`` — the two templating systems serve
different purposes:

- :meth:`ExecutionContext.format_string` is **strict**: unknown
  placeholders raise ``KeyError``. Used for commit messages and shell
  commands where typos must be caught early.
- :func:`substitute_placeholders` is **permissive**: unknown
  placeholders are left as-is. This lets agent prompts evolve
  incrementally — you can reference ``{{NEW_FIELD}}`` in a prompt
  before the context learns how to populate it, and the prompt still
  renders without exploding.

The split also prevents accidental collisions between Python format
strings in Bash commands and agent-prompt placeholders.

:class:`WorkflowTemplate` is the foundational primitive for PRD-227
workflow templates. A template defines required opening tasks, a
constrained middle slot, and required closing tasks. ``.compose()``
concatenates ``[*open, *middle, *close]`` into a :class:`Workflow`,
validating the middle against ``middle_kinds`` and ``middle_required``
constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .workflow import BuiltIn, Workflow

if TYPE_CHECKING:
    from .workflow import ExecutionContext


PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
"""Matches ``{{NAME}}`` tokens in prompt templates.

The captured group is the placeholder name (alphanumeric + underscore).
Non-matching sequences pass through unchanged, so literal ``{{ }}`` in
documentation or code blocks inside prompts survive the substitution.
"""


def load_prompt_files(workflow_dir: Path, paths: list[str]) -> str:
    """Read and concatenate prompt files from a workflow directory.

    Each path in ``paths`` is resolved relative to ``workflow_dir`` and
    read as UTF-8. Results are joined with ``"\\n\\n"`` separators so the
    agent sees them as distinct sections rather than one run-on prompt.

    Raises ``FileNotFoundError`` with the workflow directory in the
    message if any path doesn't resolve — typos in ``AgentTask.prompts``
    should fail loudly at runtime, not silently produce empty prompts.
    """
    parts: list[str] = []
    for path in paths:
        full = workflow_dir / path
        if not full.exists():
            raise FileNotFoundError(
                f"prompt file not found in workflow {workflow_dir.name!r}: {path} "
                f"(looked in {full})"
            )
        parts.append(full.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def substitute_placeholders(template: str, context: Mapping[str, object]) -> str:
    """Replace ``{{NAME}}`` tokens in ``template`` using ``context``.

    Unknown placeholders (names not in ``context``) are left unchanged.
    This is intentional — it lets prompt authors reference future
    placeholders without breaking the current rendering, and it means a
    ``{{CHECK_OUTPUT}}`` reference in verify.md stays literal during
    the initial rendering pass (when no check has failed yet) and gets
    substituted only on retry.

    Values are coerced to ``str`` via ``str()``, so integers, paths,
    and dataclass reprs all work without caller ceremony.
    """

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        return match.group(0)  # leave unchanged

    return PLACEHOLDER_RE.sub(replace, template)


def compose_prompt(
    workflow: Workflow,
    prompts: list[str],
    execution_context: ExecutionContext,
    extras: Mapping[str, object] | None = None,
) -> str:
    """End-to-end: load prompt files and substitute context placeholders.

    The standard placeholder set populated from the ExecutionContext:

    - ``{{PRD_ID}}`` — the PRD's id
    - ``{{PRD_TITLE}}`` — the PRD's title
    - ``{{PRD_PATH}}`` — absolute path to the PRD file
    - ``{{PRD_SLUG}}`` — the slug portion of the PRD filename
    - ``{{BRANCH_NAME}}`` — the current branch name
    - ``{{BASE_REF}}`` — the base ref the branch was created from
    - ``{{WORKTREE_PATH}}`` — the worktree path (or empty string if unset)

    ``extras`` is merged into the context after the standard keys, so
    callers can inject ad-hoc values (e.g. ``CHECK_OUTPUT`` for retry
    prompts) without modifying the ExecutionContext.

    Raises ``ValueError`` if the workflow has no ``workflow_dir`` set
    (shouldn't happen in practice — the loader sets it — but makes the
    failure explicit if someone constructs a Workflow by hand).
    """
    if workflow.workflow_dir is None:
        raise ValueError(
            f"workflow {workflow.name!r} has no workflow_dir; "
            "the loader normally sets this at import time"
        )

    raw = load_prompt_files(workflow.workflow_dir, prompts)

    prd = execution_context.prd
    context: dict[str, object] = {
        "PRD_ID": prd.id,
        "PRD_TITLE": prd.title,
        "PRD_PATH": str(prd.path),
        "PRD_SLUG": prd.slug,
        "BRANCH_NAME": execution_context.branch_name,
        "BASE_REF": execution_context.base_ref,
        "WORKTREE_PATH": (
            str(execution_context.worktree_path)
            if execution_context.worktree_path
            else ""
        ),
    }
    if extras:
        context.update(extras)

    return substitute_placeholders(raw, context)


# ---------- WorkflowTemplate ----------


class TemplateViolation(Exception):
    """Raised when a composed middle violates the template's constraints."""


@dataclass(frozen=True)
class WorkflowTemplate:
    """A reusable recipe that stamps out :class:`Workflow` instances.

    A template defines:

    - Required **opening** tasks that always run first (``open``).
    - A constrained **middle** slot for caller-supplied tasks.
    - Required **closing** tasks that always run last (``close``).

    :meth:`compose` validates the caller's middle tasks against
    ``middle_kinds`` and ``middle_required``, then returns a
    :class:`Workflow` whose task list is ``[*open, *middle, *close]``
    with ``template_name`` set to this template's ``name``.
    """

    name: str
    description: str
    open: list[BuiltIn]
    close: list[BuiltIn]
    middle_kinds: list[type] = field(default_factory=list)
    middle_required: dict[type, tuple[int, int | None]] = field(default_factory=dict)

    def compose(
        self,
        name: str,
        description: str,
        applies_to: Callable[..., bool],
        priority: int,
        middle: list[Any],
    ) -> Workflow:
        """Validate ``middle`` and return a complete :class:`Workflow`.

        Parameters match :class:`Workflow` constructor arguments for the
        caller-supplied fields. ``tasks`` and ``template_name`` are set
        by this method.

        Raises :class:`TemplateViolation` if any task in ``middle`` is
        not an instance of one of ``middle_kinds``, or if the count of
        any required kind falls outside the ``middle_required`` bounds.
        """
        self._validate_middle(middle)
        return Workflow(
            name=name,
            description=description,
            applies_to=applies_to,
            priority=priority,
            tasks=[*self.open, *middle, *self.close],
            template_name=self.name,
        )

    def _validate_middle(self, middle: list[Any]) -> None:
        if self.middle_kinds:
            for task in middle:
                if not isinstance(task, tuple(self.middle_kinds)):
                    raise TemplateViolation(
                        f"Task {task!r} is not an allowed middle kind "
                        f"(allowed: {[k.__name__ for k in self.middle_kinds]})"
                    )
        for kind, (min_count, max_count) in self.middle_required.items():
            actual = sum(1 for t in middle if isinstance(t, kind))
            if actual < min_count:
                raise TemplateViolation(
                    f"Template requires at least {min_count} {kind.__name__} "
                    f"in the middle, got {actual}"
                )
            if max_count is not None and actual > max_count:
                raise TemplateViolation(
                    f"Template allows at most {max_count} {kind.__name__} "
                    f"in the middle, got {actual}"
                )
