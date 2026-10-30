"""#10090: the PM venue process's low-rate stack sampler (`app/utils/loop_cpu_sampler.py`).

Real ITIMER_PROF / SIGPROF on the pytest main thread, the real fold and line.
No venue, DB or Redis. Every test that starts a sampler stops it and puts the
process's SIGPROF handler and timer back.
"""

import asyncio
import logging
import os
import selectors
import signal
import socket
import sys
import threading
import time

import pytest

import run_kalshi_ws as runner
from app.utils import loop_cpu_sampler as mod
from app.utils.loop_cpu_sampler import IDLE, LoopCpuSampler


@pytest.fixture
def restore_sigprof():
    previous = signal.getsignal(signal.SIGPROF)
    yield
    signal.setitimer(signal.ITIMER_PROF, 0)
    signal.signal(signal.SIGPROF, previous if previous is not None else signal.SIG_DFL)


def _on():
    return True


def hot_three():
    x = 0
    for i in range(30000):
        x += i * i
    return x


def hot_one():
    x = 0
    for i in range(10000):
        x += i * i
    return x


def _burn(seconds, *steps):
    end = time.process_time() + seconds
    while time.process_time() < end:
        for step in steps:
            step()


def _deep(depth, seconds, *steps):
    if depth:
        return _deep(depth - 1, seconds, *steps)
    return _burn(seconds, *steps)


def _names(counts):
    return {code.co_name: n for code, n in counts.items()}


def test_real_timer_charges_cpu_to_the_function_that_spent_it(restore_sigprof):
    """The rejected thread designs read the selector, not the hot path: this is
    the property that makes the line worth reading."""
    sampler = LoopCpuSampler(interval_s=0.002, enabled=_on).start(thread=False)
    assert sampler is not None
    try:
        _burn(1.0, hot_three, hot_one)
    finally:
        sampler.stop()
    counts = _names(sampler._window.self_counts)
    three, one = counts.get("hot_three", 0), counts.get("hot_one", 0)
    assert three + one >= 100, counts
    assert 0.6 <= three / (three + one) <= 0.9, counts  # 3:1 work, 0.75 expected
    assert signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0)


def test_sampler_costs_under_half_a_percent_at_10hz(restore_sigprof):
    """The cost bound at production's rate, on a deep stack."""
    sampler = LoopCpuSampler(enabled=_on).start(thread=False)
    try:
        cpu0 = time.process_time()
        _deep(80, 3.0, hot_three)
        spent = time.process_time() - cpu0
    finally:
        sampler.stop()
    w = sampler._window
    assert w.n >= 15, w.n  # ~10 per CPU second
    assert w.handler_cpu / spent < 0.005, (w.handler_cpu, spent, w.n)
    # The thread's share: one line per window, built off the loop.
    t0 = time.thread_time()
    sampler.line()
    assert time.thread_time() - t0 < 0.05


