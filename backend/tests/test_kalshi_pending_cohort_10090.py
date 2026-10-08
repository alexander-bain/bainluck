"""Pending blend debt cannot join independent game prices or read a partial game."""

import asyncio

import pytest

from app.tasks.kalshi_ws import linked_first_phases
from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.test_kalshi_game_isolation_10655 import rig


class Recording(LiveBlendRefresher):
    def __init__(self, x):
        super().__init__("kalshi", min_refresh_interval_s=0)
        self.x = x
        self.hold = False
        self.entered, self.release, self.cleaned = (
            asyncio.Event(), asyncio.Event(), asyncio.Event()
        )

    async def _prepare_groups(self, ids):
        return {}

    async def _refresh_batch(self, ids, now, *, prepared=None,
                             on_committed=None, publish_committed=None):
        self.x.trace.append(("admit", tuple(ids), tuple(self.x.committed)))
        for event in ids:
            assert all(oid in self.x.committed for oid in self.x.batch
                       if self.x.events.get(oid) == event)
        if self.hold:
            self.entered.set()
            try:
                await self.release.wait()
            finally:
                self.cleaned.set()
        self._last_refresh_at.update(dict.fromkeys(ids, now))
        if on_committed is not None:
            on_committed(ids)

    async def publish_market_changes(self, session):
        self.x.trace.append(("publish", tuple(session.rows)))


def bind(x, pending):
    r = Recording(x)
    r.adopt_pending(pending)
    x.ns["blend_refresher"] = r
    return r


async def test_pending_later_game_does_not_hold_first_commit_or_stamp():
    x = rig()
    r = bind(x, {200})
    task = asyncio.create_task(x.flush(flush_started=1000))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert x.committed == [1, 2]
        assert ("admit", (100,), (1, 2)) in x.trace
        assert not any(t[0] == "admit" and 200 in t[1] for t in x.trace)
        assert r.pending_event_ids() == frozenset({200})
        x.release.set()
        assert await asyncio.wait_for(task, 1)
        assert ("admit", (200,), (1, 2, 3)) in x.trace
        assert not r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_locked_debt_game_stays_owed_while_independent_game_commits():
    x = rig(locked={1})
    r = bind(x, {100})
    x.release.set()
    assert await x.flush(flush_started=1000) is False
    assert x.committed == [3, 9]
    assert set(x.batch) == {1, 2}
    assert r.pending_event_ids() == frozenset({100})
    assert not any(t[0] == "admit" and 100 in t[1] for t in x.trace)
    assert any(t[0] == "admit" and 200 in t[1] for t in x.trace)
    x.lock_released.set()
    assert await x.flush(flush_started=1002)
    assert not x.batch and not r.pending_event_ids()


async def test_late_bridge_to_future_phase_keeps_partial_board_excluded():
    x = rig()
    r = bind(x, {100})
    def bridge(_session, **kwargs):
        if 1 in kwargs["outcome_observed_at"]:
            x.events[3] = 100  # plan existed before this subscription bridge
    x.ns["queue_market_change"] = bridge
    task = asyncio.create_task(x.flush(flush_started=1000))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert x.committed == [1, 2]
        assert not any(t[0] == "admit" for t in x.trace)
        assert r.pending_event_ids() == frozenset({100})
        x.release.set()
        assert await asyncio.wait_for(task, 1)
        assert ("admit", (100,), (1, 2, 3)) in x.trace
        assert not r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_market_ack_late_bridge_recheck_keeps_new_event_owed_until_complete():
    x = rig()
    r = bind(x, {200})
    publish = r.publish_market_changes
    async def bridge_after_ack(session):
        await publish(session)
        if session.rows == [1, 2]:
            x.events[1] = x.events[2] = 200
    r.publish_market_changes = bridge_after_ack
    task = asyncio.create_task(x.flush(flush_started=1000))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert not any(t[0] == "admit" and 200 in t[1] for t in x.trace)
        assert r.pending_event_ids() == frozenset({200})
        x.release.set()
        assert await asyncio.wait_for(task, 1)
        assert ("admit", (200,), (1, 2, 3)) in x.trace
        assert not r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancel_joins_ready_stamp_and_keeps_excluded_and_committed_debt():
    x = rig()
    r = bind(x, {200})
    r.hold = True
    task = asyncio.create_task(x.flush(flush_started=1000))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        await asyncio.wait_for(r.entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert r.cleaned.is_set()
        assert r.pending_event_ids() == frozenset({100, 200})
        assert x.committed == [1, 2] and set(x.batch) == {3, 9}
    finally:
        x.release.set()
        r.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_budget_deferred_game_is_never_paid_by_final_implicit_refresh(monkeypatch):
    import app.tasks.live_blend_refresh as lbr
    from app.tasks.kalshi_ws import yield_written_nonlive_tail
    x = rig()
    r = bind(x, {200})
    x.ns["live_event_ids"] = {100}
    x.ns["yield_written_nonlive_tail"] = yield_written_nonlive_tail
    clock = [1000]
    publish = r.publish_market_changes
    async def pay_budget(session):
        await publish(session)
        clock[0] = 1004  # next nonlive phase starts at the actual budget edge
    r.publish_market_changes = pay_budget
    x.release.set()
    monkeypatch.setattr(lbr, "_mono", lambda: clock[0])
    assert await x.flush(flush_started=1000)
    assert x.committed == [1, 2] and set(x.batch) == {3, 9}
    assert r.pending_event_ids() == frozenset({200})
    assert not any(t[0] == "admit" and 200 in t[1] for t in x.trace)


def test_only_fenced_planner_caller_bypasses_debt_join_and_keeps_order():
    batch = {3: "later", 9: "tail", 1: "first", 2: "sibling"}
    markets, events = {1: 10, 2: 10, 3: 20, 9: 90}, {1: 100, 2: 100, 3: 200}
    assert linked_first_phases(batch, markets, events, {200}) == [
        {3: "later", 1: "first", 2: "sibling"}, {9: "tail"},
    ]
    assert linked_first_phases(batch, markets, events, {200}, {100}, True) == [
        {1: "first", 2: "sibling"}, {3: "later"}, {9: "tail"},
    ]
    assert linked_first_phases(batch, {**markets, 2: None}, events,
                               {200}, {100}, True) == [batch]
