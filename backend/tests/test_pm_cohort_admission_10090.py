"""Unfinished PM cohorts remain owed while independent complete games stamp."""

import asyncio

import pytest

from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.test_polymarket_withdrawal_speed_10651 import rig


class Recording(LiveBlendRefresher):
    def __init__(self, trace):
        super().__init__("polymarket", min_refresh_interval_s=0)
        self.trace = trace
        self.held = asyncio.Event()
        self.release = asyncio.Event()
        self.hold = False

    async def _prepare_groups(self, ids):
        return {}

    async def _refresh_batch(self, ids, now, *, prepared=None, on_committed=None,
                             publish_committed=None):
        self.trace.append(("admit", sorted(ids)))
        if self.hold:
            self.held.set()
            await self.release.wait()
        self._last_refresh_at.update(dict.fromkeys(ids, now))
        if on_committed is not None:
            on_committed(ids)

    async def publish_market_changes(self, session):
        self.trace.append(("publish", None))


async def test_exclusions_keep_fresh_retry_and_throttle_debt_and_default_readmits_all(monkeypatch):
    from app.tasks import live_blend_refresh as module

    monkeypatch.setattr(module, "_mono", lambda: 100)
    r = Recording([])
    r._lock_retry.add(90)
    r.adopt_pending([91])
    await r.refresh([10, 92], flush_started=100, defer_event_ids={90, 91, 92})
    assert r.trace == [("admit", [10])]
    assert r.pending_event_ids() == frozenset({90, 91, 92})
    assert 90 in r._lock_retry
    assert not ({90, 91, 92} & r._last_refresh_at.keys())
    monkeypatch.setattr(module, "_mono", lambda: 102)
    await r.refresh_pending(flush_started=102)
    assert {eid for kind, ids in r.trace[1:] if kind == "admit" for eid in ids} == {
        90, 91, 92,
    }
    assert not r.pending_event_ids()


async def test_cancel_preserves_excluded_debt_and_the_uncommitted_admitted_game():
    r = Recording([])
    r.hold = True
    r.adopt_pending([90])
    task = asyncio.create_task(r.refresh([10], defer_event_ids={90}))
    await asyncio.wait_for(r.held.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert r.pending_event_ids() == frozenset({10, 90})


async def test_debt_with_one_leg_written_waits_for_its_last_leg_while_other_game_progresses():
    x = rig(batch={1: 0.1, 2: 0.7, 900: 0.9},
            mapping={1: 90, 2: 10, 900: 90}, books={})
    x.ns["FLUSH_CHUNK_ROWS"] = 1
    x.ns["open_complement_of"] = {}
    r = Recording(x.trace)
    r.hold = True
    r.adopt_pending([90])
    x.ns["blend_refresher"] = r
    task = asyncio.create_task(x.ns["flush_prices"](flush_started=100))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert ("write", [1]) in x.trace and 1 not in x.ns["price_buffer"]
        assert ("admit", [10]) in x.trace
        assert not any(90 in ids for kind, ids in x.trace if kind == "admit")
        assert r.pending_event_ids() == frozenset({90})
        assert 900 in x.ns["price_buffer"]
        r.release.set()
        x.release.set()
        assert await asyncio.wait_for(task, 1)
        assert x.trace.index(("write", [900])) < x.trace.index(("admit", [90]))
        assert not r.pending_event_ids()
    finally:
        r.release.set()
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_failed_planned_leg_never_enters_implicit_or_tail_stamp():
    x = rig(batch={1: 0.6, 2: 0.4, 900: 0.1, 901: 0.9},
            mapping={1: 10, 2: 10, 900: 90, 901: 90}, books={}, failed_price=900)
    x.ns["FLUSH_CHUNK_ROWS"] = 1
    x.release.set()
    r = Recording(x.trace)
    r.adopt_pending([90])
    x.ns["blend_refresher"] = r
    assert not await x.ns["flush_prices"](flush_started=100)
    assert ("admit", [10]) in x.trace
    assert not any(90 in ids for kind, ids in x.trace if kind == "admit")
    assert r.pending_event_ids() == frozenset({90})


async def test_capped_out_tail_preserves_the_existing_planned_chunk_boundary():
    x = rig(batch={1: 0.6, 2: 0.4, 900: 0.1, 901: 0.9},
            mapping={1: 10, 2: 10, 900: 90, 901: 90}, books={})
    x.ns["FLUSH_CHUNK_ROWS"] = 1
    x.ns["OPEN_FLUSH_CHUNKS_PER_FLUSH"] = 1
    x.release.set()
    r = Recording(x.trace)
    r.adopt_pending([90])
    x.ns["blend_refresher"] = r
    assert await x.ns["flush_prices"](flush_started=100)
    assert ("admit", [90]) in x.trace
    assert 901 in x.ns["price_buffer"]
    assert not r.pending_event_ids()


async def test_quiet_failed_withdrawal_keeps_debt_then_stamps_after_success():
    x = rig(batch={}, books={44: (0.2, 0.8)}, mapping={44: 90}, fail=True)
    r = Recording(x.trace)
    r.adopt_pending([90, 20])
    x.ns["blend_refresher"] = r
    assert not await x.ns["flush_prices"](flush_started=100)
    assert ("admit", [20]) in x.trace and ("admit", [90]) not in x.trace
    assert r.pending_event_ids() == frozenset({90})
    x.control["fail"] = False
    assert await x.ns["flush_prices"](flush_started=102)
    assert x.trace[-1] == ("admit", [90])
    assert not r.pending_event_ids()
