"""verify-merges system operation.

Audit all merged PRs and verify their merge commits are ancestors of main.
Detects silent code loss from branch merges that didn't actually integrate
into the mainline (e.g. stale branches overwriting concurrent work).
"""

from darkfactory.system import SystemOperation
from darkfactory.workflow import ShellTask

operation = SystemOperation(
    name="verify-merges",
    description=(
        "Audit all merged PRs to verify their merge commits are ancestors "
        "of main. Detects silent code loss from improperly integrated merges."
    ),
    creates_pr=False,
    requires_clean_main=False,
    tasks=[
        ShellTask(
            name="verify-merge-ancestry",
            cmd="python .darkfactory/operations/verify-merges/check.py",
        ),
    ],
)
