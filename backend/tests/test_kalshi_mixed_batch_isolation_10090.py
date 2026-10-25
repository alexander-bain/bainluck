"""#10090 — a live game's known props never share a phase with unrelated work.

Production v5771 (2026-10-17 22:52:49–22:54:07Z): 131 lock timeouts on the
non-live tail held a live game's total-points lines ~78 s, because the planner
packed that game's props (known non-speakers, outside its headline cohort) into
the same 200-row phases as unrelated futures, and a lock timeout rolls back its
whole phase. The three flush controls are Root's attempt45 countercase on
exact deployed df2363aa15 (1 failed / 2 passed there), adopted unchanged.
"""
import random

import pytest

from app.tasks import kalshi_ws
from app.tasks.kalshi_ws import (
    NONLIVE_PHASE_MAX_ROWS,
    _KalshiHeadlineEvents,
    _packed,
    flush_budget_spent,
    linked_first_phases,
)
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_held_quotes_10090 import Clock


def mixed(monkeypatch, locked):
    clock = Clock(monkeypatch)
    x = rig(locked=locked)
    x.release.set()
    x.ns.update(live_event_ids={100, 200}, flush_period=.25,
                live_preempts_tail=kalshi_ws.live_preempts_tail,
                yield_written_nonlive_tail=kalshi_ws.yield_written_nonlive_tail)
    x.ns['non_blend_outcome_ids'].add(3)  # live game 200's prop, not its winner
    # Winner 1/2 is an unaffected control. Future 9 is unrelated to prop 3.
    initial = dict(x.batch)
    x.batch.clear()
    x.batch.update((oid, initial[oid]) for oid in (9, 3, 1, 2))
    return clock, x


@pytest.mark.asyncio
async def test_live_prop_commits_despite_an_unrelated_future_lock(monkeypatch):
    clock, x = mixed(monkeypatch, locked=(9,))
    assert await x.flush(flush_started=clock.t)
    assert {1, 2}.issubset(x.committed)  # headline cohort already isolated
    assert 3 in x.committed, {'committed': x.committed, 'buffer': list(x.batch),
                              'trace': x.trace}
    assert 9 in x.batch and 9 not in x.committed
    assert all(200 not in ids for kind, ids in x.trace if kind == 'refresh')


@pytest.mark.asyncio
async def test_mixed_batch_recovery_keeps_inputs_and_does_not_stamp_prop_as_winner(monkeypatch):
    clock, x = mixed(monkeypatch, locked=(9,))
    assert await x.flush(flush_started=clock.t)
    assert set(x.batch) | set(x.committed) == {1, 2, 3, 9}
    x.lock_released.set()
    clock.t += x.ns['PRICE_FLUSH_SECONDS']
    assert await x.flush(flush_started=clock.t)
    assert not x.batch and set(x.committed) == {1, 2, 3, 9}
    assert len(x.committed) == 4
    assert all(200 not in ids for kind, ids in x.trace if kind == 'refresh')


@pytest.mark.asyncio
async def test_uncontended_mixed_batch_commits_all_inputs(monkeypatch):
    clock, x = mixed(monkeypatch, locked=())
    assert await x.flush(flush_started=clock.t)
    assert not x.batch and set(x.committed) == {1, 2, 3, 9}
    assert all(200 not in ids for kind, ids in x.trace if kind == 'refresh')


@pytest.mark.asyncio
async def test_the_locked_future_keeps_its_retry_and_the_prop_owes_none(monkeypatch):
    clock, x = mixed(monkeypatch, locked=(9,))
    assert await x.flush(flush_started=clock.t)
    retry = x.ns['prices'].lock_retry_until
    assert 9 in retry and 3 not in retry
    assert x.stats['requeued'] == 1


# Planner: games 100 (winner 1/2, live) and 200 (live, props only), future 9x.
WINNER, PROPS_200, PROPS_300 = {1: 10, 2: 10}, {3: 20, 4: 21}, {5: 30}
OWNERS = {1: 100, 2: 100, 3: 200, 4: 200, 5: 300}
NON_SPEAKERS = {3, 4, 5}


