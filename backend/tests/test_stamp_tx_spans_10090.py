"""#10090: the venue minute lines say where the STAMP time went.

Speed's PM `game_flush` readout (v5996): the game loop busy ~60 s a minute,
`stamp=` ~41-53 s of it at ~0.16-0.18 s per stamped event. `stamp=` was one
number. `StampSpans` splits every `_refresh_batch` transaction into slot,
read, compute, write, commit and publish, plus whether the loop was busy or
idle while the stamp awaited, so a trial of `FRESH_STAMP_WORKERS` can tell a
database-wait-bound stamp (more workers help) from a CPU-bound one (they
won't). These drive the REAL `_refresh_batch` on a fake session and clock.
"""

import ast
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as lbr
from app.tasks import polymarket_ws as pm
from app.tasks import ws_consumer_sessions as wcs
from tests.test_live_blend_refresh import (
    NormalRecoverySession, _RecordingSession, _event_and_market,
    _one_event_refresher, is_normal_recovery_owner,
)

BACKEND = Path(__file__).resolve().parents[1]

# Each stage advances the fake clock by its own power of two, so every bucket
# sum below is exact and a stage landing in the wrong bucket cannot cancel out.
SLOT, READ, COMPUTE, WRITE, COMMIT, PUBLISH = 1 / 32, 0.5, 1.0, 0.25, 0.125, 1 / 16


class Clock:
    def __init__(self):
        self.t = 100.0
        self.cpu = 10.0
        #: True: the loop thread was busy the whole time (CPU moves with wall).
        self.saturated = False

    def advance(self, seconds, *, own_cpu=False):
        self.t += seconds
        if own_cpu or self.saturated:
            self.cpu += seconds


def rig(monkeypatch, *, read_fails=False, pool_full=False):
    clock = Clock()
    monkeypatch.setattr(lbr, "_stamp_span_clock", lambda: clock.t)
    monkeypatch.setattr(lbr, "_stamp_span_cpu", lambda: clock.cpu)
    event, market = _event_and_market()
    returned = {"polymarket": {"value": 0.9, "updated_at": "2026-10-31T04:00:00+00:00"}}

    class Session(_RecordingSession):
        checked_out = False

        async def execute(self, statement, *args, **kwargs):
            if not self.checked_out:
                # The pool hands the connection over at the first statement.
                self.checked_out = True
                clock.advance(1 / 64)
                wcs._probe_checked_out()
            if isinstance(statement, Update):
                clock.advance(WRITE)
            return await super().execute(statement, *args, **kwargs)

    session = Session([(market, event)], [], returned)
    r, published = _one_event_refresher(monkeypatch, session, min_refresh_interval_s=0)
    r._last_snapshot_at = {1: 10**12}  # no chart point owed: one UPDATE only

    def compute(group, home, away, **_kwargs):
        clock.advance(COMPUTE, own_cpu=True)
        return SimpleNamespace(
            home_probability=0.9, away_probability=None, draw_probability=None,
            eligibility=None,
        )

    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", compute)

    pool = SimpleNamespace(
        checkedout=lambda: 5, size=lambda: 5 if pool_full else 7, _max_overflow=0,
    )
    engine = SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))

    @asynccontextmanager
    async def factory():
        if is_normal_recovery_owner(r):
            yield NormalRecoverySession()
            return
        clock.advance(SLOT)
        token = wcs._SESSION_ENGINE.set(engine)
        try:
            yield session
            clock.advance(COMMIT)  # COMMIT and close
        finally:
            wcs._SESSION_ENGINE.reset(token)

    real_read = r._read_groups

    async def read(session, event_ids, **kwargs):
        if read_fails:
            clock.advance(READ)
            raise RuntimeError("the read failed")
        grouped = await real_read(session, event_ids, **kwargs)  # checkout first
        clock.advance(READ)
        return grouped

    async def publish(frames):
        clock.advance(PUBLISH)
        published.extend(frames)

    r._session_factory = factory
    r._read_groups = read
    r._publish = publish
    return SimpleNamespace(r=r, clock=clock, published=published, session=session)


@pytest.mark.asyncio
async def test_one_stamp_lands_in_its_own_buckets(monkeypatch):
    x = rig(monkeypatch)
    await x.r._refresh_batch([1], 1000.0)
    assert x.r._dispositions[1][0] == "stamped" and len(x.published) == 1
    s = x.r.stamp_spans
    assert (s.transactions, s.events, s.prepared) == (1, 1, 0)
    assert s.spent == {
        "slot": SLOT, "read": READ + 1 / 64, "compute": COMPUTE, "write": WRITE,
        "commit": COMMIT, "publish": PUBLISH,
    }
    assert s.checkout == pytest.approx(1 / 64)  # nested in `read`, not added
    assert (s.pool_full, s.probed) == (0, 1)
    assert (s.slots_max, s.slots_seen, s.slot_full) == (1, 1, 0)
    # An idle loop: every awaited second was spent waiting on the database.
    awaited = SLOT + READ + 1 / 64 + WRITE + COMMIT + PUBLISH
    assert (s.busy, s.idle) == (0.0, pytest.approx(awaited))


