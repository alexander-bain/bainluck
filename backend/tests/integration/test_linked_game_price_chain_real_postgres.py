"""One low-value future game, from unreadable ingest to a hero that shows a price.

## the ship, stated as the user sees it

A game the venue is actively trading stops reading **"No price yet"** on its
event page — including the games nobody has curated, nobody has put on page one,
and nobody is watching yet because they are days away.

## why this file exists, and what it is answering

CERT-2082 blocked #3518's first presentation on exactly the right ground: the
placeholder write is correct, and *creating a row is not showing a price*. The
hero does not read outcome existence — it reads the event's blended probability
— so a market with two NULL legs renders the same words it rendered before.
This is the composition the block required, and it is one test rather than three
because the failure it guards is that each half works and the chain still does
not deliver.

## the four things this drives, in order, all of them production code

1. **`_poll_kalshi_markets`** on an event whose books cannot be read — the
   #3518 half. Two ungraded, unpriced rows exist where there were none.
2. **the controls**: no other path can fill them. Each is executed here rather
   than quoted from a docstring, because "nothing else covers this" is the
   claim the whole chain rests on.
3. **`_refresh_linked_game_books`** once the venue quotes — the #3569 half,
   reading the venue's CURRENT `*_dollars` dialect through the service parser,
   one request per series.
4. **`_phase2_persist_group_reading`** — the 15-minute matcher's own writer, the
   one that stamps `Event.win_probability_sources` for a SCHEDULED event — and
   then `compute_aggregate_probability`, which is the function behind the hero's
   `homeProb === null && awayProb === null` test in
   `frontend/components/EventHeroProbabilityPair.tsx`. That expression returning
   a number is the ship, expressed in the code the page actually branches on.

## the specimen is deliberately the least-covered event in the system

Two days out (so the 2-minute live poll's live-or-≤3h scope excludes it), no
volume recorded, in no tournament register, on no served page-one payload. Every
one of those is asserted, not assumed: an accidentally-valuable fixture would be
rescued by `futures_price_refresh` and this file would pass while the defect it
names stayed open for the 415 linked markets that look like this one.

There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`), so
CI is the environment that runs this — the `search-recall` job.
"""

from __future__ import annotations

import json
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.services.kalshi_api import KalshiEvent, KalshiMarket

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres linked-game "
            "price chain (CI job `search-recall` provides one)"
        ),
    ),
]

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "kalshi_markets_endpoint_20260906.json"
)
#: The venue's own bytes, `*_dollars` and all (captured 2026-09-06 14:40Z).
CAPTURED = {m["ticker"]: m for m in json.loads(FIXTURE.read_text())["markets"]}

EVENT_TICKER = "KXNFLGAME-26SEP21NYGLAR"
SERIES = "KXNFLGAME"
NYG = f"{EVENT_TICKER}-NYG"
LAR = f"{EVENT_TICKER}-LAR"

#: Midpoints of the captured books. Derived from the fixture, not from the code
#: under test — and DIFFERENT from each other, so a swapped assignment fails
#: rather than passing on a symmetric pair.
EXPECTED = {NYG: 0.225, LAR: 0.77}

HOME = "Los Angeles R"
AWAY = "New York G"


def _unreadable_leg(suffix: str, name: str) -> KalshiMarket:
    """A leg the venue LISTS before its book opens: no bid, no ask, no trade."""
    return KalshiMarket(
        ticker=f"{EVENT_TICKER}-{suffix}",
        event_ticker=EVENT_TICKER,
        title=f"{name} wins",
        yes_sub_title=name,
        status="active",
        close_time=datetime.now(timezone.utc) + timedelta(days=10),
        occurrence_datetime=datetime.now(timezone.utc) + timedelta(days=2),
        yes_bid=None,
        yes_ask=None,
        last_price=None,
        volume=0,
    )


def _venue_event_before_the_book_opens() -> KalshiEvent:
    return KalshiEvent(
        event_ticker=EVENT_TICKER,
        title=f"{AWAY} at {HOME}",
        category="Football",
        mutually_exclusive=True,
        markets=[_unreadable_leg("NYG", AWAY), _unreadable_leg("LAR", HOME)],
    )


@asynccontextmanager
async def _yields(session):
    yield session


def _matcher_stats() -> dict:
    """The stats dict Phase 2's writer is called with, keys and all.

    Deliberately NOT a defaultdict. The writer increments named counters, so a
    dict that invents a missing key would let this file keep passing while the
    caller and the writer disagreed about what is being counted — and a
    disagreement there is how a run reports work it did not do.
    """
    return {
        "markets_scanned": 0,
        "newly_linked": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "orphaned_snapshots_deleted": 0,
        "errors": [],
        "funnel": {},
    }


