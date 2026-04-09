"""audit-impacts system operation.

Walk all PRDs, check that each declared impact path exists on disk.
Reports missing paths — catches PRD-vs-repo drift.
"""

from darkfactory.system import SystemOperation
from darkfactory.workflow import BuiltIn

operation = SystemOperation(
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
