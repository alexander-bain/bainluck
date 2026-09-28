"""One event's failed write does not sink the rest of the Kalshi beat (#9460). Real Postgres.

## the defect

`_poll_kalshi_markets` upserts every fetched event inside the beat's one
transaction and swallows a per-event failure into `stats["errors"]`. On Postgres
a failed statement ABORTS the transaction, so every later event raised
`InFailedSQLTransactionError` at once, and nothing after the last 200-event
commit was written. Measured on production 9/28 (20:45Z beat, heavy v113):
commit batches every 200 events up to 20:51:02Z, then none. `5160 processed …
6253 errors`. New events go first, so the cascade took the EXISTING rows,
including every single-leg threshold market #9383 needed to relabel.

## the arms

* ship: an event whose market upsert fails the real way (a title over the
  `name` column's 300 characters, rejected by the server) costs only itself.
  The events after it are written, and a threshold market among them carries
  #9383's label. RED before #9460: every later event reported an error.
* kill control: with no failing event, every event lands. A savepoint that was
  opened and never released would pass the ship on the failing event alone and
  still lose the batch.

The failing shape is chosen because the server rejects it on the real upsert,
with nothing patched. The main loop writes `event.title` untruncated, where
`_create_settled_market` cuts it to `[:300]`.

Rig: the three seams of `test_kalshi_unpriced_outcome_is_recorded_real_postgres.py`
(network, `get_task_session`, Redis raised). CI job `search-recall`.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9460 gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

KICKOFF = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
CLOSE = KICKOFF + timedelta(days=1)

#: One series for every fixture, so `_floor_series_first` and the new/existing
#: partition keep the list order: the failing event sits between healthy ones.
_BEFORE = "KXNCAAFOT-26OCT03VANUGA"
_FAILING = "KXNCAAFOT-26OCT03CINARIZ"
_AFTER_THRESHOLD = "KXNCAAFOT-26OCT03BAMAMISS"
_AFTER = "KXNCAAFOT-26OCT03OSUMICH"

#: The column is `String(300)`; the server refuses one more character.
_OVERLONG_TITLE = "Cincinnati vs Arizona: Overtime " + "x" * 300

#: The venue's own leg, read 2026-09-28 (`KXNCAAFOT-26OCT03CINARIZ-1`).
_THRESHOLD_LABEL = "1+ overtime periods"


def _ot_event(event_ticker, title):
    """A single-leg NCAAF Overtime event, as the venue serves it."""
    return KalshiEvent(
        event_ticker=event_ticker,
        title=title,
        category="Sports",
        mutually_exclusive=False,
        markets=[
            KalshiMarket(
                ticker=f"{event_ticker}-1",
                event_ticker=event_ticker,
                title=_THRESHOLD_LABEL,
                yes_sub_title=_THRESHOLD_LABEL,
                status="active",
                close_time=CLOSE,
                occurrence_datetime=KICKOFF,
                yes_bid=0.04,
                yes_ask=0.06,
                last_price=0.05,
                volume=1500,
                strike_type="greater_or_equal",
                floor_strike=1.0,
            )
        ],
    )


def _events(*, with_failure):
    return [
        _ot_event(_BEFORE, "Vanderbilt vs Georgia: Overtime"),
        _ot_event(
            _FAILING,
            _OVERLONG_TITLE if with_failure else "Cincinnati vs Arizona: Overtime",
        ),
        _ot_event(_AFTER_THRESHOLD, "Alabama vs Ole Miss: Overtime"),
        _ot_event(_AFTER, "Ohio State vs Michigan: Overtime"),
    ]


async def _run_poll(session, events):
    """The REAL `_poll_kalshi_markets` on this session; returns its stats.

    Unlike the #3518 rig this does NOT assert `errors == []`: the ship arm's
    fixture fails on purpose, and the arms read the errors themselves.
    """
    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=events)
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm(**_budget):
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(patch("app.tasks.kalshi.get_task_session", _session_cm))
        es.enter_context(
            patch(
                "app.tasks.redis_state.get_redis_client",
                side_effect=RuntimeError("no Redis in this gate"),
            )
        )
        es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
        from app.tasks.kalshi import _poll_kalshi_markets

        stats = await _poll_kalshi_markets()
    await session.commit()
    return stats


async def _stored(session):
    """Ticker → (threshold_label, outcome count), read back from the SERVER."""
    rows = await session.execute(
        text(
            "SELECT m.external_id, m.market_metadata->>'threshold_label', "
            "(SELECT count(*) FROM futures_outcomes o WHERE o.market_id = m.id) "
            "FROM futures_markets m WHERE m.source = 'kalshi'"
        )
    )
    return {r[0]: (r[1], r[2]) for r in rows.fetchall()}


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


class TestOneFailedEventCostsOnlyItself:
    async def test_the_events_after_a_failed_write_are_still_written(self, pg_session):
        stats = await _run_poll(pg_session, _events(with_failure=True))
        got = await _stored(pg_session)

        # The premise: the failure is real, reported once, and is the fixture's.
        assert len(stats["errors"]) == 1 and stats["errors"][0].startswith(
            _FAILING
        ), (
            "exactly one event must fail, and it must be the overlong title. "
            f"errors: {stats['errors']!r}. More than one is #9460's cascade: "
            "the failed statement aborted the transaction and every later "
            "event raised."
        )
        assert _FAILING not in got, "the refused row must not be half-written"

        for ticker in (_BEFORE, _AFTER_THRESHOLD, _AFTER):
            assert ticker in got and got[ticker][1] == 1, (
                f"{ticker} was not written with its outcome ({got.get(ticker)}): "
                "a failed event sank its siblings"
            )
        assert stats["events_processed"] == 3, stats["events_processed"]

    async def test_a_threshold_market_after_the_failure_carries_its_label(
        self, pg_session
    ):
        """#9383's label, on the existing-row path the cascade starved."""
        await _run_poll(pg_session, _events(with_failure=True))
        got = await _stored(pg_session)
        assert got.get(_AFTER_THRESHOLD, (None,))[0] == _THRESHOLD_LABEL, (
            f"{_AFTER_THRESHOLD} stored {got.get(_AFTER_THRESHOLD)}; a market "
            "processed after a failed event must still be upserted with its "
            "threshold label"
        )


class TestTheHealthyBeatIsUntouched:
    async def test_with_no_failure_every_event_lands(self, pg_session):
        """Kill control: the savepoint is released, not left open and lost."""
        stats = await _run_poll(pg_session, _events(with_failure=False))
        got = await _stored(pg_session)

        assert stats["errors"] == [], stats["errors"]
        assert stats["events_processed"] == 4
        assert {t for t, (_, n) in got.items() if n == 1} == {
            _BEFORE,
            _FAILING,
            _AFTER_THRESHOLD,
            _AFTER,
        }, got
        assert all(label == _THRESHOLD_LABEL for label, _ in got.values()), got