async def _run_ingest(session, venue_event):
    """Step 1: the REAL 2-hour poll, on the seams it already owns.

    Network (`KalshiAPIService`), connection (`get_task_session`, yielding OUR
    session), Redis (raised, so every marker/cursor branch takes its no-op path
    and the post-loop fix-ups stay dry runs). The rig is
    `test_kalshi_unpriced_outcome_is_recorded_real_postgres.py`'s.
    """
    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=[venue_event])
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(patch("app.tasks.kalshi.get_task_session", _session_cm))
        es.enter_context(
            patch(
                "app.tasks.redis_state.get_redis_client",
                side_effect=RuntimeError("no Redis in this gate — take the None branch"),
            )
        )
        es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
        from app.tasks.kalshi import _poll_kalshi_markets

        stats = await _poll_kalshi_markets()

    assert stats["errors"] == [], f"the ingest reported errors: {stats['errors']}"
    await session.commit()
    return stats


async def _link_to_a_future_event(session):
    """The matcher's job, done directly: this chain is about PRICE, not linkage.

    Two days out, so the specimen sits outside the 2-minute poll's
    live-or-within-3h scope by construction rather than by luck.
    """
    from app.models.models import Event, Sport

    sport = Sport(key="americanfootball_nfl", name="NFL", group="American Football")
    session.add(sport)
    await session.flush()

    event = Event(
        sport_id=sport.id,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=datetime.now(timezone.utc) + timedelta(days=2),
        status="scheduled",
    )
    session.add(event)
    await session.flush()

    await session.execute(
        text(
            "UPDATE futures_markets SET event_id = :eid, volume = NULL, "
            "       market_tier = 5, llm_sport_category = 'football' "
            " WHERE source = 'kalshi' AND external_id = :t"
        ),
        {"eid": event.id, "t": EVENT_TICKER},
    )
    await session.commit()
    return event


async def _run_linked_book_refresh(session, raw_markets):
    """Step 3: the REAL per-series pass, with only the network stubbed.

    The service object is real, so `parse_markets` — the seam that reads the
    venue's current dialect — is production code rather than a fixture's idea of
    it. `get_markets` returns the venue's raw JSON, exactly as the venue does.
    """
    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService(api_key="test-key")
    service.get_markets = AsyncMock(return_value=(raw_markets, None))
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(patch("app.tasks.kalshi.get_task_session", _session_cm))
        from app.tasks.kalshi import _refresh_linked_game_books

        stats = await _refresh_linked_game_books()

    assert stats["errors"] == [], f"the refresh reported errors: {stats['errors']}"
    await session.commit()
    return stats, service


async def _outcomes(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.current_probability, o.is_winner "
            "  FROM futures_outcomes o "
            "  JOIN futures_markets m ON m.id = o.market_id "
            " WHERE m.source = 'kalshi' AND m.external_id = :t"
        ),
        {"t": EVENT_TICKER},
    )
    return {r[0]: {"prob": r[1], "is_winner": r[2]} for r in rows.fetchall()}


async def _market_id(session) -> int:
    return (
        await session.execute(
            text(
                "SELECT id FROM futures_markets "
                " WHERE source = 'kalshi' AND external_id = :t"
            ),
            {"t": EVENT_TICKER},
        )
    ).scalar()


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


@pytest.fixture
async def unpriced_and_linked(pg_session):
    """Steps 1-2: ingested with unreadable books, linked to an event 2 days out."""
    await _run_ingest(pg_session, _venue_event_before_the_book_opens())
    event = await _link_to_a_future_event(pg_session)
    return pg_session, event


class TestStepOneTheRowsExistAndAreUngraded:
    async def test_two_unpriced_rows_exist_after_an_unreadable_ingest(
        self, unpriced_and_linked
    ):
        session, _event = unpriced_and_linked
        got = await _outcomes(session)

        assert set(got) == {NYG, LAR}, f"#3518's write did not land: {got}"
        for ticker, row in got.items():
            assert row["prob"] is None, f"{ticker} was given a price nobody quoted"
            assert row["is_winner"] is None, (
                f"{ticker} was born graded — `boolean NULL DEFAULT false` means an "
                "omitted is_winner is an affirmative LOSS (CAL-P1004R)"
            )


