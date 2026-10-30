"""#10090 — the history backfills never hold a transaction across a network call.

`_backfill_polymarket_price_history` committed once, after its whole run, and
`_backfill_kalshi_price_history` every 50 outcomes. Every opening UPDATE kept
its `futures_outcomes` row locked across the run's HTTP calls — minutes — and
in `open_sparse` those are the rows the live socket writes (15:16-15:21Z on
2026-10-30: whole 500-price batches refused on `LockNotAvailable`).

These tests start the real functions (fake DB session + fake venue client, no
network). The fake services record every call made while the session holds an
open transaction; the fake session can fail one outcome's write.
"""

from __future__ import annotations

import asyncio
from collections import namedtuple
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import app.services.kalshi_api as kalshi_api
import app.services.polymarket_api as pm_api
import app.tasks.kalshi as kalshi_tasks
import app.tasks.polymarket as pm

BOUNDARY = datetime(2026, 1, 1, tzinfo=timezone.utc)
QUOTE_AT = BOUNDARY - timedelta(days=1)
PmRow = namedtuple(
    "PmRow", "id external_id market_external_id resolution_date settled_at"
)
KalshiRow = namedtuple("KalshiRow", "outcome_id ticker event_ticker")


class _Result:
    def __init__(self, rows=None, rowcount=None):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _TxnSession:
    """Tracks the open transaction and which writes actually committed."""

    def __init__(self, rows, fail_update_for=()):
        self.rows = rows
        self.fail_update_for = set(fail_update_for)
        self.in_txn = False
        self.pending: list[tuple[str, object]] = []
        self.committed: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        self.in_txn = True
        sql = str(stmt)
        p = dict(params or {})
        if "UPDATE futures_outcomes" in sql:
            oid = p.get("oid", p.get("id"))
            if oid in self.fail_update_for:
                raise RuntimeError(f"simulated write failure on {oid}")
            self.pending.append(("opening", oid))
            return _Result(rowcount=1)
        if "SELECT fo.id" in sql:
            return _Result(rows=self.rows)
        # The snapshot insert: read its outcome id off the bound values.
        oid = stmt.compile().params.get("outcome_id_m0")
        self.pending.append(("snapshots", oid))
        return _Result()

    async def commit(self):
        self.committed.extend(self.pending)
        self.pending.clear()
        self.in_txn = False
        self.commits += 1

    async def rollback(self):
        self.pending.clear()
        self.in_txn = False
        self.rollbacks += 1


def _patch_common(monkeypatch, module, session):
    @asynccontextmanager
    async def fake_session():
        yield session

    async def no_sleep(_):
        return None

    monkeypatch.setattr(module, "get_task_session", fake_session)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)


# ── Polymarket ───────────────────────────────────────────────────────────────


class _PmService:
    def __init__(self, session):
        self.session = session
        self.calls_in_txn: list[str] = []

    def _check(self, what):
        if self.session.in_txn:
            self.calls_in_txn.append(what)

    async def get_event_by_id(self, event_id):
        self._check(f"event:{event_id}")
        return {
            "markets": [
                {"conditionId": f"0x{event_id}", "clobTokenIds": '["tok_yes","tok_no"]'}
            ]
        }

    async def get_prices_history(self, token_id, interval, fidelity):
        self._check(f"history:{token_id}")
        return [{"t": int(QUOTE_AT.timestamp()), "p": 0.4}]

    async def close(self):
        pass


def _pm_rows(n):
    return [PmRow(i, f"0x{i}_yes", str(i), BOUNDARY, None) for i in range(1, n + 1)]


def _run_pm(monkeypatch, rows, mode="open_sparse", fail_update_for=()):
    session = _TxnSession(rows, fail_update_for)
    service = _PmService(session)
    _patch_common(monkeypatch, pm, session)
    monkeypatch.setattr(pm_api, "PolymarketAPIService", lambda: service)
    stats = asyncio.run(pm._backfill_polymarket_price_history(limit=10, mode=mode))
    return stats, session, service


def test_pm_no_network_call_runs_inside_an_open_transaction(monkeypatch):
    for mode in ("open_sparse", "resolved_zero"):
        stats, session, service = _run_pm(monkeypatch, _pm_rows(3), mode=mode)
        assert service.calls_in_txn == [], mode
        assert stats["opening_written"] == 3, mode
        assert session.in_txn is False, mode


def test_pm_each_outcome_commits_its_own_writes(monkeypatch):
    stats, session, _ = _run_pm(monkeypatch, _pm_rows(3))
    # The read, then one commit per outcome.
    assert session.commits == 1 + 3
    assert session.committed == [
        ("snapshots", 1), ("opening", 1),
        ("snapshots", 2), ("opening", 2),
        ("snapshots", 3), ("opening", 3),
    ]


def test_pm_one_bad_write_leaves_its_siblings_committed(monkeypatch):
    stats, session, service = _run_pm(monkeypatch, _pm_rows(3), fail_update_for={2})
    assert service.calls_in_txn == []
    assert session.rollbacks == 1
    assert session.committed == [
        ("snapshots", 1), ("opening", 1),
        ("snapshots", 3), ("opening", 3),
    ]
    assert stats["outcomes_processed"] == 2
    assert stats["opening_written"] == 2
    # Stats count only what committed: outcome 2's snapshots rolled back.
    assert stats["snapshots_created"] == 2
    assert [e for e in stats["errors"] if e.startswith("2: write:")]
    assert not any(e.startswith("task_error") for e in stats["errors"])


