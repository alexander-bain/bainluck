"""#10090 — the stats line says where the minute's longest flush WAITED.

Production showed one Kalshi flush of 2.6 s holding every Kalshi stamp while
Polymarket stamped every quarter second. The fix differs by cause (pool or SQL,
publish, or the run's own stamp join), and the existing buckets cannot say:
`stamp` joins whichever flush ends later and `rank_commit` is a floored
remainder (`_FlushTimings`). `slowest` times the flush's own awaits on its own
clock. This file drives the SHIPPED `flush_prices` (AST-exec'd, as the #10655
rig does) with real sleeps injected at one seam at a time and checks each
lands in its own field, a stamp the flush did not wait for lands in none, and
a stats-line reset mid-flush keeps the flush whole.

Inside `db`, `slowest_db` nests the lock-timeout SET (lazy checkout), the price
pipeline and the re-rank execute; `db.unknown` is the rest (enter, exit,
commit). The nested spans are part of `db`, never added to it.

VIRTUAL TIME (#10090, integrator 2001Z: `db=0.31 s` against a 0.1 s bound on a
loaded CI runner). Every test here runs on `_VirtualClockLoop`, and the timings
read that loop's clock: time stands still while anything is runnable and jumps
to the next timer when nothing is. An injected sleep measures exactly, a seam
nothing was injected into measures zero, and a runner stall moves neither
(`test_a_runner_stall_lands_in_no_field`).
"""

import ast
import asyncio
import contextlib  # noqa: F401 — the exec'd flush reads it
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks.kalshi_ws import (  # noqa: F401 — the exec'd flush reads these
    PRICE_FLUSH_SECONDS,
    PRICE_PHASE_LOCK_TIMEOUT_MS,
    _FlushTimings,
    _KalshiPriceOwner,
    flush_budget_spent,
    linked_first_phases,
    live_preempts_tail,
    yield_written_nonlive_tail,
)
from app.tasks.live_blend_refresh import _mono, event_ids_for_outcomes  # noqa: F401
from app.utils.futures_rank import rerank_market_fields_stmt  # noqa: F401
from app.utils.repair_lock_budget import (  # noqa: F401 — read by the exec'd flush
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from tests._kalshi_price_session import bind_session, consumer_engine
from tests.pm_bulk_test_support import price_writes, statement_params

pytestmark = pytest.mark.asyncio


class _JumpingSelector:
    """The loop's selector, except that a wait for the next timer is not
    slept: the loop's clock moves to that timer and the poll returns."""

    def __init__(self, selector, loop):
        self._selector, self._loop = selector, loop

    def select(self, timeout=None):
        if timeout is not None and timeout > 0:
            self._loop.virtual_now += timeout
            timeout = 0
        return self._selector.select(timeout)

    def __getattr__(self, name):
        return getattr(self._selector, name)


class _VirtualClockLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        super().__init__()
        self.virtual_now = 0.0
        self._selector = _JumpingSelector(self._selector, self)

    def time(self):
        return self.virtual_now


class _VirtualClockPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        return _VirtualClockLoop()


@pytest.fixture(scope="module")
def event_loop_policy():
    # Deprecated in pytest-asyncio 1.x in favour of a 1.x-only hook; kept
    # because `requirements.txt` admits >=0.23.3, which has only this.
    return _VirtualClockPolicy()


def _now():
    try:
        return asyncio.get_running_loop().time()
    except RuntimeError:  # the synchronous unit tests: no loop, no timing
        return time.monotonic()


@pytest.fixture(autouse=True)
def _timings_read_the_loop_clock(monkeypatch):
    import app.tasks.kalshi_ws as module

    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=_now))


SLOW = 0.25
#: Everything not injected is in-memory; well under this on any runner.
QUIET = 0.1


