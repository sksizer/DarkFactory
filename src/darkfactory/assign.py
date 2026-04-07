"""Workflow assignment logic.

Given a PRD and a set of loaded workflows, decide which workflow should
run for it. The resolution priority is:

1. **Explicit frontmatter field**: if ``prd.workflow`` is set and names
   a loaded workflow, return it unconditionally. This lets authors
   pin a specific workflow to a specific PRD, overriding any predicate
   matching.
2. **applies_to predicates**: otherwise, evaluate every workflow's
   :attr:`~darkfactory.workflow.Workflow.applies_to` predicate and pick
   the highest-priority workflow that returns truthy. Ties are broken
   alphabetically by workflow name for determinism.
3. **Default fallback**: if no predicate matches, return the
   ``default`` workflow. If there's no default either, raise
   ``KeyError``.

The two-argument ``applies_to(prd, prds)`` signature is preferred, but
single-arg legacy lambdas (``lambda prd: ...``) are tolerated via a
``TypeError`` fallback — workflows authored before the signature
expansion keep working.

``assign_all`` is a convenience for bulk resolution across a whole PRD
set, used by the ``prd assign`` CLI subcommand.
"""

from __future__ import annotations

from typing import Any

from .prd import PRD
from .workflow import Workflow


def assign_workflow(
    prd: PRD,
    prds: dict[str, PRD],
    workflows: dict[str, Workflow],
) -> Workflow:
    """Resolve the workflow for a single PRD.

    See the module docstring for resolution priority. Raises ``KeyError``
    only if no workflow matches *and* there's no ``default`` workflow in
    the set — which is a misconfiguration the caller should catch and
    surface (missing default workflow is a deployment problem, not a
    per-PRD problem).
    """
    # 1. Explicit frontmatter field wins.
    if prd.workflow and prd.workflow in workflows:
        return workflows[prd.workflow]

    # 2. Predicate match by priority, alphabetical tie-break for determinism.
    matches = [w for w in workflows.values() if _matches(w, prd, prds)]
    if matches:
        matches.sort(key=lambda w: (-w.priority, w.name))
        return matches[0]

    # 3. Fall back to default.
    if "default" in workflows:
        return workflows["default"]

    raise KeyError(
        f"no workflow matches {prd.id!r} and no 'default' workflow is registered"
    )


def assign_all(
    prds: dict[str, PRD],
    workflows: dict[str, Workflow],
) -> dict[str, Workflow]:
    """Resolve workflow assignments for every PRD in ``prds``.

    Returns a dict keyed by PRD id. Used by ``prd assign`` to dump the
    full assignment table and optionally persist it to frontmatter via
    ``--write``. Propagates ``KeyError`` from :func:`assign_workflow` if
    any single PRD has no match and there's no default.
    """
    return {prd_id: assign_workflow(prd, prds, workflows) for prd_id, prd in prds.items()}


def _matches(workflow: Workflow, prd: PRD, prds: dict[str, PRD]) -> bool:
    """Call ``workflow.applies_to`` tolerating 1-arg and 2-arg signatures.

    The canonical signature is ``(prd, prds) -> bool`` — passing the full
    PRD set lets predicates reach for parent/sibling context. Older
    workflows written with ``(prd) -> bool`` still work: we try the
    two-argument form first, catch ``TypeError``, and retry with one arg.

    Errors inside the predicate itself (not argument-count errors) are
    allowed to propagate so the caller can see the real failure.
    """
    try:
        return bool(workflow.applies_to(prd, prds))
    except TypeError:
        # Too-few-arguments TypeError path: retry with single arg.
        # The declared type is 2-arg; the 1-arg call is deliberately
        # off-type to support legacy workflow lambdas.
        try:
            legacy_predicate: Any = workflow.applies_to
            return bool(legacy_predicate(prd))
        except TypeError:
            # Still failing — re-raise the original problem for the caller.
            raise
