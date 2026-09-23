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


# ---------------------------------------------------------------------------
# The market-level half of the slate: a market the venue has already SETTLED.
#
# The event window above is deliberately clock-free on the live arm, and its
# docstring says the stuck-at-live hazard needs "the venue's own resolution"
# rather than a clock. `futures_markets.status = 'resolved'` is that signal, and
# it was not being read: measured on production 2026-09-23 05:2xZ, 54 markets /
# 108 outcomes on 12 events inside the event window were already resolved in our
# own database — 7.6% of a byte-capped subscription sitting at 40,594 of 40,960
# bytes. A 120-second probe of the public CLOB socket returned NOTHING for four
# such tokens (not even the opening `book` frame), while the same connection's
# control arm got its books at once and 726 `price_change` frames.
#
# EVERY CASE BELOW SITS ON A `live` EVENT, so the event window keeps all of them
# and only the market predicate can move one. Two of the four are on ONE event,
# which is the whole point: the fix drops a settled MARKET, never an event.
# ---------------------------------------------------------------------------


async def _seed_markets(session):
    """One live event with a settled market and an open one, plus two controls."""
    from sqlalchemy import text as sql_text

    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)

    sport = Sport(key="tennis_atp", name="ATP")
    session.add(sport)
    await session.flush()

    def _event(name):
        return Event(
            sport_id=sport.id,
            home_team_name=f"{name} Home",
            away_team_name=f"{name} Away",
            commence_time=now - timedelta(hours=3),
            status="live",
        )

    # THE MODEL IS STRICTER THAN THE DEPLOYED COLUMN, AND THE PREDICATE HAS TO
    # SURVIVE THE DEPLOYED ONE. `FuturesMarket.status` is `Mapped[str]`, so
    # `create_all` emits NOT NULL here — but production's column is
    # `is_nullable = YES` with `DEFAULT 'open'` (read 2026-09-23 05:3xZ), so a
    # raw-SQL writer that sets it to NULL is refused in this database and
    # accepted in the one serving readers. Seeding the fail-open control
    # against the model's schema is impossible; seeding it against production's
    # is the whole point, so the column is relaxed to match what is deployed.
    # If a migration ever adds the NOT NULL for real, this ALTER becomes a
    # no-op and the control becomes belt-and-braces rather than live.
    assert FuturesMarket.__table__.c.status.nullable is False, (
        "model tightened; re-read production's information_schema before "
        "deciding this control is dead"
    )
    await session.execute(
        sql_text("ALTER TABLE futures_markets ALTER COLUMN status DROP NOT NULL")
    )

    # The M25 Yinchuan shape from the production read: one event whose
    # moneyline the venue settled while a sibling market is still open.
    yinchuan = _event("Yinchuan")
    lone = _event("Lone")
    session.add_all([yinchuan, lone])
    await session.flush()

    cases = {
        # ---- the ship -------------------------------------------------
        "the_market_the_venue_settled": (yinchuan.id, "resolved"),
        # ---- kill control, on the SAME event --------------------------
        "the_open_sibling_on_that_event": (yinchuan.id, "open"),
        # ---- fail-open controls ---------------------------------------
        "the_market_with_no_status": (lone.id, None),
        "the_suspended_market": (lone.id, "suspended"),
    }

    null_status_ids = []
    for case, (event_id, status) in cases.items():
        market = FuturesMarket(
            source="polymarket",
            external_id=f"0x{case}",
            name=f"{case} moneyline",
            event_id=event_id,
            # `status` is `default="open"`, so passing None here would be
            # overwritten by the Python-side default at flush — the NULL has to
            # be written afterwards in SQL, below, or the control is vacuous.
            **({} if status is None else {"status": status}),
        )
        session.add(market)
        await session.flush()
        if status is None:
            null_status_ids.append(market.id)
        session.add(
            FuturesOutcome(
                market_id=market.id,
                name=case,
                external_id=f"0x{case}_yes",
            )
        )

    if null_status_ids:
        await session.execute(
            sql_text(
                "UPDATE futures_markets SET status = NULL WHERE id = ANY(:ids)"
            ),
            {"ids": null_status_ids},
        )

    await session.commit()

    # The NULL control is only a control if the NULL actually landed. A column
    # constraint or a writer default would make it read as 'open' and the arm
    # would pass for the wrong reason.
    stored = (
        await session.execute(
            sql_text(
                "SELECT status FROM futures_markets WHERE id = ANY(:ids)"
            ),
            {"ids": null_status_ids},
        )
    ).scalars().all()
    assert stored == [None], f"NULL-status control did not land: {stored!r}"

    return {case: f"0x{case}" for case in cases}


