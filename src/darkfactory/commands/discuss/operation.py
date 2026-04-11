"""Discuss operation definition — the SystemOperation for ``prd discuss``."""

from __future__ import annotations

from darkfactory.system import SystemOperation
from darkfactory.workflow import BuiltIn

discuss_operation = SystemOperation(
    name="discuss",
    description="Interactive PRD discussion chain — gather, discuss, critique, commit.",
    requires_clean_main=False,
    creates_pr=False,
    accepts_target=True,
    tasks=[
        BuiltIn("gather_prd_context"),
        BuiltIn(
            "discuss_prd",
            kwargs={
                "phase": "discuss",
                "prompt_file": "prompts/discuss.md",
            },
        ),
        BuiltIn(
            "discuss_prd",
            kwargs={
                "phase": "critique",
                "prompt_file": "prompts/critique.md",
            },
        ),
        BuiltIn(
            "commit_prd_changes",
            kwargs={
                "message": "docs(prd): {target_prd} discuss session refinements",
            },
        ),
    ],
)
