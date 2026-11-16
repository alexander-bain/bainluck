"""Ruling 198-B on a real Postgres: the refused-book stamp's whole lifecycle.

The unit file proves the refresh ISSUES the statements. This one proves what they
DO: one refused read stamps, a refused read from a LATER run confirms, the same
run cannot confirm its own stamp, an accepted price clears both and nothing else,
only open Polymarket markets are stamped, and the hourly poll's wholesale
metadata replace carries the stamps rather than erasing them.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.utils.futures_liveness import (
    BOOK_REFUSED_FIRST_KEY,
    BOOK_REFUSED_KEY,
    CLEAR_BOOK_REFUSED_SQL,
    STAMP_BOOK_REFUSED_SQL,
    VENUE_SETTLED_KEY,
    preserve_venue_settled,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres 198-B stamp gate",
    ),
]


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _market(session, *, source="polymarket", status="open", metadata=None):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source=source,
        external_id=f"{source}-{status}-{id(metadata)}",
        name="Will it happen?",
        category="futures",
        market_tier=2,
        status=status,
        market_metadata=metadata,
    )
    session.add(m)
    await session.flush()
    await session.commit()
    return m.id


def _utc_naive(delta_minutes=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)).replace(tzinfo=None)


async def _stamp(session, mid, run_started):
    rows = (
        await session.execute(
            text(STAMP_BOOK_REFUSED_SQL), {"mid": mid, "run_started": run_started}
        )
    ).fetchall()
    await session.commit()
    return rows


async def _meta(session, mid):
    return (
        await session.execute(
            text("SELECT market_metadata FROM futures_markets WHERE id = :m"), {"m": mid}
        )
    ).scalar()


async def test_first_refused_read_stamps_and_is_not_yet_confirmed(db):
    mid = await _market(db, metadata={"polymarket_event_id": "9"})
    rows = await _stamp(db, mid, _utc_naive(-1))
    assert rows == [(False,)]
    meta = await _meta(db, mid)
    assert BOOK_REFUSED_FIRST_KEY in meta and BOOK_REFUSED_KEY not in meta
    assert meta["polymarket_event_id"] == "9"


async def test_a_market_with_no_metadata_at_all_still_stamps(db):
    mid = await _market(db, metadata=None)
    assert await _stamp(db, mid, _utc_naive(-1)) == [(False,)]
    assert BOOK_REFUSED_FIRST_KEY in await _meta(db, mid)


async def test_the_same_run_cannot_confirm_its_own_stamp(db):
    mid = await _market(db)
    started = _utc_naive(-1)
    await _stamp(db, mid, started)
    assert await _stamp(db, mid, started) == []
    assert BOOK_REFUSED_KEY not in await _meta(db, mid)


async def test_a_later_runs_refused_read_confirms(db):
    mid = await _market(db)
    await _stamp(db, mid, _utc_naive(-1))
    assert await _stamp(db, mid, _utc_naive(+1)) == [(True,)]
    meta = await _meta(db, mid)
    assert BOOK_REFUSED_KEY in meta and BOOK_REFUSED_FIRST_KEY in meta
    # confirmed is terminal until a price clears it: further reads write nothing
    assert await _stamp(db, mid, _utc_naive(+2)) == []


async def test_an_accepted_price_clears_both_and_keeps_everything_else(db):
    mid = await _market(db, metadata={VENUE_SETTLED_KEY: "2026-11-15T00:00:00", "x": 1})
    await _stamp(db, mid, _utc_naive(-1))
    await _stamp(db, mid, _utc_naive(+1))
    result = await db.execute(text(CLEAR_BOOK_REFUSED_SQL), {"mid": mid})
    await db.commit()
    assert result.rowcount == 1
    meta = await _meta(db, mid)
    assert BOOK_REFUSED_KEY not in meta and BOOK_REFUSED_FIRST_KEY not in meta
    assert meta[VENUE_SETTLED_KEY] == "2026-11-15T00:00:00" and meta["x"] == 1


async def test_clearing_an_unstamped_market_rewrites_nothing(db):
    mid = await _market(db, metadata={"x": 1})
    result = await db.execute(text(CLEAR_BOOK_REFUSED_SQL), {"mid": mid})
    await db.commit()
    assert result.rowcount == 0


@pytest.mark.parametrize("source,status", [("kalshi", "open"), ("polymarket", "resolved")])
async def test_only_open_polymarket_markets_are_stamped(db, source, status):
    mid = await _market(db, source=source, status=status)
    assert await _stamp(db, mid, _utc_naive(-1)) == []
    assert not (await _meta(db, mid) or {}).get(BOOK_REFUSED_FIRST_KEY)


async def test_the_polls_metadata_replace_carries_both_stamps(db):
    from sqlalchemy import update

    from app.models.models import FuturesMarket

    mid = await _market(db)
    await _stamp(db, mid, _utc_naive(-1))
    await _stamp(db, mid, _utc_naive(+1))
    # what the hourly poll does: SET market_metadata to a freshly built dict
    await db.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == mid)
        .values(
            market_metadata=preserve_venue_settled(
                {"polymarket_event_id": "new"}, FuturesMarket.market_metadata
            )
        )
    )
    await db.commit()
    meta = await _meta(db, mid)
    assert meta["polymarket_event_id"] == "new"
    assert BOOK_REFUSED_KEY in meta and BOOK_REFUSED_FIRST_KEY in meta
