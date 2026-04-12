"""audit-impacts project operation.

Walk all PRDs, check that each declared impact path exists on disk.
Reports missing paths — catches PRD-vs-repo drift.
"""

from darkfactory.project import ProjectOperation
from darkfactory.workflow import BuiltIn

operation = ProjectOperation(
    name="audit-impacts",
    description=(
        "Walk all PRDs, check that declared impact paths exist on disk. "
        "Reports missing paths — catches PRD-vs-repo drift."
    ),
    creates_pr=False,
    requires_clean_main=False,
    tasks=[
        BuiltIn("audit_impacts_check"),
    ],
)
