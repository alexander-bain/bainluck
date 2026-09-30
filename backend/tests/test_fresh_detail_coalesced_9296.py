"""#9296 — a broadcast `fresh=true` detail read costs ≤ 2 builds per worker, not one per page.

#9295 relays a folded contributor's venue frame to EVERY open page of the game
as a price-less invalidation, and #9296 answers it with `?fresh=true`, which
bypasses `_event_detail_cache`. Uncoalesced, N viewers make N full detail
builds per venue frame, all in the same second. The barrier's two promises,
graded here against the real `get_event` body:

* bounded — N fresh readers who arrive while one build runs share the NEXT
  build: 2 builds total, whatever N is;
* exact — no fresh reader is ever answered by a build that started before it
  asked (that build may predate the write it was told about), and an older
  build's error or cancellation is never inherited.

The control proves the rig can see the stampede, so the bound is not vacuous.
"""
import asyncio

import pytest

from app.routes import events as events_route
from app.routes.events import get_event
from tests.test_blend_fold_chart_pin_parity_3911 import CANON_ID, _now
from tests.test_fold_revision_9051 import _RevisionedSession, _vector, both_routes as _revision_routes
from tests.test_series_fold_3810 import is_blend_fold

N_READERS = 20


@pytest.fixture
def routes(monkeypatch):
    rig = _revision_routes.__wrapped__(monkeypatch)
    rig.cache.clear()
    events_route._DETAIL_FRESH_BUILDS.clear()
    yield rig
    rig.cache.clear()
    assert events_route._DETAIL_FRESH_BUILDS == {}, "a finished build left its slot held"


class _GatedSession(_RevisionedSession):
    """Holds its build inside the fold read until the test opens the gate, so
    other readers arrive while it is IN FLIGHT — the herd's actual shape."""

    def __init__(self, now, gate, *, fail=False, **kw):
        super().__init__(now, **kw)
        self.gate = gate
        self.fail = fail

    async def execute(self, statement, *a, **kw):
        if is_blend_fold(" ".join(str(statement).split())):
            await self.gate.wait()
            if self.fail:
                self.blend_fold_lookups += 1
                # Still in flight when the other readers look — a real query
                # yields; this fake would otherwise finish before they wake.
                await _settle()
                raise RuntimeError("database went away mid-build")
        return await super().execute(statement, *a, **kw)


def _old(now, gate, **kw):
    return _GatedSession(now, gate, canon_rev=4, twin_rev=9, canon=0.6, twin=0.4, **kw)


def _new(now, gate):
    return _GatedSession(now, gate, canon_rev=5, twin_rev=10, canon=0.2, twin=0.1)


async def _settle():
    for _ in range(20):
        await asyncio.sleep(0)


async def _herd(now, *, leader_kw=None, cancel_leader=False):
    """One build already running on the old state; N readers arrive after it
    started, each carrying a session that would read the NEW state."""
    gate = asyncio.Event()
    leader_session = _old(now, gate, **(leader_kw or {}))
    leader = asyncio.ensure_future(get_event(CANON_ID, db=leader_session, fresh=True))
    await _settle()  # the leader is parked inside its fold read
    sessions = [_new(now, gate) for _ in range(N_READERS)]
    readers = [asyncio.ensure_future(get_event(CANON_ID, db=s, fresh=True)) for s in sessions]
    await _settle()
    if cancel_leader:
        leader.cancel()
        await _settle()
    gate.set()
    leader_outcome = (await asyncio.gather(leader, return_exceptions=True))[0]
    results = await asyncio.gather(*readers)
    builds = leader_session.blend_fold_lookups + sum(s.blend_fold_lookups for s in sessions)
    return leader_outcome, results, builds


def test_a_herd_arriving_mid_build_shares_one_next_build(routes):
    leader, results, builds = asyncio.run(_herd(_now()))
    assert builds == 2, f"{N_READERS} fresh readers cost {builds} builds"
    # The leader reads the state it started on; nobody who asked after it began
    # is handed that answer — every reader gets the build that started after it.
    assert leader["blend_fold_revision"] == _vector(4, 9)
    for payload in results:
        assert payload["blend_fold_revision"] == _vector(5, 10)
        assert payload["hero_probability"] == pytest.approx(0.15)
    assert all(payload is results[0] for payload in results)
    # And the ordinary cache now holds the newest build for everyone else.
    assert routes.cache[CANON_ID][2] is results[0]


def test_control_without_the_barrier_the_rig_sees_the_stampede(routes, monkeypatch):
    async def _uncoalesced(_event_id, _asked_at, build):
        token = events_route._detail_fresh_leader.set(True)
        try:
            return await build()
        finally:
            events_route._detail_fresh_leader.reset(token)

    monkeypatch.setattr(events_route, "_coalesced_fresh_detail", _uncoalesced)
    _leader, _results, builds = asyncio.run(_herd(_now()))
    assert builds == N_READERS + 1


def test_an_older_builds_failure_is_not_inherited(routes):
    leader, results, builds = asyncio.run(_herd(_now(), leader_kw={"fail": True}))
    assert isinstance(leader, RuntimeError)
    assert builds == 2
    for payload in results:
        assert payload["blend_fold_revision"] == _vector(5, 10)


def test_a_cancelled_build_elects_a_new_one_instead_of_cancelling_its_waiters(routes):
    leader, results, builds = asyncio.run(_herd(_now(), cancel_leader=True))
    assert isinstance(leader, asyncio.CancelledError)
    assert builds == 1  # the cancelled leader never finished its fold read
    for payload in results:
        assert payload["blend_fold_revision"] == _vector(5, 10)


def test_same_generation_readers_share_the_builds_error(routes):
    async def scenario():
        now = _now()
        gate = asyncio.Event()
        first = _old(now, gate)
        leader = asyncio.ensure_future(get_event(CANON_ID, db=first, fresh=True))
        await _settle()
        # The next generation's elected builder fails: that IS their answer.
        failing = _GatedSession(now, gate, fail=True, canon_rev=5, twin_rev=10)
        others = [_new(now, gate) for _ in range(3)]
        tasks = [asyncio.ensure_future(get_event(CANON_ID, db=s, fresh=True))
                 for s in [failing, *others]]
        await _settle()
        gate.set()
        await leader
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        return outcomes, failing.blend_fold_lookups + sum(s.blend_fold_lookups for s in others)

    outcomes, next_builds = asyncio.run(scenario())
    assert next_builds == 1
    assert all(isinstance(o, RuntimeError) for o in outcomes)


def test_a_reader_arriving_after_the_build_finished_gets_a_new_build(routes):
    async def scenario():
        now = _now()
        gate = asyncio.Event()
        gate.set()
        first = await get_event(CANON_ID, db=_old(now, gate), fresh=True)
        later_session = _new(now, gate)
        later = await get_event(CANON_ID, db=later_session, fresh=True)
        return first, later, later_session.blend_fold_lookups

    first, later, later_builds = asyncio.run(scenario())
    assert later_builds == 1
    assert first["blend_fold_revision"] == _vector(4, 9)
    assert later["blend_fold_revision"] == _vector(5, 10)


def test_the_leader_flag_does_not_leak_into_ordinary_reads(routes):
    async def scenario():
        now = _now()
        gate = asyncio.Event()
        gate.set()
        built = await get_event(CANON_ID, db=_old(now, gate), fresh=True)
        assert events_route._detail_fresh_leader.get() is False
        cached_session = _new(now, gate)
        served = await get_event(CANON_ID, db=cached_session)
        return built, served, cached_session.blend_fold_lookups

    built, served, lookups = asyncio.run(scenario())
    assert served is built
    assert lookups == 0
