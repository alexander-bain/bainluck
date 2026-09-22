"""#8022: which empty-event markets are even ELIGIBLE to be confirmed purged, on a REAL PostgreSQL.

## why this half needs a real server

`_select_purge_confirmable_markets()` is the PRECONDITION of the purge repair: of
the markets whose Kalshi event answered `200 markets:[]`, which ones does *our own
row* describe unambiguously enough that a venue purge should settle them? The whole
claim is three aggregate HAVING clauses:

    HAVING COUNT(*) FILTER (WHERE resolution_source IN <authoritative>) = COUNT(*)
       AND COUNT(*) FILTER (WHERE is_winner IS TRUE) = 1
       AND COUNT(*) FILTER (WHERE is_winner IS TRUE
                              AND resolution_source IN <authoritative>) = 1

A fake session cannot test any of that. It answers "any statement mentioning
`futures_markets`" with a canned list, so a row is absent only because the test
author left it out — delete a HAVING clause, or the `source = 'kalshi'` filter, or
the `status <> 'resolved'` filter, and a unit rig still passes. `FILTER` is also
real Postgres syntax with real NULL semantics, and `COALESCE(resolution_source,'')`
against a NULL leg is exactly the kind of thing that reads fine and behaves
otherwise. So this gate runs against the real schema and the real planner.

## what the precondition is FOR, and what it is deliberately not

It is not the licence. Band 5's own docstring already measured the trap: "every leg
authoritatively graded" is **1,160 rows of which 0 of 69 probed were terminal at the
venue**, because the CAL-P1004 fabricator writes `api_settlement` onto markets the
venue still calls `active`. So this selector answers only "is our verdict complete
and single-winner"; `_resolve_purge_confirmed_markets` must then get
`Disposition.PURGED` from Kalshi's market channel before anything is written. The
two halves live in different functions so a later edit cannot quietly drop the
second, and `tests/test_purged_kalshi_market_stops_reading_live_8022.py` guards it.

## the corpus

Nine markets, eight of which must be REFUSED. The admitted pair are the shopper's
own specimens reduced to their stored shape; the refusals are each one clause.

`ZERO_WINNERS` is worth naming: the shopper found two of those on the same page
(109889 Ohio Republican Governor nominee, 109796 North Carolina Democratic Senate
nominee — `settled: true`, no graded winner). That is a DIFFERENT state, closer to
#2077, and this rail must not touch it: settling a market whose winner we do not
know would print a settled page with no result on it.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres purge-confirmable "
        "selector gate (CI job `search-recall` provides one)"
    ),
)


#: `(key, source, status, external_id, [(leg_suffix, is_winner, resolution_source)])`
#:
#: Leg sources are quoted from `resolution_authority.AUTHORITATIVE_SOURCES`, never
#: invented — `api_settlement` is what Kalshi's own grader writes and is what all
#: nine production specimens carry.
def _corpus():
    return [
        # ---- ADMITTED: a complete, single-winner, authoritative verdict --------
        # `/futures/109903`, the shopper's hero specimen. Rob Sand won the Iowa
        # Democratic primary in June; Kalshi graded all three legs on 2026-07-24.
        (
            "IOWA_DEM_GOV",
            "kalshi",
            "open",
            "KXGOVIANOMD-26",
            [
                ("RSAN", True, "api_settlement"),
                ("JSTA", False, "api_settlement"),
                ("PDAH", False, "api_settlement"),
            ],
        ),
        # A second authoritative source, so the rail is not accidentally welded to
        # the string `api_settlement` when the predicate says "the tier-3 set".
        (
            "CLEAN_RESOLUTION_SOURCE",
            "kalshi",
            "open",
            "KXSENATEMTR-26",
            [
                ("KALM", True, "clob_authoritative"),
                ("CWAL", False, "clob_authoritative"),
            ],
        ),
        # ---- REFUSED: one clause each -----------------------------------------
        # A ladder mid-flight: the winner is graded, two legs are not. This is the
        # ORDINARY shape of an open market and the population's dominant one.
        (
            "PARTIAL_GRADE",
            "kalshi",
            "open",
            "KXPARTIAL-26",
            [
                ("W", True, "api_settlement"),
                ("U1", None, None),
                ("U2", None, None),
            ],
        ),
        # Two winners: our renderer picks with `outcomes.find(o => o.is_winner)`,
        # so settling this would put whichever leg sorts first on the hero.
        (
            "MULTI_WINNER",
            "kalshi",
            "open",
            "KXMULTI-26",
            [
                ("W1", True, "api_settlement"),
                ("W2", True, "api_settlement"),
                ("L", False, "api_settlement"),
            ],
        ),
        # Every leg graded, none a winner — the #2077-adjacent state the shopper
        # found twice. Settling it would print a settled page with no result.
        (
            "ZERO_WINNERS",
            "kalshi",
            "open",
            "KXNOWINNER-26",
            [
                ("A", False, "api_settlement"),
                ("B", False, "api_settlement"),
            ],
        ),
        # The winner is a GUESS, not the venue's word. `price_crown` is outside
        # AUTHORITATIVE_SOURCES; band 5 would not even have selected this row.
        (
            "UNAUTHORITATIVE_WINNER",
            "kalshi",
            "open",
            "KXGUESS-26",
            [
                ("W", True, "price_crown"),
                ("L", False, "api_settlement"),
            ],
        ),
        # Already settled: nothing to do, and re-writing it would move settled_at.
        (
            "ALREADY_RESOLVED",
            "kalshi",
            "resolved",
            "KXDONE-26",
            [
                ("W", True, "api_settlement"),
                ("L", False, "api_settlement"),
            ],
        ),
        # Same perfect shape, wrong venue. The Kalshi market channel knows nothing
        # about a Polymarket condition id, so `source = 'kalshi'` is load-bearing.
        (
            "POLYMARKET_TWIN",
            "polymarket",
            "open",
            "KXPOLY-26",
            [
                ("W", True, "clob_authoritative"),
                ("L", False, "clob_authoritative"),
            ],
        ),
        # Perfect shape, but never handed in as a candidate: proves the
        # `external_id = ANY(:tickers)` bind actually binds rather than the
        # selector returning the whole population.
        (
            "NOT_A_CANDIDATE",
            "kalshi",
            "open",
            "KXUNASKED-26",
            [
                ("W", True, "api_settlement"),
                ("L", False, "api_settlement"),
            ],
        ),
    ]


#: Everything we hand the selector. `NOT_A_CANDIDATE` is deliberately absent.
CANDIDATES = [
    "KXGOVIANOMD-26",
    "KXSENATEMTR-26",
    "KXPARTIAL-26",
    "KXMULTI-26",
    "KXNOWINNER-26",
    "KXGUESS-26",
    "KXDONE-26",
    "KXPOLY-26",
]


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason the sibling PG gates record: `pytest.ini` leaves
    `asyncio_default_fixture_loop_scope` unset, so a module-scoped async fixture
    would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await _seed(conn)

    yield engine

    await engine.dispose()


async def _seed(conn) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK OPTIONAL.
    `futures_markets.category` / `.mutually_exclusive` / `.status` carry a
    **client-side `default=`** applied by the ORM and invisible to a raw INSERT, so
    omitting one raises `NotNullViolation` rather than taking the default.
    `tests/test_pg_gate_seed_completeness.py` parses these statements against live
    ORM metadata and this file is enrolled in its `COVERED` tuple.
    """
    for key, source, status, ext, outcomes in _corpus():
        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, status) "
                    "VALUES (:source, :ext, :name, 'championship', true, :status) "
                    "RETURNING id"
                ),
                {
                    "source": source,
                    "ext": ext,
                    "name": f"{key} market",
                    "status": status,
                },
            )
        ).scalar_one()

        for leg_ext, is_winner, resolution_source in outcomes:
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes "
                    "(market_id, external_id, name, is_winner, resolution_source) "
                    "VALUES (:mid, :ext, :name, :w, :src)"
                ),
                {
                    "mid": market_id,
                    "ext": f"{ext}-{leg_ext}",
                    "name": f"{key} {leg_ext}",
                    "w": is_winner,
                    "src": resolution_source,
                },
            )


