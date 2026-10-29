"""#10090: `events_gin_fastupdate_off` covers every `events` GIN and nothing else.

THE SHIP. A live score or price write on `events` never stops for seconds to
merge a search index's backlog inside its own statement.

These are the shape guards that run without a database. The behaviour gate —
writes leave no pending pages after the upgrade, and the downgrade restores
them — is `tests/integration/test_events_writes_never_merge_a_gin_backlog_10090_pg.py`.

Pins:
* every GIN index any migration creates on `events` is in the migration, so no
  writer is left with a list to merge (a sixth one must join by an edit);
* each statement is `ALTER INDEX IF EXISTS … SET (fastupdate = off)`, so the
  attended drop of the duplicate pair can run before or after it;
* the downgrade resets `fastupdate` only, keeping production's
  `gin_pending_list_limit` values;
* the script never commits mid-batch, so `alembic/env.py` keeps its lock retry.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.utils.migration_lock_budget import batch_is_retryable

BACKEND = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
NAME = "events_gin_fastupdate_off"
SOURCE = (VERSIONS / f"{NAME}.py").read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(NAME, VERSIONS / f"{NAME}.py")
MIGRATION = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MIGRATION)

_EVENTS_GIN = re.compile(
    r"CREATE INDEX\s+(?:CONCURRENTLY\s+)?(?:IF NOT EXISTS\s+)?(\w+)\s+"
    r"ON\s+events\s+USING\s+gin\b",
    re.IGNORECASE,
)


def _events_gin_indexes_created_by_migrations() -> set[str]:
    names: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        if path.stem == NAME:
            continue
        text = " ".join(path.read_text(encoding="utf-8").replace('"', " ").split())
        names.update(_EVENTS_GIN.findall(text))
    return names


def test_revision_id_fits_gotcha_1_and_is_the_single_head():
    assert MIGRATION.revision == NAME
    assert len(MIGRATION.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert list(script.get_heads()) == [NAME]
    assert script.get_revision(MIGRATION.down_revision) is not None


def test_every_events_gin_index_is_covered():
    created = _events_gin_indexes_created_by_migrations()
    assert created == {
        "ix_events_event_tags",
        "ix_events_home_trgm",
        "ix_events_away_trgm",
        "ix_events_home_team_name_trgm",
        "ix_events_away_team_name_trgm",
    }, "the census regex no longer sees the five production indexes"
    assert set(MIGRATION.INDEXES) == created
    assert len(MIGRATION.INDEXES) == len(created)


def test_the_write_path_index_goes_first():
    assert MIGRATION.INDEXES[0] == "ix_events_event_tags"


def test_upgrade_sets_only_fastupdate_off_and_tolerates_a_dropped_index():
    assert MIGRATION.UPGRADE_SQL == tuple(
        f"ALTER INDEX IF EXISTS {name} SET (fastupdate = off)"
        for name in MIGRATION.INDEXES
    )


def test_downgrade_resets_only_fastupdate():
    assert MIGRATION.DOWNGRADE_SQL == tuple(
        f"ALTER INDEX IF EXISTS {name} RESET (fastupdate)"
        for name in MIGRATION.INDEXES
    )
    assert all("gin_pending_list_limit" not in s for s in MIGRATION.DOWNGRADE_SQL)


def test_upgrade_and_downgrade_execute_exactly_those_statements(monkeypatch):
    executed: list[str] = []
    monkeypatch.setattr(MIGRATION, "op", SimpleNamespace(execute=executed.append))
    MIGRATION.upgrade()
    assert tuple(executed) == MIGRATION.UPGRADE_SQL
    executed.clear()
    MIGRATION.downgrade()
    assert tuple(executed) == MIGRATION.DOWNGRADE_SQL


def test_the_batch_keeps_envs_lock_retry():
    assert batch_is_retryable([SOURCE])
