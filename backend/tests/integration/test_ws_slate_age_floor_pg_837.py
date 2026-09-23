"""The Polymarket socket stops subscribing to finished sport. #837, real Postgres.

WHAT WAS WRONG. The slate query that decides which markets the socket streams
was bounded at one end only — ``commence_time <= NOW() + 6 hours``. That reads
as "starting soon", but it is satisfied by *every* past time too, so it is not a
statement about the future at all: an event that never left ``status='scheduled'``
stayed in the subscription forever. Measured on production 2026-09-23 02:5xZ,
before the floor:

    CURRENT (live, or starting within 6 h) ......   640 markets,  79 events
    STALE   (started > 6 h ago, still 'scheduled')  1,248 markets, 107 events
            oldest commence_time 2026-06-01 — nearly four months

**66 % of the subscription was finished sport**, and the venue says those rows
are gone rather than quiet: 27 of 30 randomly sampled stale tokens answered
``/book`` with *"No orderbook exists for the requested token id"*, against 30 of
30 alive on a same-size current control. That is the whole of #837's
``served=1413/3367`` — the four contiguous shards reading 14/500, 26/500,
36/500, 39/500 were holding dead tokens, not being truncated by the venue.

WHY IT REACHED A READER, which is what makes this a fix. The token top-up that
gives a market its ``clob_token_ids`` is capped per recycle and ordered by a
rotating cursor, not by whether anyone is watching. Its queue was **253 stale
against 46 current**, so live games waited behind finished ones for a budget
85 % of which could never pay. At the moment of the measurement, 42 markets on
games *in progress* had no tokens and therefore no price stream at all — eight
MLB games among them, including the Dodgers/Padres game filed as #8156.

WHY THIS IS A POSTGRES TEST. The whole fix is one SQL predicate, and both ways
of getting it wrong are invisible to anything that does not let Postgres answer.
A unit test that asserts on the compiled string passes for a floor written
*inside* the ``scheduled`` arm, which is the bug that matters — the ``live`` arm
has no time bound of its own, so the first event that sticks at ``status='live'``
walks straight back in. ``the_event_stuck_at_live`` is that case, and it is the
reason the floor is applied once, above the ``or_()``.

THE CASES, and which direction each fails in:

    the_finished_us_open_match .. THE SHIP. Scheduled, 20 days old — the
                                  1,248-market bag, in miniature.
    the_event_stuck_at_live ..... THE SHIP's other half. The or_() sibling arm.
                                  Excluded only by a floor above the OR.
    the_game_in_progress ........ KILL CONTROL. If the floor were too broad, or
                                  had disabled the slate, this would vanish.
    the_game_starting_soon ...... KILL CONTROL for the same.
    the_game_in_a_rain_delay .... The floor is not too TIGHT: started 20 h ago
                                  and still streaming. A start time is not a
                                  finish time.
    the_game_tomorrow ........... The upper bound still works. Proves the fix
                                  widened nothing while narrowing.

Two of the six change with the fix and four are controls, so a run that lost the
ship cases would still print a green summary — the CI step counts passes.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

#: Its own variable, deliberately not falling back to `$DATABASE_URL`: a gate
#: that quietly runs against whatever the shell happens to export is a gate
#: nobody can read the result of.
DB_URL = os.environ.get("WS_SLATE_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set WS_SLATE_DATABASE_URL to run the real-Postgres subscription-slate "
        "contract (CI does; the step fails on a skip)"
    ),
)


async def _seed(session):
    """One Polymarket market per case, each on an event with a telling clock."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)

    sport = Sport(key="tennis_atp", name="ATP")
    session.add(sport)
    await session.flush()

    def _event(name, commence_time, status):
        return Event(
            sport_id=sport.id,
            home_team_name=f"{name} Home",
            away_team_name=f"{name} Away",
            commence_time=commence_time,
            status=status,
        )

    events = {
        # ---- the ship -------------------------------------------------
        "the_finished_us_open_match": _event(
            "Finished", now - timedelta(days=20), "scheduled"
        ),
        "the_event_stuck_at_live": _event(
            "StuckLive", now - timedelta(days=30), "live"
        ),
        # ---- controls -------------------------------------------------
        "the_game_in_progress": _event(
            "InProgress", now - timedelta(hours=1), "live"
        ),
        "the_game_starting_soon": _event(
            "StartingSoon", now + timedelta(hours=2), "scheduled"
        ),
        "the_game_in_a_rain_delay": _event(
            "RainDelay", now - timedelta(hours=20), "live"
        ),
        "the_game_tomorrow": _event(
            "Tomorrow", now + timedelta(hours=30), "scheduled"
        ),
    }
    session.add_all(list(events.values()))
    await session.flush()

    for case, event in events.items():
        market = FuturesMarket(
            source="polymarket",
            external_id=f"0x{case}",
            name=f"{case} moneyline",
            event_id=event.id,
        )
        session.add(market)
        await session.flush()
        # The slate selects OUTCOMES, so a market with none is invisible to it
        # whatever the event clock says. One per market, as production has.
        session.add(
            FuturesOutcome(
                market_id=market.id,
                name=case,
                external_id=f"0x{case}_yes",
            )
        )

    await session.commit()
    return {case: event.id for case, event in events.items()}


