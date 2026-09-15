"""#5869 — a futures leg that VANISHED from the book stops claiming it is impossible.

WHAT A READER SEES TODAY. `https://bainluck.com/futures/1`, MLB World Series
Winner, "Show more". Read from the served payload 2026-09-15 ~12:4xZ:

    {"name": "Athletics", "probability": 0.0, "american_odds": 331909,
     "is_winner": false, "resolution_source": null}

`0%` — the site asserting, flatly, that the Athletics cannot win the World
Series — sitting beside a price that implies 0.03%. 435 legs across 8 open
markets render that way; 122 of the 205 outcomes on "The Open Winner" are it.

── WHY 0 AND NULL ARE DIFFERENT SENTENCES, WHICH IS THE WHOLE SHIP ─────────────

`_poll_futures_odds`'s stale block (`app/tasks/futures.py`, "zero out stale
outcomes absent from API response") knows one fact: the outcome was ABSENT from
the response for over a day. "We no longer have a price" is NULL. It wrote 0,
which says IMPOSSIBLE, and nothing in that block established impossibility.

It survived because most readers of the column cannot tell the two apart — the
falsy idiom (`if o.current_probability`, `or 0`) that dominates
`routes/futures.py` folds them together, and `routes/teams.py:675` drops both.
The serializers `#6081` converted to `is not None` are the ones that CAN, and on
those the difference is the whole render:

    stored NULL -> `probability: null` -> formatProbability -> "-"
    stored 0    -> `probability: 0.0`  -> probabilityParts   -> "0%"

`probabilityParts` (`frontend/lib/probabilityDisplay.ts:136`) reaches for the
truthful `<1%` marker only when `prob > 0`, so 0 is precisely the one value that
escapes UX-P046 and prints as a hard claim.

🔴 THE REPAIR MAY NOT DERIVE A PROBABILITY FROM THE SURVIVING ODDS, and this test
deliberately does not assert one. On 430 of the 435 the zeroed legs last moved in
May–August while their priced siblings refreshed today, so
`current_american_odds` there is a months-old relic; turning it into a live price
would store a stale number as a current one on almost the whole population —
plausible, wrong, and indistinguishable from a real repair afterwards. "-" is
what we actually know. (Measured and written up on #1541; the odds column is kept
because it is the last honest quote, not because it can speak for now.)

The stored 435 are the sibling half of this ship and are retired by
`scripts/repair_5869_stale_futures_legs_claiming_impossible.py`; this file is the
producer gate, so the population cannot grow back (5 new legs joined it in the
30 days to 2026-09-15).

── WHAT EACH TEST HOLDS ────────────────────────────────────────────────────────

The round trip is the REAL task against a REAL Postgres, with two seams: the
venue (stubbed payload) and the connection. `stats["stale_zeroed"]` is asserted
in every arm that claims a retirement, because a seed that never reached the
block would satisfy a NULL assertion by doing nothing at all.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres futures-poll "
            "round trip (CI job `search-recall` provides one)"
        ),
    ),
]

SPORT_KEY = "golf_masters_tournament_winner"
PRICED = "Scottie Scheffler"
VANISHED = "Joe Highsmith"
RECENTLY_ABSENT = "Nevill Ruiter"

#: The last quote the vanished leg carried before the book dropped it. Kept as a
#: real number so "the witness survived" is an assertion and not a tautology.
VANISHED_LAST_ODDS = 66792


def _response_market():
    """One bookmaker's column, carrying ONLY the leg that is still priced.

    The vanished legs are absent by omission — which is exactly how the venue
    expresses "this outcome is no longer in the field", and the only input the
    stale block ever gets.
    """
    return SimpleNamespace(
        bookmaker="draftkings",
        market_name="The Masters Winner",
        outcomes=[
            SimpleNamespace(name=PRICED, probability=0.25, american_odds=300),
            SimpleNamespace(name="Rory McIlroy", probability=0.20, american_odds=400),
        ],
    )


async def _seed(session):
    """Two stale legs and one that will be re-priced.

    `VANISHED` is the specimen: absent from the response AND older than the
    24-hour floor. `RECENTLY_ABSENT` is the control for that floor — absent from
    the same response, but seen an hour ago, so a transient venue omission must
    not retire it.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)

    # No `Sport` row on purpose. `sports.key` is UNIQUE and this fixture no
    # longer drops anything, so seeding one would collide with a neighbour in
    # the shared CI database or with this file's own second run. The task links
    # through `sport_map.get(_infer_base_sport(...))` and
    # `futures_markets.sport_id` is nullable, so the absence costs nothing the
    # block under test can observe.
    market = FuturesMarket(
        source="odds_api",
        external_id=SPORT_KEY,
        sport_id=None,
        name="The Masters Winner",
        category="championship",
        mutually_exclusive=True,
        status="open",
    )
    session.add(market)
    await session.flush()

    session.add_all(
        [
            FuturesOutcome(
                market_id=market.id,
                external_id=PRICED,
                name=PRICED,
                current_probability=0.24,
                current_american_odds=310,
                last_updated=now - timedelta(days=3),
                rank=1,
                is_winner=None,
            ),
            FuturesOutcome(
                market_id=market.id,
                external_id=VANISHED,
                name=VANISHED,
                current_probability=0.05,
                current_american_odds=VANISHED_LAST_ODDS,
                probability_change_24h=-0.01,
                last_updated=now - timedelta(days=3),
                rank=9,
                is_winner=None,
            ),
            FuturesOutcome(
                market_id=market.id,
                external_id=RECENTLY_ABSENT,
                name=RECENTLY_ABSENT,
                current_probability=0.03,
                current_american_odds=3200,
                last_updated=now - timedelta(hours=1),
                rank=12,
                is_winner=None,
            ),
        ]
    )
    await session.commit()
    return market