@pytest.fixture
async def selected_markets():
    """The same shipped query, read back per MARKET rather than per event."""
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.tasks.polymarket_ws import _slate_event_window, _slate_market_filter

    engine, maker = await _engine_with_tables()
    async with maker() as session:
        ids = await _seed_markets(session)

    async with maker() as session:
        result = await session.execute(
            select(FuturesOutcome.id, FuturesMarket.external_id)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.isnot(None),
                _slate_event_window(),
                _slate_market_filter(),
            )
        )
        kept = {row.external_id for row in result.all()}

    await engine.dispose()

    yield {case: (ext_id in kept) for case, ext_id in ids.items()}


@needs_postgres
class TestASettledMarketLeavesTheSubscription:
    """Four Polymarket markets on two live events, one real query."""

    async def test_a_market_the_venue_has_settled_is_dropped(self, selected_markets):
        # THE SHIP. 54 markets like this one were subscribed at the moment of
        # the production read, and the venue answers their tokens with silence
        # — no book, no price_change, nothing in 120 seconds.
        assert selected_markets["the_market_the_venue_settled"] is False

    async def test_its_open_sibling_on_the_same_event_still_streams(
        self, selected_markets
    ):
        # KILL CONTROL, and the reason this predicate is market-level. The
        # event stays live and every market on it that the venue has NOT
        # settled keeps its stream; a reader watching that game loses nothing.
        assert selected_markets["the_open_sibling_on_that_event"] is True

    async def test_a_market_with_no_status_still_streams(self, selected_markets):
        # FAIL-OPEN CONTROL, and the only arm that tells the shipped predicate
        # apart from a plain `status != 'resolved'`: in SQL that comparison is
        # NULL for a NULL status, so the plain form drops this row — a live
        # market going dark because nobody wrote a status.
        assert selected_markets["the_market_with_no_status"] is True

    async def test_a_suspended_market_still_streams(self, selected_markets):
        # Only `resolved` is terminal. A suspended market can reopen, and
        # unsubscribing it would need a re-subscribe nobody schedules.
        assert selected_markets["the_suspended_market"] is True


def test_the_consumer_actually_applies_both_halves_of_the_slate():
    """The predicates are WIRED into the query the socket runs.

    Not Postgres-gated, and not decoration. Everything above stands the
    predicate functions in for the where-clause, which reads the shipped
    expression but not the shipped CALL SITE — so deleting
    ``_slate_market_filter()`` from ``run_polymarket_ws``'s ``.where(...)``
    leaves this file 11/11 green while the socket subscribes to every settled
    market again. That mutation was run (2026-09-23, 8 arms, all passed) and is
    the reason this test exists: a defined-but-uncalled filter is the exact
    shape of an unwired fix.

    AST rather than a substring, so a comment mentioning the name cannot
    satisfy it and reformatting cannot break it: both filters must appear as
    CALLS inside the argument list of one `.where(...)` call.
    """
    import ast
    import inspect

    from app.tasks import polymarket_ws

    tree = ast.parse(inspect.getsource(polymarket_ws))

    wired = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "where"):
            continue
        names = {
            a.func.id
            for a in node.args
            if isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
        }
        if "_slate_event_window" in names:
            wired |= names

    assert "_slate_event_window" in wired, (
        "no .where() applies the event window — the slate is unwired"
    )
    assert "_slate_market_filter" in wired, (
        "_slate_market_filter() is not applied in the same .where() as the "
        "event window: settled markets are back in the subscription"
    )
