"""Discuss operation definition — the Workflow for ``prd discuss``."""

from __future__ import annotations

from darkfactory.workflow import BuiltIn, InteractiveTask, Workflow

discuss_operation = Workflow(
    name="discuss",
    description="Interactive PRD discussion chain — gather, discuss, critique, commit.",
    tasks=[
        BuiltIn("gather_prd_context"),
        # Discussion phases use Claude Code's highest adaptive-reasoning
        # budget — refinement and critique are reasoning-heavy tasks where
        # more deliberation directly improves output quality. ``max`` is
        # Opus 4.6 only, so discuss sessions run on Opus.
        InteractiveTask(
            name="discuss",
            prompt_file="prompts/discuss.md",
            effort_level="max",
        ),
        InteractiveTask(
            name="critique",
            prompt_file="prompts/critique.md",
            effort_level="max",
        ),
        BuiltIn(
            "commit_prd_changes",
            kwargs={
                "message": "docs(prd): {target_prd} discuss session refinements",
            },
        ),
    ],
)
