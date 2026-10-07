"""#10678 lab controls: live-first ordering of the reviewed #10655 phases.

Run from backend/ (so `app.` imports and asyncio_mode=auto apply):

    cd backend && python3 -m pytest ../tools/live-speed-lab/live-priority-test.py \
        -c pytest.ini --rootdir . -p no:cacheprovider

Every control runs BASELINE (the pinned planner, `linked_first_phases` at
eaa8027a59) and CANDIDATE (`live_first_phases`) on the same inputs. The flush
controls execute the real `flush_prices` closure extracted from the pinned
kalshi_ws.py (the #10655 rig's technique) with only the planner name rebound.
They prove commit/publish/refresh ORDER. They measure no latency.
"""
import ast
import asyncio
import contextlib  # noqa: F401  (flush_prices reads it)
import importlib.util
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, or_, update  # noqa: F401  (names flush_prices reads)
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesOutcome  # noqa: F401
from app.tasks.kalshi_ws import linked_first_phases
from app.tasks.live_blend_refresh import event_ids_for_outcomes  # noqa: F401
from app.utils.futures_rank import rerank_market_fields_stmt  # noqa: F401
from app.utils.price_change_stamp import (  # noqa: F401
    price_changed_at_value, quote_moved_column)
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES  # noqa: F401

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
_spec = importlib.util.spec_from_file_location(
    "live_priority_planner", HERE / "live-priority-planner.py")
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)
live_first_phases = lp.live_first_phases


def canon(phases):
    """Phase list as comparable (order-sensitive) item tuples."""
    return [tuple(p.items()) for p in phases]


# Two games and one futures row. Game A (event 100: markets 10, 11 -- a
# complement pair each) is SCHEDULED and arrives first; game B (event 200:
# market 20) is LIVE and arrives second; 9 is an unlinked futures row.
BATCH = {1: "a1", 2: "a2", 3: "a3", 4: "a4", 5: "b1", 6: "b2", 9: "z"}
MARKETS = {1: 10, 2: 10, 3: 11, 4: 11, 5: 20, 6: 20, 9: 90}
EVENTS = {1: 100, 2: 100, 3: 100, 4: 100, 5: 200, 6: 200}


# ---------------------------------------------------------------- planner
def test_empty_live_set_is_the_baseline_plan_exactly():
    base = linked_first_phases(BATCH, MARKETS, EVENTS)
    assert canon(live_first_phases(BATCH, MARKETS, EVENTS)) == canon(base)
    assert canon(live_first_phases(BATCH, MARKETS, EVENTS,
                                   live_event_ids=())) == canon(base)


def test_all_live_equals_baseline():
    base = linked_first_phases(BATCH, MARKETS, EVENTS)
    cand = live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids={100, 200})
    assert canon(cand) == canon(base)


def test_all_scheduled_equals_baseline():
    base = linked_first_phases(BATCH, MARKETS, EVENTS)
    cand = live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids={999})
    assert canon(cand) == canon(base)


def test_live_game_moves_ahead_of_scheduled_whole():
    base = linked_first_phases(BATCH, MARKETS, EVENTS)
    cand = live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids={200})
    assert canon(base) == canon([{1: "a1", 2: "a2", 3: "a3", 4: "a4"},
                                 {5: "b1", 6: "b2"}, {9: "z"}])
    assert canon(cand) == canon([{5: "b1", 6: "b2"},
                                 {1: "a1", 2: "a2", 3: "a3", 4: "a4"},
                                 {9: "z"}])
    # Same phases, same rows: re-order only, never re-cut.
    assert sorted(canon(cand)) == sorted(canon(base))


def test_mixed_component_touching_a_live_event_is_live_and_whole():
    # Market 20 is shared by events 200 (live) and 300 (scheduled); market 30
    # belongs to 300 only. One component; it must stay whole and go live-tier.
    batch = {1: "s", 7: "m30", 5: "m20", 9: "z"}
    markets = {1: 10, 7: 30, 5: 20, 6: 20, 9: 90}
    events = {1: 100, 7: 300, 5: 200, 6: 300}
    base = linked_first_phases(batch, markets, events)
    cand = live_first_phases(batch, markets, events, live_event_ids={200})
    assert canon(base) == canon([{1: "s"}, {7: "m30", 5: "m20"}, {9: "z"}])
    assert canon(cand) == canon([{7: "m30", 5: "m20"}, {1: "s"}, {9: "z"}])


def test_live_event_reached_only_through_unbuffered_sibling_marks_phase():
    # Outcome 2 (market 10, event 200 live) has no buffered tick; outcome 1
    # shares market 10. The component still touches the live event.
    batch = {3: "sched", 1: "tick", 9: "z"}
    markets = {1: 10, 2: 10, 3: 20, 9: 90}
    events = {2: 200, 3: 100}
    cand = live_first_phases(batch, markets, events, live_event_ids={200})
    assert canon(cand) == canon([{1: "tick"}, {3: "sched"}, {9: "z"}])


