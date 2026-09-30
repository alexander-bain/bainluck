"""The Kalshi beat upserts the existing rows it wrote longest ago first (#9543). Real Postgres.

## the defect

`_poll_kalshi_markets` breaks on a 480s deadline every beat and walked the
existing partition in the venue's listing order, the same order every beat, so
the same tail was cut off every beat. The production scan report on 2026-09-29
read `starved` on three straight beats with 9,436–17,579 existing events
unreached per beat. 60481264 (Pokemon Up/Down) had not been written since
06:57Z 9/28, so #9383's threshold label never reached it and the page kept
printing "Yes".

## the arms

* ship: the poll reads each existing row's `volume_updated_at` (the stamp only
  this poll writes on a Kalshi row) from the SERVER and hands the loop the
  existing events oldest-first, never-stamped first, after the new events.
  RED before #9543: the loop got them in listing order.
* control: rows the poll has never seen still go first. #995's creation fix
  must not be traded for the rotation.

The order is read at `_floor_series_first`, the last step before the loop. A
truncated beat cannot be staged here without faking the clock the event loop
also runs on, so the gate pins the order the deadline cuts.

Rig: the three seams of the #9460 gate (network, `get_task_session`, Redis
raised). CI job `search-recall`.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9543 gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

KICKOFF = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
CLOSE = KICKOFF + timedelta(days=1)

#: One series, so `_floor_series_first` keeps whatever order it is handed.
#: Listing order is RECENT, STALE, NEVER — the reverse of the order they are owed.
_RECENT = "KXNCAAFOT-26OCT03VANUGA"
_STALE = "KXNCAAFOT-26OCT03BAMAMISS"
_NEVER = "KXNCAAFOT-26OCT03OSUMICH"
_NEW = "KXNCAAFOT-26OCT03CINARIZ"

_THRESHOLD_LABEL = "1+ overtime periods"


def _ot_event(event_ticker, title, status="active"):
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
                status=status,
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


_TITLES = {
    _RECENT: "Vanderbilt vs Georgia: Overtime",
    _STALE: "Alabama vs Ole Miss: Overtime",
    _NEVER: "Ohio State vs Michigan: Overtime",
    _NEW: "Cincinnati vs Arizona: Overtime",
}


def _events(*tickers):
    return [_ot_event(t, _TITLES[t]) for t in tickers]


async def _run_poll(session, events, record="_floor_series_first"):
    """The REAL `_poll_kalshi_markets` on this session.

    Returns ``(stats, order)``: ``order`` is the ticker list returned by the
    real ordering step named in ``record`` (default `_floor_series_first`).
    `_settled_rows_last` is the last step before the loop.
    """
    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=events)
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm(**_budget):
        yield session

    from app.tasks import kalshi as kalshi_mod

    real_step = getattr(kalshi_mod, record)
    seen: list[list[str]] = []

    def _recording_step(*args):
        out = real_step(*args)
        seen.append([e.event_ticker for e in out])
        return out

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
        es.enter_context(
            patch(f"app.tasks.kalshi.{record}", _recording_step)
        )
        es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
        stats = await kalshi_mod._poll_kalshi_markets()
    await session.commit()
    assert len(seen) == 1, f"the loop order was built {len(seen)} times"
    return stats, seen[0]


async def _seed_existing(session):
    """Three existing rows, then their poll stamps: 1h ago, 30h ago, never."""
    stats, _ = await _run_poll(session, _events(_RECENT, _STALE, _NEVER))
    assert stats["errors"] == [], stats["errors"]
    now = datetime.now(timezone.utc)
    for ticker, stamp in (
        (_RECENT, now - timedelta(hours=1)),
        (_STALE, now - timedelta(hours=30)),
        (_NEVER, None),
    ):
        await session.execute(
            text(
                "UPDATE futures_markets SET volume_updated_at = :s "
                "WHERE source = 'kalshi' AND external_id = :t"
            ),
            {"s": stamp, "t": ticker},
        )
    await session.commit()


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


class TestTheStalestExistingRowsGoFirst:
    async def test_existing_rows_are_handed_to_the_loop_oldest_poll_first(
        self, pg_session
    ):
        await _seed_existing(pg_session)
        stats, order = await _run_poll(
            pg_session, _events(_RECENT, _STALE, _NEVER, _NEW)
        )

        assert stats["errors"] == [], stats["errors"]
        assert order == [_NEW, _NEVER, _STALE, _RECENT], (
            f"loop order {order}. Expected new first (#995), then existing "
            "rows by when this poll last wrote them: never, 30h, 1h. Listing "
            f"order {[_RECENT, _STALE, _NEVER]} for the existing three is "
            "#9543's defect: the same tail is cut off every beat."
        )

    async def test_the_reached_rows_carry_a_fresh_stamp(self, pg_session):
        """The rotation's input moves: a reached row is not stale next beat."""
        await _seed_existing(pg_session)
        await _run_poll(pg_session, _events(_RECENT, _STALE, _NEVER, _NEW))
        rows = await pg_session.execute(
            text(
                "SELECT external_id, volume_updated_at FROM futures_markets "
                "WHERE source = 'kalshi'"
            )
        )
        stamps = dict(rows.fetchall())
        floor = datetime.now(timezone.utc) - timedelta(minutes=10)
        for ticker in (_NEVER, _STALE, _RECENT, _NEW):
            assert stamps.get(ticker) is not None and stamps[ticker] > floor, (
                f"{ticker} stamp {stamps.get(ticker)}: the upsert must rewrite "
                "volume_updated_at, or the stalest row stays stalest forever "
                "and the rotation never turns"
            )


