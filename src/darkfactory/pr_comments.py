"""Fetch and filter unaddressed PR review comments via the gh CLI.

This module provides ``fetch_pr_comments`` which shells out to ``gh pr view``
to retrieve review threads, then applies configurable filters before returning
structured ``ReviewThread`` dataclasses suitable for composing into a feedback
prompt.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewComment:
    author: str
    body: str
    posted_at: str


@dataclass
class ReviewThread:
    thread_id: str
    author: str
    path: str | None  # None for issue-level comments
    line: int | None  # None for issue-level comments
    body: str
    posted_at: str
    is_resolved: bool
    replies: list[ReviewComment]
    review_state: str | None  # "CHANGES_REQUESTED", "APPROVED", etc.


@dataclass
class CommentFilters:
    include_resolved: bool = False
    since_commit: str | None = None
    reviewer: str | None = None
    single_comment_id: str | None = None
    bot_usernames: list[str] = field(default_factory=list)


def fetch_pr_comments(
    pr_number: int,
    filters: CommentFilters | None = None,
) -> list[ReviewThread]:
    """Fetch and filter PR review threads from GitHub.

    Shells out to ``gh pr view <pr_number> --json comments,reviews,reviewThreads``
    and returns a list of ``ReviewThread`` objects matching the given filters.
    """
    raw = _gh_fetch(pr_number)
    threads = _parse_threads(raw)
    return _apply_filters(threads, filters or CommentFilters())


def _gh_fetch(pr_number: int) -> dict[str, Any]:
    """Run gh pr view and return parsed JSON."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "comments,reviews,reviewThreads",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def _parse_threads(raw: dict[str, Any]) -> list[ReviewThread]:
    """Parse gh JSON into ReviewThread objects.

    ``gh pr view`` returns three keys:

    - ``reviewThreads``: inline line-anchored comment threads (each thread
      has ``comments``, ``isResolved``, ``path``, ``line``)
    - ``reviews``: per-reviewer summaries (body + state, no line anchor)
    - ``comments``: issue-level PR comments (no line anchor)

    We normalise all three into ``ReviewThread`` objects with a consistent
    shape so callers don't need to care about the source.
    """
    threads: list[ReviewThread] = []

    # 1. Inline review threads (line-anchored)
    for idx, rt in enumerate(raw.get("reviewThreads") or []):
        comments = rt.get("comments") or []
        if not comments:
            continue
        first = comments[0]
        author = (first.get("author") or {}).get("login") or ""
        body = first.get("body") or ""
        posted_at = first.get("createdAt") or ""
        path = rt.get("path") or None
        line = rt.get("line") or rt.get("originalLine") or None
        is_resolved = bool(rt.get("isResolved"))

        replies: list[ReviewComment] = []
        for c in comments[1:]:
            reply_author = (c.get("author") or {}).get("login") or ""
            replies.append(
                ReviewComment(
                    author=reply_author,
                    body=c.get("body") or "",
                    posted_at=c.get("createdAt") or "",
                )
            )

        thread_id = first.get("id") or f"rt-{idx}"
        threads.append(
            ReviewThread(
                thread_id=thread_id,
                author=author,
                path=path,
                line=line,
                body=body,
                posted_at=posted_at,
                is_resolved=is_resolved,
                replies=replies,
                review_state=None,
            )
        )

    # 2. Review summaries (per-reviewer body + state, no line anchor)
    for idx, rev in enumerate(raw.get("reviews") or []):
        body = rev.get("body") or ""
        if not body.strip():
            # Skip empty review summaries (just approvals with no comment)
            continue
        author = (rev.get("author") or {}).get("login") or ""
        posted_at = rev.get("submittedAt") or ""
        state = rev.get("state") or None
        thread_id = rev.get("id") or f"review-{idx}"
        threads.append(
            ReviewThread(
                thread_id=thread_id,
                author=author,
                path=None,
                line=None,
                body=body,
                posted_at=posted_at,
                is_resolved=False,  # review summaries don't have a resolved flag
                replies=[],
                review_state=state,
            )
        )

    # 3. Issue-level PR comments
    for idx, c in enumerate(raw.get("comments") or []):
        body = c.get("body") or ""
        author = (c.get("author") or {}).get("login") or ""
        posted_at = c.get("createdAt") or ""
        thread_id = c.get("id") or f"comment-{idx}"
        threads.append(
            ReviewThread(
                thread_id=thread_id,
                author=author,
                path=None,
                line=None,
                body=body,
                posted_at=posted_at,
                is_resolved=False,
                replies=[],
                review_state=None,
            )
        )

    return threads


def _resolve_commit_timestamp(commit: str) -> str:
    """Resolve a commit SHA or ref to an ISO-8601 author timestamp."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%aI", commit],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _is_bot_comment(author: str, body: str, bot_usernames: list[str]) -> bool:
    """Return True if the comment was authored by the harness bot."""
    if author in bot_usernames:
        return True
    if body.lstrip().startswith("[harness]"):
        return True
    return False


def _apply_filters(
    threads: list[ReviewThread],
    filters: CommentFilters,
) -> list[ReviewThread]:
    """Apply filtering rules to threads.

    Filters applied in order:

    1. ``single_comment_id`` — return exactly the thread with that ID, or []
    2. ``include_resolved`` — exclude resolved threads unless True
    3. ``reviewer`` — keep only threads from the specified author
    4. ``bot_usernames`` — drop comments authored by the bot
    5. ``since_commit`` — drop threads posted before the commit timestamp
    """
    # 1. Single comment shortcut
    if filters.single_comment_id is not None:
        return [t for t in threads if t.thread_id == filters.single_comment_id]

    result = list(threads)

    # 2. Resolved filter
    if not filters.include_resolved:
        result = [t for t in result if not t.is_resolved]

    # 3. Reviewer filter
    if filters.reviewer is not None:
        result = [t for t in result if t.author == filters.reviewer]

    # 4. Bot filter
    if filters.bot_usernames:
        result = [
            t
            for t in result
            if not _is_bot_comment(t.author, t.body, filters.bot_usernames)
        ]

    # 5. Since-commit filter
    if filters.since_commit is not None:
        cutoff = _resolve_commit_timestamp(filters.since_commit)
        result = [t for t in result if t.posted_at >= cutoff]

    return result
