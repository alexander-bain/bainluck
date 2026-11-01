"""#10090: the Polymarket minute line says where the GAME flush time went.

Kalshi's minute line carries `flush n= total= max= phases= save= rank_commit=
publish= stamp=`; that is what showed its flush loop was saturated. PM's line
had none of it, so its 4.8x slower median on the same event had no stage to
aim at. These drive the REAL `_flush_prices` / `write_chunk` (the stage-trace
rig), the real stamp owner and market sender, and the real `_log_stats_line`.
Log only: every span here is the existing await, unchanged.
"""

import asyncio
import contextvars
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks import polymarket_ws as pm
from tests.test_pm_stage_trace_10090 import flush, trace_rig

TASK_STATS = {"price_updates": 3, "trade_updates": 0, "resolutions": 0, "errors": 0,
              "price_rows_skipped_locked": 5, "repeats_skipped": 4321}
BLEND = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}


def logged_line(caplog, **kwargs):
    with caplog.at_level(logging.INFO, logger=pm.logger.name):
        pm._log_stats_line(dict(TASK_STATS), {}, dict(BLEND), **kwargs)
    (line,) = [r.getMessage() for r in caplog.records if "Polymarket WS: " in r.getMessage()]
    return line


def test_the_line_names_kalshis_fields_for_the_game_flush():
    t = pm._PMGameFlushTimings()
    t.add("save", 1.25, phase=True)
    t.add("save", 0.5, phase=True)
    t.add("publish", 0.25)
    t.add("stamp", 0.5)
    t.flushed(3.0)
    t.flushed(1.0)
    t.note_sizes(8120, 37)
    t.note_sizes(7990, 52)
    assert t.line() == (
        "game_flush n=2 total=4.0s max=3.0s phases=2 save=1.8s rank_commit=1.5s "
        "publish=0.2s stamp=0.5s buf_max=8120 batch_max=52"
    )
    t.reset()
    assert t.line().startswith("game_flush n=0 total=0.0s max=0.0s phases=0 ")
    assert t.line().endswith(" buf_max=0 batch_max=0")


def test_every_game_flush_reports_its_buffer_and_batch_sizes():
    """#10090 CPU: the flush copies the whole price buffer and walks it four
    times a second; the minute line names the largest of each."""
    import inspect

    source = inspect.getsource(pm._run_polymarket_ws_consumer)
    assert "timings.note_sizes(len(price_buffer), len(batch))" in source


def test_the_segment_sits_before_held_and_repeats_skipped_still_ends_the_line(caplog):
    line = logged_line(
        caplog, game_flush="game_flush n=7 total=6.0s max=2.5s phases=9 save=1.0s "
        "rank_commit=4.0s publish=0.5s stamp=0.5s",
    )
    assert "| game_flush n=7 total=6.0s max=2.5s phases=9 save=1.0s rank_commit=4.0s " \
        "publish=0.5s stamp=0.5s | stamp_tx - | held withdrawn=0 " in line
    # The existing minute-line parsers keep reading what they read.
    assert re.search(r"skipped_locked=(\d+) repeats_skipped=(\d+)$", line).groups() == (
        "5", "4321",
    )
    assert line.index("outside_wide_book=0 | game_flush") < line.index("stamp_wait_s=")


def test_a_caller_without_timings_prints_a_dash(caplog):
    line = logged_line(caplog)
    assert "outside_wide_book=0 | game_flush - | stamp_tx - | held withdrawn=0" in line
    assert line.endswith("repeats_skipped=4321")


