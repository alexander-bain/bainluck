"""#10090 — qualification of the live-prop isolation (PR #11206) on real Postgres.

## the ship

A live game's prop prices keep updating while an unrelated futures row is
locked, without tearing a two-leg market, without a prop joining the game's
headline cohort, and without older retained quotes or settled rows winning.

## what this adds to the adopted gate

`test_kalshi_live_prop_beside_locked_future_10090_pg.py` (Root attempt45) is
the parent-fails/candidate-passes case. These are Root's three bounded
qualifications of Argon's mixed-batch review (2026-10-18):

1. Same-game two-leg prop, classified from a REAL Kalshi prop ticker through
   the consumer's own classifier: prop-only input publishes the whole market
   and starts no headline refresh; with one prop leg locked, the winner still
   commits and stamps, neither prop leg moves, and no prop is ever held as a
   headline quote. Two strawman sources (Argon's raw-map cohort) must fail it.
2. The isolated prop phase keeps the existing retry contracts: a newer
   buffered quote is what the periodic retry writes (never the older retained
   one), the retry waits out its cooldown, and a row a settlement writer
   commits with an `AUTHORITATIVE_SOURCES` `FuturesOutcome.resolution_source`
   is refused by the price statement. All inside the running consumer, never
   the final drain.
3. Continuous winner and prop traffic with a quiet healthy future in a
   DIFFERENT phase from a locked future: the healthy future publishes while
   the lock holds, including a tick landing as the locked phase's cooldown
   expires (when the failed phase spends the round's non-live start), and the
   locked phase's attempts stay bounded by its cooldown. A separate
   observation at the production row cap records the known coupling: a
   standalone future packed with the locked one waits for it (unchanged by
   #11206; not asserted).

Rig: `test_kalshi_live_beside_inflight_nonlive_10090_pg.py` (the shipped
closures on real Postgres, production cadence, independent readback), plus
the production #11138 overlay (`HeldRowQuotes` with real `TailReceipts`).
Synthetic rows; order, coherence and progress, not production timing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time

import pytest
from sqlalchemy import text

from tests.integration.test_kalshi_live_beside_inflight_nonlive_10090_pg import (
    PERIOD, SOURCE, _consumer, _rig, _stored, _tick, _wait_until, pg,  # noqa: F401
)
from tests.integration.test_kalshi_price_lock_budget_pg_10661 import (
    _holding, _wait_for_a_lock_wait,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not os.environ.get('BLEND_DEADLOCK_DATABASE_URL'), reason='exclusive disposable PG required',
)]

#: Real Kalshi series shapes: the game winner speaks, the total does not.
WINNER_TICKER = 'KXMLBGAME-26OCT171905NYYBOS'
PROP_TICKER = 'KXMLBTOTAL-26OCT171905NYYBOS'
SEED = {'home': .40, 'away': .60, 'p1': .45, 'p2': .55, 'x1': .30, 'x2': .70}


async def _qualified_rig(engine, side, ids, source=None):
    """The adopted gate's rig with the prop market attached to the live game
    under a real prop ticker, the classification derived as the consumer
    derives it, and the production held-quote overlay."""
    from functools import partial

    from app.tasks import kalshi_ws
    from app.tasks.base import get_task_session
    from app.tasks.live_blend_refresh import HeldRowQuotes, TailReceipts

    markets = ids['markets']
    async with side.begin() as conn:
        await conn.execute(text(
            'UPDATE futures_markets SET event_id=:e, external_id=:t WHERE id=:m'
        ), {'e': ids['event'], 't': PROP_TICKER, 'm': markets['pregame']})
        await conn.execute(text('UPDATE futures_markets SET external_id=:t WHERE id=:m'),
                           {'t': WINNER_TICKER, 'm': markets['live']})
    ns, record = _rig(engine, side, ids, source=source)
    legs = ids['legs']
    for leg in ('p1', 'p2'):
        ns['event_id_by_outcome'][legs[leg]] = ids['event']
    # `_run_kalshi_ws_consumer`'s comprehension over the stored market tickers.
    async with side.connect() as conn:
        ticker_by_market = dict((await conn.execute(text(
            'SELECT id, external_id FROM futures_markets'
        ))).all())
    ns['non_blend_outcome_ids'].update(
        oid for oid, mid in ns['market_id_by_outcome'].items()
        if kalshi_ws.kalshi_non_speaking_ticker(ticker_by_market.get(mid))
    )
    assert ns['non_blend_outcome_ids'] == {legs['p1'], legs['p2']}

    receipts = TailReceipts('kalshi')
    refresher = ns['blend_refresher']
    refresher.receipts = receipts
    ns['tail_receipts'] = receipts
    held = HeldRowQuotes()
    assert await held.sample_database_clock(partial(get_task_session, engine=engine))
    refresher.held_quotes = held
    record.held_ids = set()
    hold = held.hold

    def recording_hold(quotes):
        record.held_ids.update(quotes)
        return hold(quotes)

    held.hold = recording_hold
    record.attempts = []
    phase = ns['prices'].phase

    def counted(session, group, **kwargs):
        record.attempts.append((time.monotonic(), frozenset(group)))
        return phase(session, group, **kwargs)

    ns['prices'].phase = counted
    record.plans = []
    planner = ns['linked_first_phases']

    def recording_planner(*args, **kwargs):
        planned = planner(*args, **kwargs)
        record.plans.append([frozenset(p) for p in planned])
        return planned

    ns['linked_first_phases'] = recording_planner
    return ns, record


async def test_the_prop_and_winner_tickers_are_classified_by_the_consumers_rule():
    from app.tasks.kalshi_ws import kalshi_non_speaking_ticker

    assert kalshi_non_speaking_ticker(PROP_TICKER)
    assert not kalshi_non_speaking_ticker(WINNER_TICKER)


def _published(record, market, values):
    return [t for t, m, v in record.publications
            if m == market and all(v[k] == x for k, x in values.items())]


async def test_a_live_games_prop_alone_publishes_whole_and_starts_no_headline_refresh(pg):
    engine, side, ids = pg
    legs, markets = ids['legs'], ids['markets']
    ns, record = await _qualified_rig(engine, side, ids)
    prop = {legs['p1']: .65, legs['p2']: .35}

    async def prop_published():
        return bool(_published(record, markets['pregame'], prop))

    async with _consumer(ns):
        await _tick(ns, 'p1', .64, .66)
        await _tick(ns, 'p2', .34, .36)
        await _wait_until(prop_published, 2.0)
        await asyncio.sleep(3 * PERIOD)  # any refresh a prop could start, started
    stored = await _stored(side)
    print('EVIDENCE', json.dumps(dict(
        plans=[[sorted(p) for p in plan] for plan in record.plans],
        stamps=[(t, e) for t, e, _ in record.stamps], stats=dict(ns['stats']))))
    assert (stored[legs['p1']][0], stored[legs['p2']][0]) == (.65, .35)
    assert stored[legs['home']][0] == SEED['home'] and stored[legs['away']][0] == SEED['away']
    # Both legs in one transaction: every frame of the prop market reads
    # either both seeded legs or both new ones, never one of each.
    frames = [(v[legs['p1']], v[legs['p2']]) for _, m, v in record.publications
              if m == markets['pregame']]
    assert frames and set(frames) <= {(SEED['p1'], SEED['p2']), (.65, .35)}, frames
    assert not record.stamp_started and not record.stamps
    assert not record.held_ids


async def _locked_prop_leg(engine, side, ids, source=None):
    """One prop leg locked by another writer; both prop legs and the game's
    winner legs queued. Returns observations; asserts nothing."""
    legs, markets = ids['legs'], ids['markets']
    ns, record = await _qualified_rig(engine, side, ids, source=source)
    await _tick(ns, 'p1', .64, .66)
    await _tick(ns, 'p2', .34, .36)
    await _tick(ns, 'home', .73, .75)
    await _tick(ns, 'away', .25, .27)

    async def winner_published():
        return bool(_published(record, markets['live'], {legs['home']: .74}))

    async with _holding(side, legs['p1']) as held:
        async with _consumer(ns):
            try:
                await _wait_for_a_lock_wait(side)
                arrived = time.monotonic()
                with contextlib.suppress(TimeoutError):
                    await _wait_until(winner_published, 1.0)
                # Past the prop's first refusal and one more period of work.
                await asyncio.sleep(2 * PERIOD)
                before = dict(
                    stored=await _stored(side), held_active=held.is_active,
                    publications=list(record.publications), stamps=list(record.stamps),
                    held_ids=set(record.held_ids), arrived=arrived,
                    winner=_published(record, markets['live'], {legs['home']: .74}),
                )
            finally:
                await held.rollback()
    return ns, record, before


async def test_a_locked_prop_leg_holds_its_whole_market_and_never_the_winner(pg):
    engine, side, ids = pg
    legs, markets = ids['legs'], ids['markets']
    ns, record, before = await _locked_prop_leg(engine, side, ids)
    p1, p2, home, away = (legs[k] for k in ('p1', 'p2', 'home', 'away'))
    print('EVIDENCE', json.dumps(dict(
        plans=[[sorted(p) for p in plan] for plan in record.plans],
        winner_ms=(before['winner'][0] - before['arrived']) * 1000 if before['winner'] else None,
        held_ids=sorted(before['held_ids']), stats=dict(ns['stats']))))
    assert before['held_active']
    # The planner: winner legs and prop legs never share a phase.
    first = record.plans[0]
    assert any(p == {home, away} for p in first) and any(p == {p1, p2} for p in first), first
    # The winner committed, published and stamped with the prop leg locked.
    assert before['winner'], 'the winner waited on its own prop leg'
    assert before['stored'][home][0] == .74 and before['stored'][away][0] == .26
    assert any(e == (ids['event'],) and v[home] == .74 for _, e, v in before['stamps'])
    # Neither prop leg moved: no partial commit of the two-leg market.
    assert (before['stored'][p1][0], before['stored'][p2][0]) == (SEED['p1'], SEED['p2'])
    assert all((v[p1], v[p2]) == (SEED['p1'], SEED['p2']) for _, _, v in before['publications'])
    assert not [t for t, m, _ in before['publications'] if m == markets['pregame']]
    # A prop can never move the headline, so it is never a held headline quote.
    assert not before['held_ids'] & {p1, p2}
    assert not record.held_ids & {p1, p2}
    # Released: the whole market lands together; nothing is left owed.
    stored = await _stored(side)
    assert (stored[p1][0], stored[p2][0]) == (.65, .35)
    assert not ns['price_buffer']
    frames = {(v[p1], v[p2]) for _, m, v in record.publications if m == markets['pregame']}
    assert frames == {(.65, .35)}, frames


#: Argon's strawman: the raw owner map as the planner's cohort (props join
#: the game's phase), and the cohort view without the classification.
STRAWMEN = {
    'raw-map-as-planner-cohort': (
        'batch, market_id_by_outcome, cohort_event_ids,\n            pending_events=',
        'batch, market_id_by_outcome, event_id_by_outcome,\n            pending_events=',
    ),
    'cohort-view-ignores-classification': (
        'event_id_by_outcome, () if final_drain else non_blend_outcome_ids,',
        'event_id_by_outcome, (),',
    ),
}


@pytest.mark.parametrize('name', sorted(STRAWMEN))
async def test_strawman_a_prop_in_the_winners_cohort_holds_the_winner(pg, name):
    engine, side, ids = pg
    old, new = STRAWMEN[name]
    source = SOURCE.read_text()
    assert source.count(old) == 1, name
    ns, record, before = await _locked_prop_leg(engine, side, ids, source=source.replace(old, new))
    legs = ids['legs']
    print('EVIDENCE', name, json.dumps(dict(
        plans=[[sorted(p) for p in plan] for plan in record.plans],
        winner=bool(before['winner']), held_ids=sorted(before['held_ids']))))
    # The real test's central assertion fails under the strawman.
    assert not before['winner']
    assert before['stored'][legs['home']][0] == SEED['home']


async def _retained_prop(engine, side, ids):
    """The prop phase refused by a lock and retained in cooldown; the game's
    winner committed beside it. Yields (ns, record, held, refused_until)."""
    legs, markets = ids['legs'], ids['markets']
    ns, record = await _qualified_rig(engine, side, ids)
    await _tick(ns, 'p1', .64, .66)
    await _tick(ns, 'p2', .34, .36)
    await _tick(ns, 'home', .73, .75)
    await _tick(ns, 'away', .25, .27)
    async def refused():
        # Rebound at every flush start: read through the owner each time.
        retry = ns['prices'].lock_retry_until
        return legs['p1'] in retry and legs['p2'] in retry

    async def winner_published():
        return bool(_published(record, markets['live'], {legs['home']: .74}))

    return ns, record, refused, winner_published


async def test_the_retained_prop_retries_after_its_cooldown_with_the_newest_quote(pg):
    from app.tasks.live_blend_refresh import _mono

    engine, side, ids = pg
    legs, markets = ids['legs'], ids['markets']
    p1, p2 = legs['p1'], legs['p2']
    ns, record, refused, winner_published = await _retained_prop(engine, side, ids)

    async def newest_stored():
        s = await _stored(side)
        return (s[p1][0], s[p2][0]) == (.70, .30)

    async with _holding(side, p1) as held:
        async with _consumer(ns):
            try:
                await _wait_until(refused, 2.0)
                refused_until = ns['prices'].lock_retry_until[p1]
                await _wait_until(winner_published, 1.0)
                # A newer prop quote arrives while the older one is retained.
                await _tick(ns, 'p1', .69, .71)
                await _tick(ns, 'p2', .29, .31)
                assert _mono() < refused_until, 'release must precede the cooldown'
            finally:
                await held.rollback()
            released = _mono()
            # Paid by the PERIODIC retry inside the running consumer.
            await _wait_until(newest_stored, refused_until - _mono() + 2.0)
            landed = _mono()
            stats = dict(ns['stats'])
    print('EVIDENCE', json.dumps(dict(
        refused_until_after_release=refused_until - released,
        landed_after_cooldown=landed - refused_until, stats=stats)))
    # The cooldown is honest: not written before it expired, and written by
    # the first flush after it (one period plus a bounded flush).
    assert landed >= refused_until
    assert landed - refused_until <= PERIOD + 0.75
    # The older retained quote never landed and was never published.
    frames = {(v[p1], v[p2]) for _, m, v in record.publications if m == markets['pregame']}
    assert frames == {(.70, .30)}, frames
    assert not ns['price_buffer']


async def test_a_settlement_committed_by_the_lock_holder_is_never_repriced(pg):
    from app.tasks.live_blend_refresh import _mono
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

    engine, side, ids = pg
    legs, markets = ids['legs'], ids['markets']
    p1, p2 = legs['p1'], legs['p2']
    assert 'settlement_sync' in AUTHORITATIVE_SOURCES
    ns, record, refused, winner_published = await _retained_prop(engine, side, ids)

    async def p2_stored():
        return (await _stored(side))[p2][0] == .35

    async with _holding(side, p1) as held:
        async with _consumer(ns):
            try:
                await _wait_until(refused, 2.0)
                refused_until = ns['prices'].lock_retry_until[p1]
                await _wait_until(winner_published, 1.0)
                # The writer holding the row was settling it (the column the
                # UPDATE's refusal reads: FuturesOutcome.resolution_source).
                await held.connection.execute(text(
                    "UPDATE futures_outcomes SET current_probability=1.0, "
                    "resolution_source='settlement_sync' WHERE id=:id"
                ), {'id': p1})
                assert _mono() < refused_until
                await held.commit()
            finally:
                if held.is_active:
                    await held.rollback()
            await _wait_until(p2_stored, refused_until - _mono() + 2.0)
            landed = _mono()
            stats = dict(ns['stats'])
    async with side.connect() as conn:
        row = (await conn.execute(text(
            'SELECT current_probability, resolution_source FROM futures_outcomes WHERE id=:id'
        ), {'id': p1})).one()
    print('EVIDENCE', json.dumps(dict(landed_after_cooldown=landed - refused_until, stats=stats)))
    assert landed >= refused_until
    assert (float(row.current_probability), row.resolution_source) == (1.0, 'settlement_sync')
    assert stats['settled_declined'] >= 1
    # No frame ever carried a live price for the settled leg.
    assert all(v[p1] in (SEED['p1'], 1.0) for _, _, v in record.publications)
    assert not ns['price_buffer']


async def _healthy_future(side, ids):
    """A second standalone futures market, two legs (h1/h2), rank seeded."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import FuturesMarket, FuturesOutcome

    async with async_sessionmaker(side, expire_on_commit=False)() as session:
        sport = await session.scalar(text('SELECT sport_id FROM futures_markets LIMIT 1'))
        market = FuturesMarket(sport_id=sport, source='kalshi',
                               external_id='KX10090IF-healthy', name='market healthy')
        session.add(market)
        await session.flush()
        for leg, prob, rank in (('h1', .25, 2), ('h2', .75, 1)):
            outcome = FuturesOutcome(market_id=market.id, name=leg,
                                     external_id=f'KX10090IF-{leg.upper()}',
                                     current_probability=prob, rank=rank)
            session.add(outcome)
            await session.flush()
            ids.setdefault('healthy_legs', {})[leg] = outcome.id
        ids['markets']['healthy'] = market.id
        await session.commit()
    return ids['markets']['healthy']


