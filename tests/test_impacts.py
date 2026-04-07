"""Tests for file impact tracking and overlap detection."""

from __future__ import annotations

from pathlib import Path

from prd_harness import impacts
from prd_harness.prd import load_all

from .conftest import write_prd


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


def test_impacts_overlap_disjoint(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b", impacts=["src/bar.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs", "src/bar.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files)
    assert overlap == set()


def test_impacts_overlap_intersecting(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs", "src/bar.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b", impacts=["src/bar.rs", "src/baz.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs", "src/bar.rs", "src/baz.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files)
    assert overlap == {"src/bar.rs"}


def test_impacts_overlap_glob_intersection(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/*.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b", impacts=["src/foo.rs"])
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs", "src/bar.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files)
    assert overlap == {"src/foo.rs"}


def test_impacts_overlap_undeclared_returns_empty(tmp_prd_dir: Path) -> None:
    write_prd(tmp_prd_dir, "PRD-001", "a", impacts=["src/foo.rs"])
    write_prd(tmp_prd_dir, "PRD-002", "b")  # no impacts declared
    prds = load_all(tmp_prd_dir)
    files = ["src/foo.rs"]
    overlap = impacts.impacts_overlap(prds["PRD-001"], prds["PRD-002"], files)
    assert overlap == set()
