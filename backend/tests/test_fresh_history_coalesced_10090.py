"""#10090 R3 — a broadcast `fresh=true` history read costs ≤ 2 builds per worker per view, not one per page.

The recovery pair (#10090 G1) re-reads detail AND history with `fresh=true`
when a page is told its held blend moved. That hint is broadcast to every open
page of the game, and detail has been coalesced since #9296 — but history was
not (`if fresh: await _build(publish=False)`), so one venue frame became one
full history build per viewer.

The route now runs the same #9296 barrier (`_coalesced_fresh_build`) under its
own cache key. Graded here against the real `get_event_odds_history_cached`
with only the build replaced:

* bounded — N fresh readers who arrive while one build runs share the NEXT
  build: 2 builds total, whatever N is;
* exact — no fresh reader is answered by a build that started before it asked;
  an older build's error or cancellation is never inherited;
* keyed — event, hours and range each separate views (#11186: equal hours is
  not the same view); the route reads no principal, and a guard says so;
* isolated — a cancelled reader's session is never used after it goes away,
  a waiter's cancellation leaves the shared build running, and a fresh body
  never lands in the ordinary history cache.

The controls prove the rig can see the stampede, and a build that outlives its
cancelled request, so neither guard is vacuous.
"""
import asyncio
import inspect
import json

import pytest
from fastapi import HTTPException

from app.routes import events as events_route
from app.utils import event_history_cache as ehc
from app.utils import request_cache as rc

EVENT_ID = 15324058
HOURS = 48
RANGE = "since_start"
N_READERS = 20

#: Every session a test made, so teardown can ask whether any was used after
#: its request went — including by a build nobody awaits any more.
_SESSIONS: list["_Session"] = []


class _Session:
    """One request's DB session. ``rev`` is the state a build on it would
    read; ``gate`` parks the build mid-flight so other readers arrive while it
    runs. ``closed`` is what `get_db`'s teardown does when the request goes."""

    def __init__(self, rev, gate, *, fail=None):
        self.rev = rev
        self.gate = gate
        self.fail = fail
        self.closed = False
        self.used_after_close = False
        self.builds = 0
        _SESSIONS.append(self)


def _used_after_close():
    return [s for s in _SESSIONS if s.used_after_close]


async def _fake_history(event_id, *, hours, chart_range, response, db, fresh):
    assert fresh is True
    await db.gate.wait()
    if db.closed:
        # Recorded, not only raised: a build that outlived its cancelled
        # request runs in a task nobody awaits, so its error is never read.
        db.used_after_close = True
        raise AssertionError("a build ran on a session whose request had gone")
    db.builds += 1
    # Still in flight when the other readers look: a real build yields on
    # every query, and an `Event` that is already set returns without yielding.
    await _settle()
    if db.fail is not None:
        raise db.fail
    response.headers["Cache-Control"] = "no-store"
    # A finished game's body: the one the history cache would hold longest, so
    # a fresh build that published would be seen by the next ordinary reader.
    ehc.mark_finished(True)
    # The pinned edge's VALUE and its revision come from the same read; a body
    # that mixed two builds would show it.
    return {
        "event_id": event_id,
        "hours": hours,
        "range": chart_range,
        "rev": db.rev,
        "blend_edge_value": db.rev / 10,
        "blend_edge_fold_revision": {str(event_id): db.rev},
    }


@pytest.fixture(autouse=True)
def rig(monkeypatch):
    monkeypatch.setattr(events_route, "get_event_odds_history", _fake_history)
    events_route._HISTORY_FRESH_BUILDS.clear()
    ehc._reset_for_tests()
    _SESSIONS.clear()
    yield
    assert events_route._HISTORY_FRESH_BUILDS == {}, "a finished build left its slot held"
    assert _used_after_close() == [], "a build ran on a session whose request had gone"
    _SESSIONS.clear()
    ehc._reset_for_tests()


async def _settle():
    for _ in range(20):
        await asyncio.sleep(0)


def _call(session, *, event_id=EVENT_ID, hours=HOURS, chart_range=RANGE, fresh=True):
    return events_route.get_event_odds_history_cached(
        event_id, hours=hours, chart_range=chart_range, response=None, db=session, fresh=fresh
    )


def _read(session, **kw):
    return asyncio.ensure_future(_call(session, **kw))


def _body(resp):
    return json.loads(resp.body)


async def _herd(*, leader_fail=None, cancel_leader=False):
    """One build already running on the old state; N readers arrive after it
    started, each carrying a session that would read the NEW state."""
    gate = asyncio.Event()
    leader_session = _Session(1, gate, fail=leader_fail)
    leader = _read(leader_session)
    await _settle()  # the leader is parked inside its build
    sessions = [_Session(2, gate) for _ in range(N_READERS)]
    readers = [_read(s) for s in sessions]
    await _settle()
    if cancel_leader:
        leader.cancel()
        await _settle()
        leader_session.closed = True  # its request is gone, and so is its session
    gate.set()
    leader_outcome = (await asyncio.gather(leader, return_exceptions=True))[0]
    results = await asyncio.gather(*readers)
    # Let any build that outlived its reader reach its session before
    # `asyncio.run` cancels it at shutdown and hides it.
    await _settle()
    builds = leader_session.builds + sum(s.builds for s in sessions)
    return leader_outcome, results, builds


