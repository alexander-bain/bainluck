"""Event chart history cache — Alex Oct 8 load-speed push (#10090, #1469).

The route wrapper `get_event_odds_history_cached` answers a repeat reader from
memory instead of rebuilding the chart. Root scope (Oct 8): finished games only,
45 s; a partial body (a read the build swallowed) and `fresh=true` never touch
the store; a waiter never starts a second build beside a live leader.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.routes import events as events_route
from app.utils import event_history_cache as ehc

NOW = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


def _payload(status, marker=0, refill=None):
    return {
        "event_id": 7,
        "status": status,
        "aggregate_line": [{"t": "2026-10-08T13:00:00+00:00", "p": 0.5}],
        "marker": marker,
        "on_demand_backfill": refill,
    }


def _marks(finished=True, partial=False):
    m = ehc.BuildMarks()
    m.finished, m.partial = finished, partial
    return m


class TestLease:
    def test_finished_is_45s(self):
        assert ehc.lease_for(_marks(), _payload("completed")) == ehc.FINISHED_TTL == 45.0

    def test_not_finished_is_never_stored(self):
        assert ehc.lease_for(_marks(finished=False), _payload("live")) == 0.0

    def test_partial_finished_is_never_stored(self):
        assert ehc.lease_for(_marks(partial=True), _payload("completed")) == 0.0

    def test_enqueued_refill_is_never_stored(self):
        p = _payload("completed", refill={"enqueue": True, "reason": "thin"})
        assert ehc.lease_for(_marks(), p) == 0.0

    def test_declined_refill_is_stored(self):
        p = _payload("completed", refill={"enqueue": False, "reason": "no_venue_markets"})
        assert ehc.lease_for(_marks(), p) == ehc.FINISHED_TTL

    def test_marks_outside_a_build_are_inert(self):
        ehc.mark_partial()
        ehc.mark_finished(True)  # no marks installed: must not raise

    def test_marks_land_on_the_installed_build_only(self):
        marks, token = ehc.begin_marks()
        try:
            ehc.mark_finished(True)
            ehc.mark_partial()
        finally:
            ehc.end_marks(token)
        assert (marks.finished, marks.partial) == (True, True)
        ehc.mark_finished(False)
        assert marks.finished is True


class TestStore:
    def test_expires_at_lease(self):
        k = ehc.cache_key(1, 48, "since_start")
        ehc.write(k, b"{}", None, 10.0, now=100.0)
        assert ehc.read(k, now=109.9) == (b"{}", None)
        assert ehc.read(k, now=110.0) is None
        assert ehc.total_bytes() == 0

    def test_byte_bound_evicts_oldest(self, monkeypatch):
        monkeypatch.setattr(ehc, "MAX_BYTES", 10)
        ehc.write(ehc.cache_key(1, 1, "all"), b"123456", None, 60, now=0)
        ehc.write(ehc.cache_key(2, 1, "all"), b"123456", None, 60, now=0)
        assert ehc.read(ehc.cache_key(1, 1, "all"), now=1) is None
        assert ehc.read(ehc.cache_key(2, 1, "all"), now=1) == (b"123456", None)
        assert ehc.total_bytes() == 6

    def test_oversized_body_not_cached(self, monkeypatch):
        monkeypatch.setattr(ehc, "MAX_ENTRY_BYTES", 3)
        ehc.write(ehc.cache_key(1, 1, "all"), b"1234", None, 60, now=0)
        assert ehc.read(ehc.cache_key(1, 1, "all"), now=1) is None


def _install_build(monkeypatch, payloads, cache_control=None, delay=0.0, partial=False):
    """A stand-in build that leaves the marks the real one does: finished for a
    `completed` payload, partial when told a read was swallowed."""
    calls = []

    async def fake_build(event_id, *, hours, chart_range, response, db, fresh):
        calls.append((event_id, hours, chart_range, fresh))
        if delay:
            await asyncio.sleep(delay)
        if cache_control:
            response.headers["Cache-Control"] = cache_control
        item = payloads[min(len(calls) - 1, len(payloads) - 1)]
        if isinstance(item, Exception):
            raise item
        ehc.mark_finished(item.get("status") == "completed")
        if partial:
            ehc.mark_partial()
        return item

    monkeypatch.setattr(events_route, "get_event_odds_history", fake_build)
    return calls


async def _get(event_id=7, hours=48, chart_range="since_start", fresh=False):
    return await events_route.get_event_odds_history_cached(
        event_id, hours=hours, chart_range=chart_range, response=None, db=None, fresh=fresh
    )


class TestRoute:
    @pytest.mark.asyncio
    async def test_second_reader_is_served_from_memory(self, monkeypatch):
        calls = _install_build(
            monkeypatch,
            [_payload("completed", 1), _payload("completed", 2)],
            cache_control="public, max-age=3600, stale-while-revalidate=300",
        )
        first = await _get()
        second = await _get()
        assert len(calls) == 1
        assert first.body == second.body
        assert json.loads(second.body)["marker"] == 1
        assert first.headers["x-feed-cache"] == "miss"
        assert second.headers["x-feed-cache"] == "hit"
        assert second.headers["cache-control"].startswith("public, max-age=3600")

    @pytest.mark.asyncio
    async def test_finished_entry_expires_at_45s(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(ehc.time, "time", lambda: clock[0])
        calls = _install_build(monkeypatch, [_payload("completed", 1), _payload("completed", 2)])
        await _get()
        clock[0] += 44.9
        assert json.loads((await _get()).body)["marker"] == 1
        clock[0] += 0.1
        assert json.loads((await _get()).body)["marker"] == 2
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_live_is_never_served_from_memory(self, monkeypatch):
        calls = _install_build(monkeypatch, [_payload("live", 1), _payload("live", 2)])
        await _get()
        second = await _get()
        assert len(calls) == 2
        assert json.loads(second.body)["marker"] == 2
        assert ehc.total_bytes() == 0

    @pytest.mark.asyncio
    async def test_partial_finished_body_is_served_but_not_kept(self, monkeypatch):
        calls = _install_build(
            monkeypatch, [_payload("completed", 1), _payload("completed", 2)], partial=True
        )
        first = await _get()
        second = await _get()
        assert json.loads(first.body)["marker"] == 1
        assert json.loads(second.body)["marker"] == 2
        assert len(calls) == 2
        assert ehc.total_bytes() == 0

    @pytest.mark.asyncio
    async def test_params_are_part_of_the_key(self, monkeypatch):
        calls = _install_build(
            monkeypatch, [_payload("completed", 1), _payload("completed", 2)]
        )
        await _get(chart_range="since_start")
        other = await _get(chart_range="all")
        assert len(calls) == 2
        assert json.loads(other.body)["marker"] == 2

    @pytest.mark.asyncio
    async def test_fresh_neither_reads_nor_writes(self, monkeypatch):
        calls = _install_build(
            monkeypatch,
            [_payload("completed", 1), _payload("completed", 2), _payload("completed", 3)],
        )
        await _get()
        fresh = await _get(fresh=True)
        after = await _get()
        assert [c[3] for c in calls] == [False, True]
        assert json.loads(fresh.body)["marker"] == 2
        assert fresh.headers["x-feed-cache"] == "bypass"
        assert json.loads(after.body)["marker"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_readers_share_one_build(self, monkeypatch):
        calls = _install_build(monkeypatch, [_payload("live", 1)], delay=0.05)
        results = await asyncio.gather(*[_get() for _ in range(5)])
        assert len(calls) == 1
        assert {r.body for r in results} == {results[0].body}
        assert sorted(r.headers["x-feed-cache"] for r in results) == ["coalesced"] * 4 + ["miss"]

    @pytest.mark.asyncio
    async def test_slow_leader_never_gets_a_second_build(self, monkeypatch):
        # The first version bounded the waiter at 25 s and then built its own
        # beside the still-running leader. Shrink every `wait_for` bound so a
        # waiter that still has one times out here — and must still not build.
        real_wait_for = asyncio.wait_for

        async def short_wait_for(aw, timeout=None):
            return await real_wait_for(aw, timeout=0.01)

        monkeypatch.setattr(asyncio, "wait_for", short_wait_for)
        gate = asyncio.Event()
        calls = []

        async def slow_build(event_id, *, hours, chart_range, response, db, fresh):
            calls.append(fresh)
            await gate.wait()
            ehc.mark_finished(True)
            return _payload("completed", 1)

        monkeypatch.setattr(events_route, "get_event_odds_history", slow_build)
        leader = asyncio.create_task(_get())
        await asyncio.sleep(0)
        waiters = [asyncio.create_task(_get()) for _ in range(3)]
        await asyncio.sleep(0.05)
        assert len(calls) == 1 and not any(w.done() for w in waiters)
        gate.set()
        results = await asyncio.gather(leader, *waiters)
        assert len(calls) == 1
        assert sorted(r.headers["x-feed-cache"] for r in results) == ["coalesced"] * 3 + ["miss"]

    @pytest.mark.asyncio
    async def test_failed_leader_hands_off_to_exactly_one_waiter(self, monkeypatch):
        calls = _install_build(
            monkeypatch,
            [RuntimeError("leader failed"), _payload("completed", 2)],
            delay=0.05,
        )
        results = await asyncio.gather(*[_get() for _ in range(4)], return_exceptions=True)
        assert sum(isinstance(r, RuntimeError) for r in results) == 1
        served = [r for r in results if not isinstance(r, Exception)]
        assert len(served) == 3
        assert {json.loads(r.body)["marker"] for r in served} == {2}
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_404_is_not_cached(self, monkeypatch):
        calls = _install_build(
            monkeypatch, [HTTPException(status_code=404, detail="Event not found")]
        )
        for _ in range(2):
            with pytest.raises(HTTPException):
                await _get()
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_body_is_what_fastapi_would_have_serialized(self, monkeypatch):
        p = _payload("completed")
        _install_build(monkeypatch, [p])
        resp = await _get()
        assert json.loads(resp.body) == p
        assert resp.media_type == "application/json"


# --- the REAL build behind the wrapper (Root's rig, Oct 8) --------------------


def _real_rig(monkeypatch, *, live=False, fail_scores=False):
    from app.tasks import event_chart_backfill
    from tests.test_history_window_budget_6921 import (
        EVENT_ID,
        _finished_event,
        _kickoff,
        _snapshot,
    )
    from tests.test_price_table_fold_6390 import _HistoryRouteSession

    async def no_refill(*args, **kwargs):
        return None

    monkeypatch.setattr(event_chart_backfill, "plan_on_demand_fill", no_refill)
    kickoff = _kickoff()
    event = _finished_event(kickoff)
    if live:
        event.status, event.completed_at = "live", None

    class Session(_HistoryRouteSession):
        reads = 0

        async def execute(self, statement, *args, **kwargs):
            self.reads += 1
            if fail_scores and "score_snapshots" in str(statement):
                raise RuntimeError("score read failed")
            return await super().execute(statement, *args, **kwargs)

    session = Session(event, [], [
        _snapshot(kickoff - timedelta(minutes=5), snap_id=1),
        _snapshot(kickoff + timedelta(minutes=5), snap_id=2),
    ])

    async def call():
        return await events_route.get_event_odds_history_cached(
            EVENT_ID, hours=48, chart_range="all", response=None, db=session, fresh=False
        )

    return call, session


class TestRealBuild:
    @pytest.mark.asyncio
    async def test_finished_chart_is_kept(self, monkeypatch):
        call, session = _real_rig(monkeypatch)
        first = await call()
        reads = session.reads
        second = await call()
        assert session.reads == reads
        assert second.body == first.body and second.headers["x-feed-cache"] == "hit"

    @pytest.mark.asyncio
    async def test_live_chart_is_not_kept(self, monkeypatch):
        call, session = _real_rig(monkeypatch, live=True)
        await call()
        reads = session.reads
        await call()
        assert session.reads > reads
        assert ehc.total_bytes() == 0

    @pytest.mark.asyncio
    async def test_swallowed_score_read_is_not_kept(self, monkeypatch):
        call, session = _real_rig(monkeypatch, fail_scores=True)
        first = await call()
        assert json.loads(first.body)["score_history"] == []
        reads = session.reads
        await call()
        assert session.reads > reads
        assert ehc.total_bytes() == 0
