"""verify-merges project operation.

Audit all merged PRs and verify their merge commits are ancestors of main.
Detects silent code loss from branch merges that didn't actually integrate
into the mainline (e.g. stale branches overwriting concurrent work).
"""

from pathlib import Path

from darkfactory.project import ProjectOperation
from darkfactory.workflow import ShellTask

_CHECK_SCRIPT = str(Path(__file__).resolve().parent / "check.py")

operation = ProjectOperation(
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
            cmd=f"python {_CHECK_SCRIPT}",
        ),
    ],
)
