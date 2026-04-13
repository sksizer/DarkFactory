"""audit-impacts project workflow.

Walk all PRDs, check that each declared impact path exists on disk.
Reports missing paths — catches PRD-vs-repo drift.
"""

from darkfactory.workflow import BuiltIn, Workflow

workflow = Workflow(
    name="audit-impacts",
    description=(
        "Walk all PRDs, check that declared impact paths exist on disk. "
        "Reports missing paths — catches PRD-vs-repo drift."
    ),
    tasks=[
        BuiltIn("audit_impacts_check"),
    ],
)
