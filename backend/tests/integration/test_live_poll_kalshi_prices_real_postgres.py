"""The venue's live price reaches the row, out of a real server (#3569).

## the ship

An outcome row that exists but holds no price renders "No price yet" on the
event page. #3518 made sure the ROW exists for every leg the venue lists; this
is the other half — the 2-minute poll putting the venue's current price INTO it.

## the defect these arms are pointed at

`_poll_live_prediction_market_prices` reads Kalshi prices off
`KalshiAPIService.get_markets`, which returns the venue's RAW JSON. It read
`yes_bid` / `yes_ask` / `last_price` and divided by 100. Those keys are ABSENT
from the venue's response — only `*_dollars` strings and `*_fp` counts remain
(measured 2026-09-06 14:40Z; `tests/fixtures/kalshi_markets_endpoint_20260906.json`
is that response verbatim, and it is what these arms feed the task). So every
market fell through the branch's `else: continue`, silently, on every beat,
while `kalshi_fetched` counted the request.

Production over the 3h before the fix, inside this function's own scope
(markets linked to live or ≤3h-away events): Polymarket **4,910** snapshots
across **54 distinct minutes**, Kalshi **0 rows — the bookmaker did not appear
in the result at all**, against 34 live Kalshi markets / 19 events / 177
outcomes the task fetched and threw away. The venues share one function, one
session and one beat, so that is an A/B, not two observations.

## why a real server

The claim is "the price is in the table", and a statement-shape assertion reads
back whatever the caller passed. Worse, the specific failure mode here is
NUMERIC and legal: a `*_dollars` string divided by 100 a second time gives
0.0022 for a 22% team, which satisfies `0 < p < 1`, stores in `Numeric(5,4)`,
charts, and blends — so an arm has to read the stored value back and judge its
SCALE, not merely its presence.

## how these arms discriminate

`test_the_venues_dollar_payload_prices_the_row` is fed the captured payload and
nothing else. On the pre-fix code every price key it reads is missing, so the
outcomes stay NULL and the arm fails — it is the regression gate, not a
smoke test. `TestTheRepairDidNotBecomeWriteAnyNumber` is the opposite control:
a wide one-sided book must still write nothing, or "the branch now writes" would
have been bought by fabricating quotes the 2-hour poll refuses.

There is no local Postgres in the agent sandbox (`initdb` fails on `shmget`), so
CI is the environment that runs this — the `search-recall` job, whose rig this
reuses.
"""

from __future__ import annotations

import json
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres live-price "
            "round trip (CI job `search-recall` provides one)"
        ),
    ),
]

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "kalshi_markets_endpoint_20260906.json"
)
CAPTURED = {m["ticker"]: m for m in json.loads(FIXTURE.read_text())["markets"]}

EVENT_TICKER = "KXNFLGAME-26SEP21NYGLAR"
NYG = f"{EVENT_TICKER}-NYG"
LAR = f"{EVENT_TICKER}-LAR"

#: Derived from the captured book, not from the code under test: NYG bid 0.22 /
#: ask 0.23 and LAR bid 0.76 / ask 0.78 are both TIGHT two-sided books, so
#: `_kalshi_yes_probability` takes the midpoint.
EXPECTED = {NYG: 0.225, LAR: 0.77}


def _wide_book(ticker: str) -> dict:
    """A venue market whose book cannot be read: wide, one-sided, never traded.

    Written in the venue's CURRENT dialect, because a control written in the
    dead dialect would be refused for the wrong reason and prove nothing.
    """
    return {
        "ticker": ticker,
        "event_ticker": EVENT_TICKER,
        "title": "Los Angeles R wins",
        "yes_sub_title": "Los Angeles R",
        "status": "active",
        "yes_bid_dollars": "0.0500",
        "yes_ask_dollars": "0.9500",
        "last_price_dollars": "0.0000",
        "volume_fp": "0",
    }


async def _seed(session, *, event_status="live"):
    """One live NFL game with a Kalshi market whose two legs hold NO price.

    That is #3518's output state and the page's "No price yet" — the row the
    live poll is supposed to fill.
    """
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    sport = Sport(key="americanfootball_nfl", name="NFL", group="American Football")
    session.add(sport)
    await session.flush()

    event = Event(
        sport_id=sport.id,
        home_team_name="Los Angeles R",
        away_team_name="New York G",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=30),
        status=event_status,
    )
    session.add(event)
    await session.flush()

    market = FuturesMarket(
        source="kalshi",
        external_id=EVENT_TICKER,
        event_id=event.id,
        name="New York G at Los Angeles R",
        category="championship",
        llm_sport_category="football",
        market_type="game_winner",
        status="open",
    )
    session.add(market)
    await session.flush()

    for ticker, name in ((NYG, "New York G"), (LAR, "Los Angeles R")):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=ticker,
                name=name,
                current_probability=None,  # "No price yet"
                is_winner=None,
            )
        )
    await session.flush()
    await session.commit()
    return event, market


