"""#10090 — `PM_WS_UPCOMING_HOURS` narrows only the scheduled arm. Real Postgres.

At 13:40Z on 2026-10-30 the Polymarket socket's slate held 354 markets on live
games and 1,633 on games 2-6 h away, on a venue process at loop cpu 0.95.
Decision L would set the upcoming window to 3 h; this file proves what that
setting selects, against the shipped predicate, before anyone sets it.

    the_game_in_four_hours ..... THE SHIP. Dropped at 3, kept at 6.
    the_game_in_two_hours ...... Kept at both: the window narrowed, not closed.
    the_game_in_progress ....... Live arm: no clock, kept at both.
    the_event_stuck_at_live .... Live arm at 30 days: kept at both.
    the_suspended_match ........ Suspended arm, open market: kept at both.
    the_game_that_started ...... Scheduled, started 2 h ago: the 24 h floor
                                 is unchanged, kept at both.
    the_game_tomorrow .......... Out at both.

Not wired into CI (the #837/#9484 steps carry exact count pins, and ci.yml sits
just under GitHub's size limit); it skips without `WS_SLATE_DATABASE_URL` and
is run by hand against a local Postgres. The offline half,
`tests/test_pm_ws_upcoming_hours_10090.py`, pins the SQL text in CI.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

DB_URL = os.environ.get("WS_SLATE_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason="set WS_SLATE_DATABASE_URL to run the real-Postgres upcoming-window proof",
)

#: case -> (event status, hours from now to commence)
CASES = {
    "the_game_in_four_hours": ("scheduled", 4),
    "the_game_in_two_hours": ("scheduled", 2),
    "the_game_in_progress": ("live", -1),
    "the_event_stuck_at_live": ("live", -24 * 30),
    "the_suspended_match": ("suspended", -6),
    "the_game_that_started": ("scheduled", -2),
    "the_game_tomorrow": ("scheduled", 30),
}

#: hours setting -> cases the slate keeps
KEPT = {
    3: {
        "the_game_in_two_hours",
        "the_game_in_progress",
        "the_event_stuck_at_live",
        "the_suspended_match",
        "the_game_that_started",
    },
    6: {
        "the_game_in_four_hours",
        "the_game_in_two_hours",
        "the_game_in_progress",
        "the_event_stuck_at_live",
        "the_suspended_match",
        "the_game_that_started",
    },
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
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    sport = Sport(key="americanfootball_nfl", name="NFL")
    session.add(sport)
    await session.flush()

    event_ids = {}
    for case, (status, hours) in CASES.items():
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
        market = FuturesMarket(
            source="polymarket",
            external_id=f"0x{case}",
            name=f"{case} moneyline",
            event_id=event.id,
            status="open",
        )
        session.add(market)
        await session.flush()
        session.add(FuturesOutcome(
            market_id=market.id, name=case, external_id=f"0x{case}_yes",
        ))
    await session.commit()
    return event_ids


async def _kept(hours, monkeypatch):
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.tasks import polymarket_ws

    monkeypatch.setattr(polymarket_ws, "PM_WS_UPCOMING_HOURS", hours)
    engine, maker = await _engine_with_tables()
    try:
        async with maker() as session:
            ids = await _seed(session)
        async with maker() as session:
            kept = {
                row.event_id
                for row in (await session.execute(
                    select(FuturesOutcome.id, FuturesMarket.event_id)
                    .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                    .join(Event, FuturesMarket.event_id == Event.id)
                    .where(
                        FuturesMarket.source == "polymarket",
                        FuturesMarket.event_id.isnot(None),
                        polymarket_ws._slate_event_window(),
                        polymarket_ws._slate_market_filter(),
                    )
                )).all()
            }
    finally:
        await engine.dispose()
    return {case for case, eid in ids.items() if eid in kept}


@needs_postgres
@pytest.mark.parametrize("hours", sorted(KEPT))
async def test_the_upcoming_window_keeps_exactly(hours, monkeypatch):
    assert await _kept(hours, monkeypatch) == KEPT[hours]
