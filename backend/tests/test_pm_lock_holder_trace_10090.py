"""#10090: the rank-lock holder sampler's bounds, without a database.

The real-Postgres half (a held row, the actual `write_chunk`, the actual probe
SQL) is `tests/integration/test_pm_rank_lock_holder_10090_pg.py`. This file pins
what that one cannot cheaply: off by default, the window and probe caps, single
flight, the per-minute floor, no probe for a rank that finished inside the
delay, STOP at the first holder, a probe that overruns its deadline, an empty
application tag kept as UNKNOWN, and a writer that never waits on the observer.
"""

from __future__ import annotations

import asyncio

import pytest

import app.utils.pm_lock_holder_trace as mod
from app.utils.pm_lock_holder_trace import RankLockHolderSampler

pytestmark = pytest.mark.asyncio

NOW = 1_000_000.0


class _Clock:
    def __init__(self):
        self.wall = NOW
        self.mono = 50.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


class _Conn:
    def __init__(self, engine):
        self.engine = engine

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        self.engine.calls.append(params)
        if params is None:  # the warm-up SELECT 1
            return None
        if self.engine.hang:
            await asyncio.sleep(10)
        if self.engine.during_probe is not None:
            self.engine.during_probe()
        engine = self.engine

        class _Result:
            def mappings(self):
                return list(engine.rows)

        return _Result()


class _Engine:
    def __init__(self, rows=(), hang=False, during_probe=None):
        self.rows = list(rows)
        self.hang = hang
        self.during_probe = during_probe
        self.calls = []
        self.disposed = False

    def connect(self):
        return _Conn(self)

    async def dispose(self):
        self.disposed = True


def _sampler(env=None, engine=None, clock=None):
    clock = clock or _Clock()
    lines = []
    engine = engine or _Engine()
    sampler = RankLockHolderSampler.from_env(
        env if env is not None else {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(NOW + 600)},
        run="r1", wall=lambda: clock.wall, mono=lambda: clock.mono,
        emit=lines.append, engine_factory=lambda: engine,
    )
    return sampler, lines, engine, clock


async def _warm(sampler):
    assert sampler.ready() is False  # first call starts the warm-up
    await sampler.warming
    assert sampler.ready() is True


HOLDER_ROW = {
    "writer_wait_event_type": "Lock",
    "writer_wait_event": "transactionid",
    "blocking_pid": 4242,
    "blocker_application": "",
    "blocker_state": "idle in transaction",
    "blocker_transaction_age_s": 12.3456,
}


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": ""},
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": "soon"},
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(NOW - 1)},
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(NOW + mod.MAX_WINDOW_S + 1)},
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(NOW + 60), "WS_PM_LOCK_HOLDER_MAX_PROBES": "0"},
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(NOW + 60), "WS_PM_LOCK_HOLDER_MAX_PROBES": "31"},
    ],
)
async def test_off_unless_a_bounded_window_is_configured(env):
    sampler, lines, _engine, _clock = _sampler(env=env)
    assert sampler is None
    assert lines == []