def test_a_herd_arriving_mid_build_shares_one_next_build():
    leader, results, builds = asyncio.run(_herd())
    assert builds == 2, f"{N_READERS} fresh readers cost {builds} builds"
    # The leader reads the state it started on; nobody who asked after it began
    # is handed that answer — every reader gets the build that started after it.
    assert _body(leader)["rev"] == 1
    assert {r.body for r in results} == {results[0].body}
    body = _body(results[0])
    assert (body["rev"], body["blend_edge_value"], body["blend_edge_fold_revision"]) == (
        2, 0.2, {str(EVENT_ID): 2},
    )
    # Every reader still gets its own response with the build's headers.
    assert len({id(r) for r in results}) == N_READERS
    assert all(r.headers["x-feed-cache"] == "bypass" for r in results)
    assert all(r.headers["cache-control"] == "no-store" for r in results)


def test_control_without_the_barrier_the_rig_sees_the_stampede(monkeypatch):
    async def _uncoalesced(_builds, _key, _asked_at, build, **_kw):
        return await build()

    monkeypatch.setattr(events_route, "_coalesced_fresh_build", _uncoalesced)
    _leader, _results, builds = asyncio.run(_herd())
    assert builds == N_READERS + 1


def test_an_older_builds_failure_is_not_inherited():
    leader, results, builds = asyncio.run(_herd(leader_fail=RuntimeError("db went away")))
    assert isinstance(leader, RuntimeError)
    assert builds == 2
    assert all(_body(r)["rev"] == 2 for r in results)


def test_a_cancelled_leader_elects_a_new_build_on_a_live_session():
    """The cancelled reader's build stops with it; its waiters are not
    cancelled, and the build that answers them runs on one of THEIR sessions,
    never on the session `get_db` has closed."""
    leader, results, builds = asyncio.run(_herd(cancel_leader=True))
    assert isinstance(leader, asyncio.CancelledError)
    assert builds == 1  # the cancelled leader never finished its build
    assert all(_body(r)["rev"] == 2 for r in results)
    assert _used_after_close() == []


def test_control_a_build_that_outlives_its_cancelled_leader_is_seen(monkeypatch):
    """The guard above must be able to fail. Shield the leader's build so it
    keeps running after its request is cancelled — its waiters are still
    answered correctly and the leader still reads as cancelled, so only the
    closed session can tell. The rig must see it."""
    barrier = events_route._coalesced_fresh_build

    async def _shielding(builds, key, asked_at, build, **kw):
        return await barrier(builds, key, asked_at, lambda: asyncio.shield(build()), **kw)

    monkeypatch.setattr(events_route, "_coalesced_fresh_build", _shielding)
    leader, results, builds = asyncio.run(_herd(cancel_leader=True))
    assert isinstance(leader, asyncio.CancelledError)
    assert all(_body(r)["rev"] == 2 for r in results)
    assert len(_used_after_close()) == 1
    _SESSIONS.clear()  # seen; teardown's guard is for the real route


def test_a_waiters_cancellation_leaves_the_shared_build_running():
    async def scenario():
        gate = asyncio.Event()
        first = _read(_Session(1, gate))
        await _settle()
        sessions = [_Session(2, gate) for _ in range(4)]
        tasks = [_read(s) for s in sessions]
        await _settle()
        gate.set()
        await first
        for _ in range(100):  # until the next generation's build is in flight
            building = [i for i, s in enumerate(sessions) if s.builds == 1]
            if building:
                break
            await asyncio.sleep(0)
        assert len(building) == 1
        quitter = next(i for i in range(4) if i not in building)
        tasks[quitter].cancel()
        sessions[quitter].closed = True
        outcomes = await asyncio.gather(first, *tasks, return_exceptions=True)
        assert not any(t.cancelled() for i, t in enumerate(tasks) if i != quitter)
        return outcomes, quitter, sum(s.builds for s in sessions)

    outcomes, quitter, next_builds = asyncio.run(scenario())
    assert next_builds == 1
    assert isinstance(outcomes[1 + quitter], asyncio.CancelledError)
    rest = [o for i, o in enumerate(outcomes[1:]) if i != quitter]
    assert all(_body(o)["rev"] == 2 for o in rest)