class TestNothingElseCouldHaveFilledThem:
    """The claim the whole chain rests on, executed rather than quoted."""

    async def test_the_two_minute_poll_does_not_reach_a_game_two_days_out(
        self, unpriced_and_linked
    ):
        session, _event = unpriced_and_linked

        service = MagicMock()
        service.get_markets = AsyncMock(return_value=(list(CAPTURED.values()), None))
        service.close = AsyncMock()

        with ExitStack() as es:
            es.enter_context(
                patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
            )
            es.enter_context(
                patch(
                    "app.tasks.prediction_market_matching.get_task_session",
                    lambda: _yields(session),
                )
            )
            from app.tasks.prediction_market_matching import (
                _poll_live_prediction_market_prices,
            )

            stats = await _poll_live_prediction_market_prices()

        assert stats["kalshi_fetched"] == 0
        assert service.get_markets.await_count == 0, (
            "the live poll asked the venue about an event two days out — its "
            "scope is live-or-within-3h and this specimen must sit outside it, "
            "or the chain below proves nothing about the 415 markets that do"
        )
        assert (await _outcomes(session))[NYG]["prob"] is None

    async def test_the_hourly_value_sweep_does_not_select_it(
        self, unpriced_and_linked
    ):
        """Low volume, no tier-1 fence, no register, no served page — no arm."""
        session, _event = unpriced_and_linked
        from app.tasks.futures_price_refresh import (
            HIGH_VALUE_VOLUME_FLOOR,
            STALE_AFTER_HOURS,
            _scan_candidates,
        )

        picked = await _scan_candidates(
            session,
            volume_floor=HIGH_VALUE_VOLUME_FLOOR,
            stale_hours=STALE_AFTER_HOURS,
        )

        assert await _market_id(session) not in {m["id"] for m in picked}, (
            "the value arm selected the specimen, so this file would be testing "
            "a market `futures_price_refresh` already covers"
        )

    async def test_the_refresh_writer_refuses_to_create_the_missing_row(
        self, unpriced_and_linked
    ):
        """#2199's stated refusal, exercised — a price for an id we do not hold."""
        session, _event = unpriced_and_linked
        from app.tasks.futures_price_refresh import _write_prices

        stats = {"unknown_outcomes": 0}
        written = await _write_prices(
            session,
            await _market_id(session),
            "kalshi",
            [
                {
                    "external_id": f"{EVENT_TICKER}-NOSUCHLEG",
                    "probability": 0.5,
                    "yes_bid": 0.49,
                    "yes_ask": 0.51,
                    "last_price": 0.5,
                }
            ],
            stats,
        )

        assert written == 0
        assert stats["unknown_outcomes"] == 1, (
            "the price refresh is supposed to DROP a price whose outcome row is "
            "missing — if that changed, the linked-game pass is redundant and "
            "should be deleted rather than left as a second writer"
        )


class TestStepTwoTheVenuesPriceLands:
    async def test_each_leg_gets_the_price_of_its_own_ticker(
        self, unpriced_and_linked
    ):
        session, _event = unpriced_and_linked
        stats, _service = await _run_linked_book_refresh(
            session, list(CAPTURED.values())
        )

        got = await _outcomes(session)
        for ticker, expected in EXPECTED.items():
            assert got[ticker]["prob"] is not None, (
                f"{ticker} is still NULL after the venue quoted it. stats: {stats}"
            )
            assert float(got[ticker]["prob"]) == pytest.approx(expected, abs=0.0001), (
                f"{ticker} got {got[ticker]['prob']}, expected {expected}. The two "
                "legs carry different prices on purpose: a swap, or a price keyed "
                "by response position instead of by the market's own ticker, "
                "cannot pass this."
            )
        assert stats["outcomes_repriced"] == 2
        assert stats["markets_reached"] == 1

    async def test_the_price_is_not_scaled_by_a_hundred(self, unpriced_and_linked):
        session, _event = unpriced_and_linked
        await _run_linked_book_refresh(session, list(CAPTURED.values()))

        stored = float((await _outcomes(session))[LAR]["prob"])
        assert stored > 0.5, (
            f"LAR stored at {stored}. `last_price_dollars` is '0.7900' — already "
            "decimal. Dividing by 100 gives 0.0079, which fits the column, passes "
            "0 < p < 1, and charts a 77% favourite as a 1% longshot silently."
        )

    async def test_one_request_per_series_not_one_per_event(
        self, unpriced_and_linked
    ):
        """The bound the block asked for, read off the call rather than asserted in prose."""
        session, _event = unpriced_and_linked
        _stats, service = await _run_linked_book_refresh(
            session, list(CAPTURED.values())
        )

        assert service.get_markets.await_count == 1
        kwargs = service.get_markets.await_args.kwargs
        assert kwargs.get("series_ticker") == SERIES, (
            f"the pass fetched with {kwargs} — asking per EVENT makes its cost "
            "scale with the slate (415 markets) instead of with the leagues (62)"
        )
        assert kwargs.get("event_ticker") is None

    async def test_a_graded_row_is_never_repriced(self, unpriced_and_linked):
        """Gotcha #21, against the tri-state that actually exists in this column."""
        session, _event = unpriced_and_linked
        await session.execute(
            text(
                "UPDATE futures_outcomes SET is_winner = TRUE, "
                "       current_probability = 1.0 "
                " WHERE external_id = :t"
            ),
            {"t": LAR},
        )
        await session.commit()

        await _run_linked_book_refresh(session, list(CAPTURED.values()))

        got = await _outcomes(session)
        assert float(got[LAR]["prob"]) == pytest.approx(1.0), (
            "a settled leg was re-priced off a book that is still quoting — "
            "re-pricing resolved state can only corrupt it"
        )
        assert float(got[NYG]["prob"]) == pytest.approx(0.225, abs=0.0001), (
            "the unsettled sibling must still be priced, or the settled guard is "
            "just a switch that turns the pass off"
        )