def test_selector_wait_is_counted_as_select_not_a_hot_function():
    sampler = LoopCpuSampler(enabled=_on)
    selector = selectors.DefaultSelector()
    wake_r, wake_w = socket.socketpair()
    selector.register(wake_r, selectors.EVENT_READ)
    thread = threading.Thread(target=lambda: selector.select(timeout=5.0), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            frame = sys._current_frames()[thread.ident]
            if frame.f_code.co_name == "select":
                break
            time.sleep(0.01)
        sampler.fold(frame)
        del frame
    finally:
        wake_w.send(b"x")
        thread.join(5)
        selector.close()
        wake_r.close()
        wake_w.close()
    w = sampler._window
    assert w.n == 1 and w.stage_counts == {IDLE: 1} and not w.self_counts


def _compiled(filename, source, scope):
    exec(compile(source, filename, "exec"), scope)
    return scope


def test_stage_is_the_outermost_match_and_marks_refresher_code_inside_it():
    sampler = LoopCpuSampler(enabled=_on)
    scope = {"sys": sys, "sampler": sampler}
    _compiled("/app/backend/app/tasks/live_blend_refresh.py",
              "def refresh():\n    sampler.fold(sys._getframe())\n", scope)
    _compiled("/app/backend/app/tasks/polymarket_ws.py",
              "def flush_prices():\n    refresh()\n"
              "def handle_price():\n    sampler.fold(sys._getframe())\n"
              "def helper():\n    sampler.fold(sys._getframe())\n", scope)
    scope["flush_prices"]()
    scope["handle_price"]()
    scope["refresh"]()
    scope["helper"]()
    assert sampler._window.stage_counts == {
        "flush+refresher": 1, "receive": 1, "refresher": 1, "other": 1,
    }
    line = sampler.line()
    assert "app/tasks/live_blend_refresh.py:refresh:1=" in line  # short path, def line
    assert "stages=[" in line and "flush+refresher=25.0" in line


def test_line_is_capped_at_8kb_names_every_field_and_resets():
    sampler = LoopCpuSampler(enabled=_on)
    scope = {"sys": sys, "sampler": sampler}
    source = "".join(
        f"def f{i}_{'x' * 200}():\n    sampler.fold(sys._getframe())\n" for i in range(400)
    )
    _compiled("/app/backend/app/tasks/polymarket_ws.py", source, scope)
    for i in range(400):
        for _ in range(1 + i % 7):
            scope[f"f{i}_{'x' * 200}"]()
    line = sampler.line(thread_cpu=0.0)
    assert len(line.encode()) <= mod.MAX_LINE_BYTES
    for field in ("pm-cpu-sample n=", " win=", " loop_cpu=", " proc_cpu=", " self_cpu=",
                  " err=0", " stages=[", " top_self=[", " top_cum=[", " top_line=["):
        assert field in line, field
    assert sampler._window.n == 0 and not sampler._window.self_counts


def test_disabled_off_main_or_taken_installs_nothing(restore_sigprof):
    before = signal.getsignal(signal.SIGPROF)
    assert LoopCpuSampler(enabled=lambda: False).start() is None
    assert LoopCpuSampler(enabled=lambda: 1 / 0).start() is None  # a raising switch is off
    assert signal.getsignal(signal.SIGPROF) is before

    result = []
    thread = threading.Thread(target=lambda: result.append(LoopCpuSampler(enabled=_on).start()))
    thread.start()
    thread.join(5)
    assert result == [None] and signal.getsignal(signal.SIGPROF) is before

    def theirs(signum, frame):
        pass

    signal.signal(signal.SIGPROF, theirs)
    assert LoopCpuSampler(enabled=_on).start() is None
    assert signal.getsignal(signal.SIGPROF) is theirs
    assert signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0)


def test_stopped_handler_stays_installed_inert_and_a_new_sampler_takes_it_over(restore_sigprof):
    first = LoopCpuSampler(interval_s=0.002, enabled=_on).start(thread=False)
    first.stop()
    n = first._window.n
    assert signal.getsignal(signal.SIGPROF) == first._on_signal  # never back to SIG_DFL
    assert signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0)
    first._on_signal(signal.SIGPROF, sys._getframe())
    assert first._window.n == n and signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0)

    second = LoopCpuSampler(interval_s=0.002, enabled=_on).start(thread=False)
    assert second is not None
    second.stop()


def test_fold_and_handler_never_raise():
    sampler = LoopCpuSampler(enabled=_on)
    sampler.fold(object())  # no f_code
    assert sampler._window.errors == 1
    sampler._active = True
    sampler._arm = lambda: 1 / 0
    sampler._on_signal(signal.SIGPROF, object())
    sampler._on_signal(signal.SIGPROF, None)


def test_thread_logs_one_line_per_window_and_reads_the_switch_at_each_boundary(restore_sigprof):
    lines, switch = [], {"on": True}

    class Capture(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    log = logging.getLogger("test_loop_cpu_sampler_10090")
    log.addHandler(Capture())
    log.setLevel(logging.INFO)
    sampler = LoopCpuSampler(interval_s=0.002, window_s=0.4, enabled=lambda: switch["on"], log=log)
    assert sampler.start() is sampler
    try:
        deadline = time.monotonic() + 10
        while len(lines) < 2 and time.monotonic() < deadline:
            _burn(0.05, hot_three)
        assert len(lines) >= 2, lines
        assert all(line.startswith("pm-cpu-sample n=") for line in lines)
        assert "hot_three" in lines[-1]
        switch["on"] = False
        deadline = time.monotonic() + 10
        while signal.getitimer(signal.ITIMER_PROF) != (0.0, 0.0) and time.monotonic() < deadline:
            _burn(0.05, hot_three)
        assert signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0)  # disarmed at the boundary
        _burn(0.3, hot_three)
        logged = len(lines)
        time.sleep(1.0)
        assert len(lines) == logged  # off: no lines
        switch["on"] = True
        deadline = time.monotonic() + 10
        while len(lines) == logged and time.monotonic() < deadline:
            _burn(0.05, hot_three)
        assert len(lines) > logged  # re-armed at a later boundary
    finally:
        sampler.stop(join_timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("venue", ["kalshi", "polymarket"])
@pytest.mark.parametrize("fails", [False, True])
async def test_only_the_polymarket_venue_starts_it_and_a_failure_never_stops_the_venue(
    monkeypatch, venue, fails,
):
    events = []

    class Fake:
        def __init__(self, **kwargs):
            pass

        def start(self):
            if fails:
                raise RuntimeError("no sampler")
            events.append("start")
            return self

        def stop(self, join_timeout=None):
            events.append("stop")

    monkeypatch.setattr(mod, "LoopCpuSampler", Fake)
    callbacks = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda sig, cb: callbacks.update({sig: cb}))
    monkeypatch.setattr(loop, "remove_signal_handler", lambda sig: callbacks.pop(sig))
    running = asyncio.Event()

    async def held():
        running.set()
        await asyncio.Event().wait()

    for name in ("kalshi", "polymarket"):
        monkeypatch.setattr(runner, f"run_{name}", held)
        monkeypatch.setattr(runner, f"run_{name}_shadow", held)
    monkeypatch.setattr(runner, "heartbeat", lambda arms: held())
    task = asyncio.create_task(runner.run_venue(venue))
    await asyncio.wait_for(running.wait(), 1)
    callbacks[signal.SIGTERM]()
    await asyncio.wait_for(task, 1)
    expected = ["start", "stop"] if venue == "polymarket" and not fails else []
    assert events == expected


