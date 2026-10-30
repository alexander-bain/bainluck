"""#10090 — the Polymarket flush's headline-event view answers without a KeyError per miss.

Production 2026-10-30 12:33-13:17Z: the Polymarket venue process ran at
cpu=0.93-0.95 while its worst moved prices waited 6-11 s. Each game flush
(every 0.25 s, and on every wake) reads `_PMHeadlineEvents` once per buffered
outcome, and most of the buffer is the open-contract backlog with no event
(the 'deferred' counter: ~3.3k rows/s at 13:12Z). `Mapping.get` / `in` answer
a miss by raising and catching KeyError. The Kalshi twin was fixed the same
way (`_KalshiHeadlineEvents`, test_kalshi_headline_view_cpu_10090.py).

These pin the same answers, and that a miss or an excluded outcome no longer
costs a raised exception.
"""

import random
from collections.abc import Mapping

from app.tasks.live_blend_refresh import event_ids_for_outcomes
from app.tasks.polymarket_ws import _PMHeadlineEvents


def _view(seed=11):
    rng = random.Random(seed)
    events = {oid: 900 + oid // 3 for oid in range(1, 400)}
    events[7] = None  # an admitted outcome with no event
    non_speakers = set(rng.sample(sorted(events), 60))
    return _PMHeadlineEvents(events, non_speakers), events, non_speakers


KEYS = list(range(-5, 450)) + [10_000_000 + i for i in range(50)]


def test_get_and_contains_give_the_mapping_answers():
    view, _, _ = _view()
    sentinel = object()
    for oid in KEYS:
        assert view.get(oid) == Mapping.get(view, oid)
        assert view.get(oid, sentinel) == Mapping.get(view, oid, sentinel)
        assert (oid in view) is Mapping.__contains__(view, oid)


def test_the_final_drains_view_with_no_non_speakers_is_the_owner_map():
    events = {1: 10, 2: None, 3: 30}
    view = _PMHeadlineEvents(events, ())
    for oid in (0, 1, 2, 3, 4):
        assert view.get(oid) == events.get(oid)
        assert (oid in view) is (oid in events)


def test_owner_maps_are_read_in_place():
    view, events, non_speakers = _view()
    assert view.get(10_000_001) is None and 10_000_001 not in view
    events[10_000_001] = 4242  # a catalog boundary bridges an open contract
    assert view.get(10_000_001) == 4242 and 10_000_001 in view
    non_speakers.add(10_000_001)
    assert view.get(10_000_001) is None and 10_000_001 not in view


def test_a_miss_raises_nothing():
    class Counting(_PMHeadlineEvents):
        raised = 0

        def __getitem__(self, outcome_id):
            Counting.raised += 1
            return super().__getitem__(outcome_id)

    _, events, non_speakers = _view()
    view = Counting(events, non_speakers)
    misses = [10_000_000 + i for i in range(1000)] + sorted(non_speakers)
    assert all(view.get(oid) is None for oid in misses)
    assert not any(oid in view for oid in misses)
    assert event_ids_for_outcomes(view, misses) == set()
    assert Counting.raised == 0


def test_event_ids_for_outcomes_is_unchanged():
    view, events, non_speakers = _view()
    rng = random.Random(5)
    for size in (0, 5, 399, 2000):
        ids = [rng.choice(KEYS) for _ in range(size)]
        expected = {
            events[oid] for oid in ids
            if oid in events and oid not in non_speakers and events[oid] is not None
        }
        assert event_ids_for_outcomes(view, ids) == expected
