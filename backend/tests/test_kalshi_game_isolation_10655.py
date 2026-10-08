"""Execute the production flush with a later game's database write held.

Real SQL construction/production closure; controlled transaction boundary.
These tests prove commit/publication ordering, not production latency.
"""
import ast
import asyncio
import contextlib
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, or_, update
from sqlalchemy.exc import OperationalError

from app.models.models import FuturesOutcome
from app.tasks.kalshi_ws import (  # noqa: F401 — the exec'd flush reads these
    PRICE_PHASE_LOCK_TIMEOUT_MS,
    PRICE_FLUSH_SECONDS,
    _KalshiPriceOwner,
    flush_budget_spent,
    linked_first_phases,
)
from app.tasks.live_blend_refresh import event_ids_for_outcomes
from app.utils.futures_rank import rerank_market_fields_stmt
from app.utils.kalshi_price_statement import (  # noqa: F401 — read by the exec'd flush
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)
from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
from app.utils.repair_lock_budget import (  # noqa: F401 — read by the exec'd flush
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES
from tests._kalshi_price_session import bind_session, consumer_engine
from tests.pm_bulk_test_support import price_writes, statement_params


class LockNotAvailable(Exception):
    """asyncpg's shape: the SQLSTATE rides the driver error SQLAlchemy wraps."""
    sqlstate = "55P03"


def rig(*, failed=None, declined=None, pending=(), locked=(), unchanged=()):
    batch = {1: (.6, .59, .61), 2: (.4, .39, .41),
             3: (.7, .69, .71), 9: (.1, .09, .11)}
    markets, events = {1: 10, 2: 10, 3: 20, 9: 90}, {1: 100, 2: 100, 3: 200}
    trace, committed = [], []
    entered, release = asyncio.Event(), asyncio.Event()
    control = {"failed": failed, "declined": declined, "locked": set(locked),
               "unchanged": set(unchanged)}  # #10693: written, quote did not move
    # #10661: a row another writer holds. Like Postgres, a transaction that set
    # `lock_timeout` gives up with 55P03; one that did not waits for the holder.
    lock_released = asyncio.Event()
    stats = defaultdict(int)

    class Session:
        def __init__(self):
            self.rows = []
            self.lock_timeout = None

        async def execute(self, stmt, bind=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                self.lock_timeout = bind["ms"]
                trace.append(("lock_timeout", bind["ms"]))
                return SimpleNamespace(rowcount=1)
            params = statement_params(stmt, bind)  # #10689
            written = price_writes(stmt, params)  # #10689: either shape
            if not written:
                trace.append(("rank", tuple(self.rows)))
                return SimpleNamespace(rowcount=0)
            (oid, _prob), = written
            trace.append(("write", oid))
            if oid == 3:
                entered.set()
                await release.wait()
            if oid in control["locked"] and not lock_released.is_set():
                if self.lock_timeout is not None:
                    raise OperationalError("UPDATE", {}, LockNotAvailable())
                trace.append(("lock-wait", oid))
                await lock_released.wait()
            if oid == control["failed"]:
                raise RuntimeError("controlled later-game write failure")
            if oid == control["declined"]:
                return SimpleNamespace(rowcount=0, all=lambda: [])
            self.rows.append(oid)
            row = SimpleNamespace(id=oid, market_id=markets[oid], last_updated=oid,
                                  quote_moved=oid not in control["unchanged"])
            return SimpleNamespace(rowcount=1, all=lambda: [row])

    # #10693: the flush writes through the run's price pipeline, installed on
    # the engine its sessions are bound to.
    engine = consumer_engine()

    @asynccontextmanager
    async def session():
        s = bind_session(Session(), engine)
        try:
            yield s
        except BaseException:
            trace.append(("rollback", tuple(s.rows)))
            raise
        else:
            committed.extend(s.rows)
            trace.append(("commit", tuple(s.rows)))

    class Refresher:
        def pending_event_ids(self):
            return frozenset(pending)

        def adopt_pending(self, ids):
            pass

        async def publish_market_changes(self, s):
            trace.append(("publish", tuple(s.rows)))

        async def refresh(self, ids, **kwargs):
            trace.append(("refresh", tuple(sorted(ids))))

        async def refresh_pending(self, **kwargs):
            trace.append(("pending",))

    class Receipts:
        def stage(self, marks):
            trace.append(("receipt", tuple(marks)))

    ns = dict(globals(), price_buffer=batch, buffer_lock=asyncio.Lock(),
              market_id_by_outcome=markets, event_id_by_outcome=events,
              non_blend_outcome_ids=set(),
              input_marks={oid: oid for oid in batch}, tail_receipts=Receipts(),
              open_contract_outcome_ids={9}, blend_refresher=Refresher(),
              # #10090: no live set is the pre-#10090 plan, and no budget.
              live_event_ids=None, flush_budget=None,
              get_task_session=session, stats=stats,
              prices=_KalshiPriceOwner(),
              logger=logging.getLogger(__name__),
              queue_market_change=lambda *args, **kwargs: None)
    path = Path(__file__).resolve().parents[1] / 'app/tasks/kalshi_ws.py'
    tree = ast.parse(path.read_text())
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
             and n.name == 'flush_prices']
    assert len(nodes) == 1
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return SimpleNamespace(flush=ns['flush_prices'], batch=batch, trace=trace,
                           committed=committed, entered=entered, release=release,
                           control=control, stats=stats, events=events,
                           lock_released=lock_released, ns=ns)


async def test_ready_game_publishes_while_later_game_write_is_held():
    r = rig()
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(r.entered.wait(), 2)
        assert r.committed == [1, 2]
        assert ('refresh', (100,)) in r.trace
        assert r.trace.index(('commit', (1, 2))) < r.trace.index(('publish', (1, 2)))
        assert r.trace.index(('commit', (1, 2))) < r.trace.index(('refresh', (100,)))
        assert ('receipt', (1, 2)) in r.trace
        assert set(r.batch) == {3, 9}
    finally:
        r.release.set()
        await asyncio.wait_for(task, 2)
    assert r.committed == [1, 2, 3, 9]
    assert not r.batch
    assert r.stats['flushes'] == 1
    assert r.stats['price_updates'] == 4


async def test_later_game_failure_retains_only_unpaid_rows():
    r = rig(failed=3)
    r.release.set()
    assert await r.flush() is False
    assert r.committed == [1, 2]
    assert set(r.batch) == {3, 9}
    assert r.stats['requeued'] == 2
    assert ('refresh', (200,)) not in r.trace
    r.control['failed'] = None
    assert await r.flush() is True
    assert r.committed == [1, 2, 3, 9]
    assert not r.batch


async def test_cancellation_keeps_only_uncommitted_game_and_tail():
    r = rig()
    task = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert r.committed == [1, 2]
    assert set(r.batch) == {3, 9}
    r.release.set()
    assert await r.flush() is True
    assert r.committed == [1, 2, 3, 9]


async def test_newer_tick_and_settlement_refusal_survive_separation():
    r = rig(declined=2)
    task = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)
    r.batch[3] = (.8, .79, .81)
    r.release.set()
    assert await task is True
    assert r.committed == [1, 3, 9]
    assert r.batch == {3: (.8, .79, .81)}
    assert r.stats['settled_declined'] == 1
    assert ('receipt', (1,)) in r.trace
    assert ('receipt', (1, 2)) not in r.trace
    assert await r.flush() is True
    assert not r.batch


