"""Tests for file impact tracking and overlap detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory import impacts
from darkfactory.prd import load_all

from .conftest import write_prd


# ---------- expand_impacts (unchanged from previous PRDs) ----------


def test_expand_impacts_literal_path() -> None:
    files = ["src/foo.rs", "src/bar.rs", "tests/baz.py"]
    matched = impacts.expand_impacts(["src/foo.rs"], files)
    assert matched == {"src/foo.rs"}


def test_expand_impacts_glob() -> None:
    files = ["src/foo.rs", "src/bar.rs", "tests/baz.py"]
    matched = impacts.expand_impacts(["src/*.rs"], files)
    assert matched == {"src/foo.rs", "src/bar.rs"}


def test_expand_impacts_multiple_patterns() -> None:
    files = ["src/foo.rs", "src/bar.rs", "tests/baz.py"]
    matched = impacts.expand_impacts(["src/foo.rs", "tests/*.py"], files)
    assert matched == {"src/foo.rs", "tests/baz.py"}


def test_expand_impacts_no_match() -> None:
    files = ["src/foo.rs"]
    matched = impacts.expand_impacts(["nonexistent/*.py"], files)
    assert matched == set()


def test_expand_impacts_literal_nonexistent_file() -> None:
    """Literal paths for files that don't yet exist are included verbatim.

    This lets a PRD declare an impact on a file it plans to create — two
    PRDs both targeting the same new file should conflict even before
    either one runs.
    """
    files = ["other/existing.rs"]
    matched = impacts.expand_impacts(["src/new_file.rs"], files)
    assert matched == {"src/new_file.rs"}


def test_expand_impacts_glob_nonexistent_remains_empty() -> None:
    """Glob patterns that match no existing files produce no results."""
    files = ["src/foo.rs"]
    matched = impacts.expand_impacts(["src/*.py"], files)
    assert matched == set()


def test_expand_impacts_mixed_glob_and_literal() -> None:
    """A mix of glob (matched against files) and literal (always included)."""
    files = ["src/foo.rs", "src/bar.rs"]
    matched = impacts.expand_impacts(
        ["src/*.rs", "src/brand_new.rs"],
        files,
    )
    assert matched == {"src/foo.rs", "src/bar.rs", "src/brand_new.rs"}


# ---------- effective_impacts (PRD-212) ----------


def test_effective_impacts_leaf_returns_declared(tmp_prd_dir: Path) -> None:
    """A leaf PRD (no children) returns its own declared impacts."""
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs", "src/bar.rs"])
    prds = load_all(tmp_prd_dir)
    result = impacts.effective_impacts(prds["PRD-001"], prds)
    assert result == ["src/foo.rs", "src/bar.rs"]


def test_effective_impacts_leaf_empty_returns_empty(tmp_prd_dir: Path) -> None:
    """A leaf with no declared impacts returns an empty list."""
    write_prd(tmp_prd_dir, "PRD-001", "a")
    prds = load_all(tmp_prd_dir)
    assert impacts.effective_impacts(prds["PRD-001"], prds) == []


def test_effective_impacts_container_aggregates_children(tmp_prd_dir: Path) -> None:
    """A container returns the sorted union of leaf descendants' impacts."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(
        tmp_prd_dir,
        "PRD-002",
        "task-a",
        parent="PRD-001",
        impacts=["src/foo.rs"],
    )
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "task-b",
        parent="PRD-001",
        impacts=["src/bar.rs", "src/baz.rs"],
    )
    prds = load_all(tmp_prd_dir)
    result = impacts.effective_impacts(prds["PRD-001"], prds)
    assert result == ["src/bar.rs", "src/baz.rs", "src/foo.rs"]


def test_effective_impacts_container_with_declared_raises(tmp_prd_dir: Path) -> None:
    """A container that declares impacts is a tree-consistency violation."""
    write_prd(
        tmp_prd_dir,
        "PRD-001",
        "epic",
        kind="epic",
        impacts=["something.rs"],  # should be empty
    )
    write_prd(tmp_prd_dir, "PRD-002", "child", parent="PRD-001", impacts=["src/foo.rs"])
    prds = load_all(tmp_prd_dir)
    with pytest.raises(ValueError, match="container"):
        impacts.effective_impacts(prds["PRD-001"], prds)


def test_effective_impacts_nested_containers_aggregate(tmp_prd_dir: Path) -> None:
    """Intermediate containers contribute via their descendants' leaves."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-002", "feature", kind="feature", parent="PRD-001")
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "leaf-1",
        parent="PRD-002",
        impacts=["a.rs"],
    )
    write_prd(
        tmp_prd_dir,
        "PRD-004",
        "leaf-2",
        parent="PRD-002",
        impacts=["b.rs"],
    )
    write_prd(
        tmp_prd_dir,
        "PRD-005",
        "direct-child-leaf",
        parent="PRD-001",
        impacts=["c.rs"],
    )
    prds = load_all(tmp_prd_dir)
    # The top-level epic aggregates all three leaf impacts.
    result = impacts.effective_impacts(prds["PRD-001"], prds)
    assert result == ["a.rs", "b.rs", "c.rs"]


def test_effective_impacts_container_with_no_children_yet(tmp_prd_dir: Path) -> None:
    """A PRD with no children is treated as a leaf (returns declared)."""
    # kind is "epic" but no children exist yet — it's "pre-planning".
    # We treat it as a leaf (its declared impacts, which are empty).
    write_prd(tmp_prd_dir, "PRD-001", "unplanned-epic", kind="epic")
    prds = load_all(tmp_prd_dir)
    assert impacts.effective_impacts(prds["PRD-001"], prds) == []


def test_effective_impacts_container_ignores_empty_leaves(tmp_prd_dir: Path) -> None:
    """Leaves that don't declare impacts contribute nothing to the aggregate."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(
        tmp_prd_dir, "PRD-002", "declared", parent="PRD-001", impacts=["x.rs"]
    )
    write_prd(tmp_prd_dir, "PRD-003", "undeclared", parent="PRD-001")  # empty
    prds = load_all(tmp_prd_dir)
    assert impacts.effective_impacts(prds["PRD-001"], prds) == ["x.rs"]


