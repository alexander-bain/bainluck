"""#3613's selector, executed against real Postgres — the half a fake session cannot reach.

`tests/test_polymarket_dark_linked_market_gets_a_price_3613.py` drives the whole
pass, but its recording session ANSWERS the selector instead of running it. So
every claim that file makes about *which* markets get picked is a claim about
SQL nothing has executed: `make_interval(hours => :lookback_hours)`, the
`NOT EXISTS` anti-join, the `NOT LIKE '0x%'` exclusion and the `ORDER BY` are all
unproved there. A raw-SQL typo in a beat task is invisible until the beat runs in
production and logs an error nobody reads.

This file is the twin of `test_linked_game_price_chain_real_postgres.py` for the
Polymarket side, and it is deliberately small: the population, then one write.

**Five rows, four of which must NOT be selected**, each excluded for a different
reason, because a selector that returns the right answer for one reason and the
wrong answer for three is indistinguishable from a correct one when the fixture
only holds the specimen:

    picked   the specimen — open, linked, 13.4 days out, ZERO legs
    skipped  has a leg already          (the anti-join)
    skipped  keyed by condition_id      (`/events?id=` cannot address it)
    skipped  20 days out                (outside the measured 14-day bound)
    skipped  resolved                   (`status = 'open'`)

The 13.4-day specimen is the point of the horizon, not an arbitrary date: the
Kalshi twin stops at 7 days, and #3602 is the issue that closed because of it.

There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`), so
CI is the environment that runs this — the `search-recall` job.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the dark-Polymarket selector "
            "against real Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

UTC = timezone.utc

#: The production specimen (2026-09-06): Gamma event id, and its moneyline leg.
SPECIMEN_EXTERNAL_ID = "972409"
SPECIMEN_TITLE = "UFC 331: Ozzy Diaz vs. Ryan Gandra (Middleweight, Early Prelims)"
MONEYLINE_CID = "0xf5200af34f486ef08072a3759b351021d4895123ed6a6ab338fbc5458147a365"
MONEYLINE_PRICE, MONEYLINE_BID, MONEYLINE_ASK = 0.295, 0.21, 0.38


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


async def _seed(session):
    """The five rows. Returns `{label: market_id}`."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    sport = Sport(key="mma_mixed_martial_arts", name="MMA", group="Fighting")
    session.add(sport)
    await session.flush()

    def _event(days):
        e = Event(
            sport_id=sport.id,
            home_team_name="Gandra",
            away_team_name="Diaz",
            commence_time=datetime.now(UTC) + timedelta(days=days),
            status="scheduled",
        )
        session.add(e)
        return e

    near, far = _event(13.4), _event(20)
    await session.flush()

    def _market(external_id, event, status="open"):
        m = FuturesMarket(
            source="polymarket",
            external_id=external_id,
            name=SPECIMEN_TITLE,
            category="championship",
            market_tier=5,
            status=status,
            event_id=event.id,
        )
        session.add(m)
        return m

    ids = {
        "specimen": _market(SPECIMEN_EXTERNAL_ID, near),
        "already_has_a_leg": _market("111111", near),
        "condition_id_keyed": _market("0xdeadbeef", near),
        "beyond_the_horizon": _market("222222", far),
        "resolved": _market("333333", near, status="resolved"),
    }
    await session.flush()

    session.add(
        FuturesOutcome(
            market_id=ids["already_has_a_leg"].id,
            external_id="0xalready",
            name="Somebody",
            current_probability=0.5,
            rank=1,
        )
    )
    await session.commit()
    return {k: m.id for k, m in ids.items()}


async def _select(session):
    """Execute the shipping selector, with the shipping bound values."""
    from app.tasks.polymarket import (
        LINKED_POLY_BOOK_HORIZON_DAYS,
        LINKED_POLY_BOOK_LOOKBACK_HOURS,
        _LINKED_POLY_BOOKS_SQL,
        _LINKED_POLY_MAX_MARKETS,
    )

    rows = (
        await session.execute(
            _LINKED_POLY_BOOKS_SQL,
            {
                "lookback_hours": LINKED_POLY_BOOK_LOOKBACK_HOURS,
                "horizon_days": LINKED_POLY_BOOK_HORIZON_DAYS,
                "max_markets": _LINKED_POLY_MAX_MARKETS,
            },
        )
    ).fetchall()
    return rows