def test_each_rearm_is_jittered_so_samples_cannot_alias_with_the_flush_cadence(monkeypatch):
    armed = []
    monkeypatch.setattr(mod.signal, "setitimer", lambda which, seconds: armed.append((which, seconds)))
    sampler = LoopCpuSampler(enabled=_on)
    for _ in range(200):
        sampler._arm()
    seconds = [s for _, s in armed]
    assert {w for w, _ in armed} == {signal.ITIMER_PROF}
    assert 0.05 <= min(seconds) < 0.06 and 0.14 < max(seconds) <= 0.15
    assert len(set(seconds)) > 150


@pytest.mark.parametrize("path, short", [
    ("/app/app/tasks/polymarket_ws.py", "app/tasks/polymarket_ws.py"),
    ("/tmp/wt/backend/app/tasks/polymarket_ws.py", "app/tasks/polymarket_ws.py"),
    ("/app/.heroku/python/lib/python3.11/site-packages/sqlalchemy/sql/base.py", "sqlalchemy/sql/base.py"),
    ("/app/.heroku/python/lib/python3.11/asyncio/base_events.py", "asyncio/base_events.py"),
    ("<frozen _collections_abc>", "<frozen _collections_abc>"),
])
def test_paths_are_short_on_heroku_and_locally(path, short):
    assert mod.short_path(path) == short


def syscall_decoy():
    for _ in range(400):
        os.getppid()


def _cpu_per_call(fn, calls=30):
    t0 = time.thread_time()
    for _ in range(calls):
        fn()
    return (time.thread_time() - t0) / calls


@pytest.mark.parametrize("timer", [
    pytest.param(signal.ITIMER_PROF, id="prof", marks=pytest.mark.skipif(
        sys.platform != "linux",
        reason="macOS notices an expired CPU timer only at the next kernel entry")),
    pytest.param(signal.ITIMER_REAL, id="real"),
])
def test_samples_are_not_pulled_onto_the_frame_that_makes_syscalls(restore_sigprof, timer):
    """Production's timer (prof, on Linux) charges CPU where it was spent even
    when a neighbour makes a syscall every microsecond. On macOS the prof
    timer fails exactly this (the decoy takes the hot function's samples),
    which is why a rig there uses the real timer."""
    previous_alarm = signal.getsignal(signal.SIGALRM)
    hot, decoy = _cpu_per_call(hot_three), _cpu_per_call(syscall_decoy)
    expected = hot / (hot + decoy)
    rounds = max(50, int(1.5 / (hot + decoy)))
    sampler = LoopCpuSampler(interval_s=0.003, enabled=_on, timer=timer).start(thread=False)
    try:
        for _ in range(rounds):
            hot_three()
            syscall_decoy()
    finally:
        sampler.stop()
        signal.signal(signal.SIGALRM, previous_alarm)
    counts = _names(sampler._window.self_counts)
    got_hot, got_decoy = counts.get("hot_three", 0), counts.get("syscall_decoy", 0)
    assert got_hot + got_decoy >= 150, counts
    share = got_hot / (got_hot + got_decoy)
    assert abs(share - expected) < 0.15, (share, expected, counts)
