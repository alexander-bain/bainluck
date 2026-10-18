"""#10090 — a live game's prop publishes while an unrelated future is locked.

Root's attempt45 real-PG countercase, adopted: on deployed df2363aa15 the prop
shared the future's phase and had no publication through 1252 ms of the lock
(exit 1); with its own phase it published at ~321 ms, lock still held.
Real lock, production cadence, price SQL and committed publication readback.
The fixture records blend SQL; this is not a rendered-page latency test.
Adoption changes: the evidence file is written only when ATTEMPT45_RESULT is
set, and the absolute 1.0 s bound is dropped (runner speed): the bound is the
1.25 s wait from arrival with the lock still held (``held_active``).
"""
import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.integration.test_kalshi_live_beside_inflight_nonlive_10090_pg import (
    _consumer, _rig, _stored, _tick, _wait_until, pg,
)
from tests.integration.test_kalshi_price_lock_budget_pg_10661 import (
    _holding, _wait_for_a_lock_wait,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not os.environ.get('BLEND_DEADLOCK_DATABASE_URL'), reason='exclusive disposable PG required',
)]


async def test_live_prop_publishes_before_unrelated_future_unlocks(pg):
    engine, side, ids = pg
    legs, markets = ids['legs'], ids['markets']
    # Reuse the pregame market as a prop linked to the live event. It remains
    # excluded from the winner cohort in exactly the consumer's map view.
    async with side.begin() as conn:
        await conn.execute(text('UPDATE futures_markets SET event_id=:e WHERE id=:m'),
                           {'e': ids['event'], 'm': markets['pregame']})
    ns, record = _rig(engine, side, ids)
    for leg in ('p1', 'p2'):
        ns['event_id_by_outcome'][legs[leg]] = ids['event']
        ns['non_blend_outcome_ids'].add(legs[leg])
    async with side.connect() as conn:
        assert await conn.scalar(text('SELECT count(*) FROM bl_inflight_blocker')) == 0

    # Both questions arrive before the first snapshot: no timing race can
    # accidentally put the live prop in a successor flush in the parent.
    await _tick(ns, 'x1', .79, .81)
    await _tick(ns, 'x2', .19, .21)
    await _tick(ns, 'p1', .64, .66)
    await _tick(ns, 'p2', .34, .36)
    arrived = time.monotonic()
    selected = {legs[x] for x in ('x1', 'x2', 'p1', 'p2')}
    plan_ids = []
    planner = ns['linked_first_phases']

    def record_plan(*args, **kwargs):
        planned = planner(*args, **kwargs)
        if not plan_ids and set(args[0]) == selected:
            plan_ids.extend([list(p) for p in planned])
        return planned

    ns['linked_first_phases'] = record_plan

    async def winner_published():
        return any(m == markets['live'] and v[legs['home']] == .74
                   for _, m, v in record.publications)

    async def prop_published():
        return any(m == markets['pregame'] and v[legs['p1']] == .65
                   and v[legs['p2']] == .35 for _, m, v in record.publications)

    async with _holding(side, legs['x1']) as held:
        async with _consumer(ns):
            try:
                await _wait_for_a_lock_wait(side)
                # No winner input has arrived: prop-only activity cannot stamp.
                assert not record.stamps
                winner_arrived = time.monotonic()
                await _tick(ns, 'home', .73, .75)
                await _tick(ns, 'away', .25, .27)
                await _wait_until(winner_published, 1.0)
                try:
                    await _wait_until(prop_published, max(.01, arrived + 1.25 - time.monotonic()))
                except TimeoutError:
                    pass
                before_release = await _stored(side)
                held_active = held.is_active
                unpaid_before_release = dict(ns['price_buffer'])
                release_at = time.monotonic()
                before_publications = list(record.publications)
            finally:
                # The consumer's normal final drain can only finish after the
                # independently owned lock is released, including on failure.
                await held.rollback()

    stored = await _stored(side)
    assert plan_ids and set().union(*(set(p) for p in plan_ids)) == selected
    assert not ns['price_buffer']
    assert stored[legs['x1']][0] == .80 and stored[legs['x2']][0] == .20
    assert stored[legs['p1']][0] == .65 and stored[legs['p2']][0] == .35
    assert stored[legs['home']][0] == .74 and stored[legs['away']][0] == .26
    assert all(v[1] == v[2] for v in stored.values()), stored
    assert all(events == (ids['event'],) for _, events, _ in record.stamps)
    assert all(t >= winner_arrived for t, _, _ in record.stamps)
    prop_frames = [(t, v) for t, m, v in before_publications if m == markets['pregame']]
    winner_frames = [(t, v) for t, m, v in before_publications if m == markets['live']]
    observed = dict(planned_phase_ids=plan_ids, arrival=arrived, release_at=release_at,
                    held_active=held_active, before_release=before_release,
                    unpaid_before_release=unpaid_before_release,
                    before_publications=before_publications, publications=record.publications,
                    stamps=record.stamps, final=stored, stats=dict(ns['stats']),
                    winner_first_publish_ms=(winner_frames[0][0]-winner_arrived)*1000,
                    prop_first_publish_ms=(prop_frames[0][0]-arrived)*1000 if prop_frames else None)
    if os.environ.get('ATTEMPT45_RESULT'):
        output = Path(os.environ['ATTEMPT45_RESULT'])
        output.write_text(json.dumps(observed, indent=2)+'\n')
    print('EVIDENCE', json.dumps(observed))
    assert held_active
    assert prop_frames, 'unlocked live prop had no committed publication while unrelated future stayed locked'
