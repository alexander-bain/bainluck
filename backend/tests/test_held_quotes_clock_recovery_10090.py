"""One early clock recovery probe shortens observation stalls, without a retry storm."""
import asyncio

import pytest

from tests.test_held_quotes_idle_bound_10090 import Clock, FakeDB, _held, _mark


class BrokenDB(FakeDB):
    async def _read(self, gate, value):
        raise TimeoutError("controlled clock failure")


async def test_one_early_probe_then_five_second_backoff_despite_input_and_call_storm():
    clock = Clock()
    held = _held(clock)
    db = BrokenDB(clock)
    assert not await held.sample_database_clock(db)
    assert held._sample_backoff_until == .25
    for tick in range(1, 526):
        clock.t = tick / 100
        held.note_input(_mark())
        await asyncio.gather(*(held.sample_database_clock(db) for _ in range(5)))
        if tick < 25:
            assert db.calls == 1
        elif tick < 525:
            assert db.calls == 2
    assert db.calls == 3 and held.sample_failures == 3
    assert held._sample_backoff_until == 10.25
    task = held._idle_task
    held.close()
    if task:
        await asyncio.gather(task, return_exceptions=True)


async def test_healthy_recovery_changes_only_future_inputs_and_rearms_next_episode():
    clock = Clock()
    held = _held(clock, events=())
    healthy = FakeDB(clock)
    assert await held.sample_database_clock(healthy)
    held.preview_events = lambda: (7,)
    clock.t = .25
    assert not await held.sample_database_clock(BrokenDB(clock))
    clock.t = .5
    frozen = _mark(event_id=8)
    held.note_input(frozen)
    assert held.bound_for(frozen) == 1000
    assert await held.sample_database_clock(healthy)
    assert held.bound_for(frozen) == 1000
    after = _mark(event_id=8)
    held.note_input(after)
    assert held.bound_for(after) == 1000.5
    assert not held._sample_failure_episode
    clock.t = .75
    assert not await held.sample_database_clock(BrokenDB(clock))
    assert held._sample_backoff_until == 1.0


async def test_only_one_recovery_probe_can_be_in_flight_and_cancellation_consumes_it():
    clock = Clock()
    held = _held(clock)
    assert not await held.sample_database_clock(BrokenDB(clock))
    clock.t = .25
    db = FakeDB(clock)
    db.gates.append(asyncio.Event())
    probe = asyncio.create_task(held.sample_database_clock(db))
    await asyncio.sleep(0)
    assert db.active == 1
    assert not any(await asyncio.gather(*(held.sample_database_clock(db) for _ in range(20))))
    assert db.calls == 1
    probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await probe
    clock.t = .5
    assert not await held.sample_database_clock(db)
    assert db.calls == 1 and held._sample_backoff_until == 5.25
    assert held.sample_failures == 1  # cancellation is not a SQL failure


async def test_older_success_does_not_clear_newer_failure_episode():
    clock = Clock()
    held = _held(clock)
    db = FakeDB(clock)
    gate = asyncio.Event()
    db.gates.append(gate)
    old = asyncio.create_task(held.sample_database_clock(db))
    await asyncio.sleep(0)
    assert not await held.sample_database_clock(BrokenDB(clock))
    until = held._sample_backoff_until
    gate.set()
    assert await old
    assert held._sample_failure_episode and held._sample_backoff_until == until
    clock.t = until
    assert await held.sample_database_clock(db)
    assert not held._sample_failure_episode


async def test_older_failure_does_not_throttle_newer_success():
    clock = Clock()
    held = _held(clock)
    gate = asyncio.Event()

    class LateFailure(FakeDB):
        async def _read(self, *_):
            await gate.wait()
            raise TimeoutError("old read")

    old = asyncio.create_task(held.sample_database_clock(LateFailure(clock)))
    await asyncio.sleep(0)
    clock.t = .1
    assert await held.sample_database_clock(FakeDB(clock))
    gate.set()
    assert not await old
    assert held.sample_failures == 1
    assert not held._sample_failure_episode and held._sample_backoff_until == 0
    assert held._database_bound == 1000.1


async def test_without_preview_keeps_existing_long_backoff():
    clock = Clock()
    held = _held(clock, events=())
    assert not await held.sample_database_clock(BrokenDB(clock))
    assert held._sample_backoff_until == 5


async def test_ambiguity_failure_keeps_long_backoff_and_does_not_rearm_early_probe():
    clock = Clock()
    held = _held(clock)
    db = BrokenDB(clock)
    assert await held.stored_at_or_after(db, {101: (.46, 999)}) is None
    assert held._sample_backoff_until == 5
    clock.t = 5
    assert not await held.sample_database_clock(db)
    assert held._sample_backoff_until == 10
