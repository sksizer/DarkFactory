"""Tests for ``prd normalize`` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.cli import main

from .conftest import write_prd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prd_with_unsorted_tags(prd_dir: Path, prd_id: str = "PRD-070") -> Path:
    """Write a PRD whose tags block is intentionally out of order."""
    slug = prd_id.lower().replace("-", "")
    path = prd_dir / f"{prd_id}-{slug}.md"
    path.write_text(
        "---\n"
        f'id: "{prd_id}"\n'
        f'title: "Test {prd_id}"\n'
        "kind: task\n"
        "status: ready\n"
        "priority: medium\n"
        "effort: s\n"
        "capability: simple\n"
        "parent: null\n"
        "depends_on: []\n"
        "blocks: []\n"
        "impacts: []\n"
        "workflow: null\n"
        "created: 2026-04-06\n"
        "updated: 2026-04-06\n"
        "tags:\n"
        "  - zebra\n"
        "  - apple\n"
        "---\n"
        "\n"
        "# Body\n",
        encoding="utf-8",
    )
    return path


def _prd_canonical(prd_dir: Path, prd_id: str = "PRD-070") -> Path:
    """Write a PRD whose list fields are already in canonical order."""
    slug = prd_id.lower().replace("-", "")
    path = prd_dir / f"{prd_id}-{slug}.md"
    path.write_text(
        "---\n"
        f'id: "{prd_id}"\n'
        f'title: "Test {prd_id}"\n'
        "kind: task\n"
        "status: ready\n"
        "priority: medium\n"
        "effort: s\n"
        "capability: simple\n"
        "parent: null\n"
        "depends_on: []\n"
        "blocks: []\n"
        "impacts: []\n"
        "workflow: null\n"
        "created: 2026-04-06\n"
        "updated: 2026-04-06\n"
        "tags:\n"
        "  - alpha\n"
        "  - beta\n"
        "---\n"
        "\n"
        "# Body\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Single-PRD normalization
# ---------------------------------------------------------------------------


def test_normalize_single_prd_sorts_tags(tmp_path: Path) -> None:
    """``prd normalize PRD-070`` sorts tags and exits 0."""
    path = _prd_with_unsorted_tags(tmp_path)
    rc = main(["--prd-dir", str(tmp_path), "normalize", "PRD-070"])
    assert rc == 0
    after = path.read_text(encoding="utf-8")
    assert after.index("  - apple\n") < after.index("  - zebra\n")


def test_normalize_single_prd_no_changes_reports_canonical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-4: already-canonical PRD reports no changes."""
    _prd_canonical(tmp_path)
    rc = main(["--prd-dir", str(tmp_path), "normalize", "PRD-070"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No changes" in out or "already canonical" in out


def test_normalize_unknown_prd_exits_nonzero(tmp_path: Path) -> None:
    """Requesting a PRD that doesn't exist raises SystemExit."""
    write_prd(tmp_path, "PRD-001", "existing")
    with pytest.raises(SystemExit):
        main(["--prd-dir", str(tmp_path), "normalize", "PRD-999"])


# ---------------------------------------------------------------------------
# --all
# ---------------------------------------------------------------------------


def test_normalize_all_normalizes_multiple_prds(tmp_path: Path) -> None:
    """``--all`` normalizes every PRD in the directory."""
    path1 = _prd_with_unsorted_tags(tmp_path, "PRD-070")
    path2 = _prd_with_unsorted_tags(tmp_path, "PRD-071")
    rc = main(["--prd-dir", str(tmp_path), "normalize", "--all"])
    assert rc == 0
    for path in (path1, path2):
        after = path.read_text(encoding="utf-8")
        assert after.index("  - apple\n") < after.index("  - zebra\n")


# ---------------------------------------------------------------------------
# --check (AC-5)
# ---------------------------------------------------------------------------


def test_normalize_check_exits_nonzero_on_drifted_file(tmp_path: Path) -> None:
    """AC-5a: ``--check`` exits non-zero when at least one file is not canonical."""
    path = _prd_with_unsorted_tags(tmp_path)
    original = path.read_text(encoding="utf-8")
    rc = main(["--prd-dir", str(tmp_path), "normalize", "--all", "--check"])
    assert rc != 0
    # --check must not modify the file.
    assert path.read_text(encoding="utf-8") == original


def test_normalize_check_exits_zero_on_canonical_set(tmp_path: Path) -> None:
    """AC-5b: ``--check`` exits 0 when all files are already canonical."""
    _prd_canonical(tmp_path)
    rc = main(["--prd-dir", str(tmp_path), "normalize", "--all", "--check"])
    assert rc == 0


def test_normalize_check_does_not_write(tmp_path: Path) -> None:
    """``--check`` must never write to disk."""
    path = _prd_with_unsorted_tags(tmp_path)
    before = path.read_text(encoding="utf-8")
    main(["--prd-dir", str(tmp_path), "normalize", "--all", "--check"])
    assert path.read_text(encoding="utf-8") == before
