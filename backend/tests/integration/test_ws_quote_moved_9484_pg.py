"""#9484 — the Kalshi socket signals a quote that moved, on real Postgres.

WHY POSTGRES. The book arm of `quote_moved_column` reads the row as it was
BEFORE the UPDATE through a scalar subquery in RETURNING. That is statement-
snapshot semantics: Postgres evaluates the subquery against the pre-statement
snapshot, SQLite evaluates it after the write and sees the new row. So on the
SQLite rig (`tests/test_ws_market_change_hooks_9484.py`) a book-only move reads
as "nothing changed" and the arm can neither pass nor fail there. The price arm
also rounds here as production does (NUMERIC(7, 6)); SQLite compares raw floats.

Every case drives the REAL `_run_kalshi_ws_consumer` through that file's rig,
handed a Postgres engine instead of a SQLite one: its UPDATE ... RETURNING, the
#5411 guard and the after-commit publish all run on this server.

    the_book_that_widened ........ THE ARM THIS FILE EXISTS FOR. Same midpoint
                                   (0.42), wider book (0.41/0.43 → 0.40/0.44):
                                   the serve path reads the book (#6676), so it
                                   is a served change → one frame.
    the_tick_that_changed_nothing  Same price, same book → written, no frame.
    the_rounding_that_hides ...... The stored 0.420000 against a tick whose
                                   midpoint is 0.42000000000000004, book equal
                                   at NUMERIC(5, 4) → no frame (the precision
                                   trap, answered by the columns' own types).
    the_price_that_moved ......... CONTROL: 0.30 → 0.42 → one frame.

Opt-in on `SEARCH_TEST_DATABASE_URL` (CI job `search-recall`, whose step fails
on a skip).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from tests.test_ws_market_change_hooks_9484 import (
    MARKET_EXT,
    MARKET_ID,
    OUTCOME_ID,
    TICK,
    _as_utc,
    _drive_kalshi,
    _stored,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres quote-moved "
            "gate (CI job: search-recall)"
        ),
    ),
]

MOVED_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _tables_for_outcomes():
    """`futures_outcomes` and everything its foreign keys reach — no more, so the
    one PG15-only index elsewhere in the schema never has to compile."""
    from app.models.models import FuturesOutcome

    seen = []

    def walk(table):
        if table in seen:
            return
        seen.append(table)
        for fk in table.foreign_keys:
            walk(fk.column.table)

    walk(FuturesOutcome.__table__)
    return seen


@pytest.fixture
def pg():
    from sqlalchemy import create_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_engine(DB_URL.replace("+asyncpg", "+psycopg2"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine, tables=_tables_for_outcomes())
    try:
        yield engine
    finally:
        # CI runs the real-Postgres files one after another on ONE database.
        # The seed writes explicit ids (market 7) without advancing the
        # sequences, so leaving the rows behind hands the next file's first
        # autoincrement insert a duplicate key (the #5869 step, CI run
        # 36538546164). Leave the schema as empty as the opening drop found it.
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed(engine, *, probability, book):
    from sqlalchemy import insert

    from app.models.models import FuturesMarket, FuturesOutcome

    with engine.begin() as conn:
        conn.execute(insert(FuturesMarket.__table__).values(
            id=MARKET_ID, source="kalshi", external_id=MARKET_EXT,
            name="A standalone question", category="futures", status="open",
        ))
        conn.execute(insert(FuturesOutcome.__table__).values(
            id=OUTCOME_ID, market_id=MARKET_ID, external_id="KXTEST-Y",
            name="Yes", current_probability=probability,
            current_yes_bid=book[0], current_yes_ask=book[1],
            price_changed_at=MOVED_AT,
        ))


async def test_the_book_that_widened(monkeypatch, pg):
    _seed(pg, probability=0.42, book=(0.41, 0.43))
    published, stats = await _drive_kalshi(monkeypatch, pg, [TICK])

    assert stats["errors"] == 0
    assert len(published) == 1, published
    # The price did not move — the book did, and only the book arm saw it.
    assert _as_utc(_stored(pg, "futures_outcomes", "price_changed_at", OUTCOME_ID)) == MOVED_AT
    assert float(_stored(pg, "futures_outcomes", "current_yes_bid", OUTCOME_ID)) == 0.40
    assert stats["quotes_unchanged"] == 0


async def test_the_tick_that_changed_nothing(monkeypatch, pg):
    _seed(pg, probability=0.42, book=(0.40, 0.44))
    published, stats = await _drive_kalshi(monkeypatch, pg, [TICK])

    assert stats["errors"] == 0
    assert published == []
    assert stats["quotes_unchanged"] == 1
    # Written all the same: liveness moved, the change stamp did not.
    assert _as_utc(_stored(pg, "futures_outcomes", "last_updated", OUTCOME_ID)) > MOVED_AT
    assert _as_utc(_stored(pg, "futures_outcomes", "price_changed_at", OUTCOME_ID)) == MOVED_AT


async def test_the_rounding_that_hides(monkeypatch, pg):
    # 0.40/0.44 midpoints to 0.42000000000000004 in float; stored is 0.420000.
    assert (0.40 + 0.44) / 2 != 0.42
    _seed(pg, probability=0.42, book=(0.4000, 0.4400))
    published, stats = await _drive_kalshi(monkeypatch, pg, [TICK])

    assert published == []
    assert stats["quotes_unchanged"] == 1


async def test_the_price_that_moved(monkeypatch, pg):
    _seed(pg, probability=0.30, book=(0.40, 0.44))
    published, stats = await _drive_kalshi(monkeypatch, pg, [TICK])

    assert stats["errors"] == 0
    assert len(published) == 1, published
    assert published[0][2] == pytest.approx(0.42)
    assert stats["quotes_unchanged"] == 0