class TestTheSelectorAgainstRealPostgres:
    async def test_it_picks_the_specimen_and_nothing_else(self, pg_session):
        ids = await _seed(pg_session)
        rows = await _select(pg_session)
        assert [r.id for r in rows] == [ids["specimen"]], (
            "the five-row fixture excludes four rows for four different reasons; "
            "any other answer means one of those clauses is not doing its job"
        )

    async def test_the_row_carries_what_the_pass_reads_off_it(self, pg_session):
        """The pass reads `.id`, `.external_id`, `.name` and `.event_id`. A
        column renamed out of the SELECT is an AttributeError at beat time."""
        await _seed(pg_session)
        (row,) = await _select(pg_session)
        assert str(row.external_id) == SPECIMEN_EXTERNAL_ID
        assert row.name == SPECIMEN_TITLE
        assert row.event_id is not None

    async def test_a_started_but_unflipped_event_is_still_selected(self, pg_session):
        """The lookback, executed. A game whose row never flipped to `live`
        must not drop out of the population an hour after kick-off — those are
        the rows most likely to be looked at."""
        ids = await _seed(pg_session)
        await pg_session.execute(
            text(
                "UPDATE events SET commence_time = NOW() - INTERVAL '2 hours' "
                "WHERE id = (SELECT event_id FROM futures_markets WHERE id = :m)"
            ),
            {"m": ids["specimen"]},
        )
        await pg_session.commit()
        assert [r.id for r in await _select(pg_session)] == [ids["specimen"]]

    async def test_seven_hours_after_kickoff_it_drops_out(self, pg_session):
        """...and the lookback is a bound, not an open door."""
        ids = await _seed(pg_session)
        await pg_session.execute(
            text(
                "UPDATE events SET commence_time = NOW() - INTERVAL '7 hours' "
                "WHERE id = (SELECT event_id FROM futures_markets WHERE id = :m)"
            ),
            {"m": ids["specimen"]},
        )
        await pg_session.commit()
        assert await _select(pg_session) == []

    async def test_a_live_event_is_in_scope_whatever_its_clock_says(self, pg_session):
        ids = await _seed(pg_session)
        await pg_session.execute(
            text(
                "UPDATE events SET status = 'live', "
                "       commence_time = NOW() - INTERVAL '3 days' "
                "WHERE id = (SELECT event_id FROM futures_markets WHERE id = :m)"
            ),
            {"m": ids["specimen"]},
        )
        await pg_session.commit()
        assert [r.id for r in await _select(pg_session)] == [ids["specimen"]]