def test_a_span_counts_only_inside_a_game_flush_and_only_when_on(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(pm, "_pm_flush_clock", lambda: clock[0])
    timings = pm._PMGameFlushTimings()
    with pm._pm_game_flush_span("save", phase=True):  # no game flush: nothing
        clock[0] += 5.0
    token = pm._PM_GAME_FLUSH_TIMINGS.set(timings)
    try:
        with pm._pm_game_flush_span("save", phase=True):
            clock[0] += 0.75
        with pm._pm_game_flush_span("save", phase=True, on=False):  # a side chunk
            clock[0] += 9.0
        with pytest.raises(RuntimeError):
            with pm._pm_game_flush_span("publish"):
                clock[0] += 0.25
                raise RuntimeError("the body's own failure still propagates")
    finally:
        pm._PM_GAME_FLUSH_TIMINGS.reset(token)
    timings.flushed(2.0)
    assert timings.spent == {"save": 0.75, "publish": 0.25, "stamp": 0.0}
    assert timings.phases == 1


@pytest.mark.asyncio
async def test_a_stamp_task_a_game_flush_starts_is_timed_start_to_end(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(pm, "_pm_flush_clock", lambda: clock[0])
    timings = pm._PMGameFlushTimings()
    release = asyncio.Event()

    async def stamp():
        await release.wait()

    owner = pm._PMStampOwner(SimpleNamespace())
    owner.task = asyncio.create_task(stamp())  # outside a game flush: untimed
    token = pm._PM_GAME_FLUSH_TIMINGS.set(timings)
    try:
        timed = asyncio.create_task(stamp())
        owner.task = timed
    finally:
        pm._PM_GAME_FLUSH_TIMINGS.reset(token)
    clock[0] = 1.5  # the stamp outlives its flush; its time is still its own
    release.set()
    await timed
    await asyncio.sleep(0)  # done callbacks
    timings.flushed(0.5)
    assert timings.spent["stamp"] == 1.5


@pytest.mark.asyncio
async def test_the_market_sender_a_game_flush_starts_is_timed(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(pm, "_pm_flush_clock", lambda: clock[0])
    sent = []

    class Refresher:
        async def publish_market_frames(self, changes):
            clock[0] += 0.4
            sent.append(list(changes))

    timings = pm._PMGameFlushTimings()
    publisher = pm.PMWithdrawalMarketPublisher()
    publisher.pending = [{"market_id": 1}]
    publisher.start(Refresher())  # a side loop's sender: untimed
    await publisher.join()
    publisher.pending = [{"market_id": 2}]
    token = pm._PM_GAME_FLUSH_TIMINGS.set(timings)
    try:
        publisher.start(Refresher())
    finally:
        pm._PM_GAME_FLUSH_TIMINGS.reset(token)
    await publisher.join()
    timings.flushed(1.0)
    assert sent == [[{"market_id": 1}], [{"market_id": 2}]]
    assert timings.spent["publish"] == pytest.approx(0.4)


async def timed_flush(t, monkeypatch, timings):
    monkeypatch.setattr(pm, "_pm_flush_clock", lambda: t.clock[0])
    context = contextvars.copy_context()
    context.run(pm._PM_GAME_FLUSH_TIMINGS.set, timings)
    task = asyncio.get_running_loop().create_task(flush(t, started=500.0), context=context)
    return await task


@pytest.mark.asyncio
async def test_a_slow_price_statement_reads_as_save_on_the_real_game_flush(monkeypatch):
    t = trace_rig(monkeypatch, slow_write=1.0)
    timings = pm._PMGameFlushTimings()
    assert await timed_flush(t, monkeypatch, timings)
    timings.flushed(1.0)
    assert timings.spent["save"] == 1.0 and timings.phases == 1
    assert timings.spent["stamp"] == 0.0


@pytest.mark.asyncio
async def test_a_slow_stamp_reads_as_stamp_not_save_on_the_real_game_flush(monkeypatch):
    t = trace_rig(monkeypatch, slow_stamp=1.0)
    timings = pm._PMGameFlushTimings()
    assert await timed_flush(t, monkeypatch, timings)
    timings.flushed(0.0)
    assert timings.spent["save"] == 0.0 and timings.phases == 1
    assert timings.spent["stamp"] == 1.0


@pytest.mark.asyncio
async def test_a_side_chunk_is_never_the_game_flushs_save(monkeypatch):
    # An open-catalog leg is not a game chunk (`game_chunk`): the bridged and
    # standalone writers inherit a game flush's context but not its `save`.
    t = trace_rig(monkeypatch, slow_write=1.0)
    t.p.ns["open_outcome_ids"] = {1}
    timings = pm._PMGameFlushTimings()
    monkeypatch.setattr(pm, "_pm_flush_clock", lambda: t.clock[0])
    token = pm._PM_GAME_FLUSH_TIMINGS.set(timings)
    try:
        await t.p.ns["write_chunk"]({1: 0.6, 2: 0.4})
    finally:
        pm._PM_GAME_FLUSH_TIMINGS.reset(token)
    timings.flushed(1.0)
    assert timings.spent["save"] == 0.0 and timings.phases == 0


@pytest.mark.asyncio
async def test_without_a_game_flush_the_real_flush_is_unchanged_and_untimed(monkeypatch):
    t = trace_rig(monkeypatch, slow_write=1.0)
    monkeypatch.setattr(pm, "_pm_flush_clock", lambda: t.clock[0])
    assert await flush(t, started=500.0)
    assert t.x.published == [1]
    assert pm._PM_GAME_FLUSH_TIMINGS.get() is None


def test_the_consumer_times_the_game_loop_and_logs_then_resets_each_minute():
    source = (Path(pm.__file__)).read_text()
    loop = source[source.index("    async def flush_loop():"):]
    loop = loop[:loop.index("    async def standalone_loop():")]
    assert "timed_game_flush, game_period" in loop
    timed = source[source.index("    async def timed_game_flush(flush_started):"):]
    timed = timed[:timed.index("    async def flush_loop():")]
    assert "_PM_GAME_FLUSH_TIMINGS.set(game_flush_timings)" in timed
    assert "return await flush_prices(flush_started)" in timed
    assert "game_flush_timings.flushed(_pm_flush_clock() - started)" in timed
    assert "_PM_GAME_FLUSH_TIMINGS.reset(token)" in timed
    stats = source[source.index("    async def stats_loop():"):]
    stats = stats[:stats.index("_report_liveness(")]
    assert "stats, ws_stats, blend, game_flush=game_flush_timings.line()," in stats
    assert stats.index("game_flush=game_flush_timings.line(),") < stats.index(
        "game_flush_timings.reset()")
    # #10090 stamp_tx: the refresher's stamp spans ride the same line and reset.
    assert '"stamp_tx": stamp_spans.line()' in stats
    assert "stamp_spans.reset()" in stats
    # The side loops stay off it.
    side = source[source.index("    async def standalone_loop():"):source.index(
        "    async def stats_loop():")]
    assert "timed_game_flush" not in side