def test_live_event_two_hops_away_through_unbuffered_market_marks_phase():
    # Buffered outcome 1 (market 10) belongs to scheduled event 300. Market 20
    # has NO buffered tick but belongs to both 300 and live event 200, so the
    # #10655 component {10, 20} touches the live event only via market 20.
    batch = {3: "sched", 1: "tick", 9: "z"}
    markets = {1: 10, 2: 20, 4: 20, 3: 30, 9: 90}
    events = {1: 300, 2: 300, 4: 200, 3: 100}
    assert canon(linked_first_phases(batch, markets, events)) == canon(
        [{3: "sched"}, {1: "tick"}, {9: "z"}])
    cand = live_first_phases(batch, markets, events, live_event_ids={200})
    assert canon(cand) == canon([{1: "tick"}, {3: "sched"}, {9: "z"}])


def test_unknown_membership_keeps_the_single_transaction():
    for markets in ({1: 10, 5: 20}, {1: 10, 5: 20, 9: None}):
        batch = {1: "a", 5: "b", 9: "z"}
        cand = live_first_phases(batch, markets, {1: 100, 5: 200},
                                 live_event_ids={200})
        assert cand == [batch]
    assert live_first_phases({}, {}, {}, live_event_ids={1}) == [{}]


def test_pending_refresh_debt_keeps_baseline_all_games_phase():
    base = linked_first_phases(BATCH, MARKETS, EVENTS, pending_events={100})
    cand = live_first_phases(BATCH, MARKETS, EVENTS, pending_events={100},
                             live_event_ids={200})
    assert canon(cand) == canon(base)
    assert list(cand[0]) == [1, 2, 3, 4, 5, 6]  # batch order, one game phase


def test_stable_order_within_tiers():
    # Arrival: S1, L1, S2, L2, futures. Expect L1, L2, S1, S2, futures.
    batch = {1: "S1", 2: "L1", 3: "S2", 4: "L2", 9: "z"}
    markets = {1: 10, 2: 20, 3: 30, 4: 40, 9: 90}
    events = {1: 100, 2: 200, 3: 300, 4: 400}
    cand = live_first_phases(batch, markets, events, live_event_ids={200, 400})
    assert [list(p.values()) for p in cand] == [
        ["L1"], ["L2"], ["S1"], ["S2"], ["z"]]


def test_unrelated_phase_stays_last_and_only_unlinked_rows_are_in_it():
    cand = live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids={200})
    assert cand[-1] == {9: "z"}
    assert all(9 not in p for p in cand[:-1])


def test_live_set_is_snapshotted_on_entry():
    live = {200}
    first = live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids=live)
    live.clear()  # status flips after the plan was made
    assert canon(first)[0] == ((5, "b1"), (6, "b2"))
    # The flip takes effect on the NEXT call only.
    second = live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids=live)
    assert canon(second) == canon(linked_first_phases(BATCH, MARKETS, EVENTS))


def test_status_flip_scheduled_to_live_and_back():
    plans = [live_first_phases(BATCH, MARKETS, EVENTS, live_event_ids=s)
             for s in (set(), {200}, {100, 200}, {100})]
    heads = [tuple(p[0]) for p in plans]
    assert heads == [(1, 2, 3, 4), (5, 6), (1, 2, 3, 4), (1, 2, 3, 4)]


def test_batch_and_maps_are_not_mutated():
    b, m, e = dict(BATCH), dict(MARKETS), dict(EVENTS)
    live_first_phases(b, m, e, live_event_ids={200})
    assert (b, m, e) == (BATCH, MARKETS, EVENTS)
    assert list(b) == list(BATCH)


# ---------------------------------------------------------------- flush rig
def flush_rig(live_snapshot, *, failed=None, pending=()):
    """The real pinned `flush_prices`, planner name rebound to the candidate.

    ``live_snapshot`` is a zero-arg callable read ONCE per flush (the way the
    proposed patch reads the admission re-read's holder); ``None`` runs the
    baseline planner untouched.
    """
    batch = {oid: (oid / 10, oid / 10 - .01, oid / 10 + .01) for oid in BATCH}
    trace, committed = [], []
    stats = defaultdict(int)
    control = {"failed": failed, "reads": 0}

    class Session:
        def __init__(self):
            self.rows = []

        async def execute(self, stmt):
            params = stmt.compile(dialect=postgresql.dialect()).params
            if "current_probability" not in params:
                return SimpleNamespace(rowcount=0)
            oid = params["id_1"]
            trace.append(("write", oid))
            if oid == control["failed"]:
                raise RuntimeError("controlled write failure")
            self.rows.append(oid)
            row = SimpleNamespace(id=oid, market_id=MARKETS[oid],
                                  last_updated=oid, quote_moved=True)
            return SimpleNamespace(rowcount=1, all=lambda: [row])

    @asynccontextmanager
    async def session():
        s = Session()
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

        async def publish_market_changes(self, s):
            trace.append(("publish", tuple(s.rows)))

        async def refresh(self, ids, **kwargs):
            trace.append(("refresh", tuple(sorted(ids))))

        async def refresh_pending(self, **kwargs):
            trace.append(("pending",))

    class Receipts:
        def stage(self, marks):
            pass

    if live_snapshot is None:
        planner = linked_first_phases
    else:
        def planner(b, m, e, pending_events=()):
            control["reads"] += 1
            return live_first_phases(b, m, e, pending_events=pending_events,
                                     live_event_ids=live_snapshot(),
                                     planner=linked_first_phases)

    ns = dict(globals(), price_buffer=batch, buffer_lock=asyncio.Lock(),
              market_id_by_outcome=MARKETS, event_id_by_outcome=EVENTS,
              input_marks={oid: oid for oid in batch}, tail_receipts=Receipts(),
              open_contract_outcome_ids={9}, blend_refresher=Refresher(),
              get_task_session=session, stats=stats,
              logger=logging.getLogger(__name__),
              queue_market_change=lambda *a, **k: None)
    path = BACKEND / "app/tasks/kalshi_ws.py"
    tree = ast.parse(path.read_text())
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
             and n.name == "flush_prices"]
    assert len(nodes) == 1
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    ns["linked_first_phases"] = planner
    return SimpleNamespace(flush=ns["flush_prices"], batch=batch, trace=trace,
                           committed=committed, stats=stats, control=control)