def test_same_generation_readers_share_the_builds_error():
    async def scenario():
        gate = asyncio.Event()
        leader = _read(_Session(1, gate))
        await _settle()
        # The next generation's elected builder fails: that IS their answer.
        failing = _Session(2, gate, fail=HTTPException(status_code=404, detail="Event not found"))
        others = [_Session(2, gate) for _ in range(3)]
        tasks = [_read(s) for s in [failing, *others]]
        await _settle()
        gate.set()
        await leader
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        return outcomes, failing.builds + sum(s.builds for s in others)

    outcomes, next_builds = asyncio.run(scenario())
    assert next_builds == 1
    assert all(isinstance(o, HTTPException) and o.status_code == 404 for o in outcomes)


def test_a_reader_arriving_after_the_build_finished_gets_a_new_build():
    async def scenario():
        gate = asyncio.Event()
        gate.set()
        first = await _call(_Session(1, gate))
        later_session = _Session(2, gate)
        later = await _call(later_session)
        return first, later, later_session.builds

    first, later, later_builds = asyncio.run(scenario())
    assert later_builds == 1
    assert (_body(first)["rev"], _body(later)["rev"]) == (1, 2)


def test_distinct_views_never_share_a_build():
    """Event, hours and range each name a different body. Equal hours with a
    different range is a different view (#11186), and so is the other way."""
    views = [
        dict(event_id=EVENT_ID, hours=HOURS, chart_range="all"),
        dict(event_id=EVENT_ID, hours=HOURS, chart_range="since_start"),
        dict(event_id=EVENT_ID, hours=720, chart_range="all"),
        dict(event_id=EVENT_ID + 1, hours=HOURS, chart_range="all"),
    ]

    async def scenario():
        gate = asyncio.Event()
        sessions = [_Session(i, gate) for i in range(len(views))]
        tasks = [_read(s, **v) for s, v in zip(sessions, views)]
        await _settle()
        gate.set()
        return await asyncio.gather(*tasks), sum(s.builds for s in sessions)

    results, builds = asyncio.run(scenario())
    assert builds == len(views)
    got = [(_body(r)["event_id"], _body(r)["hours"], _body(r)["range"], _body(r)["rev"]) for r in results]
    want = [(v["event_id"], v["hours"], v["chart_range"], i) for i, v in enumerate(views)]
    assert got == want


def test_a_different_view_queued_behind_the_same_build_gets_its_own():
    """The case a too-coarse key would break: two views of one event arrive
    while a build of the first view runs. With the full key the second view
    was never in that queue and builds on arrival; with a key that dropped the
    range, both would share the next build and one would get the other's body."""

    async def scenario():
        gate = asyncio.Event()
        first = _read(_Session(0, gate), chart_range="all")
        await _settle()
        same_view = _read(_Session(1, gate), chart_range="all")
        other_view = _read(_Session(2, gate), chart_range="since_start")
        await _settle()
        gate.set()
        return await asyncio.gather(first, same_view, other_view)

    first, same_view, other_view = asyncio.run(scenario())
    assert (_body(first)["range"], _body(first)["rev"]) == ("all", 0)
    assert (_body(same_view)["range"], _body(same_view)["rev"]) == ("all", 1)
    assert (_body(other_view)["range"], _body(other_view)["rev"]) == ("since_start", 2)


def test_the_fresh_body_stays_out_of_the_ordinary_cache(monkeypatch):
    """The barrier changes how many builds run, not where a fresh body goes:
    nothing is written to the history cache or its single-flight registry, and
    the next ordinary reader builds for itself."""
    ordinary = []

    async def scenario():
        gate = asyncio.Event()
        gate.set()
        await _call(_Session(1, gate))
        assert ehc.read(ehc.cache_key(EVENT_ID, HOURS, RANGE)) is None
        assert not any("event_history:" in str(k) for k in rc._inflight)

        async def _ordinary_build(event_id, *, hours, chart_range, response, db, fresh):
            ordinary.append(fresh)
            return {"rev": 9}

        monkeypatch.setattr(events_route, "get_event_odds_history", _ordinary_build)
        return await _call(_Session(9, gate), fresh=False)

    resp = asyncio.run(scenario())
    assert ordinary == [False]
    assert resp.headers["x-feed-cache"] == "miss"


def test_the_key_is_every_input_the_route_reads():
    """The coalescing key is `ehc.cache_key(event_id, hours, range)`. That is
    sound only while those are the route's only semantic inputs: a principal,
    a header or another query parameter would make two readers of one key ask
    different questions. Adding one must come with a key that carries it."""
    route = set(inspect.signature(events_route.get_event_odds_history_cached).parameters)
    assert route == {"event_id", "hours", "chart_range", "response", "db", "fresh"}
    source = inspect.getsource(events_route.get_event_odds_history_cached)
    assert "key = ehc.cache_key(event_id, hours, chart_range)" in source
    assert "_coalesced_fresh_build(\n            _HISTORY_FRESH_BUILDS, key," in source
