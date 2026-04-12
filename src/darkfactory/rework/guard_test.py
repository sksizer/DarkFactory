"""Unit tests for rework_guard — loop detection core logic."""

from __future__ import annotations

from pathlib import Path

from darkfactory.rework.guard import DEFAULT_MAX_CONSECUTIVE, ReworkGuard


# ---------- helpers ----------


def _guard(tmp_path: Path, *, max_consecutive: int = 2) -> ReworkGuard:
    """Build a ReworkGuard rooted at tmp_path with a fast-expiring threshold."""
    return ReworkGuard(tmp_path, max_consecutive=max_consecutive)


# ---------- initial state ----------


def test_new_prd_not_blocked(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    assert not guard.is_blocked("PRD-001")


def test_new_prd_zero_consecutive(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    assert guard.get_consecutive_no_change("PRD-001") == 0


# ---------- changes reset counter ----------


def test_changes_reset_counter_from_nonzero(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    guard.record_outcome("PRD-001", had_changes=False)
    outcome = guard.record_outcome("PRD-001", had_changes=True)
    assert outcome.consecutive_no_change == 0
    assert not outcome.blocked
    assert guard.get_consecutive_no_change("PRD-001") == 0


def test_changes_unblock_blocked_prd(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=1)
    guard.record_outcome("PRD-001", had_changes=False)  # blocked after 1
    assert guard.is_blocked("PRD-001")

    outcome = guard.record_outcome("PRD-001", had_changes=True)
    assert not outcome.blocked
    assert not guard.is_blocked("PRD-001")


def test_changes_reset_returns_no_warning(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    guard.record_outcome("PRD-001", had_changes=False)
    outcome = guard.record_outcome("PRD-001", had_changes=True)
    assert outcome.warning is None


# ---------- warning escalation ----------


def test_first_no_change_emits_warning(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=2)
    outcome = guard.record_outcome("PRD-001", had_changes=False)
    assert outcome.consecutive_no_change == 1
    assert not outcome.blocked
    assert outcome.warning is not None
    assert "PRD-001" in outcome.warning


def test_warning_includes_threshold_info(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=3)
    outcome = guard.record_outcome("PRD-001", had_changes=False)
    assert outcome.warning is not None
    # Should mention the count and threshold
    assert "1" in outcome.warning
    assert "3" in outcome.warning


# ---------- blocking ----------


def test_blocked_after_n_consecutive(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=2)
    guard.record_outcome("PRD-001", had_changes=False)
    outcome = guard.record_outcome("PRD-001", had_changes=False)
    assert outcome.blocked
    assert guard.is_blocked("PRD-001")


def test_blocked_outcome_has_error_warning(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=2)
    guard.record_outcome("PRD-001", had_changes=False)
    outcome = guard.record_outcome("PRD-001", had_changes=False)
    assert outcome.warning is not None
    assert "blocked" in outcome.warning.lower()
    assert "PRD-001" in outcome.warning


def test_not_blocked_below_threshold(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=3)
    guard.record_outcome("PRD-001", had_changes=False)
    outcome = guard.record_outcome("PRD-001", had_changes=False)
    assert not outcome.blocked
    assert not guard.is_blocked("PRD-001")


def test_default_max_consecutive_is_two() -> None:
    assert DEFAULT_MAX_CONSECUTIVE == 2


# ---------- state persistence ----------


def test_state_persists_across_guard_instances(tmp_path: Path) -> None:
    guard1 = _guard(tmp_path, max_consecutive=2)
    guard1.record_outcome("PRD-001", had_changes=False)

    # Create a fresh guard pointing at the same directory.
    guard2 = _guard(tmp_path, max_consecutive=2)
    assert guard2.get_consecutive_no_change("PRD-001") == 1


def test_state_file_created_in_expected_location(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    guard.record_outcome("PRD-001", had_changes=False)
    expected = tmp_path / ".darkfactory" / "state" / "rework-guard.json"
    assert expected.exists()


def test_state_file_is_valid_json(tmp_path: Path) -> None:
    import json

    guard = _guard(tmp_path)
    guard.record_outcome("PRD-001", had_changes=False)
    state_file = tmp_path / ".darkfactory" / "state" / "rework-guard.json"
    data = json.loads(state_file.read_text())
    assert "PRD-001" in data
    assert data["PRD-001"]["consecutive_no_change"] == 1


def test_blocked_state_persists(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=2)
    guard.record_outcome("PRD-001", had_changes=False)
    guard.record_outcome("PRD-001", had_changes=False)

    fresh = _guard(tmp_path, max_consecutive=2)
    assert fresh.is_blocked("PRD-001")


# ---------- independent counters per PRD ----------


def test_different_prds_have_independent_counters(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=2)
    guard.record_outcome("PRD-001", had_changes=False)
    guard.record_outcome("PRD-001", had_changes=False)  # PRD-001 now blocked

    # PRD-002 should be unaffected.
    assert not guard.is_blocked("PRD-002")
    assert guard.get_consecutive_no_change("PRD-002") == 0


def test_change_in_one_prd_does_not_affect_another(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=2)
    guard.record_outcome("PRD-001", had_changes=False)
    guard.record_outcome("PRD-002", had_changes=False)

    # Reset PRD-001 with changes — PRD-002 counter should remain.
    guard.record_outcome("PRD-001", had_changes=True)
    assert guard.get_consecutive_no_change("PRD-001") == 0
    assert guard.get_consecutive_no_change("PRD-002") == 1


# ---------- manual reset ----------


def test_reset_clears_blocked_state(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_consecutive=1)
    guard.record_outcome("PRD-001", had_changes=False)
    assert guard.is_blocked("PRD-001")

    guard.reset("PRD-001")
    assert not guard.is_blocked("PRD-001")
    assert guard.get_consecutive_no_change("PRD-001") == 0


def test_reset_nonexistent_prd_is_noop(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    guard.reset("PRD-999")  # should not raise


# ---------- corrupt/missing state file ----------


def test_missing_state_file_returns_defaults(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    assert not guard.is_blocked("PRD-001")
    assert guard.get_consecutive_no_change("PRD-001") == 0


def test_corrupt_state_file_treated_as_empty(tmp_path: Path) -> None:
    state_dir = tmp_path / ".darkfactory" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "rework-guard.json").write_text("not json", encoding="utf-8")

    guard = _guard(tmp_path)
    # Should not raise; returns defaults.
    assert not guard.is_blocked("PRD-001")


# ---------- guard state accessible for rework-watch integration ----------


def test_is_blocked_readable_from_known_state_file_path(tmp_path: Path) -> None:
    """Guard state is at a known path so rework-watch can query it."""
    guard = _guard(tmp_path, max_consecutive=1)
    guard.record_outcome("PRD-001", had_changes=False)

    # A second guard (simulating the watcher process) reads the same file.
    watcher_guard = ReworkGuard(tmp_path)
    assert watcher_guard.is_blocked("PRD-001")