async def _run_poll(session, payload):
    """Run the REAL live poll against this Postgres session.

    Two seams, both the task's own boundaries: the connection
    (`get_task_session`, which yields OUR session and does not close it) and the
    network. The service object is the REAL `KalshiAPIService` with only
    `get_markets` stubbed, so `parse_markets` — the seam the repair added — is
    the production one. Stubbing the parser too would make the round trip agree
    with the fixture by construction.
    """
    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService(api_key="test-key")
    service.get_markets = AsyncMock(return_value=(payload, None))
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(
            patch("app.tasks.prediction_market_matching.get_task_session", _session_cm)
        )
        from app.tasks.prediction_market_matching import (
            _poll_live_prediction_market_prices,
        )

        stats = await _poll_live_prediction_market_prices()

    # The Kalshi loop swallows per-market failures into `stats["errors"]` — it
    # must, one bad event may not wipe a beat — so an unasserted error list
    # would let a silently-skipped market read as a passing round trip.
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    assert stats["kalshi_fetched"] == 1, (
        f"the fixture never reached the Kalshi branch. stats: {stats}"
    )
    await session.commit()
    return stats


async def _outcomes(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.current_probability, o.current_yes_bid, "
            "       o.current_yes_ask, o.current_american_odds "
            "FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            "WHERE m.source = 'kalshi' AND m.external_id = :t"
        ),
        {"t": EVENT_TICKER},
    )
    return {
        r[0]: {"prob": r[1], "bid": r[2], "ask": r[3], "american": r[4]}
        for r in rows.fetchall()
    }


async def _kalshi_snapshots(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, s.probability, s.yes_bid, s.yes_ask, s.last_price "
            "FROM futures_odds_snapshots s "
            "JOIN futures_outcomes o ON o.id = s.outcome_id "
            "WHERE s.bookmaker = 'kalshi'"
        )
    )
    return {r[0]: {"prob": r[1], "bid": r[2], "ask": r[3], "last": r[4]} for r in rows.fetchall()}


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that created
    its engine.
    """
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


class TestTheVenuesPriceReachesTheRow:
    """The ship, and the regression gate: master fails every arm here."""

    async def test_the_venues_dollar_payload_prices_the_row(self, pg_session):
        await _seed(pg_session)
        stats = await _run_poll(pg_session, list(CAPTURED.values()))

        got = await _outcomes(pg_session)
        for ticker, expected in EXPECTED.items():
            assert got[ticker]["prob"] is not None, (
                f"{ticker} is still NULL after a poll of a payload the venue is "
                "actively trading — the event page still reads 'No price yet'. "
                f"stats: {stats}"
            )
            assert float(got[ticker]["prob"]) == pytest.approx(expected, abs=0.0001)

    async def test_the_stored_price_is_a_probability_not_a_hundredth_of_one(
        self, pg_session
    ):
        """The one wrong answer that never raises."""
        await _seed(pg_session)
        await _run_poll(pg_session, list(CAPTURED.values()))

        stored = float((await _outcomes(pg_session))[LAR]["prob"])
        assert stored > 0.5, (
            f"LAR stored at {stored}. The venue's `last_price_dollars` is "
            "'0.7900' — already a decimal probability. Dividing by 100 gives "
            "0.0079, which fits Numeric(5,4), passes 0 < p < 1, and charts a "
            "77% favourite as a 1% longshot without one exception anywhere."
        )

    async def test_the_book_itself_is_stored_beside_the_price(self, pg_session):
        await _seed(pg_session)
        await _run_poll(pg_session, list(CAPTURED.values()))

        got = await _outcomes(pg_session)
        assert float(got[NYG]["bid"]) == pytest.approx(0.22, abs=0.0001)
        assert float(got[NYG]["ask"]) == pytest.approx(0.23, abs=0.0001)
        assert got[NYG]["american"] is not None, (
            "American odds are derived at write time; a null here means the "
            "row was written by some path other than this poll"
        )

    async def test_the_chart_gets_its_point(self, pg_session):
        """`futures_odds_snapshots` is what the outcome's trend line is drawn from."""
        await _seed(pg_session)
        stats = await _run_poll(pg_session, list(CAPTURED.values()))

        snaps = await _kalshi_snapshots(pg_session)
        assert set(snaps) == {NYG, LAR}, (
            f"expected one kalshi snapshot per leg, got {sorted(snaps)}"
        )
        assert float(snaps[LAR]["prob"]) == pytest.approx(0.77, abs=0.0001)
        assert float(snaps[LAR]["last"]) == pytest.approx(0.79, abs=0.0001), (
            "the traded price is carried through to the snapshot unrounded and "
            "unscaled, separately from the midpoint it was not used for"
        )
        assert stats["futures_snapshots_written"] == 2