def rig(*, games=2, live=None, delays=None, on_commit=None, commits=()):
    """The shipped flush; ``delays`` sleeps at one seam: prepare, commit,
    publish, stamp (the refresh task's own work) or pending (inline refresh);
    inside the transaction set_lock, write (each price row) or rerank.
    ``commits`` overrides the commit sleep per transaction, in order."""
    delays = defaultdict(float, delays or {})
    commits = list(commits)
    markets = {oid: 1000 + g for g in range(games) for oid in (2 * g, 2 * g + 1)}
    events = {oid: 5000 + g for g in range(games) for oid in (2 * g, 2 * g + 1)}

    class Session:
        def __init__(self):
            self.rows = []

        async def execute(self, stmt, bind=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                await asyncio.sleep(delays["set_lock"])
                return SimpleNamespace(rowcount=1)
            pairs = price_writes(stmt, statement_params(stmt, bind))
            if not pairs:
                await asyncio.sleep(delays["rerank"])
                return SimpleNamespace(rowcount=0)  # the field re-rank
            await asyncio.sleep(delays["write"])
            (oid, _prob), = pairs
            self.rows.append(oid)
            row = SimpleNamespace(id=oid, market_id=markets[oid],
                                  last_updated=_now(), quote_moved=True)
            return SimpleNamespace(rowcount=1, all=lambda: [row])

    engine = consumer_engine()

    @asynccontextmanager
    async def session():
        await asyncio.sleep(delays["prepare"])  # checkout / setup
        yield bind_session(Session(), engine)
        await asyncio.sleep(commits.pop(0) if commits else delays["commit"])
        if on_commit is not None:
            on_commit()

    class Refresher:
        def pending_event_ids(self):
            return frozenset()

        async def publish_market_changes(self, _s):
            await asyncio.sleep(delays["publish"])

        async def refresh(self, ids, **_kw):
            await asyncio.sleep(delays["stamp"])

        async def refresh_pending(self, **_kw):
            await asyncio.sleep(delays["pending"])

        def admit_fresh(self, ids, **_kw):
            return set(ids)  # joins the running refresh; no wait

        def adopt_pending(self, _ids):
            return None

    refresher = Refresher()
    timings = _FlushTimings()
    # As production wraps them (`_run_kalshi_ws_consumer`): the old buckets.
    refresher.publish_market_changes = timings.timed(
        "publish", refresher.publish_market_changes)
    refresher.refresh = timings.timed("stamp", refresher.refresh)

    class Receipts:
        def stage(self, _marks):
            return None

    buffer = {}
    prices = _KalshiPriceOwner()
    prices.timings = timings
    ns = dict(globals(), price_buffer=buffer, buffer_lock=asyncio.Lock(),
              market_id_by_outcome=markets, event_id_by_outcome=events,
              non_blend_outcome_ids=set(), input_marks={},
              primary_quote_custody=PrimaryQuoteCustody(), ticker_to_ids={},
              tail_receipts=Receipts(), open_contract_outcome_ids=set(),
              blend_refresher=refresher, get_task_session=session,
              stats=defaultdict(int), prices=prices,
              live_event_ids=None if live is None else set(live),
              flush_budget=None, flush_period=1.0,
              logger=logging.getLogger(__name__),
              queue_market_change=lambda *a, **k: None)
    path = Path(__file__).resolve().parents[1] / "app/tasks/kalshi_ws.py"
    (node,) = [n for n in ast.walk(ast.parse(path.read_text()))
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "flush_prices"]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)

    async def timed_flush(**kwargs):
        # What the consumer's `timed_flush` does around the shipped flush.
        started = _now()
        try:
            return await ns["flush_prices"](None, **kwargs)
        finally:
            timings.flushed(_now() - started)

    return SimpleNamespace(flush=timed_flush, buffer=buffer, prices=prices,
                           timings=timings, delays=delays, stats=ns["stats"])


def tick(r, *games):
    for g in games:
        for oid in (2 * g, 2 * g + 1):
            r.buffer[oid] = (0.6, 0.59, 0.61)


def slowest(r):
    waits, phase = r.timings.slowest
    return waits, phase


async def settle(r):
    """The refresh this flush left running finishes, outside any flush."""
    if r.prices.stamping is not None:
        await asyncio.wait({r.prices.stamping})


# ---------------------------------------------- one seam, one field ----


@pytest.mark.parametrize("seam", ["prepare", "commit"])
async def test_a_slow_checkout_or_commit_is_db(seam):
    r = rig(games=1, delays={seam: SLOW})
    tick(r, 0)
    assert await r.flush() is True
    waits, (phase_s, live, rows) = slowest(r)
    assert waits["db"] >= SLOW
    assert waits["publish"] < QUIET and waits["stamp_wait"] < QUIET
    assert phase_s >= SLOW and live is False and rows == 2


async def test_a_slow_publish_is_publish():
    r = rig(games=1, delays={"publish": SLOW})
    tick(r, 0)
    await r.flush()
    waits, _ = slowest(r)
    assert waits["publish"] >= SLOW
    assert waits["db"] < QUIET and waits["stamp_wait"] < QUIET


async def test_a_runner_stall_lands_in_no_field():
    """The CI failure (integrator 2001Z): a loaded runner stalled the process
    ~0.3 s inside a seam nothing was injected into, and `db` read 0.31 s. The
    loop clock does not move while the process is stalled, so the injected
    publish still reads SLOW and the stalled db seam still reads zero."""
    assert isinstance(asyncio.get_running_loop(), _VirtualClockLoop)
    r = rig(games=1, delays={"publish": SLOW}, on_commit=lambda: time.sleep(0.3))
    tick(r, 0)
    await r.flush()
    waits, _ = slowest(r)
    assert waits["db"] < QUIET and waits["stamp_wait"] < QUIET
    assert waits["publish"] == pytest.approx(SLOW)


