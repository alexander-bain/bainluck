"""#10090 — the flush's headline-event view answers without a KeyError per miss.

Production 2026-10-29: the Kalshi process ran at ~0.9 CPU while its saved
prices waited 6-18 s. The flush reads `_KalshiHeadlineEvents` once per
buffered outcome, several times per phase (the beside writer's filter, its
excluded events, each stamp's unfinished events), and most of the buffer is
open contracts with no event. `Mapping.get` / `in` answer a miss by raising
and catching KeyError, so that path was most of the flush's CPU (local lab at
a 60k buffer: cpu/wall 0.38 -> 0.10 with the same flush, rows and order).

These pin the same answers, and that a miss, an excluded outcome and a large
unfinished set no longer cost a per-outcome exception or lookup.
"""

import random
from collections.abc import Mapping

import pytest

from app.tasks.kalshi_ws import _KalshiHeadlineEvents
from app.tasks.live_blend_refresh import event_ids_for_outcomes


def _view(seed=11):
    rng = random.Random(seed)
    events = {oid: 900 + oid // 3 for oid in range(1, 400)}
    events[7] = None  # an admitted outcome with no event
    non_speakers = set(rng.sample(sorted(events), 60))
    return _KalshiHeadlineEvents(events, non_speakers), events, non_speakers


KEYS = list(range(-5, 450)) + [10_000_000 + i for i in range(50)]


def test_get_and_contains_give_the_mapping_answers():
    view, _, _ = _view()
    sentinel = object()
    for oid in KEYS:
        assert view.get(oid) == Mapping.get(view, oid)
        assert view.get(oid, sentinel) == Mapping.get(view, oid, sentinel)
        assert (oid in view) is Mapping.__contains__(view, oid)


def test_a_bridge_admitted_in_place_is_seen_at_once():
    view, events, non_speakers = _view()
    assert view.get(10_000_001) is None and 10_000_001 not in view
    events[10_000_001] = 4242  # admission bridges an open contract
    assert view.get(10_000_001) == 4242 and 10_000_001 in view
    non_speakers.add(10_000_001)  # the view reads the owner sets in place
    assert view.get(10_000_001) is None and 10_000_001 not in view


def test_a_miss_raises_nothing():
    class Counting(_KalshiHeadlineEvents):
        raised = 0

        def __getitem__(self, outcome_id):
            Counting.raised += 1
            return super().__getitem__(outcome_id)

    _, events, non_speakers = _view()
    view = Counting(events, non_speakers)
    misses = [10_000_000 + i for i in range(1000)] + sorted(non_speakers)
    assert all(view.get(oid) is None for oid in misses)
    assert not any(oid in view for oid in misses)
    assert Counting.raised == 0


@pytest.mark.parametrize("size", [0, 5, 399, 400, 5000])
@pytest.mark.parametrize("kind", [set, frozenset, list, tuple])
def test_events_of_is_event_ids_for_outcomes(size, kind):
    view, _, _ = _view()
    rng = random.Random(size)
    ids = rng.sample(KEYS, min(size, len(KEYS))) + [
        20_000_000 + i for i in range(max(0, size - len(KEYS)))
    ]
    outcome_ids = kind(ids)
    assert view.events_of(outcome_ids) == event_ids_for_outcomes(view, outcome_ids)


def test_a_large_unfinished_set_is_matched_from_the_owner_map():
    view, events, _ = _view()
    unfinished = {10_000_000 + i for i in range(20_000)} | set(range(1, 60))
    looked_up = []
    original = view.get
    view.get = lambda oid, default=None: looked_up.append(oid) or original(oid, default)
    found = view.events_of(unfinished)
    assert looked_up == []  # no per-outcome lookup over the 20k open contracts
    view.get = original
    assert found == event_ids_for_outcomes(view, unfinished)


@pytest.mark.asyncio
async def test_beside_reads_no_event_for_the_owners_unfinished_outcomes(monkeypatch):
    """The beside writer's filter over the shipped `flush_prices` (the
    attribution rig): same batch, and the owner's unfinished outcomes are
    rejected before any event lookup."""
    from tests.test_kalshi_flush_wait_attribution_10090 import rig, tick

    looked_up = []
    shipped = _KalshiHeadlineEvents.get

    def recording(self, oid, default=None):
        looked_up.append(oid)
        return shipped(self, oid, default)

    monkeypatch.setattr(_KalshiHeadlineEvents, "get", recording)
    # Stamp starts read the unfinished set's events by design (checked above);
    # only the beside filter's own lookups are recorded here.
    monkeypatch.setattr(_KalshiHeadlineEvents, "events_of", lambda self, ids: {
        self.events[oid] for oid in ids
        if oid in self.events and oid not in self.non_speakers
        and self.events[oid] is not None
    }, raising=False)
    r = rig(games=3, live={5000, 5001, 5002})
    tick(r, 0, 1, 2)
    owner_unfinished = frozenset({0, 1, 2, 3})
    assert await r.flush(
        beside=(owner_unfinished, frozenset({5000, 5001}), frozenset({1000, 1001})),
        beside_stopping=lambda: False,
    ) is True
    assert r.stats["live_beside"] == 2  # game 2 only: outcomes 4 and 5
    assert set(r.buffer) == {0, 1, 2, 3}
    assert looked_up and owner_unfinished.isdisjoint(looked_up)