async def _select(engine, tickers=None):
    from app.tasks.backfill_winners import _select_purge_confirmable_markets

    async with engine.connect() as conn:
        return await _select_purge_confirmable_markets(
            conn, CANDIDATES if tickers is None else tickers
        )


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


@needs_postgres
@pytest.mark.asyncio
async def test_a_complete_single_winner_verdict_is_confirmable(pg_engine):
    """The shopper's specimen is eligible, and the leg ticker comes back with it.

    The winning leg's ticker is the whole reason this returns pairs: our
    `external_id` is an EVENT ticker, and `GET /markets/{event_ticker}` 404s for
    every event that ever existed, which would collapse the two-channel protocol
    into the "empty ⇒ settled" rule it exists to refuse.
    """
    rows = dict(await _select(pg_engine))

    assert "KXGOVIANOMD-26" in rows
    assert rows["KXGOVIANOMD-26"] == "KXGOVIANOMD-26-RSAN"


@needs_postgres
@pytest.mark.asyncio
async def test_the_predicate_is_the_authoritative_SET_not_the_string_api_settlement(
    pg_engine,
):
    rows = dict(await _select(pg_engine))

    assert rows.get("KXSENATEMTR-26") == "KXSENATEMTR-26-KALM"


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,why",
    [
        ("KXPARTIAL-26", "two legs ungraded — an ordinary ladder mid-flight"),
        ("KXMULTI-26", "two winners — the hero would take whichever sorts first"),
        ("KXNOWINNER-26", "no winner — a settled page with no result on it"),
        ("KXGUESS-26", "the winner is a guess, not the venue's word"),
        ("KXDONE-26", "already resolved; re-writing it would move settled_at"),
        ("KXPOLY-26", "not Kalshi — the market channel cannot answer for it"),
    ],
)
async def test_every_incomplete_or_ambiguous_shape_is_refused(pg_engine, ticker, why):
    """Enumerated, not spot-checked.

    The failure mode is a DROPPED clause, and each of these rows is admitted by
    exactly one such drop — so a single negative specimen would leave five of the
    six mutations alive.
    """
    rows = dict(await _select(pg_engine))

    assert ticker not in rows, f"{ticker} should be refused: {why}"


@needs_postgres
@pytest.mark.asyncio
async def test_only_the_tickers_handed_in_are_considered(pg_engine):
    """`KXUNASKED-26` has the perfect shape and was never offered as a candidate.

    Without this the selector could ignore its bind and sweep the whole table,
    which on production would hand the probe rail thousands of rows instead of a
    cycle's bounded empty bucket.
    """
    rows = dict(await _select(pg_engine))

    assert "KXUNASKED-26" not in rows
    assert set(rows) == {"KXGOVIANOMD-26", "KXSENATEMTR-26"}


@needs_postgres
@pytest.mark.asyncio
async def test_an_empty_candidate_list_selects_nothing(pg_engine):
    """The short-circuit, proven against the server rather than by reading it."""
    assert await _select(pg_engine, tickers=[]) == []
