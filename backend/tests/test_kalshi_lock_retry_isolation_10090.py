"""A failed whole game's retry hold does not sleep unrelated fresh game prices."""

import asyncio

from app.tasks.kalshi_ws import PRICE_FLUSH_SECONDS
from app.tasks.live_blend_refresh import run_flush_cadence
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pending_cohort_10090 import bind
from tests.test_ws_flush_cadence_10090 import _FakeTime


async def test_normal_cadence_keeps_fresh_game_progress_without_hammering_failed_cohort(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    x = rig(locked={1})
    r = bind(x, {100})
    x.ns["PRICE_FLUSH_SECONDS"] = PRICE_FLUSH_SECONDS
    x.release.set()
    original = x.ns["prices"].phase
    attempts = []
    async def phase(session, group):
        if 1 in group:
            attempts.append(clock.t)
        try:
            async for result in original(session, group):
                yield result
        except Exception:
            clock.t += 0.5  # the configured lock acquisition cost
            raise
    x.ns["prices"].phase = phase
    starts, committed = [], []
    stop = asyncio.Event()
    async def flush(started):
        starts.append(started)
        if len(starts) in (2, 3):
            # A newer tick on the failed game cannot bypass its entire cohort;
            # an independent game's newest quote remains eligible meanwhile.
            x.batch[1] = (0.9, 0.89, 0.91)
            x.batch[3] = (0.8, 0.79, 0.81)
        if len(starts) == 4:
            x.lock_released.set()
        result = await x.flush(flush_started=started)
        committed.append(tuple(x.committed))
        if len(starts) == 1:
            assert x.ns["prices"].lock_retry_until == {1: 1003.5, 2: 1003.5}
        if len(starts) in (2, 3):
            assert set(x.batch) == {1, 2}
            assert r.pending_event_ids() == frozenset({100})
            assert not any(t[0] == "admit" and 100 in t[1] for t in x.trace)
        if len(starts) == 4:
            stop.set()
        return result

    await run_flush_cadence(flush, 1, stop, failed_retry_interval_s=2)
    assert starts == [1001, 1002, 1003, 1004]
    assert attempts == [1001, 1004]  # more than two seconds after failure, no hammer
    assert committed[:3] == [(3, 9), (3, 9, 3), (3, 9, 3, 3)]
    assert committed[3] == (3, 9, 3, 3, 1, 2)
    assert not x.batch and not x.ns["prices"].lock_retry_until
    assert not r.pending_event_ids()
    assert x.stats["errors"] == 1 and x.stats["requeued"] == 2
