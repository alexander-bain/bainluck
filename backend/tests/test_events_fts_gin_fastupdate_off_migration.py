"""#10090: `events_fts_gin_fastupdate_off` covers the two GIN indexes no migration creates.

THE SHIP. A live score or price write on `events` never stops for seconds to
merge a search index's backlog inside its own statement.

These are the shape guards that run without a database. The behaviour gate is
`tests/integration/test_events_writes_never_merge_a_gin_backlog_10090_pg.py`.
Its census reads every `events` GIN from `pg_index` after both revisions and
requires `fastupdate=off` on each one.

Pins:
* together with its parent, the migration names every GIN index production's
  `events` carries (read 2026-10-29 19:45Z), and no index twice;
* it chains on the parent and is the single head;
* both batches open with `LOCK TABLE events IN ACCESS EXCLUSIVE MODE`;
* each ALTER is `ALTER INDEX IF EXISTS … SET (fastupdate = off)`, because a
  database built from migrations alone does not have these indexes;
* the downgrade resets `fastupdate` only, on these two only;
* the script never commits mid-batch, so `alembic/env.py` keeps its lock retry.
"""

from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.utils.migration_lock_budget import batch_is_retryable

BACKEND = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
NAME = "events_fts_gin_fastupdate_off"
PARENT = "events_gin_fastupdate_off"
SOURCE = (VERSIONS / f"{NAME}.py").read_text(encoding="utf-8")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load(NAME)
PARENT_MIGRATION = _load(PARENT)

LOCK_EVENTS = "LOCK TABLE events IN ACCESS EXCLUSIVE MODE"

#: Every GIN index on production's `events` (db-query, 2026-10-29 19:45Z,
#: artifacts/latency-10090-fts-gin-20261029T1945Z/idxdef.json), plus the
#: duplicate `_team_name_trgm` pair the parent still names with IF EXISTS
#: (dropped in attended psql before G2).
PRODUCTION_EVENTS_GIN = {
    "ix_events_event_tags",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_fts_home",
    "ix_events_fts_away",
}
DROPPED_DUPLICATES = {"ix_events_home_team_name_trgm", "ix_events_away_team_name_trgm"}


def test_revision_id_fits_gotcha_1_chains_on_the_parent_and_is_the_single_head():
    assert MIGRATION.revision == NAME
    assert len(MIGRATION.revision) <= 32
    assert MIGRATION.down_revision == PARENT
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert list(script.get_heads()) == [NAME]


def test_with_its_parent_it_names_every_production_events_gin_once():
    names = PARENT_MIGRATION.INDEXES + MIGRATION.INDEXES
    assert len(names) == len(set(names))
    assert set(names) == PRODUCTION_EVENTS_GIN | DROPPED_DUPLICATES
    assert set(MIGRATION.INDEXES) == {"ix_events_fts_home", "ix_events_fts_away"}


def test_upgrade_sets_only_fastupdate_off_after_the_table_lock():
    assert MIGRATION.UPGRADE_SQL == (LOCK_EVENTS,) + tuple(
        f"ALTER INDEX IF EXISTS {name} SET (fastupdate = off)"
        for name in MIGRATION.INDEXES
    )


def test_downgrade_resets_only_fastupdate_on_these_two():
    assert MIGRATION.DOWNGRADE_SQL == (LOCK_EVENTS,) + tuple(
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
