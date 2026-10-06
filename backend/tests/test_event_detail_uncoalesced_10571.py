"""Caller-owned canonical reads cannot spend another session's snapshot or cache it."""
import asyncio

import pytest

from app.routes import events as route
from tests.test_blend_fold_chart_pin_parity_3911 import CANON_ID, GHOST_ID, _now
from tests.test_fold_revision_9051 import _vector, both_routes as _revision_routes
from tests.test_fresh_detail_coalesced_9296 import _GatedSession, _herd, _new, _old, _settle


@pytest.fixture
def routes(monkeypatch):
    rig = _revision_routes.__wrapped__(monkeypatch)
    rig.cache.clear()
    route._DETAIL_FRESH_BUILDS.clear()
    yield rig
    rig.cache.clear()
    assert route._DETAIL_FRESH_BUILDS == {}


def _assert_flags_reset():
    assert route._detail_fresh_leader.get() is False
    assert route._detail_skip_cache_publish.get() is False


async def _ordinary_reads_still_coalesce():
    # A leaked leader costs 21 builds; a publication leak leaves no cache entry.
    _, results, builds = await _herd(_now())
    assert builds == 2
    assert all(result is results[0] for result in results)
    assert route._event_detail_cache[CANON_ID][2] is results[0]
    _assert_flags_reset()


def test_seam_preserves_full_cache_and_slots_and_builds_caller_response(routes, monkeypatch):
    async def scenario():
        now = _now()
        gate = asyncio.Event()
        gate.set()
        monkeypatch.setattr(route, "_EVENT_DETAIL_MAX_SIZE", 3)
        cached = {"old": True}
        slots = {CANON_ID: (float("inf"), object()), GHOST_ID: (1.0, object())}
        route._DETAIL_FRESH_BUILDS.update(slots)
        routes.cache.update({key: (float("inf"), "live", cached)
                             for key in (CANON_ID, GHOST_ID, -1)})
        before = dict(routes.cache)
        session = _new(now, gate)
        calls = []
        original_get_event = route.get_event
        async def tracked_get_event(event_id, db, fresh=False):
            calls.append((event_id, db, fresh))
            return await original_get_event(event_id, db=db, fresh=fresh)
        monkeypatch.setattr(route, "get_event", tracked_get_event)
        actual = await route.build_event_detail_uncoalesced(session, CANON_ID)
        assert calls == [(CANON_ID, session, True)]
        assert session.blend_fold_lookups == 1
        assert actual["blend_fold_revision"] == _vector(5, 10)
        assert actual["hero_probability"] == pytest.approx(0.15)
        assert routes.cache == before
        assert all(routes.cache[key] is before[key] for key in before)
        assert route._DETAIL_FRESH_BUILDS == slots
        _assert_flags_reset()
        route._DETAIL_FRESH_BUILDS.clear()
        routes.cache.clear()
        expected = await route.get_event(CANON_ID, db=_new(now, gate), fresh=True)
        assert actual == expected, "Reuse all canonical response semantics"
    asyncio.run(scenario())


def test_seam_never_waits_for_or_returns_another_callers_live_build(routes):
    async def scenario():
        now = _now()
        held_gate = asyncio.Event()
        old_session = _old(now, held_gate)
        old_task = asyncio.create_task(route.get_event(CANON_ID, db=old_session, fresh=True))
        await _settle()
        slots = dict(route._DETAIL_FRESH_BUILDS)
        own_gate = asyncio.Event()
        own_gate.set()
        own_session = _new(now, own_gate)
        try:
            actual = await asyncio.wait_for(
                route.build_event_detail_uncoalesced(own_session, CANON_ID), timeout=2)
            assert not old_task.done()
            assert actual["blend_fold_revision"] == _vector(5, 10)
            assert own_session.blend_fold_lookups == 1
            assert route._DETAIL_FRESH_BUILDS == slots
            assert routes.cache == {}
        finally:
            held_gate.set()
            old = await old_task
        assert old["blend_fold_revision"] == _vector(4, 9)
    asyncio.run(scenario())


def test_success_resets_flags_and_normal_fresh_reads_still_coalesce(routes):
    async def scenario():
        gate = asyncio.Event()
        gate.set()
        await route.build_event_detail_uncoalesced(_new(_now(), gate), CANON_ID)
        assert routes.cache == {}
        await _ordinary_reads_still_coalesce()
    asyncio.run(scenario())


def test_exception_resets_flags_and_normal_fresh_reads_still_coalesce(routes):
    async def scenario():
        gate = asyncio.Event()
        gate.set()
        failing = _GatedSession(_now(), gate, fail=True, canon_rev=5, twin_rev=10)
        with pytest.raises(RuntimeError, match="database went away"):
            await route.build_event_detail_uncoalesced(failing, CANON_ID)
        assert routes.cache == {}
        assert route._DETAIL_FRESH_BUILDS == {}
        await _ordinary_reads_still_coalesce()
    asyncio.run(scenario())


def test_cancellation_resets_in_same_context_before_normal_fresh_read(routes):
    async def scenario():
        gate = asyncio.Event()
        async def caller():
            try:
                await route.build_event_detail_uncoalesced(_new(_now(), gate), CANON_ID)
            except asyncio.CancelledError:
                assert routes.cache == {}
                assert route._DETAIL_FRESH_BUILDS == {}
                await _ordinary_reads_still_coalesce()
            else:
                pytest.fail("Expected held caller cancellation")
        task = asyncio.create_task(caller())
        await _settle()
        task.cancel()
        await task
    asyncio.run(scenario())


def test_nested_private_context_values_are_restored(routes):
    async def scenario():
        gate = asyncio.Event()
        gate.set()
        leader = route._detail_fresh_leader.set(True)
        cache = route._detail_skip_cache_publish.set(True)
        try:
            await route.build_event_detail_uncoalesced(_new(_now(), gate), CANON_ID)
            assert route._detail_fresh_leader.get() is True
            assert route._detail_skip_cache_publish.get() is True
            assert routes.cache == {}
        finally:
            route._detail_skip_cache_publish.reset(cache)
            route._detail_fresh_leader.reset(leader)
        _assert_flags_reset()
    asyncio.run(scenario())