def live_refresh_position(trace):
    """Writes that precede the live game's (event 200) blend refresh."""
    stop = trace.index(("refresh", (200,)))
    return sum(1 for t in trace[:stop] if t[0] == "write")


async def test_flush_baseline_vs_candidate_live_refresh_position():
    base = flush_rig(None)
    cand = flush_rig(lambda: frozenset({200}))
    assert await base.flush() is True
    assert await cand.flush() is True
    # Same rows written and paid in both; only the order differs.
    assert sorted(base.committed) == sorted(cand.committed) == sorted(BATCH)
    assert not base.batch and not cand.batch
    assert base.stats["price_updates"] == cand.stats["price_updates"] == 7
    # Baseline: the scheduled game's 4 writes precede the live refresh.
    assert live_refresh_position(base.trace) == 6
    assert live_refresh_position(cand.trace) == 2
    i = cand.trace.index
    assert i(("commit", (5, 6))) < i(("publish", (5, 6))) < i(("refresh", (200,)))
    assert i(("refresh", (200,))) < i(("write", 1))


async def test_flush_reads_the_live_snapshot_once():
    cand = flush_rig(lambda: frozenset({200}))
    assert await cand.flush() is True
    assert cand.control["reads"] == 1


async def test_flush_failure_retains_later_tiers_then_pays_them():
    # The live game commits; the scheduled game's write fails: the scheduled
    # game and the futures row are retained (none dropped) and paid next flush.
    cand = flush_rig(lambda: frozenset({200}), failed=3)
    assert await cand.flush() is False
    assert cand.committed == [5, 6]
    assert set(cand.batch) == {1, 2, 3, 4, 9}
    assert cand.stats["requeued"] == 5
    cand.control["failed"] = None
    assert await cand.flush() is True
    assert sorted(cand.committed) == sorted(BATCH)
    assert not cand.batch


async def test_flush_pending_debt_is_baseline_shape():
    base = flush_rig(None, pending={100})
    cand = flush_rig(lambda: frozenset({200}), pending={100})
    assert await base.flush() is True
    assert await cand.flush() is True
    commits = lambda r: [t for t in r.trace if t[0] in ("commit", "refresh")]
    assert commits(base) == commits(cand)


# ------------------------------------------------- sustained arrivals
def test_no_starvation_under_sustained_live_arrivals():
    """Every flush attempts every phase, so no tier waits more than 1 flush.

    Simulate 200 flushes where the live game re-ticks EVERY flush and a
    scheduled game ticks every 3rd. Each successful flush pays its whole
    batch (the #10655 contract); the candidate only reorders inside it.
    """
    markets = {1: 10, 2: 10, 3: 20, 4: 20, 9: 90}
    events = {1: 100, 2: 100, 3: 200, 4: 200}
    worst_lag = {"sched": 0, "futures": 0}
    first_seen = {}
    for f in range(200):
        arrivals = {3: f, 4: f}  # live game, every flush
        if f % 3 == 0:
            arrivals.update({1: f, 2: f})
        if f % 7 == 0:
            arrivals[9] = f
        for oid in arrivals:
            first_seen.setdefault(oid, f)
        phases = live_first_phases(arrivals, markets, events,
                                   live_event_ids={200})
        paid = {oid for p in phases for oid in p}
        assert paid == set(arrivals)  # nothing dropped
        for oid in paid:
            key = "sched" if oid in (1, 2) else "futures" if oid == 9 else None
            if key:
                worst_lag[key] = max(worst_lag[key], f - first_seen.pop(oid))
            else:
                first_seen.pop(oid)
    assert worst_lag == {"sched": 0, "futures": 0}
