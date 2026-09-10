"""The 2-minute live poll advances the observation clock, on both venues (#4157).

## the ship

`price_observed_at` is the durable answer to "when did a venue last hand us a
price for this leg?", and the freshness marks on the site are drawn from it.
#3879 wired every price writer to stamp it — except two, both inside
`_poll_live_prediction_market_prices`, which were parked behind an ownership
boundary (D39) and named in `ORM_PRICE_ASSIGNMENTS_NOT_OURS`.

CERT-2354 blocked #3879's acceptance-1 on exactly that: the two arms of the
realtime poll wrote a real venue price and `last_updated` while leaving the
freshness clock NULL or stale. Fable-5 waived D39 for this one function
(Wed 2026-09-09 4:15am PT) so the named repair
`4157-LIVE-MATCHER-ADVANCES-THE-OBSERVATION-CLOCK` could be made here.

## why these arms and not a unit test of the helper

`apply_observed_price` already has executed unit coverage in
`tests/test_price_observed_at.py`, and it proves nothing about whether this
task reaches it — a pure function is not a call site. The AST census in that
file proves the bare assignment is *gone*; only running the task proves the
stamp is *there*. Both are kept: the census catches a new unstamped writer, this
catches the wiring being right in source and wrong in flight.

## the discriminator: unchanged price, two runs

The interesting case is not the first write, it is the second. Freshness and
movement are different questions — "when did we last hear from the venue" vs
"when did the number last change" — and a poll of an unmoved book must answer
the first and not the second. So each venue is polled TWICE with the SAME
payload:

    price_observed_at   MUST advance   (we heard from the venue again)
    price_changed_at    MUST NOT move  (the number did not change)

Both stamps are asserted NOT NULL after run 1 before the equality is asserted
after run 2. Pre-fix both columns are NULL forever, and `NULL == NULL` would
have let "did not move" pass on a column nothing ever wrote — the assertion
that matters would have been bought by the defect it is pointed at.

`TestAMovedPriceMovesBoth` is the opposite control: if the guard above were
satisfied by never stamping movement at all, this fails.

There is no local Postgres in the agent sandbox (`initdb` fails on `shmget`),
so CI's `search-recall` job is the environment that runs this; the rig is
`test_live_poll_kalshi_prices_real_postgres.py`'s.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres observation-"
            "clock round trip (CI job `search-recall` provides one)"
        ),
    ),
]

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "kalshi_markets_endpoint_20260906.json"
)
CAPTURED = {m["ticker"]: m for m in json.loads(FIXTURE.read_text())["markets"]}

EVENT_TICKER = "KXNFLGAME-26SEP21NYGLAR"
NYG = f"{EVENT_TICKER}-NYG"
LAR = f"{EVENT_TICKER}-LAR"

#: The Polymarket side. The live poll keys its outcome lookup on the
#: sub-market's `conditionId`, so the seeded row's `external_id` is that id.
POLY_EVENT_ID = "poly-event-4157"
POLY_CONDITION = "0xcondition4157"


def _poly_event(price: str) -> dict:
    """A Gamma event payload with one priced sub-market.

    A tight two-sided book, so the arm takes `outcomePrices[0]` and the
    spread-vs-lastTradePrice branch (gotcha #19) is not what is under test.
    """
    return {
        "id": POLY_EVENT_ID,
        "markets": [
            {
                "conditionId": POLY_CONDITION,
                "outcomePrices": json.dumps([price, f"{1 - float(price):.4f}"]),
                "outcomes": json.dumps(["Yes", "No"]),
                "lastTradePrice": price,
                "bestBid": f"{float(price) - 0.01:.4f}",
                "bestAsk": f"{float(price) + 0.01:.4f}",
            }
        ],
    }


async def _seed(session):
    """One live game carrying BOTH a Kalshi market and a Polymarket market.

    Both venues on one event because the two arms share a session and a beat;
    seeding them together means each test exercises the arm it names without a
    second fixture drifting away from the first.
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
        status="live",
    )
    session.add(event)
    await session.flush()

    kalshi = FuturesMarket(
        source="kalshi",
        external_id=EVENT_TICKER,
        event_id=event.id,
        name="New York G at Los Angeles R",
        category="championship",
        llm_sport_category="football",
        market_type="game_winner",
        status="open",
    )
    poly = FuturesMarket(
        source="polymarket",
        external_id=POLY_EVENT_ID,
        event_id=event.id,
        name="New York G at Los Angeles R (Polymarket)",
        category="championship",
        llm_sport_category="football",
        market_type="game_winner",
        status="open",
    )
    session.add_all([kalshi, poly])
    await session.flush()

    for ticker, name in ((NYG, "New York G"), (LAR, "Los Angeles R")):
        session.add(
            FuturesOutcome(
                market_id=kalshi.id,
                external_id=ticker,
                name=name,
                current_probability=None,
                is_winner=None,
            )
        )
    session.add(
        FuturesOutcome(
            market_id=poly.id,
            external_id=POLY_CONDITION,
            name="Los Angeles R",
            current_probability=None,
            is_winner=None,
        )
    )
    await session.flush()
    await session.commit()
    return event


