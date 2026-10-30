"""#10090 — Argon's flush-loop Rank 1: a Kalshi flush fences only what is in
flight, and a write beside it is never overwritten by an older snapshot.

Production 2026-10-30 00:18:36-44Z (Kalshi 15338515, lock_retries=0): 3.19 s
receipt-to-commit, then 4.28 s held. Every stamp admission and the live write
beside a phase were fenced by ALL of the flush's unfinished snapshot
(160-220k entries). A live game whose phase was stamp-fenced (`fenced`
8-12k/min) or refused stayed in it for the rest of a 3-7 s flush: its newer
quotes could not be written beside, its committed price could not be stamped.

WHAT THIS FILE PROVES, on the SHIPPED `flush_prices` (AST-exec'd):

1. ORDERING (red->green): a live game in a LATER phase is written beside the
   running phase, and once that write has committed a newer price, the main
   flush never writes its older snapshot value for that outcome.
2. A live game whose phase was stamp-fenced is written beside a later phase of
   the same flush, and its stamp is no longer deferred by that snapshot.
3. Kept: the phase inside its transaction is never written beside; a live
   event split across phases (a late bridge) stays deferred until its last
   part commits; a non-live game keeps today's fence.

Production latency is not claimed here.
"""

import ast
import asyncio
import contextlib  # noqa: F401 — the exec'd flush reads it
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.tasks.live_blend_refresh as lbr
from app.tasks.kalshi_ws import (  # noqa: F401 — the exec'd flush reads these
    FLUSH_BUDGET_SECONDS,
    NONLIVE_PHASE_MAX_GAMES,
    NONLIVE_PHASE_MAX_ROWS,
    PRICE_PHASE_LOCK_TIMEOUT_MS,
    _FlushTimings,
    _KalshiPriceOwner,
    flush_budget_spent,
    linked_first_phases,
    live_preempts_tail,
    yield_written_nonlive_tail,
)
from app.tasks.live_blend_refresh import event_ids_for_outcomes  # noqa: F401
from app.utils.futures_rank import rerank_market_fields_stmt  # noqa: F401
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from app.utils.repair_lock_budget import (  # noqa: F401 — read by the exec'd flush
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)
from tests._kalshi_price_session import bind_session, consumer_engine
from tests.pm_bulk_test_support import price_writes, statement_params
from tests.test_flush_loop_live_aux_phase_10090 import (
    AUX_A,
    FUTURES,
    HEAD_A,
    HEAD_B,
    LIVE_A,
    LIVE_B,
    NONLIVE,
    PREGAME,
    maps,
)

pytestmark = pytest.mark.asyncio

OLD, NEW = 0.5, 0.7


def quote(p):
    return (p, p - 0.01, p + 0.01)


