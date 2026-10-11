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
from collections import defaultdict
from contextlib import asynccontextmanager

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


async def _caused(event, failure):
    """Wait on the cause itself; its absence within the rig's bound is a finding."""
    try:
        await asyncio.wait_for(event.wait(), 2)
    except asyncio.TimeoutError:
        raise AssertionError(failure) from None


async def _quiet_slate(*, quiet_after_row3, mutate=None):
    """Run the SHIPPED flush owing only the quiet event, with game 200's row 3
    held, and assert the delivery contract at explicit causes, not turns.

    The original arm asserted one exact interleaving: the quiet stamp after
    every row, including the unrelated futures row 9. That is a scheduler
    accident — Python 3.11's ``wait_for`` adds turns before the held phase is
    observed, and the refresher then legitimately pays the quiet debt while
    row 3 is still held (artifacts/live-iteration-goal-20261011/
    quiet-debt-diagnosis). Both legal schedules are now driven explicitly:
    ``quiet_after_row3=False`` waits for the quiet stamp while row 3 is held;
    ``True`` gates the quiet stamp on row 3's commit. ``mutate`` wraps the
    refresher class for the negative controls below.
    """
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    r = isolation.rig()
    stamped = defaultdict(asyncio.Event)
    row3_committed = asyncio.Event()
    session = r.ns['get_task_session']

    @asynccontextmanager
    async def observed_session():
        async with session() as s:
            yield s
        if 3 in r.committed:
            row3_committed.set()

    r.ns['get_task_session'] = observed_session

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now, *, prepared=None,
                                 on_committed=None, publish_committed=None):
            if quiet_after_row3 and set(event_ids) == {QUIET}:  # its own read is slow
                await row3_committed.wait()
            r.trace.append(('real-refresh', tuple(sorted(event_ids)), tuple(r.committed)))
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now
            if on_committed is not None:  # the production batch's commit callback
                on_committed(event_ids)
            for event_id in event_ids:
                stamped[event_id].set()

        async def publish_market_changes(self, session):
            r.trace.append(('publish', tuple(session.rows)))

    refresher = (mutate or (lambda cls: cls))(RecordingRefresher)('kalshi')
    refresher.adopt_pending({QUIET})
    r.ns['blend_refresher'] = refresher
    task = asyncio.create_task(r.flush(flush_started=100.0))
    try:
        await asyncio.wait_for(r.entered.wait(), 2)
        await _caused(stamped[100], "game 100 was not stamped while game 200 was held")
        assert r.committed == [1, 2]
        for t in r.trace:
            if t[0] == 'real-refresh' and 100 in t[1]:
                assert t[1] == (100,), f"stamp {t[1]} joined unrelated games"
        assert ('real-refresh', (100,), (1, 2)) in r.trace
        if not quiet_after_row3:
            await _caused(stamped[QUIET], "quiet debt was not paid while game 200 was held")
            assert r.committed == [1, 2]  # still held: the quiet stamp waited on no game
        assert not stamped[200].is_set(), "game 200 stamped before its own row committed"
    finally:
        r.release.set()
        await asyncio.wait_for(task, 2)
        # The flush can return while its stamp still runs (f3236c0f23); the
        # next flush joins it. Join it here exactly as that flush would.
        await asyncio.wait_for(r.ns['prices'].join_stamp(refresher), 2)

    stamps = [(r.trace.index(t), t[1], t[2]) for t in r.trace if t[0] == 'real-refresh']
    row3_at = r.trace.index(('commit', (3,)))
    for at, ids, rows in stamps:
        if 200 in ids:
            assert at > row3_at and 3 in rows, "game 200 stamped before its own row committed"
    for at, ids, rows in stamps:
        if {100, 200, QUIET} & set(ids):
            assert len(ids) == 1, f"stamp {ids} joined unrelated games"
    quiet = [(at, rows) for at, ids, rows in stamps if ids == (QUIET,)]
    assert quiet, "quiet debt was never paid"
    game_100_at = next(at for at, ids, _ in stamps if ids == (100,))
    assert quiet[0][0] > game_100_at  # follows game 100 rather than riding its stamp
    if quiet_after_row3:
        assert {1, 2, 3} <= set(quiet[0][1])
    else:
        assert quiet[0][1] == (1, 2)
    assert sorted(ids for _, ids, _ in stamps) == [(100,), (200,), (QUIET,)]
    assert r.committed == [1, 2, 3, 9]
    assert refresher.pending_event_ids() == frozenset()
    assert refresher.stats['throttled'] == 0


@pytest.mark.parametrize("quiet_after_row3", [False, True],
                         ids=["quiet-paid-while-held", "quiet-paid-after-row3"])
async def test_quiet_debt_is_paid_after_the_first_game_commits_not_joined(quiet_after_row3):
    """Game 100 commits and is stamped while game 200's write is still held;
    game 200 then gets its own unthrottled stamp, and the quiet debt is paid.

    fe0aa54fbf / ff98c3547f: a fresh stamp reads only its fresh events, and a
    fresh-bearing flush then attempts its one old owed event with its own
    read — so the quiet stamp follows game 100 rather than riding its stamp,
    whether it lands while game 200 is held or after.
    """
    await _quiet_slate(quiet_after_row3=quiet_after_row3)


def _drops_quiet_debt(cls):
    class Dropping(cls):
        async def refresh(self, event_ids, **kwargs):
            self._throttle_deferred.discard(QUIET)  # neither stamped nor owed
            return await super().refresh(event_ids, **kwargs)
    return Dropping


def _stamps_game_200_before_its_commit(cls):
    class Early(cls):
        async def refresh(self, event_ids, **kwargs):
            ids = set(event_ids)
            if 100 in ids:  # the fence lost: 200 read from a partial board
                ids.add(200)
                kwargs['defer_event_ids'] = set(kwargs.get('defer_event_ids', ())) - {200}
            return await super().refresh(ids, **kwargs)
    return Early


def _joins_quiet_debt_to_game_100(cls):
    class Joined(cls):
        async def _refresh_batch(self, event_ids, now, **kwargs):
            if 100 in event_ids and QUIET not in event_ids:
                event_ids = [*event_ids, QUIET]
            return await super()._refresh_batch(event_ids, now, **kwargs)
    return Joined


@pytest.mark.parametrize("quiet_after_row3", [False, True],
                         ids=["quiet-paid-while-held", "quiet-paid-after-row3"])
@pytest.mark.parametrize("mutate, finding", [
    (_drops_quiet_debt, "quiet debt was (not|never) paid"),
    (_stamps_game_200_before_its_commit, "game 200 stamped before its own row committed"),
    (_joins_quiet_debt_to_game_100, r"stamp \(100, 500\) joined unrelated games"),
], ids=["drops-quiet-debt", "stamps-200-precommit", "joins-quiet-to-100"])
async def test_strawman_the_quiet_contract_rejects_lost_debt_early_and_joined_stamps(
    mutate, finding, quiet_after_row3,
):
    """The same slate through refreshers that drop the quiet debt, stamp game
    200 before its row commits, or pay the debt inside game 100's stamp: each
    fails the contract above on its own clause, so it is not vacuous."""
    with pytest.raises(AssertionError, match=finding):
        await _quiet_slate(quiet_after_row3=quiet_after_row3, mutate=mutate)


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
