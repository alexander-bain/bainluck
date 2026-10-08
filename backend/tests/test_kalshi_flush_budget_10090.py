"""#10090 — a Kalshi flush meant to run every 2 s must not stretch to minutes.

THE SHIP. A real moving Kalshi probability reaches the event-page headline and
chart within seconds. Production 2026-10-08 00:25–00:35Z (run b47fefde, the
retained #10702 log): no errors, yet one flush per 1.5–3.3 min on the 2 s
cadence. Each flush wrote every game that had ticked since the last one, one
phase per game (~55 s across ~976 subscribed events), then one ~1,300-row
futures/props transaction; the live WNBA game's moving quote waited for all of
it, and a stretched flush buffered still more for the next.

WHAT THIS FILE PROVES, on the SHIPPED `flush_prices` (AST-exec'd, as the
#10655 rig does) with a simulated clock:

1. The planner: live games first, one phase each; other games packed whole (at
   most `NONLIVE_PHASE_MAX_GAMES` a phase) and futures/props whole markets at a
   time, at most `NONLIVE_PHASE_MAX_ROWS` rows a phase; no live set keeps the
   pre-#10090 plan exactly.
2. A periodic flush stops STARTING non-live phases past `FLUSH_BUDGET_SECONDS`,
   whatever the backlog; what it leaves stays buffered and is the head of the
   next flush; nothing is lost and nothing starves. The final drain is never
   budgeted.
3. The loop: over many cycles with ticks arriving everywhere, the live game's
   tick-to-write delay stays within the budget. Strawman: the same rig on the
   pre-#10090 plan delays it by minutes, so the bound is not vacuous.
4. Timings: the stats line's phase split adds up and counts phases.

Production latency is not claimed here; the next stats line measures it.
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
)
from app.tasks.live_blend_refresh import event_ids_for_outcomes  # noqa: F401
from app.utils.futures_rank import rerank_market_fields_stmt  # noqa: F401
from app.utils.repair_lock_budget import (  # noqa: F401 — read by the exec'd flush
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)
from tests._kalshi_price_session import bind_session, consumer_engine
from tests.pm_bulk_test_support import price_writes, statement_params

pytestmark = pytest.mark.asyncio

#: Simulated costs, near the production shape: ~0.4 s of fixed work per
#: transaction (checkout, rank, commit, publish) plus a little per row, and a
#: blend stamp per refreshed event.
PHASE_COST = 0.4
ROW_COST = 0.002
STAMP_COST = 0.05

LIVE_EVENT = 5000


def _game(g):
    """Game ``g``: market 1000+g, event 5000+g, outcomes 2g and 2g+1."""
    return (2 * g, 2 * g + 1), 1000 + g, LIVE_EVENT + g


def maps(games, futures_markets=0, outcomes_per_future=10):
    markets, events = {}, {}
    for g in range(games):
        oids, market, event = _game(g)
        for oid in oids:
            markets[oid], events[oid] = market, event
    for m in range(futures_markets):
        for k in range(outcomes_per_future):
            markets[100_000 + m * 100 + k] = 9000 + m
    return markets, events


def rig(*, games, futures_markets=0, live=frozenset({LIVE_EVENT})):
    """The shipped flush over ``games`` games and some futures, on a fake clock.

    Batch order puts the live game LAST: it ticked most recently, the worst
    case for a plan that writes in arrival order.
    """
    markets, events = maps(games, futures_markets)
    clock = {"now": 0.0}
    written = []  # (outcome, simulated write instant)
    stats = defaultdict(int)

    class Session:
        def __init__(self):
            self.rows = []

        async def execute(self, stmt, bind=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                return SimpleNamespace(rowcount=1)
            pairs = price_writes(stmt, statement_params(stmt, bind))
            if not pairs:
                return SimpleNamespace(rowcount=0)  # the field re-rank
            (oid, _prob), = pairs
            self.rows.append(oid)
            row = SimpleNamespace(id=oid, market_id=markets[oid],
                                  last_updated=clock["now"], quote_moved=True)
            return SimpleNamespace(rowcount=1, all=lambda: [row])

    engine = consumer_engine()

    @asynccontextmanager
    async def session():
        s = bind_session(Session(), engine)
        yield s
        clock["now"] += PHASE_COST + ROW_COST * len(s.rows)
        written.extend((oid, clock["now"]) for oid in s.rows)

    class Refresher:
        def pending_event_ids(self):
            return frozenset()

        async def publish_market_changes(self, _s):
            return 0

        async def refresh(self, ids, **_kw):
            clock["now"] += STAMP_COST * len(ids)

        async def refresh_pending(self, **_kw):
            return None

    class Receipts:
        def stage(self, _marks):
            return None

    buffer = {}
    prices = _KalshiPriceOwner()
    prices.timings = _FlushTimings()
    ns = dict(globals(), price_buffer=buffer, buffer_lock=asyncio.Lock(),
              market_id_by_outcome=markets, event_id_by_outcome=events,
              input_marks={}, tail_receipts=Receipts(),
              open_contract_outcome_ids=set(), blend_refresher=Refresher(),
              get_task_session=session, stats=stats, prices=prices,
              live_event_ids=None if live is None else set(live),
              flush_budget=None,  # the unset run: `FLUSH_BUDGET_SECONDS`
              logger=logging.getLogger(__name__),
              queue_market_change=lambda *a, **k: None)
    path = Path(__file__).resolve().parents[1] / "app/tasks/kalshi_ws.py"
    (node,) = [n for n in ast.walk(ast.parse(path.read_text()))
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "flush_prices"]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return SimpleNamespace(flush=ns["flush_prices"], buffer=buffer, clock=clock,
                           written=written, stats=stats, markets=markets,
                           events=events, prices=prices)


def tick(r, oid, p=0.5):
    """A venue tick, buffered the way `handle_ticker` keys it."""
    r.buffer[oid] = (p, p - 0.01, p + 0.01)


def tick_everything(r, p):
    """Every game except the live one, then the futures, then the live game."""
    for oid in r.markets:
        if r.events.get(oid) != LIVE_EVENT:
            tick(r, oid, p)
    for oid in _game(0)[0]:
        tick(r, oid, p)


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """`flush_budget_spent` reads the refresher's clock seam at call time."""
    holder = {}
    monkeypatch.setattr(lbr, "_mono", lambda: holder["rig"].clock["now"])
    return holder


