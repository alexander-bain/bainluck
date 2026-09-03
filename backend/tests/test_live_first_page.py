"""#2709 (Alex P1) — a live game reaches the first page of the sports feed.

WHAT THE ARMS ARE, BECAUSE THEY ARE NOT THE USUAL SHAPE
--------------------------------------------------------
`hoist_live_events_into_first_page` is NEW logic, not a changed line, so a
"revert to the parent" arm cannot exercise it — the module does not exist on the
parent and the file would fail to import. Red-first grades a CHANGE; counter-
cases grade an ADDITION (ux/1019's lesson #8). So:

* The RED ARM for this ship lives at the route level
  (`tests/integration/test_route_feed_live_first_page_2709.py`), where reverting
  only the call site in `apply_discover_display_chain` — keeping the import, or
  it dangles and you get a collection error rather than a red arm — turns the
  served payload back into the reported defect.
* The four COUNTER-CASES below are what grade this module. Each is a fix a
  reader could plausibly write from the issue text, and each fails differently.

THE CORPUS IS REAL, AND IN SERVED ORDER
----------------------------------------
`fixtures/sports_feed_served_order_2709.json` is the actual
`GET /api/feed?mode=sports&limit=200` response of 2026-09-03, 154 items, in the
order production served them, trimmed to the fields this pass reads. Every
number asserted below was measured by replaying the SHIPPED function over it —
not by a script that reimplements the rule (ux/1016's lesson #4).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.utils.live_first_page import (
    LIVE_FIRST_PAGE_WINDOW_SHARE,
    MARQUEE_PIN_KEY,
    hoist_live_events_into_first_page,
    is_hoistable_live_event,
    live_first_page_budget,
)

CORPUS_PATH = (
    Path(__file__).parent / "fixtures" / "sports_feed_served_order_2709.json"
)


def _corpus() -> list[dict]:
    return json.loads(CORPUS_PATH.read_text())


def _live_slots(items: list[dict]) -> list[int]:
    return [i + 1 for i, it in enumerate(items) if is_hoistable_live_event(it)]


def _event(status="live", prob=0.56, **data) -> dict:
    d = {"status": status, "current_odds": {"home_probability": prob}}
    d.update(data)
    return {"type": "event", "data": d}


def _filler(n: int, status="completed") -> list[dict]:
    return [_event(status=status, prob=0.5, id=f"filler-{i}") for i in range(n)]


# ---------------------------------------------------------------------------
# The corpus: the reported defect, and the ship, as measured numbers
# ---------------------------------------------------------------------------


class TestServedCorpus:
    def test_the_corpus_reproduces_the_reported_defect(self):
        """1 of 9 live games inside the 20-item first paint, the rest at 48-119.

        This is the state Alex reported, one day later and one worse: he saw a
        live rail with zero of six US Open matches; the corpus has nine live
        priced events and one on the page.
        """
        items = _corpus()
        assert len(items) == 154
        assert _live_slots(items) == [16, 48, 49, 102, 103, 104, 110, 111, 119]
        assert sum(1 for s in _live_slots(items) if s <= 20) == 1

    def test_every_live_game_reaches_the_first_page(self):
        items = _corpus()
        out, meta = hoist_live_events_into_first_page(items, first_page_size=20)

        assert meta["live_in_window_before"] == 1
        assert meta["live_available_beyond"] == 8
        assert meta["hoisted"] == 8
        assert meta["live_in_window_after"] == 9
        assert meta["unhoisted"] == 0
        assert _live_slots(out) == [12, 13, 14, 15, 16, 17, 18, 19, 20]

    def test_the_page_keeps_its_length_and_loses_nothing(self):
        """A swap, not a filter. #1091: changing a feed cap is how Sports emptied."""
        items = _corpus()
        out, _ = hoist_live_events_into_first_page(items, first_page_size=20)

        assert len(out) == len(items)
        assert sorted(map(id, out)) == sorted(map(id, items))

    def test_no_score_is_touched(self):
        """A pure reorder. Every dict is the SAME object, not a rewritten copy."""
        items = _corpus()
        before = [json.dumps(it, sort_keys=True) for it in items]
        out, _ = hoist_live_events_into_first_page(items, first_page_size=20)
        after = sorted(json.dumps(it, sort_keys=True) for it in out)

        assert after == sorted(before)

    def test_the_displaced_cards_are_still_in_the_feed(self):
        """The eight displaced cards moved down; none of them left."""
        items = _corpus()
        window_before = {id(it) for it in items[:20]}
        out, _ = hoist_live_events_into_first_page(items, first_page_size=20)
        window_after = {id(it) for it in out[:20]}

        displaced = window_before - window_after
        assert len(displaced) == 8
        assert displaced <= {id(it) for it in out[20:]}


