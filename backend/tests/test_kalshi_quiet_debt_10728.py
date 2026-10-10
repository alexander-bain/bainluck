"""#10728 — a quiet game's owed stamp must not collapse the live-first plan.

At 238ba632 `linked_first_phases` joined EVERY game into one transaction
whenever the refresher owed any stamp. The join protects one thing: an owed
event whose new price is in this batch must not be stamped (and throttled)
by an earlier phase's refresh before that price is written. Debt owed only
to events with no price in the batch (a quiet game whose written price the
throttle or a row lock held) cannot do that, yet it put the live game behind
every other game and past the non-live budget.

Proves on the planner and on the SHIPPED `flush_prices` (the #10655 and
#10090 rigs): disjoint debt keeps independent live-first phases and is paid
without joining them; on the planner, overlapping or mixed debt keeps the whole
original join; empty debt and unmapped outcomes are unchanged. Not a speed claim.

1cbd6e28e9: the shipped flush now asks the planner for FENCED phases — an owed
game is fenced out of every stamp until its own price commits, instead of
joining every game. The flush-level arms below assert that contract; the
strawman runs the same slate through the unfenced planner to show the rig
still sees a join.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as lbr
from app.tasks.kalshi_ws import FLUSH_BUDGET_SECONDS, linked_first_phases
from tests import test_kalshi_flush_budget_10090 as budget
from tests import test_kalshi_game_isolation_10655 as isolation

QUIET = 500  # an owed event with no outcome in any batch below


@pytest.fixture
def fake_clock(monkeypatch):
    """The #10090 rig's clock seam; only its tests below take it."""
    holder = {}
    monkeypatch.setattr(lbr, "_mono", lambda: holder["rig"].clock["now"])
    return holder

# ------------------------------------------------------------ the planner ----

MARKETS = {1: 10, 2: 10, 3: 20, 4: 30, 9: 90}
EVENTS = {1: 100, 2: 100, 3: 200, 4: 300}
BATCH = {3: 'c', 9: 'z', 1: 'a', 4: 'd', 2: 'b'}
JOINED = {3: 'c', 1: 'a', 4: 'd', 2: 'b'}  # every game row, batch order


@pytest.mark.parametrize("live", [None, {300}])
def test_disjoint_debt_plans_exactly_as_no_debt(live):
    plain = linked_first_phases(BATCH, MARKETS, EVENTS, live_events=live)
    assert len(plain) > 2  # the games really are split without debt
    assert linked_first_phases(
        BATCH, MARKETS, EVENTS, {QUIET}, live_events=live) == plain


@pytest.mark.parametrize("pending", [{200}, {200, QUIET}, {100, 300, QUIET}])
@pytest.mark.parametrize("live", [None, set(), {300}])
def test_overlapping_or_mixed_debt_keeps_the_whole_original_join(pending, live):
    phases = linked_first_phases(BATCH, MARKETS, EVENTS, pending, live_events=live)
    assert phases == [JOINED, {9: 'z'}]
    assert list(phases[0]) == list(JOINED)


def test_empty_debt_and_unmapped_outcomes_are_unchanged():
    assert linked_first_phases(BATCH, MARKETS, EVENTS, frozenset()) == \
        linked_first_phases(BATCH, MARKETS, EVENTS)
    unmapped = {**MARKETS, 2: None}
    for pending in ((), {QUIET}, {200}):
        assert linked_first_phases(BATCH, unmapped, EVENTS, pending) == [BATCH]


def test_debt_with_no_game_in_the_batch_is_unchanged():
    futures = {9: 'z'}
    assert linked_first_phases(futures, MARKETS, EVENTS, {200}) == [futures]


# ---------------------------------------- the shipped flush, #10655 rig ----