# ------------------------------------------------------- 1. the planner ----


def _batch(oids):
    return {oid: (0.5, 0.49, 0.51) for oid in oids}


def test_live_games_come_first_one_phase_each():
    markets, events = maps(6)
    order = [oid for g in (3, 1, 0, 4, 2, 5) for oid in _game(g)[0]]
    phases = linked_first_phases(_batch(order), markets, events,
                                 live_events={LIVE_EVENT + 2, LIVE_EVENT + 4})
    assert [list(p) for p in phases[:2]] == [[8, 9], [4, 5]]  # batch order
    assert sorted(oid for p in phases[2:] for oid in p) == [0, 1, 2, 3, 6, 7, 10, 11]
    assert len(phases) == 3  # the four other games packed into one phase


def test_other_games_and_futures_are_packed_whole_up_to_the_cap():
    games, futures = 250, 45  # 500 game rows, 450 futures rows
    markets, events = maps(games, futures)
    phases = linked_first_phases(_batch(markets), markets, events, live_events=set())
    for phase in phases:
        assert len(phase) <= NONLIVE_PHASE_MAX_ROWS
        # Whole games and whole markets: never a partial cut.
        for oid in phase:
            siblings = [o for o, m in markets.items() if m == markets[oid]]
            assert all(s in phase for s in siblings)
    games_phases = [p for p in phases if any(o in events for o in p)]
    assert all(all(o in events for o in p) for p in games_phases)  # never mixed
    assert all(len({events[o] for o in p}) <= NONLIVE_PHASE_MAX_GAMES
               for p in games_phases)
    assert len(games_phases) == 32 and len(phases) == 35  # 250/8 up; 200+200+50
    flat = [oid for p in phases for oid in p]
    assert flat == list(markets)  # batch order: oldest buffered first


def test_a_game_or_market_larger_than_the_cap_is_one_phase_not_cut():
    markets = {oid: 9000 for oid in range(NONLIVE_PHASE_MAX_ROWS + 7)}
    phases = linked_first_phases(_batch(markets), markets, {}, live_events=set())
    assert [len(p) for p in phases] == [NONLIVE_PHASE_MAX_ROWS + 7]


def test_without_a_live_set_the_plan_is_the_pre_10090_one():
    markets, events = maps(5, 3)
    batch = _batch(markets)
    phases = linked_first_phases(batch, markets, events)
    assert len(phases) == 6  # five games, one futures phase
    assert list(phases[-1]) == [oid for oid in markets if oid not in events]


# ---------------------------------------- 2. one flush, budget and drain ----


