"""Render ReviewThread objects into a structured markdown feedback section.

The ``render_rework_feedback`` function converts a list of
:class:`~darkfactory.pr_comments.ReviewThread` objects into the markdown
section that gets inserted as ``{{REWORK_FEEDBACK}}`` in the rework
``task.md`` template via :func:`~darkfactory.templates.compose_prompt`.

The output format mirrors the ``workflows/rework/prompts/rework-feedback.md``
template.  Each thread becomes a heading with author and optional file
location, followed by the comment body, optional thread replies, and a
horizontal rule separator.
"""

from __future__ import annotations

from .pr_comments import ReviewThread


def render_rework_feedback(threads: list[ReviewThread]) -> str:
    """Render a list of review threads into a markdown feedback section.

    Returns a human-readable markdown string suitable for insertion as
    ``{{REWORK_FEEDBACK}}`` in the rework task prompt.

    An empty ``threads`` list returns a sentinel message so the agent is
    not left with a blank section.
    """
    if not threads:
        return "No feedback to address."

    parts: list[str] = []
    for thread in threads:
        header = f"### Comment by {thread.author}"
        if thread.path:
            header += f" on `{thread.path}`"
            if thread.line is not None:
                header += f":{thread.line}"
        parts.append(header)
        parts.append("")
        body_quoted = "\n".join(f"> {line}" for line in thread.body.splitlines())
        parts.append(body_quoted)

        if thread.replies:
            parts.append("")
            parts.append("**Thread replies:**")
            for reply in thread.replies:
                reply_quoted = "\n".join(
                    f"> {line}" for line in f"**{reply.author}:** {reply.body}".splitlines()
                )
                parts.append(reply_quoted)

        parts.append("")
        parts.append("---")

    return "\n".join(parts)
