"""#11152 (CERT-4179 ``11152-PERSIST-REAL-PG-CAS-UNDO-GUARDS``), against a real PostgreSQL.

The unplayed-series-game sweep reads a row, reads ESPN's boards, then voids the
row only while it is as the plan saw it. That guard is SQL (``NULLIF``,
``IS NOT DISTINCT FROM``, an exact ``commence_time``), and so is the undo's
(``status = 'voided'`` and JSONB ``@>``), so a recording session cannot run
either. The grader showed removing the score clause from the write survives
every committed unit test; this file is the gate that catches it.

It also pins the notice-47(c) boundary on a real server: the sweep never
creates its backup table. Without the attended packet's table it writes
nothing; with it, the full pass banks, voids, reads back and undoes.

A narrow ``events`` table in a private schema, so this runs on the lane VM's
Postgres 14 as well as in CI. The population read is swapped for a narrow
select (its window is ``now()``-relative and the specimen is dated October
2026); the boards are the recorded ESPN fixture.
"""
import contextlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from app.tasks import unplayed_series_game_sweep as sweep
from app.utils.unplayed_series_games import plan_unplayed_series_games, retirement_tag

from tests.test_unplayed_series_games_11152 import _boards, _Raw, _specimen_rows

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #11152 "
            "write/undo guard gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "unplayed_series_game_gate_11152"
GAME_5, CLINCH_ESPN = 15330460, "401908033"
TAG = retirement_tag(CLINCH_ESPN)

#: The attended packet's DDL (artifacts/live-11152/apply_15330460.sql), verbatim
#: in shape. The sweep may only ever find this table, never make it.
_PACKET_BACKUP_DDL = (
    f"CREATE TABLE {sweep.BAK_TABLE} ("
    "event_id bigint PRIMARY KEY, clinching_espn_id text NOT NULL, "
    "old_status text NOT NULL, old_tags text NOT NULL, old_xmin text, "
    "banked_at timestamptz NOT NULL DEFAULT now())"
)

_NARROW_POPULATION_SQL = """
SELECT id, home_team_name, away_team_name, commence_time, home_score, away_score,
       espn_id, status, CAST(COALESCE(event_tags, '[]'::jsonb) AS text) AS tags_text
  FROM events
 WHERE status NOT IN ('voided', 'merged')
 ORDER BY id
"""


def _restore_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "restore_11152_unplayed_series_games.py"
    spec = importlib.util.spec_from_file_location("restore_11152_pg", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def pg(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # search_path is pinned on EVERY pooled connection: the sweep commits per
    # row, and a commit may hand the session a different connection.
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _task_session():
        async with maker() as s:
            yield s

    async def _load_rows(session, **_kw):
        return (await session.execute(text(_NARROW_POPULATION_SQL))).all()

    async def _fetch_boards(_days, _sport_key=sweep.SPORT_KEY):
        return _boards()

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _task_session)
    monkeypatch.setattr(sweep, "load_rows", _load_rows)
    monkeypatch.setattr(sweep, "fetch_boards", _fetch_boards)

    async with maker() as s:
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
        await s.execute(
            text(
                f"CREATE TABLE {_SCHEMA}.events (id bigint PRIMARY KEY, sport_id int NOT NULL, "
                "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
                "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
                "espn_id varchar(50), home_score int, away_score int, event_tags jsonb)"
            )
        )
        for r in _specimen_rows():
            await s.execute(
                text(
                    "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                    "commence_time, status, espn_id, home_score, away_score, event_tags) "
                    "VALUES (:id, 1, :home, :away, :start, :status, :espn, :h, :a, "
                    "CAST(:tags AS jsonb))"
                ),
                {
                    "id": r.event_id,
                    "home": r.home_team_name,
                    "away": r.away_team_name,
                    "start": r.commence_time,
                    "status": r.status,
                    "espn": r.espn_id,
                    "h": r.home_score,
                    "a": r.away_score,
                    "tags": json.dumps(["keep:before"]),
                },
            )
        await s.commit()
        yield s
        await s.rollback()
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.commit()
    await engine.dispose()


async def _create_packet_table(s):
    await s.execute(text(_PACKET_BACKUP_DDL))
    await s.commit()


async def _game_5(s):
    return (
        await s.execute(
            text("SELECT status, espn_id, home_score, event_tags FROM events WHERE id = :id"),
            {"id": GAME_5},
        )
    ).one()


async def _table_exists(s) -> bool:
    return bool(
        (await s.execute(text(f"SELECT to_regclass('{sweep.BAK_TABLE}') IS NOT NULL"))).scalar_one()
    )


class TestTheSweepNeverMakesItsBackupTable:
    async def test_without_the_packets_table_nothing_is_written_and_no_table_appears(self, pg):
        summary = await sweep.run_unplayed_series_game_sweep(apply=True)
        assert (summary["terminal"], summary["refused"]) == ("failed", "no_backup_table")
        assert summary["to_write"] == 1 and summary["written"] == 0
        assert (await _game_5(pg)).status == "scheduled"
        assert not await _table_exists(pg)