async def _run_poll(session):
    """Run the REAL `_poll_futures_odds` against this session.

    The service is a stub rather than the real `OddsAPIService` with one method
    patched, because every call this task makes on it is network; the parse and
    the aggregation below it are the production functions, so the shape the
    block sees is the shape production builds.
    """
    service = SimpleNamespace(
        get_sports_with_outrights=AsyncMock(return_value=[{"key": SPORT_KEY}]),
        get_futures_odds=AsyncMock(return_value={}),
        _parse_futures=lambda response, sport_key: [_response_market()],
        last_requests_used=1,
        last_requests_remaining=None,  # skips the quota recorder, which is Redis
        close=AsyncMock(),
    )

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.tasks.futures.OddsAPIService", return_value=service)
        )
        es.enter_context(patch("app.tasks.futures.get_task_session", _session_cm))
        es.enter_context(
            patch(
                "app.tasks.redis_state.check_quota_guard",
                return_value=(True, "test"),
            )
        )
        from app.tasks.futures import _poll_futures_odds

        stats = await _poll_futures_odds()

    # The per-sport loop swallows failures into `stats["errors"]` — it must, one
    # bad sport may not wipe a poll — so an unasserted error list would let a
    # silently-skipped market read as a passing round trip (gotcha #42/#53).
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    await session.commit()
    return stats


async def _legs(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.current_probability, o.current_american_odds, "
            "       o.probability_change_24h "
            "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            " WHERE m.source = 'odds_api' AND m.external_id = :k"
        ),
        {"k": SPORT_KEY},
    )
    return {
        r[0]: {"prob": r[1], "american": r[2], "move": r[3]}
        for r in rows.fetchall()
    }


def _fk_closure(metadata, *names):
    """The named tables plus every table they reach through a foreign key.

    The sibling real-Postgres tests build the WHOLE schema, which needs
    PostgreSQL 15: `uq_container_anchor` is declared `NULLS NOT DISTINCT` and 14
    cannot parse it. The task under test writes four tables, so the closure of
    those four is both the honest scope and the reason this gate is runnable on
    the PG 14 a laptop has as well as the 15 CI provides — a gate only CI can
    run is a gate nobody runs before pushing.
    """
    want, seen = list(names), set()
    while want:
        name = want.pop()
        if name in seen:
            continue
        seen.add(name)
        for fk in metadata.tables[name].foreign_keys:
            want.append(fk.column.table.name)
    return [metadata.tables[n] for n in seen]


