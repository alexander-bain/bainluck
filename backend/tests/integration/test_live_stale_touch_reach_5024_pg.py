"""#5024 — the live arm reaches a market the venue stopped serving, not just an empty book.

## What a reader saw, measured on production

Raiders@Chargers, `/events/14781694`, live, 2026-09-20 22:1xZ. Kalshi held
`KXNFLFIRSTTD-26SEP20LVLAC` as **23 `finalized` legs + 3 `inactive`**, with
`result='yes'` on Tre Tucker — the first touchdown was a fact, in the play feed on
the same page. Our row read `status='open'` and the page drew the 26-rung ladder
#5024 was filed for, summing to **189%**: Tucker 0.99 with 25 losing alternatives
still listed as live possibilities.

`derive_venue_settlement` would have answered `settled_past_dormant_legs` on those
statuses the moment it was asked. It was not asked, because the row was not
selected: the live arm of `RECENT_FINAL_SELECT_SQL` screens on #5024's EMPTY BOOK
(`current_yes_bid = 0 AND current_yes_ask = 1`) and at 22:15Z **not one of the 26
legs carried it** — Tucker read `0.0200 / 0.3300`, the last two-sided quote from
before the close, beside a stored 0.99. Repo-wide that minute the empty book
reached **17 of 328** live rows.

**It is late, not unreachable, and the distinction is load-bearing.** The venue
closed Tucker's leg at 21:27:47Z and the last of the 26 at 22:07:46Z; our poller
did write the empty book eventually, and the existing screen flipped the row at
22:30:00Z — 22 minutes after the venue finished and 62 after the question was
decided. The screen this file gates reads the poller's touch stamp instead, which
tracks the venue's `close_time` to the poll cadence: at 22:34Z it took 31 rows the
empty book had not reached, ten of the sixteen sampled were all-terminal at the
venue, and those ten had been decided for 14–20 minutes while still reading open.

## Why this gate is real PostgreSQL and not a session double

The whole change is one SQL predicate, and the sibling gate
(`test_kalshi_live_settlement_5024.py`) can only assert that substrings appear in
the statement. Every way this predicate can be wrong is a way a string match
cannot see:

* `NOT EXISTS (… last_updated >= :floor)` written as `EXISTS (… < :floor)` selects
  a healthy market the instant ONE leg lags, which is most of a live slate;
* dropping the `EXISTS (… fo.market_id = fm.id)` guard makes the NOT EXISTS
  vacuously true for a row with no legs at all — "we have never priced this" read
  as "the venue dropped it";
* putting the new clause outside the live branch's parentheses would apply it to
  the completed and suspended arms too;
* binding the floor as a literal rather than a parameter (gotcha #45) reads as a
  string and returns nothing, which looks exactly like "nothing was stale".

The rows below are the production specimens: the Raiders@Chargers First Touchdown
row with its real fossil book, a still-trading control from the same game
(`KXNFLGAME-26SEP20LVLAC`, touched inside the minute), and the pre-#5024
empty-book shape that must keep its reach.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5024 "
            "live-arm reach gate (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The read's "now" — the minute the specimen was measured on production.
NOW = datetime(2026, 9, 20, 22, 15, tzinfo=timezone.utc)

#: Kickoff of both NFL specimens: inside every band this arm asks for.
KICKOFF = datetime(2026, 9, 20, 20, 5, tzinfo=timezone.utc)

#: Only this key is created, deleted or asserted over. CI's `search-recall` job
#: runs every PG gate against ONE database, so a bare `DELETE FROM events` would
#: be this file reaching into another gate's rows.
SEEDED_SPORT_KEY = "americanfootball_nfl_5024_stale_touch"


def _closure(*roots):
    """The tables these queries need, and nothing else.

    `Base.metadata.create_all()` emits DDL for every model, and one unrelated
    table carries `NULLS NOT DISTINCT` — PostgreSQL 15+ only. Building the whole
    schema would make this gate's ability to run depend on a clause no part of it
    uses. Same helper, same reason, as #5779's gate.
    """
    seen: dict = {}
    pending = list(roots)
    while pending:
        table = pending.pop()
        if table.key in seen:
            continue
        seen[table.key] = table
        for fk in table.foreign_keys:
            pending.append(fk.column.table)
    return list(seen.values())


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema. Function-scoped, like its siblings."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesOutcome, Sport
    from app.services.database import Base

    tables = _closure(Sport.__table__, Event.__table__, FuturesOutcome.__table__)
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=tables, checkfirst=True)
        )
        await conn.execute(
            text(
                "DELETE FROM futures_outcomes WHERE market_id IN ("
                " SELECT fm.id FROM futures_markets fm JOIN events e ON e.id = fm.event_id"
                " JOIN sports s ON s.id = e.sport_id WHERE s.key = :key)"
            ),
            {"key": SEEDED_SPORT_KEY},
        )
        await conn.execute(
            text(
                "DELETE FROM futures_markets WHERE event_id IN ("
                " SELECT e.id FROM events e JOIN sports s ON s.id = e.sport_id"
                " WHERE s.key = :key)"
            ),
            {"key": SEEDED_SPORT_KEY},
        )
        await conn.execute(
            text(
                "DELETE FROM events WHERE sport_id IN "
                "(SELECT id FROM sports WHERE key = :key)"
            ),
            {"key": SEEDED_SPORT_KEY},
        )
        await conn.execute(
            text("DELETE FROM sports WHERE key = :key"), {"key": SEEDED_SPORT_KEY}
        )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM futures_outcomes WHERE market_id IN ("
                " SELECT fm.id FROM futures_markets fm JOIN events e ON e.id = fm.event_id"
                " JOIN sports s ON s.id = e.sport_id WHERE s.key = :key)"
            ),
            {"key": SEEDED_SPORT_KEY},
        )
        await conn.execute(
            text(
                "DELETE FROM futures_markets WHERE event_id IN ("
                " SELECT e.id FROM events e JOIN sports s ON s.id = e.sport_id"
                " WHERE s.key = :key)"
            ),
            {"key": SEEDED_SPORT_KEY},
        )
        await conn.execute(
            text(
                "DELETE FROM events WHERE sport_id IN "
                "(SELECT id FROM sports WHERE key = :key)"
            ),
            {"key": SEEDED_SPORT_KEY},
        )
        await conn.execute(
            text("DELETE FROM sports WHERE key = :key"), {"key": SEEDED_SPORT_KEY}
        )
    await engine.dispose()


async def _seed(session, *, event_status, markets, commence=KICKOFF, completed=None):
    """One event and its markets. `markets` is `[(external_id, [legs…])]`.

    A leg is `(yes_bid, yes_ask, probability, touched_minutes_ago)` — or `None`
    for "this market has no legs at all", which is the vacuous-NOT-EXISTS case.
    """
    from sqlalchemy import text

    sport_id = (
        await session.execute(
            text(
                # Idempotent: a test that seeds a live event AND a finished one
                # calls this twice, and the second call must reuse the sport
                # rather than trip `sports_key_key`.
                "INSERT INTO sports (key, name, active) VALUES (:k, :n, true)"
                " ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name"
                " RETURNING id"
            ),
            {"k": SEEDED_SPORT_KEY, "n": "NFL (#5024 gate)"},
        )
    ).scalar_one()

    event_id = (
        await session.execute(
            text(
                "INSERT INTO events (sport_id, home_team_name, away_team_name,"
                " commence_time, status, completed_at)"
                " VALUES (:s, :h, :a, :c, :st, :done) RETURNING id"
            ),
            {
                "s": sport_id,
                "h": "Los Angeles Chargers",
                "a": "Las Vegas Raiders",
                "c": commence,
                "st": event_status,
                "done": completed,
            },
        )
    ).scalar_one()

    ids = {}
    for external_id, legs in markets:
        market_id = (
            await session.execute(
                text(
                    "INSERT INTO futures_markets (event_id, source, external_id, name,"
                    " category, status, market_type, mutually_exclusive)"
                    " VALUES (:e, 'kalshi', :x, :n, 'sports', 'open', 'prop', true)"
                    " RETURNING id"
                ),
                {"e": event_id, "x": external_id, "n": external_id},
            )
        ).scalar_one()
        ids[external_id] = market_id
        for i, leg in enumerate(legs):
            bid, ask, prob, age_min = leg
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name,"
                    " current_yes_bid, current_yes_ask, current_probability,"
                    " last_updated) VALUES (:m, :x, :n, :b, :a, :p, :u)"
                ),
                {
                    "m": market_id,
                    "x": f"{external_id}-{i}",
                    "n": f"leg {i}",
                    "b": bid,
                    "a": ask,
                    "p": prob,
                    "u": NOW - timedelta(minutes=age_min),
                },
            )
    await session.commit()
    return ids


async def _select(session, *, limit=200):
    """Run the real statement with the real binds, and return the external ids."""
    from sqlalchemy import text

    from app.tasks import kalshi_resolution_sweep as sweep

    rows = (
        await session.execute(
            text(sweep.RECENT_FINAL_SELECT_SQL),
            {
                "final_floor": NOW - timedelta(hours=sweep.RECENT_FINAL_WINDOW_HOURS),
                "live_floor": NOW - timedelta(hours=sweep.LIVE_EVENT_WINDOW_HOURS),
                "suspended_floor": NOW
                - timedelta(hours=sweep.SUSPENDED_EVENT_WINDOW_HOURS),
                "stale_touch_floor": NOW
                - timedelta(minutes=sweep.LIVE_STALE_TOUCH_MINUTES),
                "frozen_gap": sweep.FROZEN_BOOK_GAP,
                "limit": limit,
            },
        )
    ).all()
    return [r[1] for r in rows]


#: Tre Tucker's real fossil: a two-sided book from before the close, beside the
#: probability that ran to the settlement tail. No leg of the real 26 carried the
#: empty book, which is the whole reason the row was unreachable.
FIRST_TD_LEGS = [
    (0.02, 0.33, 0.99, 71),
    (0.00, 0.49, 0.20, 71),
    (0.02, 0.30, 0.02, 71),
]

#: The same game's still-trading market, touched inside the minute — the control
#: that returned 0-of-8 all-terminal when this screen was measured at the venue.
GAME_LEGS = [(0.46, 0.48, 0.54, 0), (0.52, 0.54, 0.46, 0)]


class TestTheSpecimenIsReached:
    """RED before this change: the First Touchdown row is selected by nothing."""

    async def test_the_first_touchdown_row_is_selected(self, pg_session):
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLFIRSTTD-26SEP20LVLAC", FIRST_TD_LEGS)],
        )

        assert await _select(pg_session) == ["KXNFLFIRSTTD-26SEP20LVLAC"]

    async def test_a_still_trading_market_on_the_same_game_is_not_selected(
        self, pg_session
    ):
        """The screen's whole cost argument. If this fails, every live market on
        every live game goes through a venue read every ten minutes."""
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLGAME-26SEP20LVLAC", GAME_LEGS)],
        )

        assert await _select(pg_session) == []

    async def test_the_two_are_separated_when_they_sit_side_by_side(self, pg_session):
        """Both rows on one event, as they really are: the decided one is taken
        and the trading one is left. A predicate that answered on the EVENT
        rather than the market would take both and fail here."""
        await _seed(
            pg_session,
            event_status="live",
            markets=[
                ("KXNFLFIRSTTD-26SEP20LVLAC", FIRST_TD_LEGS),
                ("KXNFLGAME-26SEP20LVLAC", GAME_LEGS),
            ],
        )

        assert await _select(pg_session) == ["KXNFLFIRSTTD-26SEP20LVLAC"]

    async def test_one_touched_leg_keeps_a_market_out(self, pg_session):
        """The aggregate is per market and it is `NOT EXISTS`, not `EXISTS(… <)`.
        A market whose legs are mostly stale but which the venue is still serving
        on ONE leg is still being served. Named as a residual in
        `LIVE_STALE_TOUCH_MINUTES`, asserted here so it stays deliberate."""
        legs = list(FIRST_TD_LEGS) + [(0.10, 0.12, 0.11, 0)]
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLFIRSTTD-26SEP20LVLAC", legs)],
        )

        assert await _select(pg_session) == []


class TestTheGuardsThatKeepItNarrow:
    """Each of these is a way the predicate could be wrong that a string match
    on the statement cannot see."""

    async def test_a_market_with_no_legs_is_not_selected(self, pg_session):
        """The vacuous case. `NOT EXISTS (… last_updated >= floor)` is TRUE for a
        row with no outcomes, so without the existence guard 'we have never
        priced this' reads as 'the venue dropped it'."""
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLNOLEGS-26SEP20LVLAC", [])],
        )

        assert await _select(pg_session) == []

    async def test_a_leg_exactly_on_the_floor_is_fresh(self, pg_session):
        """`>=` on the floor, so the boundary belongs to the healthy side. A
        market touched exactly `LIVE_STALE_TOUCH_MINUTES` ago is the last one
        that must NOT be asked about."""
        from app.tasks import kalshi_resolution_sweep as sweep

        legs = [(0.02, 0.33, 0.99, sweep.LIVE_STALE_TOUCH_MINUTES)]
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLEDGE-26SEP20LVLAC", legs)],
        )

        assert await _select(pg_session) == []

    async def test_a_scheduled_event_is_never_reached_by_the_new_clause(
        self, pg_session
    ):
        """The clause lives inside the live branch's parentheses. A pre-kickoff
        market nobody has touched for an hour is not a settled one, and #5596's
        own measurement refused `scheduled` at 25% precision."""
        await _seed(
            pg_session,
            event_status="scheduled",
            commence=NOW + timedelta(hours=3),
            markets=[("KXNFLFUTURE-26SEP21LVLAC", FIRST_TD_LEGS)],
        )

        assert await _select(pg_session) == []

    async def test_a_live_event_outside_the_band_is_not_reached(self, pg_session):
        """`LIVE_EVENT_WINDOW_HOURS` still leashes the arm. A row stuck in
        `status='live'` for days must not be asked about every ten minutes
        forever just because nothing has touched it."""
        await _seed(
            pg_session,
            event_status="live",
            commence=NOW - timedelta(days=3),
            markets=[("KXNFLSTUCK-26SEP17LVLAC", FIRST_TD_LEGS)],
        )

        assert await _select(pg_session) == []


