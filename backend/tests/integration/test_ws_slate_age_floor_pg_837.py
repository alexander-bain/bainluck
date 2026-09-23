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

WHY THIS IS A POSTGRES TEST. The whole fix is one SQL predicate, and the two
ways of getting it wrong fail in OPPOSITE directions, so neither is visible to a
test that asserts on the compiled string. Too loose (no floor, or a floor that
never fires) and the 1,248-market bag stays subscribed. Too broad — the floor
written ABOVE the ``or_()`` rather than inside the ``scheduled`` arm, which is
how this fix was first drafted and why it was sent back — and the clock tests
reach live rows too: an event the graph still calls live is unsubscribed after
24 hours, and one with no recorded start is unsubscribed at once. Only Postgres
answering the real predicate tells those three apart.

THE CASES, and which direction each fails in:

    the_finished_us_open_match .. THE SHIP. Scheduled, 20 days old — the
                                  1,248-market bag, in miniature. Fails if the
                                  floor is absent or inert.
    the_event_stuck_at_live ..... LIVE-PRESERVATION CONTROL. Live, 30 days old.
                                  Fails if the floor is lifted above the or_()
                                  — the first draft dropped exactly this row.
                                  This is the whole of why the live arm carries
                                  no clock test.
    the_game_in_progress ........ KILL CONTROL. If the floor were too broad, or
                                  had disabled the slate, this would vanish.
    the_game_starting_soon ...... KILL CONTROL for the same.
    the_game_in_a_rain_delay .... The floor is not too TIGHT: started 20 h ago
                                  and still streaming. A start time is not a
                                  finish time.
    the_game_tomorrow ........... The upper bound still works. Proves the fix
                                  widened nothing while narrowing.

    the_schema_is_why_there_is .. The seventh case is not an event at all. The
      _no_null_clock_case         other live-preservation control — a live row
                                  with no recorded start — CANNOT BE SEEDED,
                                  because `events.commence_time` is NOT NULL.
                                  Rather than omit it silently, the file asserts
                                  the schema that makes it unwritable, so the
                                  day someone loosens the column this fails and
                                  the real case gets written.

ONE case changes with the fix and six are controls, so a run that lost the ship
case would still print a green summary — the CI step counts passes.

A NOTE ON THE STUCK-AT-LIVE ROW, since the contract asserts it keeps a
subscription it arguably should not have. An event wedged at ``status='live'``
for a month is a real defect, but it belongs to whatever failed to advance the
status; unsubscribing live rows on a clock trades a rare stale subscription for
a routine dark hero, and this module is already on record that a start time is
not a finish time. Production 2026-09-23 03:4xZ, all events (a superset of the
slate): 58 live rows, 0 older than 24 h — against 850 ``scheduled`` rows older
than 24 h. The ship is entirely in the scheduled arm.
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
        # ---- live-preservation controls -------------------------------
        # Both of these are dropped by a floor written above the `or_()`,
        # which is how this fix was first drafted.
        "the_event_stuck_at_live": _event(
            "StuckLive", now - timedelta(days=30), "live"
        ),
        # The NULL-clock live row that would belong here cannot be seeded:
        # `events.commence_time` is NOT NULL. `test_the_schema_is_why_there_is_
        # no_null_clock_case` holds that end instead.
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


async def _engine_with_tables():
    """A fresh engine over an empty copy of the six tables the slate joins."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

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

    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def selected():
    """Run the REAL slate predicate against Postgres; return the cases it keeps.

    Function-scoped for the reason `test_search_recall_contract.py` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture outlives the loop that created its engine.
    """
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.tasks.polymarket_ws import _slate_event_window

    engine, maker = await _engine_with_tables()
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
    """Seven events, one Polymarket market each, one real query."""

    async def test_a_match_that_finished_twenty_days_ago_is_dropped(self, selected):
        # THE SHIP. 1,248 markets like this one were being subscribed; the
        # venue has no orderbook for 90% of their tokens.
        assert selected["the_finished_us_open_match"] is False

    async def test_an_event_still_called_live_keeps_its_stream_at_thirty_days(
        self, selected
    ):
        # LIVE-PRESERVATION CONTROL. The live arm carries no clock test, so a
        # multi-day tournament, a suspended game, or a status the updater never
        # advanced keeps streaming. The first draft of this fix put the floor
        # above the `or_()` and dropped this row; that is a dark hero decided
        # by a timestamp this module does not trust.
        assert selected["the_event_stuck_at_live"] is True

    async def test_the_schema_is_why_there_is_no_null_clock_case(self):
        # The other live-preservation case — a live event with no recorded
        # start — CANNOT BE SEEDED, and that is worth an assertion rather than
        # a silent omission. `events.commence_time` is NOT NULL (model:
        # `Mapped[datetime]`, no Optional; production `information_schema`
        # 2026-09-23 03:4xZ: is_nullable = NO), so Postgres refuses the row and
        # `commence_time IS NOT NULL` can never exclude anything from the slate
        # — in this predicate or in the draft that put it above the `or_()`.
        #
        # This assertion is the tripwire: loosen the column and it fails, which
        # is the moment the live arm's fail-open behaviour needs a real case.
        from sqlalchemy.exc import IntegrityError

        from app.models.models import Event

        assert Event.__table__.c.commence_time.nullable is False

        engine, maker = await _engine_with_tables()
        try:
            async with maker() as session:
                session.add(
                    Event(
                        sport_id=None,
                        home_team_name="NoClock Home",
                        away_team_name="NoClock Away",
                        commence_time=None,
                        status="live",
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
        finally:
            await engine.dispose()

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