def rig(*, gate_oid=None, on_gate=None, on_row=None, aux=AUX_A):
    """The shipped flush, two live games, a pre-game game and futures.

    ``gate_oid``'s write waits on ``gate`` inside its phase's transaction,
    after ``on_gate`` runs (a tick arriving mid-transaction). ``on_row`` sees
    every committed-to-be row's market notification (a late bridge)."""
    markets, events = maps()
    clock = {"now": 0.0}
    writes = []  # (outcome, probability) in execution order
    commits = []
    asks = []  # ("refresh"|"admit", events, deferred, phases committed so far)
    gate = asyncio.Event()
    stats = defaultdict(int)

    class Session:
        def __init__(self):
            self.rows = []

        async def execute(self, stmt, bind=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                return SimpleNamespace(rowcount=1)
            pairs = price_writes(stmt, statement_params(stmt, bind))
            if not pairs:
                return SimpleNamespace(rowcount=0)
            (oid, prob), = pairs
            writes.append((oid, round(prob, 6)))
            if oid == gate_oid and not gate.is_set():
                if on_gate is not None:
                    on_gate()
                await gate.wait()
            self.rows.append(oid)
            row = SimpleNamespace(id=oid, market_id=markets[oid],
                                  last_updated=clock["now"], quote_moved=True)
            return SimpleNamespace(rowcount=1, all=lambda: [row])

    engine = consumer_engine()

    @asynccontextmanager
    async def session():
        s = bind_session(Session(), engine)
        yield s
        clock["now"] += 0.01
        if s.rows:
            commits.append(tuple(s.rows))

    class Refresher:
        holding = None  # `holding_event_ids` once set

        def holding_event_ids(self):
            return self.holding

        def pending_event_ids(self):
            return frozenset()

        def adopt_pending(self, ids):
            pass

        def admit_fresh(self, ids, *, defer_event_ids=(), **_kw):
            # A running call that admits whatever is not deferred.
            asks.append(("admit", set(ids), set(defer_event_ids), len(commits)))
            return frozenset(set(ids) - set(defer_event_ids))

        async def publish_market_changes(self, _s):
            return 0

        async def refresh(self, ids, *, defer_event_ids=(), **_kw):
            asks.append(("refresh", set(ids), set(defer_event_ids), len(commits)))

        async def refresh_pending(self, **_kw):
            return None

    class Receipts:
        def stage(self, _marks):
            return None

    def notify(_session, **kwargs):
        if on_row is not None:
            on_row(kwargs.get("outcome_observed_at") or {})

    buffer = {}
    prices = _KalshiPriceOwner()
    prices.timings = _FlushTimings()
    prices.headline_aux_outcome_ids.update(aux)
    refresher = Refresher()
    ns = dict(globals(), price_buffer=buffer, buffer_lock=asyncio.Lock(),
              market_id_by_outcome=markets, event_id_by_outcome=events,
              non_blend_outcome_ids=set(),
              input_marks={}, tail_receipts=Receipts(),
              primary_quote_custody=PrimaryQuoteCustody(), ticker_to_ids={},
              open_contract_outcome_ids=set(), blend_refresher=refresher,
              get_task_session=session, stats=stats, prices=prices,
              live_event_ids={LIVE_A, LIVE_B},
              flush_budget=None, flush_period=1.0,
              logger=logging.getLogger(__name__),
              queue_market_change=notify)
    path = Path(__file__).resolve().parents[1] / "app/tasks/kalshi_ws.py"
    tree = ast.parse(path.read_text())
    names = {"flush_prices", "observation_signature"}
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return SimpleNamespace(flush=ns["flush_prices"], buffer=buffer, clock=clock,
                           writes=writes, commits=commits, asks=asks, gate=gate,
                           prices=prices, refresher=refresher, events=events,
                           stats=stats)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    holder = {"now": 0.0}
    monkeypatch.setattr(lbr, "_mono", lambda: holder["now"])
    return holder


async def _until(predicate, turns=400):
    for _ in range(turns):
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


def _last_write(writes, oid):
    return [p for o, p in writes if o == oid][-1]


# ── 1. ordering ─────────────────────────────────────────────────────────────


async def test_a_beside_write_of_a_later_phase_is_never_overwritten_by_the_older_snapshot():
    r = None

    def tick_b():
        # A newer quote for live game B arrives while A's phase is open.
        r.buffer[HEAD_B[0]] = quote(NEW)
        r.prices.input_wake.set()

    r = rig(gate_oid=HEAD_A[0], on_gate=tick_b, aux=())
    r.buffer.update({oid: quote(OLD) for oid in HEAD_A + HEAD_B + NONLIVE})
    flush = asyncio.create_task(r.flush(0.0))
    try:
        # Written beside A's open transaction: B is in a LATER phase, not in
        # flight. Strawman (before): the whole snapshot fenced B out.
        assert await _until(lambda: (HEAD_B[0], NEW) in r.writes)
        assert not r.commits or HEAD_A[0] not in r.commits[-1]
    finally:
        r.gate.set()
    assert await asyncio.wait_for(flush, 5) is True
    newest = r.writes.index((HEAD_B[0], NEW))
    # The main flush's B phase must not write B's snapshot value after it.
    assert (HEAD_B[0], OLD) not in r.writes[newest:]
    assert _last_write(r.writes, HEAD_B[0]) == NEW
    assert r.stats["beside_superseded"] >= 1
    assert not r.buffer


async def test_a_tick_after_the_beside_write_is_still_written_by_the_main_flush():
    r = None
    newest = 0.9

    def tick_b_twice():
        r.buffer[HEAD_B[0]] = quote(NEW)
        r.prices.input_wake.set()

    r = rig(gate_oid=HEAD_A[0], on_gate=tick_b_twice, aux=())
    r.buffer.update({oid: quote(OLD) for oid in HEAD_A + HEAD_B})
    flush = asyncio.create_task(r.flush(0.0))
    try:
        assert await _until(lambda: (HEAD_B[0], NEW) in r.writes)
        await _until(lambda: HEAD_B[0] not in r.buffer)
        r.buffer[HEAD_B[0]] = quote(newest)  # buffered again: not superseded
    finally:
        r.gate.set()
    assert await asyncio.wait_for(flush, 5) is True
    assert _last_write(r.writes, HEAD_B[0]) == newest


# ── 2. a stamp-fenced live phase is not barred for the rest of the flush ────


async def test_a_stamp_fenced_live_game_is_written_beside_a_later_phase():
    r = None

    def release_b_and_tick():
        # B's earlier stamp returns, and a newer B quote arrives, while the
        # flush is inside A's prop-board phase (after B's phase was fenced).
        r.refresher.holding = set()
        r.buffer[HEAD_B[0]] = quote(NEW)
        r.prices.input_wake.set()

    r = rig(gate_oid=AUX_A[0], on_gate=release_b_and_tick)
    r.buffer.update({oid: quote(OLD) for oid in AUX_A + HEAD_B + HEAD_A + NONLIVE})
    stamp = asyncio.create_task(asyncio.Event().wait())  # B's stamp, running
    r.prices.stamping = stamp
    r.prices.stamping_events = {LIVE_B}
    r.refresher.holding = {LIVE_B}
    flush = asyncio.create_task(r.flush(0.0))
    try:
        assert await _until(lambda: (HEAD_B[0], NEW) in r.writes)
        assert r.stats["stamp_fenced"] == len(HEAD_B), "B's own phase was fenced"
        # Strawman (before): B sat in the unfinished snapshot until the next
        # flush; nothing wrote it beside.
        assert not any(AUX_A[0] in rows for rows in r.commits), "A's board still open"
    finally:
        r.gate.set()
    assert await asyncio.wait_for(flush, 5) is True
    assert _last_write(r.writes, HEAD_B[0]) == NEW
    stamp.cancel()
    await asyncio.gather(stamp, return_exceptions=True)


async def test_a_stamp_fenced_live_games_debt_is_not_deferred_by_the_snapshot():
    r = rig()
    r.buffer.update({oid: quote(OLD) for oid in HEAD_B + HEAD_A + NONLIVE})
    stamp = asyncio.create_task(asyncio.Event().wait())
    r.prices.stamping = stamp
    r.prices.stamping_events = {LIVE_B}
    r.refresher.holding = {LIVE_B}
    assert await r.flush(0.0) is True
    assert r.stats["stamp_fenced"] == len(HEAD_B)
    admits = [deferred for kind, _ids, deferred, _c in r.asks if kind == "admit"]
    assert admits, "the running call was offered each committed cohort"
    # Strawman (before): every admission deferred B, whose fenced quotes sat
    # in the unfinished snapshot for the rest of the flush.
    assert all(LIVE_B not in deferred for deferred in admits)
    # The non-live game keeps today's fence until its own phase commits.
    assert any(PREGAME in deferred for deferred in admits)
    stamp.cancel()
    await asyncio.gather(stamp, return_exceptions=True)


# ── 3. what stays fenced ────────────────────────────────────────────────────


async def test_the_phase_inside_its_transaction_is_never_written_beside():
    r = None

    def tick_a():
        r.buffer[HEAD_A[0]] = quote(NEW)
        r.prices.input_wake.set()

    r = rig(gate_oid=HEAD_A[1], on_gate=tick_a, aux=())
    r.buffer.update({oid: quote(OLD) for oid in HEAD_A + NONLIVE})
    flush = asyncio.create_task(r.flush(0.0))
    try:
        await _until(lambda: False, turns=40)  # beside has had its wake
        assert (HEAD_A[0], NEW) not in r.writes
    finally:
        r.gate.set()
    assert await asyncio.wait_for(flush, 5) is True
    # A's phase wrote its snapshot; the newer tick stays buffered for later.
    assert r.buffer[HEAD_A[0]] == quote(NEW)


async def test_a_live_event_split_by_a_late_bridge_stays_deferred_until_complete():
    r = None

    def bridge(observed):
        # The subscription bridges a futures outcome (a later phase) to live
        # game A while A's own phase is being written.
        if HEAD_A[0] in observed:
            r.events[FUTURES[0]] = LIVE_A

    r = rig(on_row=bridge, aux=())
    r.buffer.update({oid: quote(OLD) for oid in HEAD_A + HEAD_B + FUTURES})
    assert await r.flush(0.0) is True
    head_done = next(i for i, rows in enumerate(r.commits) if HEAD_A[0] in rows) + 1
    futures_done = next(i for i, rows in enumerate(r.commits) if FUTURES[0] in rows) + 1
    assert head_done < futures_done
    a_asks = [(deferred, committed) for _k, ids, deferred, committed in r.asks
              if LIVE_A in ids]
    # A's headline commit asks for A's stamp; the bridged futures outcome is
    # still unwritten, so A stays deferred: a partly written board is never
    # read. Its last part's commit asks again, clear.
    before = [deferred for deferred, committed in a_asks if committed < futures_done]
    after = [deferred for deferred, committed in a_asks if committed >= futures_done]
    assert before and all(LIVE_A in deferred for deferred in before)
    assert after and all(LIVE_A not in deferred for deferred in after)


async def test_split_fence_strawman_without_the_bridge_a_is_not_deferred():
    r = rig(aux=())
    r.buffer.update({oid: quote(OLD) for oid in HEAD_A + HEAD_B + FUTURES})
    assert await r.flush(0.0) is True
    a_asks = [deferred for _k, ids, deferred, _c in r.asks if LIVE_A in ids]
    assert a_asks and all(LIVE_A not in deferred for deferred in a_asks)