async def test_joining_a_held_refresh_is_stamp_wait():
    """The second flush's game is the one the first flush's refresh holds (the
    same-event fence). #10090: a periodic flush leaves its cohort buffered and
    waits for nothing; the final drain joins it, and that wait is its own
    stamp_wait, on its clock."""
    r = rig(games=1, delays={"stamp": SLOW})
    tick(r, 0)
    await r.flush()
    first, _ = slowest(r)
    assert first["stamp_wait"] < QUIET  # it started the refresh, did not wait
    r.timings.reset()
    tick(r, 0)
    await r.flush()
    waits, _ = slowest(r)
    assert waits["stamp_wait"] < QUIET and waits["db"] < QUIET
    assert r.stats["stamp_fenced"] == 2 and set(r.buffer) == {0, 1}
    r.timings.reset()
    await r.flush(final_drain=True)
    waits, _ = slowest(r)
    assert waits["stamp_wait"] >= SLOW - QUIET
    assert waits["publish"] < QUIET and not r.buffer
    await settle(r)


async def test_an_empty_flush_running_owed_stamps_inline_is_stamp_wait():
    r = rig(delays={"pending": SLOW})
    await r.flush()
    waits, phase = slowest(r)
    assert waits["stamp_wait"] >= SLOW and phase is None
    assert "db_phase=-" in r.timings.line()


@pytest.mark.parametrize("commits,named", [
    ((SLOW, 0.0), "live"),     # the live game is planned first
    ((0.0, SLOW), "nonlive"),
])
async def test_the_slowest_phase_is_named_live_or_nonlive_with_its_rows(commits, named):
    r = rig(games=2, live={5001}, commits=commits)
    tick(r, 0, 1)
    await r.flush()
    waits, (phase_s, _, rows) = slowest(r)
    assert rows == 2 and phase_s >= SLOW and waits["db"] >= SLOW
    assert waits["db"] - phase_s < QUIET  # the other phase was quick
    assert f"/{named}/2 db.set_lock=" in r.timings.line()


# ------------------------------- a stamp the flush did not wait for ----


async def test_a_refresh_outliving_its_flush_is_in_no_flushs_waits():
    """CONTROL. Flush 1 starts a slow refresh and returns; flush 2 writes a
    different game, which joins the running refresh without waiting. The old
    `stamp` bucket books the refresh on flush 2 (whichever flush ends after
    it); `slowest` books it on neither, because neither awaited it."""
    r = rig(games=2, delays={"stamp": SLOW})
    tick(r, 0)
    await r.flush()
    await settle(r)  # the refresh ends between the two flushes
    r.timings.reset()
    tick(r, 1)
    started = _now()
    await r.flush()
    assert _now() - started < QUIET
    waits, _ = slowest(r)
    assert waits["stamp_wait"] < QUIET
    assert r.timings.spent["stamp"] >= SLOW  # the old bucket: not this flush's
    await settle(r)


# ------------------------------------------------ minute continuity ----


async def test_a_minute_reset_mid_flush_keeps_its_waits_together():
    """The stats line fires between the flush's two phases: the new minute's
    `slowest` carries the whole flush, both phases' db time included."""
    holder = {}

    def on_commit():
        if not holder.get("reset"):
            holder["reset"] = True
            holder["r"].timings.reset()

    r = rig(games=2, delays={"commit": SLOW}, on_commit=on_commit)
    holder["r"] = r
    tick(r, 0, 1)
    await r.flush()
    assert holder["reset"] and r.timings.flushes == 1
    waits, (phase_s, _, _) = slowest(r)
    assert waits["db"] >= 2 * SLOW and phase_s >= SLOW
    await settle(r)


def test_the_unit_shape_and_longest_selection():
    t = _FlushTimings()
    assert t.line().endswith(" slowest -")

    async def run():
        async with t.waited("db", rows=12, live=True):
            await asyncio.sleep(0)
    asyncio.run(run())
    t.waiting["db"] = 1.25  # fixed numbers for the exact format
    t.waiting["stamp_wait"] = 0.5
    t.waiting_phase = (1.25, True, 12)
    t.flushed(2.0)
    t.waiting["publish"] = 0.75  # a shorter flush later in the minute
    t.flushed(1.0)
    assert t.line() == (
        "flush n=2 total=3.0s max=2.0s phases=0 save=0.0s rank_commit=3.0s "
        "publish=0.0s stamp=0.0s slowest db=1.25s publish=0.00s "
        "stamp_wait=0.50s db_phase=1.25s/live/12 db.set_lock=0.00s "
        "db.save=0.00s db.rerank=0.00s db.unknown=1.25s"
    )
    t.reset()
    assert t.line().endswith(" slowest -")
    t.waiting["publish"] = 0.25
    t.reset()  # mid-flush: the in-flight waits stay with their flush
    t.flushed(0.5)
    assert "slowest db=0.00s publish=0.25s stamp_wait=0.00s db_phase=-" in t.line()


