"""#13673 Part B — multi-row batching for FuturesOddsSnapshot inserts.

Verifies that:
1. ``futures_price_refresh._write_prices`` inserts non-poll snapshot rows in
   bounded multi-row batches of ``SNAPSHOT_INSERT_BATCH_SIZE`` (100) rather than
   one INSERT per outcome, while preserving single-row params for 1 row and
   skipping when nothing was written.
2. ``venue_poll_30s.write_market`` batches moved + trailing due chart points into
   bounded multi-row INSERTs before commit, preserving stats and deferred sets,
   and skips the snapshot insert when no point is due.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql

from app.tasks import futures_price_refresh as fpr
from app.tasks import venue_poll_30s as vpoll


class _Result:
    def __init__(self, rows=(), *, rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows)


class _RecordingSession:
    """AsyncSession test double that records compiled SQL & multi-row VALUES."""

    def __init__(self, outcome_rows=()):
        self.outcome_rows = list(outcome_rows)
        self.snapshot_inserts = []
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def execute(self, statement, params=None):
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled).lstrip().upper()
        if sql.startswith("INSERT INTO FUTURES_ODDS_SNAPSHOTS"):
            self.snapshot_inserts.append((statement, sql, compiled.params))
            multi = getattr(statement, "_multi_values", None) or ()
            return _Result(rowcount=sum(len(c) for c in multi) or 1)
        if sql.startswith("SELECT FO.ID, FO.CURRENT_PROBABILITY"):
            return _Result(self.outcome_rows)
        if sql.startswith("SELECT FO.ID, S.CAPTURED_AT"):
            return _Result([])
        if sql.startswith("SELECT ID, EXTERNAL_ID FROM FUTURES_OUTCOMES"):
            return _Result(self.outcome_rows)
        return _Result(rowcount=1)


def _snapshot_rows(stmt) -> list[dict]:
    """Normalize SQLAlchemy ``_multi_values`` row dicts to string column keys."""
    multi = getattr(stmt, "_multi_values", None) or ()
    out: list[dict] = []
    for chunk in multi:
        for row in chunk:
            out.append({getattr(k, "key", str(k)): v for k, v in row.items()})
    return out


def _snapshot_batch_sizes(session: _RecordingSession) -> list[int]:
    """Extract row count per executed FuturesOddsSnapshot INSERT statement."""
    sizes: list[int] = []
    for stmt, _sql, params in session.snapshot_inserts:
        rows = _snapshot_rows(stmt)
        if rows:
            sizes.append(len(rows))
        else:
            sizes.append(1 if "outcome_id" in params else len(params))
    return sizes


async def test_write_prices_batches_snapshots_in_chunks_of_100():
    """105 priced outcomes -> 2 snapshot INSERTs (100 + 5), not 105."""
    n = 105
    outcome_rows = [(i + 1, f"TKR-{i}") for i in range(n)]
    priced = [
        {
            "external_id": f"TKR-{i}",
            "probability": 0.45,
            "yes_bid": 0.44,
            "yes_ask": 0.46,
            "last_price": 0.45,
        }
        for i in range(n)
    ]
    session = _RecordingSession(outcome_rows=outcome_rows)
    stats: dict = {}

    written = await fpr._write_prices(session, 9001, "kalshi", priced, stats)

    assert written == n
    assert _snapshot_batch_sizes(session) == [100, 5]
    batch0 = _snapshot_rows(session.snapshot_inserts[0][0])
    batch1 = _snapshot_rows(session.snapshot_inserts[1][0])
    assert batch0[0]["outcome_id"] == 1
    assert batch0[-1]["outcome_id"] == 100
    assert batch1[0]["outcome_id"] == 101
    assert batch1[-1]["outcome_id"] == 105
    assert all(r["american_odds"] is not None and r["captured_at"] is not None for r in batch0 + batch1)


async def test_write_prices_single_row_preserves_scalar_params():
    session = _RecordingSession(outcome_rows=[(7, "TKR-0")])
    stats: dict = {}
    priced = [
        {
            "external_id": "TKR-0",
            "probability": 0.45,
            "yes_bid": 0.44,
            "yes_ask": 0.46,
            "last_price": 0.45,
        }
    ]

    written = await fpr._write_prices(session, 9001, "kalshi", priced, stats)

    assert written == 1
    assert _snapshot_batch_sizes(session) == [1]
    assert session.snapshot_inserts[0][2]["probability"] == 0.45
    assert session.snapshot_inserts[0][2]["outcome_id"] == 7


async def test_write_prices_skips_snapshot_insert_when_nothing_written():
    session = _RecordingSession(outcome_rows=[(1, "TKR-0")])
    stats: dict = {}
    priced = [{"external_id": "TKR-0", "probability": 1.2}]

    written = await fpr._write_prices(session, 9001, "kalshi", priced, stats)

    assert written == 0
    assert session.snapshot_inserts == []
    assert stats["legs_declined_out_of_range"] == 1


async def test_venue_poll_30s_write_market_batches_moved_and_trailing_points(monkeypatch):
    """Moved + trailing due points share one batched snapshot INSERT per market."""
    now = datetime.now(timezone.utc)
    fetched_at = now - timedelta(seconds=2)

    async def fake_write_prices(session, market_id, venue, priced, stats, poll=None):
        poll.moved.extend(
            [
                (11, {"probability": 0.62, "yes_bid": 0.60, "yes_ask": 0.64, "last_price": 0.62}),
                (12, {"probability": 0.38, "yes_bid": 0.36, "yes_ask": 0.40, "last_price": 0.38}),
            ]
        )
        poll.unchanged[13] = (0.50, 0.48, 0.52)
        return 2

    async def fake_last_points(sess, ids):
        old_ts = now - timedelta(minutes=30)
        return {11: (old_ts, 0.40), 12: (old_ts, 0.60), 13: (old_ts, 0.40)}

    monkeypatch.setattr(fpr, "_write_prices", fake_write_prices)
    monkeypatch.setattr(vpoll, "load_last_points", fake_last_points)

    session = _RecordingSession()
    poll = vpoll.PollWrite(
        now=now,
        fetched_at=fetched_at,
        stored={
            11: (0.40, 0.38, 0.42),
            12: (0.60, 0.58, 0.62),
            13: (0.50, 0.48, 0.52),
        },
        allowed=frozenset({11, 12, 13}),
    )
    deferred = vpoll.DeferredPoints(members=frozenset({13}))
    stats: dict = {}

    await vpoll.write_market(
        session,
        venue="polymarket",
        market_id=42,
        priced=[{"external_id": "x"}],
        poll=poll,
        deferred=deferred,
        stats=stats,
    )

    assert stats["history_points"] == 2
    assert stats["history_trailing_points"] == 1
    assert _snapshot_batch_sizes(session) == [3]
    rows = _snapshot_rows(session.snapshot_inserts[0][0])
    assert [r["outcome_id"] for r in rows] == [11, 12, 13]
    assert all(r["american_odds"] is not None and r["captured_at"] is not None for r in rows)
    assert session.commits == 1


async def test_venue_poll_30s_write_market_skips_insert_when_no_points_due(monkeypatch):
    now = datetime.now(timezone.utc)
    fetched_at = now - timedelta(seconds=2)

    async def fake_write_prices(session, market_id, venue, priced, stats, poll=None):
        poll.moved.append((11, {"probability": 0.41, "yes_bid": 0.40, "yes_ask": 0.42}))
        return 1

    async def fake_last_points(sess, ids):
        # Within min_interval_s -> deferred (no snapshot due).
        return {11: (now - timedelta(seconds=10), 0.40)}

    monkeypatch.setattr(fpr, "_write_prices", fake_write_prices)
    monkeypatch.setattr(vpoll, "load_last_points", fake_last_points)

    session = _RecordingSession()
    poll = vpoll.PollWrite(
        now=now,
        fetched_at=fetched_at,
        stored={11: (0.40, 0.39, 0.41)},
        allowed=frozenset({11}),
    )
    deferred = vpoll.DeferredPoints()
    stats: dict = {}

    await vpoll.write_market(
        session,
        venue="polymarket",
        market_id=42,
        priced=[{"external_id": "x"}],
        poll=poll,
        deferred=deferred,
        stats=stats,
    )

    assert stats["history_deferred"] == 1
    assert session.snapshot_inserts == []
    assert session.commits == 1
    assert 11 in deferred.add
