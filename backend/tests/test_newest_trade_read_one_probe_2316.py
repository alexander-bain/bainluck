"""#2316 — the newest-trade read asks one index probe per leg, not every snapshot.

`_newest_kalshi_trades` and `_newest_venue_trade_rows` (routes/futures.py) find
each leg's newest capture on one bookmaker and join its row(s) back. They used
to find it with `max(captured_at) ... GROUP BY outcome_id`, which on Postgres
(no skip scan) reads every snapshot a leg has ever had: ~2.8 s mean, 10-21 s
max, ~285k buffers per call on production, inside the event page's Bigger
Picture build, the playoff grid, search and the feed. The rewrite asks an
ungrouped, correlated `max()` per leg, which Postgres answers with a one-row
backward probe of `(outcome_id, bookmaker, captured_at DESC)`.

Two halves:

* BEHAVIOUR, on a real (SQLite) database through the real readers: the answer
  is exactly the old one, including the edges the old aggregate defined — ties
  at the newest capture, NULL `last_price`, another bookmaker's newer
  capture, a leg with no capture, a repeated id. (A NULL `captured_at` cannot
  be stored here — the model declares it NOT NULL — and `max()` ignores one in
  both forms.)
* SHAPE, on the compiled Postgres statement: the per-leg read must stay
  ungrouped and correlated to the outcome row. The behaviour half cannot see a
  revert to the GROUP BY form, because that form gives the same answer — it is
  only slow — so this half is what keeps the speed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
)
from app.routes import futures as F  # noqa: E402

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class _AsyncDB:
    """The readers only `await db.execute(stmt)`; the REAL statement runs."""

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, stmt):
        return self._session.execute(stmt)


def _session() -> Session:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )
    s = Session(eng)
    s.add(FuturesMarket(id=1, source="kalshi", external_id="KXTEST", name="Q?"))
    for oid in (10, 11, 12, 13, 14):
        s.add(FuturesOutcome(id=oid, market_id=1, external_id=f"o{oid}", name=f"leg {oid}"))
    snaps = [
        # 10: three Kalshi captures; two share the newest stamp. A NEWER
        # Polymarket capture must not count.
        (10, "kalshi", T0, 0.30),
        (10, "kalshi", T0 + timedelta(hours=3), 0.40),
        (10, "kalshi", T0 + timedelta(hours=3), 0.55),
        (10, "polymarket", T0 + timedelta(hours=4), 0.90),
        # 11: a capture on another bookmaker only — no Kalshi answer.
        (11, "polymarket", T0, 0.50),
        # 12: newest capture carries no price — present, with None.
        (12, "kalshi", T0, 0.20),
        (12, "kalshi", T0 + timedelta(hours=1), None),
        # 13: no snapshot at all (nothing inserted).
        # 14: Polymarket only — two rows at the newest stamp, one older.
        (14, "polymarket", T0, 0.10),
        (14, "polymarket", T0 + timedelta(hours=2), 0.40),
        (14, "polymarket", T0 + timedelta(hours=2), 0.60),
    ]
    for i, (oid, bookmaker, at, price) in enumerate(snaps, start=1):
        s.add(
            FuturesOddsSnapshot(
                id=i,
                outcome_id=oid,
                bookmaker=bookmaker,
                captured_at=at,
                last_price=price,
                probability=0.5,
            )
        )
    s.commit()
    return s


def _as_float(value):
    return None if value is None else float(value)


def test_kalshi_read_returns_each_legs_newest_capture_exactly_as_before():
    db = _AsyncDB(_session())
    got = asyncio.run(F._newest_kalshi_trades(db, [10, 11, 12, 13, 14, 10]))
    assert {k: _as_float(v) for k, v in got.items()} == {
        # the HIGHEST price among the rows tied at the newest stamp (fail-open)
        10: 0.55,
        # newest capture without a price is still the newest capture
        12: None,
    }, got


def test_venue_read_returns_every_row_at_the_newest_capture():
    db = _AsyncDB(_session())
    rows = asyncio.run(F._newest_venue_trade_rows(db, "polymarket", [10, 13, 14]))
    assert sorted((oid, _as_float(p)) for oid, p in rows) == [
        # 10's Polymarket newest capture is its only one
        (10, 0.90),
        (14, 0.40),
        (14, 0.60),
    ], rows


def test_empty_id_list_still_costs_no_query():
    class _Refuses:
        async def execute(self, _stmt):  # pragma: no cover - must not run
            raise AssertionError("an empty id list must not query")

    assert asyncio.run(F._newest_kalshi_trades(_Refuses(), [])) == {}
    assert asyncio.run(F._newest_venue_trade_rows(_Refuses(), "polymarket", [])) == []


def _compiled(stmt) -> str:
    return " ".join(
        str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).split()
    )


def test_per_leg_newest_capture_is_an_ungrouped_correlated_max():
    sql = _compiled(F._newest_capture_per_outcome([10, 11], "kalshi").element)
    # Driven from the outcome row by primary key …
    assert sql.startswith("SELECT futures_outcomes.id AS outcome_id, (SELECT max("), sql
    assert "FROM futures_outcomes WHERE futures_outcomes.id IN (10, 11)" in sql, sql
    # … asking an aliased snapshot table, correlated to THAT row …
    assert "FROM futures_odds_snapshots AS futures_odds_snapshots_1" in sql, sql
    assert "futures_odds_snapshots_1.outcome_id = futures_outcomes.id" in sql, sql
    assert "futures_odds_snapshots_1.bookmaker = 'kalshi'" in sql, sql
    # … and never grouping: a GROUP BY here is the every-snapshot scan again.
    assert "GROUP BY" not in sql, sql


def test_both_readers_join_the_per_leg_read_not_a_grouped_scan():
    captured = []

    class _Capture:
        async def execute(self, stmt):
            captured.append(stmt)

            class _R:
                def all(self):
                    return []

            return _R()

    asyncio.run(F._newest_kalshi_trades(_Capture(), [10, 11]))
    asyncio.run(F._newest_venue_trade_rows(_Capture(), "polymarket", [10, 11]))
    kalshi_sql, venue_sql = (_compiled(s) for s in captured)
    for sql in (kalshi_sql, venue_sql):
        assert "JOIN (SELECT futures_outcomes.id AS outcome_id, (SELECT max(" in sql, sql
        assert "max(futures_odds_snapshots.captured_at)" not in sql, sql
    # The Kalshi reader keeps exactly ONE grouping: the outer tie-break.
    assert kalshi_sql.count("GROUP BY") == 1, kalshi_sql
    assert kalshi_sql.endswith("GROUP BY futures_odds_snapshots.outcome_id"), kalshi_sql
    assert "GROUP BY" not in venue_sql, venue_sql
