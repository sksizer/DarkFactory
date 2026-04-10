"""Tests for ``prd new`` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from darkfactory.cli import main
from darkfactory.cli.new import _slugify

from .conftest import write_prd


# ---------------------------------------------------------------------------
# _slugify unit tests
# ---------------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert _slugify("My feature") == "my-feature"


def test_slugify_punctuation() -> None:
    assert _slugify("Hello, World!") == "hello-world"


def test_slugify_multiple_spaces() -> None:
    assert _slugify("  lots   of   spaces  ") == "lots-of-spaces"


def test_slugify_unicode() -> None:
    # Non-ASCII stripped, remaining ascii forms slug
    assert _slugify("café au lait") == "caf-au-lait"


def test_slugify_empty_title() -> None:
    assert _slugify("!!!") == "untitled"


def test_slugify_with_dashes() -> None:
    assert _slugify("my-existing-slug") == "my-existing-slug"


# ---------------------------------------------------------------------------
# cmd_new integration tests
# ---------------------------------------------------------------------------


def test_new_basic_creates_file(tmp_path: Path) -> None:
    """Basic usage creates PRD-001-my-feature.md in an empty dir."""
    prd_dir = tmp_path / "prds"
    rc = main(["--prd-dir", str(prd_dir), "new", "My feature"])
    assert rc == 0
    created = prd_dir / "PRD-001-my-feature.md"
    assert created.exists()


def test_new_auto_id_increments(tmp_path: Path) -> None:
    """Auto-id picks the number above the current max."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-005", "five", title="Existing five")
    write_prd(prd_dir, "PRD-010", "ten", title="Existing ten")

    rc = main(["--prd-dir", str(prd_dir), "new", "Next thing"])
    assert rc == 0
    assert (prd_dir / "PRD-011-next-thing.md").exists()


def test_new_explicit_id(tmp_path: Path) -> None:
    """--id pins the PRD id."""
    prd_dir = tmp_path / "prds"
    rc = main(["--prd-dir", str(prd_dir), "new", "Pinned", "--id", "PRD-500"])
    assert rc == 0
    assert (prd_dir / "PRD-500-pinned.md").exists()


def test_new_explicit_id_refused_if_exists(tmp_path: Path) -> None:
    """--id refuses if the id already exists."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-042", "fortytwo", title="Existing")

    with pytest.raises(SystemExit):
        main(["--prd-dir", str(prd_dir), "new", "Duplicate", "--id", "PRD-042"])


def test_new_refuses_overwrite(tmp_path: Path) -> None:
    """Refuses to overwrite an existing file.

    Uses --id to pin the id so we know the exact filename that will be
    attempted, then pre-creates that file as a different PRD.
    """
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    # Pre-create the exact output path as a valid PRD with a different id
    # so load_all succeeds but the file-exists guard fires.
    write_prd(prd_dir, "PRD-099", "my-title", title="Already here")

    with pytest.raises(SystemExit):
        main(["--prd-dir", str(prd_dir), "new", "My title", "--id", "PRD-099"])


def test_new_frontmatter_is_valid(tmp_path: Path) -> None:
    """Generated frontmatter has expected fields and passes basic checks."""
    prd_dir = tmp_path / "prds"
    rc = main(["--prd-dir", str(prd_dir), "new", "Check Fields"])
    assert rc == 0

    path = prd_dir / "PRD-001-check-fields.md"
    text = path.read_text(encoding="utf-8")

    # Extract frontmatter
    parts = text.split("---\n", 2)
    fm = yaml.safe_load(parts[1])

    assert fm["id"] == "PRD-001"
    assert fm["title"] == "Check Fields"
    assert fm["status"] == "draft"
    assert fm["depends_on"] == []
    assert fm["blocks"] == []
    assert fm["impacts"] == []
    assert fm["parent"] is None
    assert fm["workflow"] is None
    assert "created" in fm
    assert "updated" in fm
    assert fm["created"] == fm["updated"]


def test_new_frontmatter_kind_default(tmp_path: Path) -> None:
    """Default kind is 'task'."""
    prd_dir = tmp_path / "prds"
    main(["--prd-dir", str(prd_dir), "new", "Kind Test"])
    path = prd_dir / "PRD-001-kind-test.md"
    fm = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n", 2)[1])
    assert fm["kind"] == "task"


def test_new_frontmatter_custom_flags(tmp_path: Path) -> None:
    """Custom --kind, --priority, --effort, --capability are respected."""
    prd_dir = tmp_path / "prds"
    rc = main(
        [
            "--prd-dir",
            str(prd_dir),
            "new",
            "Custom Flags",
            "--kind",
            "feature",
            "--priority",
            "high",
            "--effort",
            "l",
            "--capability",
            "complex",
        ]
    )
    assert rc == 0
    path = prd_dir / "PRD-001-custom-flags.md"
    fm = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n", 2)[1])
    assert fm["kind"] == "feature"
    assert fm["priority"] == "high"
    assert fm["effort"] == "l"
    assert fm["capability"] == "complex"


def test_new_body_has_standard_sections(tmp_path: Path) -> None:
    """Generated body contains all standard sections."""
    prd_dir = tmp_path / "prds"
    main(["--prd-dir", str(prd_dir), "new", "Section Check"])
    path = prd_dir / "PRD-001-section-check.md"
    body = path.read_text(encoding="utf-8")

    for section in [
        "## Summary",
        "## Motivation",
        "## Requirements",
        "## Technical Approach",
        "## Acceptance Criteria",
        "## Open Questions",
        "## References",
    ]:
        assert section in body, f"Missing section: {section}"


def test_new_invalid_kind_rejected(tmp_path: Path) -> None:
    """Invalid --kind value is rejected by argparse."""
    prd_dir = tmp_path / "prds"
    with pytest.raises(SystemExit):
        main(["--prd-dir", str(prd_dir), "new", "Bad Kind", "--kind", "bogus"])


def test_new_invalid_priority_rejected(tmp_path: Path) -> None:
    """Invalid --priority value is rejected by argparse."""
    prd_dir = tmp_path / "prds"
    with pytest.raises(SystemExit):
        main(["--prd-dir", str(prd_dir), "new", "Bad Priority", "--priority", "urgent"])


def test_new_no_existing_prds_starts_at_001(tmp_path: Path) -> None:
    """With zero existing PRDs, the first id is PRD-001."""
    prd_dir = tmp_path / "prds"
    rc = main(["--prd-dir", str(prd_dir), "new", "First Ever"])
    assert rc == 0
    assert (prd_dir / "PRD-001-first-ever.md").exists()


def test_new_validate_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Generated PRD passes `prd validate`."""
    # validate calls _find_repo_root which needs a .git directory
    (tmp_path / ".git").mkdir()
    prd_dir = tmp_path / "prds"
    main(["--prd-dir", str(prd_dir), "new", "Validate Me"])

    rc = main(["--prd-dir", str(prd_dir), "validate"])
    assert rc == 0