@pytest.mark.parametrize("games", [50, 500, 2000, 8000])
async def test_a_flush_stops_starting_nonlive_phases_past_its_budget(games, fake_clock):
    r = rig(games=games, futures_markets=games // 10)
    fake_clock["rig"] = r
    tick_everything(r, 0.6)
    before = len(r.buffer)
    assert await r.flush(0.0) is True
    first = [oid for oid, _ in r.written[:2]]
    assert sorted(first) == [0, 1], "the live game is not the first write"
    # Bounded by the budget plus the one phase already started, not the backlog.
    biggest = PHASE_COST + ROW_COST * NONLIVE_PHASE_MAX_ROWS
    biggest += STAMP_COST * NONLIVE_PHASE_MAX_GAMES
    assert r.clock["now"] <= FLUSH_BUDGET_SECONDS + biggest
    assert len(r.written) + len(r.buffer) == before  # nothing lost
    assert r.stats["budget_deferred"] == len(r.buffer) > 0
    assert r.stats["errors"] == 0


async def test_the_deferred_tail_is_the_head_of_the_next_flush(fake_clock):
    r = rig(games=400, futures_markets=40)
    fake_clock["rig"] = r
    tick_everything(r, 0.6)
    expected = [oid for oid in r.buffer if r.events.get(oid) != LIVE_EVENT]
    flushes = 0
    while r.buffer:
        flushes += 1
        assert await r.flush(r.clock["now"]) is True
        assert flushes < 50, "the tail never drained"
    nonlive = [oid for oid, _ in r.written if r.events.get(oid) != LIVE_EVENT]
    assert nonlive == expected  # oldest first across flushes, none skipped
    assert flushes > 1


@pytest.mark.parametrize("started", [None, 0.0])
async def test_the_final_drain_is_never_budgeted(started, fake_clock):
    r = rig(games=600, futures_markets=60)
    fake_clock["rig"] = r
    tick_everything(r, 0.6)
    assert await r.flush(started, final_drain=True) is True
    assert not r.buffer and r.stats["budget_deferred"] == 0
    assert r.clock["now"] > FLUSH_BUDGET_SECONDS * 5  # it really was long


# ---------------------------------------------------------- 3. the loop ----


async def _live_delays(r, cycles):
    """Run ``cycles`` flushes back to back (the cadence's overdue case), with
    everything ticking before each; return each live tick's delay to its write."""
    delays = []
    for cycle in range(cycles):
        ticked_at = r.clock["now"]
        tick_everything(r, 0.3 + cycle / 1000)
        done = len(r.written)
        await r.flush(r.clock["now"])
        for oid, at in r.written[done:]:
            if oid == 0:
                delays.append(at - ticked_at)
    return delays


async def test_a_two_second_loop_keeps_the_live_game_within_seconds(fake_clock):
    r = rig(games=976, futures_markets=130)  # the b47fefde slate's size
    fake_clock["rig"] = r
    delays = await _live_delays(r, 12)
    assert len(delays) == 12  # written on EVERY flush
    assert max(delays) <= PHASE_COST + ROW_COST * 2 + STAMP_COST
    assert r.stats["errors"] == 0


async def test_strawman_the_pre_10090_plan_delays_the_live_game_by_minutes(fake_clock):
    r = rig(games=976, futures_markets=130, live=None)
    fake_clock["rig"] = r
    delays = await _live_delays(r, 3)
    assert min(delays) >= 60, delays


# ------------------------------------------------------- 4. the timings ----


async def test_the_timings_count_phases_and_split_the_flush(fake_clock):
    r = rig(games=30, futures_markets=3)
    fake_clock["rig"] = r
    tick_everything(r, 0.6)
    await r.flush(None)
    timings = r.prices.timings
    timings.flushed(1.0)  # what `timed_flush` does when the flush returns
    # One live phase, the 29 other games in phases of eight (8+8+8+5), and the
    # three futures markets (30 rows) in one.
    assert timings.phases == 6
    assert timings.spent["save"] >= 0

    async def slow():
        await asyncio.sleep(0.01)
        return "ok"

    t = _FlushTimings()
    assert await t.timed("stamp", slow)() == "ok"
    assert t.spent["stamp"] == 0  # in flight until its flush returns
    t.flushed(0.5)
    t.flushed(1.5)
    assert t.spent["stamp"] > 0
    line = t.line()
    assert line.startswith("flush n=2 total=2.0s max=1.5s phases=0 save=0.0s")
    assert "rank_commit=" in line and "stamp=0.0s" in line
    t.reset()
    assert t.flushes == 0 and t.total == 0 and t.spent["stamp"] == 0


async def test_a_minute_reset_mid_flush_keeps_the_flush_in_one_minute():
    """CERT-4016 follow-up: a reset between a flush's phases and its end must
    not leave the minute with bucket time but no total (or the reverse)."""
    t = _FlushTimings()
    t.add("save", 0.75, phase=True)  # the flush's first phase, before the line
    t.reset()                        # the stats line fires mid-flush
    t.add("stamp", 0.25)
    t.flushed(1.5)                   # the flush returns in the new minute
    assert t.spent == {"save": 0.75, "publish": 0.0, "stamp": 0.25}
    assert t.phases == 1 and t.total == 1.5
    assert "rank_commit=0.5s" in t.line()