class TestTheKalshiCountersCanTestify:
    """`kalshi_fetched` counted requests all through the outage; these count work."""

    async def test_the_counter_is_kalshis_own_not_the_shared_one(self, pg_session):
        await _seed(pg_session)
        stats = await _run_poll(pg_session, list(CAPTURED.values()))

        assert stats["kalshi_outcomes_updated"] == 2, (
            "the Kalshi-only counter must report the two writes. `outcomes_updated` "
            "cannot: Polymarket writes thousands of rows a beat into the same "
            "number, which is how a dead branch stayed invisible. "
            f"stats: {stats}"
        )
        assert stats["kalshi_books_unreadable"] == 0
        assert stats["kalshi_outcome_unmatched"] == 0

    async def test_an_unreadable_book_is_counted_as_such(self, pg_session):
        await _seed(pg_session)
        stats = await _run_poll(pg_session, [_wide_book(LAR)])

        assert stats["kalshi_books_unreadable"] == 1, (
            "a refusal must be counted, or 'wrote nothing' and 'was never "
            f"reached' produce identical stats. stats: {stats}"
        )
        assert stats["kalshi_outcomes_updated"] == 0

    async def test_a_price_with_no_row_to_land_on_is_its_own_count(self, pg_session):
        """#3518's population, kept distinct from an unreadable book."""
        await _seed(pg_session)
        unknown = dict(CAPTURED[NYG], ticker=f"{EVENT_TICKER}-NOSUCHLEG")
        stats = await _run_poll(pg_session, [unknown])

        assert stats["kalshi_outcome_unmatched"] == 1, f"stats: {stats}"
        assert stats["kalshi_books_unreadable"] == 0, (
            "the book was perfectly readable — it is the ROW that is missing, "
            "and conflating the two would send the next reader to the wrong bug"
        )


class TestTheRepairDidNotBecomeWriteAnyNumber:
    """The opposite control: filling the branch must not fabricate quotes."""

    async def test_a_wide_one_sided_book_writes_nothing(self, pg_session):
        await _seed(pg_session)
        await _run_poll(pg_session, [_wide_book(LAR)])

        got = await _outcomes(pg_session)
        assert got[LAR]["prob"] is None, (
            f"LAR was priced at {got[LAR]['prob']} off a 0.05/0.95 book with no "
            "trade — that is a fabricated ~0.50, the exact quote the 2-hour "
            "poll's spread guard refuses (gotcha #19 / #181)"
        )
        assert await _kalshi_snapshots(pg_session) == {}, (
            "a refused price must not reach the chart either"
        )

    async def test_a_settled_event_is_not_polled_at_all(self, pg_session):
        """The task's population is live-or-imminent; nothing widened it."""
        await _seed(pg_session, event_status="completed")

        from app.services.kalshi_api import KalshiAPIService

        service = KalshiAPIService(api_key="test-key")
        service.get_markets = AsyncMock(return_value=(list(CAPTURED.values()), None))
        service.close = AsyncMock()

        @asynccontextmanager
        async def _session_cm():
            yield pg_session

        with ExitStack() as es:
            es.enter_context(
                patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
            )
            es.enter_context(
                patch(
                    "app.tasks.prediction_market_matching.get_task_session",
                    _session_cm,
                )
            )
            from app.tasks.prediction_market_matching import (
                _poll_live_prediction_market_prices,
            )

            stats = await _poll_live_prediction_market_prices()

        assert stats["kalshi_fetched"] == 0
        assert service.get_markets.await_count == 0
        assert (await _outcomes(pg_session))[LAR]["prob"] is None


