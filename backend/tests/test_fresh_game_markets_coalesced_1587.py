"""#1587 — a broadcast `fresh=true` game-markets read costs ≤ 2 builds per worker, not one per page.

Measured 2026-10-10 01:40Z on production: an open live game page re-reads
`/api/events/{id}/game-markets?fresh=true` every 2 s off the market stream
(`useGameMarketsStream` → `createFuturesReadScheduler`), and `fresh` bypassed
every cache tier with no coalescing, so each read was its own full build
(NCAAF 15324058: 5,985 / 2,494 / 2,940 / 2,031 ms back to back, one tab). The
slow-request log held same-millisecond PAIRS of these builds — two pages told
of the same market frame, each paying for it.

The route now runs the #9296 barrier (`_coalesced_fresh_build`). Its two
promises, graded here against the real `get_game_markets` with only the build
replaced:

* bounded — N fresh readers who arrive while one build runs share the NEXT
  build: 2 builds total, whatever N is;
* exact — no fresh reader is ever answered by a build that started before it
  asked, and an older build's error or cancellation is never inherited.

The control proves the rig can see the stampede, so the bound is not vacuous.
"""
import asyncio

import pytest

from app.routes import events as events_route
from app.routes.events import get_game_markets

EVENT_ID = 15324058
N_READERS = 20


class _Session:
    """Stands in for one request's DB session. ``rev`` is the state a build on
    this session would read; ``gate`` parks the build mid-flight so other
    readers arrive while it runs — the herd's actual shape."""

    def __init__(self, rev, gate, *, fail=False):
        self.rev = rev
        self.gate = gate
        self.fail = fail
        self.builds = 0


async def _fake_build(event_id, db):
    await db.gate.wait()
    db.builds += 1
    # Still in flight when the other readers look: a real build yields on every
    # query, and an `Event` that is already set returns without yielding at all.
    await _settle()
    if db.fail:
        raise RuntimeError("database went away mid-build")
    return {"event_id": event_id, "rev": db.rev, "totals": [], "player_props": []}, "live", [1, 2]


@pytest.fixture(autouse=True)
def rig(monkeypatch):
    monkeypatch.setattr(events_route, "_build_game_markets", _fake_build)
    events_route._GAME_MARKETS_FRESH_BUILDS.clear()
    yield
    assert events_route._GAME_MARKETS_FRESH_BUILDS == {}, "a finished build left its slot held"


async def _settle():
    for _ in range(20):
        await asyncio.sleep(0)


def _read(session):
    return asyncio.ensure_future(get_game_markets(EVENT_ID, db=session, fresh=True, response=None))


async def _herd(*, leader_fail=False, cancel_leader=False):
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
    gate.set()
    leader_outcome = (await asyncio.gather(leader, return_exceptions=True))[0]
    results = await asyncio.gather(*readers)
    builds = leader_session.builds + sum(s.builds for s in sessions)
    return leader_outcome, results, builds


def test_a_herd_arriving_mid_build_shares_one_next_build():
    leader, results, builds = asyncio.run(_herd())
    assert builds == 2, f"{N_READERS} fresh readers cost {builds} builds"
    # The leader reads the state it started on; nobody who asked after it began
    # is handed that answer — every reader gets the build that started after it.
    assert leader["rev"] == 1
    assert all(payload["rev"] == 2 for payload in results)
    assert all(payload is results[0] for payload in results)


def test_control_without_the_barrier_the_rig_sees_the_stampede(monkeypatch):
    async def _uncoalesced(_builds, _key, _asked_at, build, **_kw):
        return await build()

    monkeypatch.setattr(events_route, "_coalesced_fresh_build", _uncoalesced)
    _leader, _results, builds = asyncio.run(_herd())
    assert builds == N_READERS + 1


def test_an_older_builds_failure_is_not_inherited():
    leader, results, builds = asyncio.run(_herd(leader_fail=True))
    assert isinstance(leader, RuntimeError)
    assert builds == 2
    assert all(payload["rev"] == 2 for payload in results)


def test_a_cancelled_build_elects_a_new_one_instead_of_cancelling_its_waiters():
    leader, results, builds = asyncio.run(_herd(cancel_leader=True))
    assert isinstance(leader, asyncio.CancelledError)
    assert builds == 1  # the cancelled leader never finished its build
    assert all(payload["rev"] == 2 for payload in results)


def test_same_generation_readers_share_the_builds_error():
    async def scenario():
        gate = asyncio.Event()
        leader = _read(_Session(1, gate))
        await _settle()
        # The next generation's elected builder fails: that IS their answer.
        failing = _Session(2, gate, fail=True)
        others = [_Session(2, gate) for _ in range(3)]
        tasks = [_read(s) for s in [failing, *others]]
        await _settle()
        gate.set()
        await leader
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        return outcomes, failing.builds + sum(s.builds for s in others)

    outcomes, next_builds = asyncio.run(scenario())
    assert next_builds == 1
    assert all(isinstance(o, RuntimeError) for o in outcomes)


def test_a_reader_arriving_after_the_build_finished_gets_a_new_build():
    async def scenario():
        gate = asyncio.Event()
        gate.set()
        first = await get_game_markets(EVENT_ID, db=_Session(1, gate), fresh=True, response=None)
        later_session = _Session(2, gate)
        later = await get_game_markets(EVENT_ID, db=later_session, fresh=True, response=None)
        return first, later, later_session.builds

    first, later, later_builds = asyncio.run(scenario())
    assert later_builds == 1
    assert (first["rev"], later["rev"]) == (1, 2)


def test_two_events_never_share_a_build():
    async def scenario():
        gate = asyncio.Event()
        a, b = _Session(1, gate), _Session(2, gate)
        ta = asyncio.ensure_future(get_game_markets(1, db=a, fresh=True, response=None))
        tb = asyncio.ensure_future(get_game_markets(2, db=b, fresh=True, response=None))
        await _settle()
        gate.set()
        return await asyncio.gather(ta, tb), a.builds + b.builds

    (ra, rb), builds = asyncio.run(scenario())
    assert builds == 2
    assert (ra["event_id"], ra["rev"], rb["event_id"], rb["rev"]) == (1, 1, 2, 2)


def test_the_fresh_answer_stays_out_of_the_ordinary_cache_ladder(monkeypatch):
    """The barrier changes how many builds run, not where a fresh body goes:
    it is still never published into L1/L2 (the route's existing contract)."""
    published = []

    async def _publish(*a, **kw):
        published.append(a)

    monkeypatch.setattr(events_route, "_publish_game_markets", _publish)
    monkeypatch.setattr(events_route, "_write_game_markets_memo", lambda *a, **kw: published.append(a))

    async def scenario():
        gate = asyncio.Event()
        gate.set()
        return await get_game_markets(EVENT_ID, db=_Session(1, gate), fresh=True, response=None)

    assert asyncio.run(scenario())["rev"] == 1
    assert published == []
