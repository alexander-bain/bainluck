"""A suspended match whose market still trades keeps its price stream. #9484, real Postgres.

WHAT WAS WRONG. Both venue sockets subscribed from events that were ``live`` or
``scheduled`` within 6 h. A row the graph suspends therefore dropped off the
socket at the next recycle, and its market froze at the last price while the
venue kept trading it. Specimen, 2026-09-28: Dickerson v Pereira (event
15320435, ``KXATPCHALLENGERMATCH-26SEP28DICPER``) went ``suspended`` by 20:45Z
with no score ever recorded; our outcomes stopped at 20:45Z; at 23:32Z Kalshi
was trading DIC .89/.90 and the page still said .51, "Last number 2 hours ago".

The rule (Alex, #9484): market lifecycle, not game phase, decides streaming.
For the ``suspended`` phase that is ``app.tasks.ws_slate.suspended_open_market_arm``
— an open market on an event suspended inside 24 h is subscribed.

WHY POSTGRES. The arm is one SQL predicate with an interval, a NULL-tolerant
status test and a status test, and each of its mutants fails in a different
direction; only the real database answering the shipped expression separates
them. Each venue's own slate function is read, not a copy.

THE CASES (one Kalshi and one Polymarket market each):

    the_suspended_match_still_trading ... THE SHIP. Started 7 h ago (past
                                          every 6 h horizon), suspended,
                                          market open. Fails without the arm.
    the_suspended_match_with_no_status .. FAIL-OPEN. Market status NULL, as
                                          production's nullable column allows.
                                          A plain ``!= 'resolved'`` drops it.
    the_suspended_match_settled ......... Market resolved. Kills an arm that
                                          lost its market test.
    the_suspension_from_yesterday ....... Started 30 h ago. Kills an arm that
                                          lost its floor.
    the_game_tomorrow ................... Scheduled +30 h. Kills an arm that
                                          lost its STATUS test — the floor is
                                          one-sided, so without the status
                                          clause every future row satisfies it.
    the_game_in_progress ................ Live control. Unchanged either way.

A slate is a read: it chooses what the socket subscribes to and writes no
event row, so a suspended match stays ``suspended`` while its market streams.
The wiring (each consumer's query calls these predicates) is pinned without a
database in ``tests/test_ws_slate_suspended_arm_wiring_9484.py``.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

#: The same disposable database as the #837 slate contract (CI provisions it
#: in the step before). Deliberately no fallback to `$DATABASE_URL`.
DB_URL = os.environ.get("WS_SLATE_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set WS_SLATE_DATABASE_URL to run the real-Postgres suspended-arm "
        "contract (CI does; the step fails on a skip)"
    ),
)

#: case -> (event status, hours from now to commence, market status or None)
CASES = {
    # -7 h: past every 6 h horizon (the scheduled arm's, #9425's recovery
    # window), as the specimen was at 6 h 22 m. Kalshi-only in production — no
    # Polymarket link — and the arm needs none.
    "the_suspended_match_still_trading": ("suspended", -7, "open"),
    "the_suspended_match_with_no_status": ("suspended", -7, None),
    "the_suspended_match_settled": ("suspended", -7, "resolved"),
    "the_suspension_from_yesterday": ("suspended", -30, "open"),
    "the_game_tomorrow": ("scheduled", 30, "open"),
    "the_game_in_progress": ("live", -1, "open"),
}


async def _engine_with_tables():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports", "teams", "venues", "events",
            "futures_markets", "futures_outcomes",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed(session):
    from sqlalchemy import text as sql_text

    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    sport = Sport(key="tennis_atp", name="ATP")
    session.add(sport)
    await session.flush()

    # Production's column is nullable (see the #837 contract for the read);
    # the model's is not, so the NULL control needs the deployed schema.
    await session.execute(
        sql_text("ALTER TABLE futures_markets ALTER COLUMN status DROP NOT NULL")
    )

    null_ids = []
    event_ids = {}
    for case, (status, hours, market_status) in CASES.items():
        event = Event(
            sport_id=sport.id,
            home_team_name=f"{case} Home",
            away_team_name=f"{case} Away",
            commence_time=now + timedelta(hours=hours),
            status=status,
        )
        session.add(event)
        await session.flush()
        event_ids[case] = event.id
        for source in ("kalshi", "polymarket"):
            market = FuturesMarket(
                source=source,
                external_id=f"{source}-{case}",
                name=f"{case} winner",
                event_id=event.id,
                # `default="open"` would overwrite a None at flush; the NULL is
                # written in SQL below instead.
                **({} if market_status is None else {"status": market_status}),
            )
            session.add(market)
            await session.flush()
            if market_status is None:
                null_ids.append(market.id)
            session.add(FuturesOutcome(
                market_id=market.id, name=case, external_id=f"{source}-{case}_yes",
            ))

    await session.execute(
        sql_text("UPDATE futures_markets SET status = NULL WHERE id = ANY(:ids)"),
        {"ids": null_ids},
    )
    await session.commit()

    stored = (await session.execute(
        sql_text("SELECT status FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": null_ids},
    )).scalars().all()
    assert stored == [None, None], f"NULL-status control did not land: {stored!r}"
    return event_ids


@pytest.fixture
async def selected():
    """{venue: {case: subscribed?}} from each venue's shipped slate predicate."""
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.tasks.kalshi_ws import _kalshi_slate_event_window
    from app.tasks.polymarket_ws import _slate_event_window, _slate_market_filter

    engine, maker = await _engine_with_tables()
    async with maker() as session:
        ids = await _seed(session)

    where_by_venue = {
        "kalshi": (_kalshi_slate_event_window(),),
        "polymarket": (_slate_event_window(), _slate_market_filter()),
    }
    out = {}
    async with maker() as session:
        for venue, clauses in where_by_venue.items():
            kept = {
                row.event_id
                for row in (await session.execute(
                    select(FuturesOutcome.id, FuturesMarket.event_id)
                    .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                    .join(Event, FuturesMarket.event_id == Event.id)
                    .where(
                        FuturesMarket.source == venue,
                        FuturesMarket.event_id.isnot(None),
                        *clauses,
                    )
                )).all()
            }
            out[venue] = {case: (eid in kept) for case, eid in ids.items()}
    await engine.dispose()
    yield out


VENUES = pytest.mark.parametrize("venue", ["kalshi", "polymarket"])


@needs_postgres
class TestASuspendedMatchStillTradingKeepsItsStream:

    @VENUES
    async def test_an_open_market_on_a_suspended_match_is_subscribed(
        self, selected, venue
    ):
        # THE SHIP — Dickerson v Pereira, in miniature.
        assert selected[venue]["the_suspended_match_still_trading"] is True

    @VENUES
    async def test_a_market_with_no_status_is_subscribed(self, selected, venue):
        assert selected[venue]["the_suspended_match_with_no_status"] is True

    @VENUES
    async def test_a_settled_market_on_a_suspended_match_is_not(
        self, selected, venue
    ):
        assert selected[venue]["the_suspended_match_settled"] is False

    @VENUES
    async def test_a_suspension_older_than_a_day_is_not(self, selected, venue):
        assert selected[venue]["the_suspension_from_yesterday"] is False

    @VENUES
    async def test_a_game_tomorrow_is_still_out_of_scope(self, selected, venue):
        assert selected[venue]["the_game_tomorrow"] is False

    @VENUES
    async def test_a_game_in_progress_still_streams(self, selected, venue):
        assert selected[venue]["the_game_in_progress"] is True