@pytest.fixture
async def selected():
    """Run the REAL slate predicate against Postgres; return the cases it keeps.

    Function-scoped for the reason `test_search_recall_contract.py` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture outlives the loop that created its engine.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.services.database import Base
    from app.tasks.polymarket_ws import _slate_event_window

    # Only this predicate's tables, plus the closure `events` needs for its FKs.
    # A whole-schema create_all needs Postgres 15 (`NULLS NOT DISTINCT`), and a
    # missing table raises here rather than passing quietly.
    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "futures_markets",
            "futures_outcomes",
        )
    ]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    # The consumer's own query, joins and all, with ONLY the predicate under
    # test standing in for the where-clause — so this reads the shipped
    # expression rather than a copy of it that can drift.
    async with maker() as session:
        result = await session.execute(
            select(FuturesOutcome.id, FuturesMarket.event_id)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.isnot(None),
                _slate_event_window(),
            )
        )
        kept_event_ids = {row.event_id for row in result.all()}

    await engine.dispose()

    yield {case: (eid in kept_event_ids) for case, eid in ids.items()}


@needs_postgres
class TestTheSlateIsBoundedAtBothEnds:
    """Six events, one Polymarket market each, one real query."""

    async def test_a_match_that_finished_twenty_days_ago_is_dropped(self, selected):
        # THE SHIP. 1,248 markets like this one were being subscribed; the
        # venue has no orderbook for 90% of their tokens.
        assert selected["the_finished_us_open_match"] is False

    async def test_an_event_stuck_at_live_is_dropped_too(self, selected):
        # The or_() sibling arm. A floor written inside the `scheduled` arm
        # leaves this one subscribed forever, and compiles to SQL that looks
        # right.
        assert selected["the_event_stuck_at_live"] is False

    async def test_a_game_in_progress_still_streams(self, selected):
        # KILL CONTROL: the point of the fix is that THIS keeps its prices.
        assert selected["the_game_in_progress"] is True

    async def test_a_game_starting_in_two_hours_still_streams(self, selected):
        assert selected["the_game_starting_soon"] is True

    async def test_a_game_twenty_hours_into_a_delay_still_streams(self, selected):
        # The floor is not too tight. A scheduled kickoff is not a finish time:
        # rain delays, five-set matches and a day of status-updater lag all sit
        # inside it.
        assert selected["the_game_in_a_rain_delay"] is True

    async def test_a_game_tomorrow_is_still_out_of_scope(self, selected):
        # The upper bound survived: the fix narrowed one end without widening
        # the other.
        assert selected["the_game_tomorrow"] is False
