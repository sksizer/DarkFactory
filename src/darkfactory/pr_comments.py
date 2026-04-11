"""Fetch and filter unaddressed PR review comments via the gh CLI.

This module provides ``fetch_pr_comments`` which shells out to
``gh api graphql`` to retrieve review threads, reviews, and issue comments,
then applies configurable filters before returning structured
``ReviewThread`` dataclasses suitable for composing into a feedback prompt.

It also provides ``post_comment_replies`` for posting bot replies back to
addressed threads, and ``parse_agent_replies`` for extracting structured reply
notes from agent output.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


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
    # Numeric REST id (databaseId, as str) of the comment we can reply to via
    # POST /pulls/{n}/comments/{id}/replies. Populated only for inline review
    # threads — review summaries and issue-level comments have no reply
    # endpoint, so it stays None for those sources.
    reply_target_id: str | None = None


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

    Shells out to ``gh api graphql`` to retrieve ``reviewThreads``,
    ``reviews``, and issue ``comments`` for the given PR, then returns
    a list of ``ReviewThread`` objects matching the given filters.
    """
    raw = _gh_fetch(pr_number)
    threads = _parse_threads(raw)
    return _apply_filters(threads, filters or CommentFilters())


_GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          path
          line
          originalLine
          comments(first: 100) {
            nodes {
              id
              databaseId
              body
              createdAt
              author { login }
            }
          }
        }
      }
      reviews(first: 100) {
        nodes {
          id
          body
          submittedAt
          state
          author { login }
        }
      }
      comments(first: 100) {
        nodes {
          id
          body
          createdAt
          author { login }
        }
      }
    }
  }
}
"""


def _gh_fetch(pr_number: int) -> dict[str, Any]:
    """Fetch PR data via gh GraphQL and reshape into the parser's dict shape.

    ``gh pr view --json`` does not expose ``reviewThreads``, so we use
    the GraphQL API instead. The response is flattened to match the
    shape ``_parse_threads`` expects::

        {"reviewThreads": [...], "reviews": [...], "comments": [...]}
    """
    owner, name = _gh_repo_nwo()
    result = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={pr_number}",
            "-f",
            f"query={_GRAPHQL_QUERY}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    pr = payload["data"]["repository"]["pullRequest"]

    review_threads: list[dict[str, Any]] = []
    for rt in pr["reviewThreads"]["nodes"]:
        review_threads.append(
            {
                "isResolved": rt["isResolved"],
                "path": rt["path"],
                "line": rt["line"],
                "originalLine": rt.get("originalLine"),
                "comments": rt["comments"]["nodes"],
            }
        )

    return {
        "reviewThreads": review_threads,
        "reviews": pr["reviews"]["nodes"],
        "comments": pr["comments"]["nodes"],
    }


def _gh_repo_nwo() -> tuple[str, str]:
    """Return ``(owner, name)`` for the current repo via gh."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=True,
    )
    nwo = result.stdout.strip()
    owner, _, name = nwo.partition("/")
    return owner, name


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
        database_id = first.get("databaseId")
        reply_target_id = str(database_id) if database_id is not None else None
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
                reply_target_id=reply_target_id,
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


@dataclass
class CommentReply:
    """A reply to post on a specific review thread."""

    thread_id: str
    body: str


# Fenced code block marker emitted by the rework agent:
#   ```json-reply-notes
#   [{"thread_id": "...", "note": "..."}]
#   ```
_REPLY_NOTES_RE = re.compile(
    r"```json-reply-notes\s*\n(.*?)\n```",
    re.DOTALL,
)


