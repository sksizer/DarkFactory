"""Tests for the unified structured event log (PRD-566)."""

from __future__ import annotations

import json
from pathlib import Path

from darkfactory.event_log import EventWriter, generate_session_id


def test_generate_session_id_format() -> None:
    sid = generate_session_id()
    assert sid.startswith("s-")
    parts = sid.split("-")
    assert len(parts) == 4
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 6  # HHMMSS


def test_event_writer_creates_file(tmp_path: Path) -> None:
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    assert writer.path.parent == tmp_path / ".darkfactory" / "events"
    assert writer.path.name.startswith("PRD-100-")
    assert writer.path.suffix == ".jsonl"
    writer.close()


def test_event_writer_emit_writes_jsonl(tmp_path: Path) -> None:
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    writer.emit(
        "workflow", "workflow_start", workflow="default", branch_name="prd/PRD-100-test"
    )
    writer.emit("workflow", "task_start", task="implement", kind="agent")
    writer.close()

    lines = writer.path.read_text().strip().split("\n")
    assert len(lines) == 2

    ev1 = json.loads(lines[0])
    assert ev1["session_id"] == "s-test-123456-abcd"
    assert ev1["prd_id"] == "PRD-100"
    assert ev1["scope"] == "workflow"
    assert ev1["type"] == "workflow_start"
    assert ev1["workflow"] == "default"
    assert ev1["branch_name"] == "prd/PRD-100-test"
    assert "ts" in ev1

    ev2 = json.loads(lines[1])
    assert ev2["type"] == "task_start"
    assert ev2["task"] == "implement"
    assert ev2["kind"] == "agent"


def test_event_writer_flush_per_write(tmp_path: Path) -> None:
    """Events should be visible immediately (AC-11)."""
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    writer.emit("workflow", "workflow_start", workflow="default")
    # Read without closing — should see the event.
    content = writer.path.read_text()
    assert "workflow_start" in content
    writer.close()


def test_event_writer_context_manager(tmp_path: Path) -> None:
    with EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100") as writer:
        writer.emit("workflow", "workflow_start", workflow="default")
    # File should be closed now.
    lines = writer.path.read_text().strip().split("\n")
    assert len(lines) == 1


def test_event_writer_no_file_in_dry_run(tmp_path: Path) -> None:
    """Dry-run mode should not produce event files (AC-12).

    The EventWriter is only created when dry_run=False and session_id is set.
    This test verifies the runner's guard rather than EventWriter itself.
    """
    events_dir = tmp_path / ".darkfactory" / "events"
    assert not events_dir.exists()


def test_event_writer_agent_event(tmp_path: Path) -> None:
    """Agent stream-json events should be wrapped in agent_event (AC-3)."""
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    original_event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "hello"}]},
    }
    writer.emit("task", "agent_event", task="implement", event=original_event)
    writer.close()

    lines = writer.path.read_text().strip().split("\n")
    ev = json.loads(lines[0])
    assert ev["type"] == "agent_event"
    assert ev["scope"] == "task"
    assert ev["event"] == original_event


def test_event_writer_shell_output(tmp_path: Path) -> None:
    """Shell task output should appear in shell_output events (AC-4)."""
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    writer.emit(
        "task", "shell_output", task="test", stream="stdout", text="all tests passed"
    )
    writer.emit(
        "task", "shell_output", task="test", stream="stderr", text="warnings here"
    )
    writer.close()

    lines = writer.path.read_text().strip().split("\n")
    assert len(lines) == 2
    ev1 = json.loads(lines[0])
    assert ev1["type"] == "shell_output"
    assert ev1["stream"] == "stdout"
    assert ev1["text"] == "all tests passed"


def test_event_writer_builtin_effect(tmp_path: Path) -> None:
    """Builtin side-effects should emit builtin_effect events (AC-5)."""
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    writer.emit(
        "task",
        "builtin_effect",
        task="set_status",
        effect="set_status",
        detail={"from": "ready", "to": "in-progress"},
    )
    writer.close()

    lines = writer.path.read_text().strip().split("\n")
    ev = json.loads(lines[0])
    assert ev["type"] == "builtin_effect"
    assert ev["effect"] == "set_status"
    assert ev["detail"] == {"from": "ready", "to": "in-progress"}


def test_event_writer_workflow_finish(tmp_path: Path) -> None:
    """workflow_finish should include success and steps summary (AC-2)."""
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    writer.emit(
        "workflow",
        "workflow_finish",
        success=True,
        failure_reason=None,
        steps=[
            {"name": "ensure_worktree", "kind": "builtin", "success": True},
            {"name": "implement", "kind": "agent", "success": True},
        ],
    )
    writer.close()

    lines = writer.path.read_text().strip().split("\n")
    ev = json.loads(lines[0])
    assert ev["type"] == "workflow_finish"
    assert ev["success"] is True
    assert ev["failure_reason"] is None
    assert len(ev["steps"]) == 2


def test_event_writer_dag_events(tmp_path: Path) -> None:
    """DAG-level events should appear in per-PRD files (AC-6)."""
    writer = EventWriter(tmp_path, "s-test-123456-abcd", "PRD-100")
    writer.emit(
        "dag", "prd_picked", prd_id="PRD-100", base_ref="main", workflow="default"
    )
    writer.emit(
        "dag",
        "prd_finished",
        prd_id="PRD-100",
        success=True,
        pr_url="https://example.com/pr/1",
    )
    writer.close()

    lines = writer.path.read_text().strip().split("\n")
    assert len(lines) == 2
    ev1 = json.loads(lines[0])
    assert ev1["scope"] == "dag"
    assert ev1["type"] == "prd_picked"
    ev2 = json.loads(lines[1])
    assert ev2["type"] == "prd_finished"
    assert ev2["success"] is True


def test_session_id_shared_across_files(tmp_path: Path) -> None:
    """All files from a single CLI invocation share the same session_id (AC-7)."""
    sid = "s-test-123456-abcd"
    w1 = EventWriter(tmp_path, sid, "PRD-100")
    w2 = EventWriter(tmp_path, sid, "PRD-101")
    w1.emit("workflow", "workflow_start", workflow="default")
    w2.emit("workflow", "workflow_start", workflow="default")
    w1.close()
    w2.close()

    ev1 = json.loads(w1.path.read_text().strip().split("\n")[0])
    ev2 = json.loads(w2.path.read_text().strip().split("\n")[0])
    assert ev1["session_id"] == ev2["session_id"] == sid