# =============================================================================
# #4356 / CERT-2384's named repair: 4356-LIVE-POLLER-CANNOT-RESTORE-WITHDRAWN-LEG
# =============================================================================
#
# CERT-2384 blocked the first presentation of #4356 on exactly the right ground.
# Clearing a withdrawn leg in `_refresh_linked_game_books` (hourly) is correct
# and is NOT the ship, because THIS poller — every two minutes from T-3h, i.e.
# precisely while a reader is watching the game — fetches `status=None`, ignored
# `km.status`, recomputed the withdrawn leg's stale one-sided book (0 / 0.39 /
# 0 -> 39% via the ask-only rung) and wrote it straight back, with a snapshot.
#
# The specimen: Kalshi opened `KXNFLFIRSTTD-26SEP10SFLAR-LARNONE` at 23:15Z on
# Sep 2, opened `...-NONE` 35 minutes later, and marked the first `inactive`.
# Byte-identical `rules_primary`, `rules_secondary` and `custom_strike` — one
# outcome duplicated and taken back. `EventProps` renders the top 2 outcomes by
# probability, so the withdrawn leg was the card's HEADLINE row at 39% while the
# live leg said 2%.
#
# These arms are on a real server because the claim is "the price is GONE from
# the table", and the failure mode is a write that puts it back. A statement
# assertion cannot see a second writer.

WD_EVENT = "KXNFLFIRSTTD-26SEP10SFLAR"
WD_WITHDRAWN = f"{WD_EVENT}-LARNONE"
WD_LIVE = f"{WD_EVENT}-NONE"
WD_PLAYER = f"{WD_EVENT}-LARKWILLIAMS23"


def _leg_payload(ticker: str, status: str, *, bid: str, ask: str, sub: str) -> dict:
    """A venue leg in the CURRENT `*_dollars` dialect (#3569)."""
    return {
        "ticker": ticker,
        "event_ticker": WD_EVENT,
        "title": f"{sub}: 1st Touchdown",
        "yes_sub_title": sub,
        "status": status,
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "last_price_dollars": "0.0000",
        "volume_fp": "0",
    }


async def _seed_withdrawn(session, *, legs):
    """The First Touchdown market, with every leg ALREADY holding a price.

    Unlike `_seed` this starts from a PRICED table, because the defect is a
    stale price surviving — a seed of NULLs could not tell a clear from a
    no-op.

    `legs` is `{ticker: (probability, is_winner, calibration_probability)}`.
    """
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    sport = Sport(key="americanfootball_nfl", name="NFL", group="American Football")
    session.add(sport)
    await session.flush()

    event = Event(
        sport_id=sport.id,
        home_team_name="Los Angeles R",
        away_team_name="San Francisco",
        commence_time=datetime.now(timezone.utc) + timedelta(hours=2),
        status="scheduled",
    )
    session.add(event)
    await session.flush()

    market = FuturesMarket(
        source="kalshi",
        external_id=WD_EVENT,
        event_id=event.id,
        name="San Francisco vs Los Angeles R: First Touchdown",
        category="championship",
        llm_sport_category="football",
        market_type="first_touchdown",
        status="open",
    )
    session.add(market)
    await session.flush()

    for ticker, (prob, winner, calib) in legs.items():
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=ticker,
                name="No Touchdown" if ticker.endswith("NONE") else "Kyren Williams",
                current_probability=prob,
                current_yes_bid=0.0,
                current_yes_ask=prob,
                is_winner=winner,
                calibration_probability=calib,
            )
        )
    await session.flush()
    await session.commit()
    return event, market


async def _wd_outcomes(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.current_probability, o.current_yes_bid, "
            "       o.current_yes_ask, o.current_american_odds "
            "FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            "WHERE m.external_id = :t"
        ),
        {"t": WD_EVENT},
    )
    return {
        r[0]: {"prob": r[1], "bid": r[2], "ask": r[3], "american": r[4]}
        for r in rows.fetchall()
    }