async def test_quiet_debt_is_paid_after_the_first_game_commits_not_joined():
    """Game 100 commits and is stamped while game 200's write is still held;
    game 200 then gets its own unthrottled stamp, and the quiet debt is paid.

    fe0aa54fbf / ff98c3547f: a fresh stamp reads only its fresh events, and a
    fresh-bearing flush then attempts its one old owed event with its own
    read — so the quiet stamp follows the games rather than riding game 100's.
    """
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    r = isolation.rig()

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now, *, prepared=None,
                                 on_committed=None, publish_committed=None):
            r.trace.append(('real-refresh', tuple(sorted(event_ids)), tuple(r.committed)))
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now
            if on_committed is not None:  # the production batch's commit callback
                on_committed(event_ids)

        async def publish_market_changes(self, session):
            r.trace.append(('publish', tuple(session.rows)))

    refresher = RecordingRefresher('kalshi')
    refresher.adopt_pending({QUIET})
    r.flush.__globals__['blend_refresher'] = refresher
    task = asyncio.create_task(r.flush(flush_started=100.0))
    try:
        await asyncio.wait_for(r.entered.wait(), 2)
        assert r.committed == [1, 2]
        assert ('real-refresh', (100,), (1, 2)) in r.trace
    finally:
        r.release.set()
        await asyncio.wait_for(task, 2)
    assert ('real-refresh', (QUIET,), (1, 2, 3, 9)) in r.trace
    assert ('real-refresh', (200,), (1, 2, 3, 9)) in r.trace
    assert r.committed == [1, 2, 3, 9]
    assert refresher.pending_event_ids() == frozenset()
    assert refresher.stats['throttled'] == 0


async def test_mixed_debt_is_fenced_not_joined():
    """1cbd6e28e9: debt owed to game 200, whose price is in the batch, no
    longer joins every game. Game 100 commits and is stamped while 200's write
    is held; 200's owed stamp waits for its own commit."""
    r = isolation.rig(pending={200, QUIET})
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(r.entered.wait(), 2)
        assert r.committed == [1, 2]
        assert ('refresh', (100,)) in r.trace
        assert not any(t[0] == 'refresh' and 200 in t[1] for t in r.trace)
    finally:
        r.release.set()
        await asyncio.wait_for(task, 2)
    assert r.trace.index(('commit', (3,))) < r.trace.index(('refresh', (200,)))
    assert ('commit', (1, 2, 3)) not in r.trace
    assert r.committed == [1, 2, 3, 9]


# ---------------------------------------- the shipped flush, #10090 rig ----


def _owing(r, pending):
    """Owe ``pending`` and record when each event's stamp lands (rig clock)."""
    refresher = r.flush.__globals__['blend_refresher']
    refresher.pending_event_ids = lambda: frozenset(pending)
    stamped, refresh = {}, refresher.refresh

    async def recording(ids, **kw):
        await refresh(ids, **kw)
        stamped.update(dict.fromkeys(ids, r.clock['now']))

    refresher.refresh = recording
    return stamped


async def _live_stamp_at(fake_clock, pending):
    """One periodic flush of a 400-game slate, live game last in batch order,
    game 7 quiet (not ticked); return when the live game's stamp lands."""
    r = budget.rig(games=400, futures_markets=40)
    fake_clock['rig'] = r
    budget.tick_everything(r, 0.6)
    quiet_oids, _, _ = budget._game(7)
    for oid in quiet_oids:
        r.buffer.pop(oid)
    stamped = _owing(r, pending)
    before = len(r.buffer)
    assert await r.flush(0.0) is True
    assert len(r.written) + len(r.buffer) == before  # nothing lost
    assert r.stats['errors'] == 0
    return stamped[budget.LIVE_EVENT], r


async def test_quiet_debt_keeps_the_live_game_first_and_the_budget(fake_clock):
    at, r = await _live_stamp_at(fake_clock, {budget.LIVE_EVENT + 7})
    assert sorted(oid for oid, _ in r.written[:2]) == [0, 1]
    assert at <= budget.PHASE_COST + budget.ROW_COST * 2 + budget.STAMP_COST
    assert r.stats['budget_deferred'] == len(r.buffer) > 0


async def test_strawman_overlapping_debt_joins_and_the_live_game_waits(
    fake_clock, monkeypatch,
):
    """Same slate, debt on a ticked game, through the UNFENCED planner (the
    flush before 1cbd6e28e9): the original join, so the live game is written
    and stamped with all 399 others, far past the budget — the guard above is
    not vacuous."""
    def unfenced(*args, **kwargs):
        return linked_first_phases(*args, **{**kwargs, "pending_events_fenced": False})

    monkeypatch.setitem(budget.__dict__, "linked_first_phases", unfenced)
    at, r = await _live_stamp_at(fake_clock, {budget.LIVE_EVENT + 3})
    assert at > FLUSH_BUDGET_SECONDS * 4
    assert not any(oid in r.events for oid in r.buffer)  # no game deferred