# ---------------------------------------------------------------------------
# CONTROLS — green on this module and on any correct implementation of it
# ---------------------------------------------------------------------------


class TestControls:
    def test_CONTROL_a_pool_with_no_buried_live_game_is_returned_unchanged(self):
        items = _filler(30)
        out, meta = hoist_live_events_into_first_page(items, first_page_size=20)

        assert out == items
        assert meta["hoisted"] == 0

    def test_CONTROL_a_window_already_at_budget_is_not_topped_up(self):
        """Ten live rows already on the page is the cap; an eleventh does not enter."""
        items = [_event(id=f"live-{i}") for i in range(10)] + _filler(10)
        items += [_event(id="buried")]
        out, meta = hoist_live_events_into_first_page(items, first_page_size=20)

        assert meta["live_in_window_before"] == 10
        assert meta["hoisted"] == 0
        assert meta["unhoisted"] == 1
        assert out == items

    def test_CONTROL_a_suspended_match_is_not_a_live_game(self):
        """`liveSectionTitle` renames the whole rail "Live & Paused" for one of
        these, so hoisting a rain delay changes the header for every reader."""
        items = _filler(20) + [_event(status="suspended", id="rain")]
        out, meta = hoist_live_events_into_first_page(items, first_page_size=20)

        assert meta["hoisted"] == 0
        assert out == items

    def test_CONTROL_the_marquee_prefix_survives(self):
        """C185: `compose_lead` owns the front of the deck and this must not."""
        marquee = _filler(1, status="scheduled")[0]
        marquee[MARQUEE_PIN_KEY] = True
        items = [marquee] + _filler(19) + [_event(id="buried")]
        out, meta = hoist_live_events_into_first_page(items, first_page_size=20)

        assert meta["hoisted"] == 1
        assert out[0] is marquee

    def test_CONTROL_an_empty_or_short_pool_is_safe(self):
        assert hoist_live_events_into_first_page([], first_page_size=20)[0] == []
        one = [_event(id="only")]
        assert hoist_live_events_into_first_page(one, first_page_size=20)[0] == one


# ---------------------------------------------------------------------------
# The admission predicate — the seam that has bitten twice
# ---------------------------------------------------------------------------


class TestAdmission:
    def test_a_Decimal_probability_is_a_number(self):
        """`Numeric` columns reach Python as `Decimal`, which is NOT a `float`
        and NOT a `numbers.Real`. #2554 and UX-P276 both paid this."""
        assert is_hoistable_live_event(_event(prob=Decimal("0.5656")))

    def test_a_bool_is_not_a_probability(self):
        assert not is_hoistable_live_event(_event(prob=True))

    @pytest.mark.parametrize("bad", [None, "0.56", float("nan"), float("inf")])
    def test_an_unusable_value_is_not_a_price(self, bad):
        assert not is_hoistable_live_event(_event(prob=bad))

    def test_an_away_only_price_still_counts(self):
        item = {
            "type": "event",
            "data": {"status": "live", "current_odds": {"away_probability": 0.4}},
        }
        assert is_hoistable_live_event(item)

    def test_an_unpriced_live_row_is_out_of_scope(self):
        """Alex's criterion is "live AND a price". A card with no number is the
        thing #2710 had just removed from this page."""
        item = {"type": "event", "data": {"status": "live"}}
        assert not is_hoistable_live_event(item)

    def test_a_futures_card_is_not_a_live_game(self):
        item = {"type": "futures", "data": {"status": "live", "current_odds": {"home_probability": 0.5}}}
        assert not is_hoistable_live_event(item)

    def test_malformed_items_do_not_raise(self):
        for junk in [None, {}, {"type": "event"}, {"type": "event", "data": None}]:
            assert not is_hoistable_live_event(junk)


class TestBudget:
    def test_the_budget_is_half_the_window(self):
        assert live_first_page_budget(20) == 10
        assert LIVE_FIRST_PAGE_WINDOW_SHARE == 2

    def test_a_tiny_window_still_admits_one(self):
        assert live_first_page_budget(1) == 1

    def test_a_live_flood_can_take_at_most_half_the_page(self):
        """2026-08-21: 2,911 live esports rows took 488 of 500 slots and the feed
        served one real game, twice. That is why there is a cap at all."""
        items = _filler(20) + [_event(id=f"flood-{i}") for i in range(2911)]
        out, meta = hoist_live_events_into_first_page(items, first_page_size=20)

        assert meta["hoisted"] == 10
        assert sum(1 for it in out[:20] if is_hoistable_live_event(it)) == 10
        assert sum(1 for it in out[:20] if not is_hoistable_live_event(it)) == 10
        assert meta["unhoisted"] == 2901