@pytest.mark.asyncio
async def test_a_saturated_loop_reads_as_busy_not_idle(monkeypatch):
    x = rig(monkeypatch)
    x.clock.saturated = True
    await x.r._refresh_batch([1], 1000.0)
    s = x.r.stamp_spans
    awaited = SLOT + READ + 1 / 64 + WRITE + COMMIT + PUBLISH
    assert s.spent["compute"] == COMPUTE
    assert (s.busy, s.idle) == (pytest.approx(awaited), 0.0)


@pytest.mark.asyncio
async def test_a_full_pool_at_the_body_start_is_counted(monkeypatch):
    x = rig(monkeypatch, pool_full=True)
    await x.r._refresh_batch([1], 1000.0)
    assert (x.r.stamp_spans.pool_full, x.r.stamp_spans.probed) == (1, 1)


@pytest.mark.asyncio
async def test_a_failed_transaction_is_still_counted_and_the_failure_propagates(monkeypatch):
    x = rig(monkeypatch, read_fails=True)
    with pytest.raises(RuntimeError, match="the read failed"):
        await x.r._refresh_batch([1], 1000.0)
    s = x.r.stamp_spans
    assert (s.transactions, s.events) == (1, 1)
    assert s.spent == {
        "slot": SLOT, "read": READ, "compute": 0.0, "write": 0.0,
        "commit": 0.0, "publish": 0.0,
    }


@pytest.mark.asyncio
async def test_waiting_for_a_slot_is_slot_time_and_counted_full(monkeypatch):
    x = rig(monkeypatch)
    slots = x.r._session_slots
    for _ in range(lbr.FRESH_STAMP_WORKERS):
        await slots.acquire()
    stamp = asyncio.create_task(x.r._refresh_batch([1], 1000.0))
    await asyncio.sleep(0)
    x.clock.advance(2.0)  # every slot held elsewhere for two seconds
    for _ in range(lbr.FRESH_STAMP_WORKERS - 1):
        slots.release()
    await stamp
    s = x.r.stamp_spans
    assert s.slot_full == 1
    assert s.spent["slot"] == 2.0 + SLOT
    # Its own slot plus the one still held elsewhere.
    assert s.slots_max == 2
    slots.release()


@pytest.mark.asyncio
async def test_a_prepared_read_adds_its_slot_and_read_but_is_no_transaction(monkeypatch):
    x = rig(monkeypatch)
    grouped = await x.r._prepare_groups([1])
    assert 1 in grouped
    s = x.r.stamp_spans
    assert (s.transactions, s.prepared) == (0, 1)
    assert s.spent["slot"] == SLOT and s.spent["read"] == READ + 1 / 64


@pytest.mark.asyncio
async def test_the_minute_line_and_its_reset(monkeypatch):
    x = rig(monkeypatch)
    await x.r._refresh_batch([1], 1000.0)
    line = x.r.stamp_spans.line()
    assert line == (
        "stamp_tx=1 events=1 prepared=0 stamp_slot=0.0s stamp_read=0.5s "
        "stamp_compute=1.0s stamp_write=0.2s stamp_commit=0.1s "
        "stamp_publish=0.1s stamp_checkout=0.0s pool_full=0/1 "
        f"loop_busy=0.0s loop_idle=1.0s workers={lbr.FRESH_STAMP_WORKERS} "
        "slots_max=1 slots_mean=1.0 slot_full=0"
    )
    # The existing `stamp=` parsers never read a sub-span.
    assert "stamp=" not in line and " n=" not in line
    x.r.stamp_spans.reset()
    assert x.r.stamp_spans.line().startswith("stamp_tx=0 events=0 prepared=0 stamp_slot=0.0s")
    assert x.r.stamp_spans.line().endswith("slots_max=0 slots_mean=0.0 slot_full=0")


def test_the_pm_line_carries_the_segment_after_game_flush(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger=pm.logger.name):
        pm._log_stats_line(
            {"price_updates": 1, "trade_updates": 0, "resolutions": 0, "errors": 0,
             "repeats_skipped": 7},
            {}, {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0},
            game_flush="game_flush n=1 total=1.0s max=1.0s phases=1 save=0.1s "
            "rank_commit=0.1s publish=0.1s stamp=0.7s",
            stamp_tx="stamp_tx=3 events=4 prepared=0 stamp_slot=0.1s",
        )
    (line,) = [r.getMessage() for r in caplog.records if "Polymarket WS: " in r.getMessage()]
    assert "stamp=0.7s | stamp_tx=3 events=4 prepared=0 stamp_slot=0.1s | held withdrawn=0" in line
    assert line.endswith("repeats_skipped=7")


def _kalshi_stats_call():
    tree = ast.parse((BACKEND / "app/tasks/kalshi_ws.py").read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call) and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith("Kalshi WS: %d updates")
        ):
            return node
    raise AssertionError("the Kalshi minute line was not found")


def test_the_kalshi_line_ends_with_the_segment_and_its_arity_holds():
    call = _kalshi_stats_call()
    fmt = call.args[0].value
    assert fmt.endswith("skipped_locked=%d | %s")
    placeholders = fmt.count("%d") + fmt.count("%s")
    assert placeholders == len(call.args) - 1
    assert "stamp_spans.line()" in ast.unparse(call.args[-1])