def test_components_keep_whole_markets_and_all_markets_of_one_event():
    batch = {1: 'a', 3: 'c', 9: 'z', 2: 'b', 4: 'd', 5: 'e'}
    markets = {1: 10, 2: 10, 3: 20, 4: 30, 5: 40, 9: 90}
    events = {1: 100, 4: 100, 3: 200, 5: 300}
    assert linked_first_phases(batch, markets, events) == [
        {1: 'a', 2: 'b', 4: 'd'}, {3: 'c'}, {5: 'e'}, {9: 'z'}]
    assert list(batch) == [1, 3, 9, 2, 4, 5]


def test_transitive_shared_market_keeps_events_together():
    batch = {1: 'a', 2: 'b', 3: 'c', 4: 'd', 5: 'e'}
    markets = {1: 10, 2: 20, 3: 20, 4: 30, 5: 40}
    events = {1: 100, 2: 100, 3: 200, 4: 200, 5: 300}
    assert linked_first_phases(batch, markets, events) == [
        {1: 'a', 2: 'b', 3: 'c', 4: 'd'}, {5: 'e'}]


def test_known_unbuffered_sibling_keeps_event_membership():
    assert linked_first_phases(
        {1: 'a', 3: 'c', 9: 'z'}, {1: 10, 2: 10, 3: 20, 9: 90},
        {2: 100, 3: 100}) == [{1: 'a', 3: 'c'}, {9: 'z'}]


def test_unknown_or_missing_market_falls_back_and_empty_is_preserved():
    for markets in ({1: 10}, {1: 10, 2: None}):
        batch = {1: 'a', 2: 'b'}
        assert linked_first_phases(batch, markets, {1: 100}) == [batch]
    assert linked_first_phases({}, {}, {}) == [{}]


async def test_existing_refresh_debt_keeps_unfinished_game_fenced():
    r = rig(pending={200})
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(r.entered.wait(), 2)
        assert r.committed == [1, 2]
        assert ('refresh', (100,)) in r.trace
        assert not any(t[0] == 'refresh' and 200 in t[1] for t in r.trace)
    finally:
        r.release.set()
        await asyncio.wait_for(task, 2)
    assert ('commit', (3,)) in r.trace
    assert ('refresh', (200,)) in r.trace
    assert r.committed == [1, 2, 3, 9]


def test_pending_fallback_preserves_batch_order():
    batch = {3: 'c', 9: 'z', 1: 'a', 2: 'b'}
    phases = linked_first_phases(batch, {1: 10, 2: 10, 3: 20, 9: 90},
                                 {1: 100, 2: 100, 3: 200}, {200})
    assert list(phases[0]) == [3, 1, 2]
    assert phases[1] == {9: 'z'}


async def test_real_refresher_debt_waits_for_its_own_game_commit():
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    r = rig()

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now):
            r.trace.append(('real-refresh', tuple(sorted(event_ids)), tuple(r.committed)))
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now

        async def publish_market_changes(self, session):
            r.trace.append(('publish', tuple(session.rows)))

    refresher = RecordingRefresher('kalshi')
    refresher.adopt_pending({200})
    r.flush.__globals__['blend_refresher'] = refresher
    task = asyncio.create_task(r.flush(flush_started=100.0))
    try:
        await asyncio.wait_for(r.entered.wait(), 2)
        assert ('real-refresh', (100,), (1, 2)) in r.trace
        assert not any(t[0] == 'real-refresh' and 200 in t[1] for t in r.trace)
    finally:
        r.release.set()
        await asyncio.wait_for(task, 2)
    assert ('real-refresh', (200,), (1, 2, 3)) in r.trace
    assert refresher.pending_event_ids() == frozenset()
    assert refresher.stats['throttled'] == 0
