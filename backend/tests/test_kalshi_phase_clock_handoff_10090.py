"""Completed Kalshi phases do not hold later prices behind optional clock IO."""
import asyncio

import pytest

from tests.test_held_quotes_idle_bound_10090 import (
    Clock, FakeDB, _held, _mark, _run_until, _settle,
)
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pipelined_stamps_10090 import held_refresher


async def stop(held):
    task = held.close()
    if task:
        await asyncio.gather(task, return_exceptions=True)


async def test_next_price_phase_commits_while_real_clock_read_is_held():
    clock = Clock()
    db = FakeDB(clock)
    held = _held(clock, events=())
    await held.sample_database_clock(db)
    clock.t = 0.1
    mark = _mark()
    held.note_input(mark)
    gate = asyncio.Event()
    db.gates.append(gate)
    real_sample = held.sample_database_clock

    async def sample(_sessions):
        return await real_sample(db)

    held.sample_database_clock = sample
    r = rig()
    r.release.set()
    stamp_gate, calls = held_refresher(r, hold_ids=())
    r.ns["blend_refresher"].held_quotes = held
    task = asyncio.create_task(r.flush())
    try:
        for _ in range(100):
            await asyncio.sleep(0)
            if db.active and 3 in r.committed:
                break
        assert db.active == 1
        assert 3 in r.committed, "next price phase must not wait for clock read"
        assert calls["started"]
        assert held.bound_for(mark) == 1000.0
        during = _mark(oid=102)
        held.note_input(during)
        assert held.bound_for(during) == 1000.0
        gate.set()
        await asyncio.wait_for(task, 2)
        await _settle()
        after = _mark(oid=103)
        held.note_input(after)
        assert held.bound_for(after) == 1000.1
        assert held.bound_for(during) == 1000.0
        assert db.max_active == 1
    finally:
        gate.set()
        stamp_gate.set()
        await asyncio.gather(task, return_exceptions=True)
        await r.ns["prices"].join_stamp(r.ns["blend_refresher"])
        await stop(held)
    assert db.active == 0 and held._idle_task is None


async def test_continuous_inputs_do_not_starve_requested_samples():
    clock = Clock()
    held = _held(clock)
    db = FakeDB(clock)
    await held.sample_database_clock(db)
    owner = None
    try:
        for n in range(1, 31):
            await _run_until(clock, n / 10)
            held.note_input(_mark())
            held.request_phase_sample(db)
            if owner is None:
                owner = held._idle_task
            assert held._idle_task is owner
            await _settle()
        assert held._database_bound >= 1002.7
        assert db.calls > 10 and db.max_active == 1
    finally:
        await stop(held)


async def test_requests_coalesce_but_request_during_read_is_retained():
    clock = Clock()
    held = _held(clock, events=())
    db = FakeDB(clock)
    gate = asyncio.Event()
    db.gates.append(gate)
    try:
        for _ in range(20):
            held.request_phase_sample(db)
        await _settle()
        assert db.calls == 1
        owner = held._idle_task
        for _ in range(20):
            held.request_phase_sample(db)
        assert held._idle_task is owner
        gate.set()
        await _settle()
        assert db.calls == 2 and db.max_active == 1
        assert owner.done()
    finally:
        gate.set()
        await stop(held)


async def test_pending_request_preserves_failure_backoff_and_graph_allowance():
    from tests.test_held_quotes_clock_recovery_10090 import BrokenDB

    clock = Clock()
    held = _held(clock)
    db = BrokenDB(clock)
    held.note_input(_mark())
    assert not await held.sample_database_clock(db)
    held._graph_sample_ordinal = held._sample_failure_ordinal + 1
    try:
        for n in range(1, 525):
            held.note_input(_mark())  # genuinely busy input, not requests alone
            held.request_phase_sample(db)
            await _run_until(clock, n / 100)
            assert db.calls == (1 if n < 25 else 2)
        assert not held._graph_idle_recovery_used
        assert held._sample_backoff_until == pytest.approx(5.25)
    finally:
        await stop(held)


async def test_close_cancels_owned_read_and_refuses_future_requests():
    clock = Clock()
    held = _held(clock, events=())
    db = FakeDB(clock)
    db.gates.append(asyncio.Event())
    held.request_phase_sample(db)
    await _settle()
    assert db.active == 1
    await stop(held)
    held.request_phase_sample(db)
    await _settle()
    assert db.active == 0 and db.calls == 1 and held._idle_task is None


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("healthy", [False, True])
async def test_pending_request_keeps_earned_quiet_graph_recovery(pending, healthy):
    from tests.test_held_quotes_clock_recovery_10090 import BrokenDB

    clock = Clock()
    held = _held(clock)
    broken = BrokenDB(clock)
    assert not await held.sample_database_clock(broken)
    clock.t = .25
    assert not await held.sample_database_clock(broken)
    deadline = held._sample_backoff_until
    clock.t = .5
    # New successful graph evidence, followed by truly quiet preview traffic.
    held._sample_started += 1
    held._graph_sample_ordinal = held._sample_started
    held._sample_published = held._sample_started
    held._database_bound = 1000.5
    db = FakeDB(clock) if healthy else BrokenDB(clock)
    held._sessions = db
    held.note_input(_mark())
    if pending:
        held.request_phase_sample(db)
    try:
        await _run_until(clock, 1.6)
        assert db.calls >= 1
        if healthy:
            assert held._database_bound >= 1001.5
            assert not held._sample_failure_episode
        else:
            assert db.calls == 1 and held._graph_idle_recovery_used
            assert held._sample_backoff_until == deadline
            await _run_until(clock, deadline - .1)
            assert db.calls == 1
    finally:
        await stop(held)
