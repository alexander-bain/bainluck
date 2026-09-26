"""One failed statement does not discard the ESPN pass. #8796, real Postgres.

``sync_espn_live_events`` is ONE transaction (``get_task_session`` commits once,
at the end). Measured on production 9/26 04:24–04:42Z: 5 of 17 passes lost a
40P01 deadlock inside ``compute_and_write_stat_model``, whose ``except`` logged
it and carried on, so the session was left aborted — every later sport and step
raised ``InFailedSQLTransactionError``, and the final ``COMMIT`` on an aborted
transaction is a ROLLBACK: the pass wrote nothing, for any sport, while the
task reported success.

Only Postgres has that behaviour; a fake session cannot abort. So this file uses
real statements that fail the real way:

* the stat_model writer's own ``UPDATE events SET win_probability_sources`` is
  made to lose a real row lock (a second connection holds ``FOR UPDATE``; the
  pass runs under a short ``lock_timeout``) — the same statement, and the same
  class of lock failure, as the production deadlock;
* the whole task runs two sports, and the first one's step aborts the
  transaction with a real SQL error — once with a statement after the swallowed
  failure, once with the swallowed failure as the step's last act (then it is
  the ``RELEASE SAVEPOINT`` that fails).

The claim tested every time is the pass's: the writes around the failure COMMIT.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text, update

#: The #7617 step's disposable database, as the #8755 file uses. This file
#: drops and creates only the tables it names, in its own CI step after those.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres ESPN-pass "
        "contract (CI job `search-recall` provisions a disposable one)"
    ),
)

MLB, NHL = "baseball_mlb", "icehockey_nhl"


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, Sport
    from app.services.database import Base

    # The #7617 file runs first on this database and leaves `futures_markets`
    # and `futures_outcomes` behind; both point at `events`, so a drop that
    # omits them dies with `DependentObjectsStillExist` (CI, 5a989a6cd2). Same
    # closure as that file, so either one can run after the other.
    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "win_prob_snapshots",
            "futures_markets",
            "futures_outcomes",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with maker() as session:
        nhl = Sport(key=NHL, name="NHL")
        mlb = Sport(key=MLB, name="MLB")
        session.add_all([nhl, mlb])
        await session.flush()

        def _row(sport, home, away, espn_id):
            return Event(
                sport_id=sport.id,
                home_team_name=home,
                away_team_name=away,
                commence_time=now - timedelta(minutes=20),
                commence_time_source="espn",
                status="live",
                espn_id=espn_id,
                # An opening price, so the model is not a prior-less coin flip
                # that defers to the market (#8522) — it computes and WRITES.
                opening_home_probability=0.55,
                win_probability_sources={},
            )

        rows = {
            "the_stat_model_row": _row(nhl, "San Jose Sharks", "Anaheim Ducks", "401803915"),
            "a_sibling_the_pass_also_writes": _row(nhl, "Los Angeles Kings", "Vegas Golden Knights", "8796-2"),
            "the_failing_sports_row": _row(mlb, "Seattle Mariners", "Los Angeles Angels", "8796-3"),
            "the_next_sports_row": _row(nhl, "Utah Mammoth", "Colorado Avalanche", "8796-4"),
        }
        session.add_all(list(rows.values()))
        await session.commit()
        ids = {name: row.id for name, row in rows.items()}

    yield engine, maker, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


async def _read(maker, event_id):
    from app.models.models import Event

    async with maker() as session:
        return (
            await session.execute(
                select(Event.period, Event.game_clock, Event.win_probability_sources)
                .where(Event.id == event_id)
            )
        ).one()


def _puck_drop():
    from tests.test_priorless_stat_model_defers_to_market_8522 import (
        _puck_drop_board_row,
    )

    return _puck_drop_board_row()


@needs_postgres
class TestTheStatModelWriterLosesALock:
    async def test_the_pass_commits_the_writes_around_it(self, db):
        """THE SHIP. RED before #8796: the lock failure left the session aborted,
        the write AFTER it raised InFailedSQLTransactionError, and the COMMIT
        discarded the write BEFORE it too."""
        from app.models.models import Event
        from app.utils.espn_helpers import compute_and_write_stat_model

        engine, maker, ids = db
        target, sibling = ids["the_stat_model_row"], ids["a_sibling_the_pass_also_writes"]

        # Another writer holds the stat_model row, as a live-state
        # compare-and-write did in production (the 40P01 report).
        holder = await engine.connect()
        holder_tx = await holder.begin()
        await holder.execute(
            text("SELECT id FROM events WHERE id = :id FOR UPDATE"), {"id": target}
        )
        try:
            stats: dict = {}
            async with maker() as session:
                await session.execute(text("SET LOCAL lock_timeout = '300ms'"))
                event = (
                    await session.execute(select(Event).where(Event.id == target))
                ).scalar_one()
                # Earlier in the pass: another game's write.
                await session.execute(
                    update(Event).where(Event.id == sibling).values(period="1st Period")
                )

                wrote = await compute_and_write_stat_model(
                    session, event, _puck_drop(), NHL, stats
                )
                # The live loop goes on reading this row. Had the savepoint's
                # rollback expired it, this attribute read would lazy-load in
                # async code and raise (gotcha #6), costing the sport anyway.
                assert event.status == "live"
                assert "stat_model" not in (event.win_probability_sources or {})

                # Later in the pass: a statement on the same session.
                await session.execute(
                    update(Event).where(Event.id == sibling).values(game_clock="12:00")
                )
                await session.commit()
        finally:
            await holder_tx.rollback()
            await holder.close()

        assert wrote is False
        assert stats.get("stat_model_errors") == 1, stats
        period, clock, _ = await _read(maker, sibling)
        assert (period, clock) == ("1st Period", "12:00"), (
            "the pass lost the writes around the failed stat_model statement"
        )
        _, _, sources = await _read(maker, target)
        assert "stat_model" not in (sources or {}), (
            "the failed stat_model reading landed anyway"
        )

    async def test_an_uncontended_row_still_gets_its_reading(self, db):
        """THE KILL CONTROL. A savepoint that swallowed every write would pass
        the ship; here the same writer, uncontended, must land its number."""
        from app.models.models import Event
        from app.utils.espn_helpers import compute_and_write_stat_model

        _, maker, ids = db
        target = ids["the_stat_model_row"]
        stats: dict = {}
        async with maker() as session:
            event = (
                await session.execute(select(Event).where(Event.id == target))
            ).scalar_one()
            wrote = await compute_and_write_stat_model(
                session, event, _puck_drop(), NHL, stats
            )
            await session.commit()

        assert wrote is True
        assert "stat_model_errors" not in stats
        _, _, sources = await _read(maker, target)
        assert "stat_model" in sources, sources


class _Espn:
    async def get_scoreboard(self, sport_key, date=None, groups=None):
        return [object()]  # a non-empty board: the sport is served

    async def close(self):
        pass


def _wire(monkeypatch, maker, ids, failing_step):
    """The real task, with only its I/O replaced: ESPN answers both sports, the
    session is a real one committed once at the end (as `get_task_session`
    does), and each sport's step makes one real write."""
    import app.services.espn_api as espn_api
    import app.tasks.espn_sync as espn_sync
    import app.utils.espn_helpers as helpers
    from app.models.models import Event

    @asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _noop(*a, **k):
        return None

    async def _keys(session):
        return [MLB, NHL], []

    async def _decide(*a, **k):
        return {}

    async def _live(session, sport_key, espn_events, stats, *a, **k):
        if sport_key == MLB:
            await failing_step(session, ids["the_failing_sports_row"])
        else:
            await session.execute(
                update(Event)
                .where(Event.id == ids["the_next_sports_row"])
                .values(period="2nd Period")
            )

    monkeypatch.setattr(espn_sync, "get_task_session", _session)
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: _Espn())
    monkeypatch.setattr(espn_sync, "_find_sport_keys_to_sync", _keys)
    for name in (
        "_settle_authority_stragglers",
        "_settle_deep_authority_stragglers",
        "_recover_unstarted_authority_fixtures",
        "_act_on_failovers",
    ):
        monkeypatch.setattr(espn_sync, name, _noop)
    monkeypatch.setattr(espn_sync, "_decide_failovers", _decide)
    monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
    for name in (
        "sync_scheduled_events",
        "fetch_completed_box_scores",
        "fetch_live_box_scores",
        "backfill_missing_scores",
    ):
        monkeypatch.setattr(helpers, name, _noop)


