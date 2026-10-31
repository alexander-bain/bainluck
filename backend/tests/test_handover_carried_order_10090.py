"""#10090 `handover_fresh` — a carried hand-over population is ordered from the
live set, without a shared read of every event (sizing Fable's §A.4 warning).

With `handover_fresh` on, a catalog handover's shed (115-244 queued attempts
each in production 16:01-16:41Z 2026-10-31) is the next call's fresh
population (`574fa549`). A fresh population wider than the fixed workers first
ran `_prepare_groups` over all of it — order only; every queued stamp rereads
its own group — and `_read_groups` builds its rows in one synchronous pass:
~230 × 62 rows, ~1-1.7 s of venue loop CPU at ~5-7 ms per event read. The
carried population now takes live-first, held-first, id order from
`_live_event_ids` (the set the door routes live games by) and reads nothing up
front; only the call's own events (usually a few) are read for their order,
so its own fresh live price still leads. A population with nothing carried
keeps its prepare read.
"""

import asyncio

import pytest

from tests.test_single_event_commit_10090 import rig as refresher_rig

pytestmark = pytest.mark.asyncio

STATUSES = {
    1: "scheduled", 2: "live", 3: "scheduled", 4: "live",
    5: "scheduled", 6: "live", 7: "live",
}
LIVE = {eid for eid, status in STATUSES.items() if status == "live"}


def _recorded(x):
    prepares, stamps = [], []
    prepare, stamp = x.r._prepare_groups, x.r._refresh_batch

    async def recording_prepare(event_ids):
        prepares.append(sorted(event_ids))
        return await prepare(event_ids)

    async def recording_stamp(group_ids, *args, **kwargs):
        stamps.extend(group_ids)
        return await stamp(group_ids, *args, **kwargs)

    x.r._prepare_groups = recording_prepare
    x.r._refresh_batch = recording_stamp
    return prepares, stamps


async def test_a_carried_shed_is_ordered_live_then_held_and_only_the_calls_own_event_is_read(monkeypatch):
    x = refresher_rig(monkeypatch, count=7, statuses=STATUSES)
    x.r.reader_held = lambda: frozenset({6})
    x.r._live_event_ids = set(LIVE)
    # What `shed_queued` leaves with the arm on: owed, and carried as fresh.
    x.r._throttle_deferred = set(range(1, 7))
    x.r._carried_fresh = set(range(1, 7))
    prepares, stamps = _recorded(x)
    await asyncio.wait_for(x.r.refresh([7], flush_started=1020), 2)
    # Before: one `_prepare_groups` read of all seven events, for order only;
    # now only the call's own event.
    assert prepares == [[7]]
    assert stamps == [6, 2, 4, 7, 1, 3, 5]
    assert sorted(x.published) == list(range(1, 8))
    assert x.r.pending_event_ids() == frozenset() and x.r._carried_fresh == set()
    assert x.r.stats["errors"] == 0


async def test_the_live_set_not_a_read_decides_the_carried_order(monkeypatch):
    # The door's live set says 3 is live and 2 is not; the stored rows say the
    # opposite. The carried population follows the set it was queued by.
    x = refresher_rig(monkeypatch, count=5, statuses=STATUSES)
    x.r._live_event_ids = {3}
    x.r._throttle_deferred = {1, 2, 3, 4}
    x.r._carried_fresh = {1, 2, 3, 4}
    prepares, stamps = _recorded(x)
    await asyncio.wait_for(x.r.refresh([5], flush_started=1020), 2)
    assert prepares == [[5]]
    assert stamps == [3, 1, 2, 4, 5]
    assert x.r.pending_event_ids() == frozenset()


async def test_a_wide_fresh_population_with_nothing_carried_still_prepares(monkeypatch):
    x = refresher_rig(monkeypatch, count=7, statuses=STATUSES)
    x.r.reader_held = lambda: frozenset({6})
    prepares, stamps = _recorded(x)
    await asyncio.wait_for(x.r.refresh(list(range(1, 8)), flush_started=1020), 2)
    assert prepares == [list(range(1, 8))]
    assert stamps == [6, 2, 4, 7, 1, 3, 5]
    assert x.r.pending_event_ids() == frozenset()
    assert x.r.stats["errors"] == 0


async def test_this_calls_own_live_price_still_leads_and_only_it_is_read(monkeypatch):
    # 7 is the flush's own fresh price and was never stamped (not in the live
    # set): its own small read keeps it ahead of the carried cohort, as today.
    x = refresher_rig(monkeypatch, count=7, statuses=STATUSES)
    x.r._live_event_ids = {4}
    x.r._throttle_deferred = set(range(1, 7))
    x.r._carried_fresh = set(range(1, 7))
    prepares, stamps = _recorded(x)
    await asyncio.wait_for(x.r.refresh([7], flush_started=1020), 2)
    assert prepares == [[7]]
    assert stamps == [4, 7, 1, 2, 3, 5, 6]
    assert sorted(x.published) == list(range(1, 8))
    assert x.r.pending_event_ids() == frozenset()


async def test_a_quiet_flush_carrying_only_the_shed_reads_nothing_up_front(monkeypatch):
    x = refresher_rig(monkeypatch, count=6, statuses=STATUSES)
    x.r.reader_held = lambda: frozenset({6})
    x.r._live_event_ids = {2, 4, 6}
    x.r._throttle_deferred = set(range(1, 7))
    x.r._carried_fresh = set(range(1, 7))
    prepares, stamps = _recorded(x)
    await asyncio.wait_for(x.r.refresh_pending(flush_started=1020), 2)
    assert prepares == []
    assert stamps == [6, 2, 4, 1, 3, 5]
    assert sorted(x.published) == list(range(1, 7))
    assert x.r.pending_event_ids() == frozenset() and x.r._carried_fresh == set()