#: Everything this test owns, deleted child-first before each run. Scoped by the
#: market's own `external_id` rather than by table, which is what lets this gate
#: share a database with the ten steps that run before it in the same CI job.
_CLEAN = (
    """DELETE FROM futures_odds_snapshots s
        USING futures_outcomes o, futures_markets m
        WHERE s.outcome_id = o.id AND o.market_id = m.id
          AND m.source = 'odds_api' AND m.external_id = :k""",
    """DELETE FROM futures_outcomes o
        USING futures_markets m
        WHERE o.market_id = m.id
          AND m.source = 'odds_api' AND m.external_id = :k""",
    "DELETE FROM futures_markets WHERE source = 'odds_api' AND external_id = :k",
)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, for the tables this task touches.

    Real Postgres and not a unit double because the market upsert compiles
    through `pg_insert(...).on_conflict_do_update(...)`, which no other dialect
    emits — the block under test only runs after that statement returns an id.

    🔴 IT DOES NOT DROP. The sibling real-Postgres fixtures open with
    `drop_all()` over the WHOLE schema, which is self-consistent: everything goes,
    so every dependency goes with it. A dropping fixture scoped to four tables is
    NOT the same thing, and the difference is invisible on a laptop. Eight other
    tables hold a foreign key INTO `futures_markets` (`prediction_challenges`,
    `settlement_captures`, `curation_signals`, …); on a fresh local database
    those tables do not exist, so the scoped `drop_all` succeeded, and in CI —
    where ten earlier steps in this same job have already built the full schema
    in the same database — it raised `DependentObjectsStillExistError` and every
    test in the file ERRORed at setup. So: create what is missing, delete only
    the rows this file owns, and leave the neighbours alone.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that created
    its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = _fk_closure(
        Base.metadata,
        "sports",
        "futures_markets",
        "futures_outcomes",
        "futures_odds_snapshots",
    )

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        for stmt in _CLEAN:
            await conn.execute(text(stmt), {"k": SPORT_KEY})

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


class TestAVanishedLegRetiresToNull:
    """The ship. Master stores 0 here and the page prints `0%`."""

    async def test_the_vanished_leg_holds_no_price_rather_than_a_zero(
        self, pg_session
    ):
        await _seed(pg_session)
        stats = await _run_poll(pg_session)

        assert stats.get("stale_zeroed") == 1, (
            "the stale block never ran, so the assertion below would pass on a "
            f"seed that was simply never touched. stats: {stats}"
        )

        got = await _legs(pg_session)
        assert got[VANISHED]["prob"] is None, (
            f"{VANISHED} stored {got[VANISHED]['prob']!r}. A stored 0 serves as "
            "`probability: 0.0` and renders a flat `0%` — the site asserting the "
            "outcome is IMPOSSIBLE. All this block observed is that the venue "
            "stopped listing it, which is `-`."
        )

    async def test_the_last_quote_is_not_destroyed_with_the_price(self, pg_session):
        """The odds column is the last honest thing we know; retiring is not erasing."""
        await _seed(pg_session)
        await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[VANISHED]["american"] == VANISHED_LAST_ODDS, (
            "the surviving quote was overwritten. `current_american_odds` is the "
            "only record of what the book last said about this outcome, and the "
            "repair on the stored population keys on it being present."
        )

    async def test_the_movement_delta_retires_in_the_same_breath(self, pg_session):
        """CERT-627, co-asserted so a later edit to this block cannot drop it."""
        await _seed(pg_session)
        await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[VANISHED]["move"] is None, (
            "a dead outcome has no movement, and this line refreshes "
            "`last_updated` — the stamp the movement window expires on — so "
            "leaving the delta hands `/api/futures/movers` a market that just "
            "vanished from the feed, wearing a fresh timestamp."
        )


class TestTheBlockStillOnlyTouchesWhatItShould:
    """Both controls. A mutation that widens the retirement fails here, not above."""

    async def test_a_leg_the_venue_still_prices_is_untouched(self, pg_session):
        await _seed(pg_session)
        await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[PRICED]["prob"] is not None and float(got[PRICED]["prob"]) > 0, (
            f"{PRICED} is in the response and came back "
            f"{got[PRICED]['prob']!r} — the retirement reached a live leg."
        )

    async def test_a_leg_absent_for_only_an_hour_is_not_retired(self, pg_session):
        """The 24h floor: a transient venue omission is not a vanished outcome."""
        await _seed(pg_session)
        stats = await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[RECENTLY_ABSENT]["prob"] is not None, (
            f"{RECENTLY_ABSENT} was last seen an hour ago and is absent from ONE "
            "response. Retiring it turns every transient API omission into a "
            f"dash on the page. stats: {stats}"
        )
        assert stats.get("stale_zeroed") == 1, (
            "exactly one leg qualifies; a second retirement means the floor "
            f"stopped holding. stats: {stats}"
        )