def _add_healthy_to(ns, ids):
    for leg, oid in ids['healthy_legs'].items():
        ns['market_id_by_outcome'][oid] = ids['markets']['healthy']
        ns['ticker_to_ids'][f'KX10090IF-{leg.upper()}'] = (ids['markets']['healthy'], oid)


async def _traffic(ns, stop, step=0.08):
    """Continuous winner and prop quotes, every value new."""
    i = 0
    while not stop.is_set():
        i += 1
        w = .50 + .01 * (i % 20)
        await _tick(ns, 'home', w - .01, w + .01)
        await _tick(ns, 'away', 1 - w - .01, 1 - w + .01)
        q = .30 + .01 * (i % 20)
        await _tick(ns, 'p1', q - .01, q + .01)
        await _tick(ns, 'p2', 1 - q - .01, 1 - q + .01)
        await asyncio.sleep(step)


async def test_continuous_live_traffic_never_starves_a_healthy_future_in_another_phase(pg, monkeypatch):
    from app.tasks import kalshi_ws
    from app.tasks.live_blend_refresh import _mono

    engine, side, ids = pg
    healthy = await _healthy_future(side, ids)
    legs = {**ids['legs'], **ids['healthy_legs']}
    x1, x2, h1, h2 = (legs[k] for k in ('x1', 'x2', 'h1', 'h2'))
    # Production phases fill at 200 rows (v5771: 170-200-row phases); a cap
    # of one two-leg market puts the healthy future in its own phase AFTER
    # the locked future's, which is the case under test.
    monkeypatch.setattr(kalshi_ws, 'NONLIVE_PHASE_MAX_ROWS', 2)
    ns, record = await _qualified_rig(engine, side, ids)
    _add_healthy_to(ns, ids)
    await _tick(ns, 'x1', .79, .81)
    await _tick(ns, 'x2', .19, .21)
    await _tick(ns, 'h1', .34, .36)
    await _tick(ns, 'h2', .64, .66)

    def healthy_at(a, b):
        async def check():
            return bool(_published(record, healthy, {h1: a, h2: b}))
        return check

    stop = asyncio.Event()
    async with _holding(side, x1) as held:
        async with _consumer(ns):
            started = _mono()
            traffic = asyncio.create_task(_traffic(ns, stop))
            try:
                await _wait_until(healthy_at(.35, .65), 1.0)
                first_ms = (_mono() - started) * 1000
                await _wait_until(lambda: _a(x1 in ns['prices'].lock_retry_until), 1.0)
                until = ns['prices'].lock_retry_until[x1]
                # The second quiet tick lands as the locked phase's cooldown
                # expires: that round the failed phase spends the non-live start.
                await asyncio.sleep(max(0, until - _mono() - .05))
                second_at = _mono()
                await _tick(ns, 'h1', .39, .41)
                await _tick(ns, 'h2', .59, .61)
                await _wait_until(healthy_at(.40, .60), 1.0)
                second_ms = (_mono() - second_at) * 1000
                await asyncio.sleep(1.0)  # traffic continues past a second cooldown
                held_active = held.is_active
                hold_s = _mono() - started
                x_attempts = [t for t, g in record.attempts if x1 in g]
                live_frames = len([1 for _, m, _ in record.publications
                                   if m == ids['markets']['live']])
                prop_frames = len([1 for _, m, _ in record.publications
                                   if m == ids['markets']['pregame']])
            finally:
                stop.set()
                await traffic
                await held.rollback()
    stored = await _stored(side)
    first_plan = next(p for p in record.plans if any(x1 in g for g in p) and any(h1 in g for g in p))
    print('EVIDENCE', json.dumps(dict(
        first_plan=[sorted(g) for g in first_plan], first_ms=first_ms, second_ms=second_ms,
        hold_s=hold_s, x_attempts=len(x_attempts), live_frames=live_frames,
        prop_frames=prop_frames, stats=dict(ns['stats']))))
    assert held_active
    # Precondition: the healthy future is in a different phase from the locked one.
    assert {x1, x2} in first_plan and {h1, h2} in first_plan
    # Live traffic kept flowing beside the held future (not a starved board).
    assert live_frames >= 5 and prop_frames >= 5
    # The locked phase's attempts are bounded by its cooldown, not the cadence.
    assert 1 <= len(x_attempts) <= int(hold_s / kalshi_ws.PRICE_FLUSH_SECONDS) + 2
    # Released, everything lands.
    assert stored[x1][0] == .80 and stored[h1][0] == .40 and stored[h2][0] == .60
    assert not ns['price_buffer']


