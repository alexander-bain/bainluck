"""#10090 — the worker-ws heartbeat says how busy the shared event loop was.

Kalshi, Polymarket and the shadow arms share one asyncio loop (`main()`'s one
`gather`). A late wake on that loop is the wait every arm's await pays, and no
existing line measured it. These tests pin the arithmetic and prove on a real
loop that a sibling hogging it shows up in the heartbeat line — and that an
idle loop does not.
"""
import asyncio
import gc
import logging
import re
import time

import pytest

import run_kalshi_ws
from run_kalshi_ws import LoopLoad


class Clock:
    def __init__(self):
        self.wall = 100.0
        self.cpu = 10.0


def test_cpu_share_and_lag_percentiles_then_reset():
    c = Clock()
    load = LoopLoad(clock=lambda: c.wall, cpu=lambda: c.cpu)
    for lag in [0.001] * 18 + [0.050, 0.400]:
        load.sample(lag)
    load.sample(-0.002)  # a timer that fired a hair early is no lag, not negative
    c.wall += 120.0
    c.cpu += 90.0
    assert load.line() == "loop cpu=0.75 lag p50=1ms p95=50ms max=400ms n=21"
    # The next line covers only the next interval.
    c.wall += 60.0
    c.cpu += 66.0
    assert load.line() == "loop cpu=1.10 lag n=0"


def test_zero_wall_interval_does_not_divide_by_zero():
    c = Clock()
    load = LoopLoad(clock=lambda: c.wall, cpu=lambda: c.cpu)
    assert load.line() == "loop cpu=0.00 lag n=0"


async def _beat_lines(monkeypatch, caplog, sibling):
    monkeypatch.setattr(run_kalshi_ws, "HEARTBEAT_SECONDS", 0.6)
    monkeypatch.setattr(run_kalshi_ws, "LOOP_SAMPLE_SECONDS", 0.05)
    caplog.set_level(logging.INFO, logger="ws_runner")
    beat = asyncio.create_task(run_kalshi_ws.heartbeat())
    try:
        await sibling()
        for _ in range(40):
            if any("heartbeat" in r.getMessage() for r in caplog.records):
                break
            await asyncio.sleep(0.05)
    finally:
        beat.cancel()
        with pytest.raises(asyncio.CancelledError):
            await beat
    (line,) = [r.getMessage() for r in caplog.records if "heartbeat" in r.getMessage()][:1]
    m = re.search(r"loop cpu=(\S+) lag p50=(\d+)ms p95=(\d+)ms max=(\d+)ms n=(\d+) max_at=", line)
    assert m, line
    return float(m[1]), int(m[4]), int(m[5])


@pytest.mark.asyncio
async def test_a_sibling_hogging_the_loop_shows_in_the_heartbeat(monkeypatch, caplog):
    async def hog():
        await asyncio.sleep(0.1)
        end = time.perf_counter() + 0.3
        while time.perf_counter() < end:  # a CPU-bound stretch on the shared loop
            pass

    cpu, worst, n = await _beat_lines(monkeypatch, caplog, hog)
    assert worst >= 200, "the 300 ms stretch must surface as a late wake"
    assert cpu >= 0.3 and n >= 3


@pytest.mark.asyncio
async def test_control_an_idle_loop_reports_no_such_lag(monkeypatch, caplog):
    async def idle():
        await asyncio.sleep(0.1)

    cpu, worst, n = await _beat_lines(monkeypatch, caplog, idle)
    assert worst < 100 and cpu < 0.3 and n >= 3


# --- #10090: WHEN the worst late wake and the longest collection happened ---


class Clocks:
    def __init__(self):
        self.mono = 1000.0
        self.cpu = 10.0
        self.wall = 1792161300.0  # 2026-10-16 14:35:00Z


def _load(c):
    return LoopLoad(clock=lambda: c.mono, cpu=lambda: c.cpu, wall=lambda: c.wall + (c.mono - 1000.0))


def test_detail_times_the_worst_wake_and_the_longest_collection_and_their_overlap():
    c = Clocks()
    load = _load(c)
    load.sample(0.010, 1001.000, 1001.010)
    load.sample(0.651, 1002.101, 1002.752)  # the window's worst late wake
    load.sample(0.200, 1003.000, 1003.200)
    c.mono = 1002.200
    load.on_gc("start", {"generation": 0})
    c.mono = 1002.205
    load.on_gc("stop", {"generation": 0, "collected": 3})
    c.mono = 1002.300
    load.on_gc("start", {"generation": 2})
    c.mono = 1002.712
    load.on_gc("stop", {"generation": 2, "collected": 9})
    c.mono = 1010.0
    assert load.detail() == (
        "max_at=14:35:02.101-14:35:02.752Z gc2=1 gc_max=412ms gen=2 "
        "gc_at=14:35:02.300-14:35:02.712Z gc_overlap=412ms"
    )