class TestCreationStillGoesFirst:
    async def test_a_row_the_poll_has_never_seen_precedes_every_existing_row(
        self, pg_session
    ):
        """Control: #995's new-first order survives, whatever the stamps say."""
        await _seed_existing(pg_session)
        _, order = await _run_poll(
            pg_session, _events(_NEVER, _STALE, _NEW, _RECENT)
        )
        assert order[0] == _NEW, (
            f"loop order {order}: a never-seen event must be created before "
            "any existing row is rewritten (#995)"
        )


class TestSettledRowsGoBehindTheOpenTail:
    """After heavy v116, oldest-first ordering put months of settled floor games
    ahead of the open tail. In one beat, 6,685 of 7,361 rewrites wrote
    ``resolved`` back onto ``resolved`` rows, and 60481264 was still unreached.
    Arms: a row settled on both sides goes last; a row we hold ``resolved`` that
    the venue lists active keeps its place (#8586)."""

    async def test_a_row_settled_on_both_sides_is_handed_to_the_loop_last(
        self, pg_session
    ):
        await _seed_existing(pg_session)
        # _NEVER (no stamp) would go first on poll age. It is settled on both
        # sides, so rewriting it changes nothing.
        await pg_session.execute(
            text(
                "UPDATE futures_markets SET status = 'resolved' "
                "WHERE source = 'kalshi' AND external_id = :t"
            ),
            {"t": _NEVER},
        )
        await pg_session.commit()
        events = [
            _ot_event(_RECENT, _TITLES[_RECENT]),
            _ot_event(_STALE, _TITLES[_STALE]),
            _ot_event(_NEVER, _TITLES[_NEVER], status="finalized"),
            _ot_event(_NEW, _TITLES[_NEW]),
        ]
        stats, order = await _run_poll(
            pg_session, events, record="_settled_rows_last"
        )
        assert stats["errors"] == [], stats["errors"]
        assert order == [_NEW, _STALE, _RECENT, _NEVER], (
            f"loop order {order}. A row resolved in our table whose venue "
            "markets are all finalized must go behind the open rows. On poll "
            "age alone it goes first and eats the beat."
        )

    async def test_a_resolved_row_the_venue_lists_active_keeps_its_place(
        self, pg_session
    ):
        """Control (#8586): the venue reopened it, so this rewrite is what turns
        it back to ``open``. It must not be pushed behind the open tail."""
        await _seed_existing(pg_session)
        await pg_session.execute(
            text(
                "UPDATE futures_markets SET status = 'resolved' "
                "WHERE source = 'kalshi' AND external_id = :t"
            ),
            {"t": _NEVER},
        )
        await pg_session.commit()
        stats, order = await _run_poll(
            pg_session,
            _events(_RECENT, _STALE, _NEVER, _NEW),
            record="_settled_rows_last",
        )
        assert stats["errors"] == [], stats["errors"]
        assert order == [_NEW, _NEVER, _STALE, _RECENT], order
        status = (
            await pg_session.execute(
                text(
                    "SELECT status FROM futures_markets "
                    "WHERE source = 'kalshi' AND external_id = :t"
                ),
                {"t": _NEVER},
            )
        ).scalar_one()
        assert status == "open", (
            f"{_NEVER} reads {status!r}: the venue lists it active, so the "
            "rewrite must reopen it"
        )