class TestThePassWritesToRealPostgres:
    async def test_the_dark_market_ends_the_pass_holding_the_venues_price(
        self, pg_session
    ):
        """End to end on real rows: the selector picks it, the writer fills it.

        Only the network is stubbed. The ON CONFLICT clause, the explicit NULL
        `is_winner` against a column that DEFAULTS TO FALSE (CAL-P1004R — the
        trap a fake session cannot show you, because only Postgres applies the
        default), and the snapshot's foreign key are all exercised for real.
        """
        from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
        from app.tasks import polymarket as poly

        ids = await _seed(pg_session)

        venue = PolymarketEvent(
            id=SPECIMEN_EXTERNAL_ID,
            title=SPECIMEN_TITLE,
            active=True,
            neg_risk=False,
            markets=[
                PolymarketMarket(
                    condition_id=MONEYLINE_CID,
                    question=SPECIMEN_TITLE,
                    outcomes=["Ozzy Diaz", "Ryan Gandra"],
                    outcome_prices=[MONEYLINE_PRICE, 0.705],
                    best_bid=MONEYLINE_BID,
                    best_ask=MONEYLINE_ASK,
                    active=True,
                ),
            ],
        )

        class _Service:
            async def get_events_by_ids(self, event_ids):
                return [{"id": i} for i in event_ids]

            def _parse_event(self, raw):
                return venue if raw["id"] == SPECIMEN_EXTERNAL_ID else None

            async def close(self):
                return None

        @asynccontextmanager
        async def _session_cm():
            yield pg_session

        with ExitStack() as es:
            es.enter_context(patch("app.tasks.polymarket.get_task_session", _session_cm))
            es.enter_context(
                patch(
                    "app.services.polymarket_api.PolymarketAPIService",
                    lambda *a, **k: _Service(),
                )
            )
            stats = await poly._refresh_linked_polymarket_books()

        assert stats["outcomes_created"] == 1, stats
        assert stats["snapshots_written"] == 1, stats

        row = (
            await pg_session.execute(
                text(
                    "SELECT external_id, current_probability, current_yes_bid, "
                    "       is_winner, resolution_source "
                    "  FROM futures_outcomes WHERE market_id = :m"
                ),
                {"m": ids["specimen"]},
            )
        ).one()
        assert row.external_id == MONEYLINE_CID
        assert float(row.current_probability) == pytest.approx(MONEYLINE_PRICE)
        assert float(row.current_yes_bid) == pytest.approx(MONEYLINE_BID)
        assert row.is_winner is None, (
            "the column DEFAULTS TO FALSE, so a stored False here would be an "
            "affirmative graded loss on a fight nobody has watched (CAL-P1004R)"
        )
        assert row.resolution_source is None

        snap = (
            await pg_session.execute(
                text(
                    "SELECT s.bookmaker, s.probability FROM futures_odds_snapshots s "
                    "  JOIN futures_outcomes o ON o.id = s.outcome_id "
                    " WHERE o.market_id = :m"
                ),
                {"m": ids["specimen"]},
            )
        ).one()
        assert snap.bookmaker == "polymarket"
        assert float(snap.probability) == pytest.approx(MONEYLINE_PRICE)

    async def test_running_it_twice_writes_nothing_the_second_time(self, pg_session):
        """Idempotence, on the real unique index rather than on a promise. The
        pass selects markets with no legs, so the second run must not even see
        it — and if a race put it back in scope, ON CONFLICT DO NOTHING is what
        stops a duplicate snapshot landing on someone else's leg."""
        from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
        from app.tasks import polymarket as poly

        ids = await _seed(pg_session)
        venue = PolymarketEvent(
            id=SPECIMEN_EXTERNAL_ID,
            title=SPECIMEN_TITLE,
            active=True,
            neg_risk=False,
            markets=[
                PolymarketMarket(
                    condition_id=MONEYLINE_CID,
                    question=SPECIMEN_TITLE,
                    outcomes=["Ozzy Diaz", "Ryan Gandra"],
                    outcome_prices=[MONEYLINE_PRICE, 0.705],
                    best_bid=MONEYLINE_BID,
                    best_ask=MONEYLINE_ASK,
                    active=True,
                ),
            ],
        )

        class _Service:
            async def get_events_by_ids(self, event_ids):
                return [{"id": i} for i in event_ids]

            def _parse_event(self, raw):
                return venue if raw["id"] == SPECIMEN_EXTERNAL_ID else None

            async def close(self):
                return None

        @asynccontextmanager
        async def _session_cm():
            yield pg_session

        with ExitStack() as es:
            es.enter_context(patch("app.tasks.polymarket.get_task_session", _session_cm))
            es.enter_context(
                patch(
                    "app.services.polymarket_api.PolymarketAPIService",
                    lambda *a, **k: _Service(),
                )
            )
            first = await poly._refresh_linked_polymarket_books()
            second = await poly._refresh_linked_polymarket_books()

        assert first["outcomes_created"] == 1
        assert second["terminal"] == "no_dark_linked_markets_in_window"
        legs = (
            await pg_session.execute(
                text("SELECT COUNT(*) FROM futures_outcomes WHERE market_id = :m"),
                {"m": ids["specimen"]},
            )
        ).scalar()
        assert legs == 1
