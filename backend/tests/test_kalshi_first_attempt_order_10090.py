"""#10090 — a live whole group's first attempt does not queue behind retained
ordinary retries; those retries still run in the same flush (Root attempt47,
qualified on the C1/C2-corrected #11208 source as attempt51)."""

import pytest
from app.tasks.kalshi_ws import SHORT_PROBE_LOCK_TIMEOUT_MS
from tests.test_kalshi_held_quotes_10090 import Clock, PERIOD, held_rig, writes_of


def fixture(monkeypatch, answer=set()):
    x = held_rig(monkeypatch, answer=answer, live=(100, 200))
    x.ns["SHORT_PROBE_LOCK_TIMEOUT_MS"] = SHORT_PROBE_LOCK_TIMEOUT_MS
    return x


@pytest.mark.asyncio
async def test_first_live_attempt_precedes_normal_retry_and_both_run(monkeypatch):
    clock = Clock(monkeypatch)
    x = fixture(monkeypatch)
    await x.flush(flush_started=clock.t)
    assert not x.committed and x.prices.short_probe_refused == {1, 2}
    clock.t += PERIOD
    x.tick(3, 0.72)
    before = len(x.trace)
    await x.flush(flush_started=clock.t)
    attempts = [v for k, v in x.trace[before:] if k == "write"]
    assert attempts[:2] == [3, 1], attempts
    assert x.committed == [3] and set(x.batch) == {1, 2}
    assert [v for k, v in x.trace[before:] if k == "lock_timeout"] == ["1ms", "50ms"]
    assert set(x.prices.lock_retry_until.values()) == {
        clock.t + x.ns["PRICE_FLUSH_SECONDS"]
    }
    assert writes_of(x, 1) == 2


@pytest.mark.asyncio
async def test_healthy_first_group_does_not_drop_ordinary_persistence(monkeypatch):
    clock = Clock(monkeypatch)
    x = fixture(monkeypatch)
    await x.flush(flush_started=clock.t)
    clock.t += PERIOD
    x.tick(3, 0.72)
    x.lock_released.set()
    await x.flush(flush_started=clock.t)
    assert x.committed == [3, 1, 2]
    assert (
        not x.batch
        and not x.prices.short_probe_refused
        and not x.prices.lock_retry_until
    )


@pytest.mark.asyncio
async def test_hot_new_group_does_not_starve_due_retry(monkeypatch):
    clock = Clock(monkeypatch)
    x = fixture(monkeypatch)
    await x.flush(flush_started=clock.t)
    writes = []
    for i in range(1, 11):
        clock.t = 1000 + i * PERIOD
        x.tick(3, 0.60 + i * 0.01)
        before = writes_of(x, 1)
        await x.flush(flush_started=clock.t)
        if writes_of(x, 1) > before:
            writes.append(i)
        assert 3 not in x.batch
    assert writes == [1, 9], writes
    assert [v for k, v in x.trace if k == "lock_timeout"].count("50ms") == 2
    x.lock_released.set()
    clock.t = max(x.prices.lock_retry_until.values())
    await x.flush(flush_started=clock.t)
    assert not x.batch and x.committed.count(1) == x.committed.count(2) == 1


@pytest.mark.asyncio
async def test_fresh_groups_keep_original_order_and_final_drain_keeps_order(
    monkeypatch,
):
    clock = Clock(monkeypatch)
    x = fixture(monkeypatch)
    x.tick(3, 0.72)
    x.lock_released.set()
    await x.flush(flush_started=clock.t)
    assert x.committed == [1, 2, 3]
    x = fixture(monkeypatch)
    await x.flush(flush_started=clock.t)
    x.tick(3, 0.72)
    x.lock_released.set()
    await x.flush(flush_started=clock.t, final_drain=True)
    assert x.committed == [1, 2, 3]


@pytest.mark.asyncio
async def test_ambiguous_first_attempt_still_escalates_immediately(monkeypatch):
    clock = Clock(monkeypatch)
    x = fixture(monkeypatch, answer={1})
    x.tick(3, 0.72)
    await x.flush(flush_started=clock.t)
    attempts = [v for k, v in x.trace if k == "write"]
    assert attempts[:3] == [1, 1, 3], attempts
    assert set(x.batch) == {1, 2} and x.committed == [3]