def parse_agent_replies(agent_output: str) -> list[CommentReply]:
    """Parse structured reply notes from rework agent output.

    The agent is instructed to emit a fenced code block tagged
    ``json-reply-notes`` containing a JSON array of objects with
    ``thread_id`` and ``note`` keys::

        ```json-reply-notes
        [{"thread_id": "IC_abc123", "note": "Addressed: renamed the method."}]
        ```

    Returns a list of :class:`CommentReply` objects.  Malformed or
    missing blocks return an empty list — callers log a warning rather
    than failing.
    """
    match = _REPLY_NOTES_RE.search(agent_output)
    if not match:
        return []

    raw_json = match.group(1).strip()
    try:
        items = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        _log.warning("parse_agent_replies: invalid JSON in reply-notes block: %s", exc)
        return []

    if not isinstance(items, list):
        _log.warning(
            "parse_agent_replies: expected JSON array, got %s", type(items).__name__
        )
        return []

    replies: list[CommentReply] = []
    for item in items:
        if not isinstance(item, dict):
            _log.warning("parse_agent_replies: skipping non-dict item: %r", item)
            continue
        thread_id = item.get("thread_id")
        note = item.get("note")
        if not thread_id or not note:
            _log.warning(
                "parse_agent_replies: skipping item missing thread_id or note: %r",
                item,
            )
            continue
        replies.append(CommentReply(thread_id=str(thread_id), body=str(note)))

    return replies


def post_comment_replies(
    pr_number: int,
    replies: list[CommentReply],
    threads: list[ReviewThread],
    commit_sha: str,
    repo_root: Path,
) -> list[tuple[str, bool]]:
    """Post replies to PR review comment threads.

    For each :class:`CommentReply`, looks up the matching
    :class:`ReviewThread` in ``threads`` by ``thread_id``, resolves its
    numeric ``reply_target_id`` (the REST ``databaseId`` of the first
    comment in the thread), and POSTs a reply via
    ``repos/{owner}/{repo}/pulls/{pr}/comments/{target}/replies``.

    The reply body is prefixed with ``[harness] addressed in {commit_sha}: ``
    so reviewers can easily distinguish bot replies from human ones.

    Returns a list of ``(thread_id, success)`` pairs.  Failures are
    logged as warnings but do not raise — the caller decides whether to
    surface them.  Replies whose ``thread_id`` isn't found in ``threads``,
    or whose target has no ``reply_target_id`` (review summaries and
    issue-level comments), are logged and marked as failed: the REST
    ``/pulls/.../comments/{id}/replies`` endpoint only accepts inline
    review-thread comment ids.

    ``repo_root`` is used as the ``cwd`` for ``gh`` subprocess calls.
    """
    results: list[tuple[str, bool]] = []
    target_by_thread_id = {t.thread_id: t.reply_target_id for t in threads}

    for reply in replies:
        target_id = target_by_thread_id.get(reply.thread_id)
        if target_id is None:
            if reply.thread_id not in target_by_thread_id:
                _log.warning(
                    "post_comment_replies: unknown thread_id %s — skipping",
                    reply.thread_id,
                )
            else:
                _log.warning(
                    "post_comment_replies: thread %s has no reply target "
                    "(review summary or issue comment) — skipping",
                    reply.thread_id,
                )
            results.append((reply.thread_id, False))
            continue

        prefix = f"[harness] addressed in {commit_sha}: "
        body = prefix + reply.body

        # gh api POST to create a reply on the specific pull request review comment.
        # GitHub REST endpoint: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies
        # {comment_id} must be the numeric databaseId, not a GraphQL node id.
        cmd = [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments/{target_id}/replies",
            "-f",
            f"body={body}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            if result.returncode != 0:
                _log.warning(
                    "post_comment_replies: gh api failed for thread %s (exit %d): %s",
                    reply.thread_id,
                    result.returncode,
                    result.stderr.strip(),
                )
                results.append((reply.thread_id, False))
            else:
                _log.info(
                    "post_comment_replies: posted reply to thread %s", reply.thread_id
                )
                results.append((reply.thread_id, True))
        except Exception as exc:
            _log.warning(
                "post_comment_replies: exception posting reply to thread %s: %s",
                reply.thread_id,
                exc,
            )
            results.append((reply.thread_id, False))

    return results


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
