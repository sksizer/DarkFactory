"""SystemOperation and SystemContext — system-level operation abstractions.

Analogous to :class:`~darkfactory.workflow.Workflow` and
:class:`~darkfactory.workflow.ExecutionContext` but targeting a different
execution shape: no single PRD, optionally read-only, with output that is
either a report or a single batched PR.

This module is pure data — no I/O, no subprocess calls.  Loader logic for
discovering operation modules lives in :func:`~darkfactory.loader.load_operations`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .workflow import Task

if TYPE_CHECKING:
    from .prd import PRD


@dataclass
class SystemOperation:
    """A named system-level operation composed of ordered :class:`Task` s.

    Authored in ``.darkfactory/operations/<name>/operation.py`` modules that
    export a top-level ``operation`` attribute.  The loader discovers them and
    sets :attr:`operation_dir` so relative paths inside tasks resolve correctly.

    Unlike a :class:`~darkfactory.workflow.Workflow`, a ``SystemOperation``
    targets the repository as a whole rather than a single PRD.  It may be
    read-only (no PR) or write a single batched PR that collects many changes.
    """

    name: str
    description: str
    tasks: list[Task]
    requires_clean_main: bool = True
    creates_pr: bool = False
    pr_title: str | None = None
    pr_body: str | None = None
    accepts_target: bool = False
    operation_dir: Path | None = None


@dataclass
class SystemContext:
    """State threaded through every task during a system operation run.

    Analogous to :class:`~darkfactory.workflow.ExecutionContext` but scoped to
    system operations rather than single-PRD workflows.

    :attr:`dry_run` tells builtins and shell tasks to log what they *would* do
    without actually performing side effects.

    :attr:`targets` holds the list of target identifiers passed on the CLI
    (e.g. PRD IDs for bulk operations).

    :attr:`target_prd` is the single PRD ID for operations that
    :attr:`~SystemOperation.accepts_target`.

    :attr:`report` accumulates human-readable output lines produced by tasks
    during the run.

    :attr:`_shared_state` is an escape hatch for tasks that need to pass
    arbitrary data to downstream tasks without adding new typed fields.
    """

    repo_root: Path
    prds: dict[str, "PRD"]
    operation: SystemOperation
    cwd: Path
    dry_run: bool = True
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("darkfactory.system")
    )
    targets: list[str] = field(default_factory=list)
    report: list[str] = field(default_factory=list)
    pr_url: str | None = None
    target_prd: str | None = None
    _shared_state: dict[str, Any] = field(default_factory=dict)

    def format_string(self, template: str) -> str:
        """Expand ``{placeholder}`` tokens against context state.

        Supported placeholders:

        - ``{operation_name}`` — the operation's name
        - ``{target_count}`` — number of entries in :attr:`targets`
        - ``{target_prd}`` — the target PRD ID, or ``""`` if not set

        Unknown placeholders raise ``KeyError`` (intentionally strict).
        """
        return template.format(
            operation_name=self.operation.name,
            target_count=len(self.targets),
            target_prd=self.target_prd or "",
        )
