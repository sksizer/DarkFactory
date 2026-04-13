"""verify-merges project workflow.

Audit all merged PRs and verify their merge commits are ancestors of main.
Detects silent code loss from branch merges that didn't actually integrate
into the mainline (e.g. stale branches overwriting concurrent work).
"""

from pathlib import Path

from darkfactory.workflow import ShellTask, Workflow

_CHECK_SCRIPT = str(Path(__file__).resolve().parent / "check.py")

workflow = Workflow(
    name="verify-merges",
    description=(
        "Audit all merged PRs to verify their merge commits are ancestors "
        "of main. Detects silent code loss from improperly integrated merges."
    ),
    tasks=[
        ShellTask(
            name="verify-merge-ancestry",
            cmd=f"python {_CHECK_SCRIPT}",
        ),
    ],
)