class TestTheFullPassBanksVoidsAndUndoes:
    async def test_banked_then_voided_then_undone_keeping_a_later_sibling_tag(self, pg):
        await _create_packet_table(pg)
        summary = await sweep.run_unplayed_series_game_sweep(apply=True)
        assert summary["terminal"] == "complete", summary
        assert (summary["written"], summary["banked"], summary["voided"]) == (1, 1, [GAME_5])

        bank = (await pg.execute(text(f"SELECT * FROM {sweep.BAK_TABLE}"))).one()
        assert (bank.event_id, bank.clinching_espn_id, bank.old_status) == (
            GAME_5,
            CLINCH_ESPN,
            "scheduled",
        )
        assert json.loads(bank.old_tags) == ["keep:before"]
        row = await _game_5(pg)
        assert (row.status, row.event_tags) == ("voided", ["keep:before", TAG])
        assert {
            r.status for r in (await pg.execute(text("SELECT status FROM events WHERE id <> :id"), {"id": GAME_5})).all()
        } <= {"scheduled", "completed"}

        await pg.execute(
            text("UPDATE events SET event_tags = event_tags || '[\"keep:after\"]'::jsonb WHERE id = :id"),
            {"id": GAME_5},
        )
        await pg.commit()
        restore = _restore_module()
        plan = (await pg.execute(text(restore._PLAN_SQL))).all()
        assert await restore.restore_rows(pg, restore.still_retired(plan)) == (1, [])
        row = await _game_5(pg)
        assert (row.status, row.event_tags) == ("scheduled", ["keep:before", "keep:after"])

    async def test_a_second_pass_after_the_undo_keeps_the_first_banked_value(self, pg):
        await _create_packet_table(pg)
        await sweep.run_unplayed_series_game_sweep(apply=True)
        restore = _restore_module()
        plan = (await pg.execute(text(restore._PLAN_SQL))).all()
        await restore.restore_rows(pg, restore.still_retired(plan))
        await pg.execute(text("UPDATE events SET status = 'live' WHERE id = :id"), {"id": GAME_5})
        await pg.commit()
        summary = await sweep.run_unplayed_series_game_sweep(apply=True)
        assert (summary["written"], summary["banked"]) == (1, 0)
        assert (await pg.execute(text(f"SELECT old_status FROM {sweep.BAK_TABLE}"))).scalar_one() == "scheduled"


#: What can land on the row between the plan's read and its write. Each one is
#: a clause of the compare-and-set; each must stop the write on its own.
_MOVES = {
    "espn_id": "espn_id = '401908034'",
    "status": "status = 'completed'",
    "home_score": "home_score = 2",
    "away_score": "away_score = 3",
    "commence_time": "commence_time = commence_time + interval '1 day'",
}


class TestTheWriteLandsOnlyOnTheRowThePlanJudged:
    async def _plan(self, pg):
        raw = [_Raw(r) for r in _specimen_rows()]
        retirements = plan_unplayed_series_games(_specimen_rows(), _boards()).retirements
        assert [r.event_id for r in retirements] == [GAME_5]
        return retirements, sweep.observed_state([r for r in raw if r.id == GAME_5])

    async def test_the_unchanged_row_is_voided(self, pg):
        retirements, observed = await self._plan(pg)
        assert await sweep.write_retirements(pg, retirements, observed) == (1, [])
        assert await sweep.read_back(pg, [GAME_5], observed) == ([GAME_5], [])

    @pytest.mark.parametrize("column", sorted(_MOVES))
    async def test_a_row_that_moved_is_left_alone(self, pg, column):
        retirements, observed = await self._plan(pg)
        await pg.execute(text(f"UPDATE events SET {_MOVES[column]} WHERE id = :id"), {"id": GAME_5})
        await pg.commit()
        assert await sweep.write_retirements(pg, retirements, observed) == (0, [])
        assert await sweep.read_back(pg, [GAME_5], observed) == ([], [GAME_5])
        assert (await _game_5(pg)).status != "voided"
        assert TAG not in (await _game_5(pg)).event_tags


class TestTheUndoTouchesOnlyWhatTheSweepVoided:
    async def test_a_banked_row_no_longer_voided_or_no_longer_tagged_is_left_alone(self, pg):
        await _create_packet_table(pg)
        await sweep.run_unplayed_series_game_sweep(apply=True)
        restore = _restore_module()
        plan = (await pg.execute(text(restore._PLAN_SQL))).all()

        await pg.execute(text("UPDATE events SET status = 'completed' WHERE id = :id"), {"id": GAME_5})
        await pg.commit()
        assert await restore.restore_rows(pg, plan) == (0, [])
        assert (await _game_5(pg)).status == "completed"

        await pg.execute(
            text("UPDATE events SET status = 'voided', event_tags = '[\"unrelated\"]'::jsonb WHERE id = :id"),
            {"id": GAME_5},
        )
        await pg.commit()
        assert await restore.restore_rows(pg, plan) == (0, [])
        assert (await _game_5(pg)).status == "voided"