async def test_untimed_owner_waits_nothing():
    prices = _KalshiPriceOwner()
    async with prices.waited("db", rows=1, live=False):
        pass


# --------------------------------------------- inside db, nested ----


@pytest.mark.parametrize("seam,named", [
    ("set_lock", "set_lock"),  # the first execute: lazy checkout lands here
    ("write", "save"),
    ("rerank", "rerank"),
    ("commit", "unknown"),     # never named commit: it is what is left
    ("prepare", "unknown"),    # an eager enter is not the first execute
])
async def test_each_db_seam_lands_in_its_nested_span_and_db_stays_whole(seam, named):
    r = rig(games=1, delays={seam: SLOW})
    tick(r, 0)
    assert await r.flush() is True
    waits, _ = slowest(r)
    inside = r.timings.slowest_db
    line = r.timings.line()
    assert waits["db"] >= SLOW  # db is inclusive: the parent still carries it
    assert waits["publish"] < QUIET and waits["stamp_wait"] < QUIET
    for other in ("set_lock", "save", "rerank"):
        if other == named:
            assert inside[other] >= SLOW
            assert inside[other] <= waits["db"]
        else:
            assert inside[other] < QUIET
    unknown = float(line.split("db.unknown=")[1].rstrip("s"))
    if named == "unknown":
        assert unknown >= SLOW - 0.01
    else:
        assert unknown < QUIET
    # Nested, never summed with their parent: the trio never exceeds the flush.
    assert sum(waits.values()) <= r.timings.longest + 0.01


async def test_nested_spans_sum_across_the_flushs_phases_like_db():
    r = rig(games=2, delays={"write": SLOW / 2})
    tick(r, 0, 1)
    await r.flush()
    waits, (phase_s, _, _) = slowest(r)
    inside = r.timings.slowest_db
    assert inside["save"] >= 4 * SLOW / 2  # four rows, two phases
    assert inside["save"] <= waits["db"] and phase_s < waits["db"]
    assert r.timings.spent["save"] == pytest.approx(inside["save"])  # same span


async def test_nested_spans_belong_to_the_longest_flush_only():
    r = rig(games=1, delays={"rerank": SLOW})
    tick(r, 0)
    await r.flush()
    r.delays["rerank"] = 0.0
    tick(r, 0)
    await r.flush()  # quicker: not the minute's slowest
    assert r.timings.flushes == 2
    assert r.timings.slowest_db["rerank"] >= SLOW
    await settle(r)


async def test_a_lock_timeout_in_the_write_still_books_its_nested_time():
    """The phase rolls back and its prices stay buffered; the time it spent
    is still that flush's db and its save, so a lock-wait flush is visible."""

    class LockTimeout(Exception):
        sqlstate = "55P03"

    r = rig(games=1)
    tick(r, 0)

    async def slow_then_refused(*_a, **_k):
        await asyncio.sleep(SLOW)
        raise LockTimeout("canceling statement due to lock timeout")
        yield  # pragma: no cover

    r.prices.pipeline = SimpleNamespace(iter_phase=slow_then_refused)
    await r.flush()
    waits, _ = slowest(r)
    assert waits["db"] >= SLOW and r.timings.slowest_db["save"] >= SLOW
    assert set(r.buffer) == {0, 1}  # retained for the next flush


def test_nested_waits_stay_with_their_flush_across_a_minute_reset():
    t = _FlushTimings()
    t.within_db("save", 0.5)
    t.waiting["db"] = 0.75
    t.reset()  # mid-flush
    t.flushed(1.0)
    assert t.slowest_db["save"] == 0.5
    assert t.line().endswith(
        "db.set_lock=0.00s db.save=0.50s db.rerank=0.00s db.unknown=0.25s"
    )


def test_a_shorter_flush_never_adds_into_the_slowest_nested_split():
    t = _FlushTimings()
    t.within_db("save", 0.5)
    t.flushed(2.0)
    t.within_db("save", 0.25)  # a shorter flush later in the minute
    t.flushed(1.0)
    assert t.slowest_db == {"set_lock": 0.0, "save": 0.5, "rerank": 0.0}


async def test_a_nested_span_never_swallows_the_error_it_times():
    t = _FlushTimings()
    with pytest.raises(RuntimeError):
        async with t.waited("rerank"):
            raise RuntimeError("the re-rank failed")
    assert t.waiting_db["rerank"] >= 0.0 and t.waiting["db"] == 0.0
