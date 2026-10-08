"""#10090 — the worker-ws heartbeat says how busy the shared event loop was.

Kalshi, Polymarket and the shadow arms share one asyncio loop (`main()`'s one
`gather`). A late wake on that loop is the wait every arm's await pays, and no
existing line measured it. These tests pin the arithmetic and prove on a real
loop that a sibling hogging it shows up in the heartbeat line — and that an
idle loop does not.
"""
import asyncio
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
    m = re.search(r"loop cpu=(\S+) lag p50=(\d+)ms p95=(\d+)ms max=(\d+)ms n=(\d+)$", line)
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