class TestStepThreeTheHeroStopsSayingNoPriceYet:
    """`compute_aggregate_probability` is the function behind the hero's test."""

    async def test_the_event_carries_no_reading_before_the_chain_runs(
        self, unpriced_and_linked
    ):
        """The before half. Without it, the after half is a fact about defaults."""
        session, event = unpriced_and_linked
        from app.utils.aggregation import compute_aggregate_probability

        assert compute_aggregate_probability(event) is None, (
            "the fixture already had a probability, so the arm below cannot "
            "attribute one to this chain"
        )

    async def test_the_matchers_writer_stamps_kalshi_once_the_rows_are_priced(
        self, unpriced_and_linked
    ):
        session, event = unpriced_and_linked
        await _run_linked_book_refresh(session, list(CAPTURED.values()))

        from app.tasks.prediction_market_matching import (
            _LinkedMarketRef,
            _phase2_persist_group_reading,
        )
        from app.utils.aggregation import compute_aggregate_probability

        market_row = (
            await session.execute(
                text(
                    "SELECT id, event_id, source, external_id, name "
                    "  FROM futures_markets WHERE external_id = :t"
                ),
                {"t": EVENT_TICKER},
            )
        ).first()

        # The same scalar copy Phase 2 builds for its own loop — not a stand-in
        # shape invented here (`_LinkedMarketRef` exists because the loop commits
        # per market and an expired ORM row raises MissingGreenlet).
        spoke = await _phase2_persist_group_reading(
            session,
            [
                _LinkedMarketRef(
                    market_id=market_row.id,
                    source=market_row.source,
                    external_id=market_row.external_id,
                    name=market_row.name,
                    event_id=market_row.event_id,
                    event_commence_time=event.commence_time,
                    home_team_name=HOME,
                    away_team_name=AWAY,
                )
            ],
            _matcher_stats(),
        )
        await session.commit()
        assert spoke is not None, (
            "the matcher's own writer declined to speak for a fully priced "
            "two-leg game — the reading never reaches the event, and the hero "
            "keeps saying 'No price yet' however good the outcome rows are"
        )

        await session.refresh(event)
        assert (event.win_probability_sources or {}).get("kalshi") is not None
        assert compute_aggregate_probability(event) is not None, (
            "this expression is what the hero branches on "
            "(`homeProb === null && awayProb === null` in "
            "EventHeroProbabilityPair.tsx). Non-null here is the ship."
        )

    async def test_the_stats_dict_this_file_passes_covers_what_the_writer_counts(self):
        """CI found this the hard way: a missing key is a KeyError mid-write.

        The writer increments named counters, so the caller's dict is part of its
        contract. Scanning the writer rather than listing the keys means the two
        cannot drift apart the next time a counter is added.
        """
        import inspect
        import re

        from app.tasks.prediction_market_matching import (
            _phase2_persist_group_reading,
        )

        counted = set(
            re.findall(
                r'stats\[["\'](\w+)["\']\]\s*\+=',
                inspect.getsource(_phase2_persist_group_reading),
            )
        )
        assert counted, "the scan found no counters — it can no longer testify"
        assert counted <= set(_matcher_stats()), (
            f"the writer counts {sorted(counted - set(_matcher_stats()))}, which "
            "this file does not pass it — the arm above would die on a KeyError "
            "inside the write rather than on the claim it is making"
        )

    async def test_the_writer_this_file_drives_is_the_one_the_matcher_calls(self):
        """A guard against proving the chain through a function nobody runs."""
        import inspect

        from app.tasks.prediction_market_matching import _match_prediction_markets

        assert "_phase2_persist_group_reading" in inspect.getsource(
            _match_prediction_markets
        ), (
            "the 15-minute matcher no longer calls the writer this file drives, "
            "so the last link of this chain is no longer a shipping path"
        )
