"""Graph clock success must not repeatedly rearm a failing shorter-budget read."""

from tests.test_observation_graph_clock_10090 import clock_rig
from tests.test_fresh_observation_preview_10090 import (
    preview_enabled as preview_enabled,
)
from tests.test_held_quotes_idle_bound_10090 import Clock, FakeDB, _mark
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
