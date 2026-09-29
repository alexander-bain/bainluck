"""#9602 — a certain postseason game's row reads as a playoff game before game day. Real Postgres.

## the ship

Wild Card Game 2 (Phillies @ Braves, White Sox @ Astros, Wed 9/30) shows
"Playoff game" on /sports the day before, not a regular-season records chip
("PHI 88-74 · ATL 94-68").

## why real Postgres

The pass's unit tests (``test_certain_postseason_games_9216`` Part E) prove
which ids it hands the statement; only a database can prove what the statement's
``WHERE`` does to rows. Here the rows are real and the statement is the pass's own.

## the arms

* ship: a held Game 2 row reading ``'regular_season'`` becomes ``'playoff'``,
  and so does one with no importance yet;
* ``'championship'`` is never downgraded (the espn_helpers rule);
* controls: a row in ANOTHER league holding an id the MLB board names (the
  statement is scoped by league as well as id — ``espn_id`` is unique, so the
  league is the guard against a misfiled row), and an MLB row whose id is not in
  the list, are left alone (else every arm passes on a statement that marks
  everything);
* a dry run counts the rows and writes none; a second run marks nothing.

Reuses the #7617 database (``DELAY_CONTRACT_DATABASE_URL``, CI job
``search-recall``) and the #8796 file's table closure.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres #9602 playoff "
        "mark (CI job `search-recall` provisions a disposable one)"
    ),
)

MLB, NHL = "baseball_mlb", "icehockey_nhl"
PHI_ATL_G2, CHW_HOU_G2 = "401907972", "401907897"


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, Sport
    from app.services.database import Base

    # Same closure as the #8796 file, so either can run after the other.
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
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    async with maker() as session:
        mlb = Sport(key=MLB, name="MLB")
        nhl = Sport(key=NHL, name="NHL")
        session.add_all([mlb, nhl])
        await session.flush()

        def _row(sport, home, away, espn_id, importance):
            return Event(
                sport_id=sport.id,
                home_team_name=home,
                away_team_name=away,
                commence_time=tomorrow,
                status="scheduled",
                espn_id=espn_id,
                llm_importance=importance,
                win_probability_sources={},
            )

        rows = {
            # 15320701 on production 9/29 11:05Z.
            "phi_atl_g2": _row(mlb, "Atlanta Braves", "Philadelphia Phillies", PHI_ATL_G2, "regular_season"),
            # A row the enrichment has not reached yet.
            "chw_hou_g2": _row(mlb, "Houston Astros", "Chicago White Sox", CHW_HOU_G2, None),
            "world_series": _row(mlb, "New York Yankees", "Los Angeles Dodgers", "9602-ws", "championship"),
            "other_league": _row(nhl, "Utah Mammoth", "Colorado Avalanche", "9602-nhl", "regular_season"),
            "mlb_not_certain": _row(mlb, "Boston Red Sox", "New York Yankees", "9602-g3", "regular_season"),
        }
        session.add_all(list(rows.values()))
        await session.commit()
        ids = {name: row.id for name, row in rows.items()}

    yield maker, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


async def _importance(maker, ids) -> dict[str, str | None]:
    from app.models.models import Event

    async with maker() as session:
        rows = (
            await session.execute(
                select(Event.id, Event.llm_importance).where(Event.id.in_(list(ids.values())))
            )
        ).all()
    by_id = dict(rows)
    return {name: by_id[i] for name, i in ids.items()}


def _candidates():
    return [
        (MLB, SimpleNamespace(espn_id=PHI_ATL_G2)),
        (MLB, SimpleNamespace(espn_id=CHW_HOU_G2)),
        (MLB, SimpleNamespace(espn_id="9602-ws")),
        (MLB, SimpleNamespace(espn_id="9602-nhl")),
    ]


def _stats():
    return {"marked_playoff": 0, "marked_playoff_ids": [], "errors": []}


@needs_postgres
class TestThePlayoffMark:
    async def test_a_held_game_two_reads_playoff_and_nothing_else_moves(self, db):
        """THE SHIP + both controls. RED before #9602: the pass wrote no importance."""
        from app.tasks import espn_certain_postseason as task

        maker, ids = db
        held = {PHI_ATL_G2, CHW_HOU_G2, "9602-ws", "9602-nhl"}
        stats = _stats()
        async with maker() as session:
            await task._mark_playoff(session, _candidates(), held, True, stats)

        assert stats["errors"] == []
        assert sorted(stats["marked_playoff_ids"]) == sorted([ids["phi_atl_g2"], ids["chw_hou_g2"]])
        assert await _importance(maker, ids) == {
            "phi_atl_g2": "playoff",
            "chw_hou_g2": "playoff",
            "world_series": "championship",
            "other_league": "regular_season",
            "mlb_not_certain": "regular_season",
        }

    async def test_a_dry_run_counts_and_writes_nothing_and_a_second_run_marks_nothing(self, db):
        from app.tasks import espn_certain_postseason as task

        maker, ids = db
        held = {PHI_ATL_G2, CHW_HOU_G2, "9602-ws", "9602-nhl"}
        before = await _importance(maker, ids)

        dry = _stats()
        async with maker() as session:
            await task._mark_playoff(session, _candidates(), held, False, dry)
        assert dry["marked_playoff"] == 2
        assert await _importance(maker, ids) == before

        first, second = _stats(), _stats()
        async with maker() as session:
            await task._mark_playoff(session, _candidates(), held, True, first)
        async with maker() as session:
            await task._mark_playoff(session, _candidates(), held, True, second)
        assert first["marked_playoff"] == 2
        assert second["marked_playoff"] == 0 and second["marked_playoff_ids"] == []