class TestTheLivePollerCannotRestoreAWithdrawnLeg:
    """CERT-2384's required repair, proven on stored rows."""

    async def test_the_withdrawn_leg_is_cleared_and_the_live_one_is_priced(
        self, pg_session
    ):
        """The ship. Both halves in ONE pass, because the risk is a fix that
        clears everything or clears nothing — either passes a one-leg test."""
        await _seed_withdrawn(
            pg_session,
            legs={
                WD_WITHDRAWN: (0.39, None, None),
                WD_LIVE: (0.02, None, None),
            },
        )
        payload = [
            _leg_payload(WD_WITHDRAWN, "inactive", bid="0.0000", ask="0.3900",
                         sub="No Touchdown"),
            _leg_payload(WD_LIVE, "active", bid="0.0100", ask="0.0300",
                         sub="No Touchdown"),
        ]
        stats = await _run_poll(pg_session, payload)

        rows = await _wd_outcomes(pg_session)

        # THE SHIP: the withdrawn leg carries no price at all.
        assert rows[WD_WITHDRAWN]["prob"] is None, (
            "the live poller restored the withdrawn leg's price — this is the "
            "defect CERT-2384 blocked on"
        )
        for col in ("bid", "ask", "american"):
            assert rows[WD_WITHDRAWN][col] is None, f"{col} survived on a withdrawn leg"

        # THE CONTROL THAT MATTERS MOST: the live leg is still repriced. A
        # repair that stops the poller writing would pass the assertion above.
        assert rows[WD_LIVE]["prob"] is not None
        assert float(rows[WD_LIVE]["prob"]) == pytest.approx(0.02, abs=1e-6)
        assert stats["kalshi_outcomes_updated"] == 1
        assert stats["kalshi_outcomes_withdrawn_cleared"] == 1

    async def test_no_snapshot_is_written_for_a_withdrawn_leg(self, pg_session):
        """A chart point for a leg the venue took back is the same fiction as
        the price. The snapshot is what makes it survive on the chart even
        after the row is cleared."""
        await _seed_withdrawn(
            pg_session,
            legs={WD_WITHDRAWN: (0.39, None, None), WD_LIVE: (0.02, None, None)},
        )
        await _run_poll(
            pg_session,
            [
                _leg_payload(WD_WITHDRAWN, "inactive", bid="0.0000", ask="0.3900",
                             sub="No Touchdown"),
                _leg_payload(WD_LIVE, "active", bid="0.0100", ask="0.0300",
                             sub="No Touchdown"),
            ],
        )
        snaps = await _kalshi_snapshots(pg_session)
        assert WD_WITHDRAWN not in snaps, "charted a withdrawn leg"
        assert WD_LIVE in snaps, "the live leg lost its chart point"

    @pytest.mark.parametrize("status", ["closed", "settled", "finalized"])
    async def test_a_finished_leg_keeps_its_closing_line(self, pg_session, status):
        """The control the over-broad version of this fix fails.

        `inactive` is how a market is TAKEN BACK; `closed`/`settled`/`finalized`
        are how one ENDS, and their last price is the closing line calibration
        reads (gotcha #21). Measured against the venue over 3,898 legs of six
        linked series: active 663, finalized 3,234, inactive 1.
        """
        await _seed_withdrawn(pg_session, legs={WD_PLAYER: (0.095, None, None)})
        await _run_poll(
            pg_session,
            [_leg_payload(WD_PLAYER, status, bid="0.0900", ask="0.1000",
                          sub="Kyren Williams")],
        )
        rows = await _wd_outcomes(pg_session)
        assert rows[WD_PLAYER]["prob"] is not None, (
            f"a {status} leg lost its closing line"
        )

    async def test_a_graded_withdrawn_leg_is_left_alone(self, pg_session):
        """Gotcha #21: never un-price a row that has been called."""
        await _seed_withdrawn(pg_session, legs={WD_WITHDRAWN: (0.39, True, None)})
        await _run_poll(
            pg_session,
            [_leg_payload(WD_WITHDRAWN, "inactive", bid="0.0000", ask="0.3900",
                          sub="No Touchdown")],
        )
        rows = await _wd_outcomes(pg_session)
        assert rows[WD_WITHDRAWN]["prob"] is not None, "wiped a graded row"

    async def test_a_captured_closing_line_is_left_alone(self, pg_session):
        """Calibration's evidence outranks this repair."""
        await _seed_withdrawn(pg_session, legs={WD_WITHDRAWN: (0.39, None, 0.41)})
        await _run_poll(
            pg_session,
            [_leg_payload(WD_WITHDRAWN, "inactive", bid="0.0000", ask="0.3900",
                          sub="No Touchdown")],
        )
        rows = await _wd_outcomes(pg_session)
        assert rows[WD_WITHDRAWN]["prob"] is not None, "wiped a captured closing line"

    async def test_a_withdrawn_leg_we_do_not_hold_clears_nothing(self, pg_session):
        """The single-outcome fallback must NOT be reused on this path.

        That fallback lands a price that has nowhere else to go. Reusing it for
        a withdrawn leg would clear a row the venue never named — the one way
        this repair could destroy a real price — and a market with exactly ONE
        outcome is the shape that triggers it.
        """
        await _seed_withdrawn(pg_session, legs={WD_PLAYER: (0.095, None, None)})
        await _run_poll(
            pg_session,
            [_leg_payload("KXNFLFIRSTTD-26SEP10SFLAR-GHOST", "inactive",
                          bid="0.0000", ask="0.3900", sub="No Touchdown")],
        )
        rows = await _wd_outcomes(pg_session)
        assert rows[WD_PLAYER]["prob"] is not None, (
            "cleared the only outcome in the market on the strength of a leg "
            "the venue named differently"
        )