def test_disjoint_maxima_report_zero_overlap_not_a_match():
    c = Clocks()
    load = _load(c)
    load.sample(0.651, 1002.101, 1002.752)
    c.mono = 1005.000
    load.on_gc("start", {"generation": 2})
    c.mono = 1005.300
    load.on_gc("stop", {"generation": 2})
    assert load.detail().endswith("gc_max=300ms gen=2 gc_at=14:35:05.000-14:35:05.300Z gc_overlap=0ms")


def test_no_collection_and_no_sample_windows_say_so():
    c = Clocks()
    load = _load(c)
    assert load.detail() == "max_at=- gc2=0 gc_max=-"
    load.sample(0.020, 1000.5, 1000.52)
    assert load.detail() == "max_at=14:35:00.500-14:35:00.520Z gc2=0 gc_max=-"
    load.on_gc("start", {"generation": 1})
    load.on_gc("stop", {"generation": 1})
    assert load.detail().startswith("max_at=14:35:00.500-14:35:00.520Z gc2=0 gc_max=0ms gen=1 ")


def test_line_resets_the_timing_window_but_a_collection_in_flight_still_closes():
    c = Clocks()
    load = _load(c)
    load.sample(0.3, 1001.0, 1001.3)
    load.on_gc("start", {"generation": 2})
    c.mono = 1001.1
    load.on_gc("stop", {"generation": 2})
    c.mono = 1001.2
    load.on_gc("start", {"generation": 2})  # still running when the line is written
    load.line()
    assert load.detail() == "max_at=- gc2=0 gc_max=-"
    c.mono = 1001.25
    load.on_gc("stop", {"generation": 2})  # counted in the window where it ended
    assert load.detail() == "max_at=- gc2=1 gc_max=50ms gen=2 gc_at=14:35:01.200-14:35:01.250Z"


def test_existing_line_fields_are_unchanged_by_the_timing_samples():
    c = Clocks()
    load = _load(c)
    for lag in [0.001] * 18 + [0.050, 0.400, -0.002]:
        load.sample(lag, c.mono, c.mono + lag)
    c.mono += 120.0
    c.cpu += 90.0
    assert load.line() == "loop cpu=0.75 lag p50=1ms p95=50ms max=400ms n=21"


def test_the_hook_keeps_no_info_and_never_raises():
    c = Clocks()
    load = _load(c)
    info = {"generation": 2}
    load.on_gc("start", info)
    load.on_gc("stop", info)
    assert all(v is not info for v in vars(load).values())
    load.on_gc("stop", None)  # unmatched stop: ignored
    load.on_gc("start", None)
    load.on_gc("stop", None)  # a malformed info cannot raise into the collector
    assert load.detail().startswith("max_at=- gc2=1 ")


@pytest.mark.asyncio
async def test_heartbeat_installs_exactly_one_hook_and_removes_it_on_cancel(monkeypatch, caplog):
    monkeypatch.setattr(run_kalshi_ws, "HEARTBEAT_SECONDS", 0.3)
    monkeypatch.setattr(run_kalshi_ws, "LOOP_SAMPLE_SECONDS", 0.05)
    caplog.set_level(logging.INFO, logger="ws_runner")
    before = list(gc.callbacks)
    for _ in range(2):  # a second lifetime must not accumulate hooks
        beat = asyncio.create_task(run_kalshi_ws.heartbeat())
        await asyncio.sleep(0.05)
        added = [cb for cb in gc.callbacks if cb not in before]
        assert len(added) == 1 and getattr(added[0], "__name__", "") == "on_gc"
        for _ in range(40):
            if any("heartbeat" in r.getMessage() for r in caplog.records):
                break
            await asyncio.sleep(0.05)
        gc.collect()  # a real collection while the hook is installed (test only)
        await asyncio.sleep(0.4)
        beat.cancel()
        with pytest.raises(asyncio.CancelledError):
            await beat
        assert gc.callbacks == before
    lines = [r.getMessage() for r in caplog.records if "heartbeat" in r.getMessage()]
    assert any(re.search(r"n=\d+ max_at=\S+Z gc2=[1-9]\d* gc_max=\d+ms gen=2 gc_at=\S+Z gc_overlap=\d+ms$", l) for l in lines), lines