async def test_a_rank_that_finishes_inside_the_delay_spends_nothing(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    sampler, lines, engine, _clock = _sampler(engine=_Engine([HOLDER_ROW]))
    await _warm(sampler)

    token = sampler.rank_started(77, {1: 0.4, 2: 0.6}, {5})
    sampler.rank_finished(token, None)
    await token.task

    assert sampler.probes == 0
    assert [c for c in engine.calls if c is not None] == []
    assert [line["kind"] for line in lines] == ["START", "WARM"]
    assert sampler.ready() is True, "an unprobed rank must not consume the minute"


async def test_a_still_running_rank_names_its_holder_and_stops(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    sampler, lines, engine, _clock = _sampler(engine=_Engine([HOLDER_ROW]))
    await _warm(sampler)

    markets = set(range(1, 12))
    token = sampler.rank_started(77, {1: 0.4, 2: 0.6, 3: 0.1}, markets)
    await token.task
    sampler.rank_finished(token, RuntimeError("canceling statement due to lock timeout"))

    probe = next(line for line in lines if line["kind"] == "PROBE")
    assert probe["result"] == "HOLDER"
    assert probe["writer_pid"] == 77
    assert probe["markets"] == list(range(1, 9)) and probe["markets_n"] == 11
    assert probe["outcomes_n"] == 3
    assert probe["writer_wait"] == "Lock/transactionid"
    assert probe["holders"] == [
        {"pid": 4242, "application": "UNKNOWN", "state": "idle in transaction",
         "xact_age_s": 12.346}
    ], "an empty application tag stays UNKNOWN"
    assert engine.calls[-1] == {"pid": 77}
    stop = next(line for line in lines if line["kind"] == "STOP")
    assert stop["reason"] == "FIRST_HOLDER"
    await asyncio.sleep(0)
    assert engine.disposed
    assert sampler.ready() is False and sampler.rank_started(78, {1: 0.5}, {5}) is None
    assert [line["kind"] for line in lines][-1] == "RANK_END"


async def test_one_probe_in_flight_and_one_per_minute(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    sampler, lines, _engine, clock = _sampler(engine=_Engine([]))
    await _warm(sampler)

    first = sampler.rank_started(1, {1: 0.5}, {5})
    assert sampler.rank_started(2, {2: 0.5}, {6}) is None, "single flight"
    await first.task
    sampler.rank_finished(first, None)
    assert next(line for line in lines if line["kind"] == "PROBE")["result"] == "NO_LOCK_WAIT"

    clock.advance(mod.MIN_PROBE_INTERVAL_S - 1)
    assert sampler.rank_started(3, {3: 0.5}, {7}) is None, "inside the minute"
    clock.advance(1)
    assert sampler.rank_started(4, {4: 0.5}, {8}) is not None


async def test_the_probe_budget_stops_the_sampler(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    env = {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(NOW + 600), "WS_PM_LOCK_HOLDER_MAX_PROBES": "2"}
    sampler, lines, _engine, clock = _sampler(env=env, engine=_Engine([]))
    await _warm(sampler)
    for pid in (1, 2):
        token = sampler.rank_started(pid, {1: 0.5}, {5})
        await token.task
        clock.advance(mod.MIN_PROBE_INTERVAL_S)
    assert [line["reason"] for line in lines if line["kind"] == "STOP"] == ["PROBE_BUDGET"]
    assert sampler.rank_started(3, {1: 0.5}, {5}) is None


async def test_a_probe_past_its_deadline_is_recorded_not_waited_on(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    monkeypatch.setattr(mod, "PROBE_DEADLINE_S", 0.02)
    sampler, lines, _engine, _clock = _sampler(engine=_Engine(hang=True))
    await _warm(sampler)
    token = sampler.rank_started(9, {1: 0.5}, {5})
    await asyncio.wait_for(token.task, 1)
    probe = next(line for line in lines if line["kind"] == "PROBE")
    assert probe["result"] == "PROBE_TIMEOUT" and probe["holders"] == []


async def test_the_writer_never_waits_on_the_observer(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.5)
    sampler, _lines, _engine, _clock = _sampler(engine=_Engine(hang=True))
    await _warm(sampler)
    loop = asyncio.get_running_loop()
    started = loop.time()
    token = sampler.rank_started(9, {1: 0.5}, {5})
    sampler.rank_finished(token, None)
    assert loop.time() - started < 0.05
    assert not token.task.done(), "the probe runs beside the writer, never in its path"
    token.task.cancel()


async def test_expiry_stops_without_a_probe(monkeypatch):
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    sampler, lines, _engine, clock = _sampler()
    await _warm(sampler)
    clock.advance(601)
    assert sampler.ready() is False
    assert [line["reason"] for line in lines if line["kind"] == "STOP"] == ["EXPIRED"]


async def test_an_unreachable_probe_connection_stops_the_sampler():
    class _Broken(_Engine):
        def connect(self):
            raise OSError("no route")

    sampler, lines, _engine, _clock = _sampler(engine=_Broken())
    assert sampler.ready() is False
    await sampler.warming
    assert [line["kind"] for line in lines][-2:] == ["UNAVAILABLE", "STOP"]
    assert sampler.ready() is False


async def test_one_sampler_per_process(monkeypatch):
    monkeypatch.setattr(mod, "_process_sampler", None)
    monkeypatch.setattr(mod, "_process_configured", False)
    built = []
    monkeypatch.setattr(
        RankLockHolderSampler, "from_env",
        classmethod(lambda cls, env, run: built.append(run) or object()),
    )
    first = mod.for_process({}, run="a")
    assert mod.for_process({}, run="b") is first
    assert built == ["a"], "a recycled consumer reuses the process's budget"


async def test_a_rank_that_ends_during_the_probe_is_attributed_to_nobody(monkeypatch):
    """Root attempt60: the token check passed, the probe was dispatched, and the
    rank returned before the snapshot. The writer's backend may already be
    waiting on its NEXT statement, so a holder row here cannot be pinned on
    this rank: no holder named, no FIRST_HOLDER stop, budget still spent."""
    monkeypatch.setattr(mod, "PROBE_DELAY_S", 0.01)
    box = {}
    engine = _Engine([HOLDER_ROW], during_probe=lambda: sampler.rank_finished(box["t"], None))
    sampler, lines, _engine, clock = _sampler(engine=engine)
    await _warm(sampler)

    box["t"] = token = sampler.rank_started(77, {1: 0.4}, {5})
    await token.task

    probe = next(line for line in lines if line["kind"] == "PROBE")
    assert probe["result"] == "STALE_RANK_ENDED"
    assert probe["holders"] == [] and probe["holders_n"] == 0
    assert probe["rank_still_running"] is False
    assert not [line for line in lines if line["kind"] == "STOP"]
    assert sampler.probes == 1
    assert sampler.rank_started(78, {1: 0.4}, {5}) is None, "the minute is spent"
    clock.advance(mod.MIN_PROBE_INTERVAL_S)
    assert sampler.rank_started(78, {1: 0.4}, {5}) is not None


async def test_the_warm_bound_covers_acquiring_the_connection(monkeypatch):
    monkeypatch.setattr(mod, "WARM_TIMEOUT_S", 0.05)

    class _SlowConnect(_Engine):
        def connect(self):
            engine = self

            class _Slow(_Conn):
                async def __aenter__(self):
                    await asyncio.sleep(10)
                    return self

            return _Slow(engine)

    engine = _SlowConnect()
    sampler, lines, _engine, _clock = _sampler(engine=engine)
    assert sampler.ready() is False
    await asyncio.wait_for(sampler.warming, 1)
    assert [line["kind"] for line in lines][-2:] == ["UNAVAILABLE", "STOP"]
    assert lines[-2]["error"] == "TimeoutError"
    assert engine.disposed