def plan(order, live, *, full=True):
    markets = {**WINNER, **PROPS_200, **PROPS_300, 90: 900, 91: 901}
    cohort = _KalshiHeadlineEvents(OWNERS, NON_SPEAKERS)
    return linked_first_phases(
        {oid: (.5, .49, .51) for oid in order}, markets, cohort,
        live_events=live, pending_events_fenced=True,
        tail_event_by_outcome=OWNERS if full else None,
    )


def test_each_live_games_props_get_their_own_phase_in_batch_order():
    phases = plan((90, 3, 1, 5, 91, 4, 2), {100, 200, 300})
    assert [list(p) for p in phases] == [[1, 2], [90, 91], [3, 4], [5]]


def test_props_of_a_game_that_is_not_live_still_pack_with_futures():
    phases = plan((90, 3, 1, 5, 91, 4, 2), {100})
    assert [list(p) for p in phases] == [[1, 2], [90, 3, 5, 91, 4]]


def test_strawman_without_the_owner_map_props_share_the_futures_phase():
    phases = plan((90, 3, 1, 5, 91, 4, 2), {100, 200, 300}, full=False)
    assert [list(p) for p in phases] == [[1, 2], [90, 3, 5, 91, 4]]


def test_a_live_prop_phase_has_no_live_priority():
    # Same tail rules: past the budget, a live game's prop phase is deferred.
    cohort = _KalshiHeadlineEvents(OWNERS, NON_SPEAKERS)
    assert flush_budget_spent(-1e9, {3: None, 4: None}, cohort, {200})
    assert not flush_budget_spent(-1e9, {1: None}, cohort, {100})


def test_a_live_games_props_split_only_between_whole_markets_at_the_cap():
    big = NONLIVE_PHASE_MAX_ROWS - 1
    markets = {oid: 500 + (oid >= big) for oid in range(big + 2)}
    owners = dict.fromkeys(markets, 200)
    phases = linked_first_phases(
        {oid: None for oid in markets}, markets,
        _KalshiHeadlineEvents(owners, set(markets)), live_events={200},
        pending_events_fenced=True, tail_event_by_outcome=owners,
    )
    assert [len(p) for p in phases] == [big, 2]


def test_a_full_prop_phase_keeps_its_place_ahead_of_later_opened_phases():
    # Prop market A (cap - 1 rows), future F, prop market B: B overflows A's
    # phase and opens a new one AFTER F's; A keeps its oldest-first place.
    big = NONLIVE_PHASE_MAX_ROWS - 1
    a = {oid: 500 for oid in range(big)}
    markets = {**a, -1: 900, -2: 501, -3: 501}
    owners = dict.fromkeys([*a, -2, -3], 200)
    phases = linked_first_phases(
        {oid: None for oid in markets}, markets,
        _KalshiHeadlineEvents(owners, set(owners)), live_events={200},
        pending_events_fenced=True, tail_event_by_outcome=owners,
    )
    assert [sorted(p)[:1] for p in phases] == [[0], [-1], [-3]]


def _legacy_packed(groups, max_rows, max_groups=None):
    phases, current, count = [], {}, 0
    for group in groups:
        if current and (
            len(current) + len(group) > max_rows
            or (max_groups is not None and count >= max_groups)
        ):
            phases.append(current)
            current, count = {}, 0
        current.update(group)
        count += 1
    if current:
        phases.append(current)
    return phases


@pytest.mark.parametrize("seed", range(40))
def test_unkeyed_packing_is_the_previous_packing(seed):
    rnd = random.Random(seed)
    oid = iter(range(10**6))
    groups = [{next(oid): None for _ in range(rnd.randint(1, 30))}
              for _ in range(rnd.randint(0, 40))]
    max_rows, max_groups = rnd.randint(1, 60), rnd.choice([None, 1, 3, 8])
    assert _packed(groups, max_rows, max_groups) == _legacy_packed(
        groups, max_rows, max_groups)
