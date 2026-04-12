"""Tests for cli.rework_watch."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.utils import Ok as _Ok
from darkfactory.utils.git import GitErr as _GitErr
from darkfactory.utils.github import GhErr as _GhErr

from darkfactory.cli.rework_watch import (
    PRWatchState,
    WatchState,
    _cmd_pause,
    _cmd_resume,
    _cmd_status,
    _cmd_stop,
    _has_new_unresolved_comments,
    _prd_id_from_branch,
    _worktree_exists,
    check_missing_worktrees,
    fetch_open_prd_prs,
    is_rate_limited,
    load_state,
    record_rework,
    run_poll_loop,
    save_state,
)


# ── _prd_id_from_branch ──────────────────────────────────────────────────────


def test_prd_id_from_branch_extracts_id() -> None:
    assert _prd_id_from_branch("prd/PRD-225.6-rework-watch") == "PRD-225.6"


def test_prd_id_from_branch_simple_id() -> None:
    assert _prd_id_from_branch("prd/PRD-42-my-feature") == "PRD-42"


def test_prd_id_from_branch_non_prd_branch() -> None:
    assert _prd_id_from_branch("feature/some-work") is None


def test_prd_id_from_branch_missing_separator() -> None:
    # branch must have a hyphen after the PRD id
    assert _prd_id_from_branch("prd/PRD-225.6") is None


# ── State persistence ────────────────────────────────────────────────────────


def test_load_state_returns_empty_when_no_file(tmp_path: Path) -> None:
    state = load_state(tmp_path)
    assert state.prs == {}


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    state = WatchState()
    pr_state = PRWatchState(
        last_seen_comment_ids={"id1", "id2"},
        rework_timestamps=[1000.0, 2000.0],
    )
    state.prs["123"] = pr_state

    save_state(tmp_path, state)
    loaded = load_state(tmp_path)

    assert loaded.prs["123"].last_seen_comment_ids == {"id1", "id2"}
    assert loaded.prs["123"].rework_timestamps == [1000.0, 2000.0]


def test_load_state_handles_corrupt_file(tmp_path: Path) -> None:
    state_file = tmp_path / ".darkfactory" / "state" / "rework-watch.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("NOT JSON {{{")

    state = load_state(tmp_path)
    assert state.prs == {}


# ── Rate limiting ─────────────────────────────────────────────────────────────


def test_is_rate_limited_false_when_no_history() -> None:
    pr_state = PRWatchState()
    assert not is_rate_limited(pr_state, max_per_hour=3, now=time.time())


def test_is_rate_limited_false_below_cap() -> None:
    now = time.time()
    pr_state = PRWatchState(rework_timestamps=[now - 100, now - 50])
    assert not is_rate_limited(pr_state, max_per_hour=3, now=now)


def test_is_rate_limited_true_at_cap() -> None:
    now = time.time()
    pr_state = PRWatchState(rework_timestamps=[now - 300, now - 200, now - 100])
    assert is_rate_limited(pr_state, max_per_hour=3, now=now)


def test_is_rate_limited_ignores_old_timestamps() -> None:
    now = time.time()
    # All 3 timestamps are older than 1 hour
    pr_state = PRWatchState(rework_timestamps=[now - 4000, now - 5000, now - 6000])
    assert not is_rate_limited(pr_state, max_per_hour=3, now=now)


def test_record_rework_appends_timestamp() -> None:
    now = time.time()
    pr_state = PRWatchState()
    record_rework(pr_state, now)
    assert len(pr_state.rework_timestamps) == 1
    assert pr_state.rework_timestamps[0] == now


def test_record_rework_prunes_old_entries() -> None:
    now = time.time()
    pr_state = PRWatchState(rework_timestamps=[now - 7200])  # 2h old
    record_rework(pr_state, now)
    assert len(pr_state.rework_timestamps) == 1
    assert pr_state.rework_timestamps[0] == now


# ── _worktree_exists ──────────────────────────────────────────────────────────


def test_worktree_exists_returns_true(tmp_path: Path) -> None:
    porcelain_output = (
        "worktree /some/path\n"
        "HEAD abc123\n"
        "branch refs/heads/prd/PRD-225.6-rework-watch\n"
        "\n"
    )
    with patch("darkfactory.cli.rework_watch.git_run") as mock_run:
        mock_run.return_value = _Ok(None, stdout=porcelain_output)
        assert _worktree_exists("PRD-225.6", tmp_path) is True


def test_worktree_exists_returns_false_when_not_found(tmp_path: Path) -> None:
    porcelain_output = (
        "worktree /some/path\nHEAD abc123\nbranch refs/heads/prd/PRD-999-other\n\n"
    )
    with patch("darkfactory.cli.rework_watch.git_run") as mock_run:
        mock_run.return_value = _Ok(None, stdout=porcelain_output)
        assert _worktree_exists("PRD-225.6", tmp_path) is False


def test_worktree_exists_returns_false_on_git_error(tmp_path: Path) -> None:
    with patch("darkfactory.cli.rework_watch.git_run") as mock_run:
        mock_run.return_value = _GitErr(1, "", "", ["git", "worktree", "list", "--porcelain"])
        assert _worktree_exists("PRD-1", tmp_path) is False


# ── check_missing_worktrees ───────────────────────────────────────────────────


def test_check_missing_worktrees_all_present(tmp_path: Path) -> None:
    prs = [{"number": 1, "headRefName": "prd/PRD-1-feat"}]
    with patch("darkfactory.cli.rework_watch._worktree_exists", return_value=True):
        missing = check_missing_worktrees(prs, tmp_path)
    assert missing == []


def test_check_missing_worktrees_detects_missing(tmp_path: Path) -> None:
    prs = [
        {"number": 1, "headRefName": "prd/PRD-1-feat"},
        {"number": 2, "headRefName": "prd/PRD-2-other"},
    ]
    with patch(
        "darkfactory.cli.rework_watch._worktree_exists",
        side_effect=[True, False],
    ):
        missing = check_missing_worktrees(prs, tmp_path)
    assert missing == ["PRD-2"]


# ── fetch_open_prd_prs ────────────────────────────────────────────────────────


def test_fetch_open_prd_prs_filters_non_prd_branches(tmp_path: Path) -> None:
    with patch("darkfactory.cli.rework_watch.gh_json") as mock_gh:
        mock_gh.return_value = _Ok([
            {"number": 1, "headRefName": "prd/PRD-1-feat"},
            {"number": 2, "headRefName": "feature/other"},
        ])
        result = fetch_open_prd_prs(tmp_path)
    assert len(result) == 1
    assert result[0]["number"] == 1


def test_fetch_open_prd_prs_returns_empty_on_failure(tmp_path: Path) -> None:
    with patch("darkfactory.cli.rework_watch.gh_json") as mock_gh:
        mock_gh.return_value = _GhErr(1, "", "error", ["gh"])
        result = fetch_open_prd_prs(tmp_path)
    assert result == []


# ── _has_new_unresolved_comments ──────────────────────────────────────────────


def test_has_new_comments_detects_new(tmp_path: Path) -> None:
    pr_state = PRWatchState(last_seen_comment_ids={"id1"})
    with patch("darkfactory.cli.rework_watch.gh_json") as mock_gh:
        mock_gh.return_value = _Ok({
            "reviewThreads": [
                {"comments": [{"id": "id1"}], "isResolved": False},
                {"comments": [{"id": "id2"}], "isResolved": False},
            ],
            "reviews": [],
            "comments": [],
        })
        has_new, current_ids = _has_new_unresolved_comments(1, pr_state, tmp_path)
    assert has_new is True
    assert "id2" in current_ids


def test_has_new_comments_no_new(tmp_path: Path) -> None:
    pr_state = PRWatchState(last_seen_comment_ids={"id1"})
    with patch("darkfactory.cli.rework_watch.gh_json") as mock_gh:
        mock_gh.return_value = _Ok({
            "reviewThreads": [
                {"comments": [{"id": "id1"}], "isResolved": False},
            ],
            "reviews": [],
            "comments": [],
        })
        has_new, current_ids = _has_new_unresolved_comments(1, pr_state, tmp_path)
    assert has_new is False


# ── Pause file ────────────────────────────────────────────────────────────────


def test_cmd_pause_creates_file(tmp_path: Path) -> None:
    _cmd_pause(tmp_path)
    assert (tmp_path / ".darkfactory" / "state" / "rework-watch.pause").exists()


def test_cmd_resume_removes_file(tmp_path: Path) -> None:
    pf = tmp_path / ".darkfactory" / "state" / "rework-watch.pause"
    pf.parent.mkdir(parents=True)
    pf.touch()
    _cmd_resume(tmp_path)
    assert not pf.exists()


def test_cmd_resume_noop_when_not_paused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _cmd_resume(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "not paused" in out


# ── Status / stop ─────────────────────────────────────────────────────────────


def test_cmd_status_no_pid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _cmd_status(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "not running" in out


def test_cmd_status_alive_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pid_file = tmp_path / ".darkfactory" / "state" / "rework-watch.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(os.getpid()))  # current PID is always alive

    rc = _cmd_status(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "running" in out


def test_cmd_stop_no_pid_file(tmp_path: Path) -> None:
    rc = _cmd_stop(tmp_path)
    assert rc == 1


def test_cmd_stop_sends_sigterm(tmp_path: Path) -> None:
    pid_file = tmp_path / ".darkfactory" / "state" / "rework-watch.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text("99999")

    with (
        patch("darkfactory.cli.rework_watch._pid_is_alive", return_value=True),
        patch("os.kill") as mock_kill,
    ):
        rc = _cmd_stop(tmp_path)
    assert rc == 0
    mock_kill.assert_called_once()


# ── run_poll_loop ─────────────────────────────────────────────────────────────


def test_poll_loop_refuses_when_worktrees_missing(tmp_path: Path) -> None:
    """run_poll_loop raises SystemExit when a worktree is missing."""
    prs = [{"number": 1, "headRefName": "prd/PRD-1-feat"}]
    with (
        patch(
            "darkfactory.cli.rework_watch.fetch_open_prd_prs",
            return_value=prs,
        ),
        patch(
            "darkfactory.cli.rework_watch._worktree_exists",
            return_value=False,
        ),
    ):
        with pytest.raises(SystemExit):
            run_poll_loop(tmp_path, tmp_path / ".darkfactory" / "prds")


def test_poll_loop_pauses_when_pause_file_exists(tmp_path: Path) -> None:
    """Poll loop skips rework when pause file is present."""
    # Create pause file
    pause_file = tmp_path / ".darkfactory" / "state" / "rework-watch.pause"
    pause_file.parent.mkdir(parents=True)
    pause_file.touch()

    call_count = 0

    def fake_sleep(secs: float) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise KeyboardInterrupt

    with (
        patch("darkfactory.cli.rework_watch.fetch_open_prd_prs", return_value=[]),
        patch("darkfactory.cli.rework_watch.check_missing_worktrees", return_value=[]),
        patch("darkfactory.cli.rework_watch.time") as mock_time,
    ):
        mock_time.time.return_value = 1000.0
        mock_time.sleep.side_effect = fake_sleep
        try:
            run_poll_loop(tmp_path, tmp_path / ".darkfactory" / "prds", poll_interval=1)
        except KeyboardInterrupt:
            pass

    # Should have slept without triggering rework
    assert call_count >= 1


def test_poll_loop_triggers_rework_on_new_comments(tmp_path: Path) -> None:
    """Poll loop calls _trigger_rework when new comments detected."""
    prs = [{"number": 1, "headRefName": "prd/PRD-1-feat"}]

    sleep_calls = 0

    def fake_sleep(secs: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        raise KeyboardInterrupt

    with (
        patch(
            "darkfactory.cli.rework_watch.fetch_open_prd_prs",
            return_value=prs,
        ),
        patch("darkfactory.cli.rework_watch.check_missing_worktrees", return_value=[]),
        patch(
            "darkfactory.cli.rework_watch._has_new_unresolved_comments",
            return_value=(True, {"new-id"}),
        ),
        patch("darkfactory.cli.rework_watch._prd_is_locked", return_value=False),
        patch(
            "darkfactory.cli.rework_watch._trigger_rework", return_value=0
        ) as mock_trigger,
        patch("darkfactory.cli.rework_watch.time") as mock_time,
    ):
        mock_time.time.return_value = 1000.0
        mock_time.sleep.side_effect = fake_sleep
        try:
            run_poll_loop(tmp_path, tmp_path / ".darkfactory" / "prds", poll_interval=1)
        except KeyboardInterrupt:
            pass

    mock_trigger.assert_called_once_with("PRD-1", tmp_path / ".darkfactory" / "prds")


def test_poll_loop_skips_rework_when_rate_limited(tmp_path: Path) -> None:
    """Poll loop skips rework when rate cap is hit."""
    prs = [{"number": 1, "headRefName": "prd/PRD-1-feat"}]
    now = time.time()

    def fake_sleep(secs: float) -> None:
        raise KeyboardInterrupt

    with (
        patch(
            "darkfactory.cli.rework_watch.fetch_open_prd_prs",
            return_value=prs,
        ),
        patch("darkfactory.cli.rework_watch.check_missing_worktrees", return_value=[]),
        patch(
            "darkfactory.cli.rework_watch._has_new_unresolved_comments",
            return_value=(True, {"new-id"}),
        ),
        patch(
            "darkfactory.cli.rework_watch.is_rate_limited",
            return_value=True,
        ),
        patch("darkfactory.cli.rework_watch._trigger_rework") as mock_trigger,
        patch("darkfactory.cli.rework_watch.time") as mock_time,
    ):
        mock_time.time.return_value = now
        mock_time.sleep.side_effect = fake_sleep
        try:
            run_poll_loop(tmp_path, tmp_path / ".darkfactory" / "prds", poll_interval=1)
        except KeyboardInterrupt:
            pass

    mock_trigger.assert_not_called()


def test_poll_loop_persists_state(tmp_path: Path) -> None:
    """Poll loop saves state after each cycle."""
    prs = [{"number": 42, "headRefName": "prd/PRD-42-feat"}]

    def fake_sleep(secs: float) -> None:
        raise KeyboardInterrupt

    with (
        patch("darkfactory.cli.rework_watch.fetch_open_prd_prs", return_value=prs),
        patch("darkfactory.cli.rework_watch.check_missing_worktrees", return_value=[]),
        patch(
            "darkfactory.cli.rework_watch._has_new_unresolved_comments",
            return_value=(False, {"seen-id"}),
        ),
        patch("darkfactory.cli.rework_watch.time") as mock_time,
    ):
        mock_time.time.return_value = 5000.0
        mock_time.sleep.side_effect = fake_sleep
        try:
            run_poll_loop(tmp_path, tmp_path / ".darkfactory" / "prds", poll_interval=1)
        except KeyboardInterrupt:
            pass

    # State file should have been written
    state_file = tmp_path / ".darkfactory" / "state" / "rework-watch.json"
    assert state_file.exists()
    state = load_state(tmp_path)
    assert "42" in state.prs
    assert state.prs["42"].last_seen_comment_ids == {"seen-id"}