async def _run_poll(session, *, kalshi_payload, poly_event):
    """Run the REAL live poll against this Postgres session, both venues stubbed
    at the network boundary only."""
    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService(api_key="test-key")
    service.get_markets = AsyncMock(return_value=(kalshi_payload, None))
    service.close = AsyncMock()

    poly_service = AsyncMock()
    poly_service.get_event_by_id = AsyncMock(return_value=poly_event)
    poly_service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(
            patch(
                "app.services.polymarket_api.PolymarketAPIService",
                return_value=poly_service,
            )
        )
        es.enter_context(
            patch("app.tasks.prediction_market_matching.get_task_session", _session_cm)
        )
        from app.tasks.prediction_market_matching import (
            _poll_live_prediction_market_prices,
        )

        stats = await _poll_live_prediction_market_prices()

    # Both arms swallow per-market failures into `stats["errors"]`, so an
    # unasserted error list lets a silently-skipped market read as a clean run.
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    await session.commit()
    return stats


async def _stamps(session, external_id):
    row = (
        await session.execute(
            text(
                "SELECT current_probability, price_observed_at, price_changed_at "
                "FROM futures_outcomes WHERE external_id = :x"
            ),
            {"x": external_id},
        )
    ).fetchone()
    assert row is not None, f"no outcome row for {external_id}"
    return {"prob": row[0], "observed": row[1], "changed": row[2]}


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


class TestTheFirstObservationIsStampedAtAll:
    """The regression gate. On the pre-repair code both columns stay NULL."""

    async def test_the_kalshi_arm_stamps_both_clocks(self, pg_session):
        await _seed(pg_session)
        stats = await _run_poll(
            pg_session,
            kalshi_payload=list(CAPTURED.values()),
            poly_event=_poly_event("0.6000"),
        )

        got = await _stamps(pg_session, LAR)
        assert got["prob"] is not None, f"the Kalshi arm wrote no price. {stats}"
        assert got["observed"] is not None, (
            "the Kalshi arm wrote a real venue price and left price_observed_at "
            "NULL — this is CERT-2354's finding, and the freshness mark on the "
            "site has nothing to read"
        )
        assert got["changed"] is not None, (
            "NULL → a price is a movement; price_changed_at must say when"
        )

    async def test_the_polymarket_arm_stamps_both_clocks(self, pg_session):
        await _seed(pg_session)
        stats = await _run_poll(
            pg_session,
            kalshi_payload=list(CAPTURED.values()),
            poly_event=_poly_event("0.6000"),
        )

        got = await _stamps(pg_session, POLY_CONDITION)
        assert got["prob"] is not None, f"the Polymarket arm wrote no price. {stats}"
        assert got["observed"] is not None, (
            "the Polymarket arm wrote a real venue price and left "
            "price_observed_at NULL — CERT-2354's second site"
        )
        assert got["changed"] is not None


class TestAnUnchangedPriceAdvancesFreshnessButNotMovement:
    """The named repair's discriminator, run on both arms.

    Each asserts NOT NULL after run 1 before comparing after run 2: on the
    pre-repair code both columns are NULL and `NULL == NULL` would buy the
    "did not move" half for free.
    """

    async def test_the_kalshi_arm(self, pg_session):
        await _seed(pg_session)
        payload = list(CAPTURED.values())

        await _run_poll(
            pg_session, kalshi_payload=payload, poly_event=_poly_event("0.6000")
        )
        first = await _stamps(pg_session, LAR)
        assert first["observed"] is not None and first["changed"] is not None

        await _run_poll(
            pg_session, kalshi_payload=payload, poly_event=_poly_event("0.6000")
        )
        second = await _stamps(pg_session, LAR)

        assert second["prob"] == first["prob"], (
            "the fixture is replayed verbatim; if the stored price moved, this "
            "test is no longer about an unchanged price"
        )
        assert second["observed"] > first["observed"], (
            "the venue handed us the same number a second time and the freshness "
            "clock did not advance — a live leg reads as stale"
        )
        assert second["changed"] == first["changed"], (
            "the price did not change, so price_changed_at must not move; a poll "
            "that touches it turns every beat into a fake movement"
        )

    async def test_the_polymarket_arm(self, pg_session):
        await _seed(pg_session)
        payload = list(CAPTURED.values())

        await _run_poll(
            pg_session, kalshi_payload=payload, poly_event=_poly_event("0.6000")
        )
        first = await _stamps(pg_session, POLY_CONDITION)
        assert first["observed"] is not None and first["changed"] is not None

        await _run_poll(
            pg_session, kalshi_payload=payload, poly_event=_poly_event("0.6000")
        )
        second = await _stamps(pg_session, POLY_CONDITION)

        assert second["prob"] == first["prob"]
        assert second["observed"] > first["observed"], (
            "the Polymarket midpoint is unmoved between beats far more often "
            "than it moves; if that case does not advance freshness, the column "
            "is stale for exactly the legs that are trading normally"
        )
        assert second["changed"] == first["changed"]


class TestAMovedPriceMovesBoth:
    """The opposite control: a guard that never stamps movement would pass above."""

    async def test_the_polymarket_arm_moves_both_clocks_on_a_real_move(
        self, pg_session
    ):
        await _seed(pg_session)
        payload = list(CAPTURED.values())

        await _run_poll(
            pg_session, kalshi_payload=payload, poly_event=_poly_event("0.6000")
        )
        first = await _stamps(pg_session, POLY_CONDITION)

        await _run_poll(
            pg_session, kalshi_payload=payload, poly_event=_poly_event("0.7500")
        )
        second = await _stamps(pg_session, POLY_CONDITION)

        assert second["prob"] != first["prob"], (
            "the second payload prices the leg at 0.75; if the stored value did "
            "not change, the arm is not reading this payload"
        )
        assert second["observed"] > first["observed"]
        assert second["changed"] > first["changed"], (
            "the number genuinely moved and price_changed_at stood still — the "
            "movement stamp is dead, and the unchanged-price test above would "
            "have passed on that same dead column"
        )