class TestTheReachThatAlreadyExisted:
    """Additive. If any of these fail, #5024's first arm or #4655 regressed."""

    async def test_the_empty_book_still_reaches_a_freshly_touched_market(
        self, pg_session
    ):
        """The pre-existing screen, on a market touched seconds ago so ONLY the
        empty book can be selecting it."""
        legs = [(0.00, 1.00, 0.99, 0), (0.00, 1.00, 0.01, 0)]
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLEMPTY-26SEP20LVLAC", legs)],
        )

        assert await _select(pg_session) == ["KXNFLEMPTY-26SEP20LVLAC"]

    async def test_a_finished_game_still_takes_the_batch_first(self, pg_session):
        """#4655's 30-minute bar. `completed_at DESC NULLS LAST` sorts every
        final ahead of every live row, so the widened live arm can still only
        consume capacity a final did not want."""
        await _seed(
            pg_session,
            event_status="live",
            markets=[("KXNFLFIRSTTD-26SEP20LVLAC", FIRST_TD_LEGS)],
        )
        await _seed(
            pg_session,
            event_status="completed",
            commence=NOW - timedelta(hours=4),
            completed=NOW - timedelta(minutes=10),
            markets=[("KXNFLGAME-26SEP20FINAL", GAME_LEGS)],
        )

        assert await _select(pg_session) == [
            "KXNFLGAME-26SEP20FINAL",
            "KXNFLFIRSTTD-26SEP20LVLAC",
        ]
