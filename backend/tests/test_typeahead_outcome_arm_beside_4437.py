"""#4437: the dropdown's outcome arm runs BESIDE the teams and games lookups.

THE SHIP. A first read of the search dropdown paid the outcome arm (1.1-2.4 s
on "mid"/"chi", Nov 7) AFTER the teams, games and next-match lookups, on the
request's one session. The arm depends on nothing those produce, so a reader's
request now starts it on a session of its own before the teams lookup and
collects it where it always joined the futures stage: the wait is the slower of
the two chains, not their sum.

What must not change: the arm's own bound, its shed rules and its answer — the
resolver is the same function, called with the same arguments, on another
session. And it stays IN PLACE wherever a second session could hurt: a test
double, a connection-bound session, a pool with no free connection, the warmer.
"""

import asyncio
import inspect

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.routes import events as events_mod
from app.routes.events import _typeahead_start_outcome_arm_beside

ARM = object()
OPEN_NOW = ("open-now",)


def _engine():
    # Never connects: the resolver is faked, so no statement is issued.
    return create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none", pool_size=2)


@pytest.fixture
def fake_resolver(monkeypatch):
    calls = []

    async def _resolve(db, arm, open_now, deadline, pattern=None, outcome_cond=None):
        calls.append({"db": db, "arm": arm, "open_now": open_now, "deadline": deadline,
                      "pattern": pattern, "outcome_cond": outcome_cond})
        await asyncio.sleep(0.05)
        return [7, 3]

    monkeypatch.setattr(events_mod, "_resolve_typeahead_outcome_arm", _resolve)
    return calls


@pytest.mark.asyncio
async def test_a_reader_session_on_an_engine_runs_the_arm_on_another_session(fake_resolver):
    engine = _engine()
    db = AsyncSession(bind=engine)
    task = _typeahead_start_outcome_arm_beside(db, ARM, OPEN_NOW, 123.0, "%mid%", "cond")
    assert task is not None
    assert await task == [7, 3]
    (call,) = fake_resolver
    assert call["db"] is not db and isinstance(call["db"], AsyncSession)
    assert (call["arm"], call["open_now"], call["deadline"], call["pattern"], call["outcome_cond"]) == (
        ARM, OPEN_NOW, 123.0, "%mid%", "cond"
    ), "the same resolver, the same arguments — only the session differs"
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_arm_overlaps_work_done_meanwhile(fake_resolver):
    """Started, it runs while the request does something else."""
    engine = _engine()
    db = AsyncSession(bind=engine)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    task = _typeahead_start_outcome_arm_beside(db, ARM, OPEN_NOW, None, "%mid%", None)
    await asyncio.sleep(0.05)  # the teams and games lookups
    await task
    assert loop.time() - t0 < 0.09, "the arm waited for the other chain instead of overlapping it"
    await engine.dispose()


@pytest.mark.asyncio
async def test_no_arm_means_nothing_starts(fake_resolver):
    engine = _engine()
    assert _typeahead_start_outcome_arm_beside(AsyncSession(bind=engine), None, OPEN_NOW, None, "%we%", None) is None
    assert fake_resolver == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_test_double_keeps_the_arm_in_place(fake_resolver):
    class _Fake:
        bind = None

    assert _typeahead_start_outcome_arm_beside(_Fake(), ARM, OPEN_NOW, None, "%mid%", None) is None


@pytest.mark.asyncio
async def test_a_connection_bound_session_keeps_the_arm_in_place(fake_resolver):
    """A second session on ONE connection would run concurrently on it."""
    db = AsyncSession()
    db.bind = object()  # not an engine
    assert _typeahead_start_outcome_arm_beside(db, ARM, OPEN_NOW, None, "%mid%", None) is None


@pytest.mark.asyncio
async def test_a_pool_with_no_free_connection_keeps_the_arm_in_place(fake_resolver, monkeypatch):
    engine = _engine()
    monkeypatch.setattr(type(engine.pool), "checkedout", lambda self: self.size())
    assert _typeahead_start_outcome_arm_beside(AsyncSession(bind=engine), ARM, OPEN_NOW, None, "%mid%", None) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_warmer_keeps_the_arm_in_place(fake_resolver):
    engine = _engine()
    token = events_mod._force_cache_rebuild.set(True)
    try:
        assert _typeahead_start_outcome_arm_beside(AsyncSession(bind=engine), ARM, OPEN_NOW, None, "%mid%", None) is None
    finally:
        events_mod._force_cache_rebuild.reset(token)
    await engine.dispose()


def test_the_route_starts_the_arm_before_the_teams_lookup_and_collects_it_at_the_futures_stage():
    src = inspect.getsource(events_mod.typeahead_search)
    start = src.index("_typeahead_start_outcome_arm_beside(")
    teams = src.index("team_result = await db.execute(team_query)")
    collect = src.index("_ta_outcome_beside\n            if _ta_outcome_beside is not None")
    futures = src.index("_ta_arm_selects = [")
    assert start < teams < collect < futures