async def _write_then_swallow(session, event_id, *, then_write: bool):
    """The stat_model shape: a write, a failure caught and logged, and (in one
    variant) the step going on to another statement on the dead session."""
    from app.models.models import Event

    await session.execute(
        update(Event).where(Event.id == event_id).values(period="Top 9th")
    )
    try:
        await session.execute(text("SELECT 1 / 0"))
    except Exception:
        pass
    if then_write:
        await session.execute(
            update(Event).where(Event.id == event_id).values(game_clock="0:00")
        )


@needs_postgres
class TestOneSportsFailureDoesNotDiscardThePass:
    @pytest.mark.parametrize("then_write", [True, False], ids=["then_writes", "fails_last"])
    async def test_the_next_sport_commits(self, db, monkeypatch, then_write):
        """THE SHIP, at the task. RED before #8796: NHL raised
        InFailedSQLTransactionError behind MLB's failure, and the pass's one
        COMMIT discarded everything — including writes that had succeeded."""
        from app.tasks.espn_sync import _sync_espn_live_events

        _, maker, ids = db

        async def _failing(session, event_id):
            await _write_then_swallow(session, event_id, then_write=then_write)

        _wire(monkeypatch, maker, ids, _failing)
        stats = await _sync_espn_live_events()

        period, _, _ = await _read(maker, ids["the_next_sports_row"])
        assert period == "2nd Period", (
            "a failure in MLB's step discarded NHL's write", stats["errors"]
        )
        assert [e.split(":")[0] for e in stats["errors"]] == [MLB], stats["errors"]
        # MLB's own step is rolled back whole: half a step is not a write.
        mlb_period, mlb_clock, _ = await _read(maker, ids["the_failing_sports_row"])
        assert (mlb_period, mlb_clock) == (None, None)

    async def test_a_clean_pass_commits_both_sports(self, db, monkeypatch):
        """THE KILL CONTROL. Savepoints that rolled back a HEALTHY step would
        pass the ship (NHL still writes) and fail here on MLB."""
        from app.models.models import Event
        from app.tasks.espn_sync import _sync_espn_live_events

        _, maker, ids = db

        async def _clean(session, event_id):
            await session.execute(
                update(Event).where(Event.id == event_id).values(period="Top 9th")
            )

        _wire(monkeypatch, maker, ids, _clean)
        stats = await _sync_espn_live_events()

        assert stats["errors"] == []
        assert (await _read(maker, ids["the_failing_sports_row"]))[0] == "Top 9th"
        assert (await _read(maker, ids["the_next_sports_row"]))[0] == "2nd Period"