# ---------- impacts_overlap (now takes prds) ----------


def test_impacts_overlap_disjoint(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b", impacts=["src/bar.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs", "src/bar.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files, prds)
    assert overlap == set()


def test_impacts_overlap_intersecting(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs", "src/bar.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b", impacts=["src/bar.rs", "src/baz.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs", "src/bar.rs", "src/baz.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files, prds)
    assert overlap == {"src/bar.rs"}


def test_impacts_overlap_glob_intersection(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/*.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b", impacts=["src/foo.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs", "src/bar.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files, prds)
    assert overlap == {"src/foo.rs"}


def test_impacts_overlap_undeclared_returns_empty(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b")  # no impacts declared
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files, prds)
    assert overlap == set()


# ---------- parent/child exemption (PRD-212) ----------


def test_impacts_overlap_parent_child_exempt(tmp_prd_dir: Path) -> None:
    """A container's effective impacts include its children, so the
    overlap between them is definitional — not a conflict."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(
        tmp_prd_dir,
        "PRD-002",
        "child",
        parent="PRD-001",
        impacts=["src/foo.rs"],
    )
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs"]
    # Epic -> child: direct containment, should return empty
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files, prds)
    assert overlap == set()
    # And the other direction
    overlap = impacts.impacts_overlap(prds["PRD-002"], prds["PRD-001"], files, prds)
    assert overlap == set()


def test_impacts_overlap_transitive_ancestor_exempt(tmp_prd_dir: Path) -> None:
    """A grandparent -> grandchild overlap is also exempt."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(tmp_prd_dir, "PRD-002", "feature", kind="feature", parent="PRD-001")
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "leaf",
        parent="PRD-002",
        impacts=["x.rs"],
    )
    prds = load_all(tmp_prd_dir)
    files = ["x.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-003"], files, prds)
    assert overlap == set()


def test_impacts_overlap_siblings_still_warn(tmp_prd_dir: Path) -> None:
    """Sibling tasks under the same container still get conflict checks.

    This is the critical case: two children of the same epic touching
    the same file need an explicit depends_on, and the validator must
    still surface this.
    """
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(
        tmp_prd_dir,
        "PRD-002",
        "sibling-a",
        parent="PRD-001",
        impacts=["src/shared.rs"],
    )
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "sibling-b",
        parent="PRD-001",
        impacts=["src/shared.rs"],
    )
    prds = load_all(tmp_prd_dir)
    files = ["src/shared.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-002"], prds["PRD-003"], files, prds)
    assert overlap == {"src/shared.rs"}


def test_impacts_overlap_cross_tree_still_warns(tmp_prd_dir: Path) -> None:
    """Unrelated PRDs touching the same file still overlap (no exemption)."""
    write_prd(tmp_prd_dir, "PRD-001", "one", impacts=["src/foo.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "two", impacts=["src/foo.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files, prds)
    assert overlap == {"src/foo.rs"}


def test_impacts_overlap_epic_vs_unrelated_uses_aggregate(tmp_prd_dir: Path) -> None:
    """An epic's overlap with an unrelated PRD is computed from the aggregate."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(
        tmp_prd_dir,
        "PRD-002",
        "child",
        parent="PRD-001",
        impacts=["src/shared.rs"],
    )
    # Unrelated PRD in a different tree
    write_prd(
        tmp_prd_dir,
        "PRD-003",
        "unrelated",
        impacts=["src/shared.rs"],
    )
    prds = load_all(tmp_prd_dir)
    files = ["src/shared.rs"]
    # Epic (aggregated from PRD-002) vs unrelated PRD-003 should overlap
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-003"], files, prds)
    assert overlap == {"src/shared.rs"}


# ---------- find_conflicts (uses new signature internally) ----------


def test_find_conflicts_excludes_parent(tmp_prd_dir: Path) -> None:
    """find_conflicts should not report a parent as conflicting with its child."""
    write_prd(tmp_prd_dir, "PRD-001", "epic", kind="epic")
    write_prd(
        tmp_prd_dir,
        "PRD-002",
        "child",
        parent="PRD-001",
        impacts=["src/foo.rs"],
    )
    prds = load_all(tmp_prd_dir)
    # find_conflicts needs a git repo to call tracked_files.
    # In this unit test we create a minimal one.
    import subprocess

    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=tmp_prd_dir, check=True
    )
    conflicts = impacts.find_conflicts(prds["PRD-001"], prds, tmp_prd_dir)
    # Epic and child don't conflict with each other
    assert not any(other_id == "PRD-002" for other_id, _ in conflicts)