# ── Kalshi ───────────────────────────────────────────────────────────────────


class _KalshiService:
    def __init__(self, session):
        self.session = session
        self.calls_in_txn: list[str] = []

    async def get_market_candlesticks(self, ticker, period_interval):
        if self.session.in_txn:
            self.calls_in_txn.append(ticker)
        return [{"t": int(QUOTE_AT.timestamp()), "yes_price": 0.4}]

    async def close(self):
        pass


def _kalshi_rows(n):
    return [KalshiRow(i, f"KX-{i}", "KXEVT") for i in range(1, n + 1)]


def _run_kalshi(monkeypatch, rows, mode="open_sparse", fail_update_for=()):
    session = _TxnSession(rows, fail_update_for)
    service = _KalshiService(session)
    _patch_common(monkeypatch, kalshi_tasks, session)
    monkeypatch.setattr(kalshi_api, "KalshiAPIService", lambda: service)
    stats = asyncio.run(
        kalshi_tasks._backfill_kalshi_price_history(limit=10, mode=mode)
    )
    return stats, session, service


def test_kalshi_no_network_call_runs_inside_an_open_transaction(monkeypatch):
    for mode in ("open_sparse", "resolved_zero"):
        stats, session, service = _run_kalshi(monkeypatch, _kalshi_rows(3), mode=mode)
        assert service.calls_in_txn == [], mode
        assert stats["outcomes_processed"] == 3, mode
        assert session.in_txn is False, mode


def test_kalshi_each_outcome_commits_its_own_writes(monkeypatch):
    stats, session, _ = _run_kalshi(monkeypatch, _kalshi_rows(3))
    assert session.commits == 1 + 3
    assert session.committed == [
        ("snapshots", 1), ("opening", 1),
        ("snapshots", 2), ("opening", 2),
        ("snapshots", 3), ("opening", 3),
    ]


def test_kalshi_one_bad_write_leaves_its_siblings_committed(monkeypatch):
    stats, session, service = _run_kalshi(
        monkeypatch, _kalshi_rows(3), fail_update_for={2}
    )
    assert service.calls_in_txn == []
    assert session.rollbacks == 1
    assert session.committed == [
        ("snapshots", 1), ("opening", 1),
        ("snapshots", 3), ("opening", 3),
    ]
    assert stats["outcomes_processed"] == 2
    assert stats["snapshots_created"] == 2
    assert [e for e in stats["errors"] if e.startswith("KX-2: write:")]
    assert not any(e.startswith("task_error") for e in stats["errors"])


# ── Kalshi pregame_gap (lane1 R1 on b7f13bb3) ────────────────────────────────
# The third mode of the same task. Its candidates are games already under way,
# so its opening UPDATEs lock exactly the rows the live socket writes.

PregameRow = namedtuple(
    "PregameRow",
    "outcome_id ticker commence_time existing_opening existing_opening_at",
)


class _PregameService:
    def __init__(self, session):
        self.session = session
        self.calls_in_txn: list[str] = []

    async def get_market_candlesticks(
        self, ticker, period_interval, start_ts=None, end_ts=None
    ):
        if self.session.in_txn:
            self.calls_in_txn.append(ticker)
        return [{"t": end_ts - 3600, "yes_price": 0.4}]

    async def close(self):
        pass


def _pregame_rows(n):
    started = datetime.now(timezone.utc) - timedelta(minutes=30)
    return [PregameRow(i, f"KX-{i}", started, None, None) for i in range(1, n + 1)]


def _run_pregame(monkeypatch, rows, fail_update_for=()):
    import app.tasks.redis_state as redis_state

    session = _TxnSession(rows, fail_update_for)
    service = _PregameService(session)
    _patch_common(monkeypatch, kalshi_tasks, session)
    monkeypatch.setattr(kalshi_api, "KalshiAPIService", lambda: service)

    def no_redis():
        raise RuntimeError("no redis in this test")

    monkeypatch.setattr(redis_state, "get_redis_client", no_redis)
    stats = asyncio.run(
        kalshi_tasks._backfill_kalshi_price_history(limit=10, mode="pregame_gap")
    )
    return stats, session, service


def test_pregame_gap_no_network_call_runs_inside_an_open_transaction(monkeypatch):
    stats, session, service = _run_pregame(monkeypatch, _pregame_rows(3))
    assert service.calls_in_txn == []
    assert stats["openings_written"] == 3
    assert session.in_txn is False


def test_pregame_gap_each_outcome_commits_its_own_update(monkeypatch):
    stats, session, _ = _run_pregame(monkeypatch, _pregame_rows(3))
    # The read, then one commit per outcome.
    assert session.commits == 1 + 3
    assert session.committed == [("opening", 1), ("opening", 2), ("opening", 3)]


def test_pregame_gap_one_bad_write_leaves_its_siblings_committed(monkeypatch):
    stats, session, service = _run_pregame(
        monkeypatch, _pregame_rows(3), fail_update_for={2}
    )
    assert service.calls_in_txn == []
    assert session.rollbacks == 1
    assert session.committed == [("opening", 1), ("opening", 3)]
    # Stats count only what committed.
    assert stats["openings_written"] == 2
    assert [e for e in stats["errors"] if e.startswith("KX-2: write:")]
    assert not any(e.startswith("task_error") for e in stats["errors"])
