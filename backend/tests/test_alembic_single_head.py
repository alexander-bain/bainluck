"""Guard test: Alembic's migration graph has one linear head (#13865).

The defect class: two migration branches merge onto ``master`` sharing the
same ``down_revision`` (for instance ``anon_install_counts_434a`` and
``poll_open_outcomes_13673`` both branching from ``retired_team_redirects_13229``).
Heroku's release step runs ``alembic upgrade heads`` and
``scripts/assert_migrations_applied.py``; a forked graph should fail in tests
before a release hits it.

No database connection is needed: :class:`alembic.script.ScriptDirectory`
resolves the migration DAG straight from ``backend/alembic/versions/``.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
ALEMBIC_SCRIPT_DIR = BACKEND_DIR / "alembic"


def load_repo_alembic_script_dir() -> ScriptDirectory:
    """Load the repository's Alembic script directory independent of CWD."""
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_DIR))
    return ScriptDirectory.from_config(config)


def _format_head_detail(script_dir: ScriptDirectory, revision_id: str) -> str:
    rev = script_dir.get_revision(revision_id)
    filename = Path(rev.path).name if rev and rev.path else "<unknown>"
    down_rev = rev.down_revision if rev is not None else "<unknown>"
    return f"{revision_id} (down_revision={down_rev!r}, file={filename})"


def assert_single_alembic_head(script_dir: ScriptDirectory) -> str:
    """Assert that ``script_dir`` resolves to one Alembic head and return it."""
    heads = sorted(script_dir.get_heads())
    if len(heads) != 1:
        details = "\n  - ".join(_format_head_detail(script_dir, hid) for hid in heads)
        detail_block = f"\n  - {details}" if details else " (none)"
        raise AssertionError(
            f"Expected exactly 1 Alembic migration head, found {len(heads)}:{detail_block}\n"
            "Re-parent any divergent migration onto current master's single head "
            "(or add an explicitly ruled merge revision)."
        )
    return heads[0]


def _make_synthetic_script_dir(
    tmp_path: Path, revisions: list[tuple[str, str | tuple[str, ...] | None]]
) -> ScriptDirectory:
    alembic_dir = tmp_path / "alembic"
    versions_dir = alembic_dir / "versions"
    versions_dir.mkdir(parents=True)
    for rev_id, down_rev in revisions:
        (versions_dir / f"{rev_id}.py").write_text(
            f"revision = {rev_id!r}\n"
            f"down_revision = {down_rev!r}\n\n"
            "def upgrade():\n    pass\n\n"
            "def downgrade():\n    pass\n",
            encoding="utf-8",
        )
    config = Config()
    config.set_main_option("script_location", str(alembic_dir))
    return ScriptDirectory.from_config(config)


def test_alembic_migrations_have_exactly_one_head():
    """The repository's migration graph must have one linear head."""
    script_dir = load_repo_alembic_script_dir()
    head = assert_single_alembic_head(script_dir)
    assert script_dir.get_revision(head) is not None


def test_single_head_guard_accepts_linear_chain(tmp_path: Path):
    script_dir = _make_synthetic_script_dir(
        tmp_path,
        [("rev_a", None), ("rev_b", "rev_a")],
    )
    assert assert_single_alembic_head(script_dir) == "rev_b"


def test_single_head_guard_rejects_two_heads_sharing_a_parent(tmp_path: Path):
    script_dir = _make_synthetic_script_dir(
        tmp_path,
        [
            ("rev_base", None),
            ("rev_branch_1", "rev_base"),
            ("rev_branch_2", "rev_base"),
        ],
    )
    with pytest.raises(AssertionError) as exc_info:
        assert_single_alembic_head(script_dir)
    msg = str(exc_info.value)
    assert "found 2" in msg
    assert "rev_branch_1" in msg
    assert "rev_branch_2" in msg
    assert "rev_base" in msg


def test_single_head_guard_rejects_empty_versions_dir(tmp_path: Path):
    script_dir = _make_synthetic_script_dir(tmp_path, [])
    with pytest.raises(AssertionError) as exc_info:
        assert_single_alembic_head(script_dir)
    assert "found 0" in str(exc_info.value)


def test_single_head_guard_accepts_merge_revision_reconverging_two_heads(
    tmp_path: Path,
):
    script_dir = _make_synthetic_script_dir(
        tmp_path,
        [
            ("rev_base", None),
            ("rev_branch_1", "rev_base"),
            ("rev_branch_2", "rev_base"),
            ("rev_merge", ("rev_branch_1", "rev_branch_2")),
        ],
    )
    assert assert_single_alembic_head(script_dir) == "rev_merge"
