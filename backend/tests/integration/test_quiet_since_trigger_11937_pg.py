"""#11937: the database keeps `futures_markets.quiet_since` on every write of
`volume_24h`, on real Postgres (the rule that a market nobody trades is not
featured rests on it).

The trigger is the production one (`app/utils/not_trading.py`), installed on a
TEMP table of the same name and shape, so nothing outside this session is
touched. Skipped without `SEARCH_TEST_DATABASE_URL`; the database-integration
job names this file and fails on any skip.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.utils import not_trading as nt

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #11937 trigger gate")


@pytest.fixture
async def conn():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as c:
        await c.execute(text(
            "CREATE TEMP TABLE futures_markets (id int PRIMARY KEY, name text NOT NULL,"
            " category text NOT NULL, source text NOT NULL, external_id text NOT NULL,"
            " status text NOT NULL, mutually_exclusive boolean NOT NULL,"
            " volume_24h bigint, quiet_since timestamptz)"
        ))
        await c.execute(text(nt.CREATE_FUNCTION_SQL))
        await c.execute(text(nt.CREATE_TRIGGER_SQL))
        yield c
        await c.rollback()
    await engine.dispose()


async def _seed(conn, mid, vol, quiet_days_ago=None):
    await conn.execute(
        text(
            "INSERT INTO futures_markets (id, name, category, source, external_id, status,"
            " mutually_exclusive, volume_24h, quiet_since) VALUES (:i, 'M', 'politics',"
            " 'kalshi', :x, 'open', true, :v,"
            " CASE WHEN CAST(:d AS int) IS NULL THEN NULL ELSE now() - make_interval(days => CAST(:d AS int)) END)"
        ),
        {"i": mid, "x": f"ext-{mid}", "v": vol, "d": quiet_days_ago},
    )


async def _q(conn, mid):
    return (await conn.execute(text("SELECT quiet_since FROM futures_markets WHERE id = :i"), {"i": mid})).scalar()


async def _set(conn, mid, vol):
    await conn.execute(text("UPDATE futures_markets SET volume_24h = :v WHERE id = :i"), {"v": vol, "i": mid})


async def test_an_insert_with_zero_volume_starts_a_quiet_spell_and_one_with_volume_does_not(conn):
    await _seed(conn, 1, 0)
    await _seed(conn, 2, 40)
    await _seed(conn, 3, None)
    assert await _q(conn, 1) is not None
    assert await _q(conn, 2) is None
    assert await _q(conn, 3) is None


async def test_a_later_zero_keeps_the_first_stamp(conn):
    await _seed(conn, 1, 0, quiet_days_ago=9)
    first = await _q(conn, 1)
    await _set(conn, 1, 0)
    assert await _q(conn, 1) == first


async def test_any_volume_clears_it(conn):
    await _seed(conn, 1, 0)
    await _set(conn, 1, 7)
    assert await _q(conn, 1) is None


async def test_a_null_reading_leaves_it_alone(conn):
    await _seed(conn, 1, 0, quiet_days_ago=9)
    first = await _q(conn, 1)
    await _set(conn, 1, None)
    assert await _q(conn, 1) == first


async def test_an_update_that_does_not_touch_volume_leaves_it_alone(conn):
    await _seed(conn, 1, 0, quiet_days_ago=9)
    first = await _q(conn, 1)
    await conn.execute(text("UPDATE futures_markets SET id = id WHERE id = 1"))
    assert await _q(conn, 1) == first
