"""Graph clock success must not repeatedly rearm a failing shorter-budget read."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from tests.test_observation_graph_clock_10090 import clock_rig
from tests.test_fresh_observation_preview_10090 import (
    preview_enabled as preview_enabled,
)
from tests.test_held_quotes_idle_bound_10090 import Clock, FakeDB, _mark, _run_until
from tests.test_held_quotes_clock_recovery_10090 import BrokenDB


async def test_graph_successes_do_not_multiply_standalone_failure_probes(monkeypatch):
    r, held, _, _, obs, validate, now, frozen, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now = clock.now
    held.preview_events = lambda: (1,)
    failed = BrokenDB(clock)
    before = held.bound_for(frozen)
    assert not await held.sample_database_clock(failed)
    assert held._sample_backoff_until == held.SAMPLE_RECOVERY_S
    for tick in range(1, 21):
        clock.t = tick / 10
        await r.preview_accepted_observations(obs, validate)
        assert held._database_bound == now.timestamp()
        assert held.bound_for(frozen) == before
        future = _mark(event_id=8, oid=102)
        held.note_input(future)
        assert held.bound_for(future) == now.timestamp()
        await held.sample_database_clock(failed)
    assert failed.calls == 2
    assert held.sample_failures == 2
    assert held._sample_failure_episode
    # If graph traffic stops, the existing standalone deadline still runs;
    # a genuine standalone success clears the episode and samples later time.
    until = held._sample_backoff_until
    healthy = FakeDB(clock)
    clock.t = until - 0.001
    assert not await held.sample_database_clock(healthy)
    assert healthy.calls == 0
    clock.t = until
    assert await held.sample_database_clock(healthy)
    assert healthy.calls == 1
    assert held._database_bound == 1000 + until
    assert not held._sample_failure_episode and held._sample_backoff_until == 0


async def test_healthy_graph_does_not_invent_a_failure_episode(monkeypatch):
    r, held, _, _, obs, validate, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now = clock.now
    await r.preview_accepted_observations(obs, validate)
    assert not held._sample_failure_episode
    db = FakeDB(clock)
    assert await held.sample_database_clock(db)
    assert db.calls == 1


async def test_standalone_success_recovers_without_overwriting_newer_graph(monkeypatch):
    r, held, _, _, obs, validate, now, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now = clock.now
    held.preview_events = lambda: (1,)
    assert not await held.sample_database_clock(BrokenDB(clock))
    clock.t = 0.25
    db = FakeDB(clock)
    gate = asyncio.Event()
    db.gates.append(gate)
    db.values.append(now.timestamp() - 0.1)
    task = asyncio.create_task(held.sample_database_clock(db))
    await asyncio.sleep(0)
    assert db.active == 1
    await r.preview_accepted_observations(obs, validate)
    graph_ordinal = held._sample_published
    gate.set()
    assert await task
    assert held._sample_published == graph_ordinal
    assert held._database_bound == now.timestamp()
    assert not held._sample_failure_episode and held._sample_backoff_until == 0


async def test_first_input_after_quiet_graph_recovery_gets_a_fresh_bound(monkeypatch):
    r, held, _, _, obs, validate, now, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now, held._sleep = clock.now, clock.sleep
    held.preview_events = lambda: (1,)
    broken = BrokenDB(clock)
    assert not await held.sample_database_clock(broken)
    clock.t = 0.3
    assert not await held.sample_database_clock(broken)
    clock.t = 0.4
    await r.preview_accepted_observations(obs, validate)

    class RecoveredDB(FakeDB):
        async def _read(self, gate, value):
            return SimpleNamespace(
                scalar_one=lambda: now + timedelta(seconds=clock.t - 0.4)
            )

    db = RecoveredDB(clock)
    held._sessions = db
    held.note_input(_mark(event_id=1, oid=102))
    try:
        await _run_until(clock, 4)
        returned = _mark(event_id=1, oid=102)
        held.note_input(returned)
        assert held.bound_for(returned) >= now.timestamp() + 3.6 - held.IDLE_SAMPLE_S
        assert not held._sample_failure_episode
    finally:
        task = held.close()
        if task:
            await asyncio.gather(task, return_exceptions=True)


async def test_failed_quiet_probe_is_once_and_does_not_delay_original_retry(
    monkeypatch,
):
    r, held, _, _, obs, validate, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now, held._sleep = clock.now, clock.sleep
    held.preview_events = lambda: (1,)
    broken = BrokenDB(clock)
    assert not await held.sample_database_clock(broken)
    clock.t = 0.3
    assert not await held.sample_database_clock(broken)
    original_retry = held._sample_backoff_until
    clock.t = 0.4
    await r.preview_accepted_observations(obs, validate)
    held.note_input(_mark(event_id=1, oid=102))
    try:
        await _run_until(clock, 2)
        assert broken.calls == 3
        assert held._sample_backoff_until == original_retry
        # More graph success cannot give the same failure episode a second
        # quiet recovery probe, even though no further source input arrived.
        await r.preview_accepted_observations(obs, validate)
        await _run_until(clock, original_retry - 0.05)
        assert broken.calls == 3
        await _run_until(clock, original_retry + 0.3)
        assert broken.calls == 4
    finally:
        task = held.close()
        if task:
            await asyncio.gather(task, return_exceptions=True)


async def test_unrelated_input_grace_cannot_consume_quiet_recovery_early(monkeypatch):
    r, held, _, _, obs, validate, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now, held._sleep = clock.now, clock.sleep
    held.preview_events = lambda: (1,)
    broken = BrokenDB(clock)
    assert not await held.sample_database_clock(broken)
    clock.t = 0.3
    assert not await held.sample_database_clock(broken)
    original_retry = held._sample_backoff_until
    clock.t = 0.4
    await r.preview_accepted_observations(obs, validate)
    held.note_input(_mark(event_id=1, oid=102))
    try:
        await _run_until(clock, 1.3)
        held.note_input(_mark(event_id=8, oid=103))
        await _run_until(clock, 2)
        assert broken.calls == 2
        assert held._sample_backoff_until == original_retry
        assert not await held.sample_database_clock(broken)
        assert broken.calls == 2
        await _run_until(clock, 2.6)
        assert broken.calls == 3
        assert held._sample_backoff_until == original_retry
    finally:
        task = held.close()
        if task:
            await asyncio.gather(task, return_exceptions=True)


async def test_cancelled_quiet_probe_consumes_opportunity_and_keeps_deadline(
    monkeypatch,
):
    r, held, _, _, obs, validate, *_ = clock_rig(monkeypatch)
    clock = Clock()
    held._now, held._sleep = clock.now, clock.sleep
    held.preview_events = lambda: (1,)
    broken = BrokenDB(clock)
    assert not await held.sample_database_clock(broken)
    clock.t = 0.3
    assert not await held.sample_database_clock(broken)
    original_retry = held._sample_backoff_until
    clock.t = 0.4
    await r.preview_accepted_observations(obs, validate)
    db = FakeDB(clock)
    db.gates.append(asyncio.Event())
    held._sessions = db
    held.note_input(_mark(event_id=1, oid=102))
    try:
        await _run_until(clock, 1.5)
        assert db.calls == 1 and db.active == 1
        held._idle_task.cancel()
        await asyncio.gather(held._idle_task, return_exceptions=True)
        assert held._sample_backoff_until == original_retry
        held.note_input(_mark(event_id=1, oid=102))
        await _run_until(clock, 3)
        assert db.calls == 1
    finally:
        task = held.close()
        if task:
            await asyncio.gather(task, return_exceptions=True)