async def _a(value):
    return value


@pytest.mark.parametrize('cap', [200, 4])
async def test_observation_a_standalone_future_packed_with_the_locked_one_waits_for_it(
    pg, monkeypatch, cap,
):
    """Known coupling: standalone futures share key None and pack together.
    At the production cap (200) the healthy future shares the locked
    future's phase in parent and candidate alike. At a cap of 4 rows, with
    batch order x, p, h, parent packs [x, p] [h] and the candidate [x, h]
    [p]: taking the prop out moves the next future into the locked phase.
    Rows per phase stay bounded by the unchanged cap, so a lock failure
    rolls back no more rows than before; WHICH rows changes (live props are
    no longer among them). Recorded, not asserted: the ship here is the
    live prop's progress, which is asserted."""
    from app.tasks import kalshi_ws

    engine, side, ids = pg
    monkeypatch.setattr(kalshi_ws, 'NONLIVE_PHASE_MAX_ROWS', cap)
    healthy = await _healthy_future(side, ids)
    legs = {**ids['legs'], **ids['healthy_legs']}
    x1, x2, h1, h2, p1, p2 = (legs[k] for k in ('x1', 'x2', 'h1', 'h2', 'p1', 'p2'))
    ns, record = await _qualified_rig(engine, side, ids)
    _add_healthy_to(ns, ids)
    for leg, bid in (('x1', .79), ('x2', .19), ('p1', .64), ('p2', .34), ('h1', .34), ('h2', .64)):
        await _tick(ns, leg, bid, bid + .02)

    async def prop_published():
        return bool(_published(record, ids['markets']['pregame'], {p1: .65, p2: .35}))

    async with _holding(side, x1) as held:
        async with _consumer(ns):
            try:
                await _wait_for_a_lock_wait(side)
                with contextlib.suppress(TimeoutError):
                    await _wait_until(prop_published, 1.25)
                await asyncio.sleep(2 * PERIOD)
                prop_before = bool(_published(record, ids['markets']['pregame'], {p1: .65, p2: .35}))
                healthy_before = bool(_published(record, healthy, {h1: .35, h2: .65}))
                held_active = held.is_active
            finally:
                await held.rollback()
    first = record.plans[0]
    locked = next(g for g in first if x1 in g)
    print('EVIDENCE', json.dumps(dict(
        cap=cap, first_plan=[sorted(g) for g in first], locked_phase_rows=len(locked),
        prop_before_release=prop_before, healthy_before_release=healthy_before)))
    assert held_active
    assert len(locked) <= cap
    assert {p1, p2} in first and not locked & {p1, p2}
    assert prop_before, 'the live prop waited on an unrelated locked future'
    stored = await _stored(side)
    assert stored[h1][0] == .35 and stored[p1][0] == .65 and not ns['price_buffer']
