"""#1958 — the ladder admission arm, over real production rows.

**The defect was a shape mismatch, not a threshold.** The audit targets
`boring-rate@20 = 0` and `ladder-rate@20 = 0` — aggregate counts over the first
twenty SERVED cards. The only aggregate control was
`cap_low_quality_families(cap=1)`, a cap PER FAMILY. PROGRAM UX cycle 95 cleared
every other candidate against real rows: not misclassification (all four reasons
correct), not staleness (a forced `x-feed-cache: miss` build put the same card at
the same rank), and not a cap failure — there was **exactly one** `low_quality`
row in all 44 futures and zero `suppress`, so the per-family cap never had a
sibling to fire on. No value of that cap can enforce a per-page target.

Fable ruling (d), 2026-08-18: named Alex exclusions remain the ONLY hard-drops;
ladders get their own admission arm with an aggregate control matched to the
aggregate target.

**The corpus is the served page, not a hand-written specimen.** Every row in
`tests/fixtures/discover_first_page_production_corpus_1958.json` came off
`GET /api/feed` on a forced fresh build. The #1976-style census below asserts the
transition class of every card the control moves — that the intended transitions
happen AND that no card makes any other transition — because a control that
reorders more than it was asked to is how a diversity cap emptied the Sports tab
(#1091/gotcha #43).
"""

import json
from pathlib import Path

import pytest

from app.utils.feed_market_quality import (
    classify_market_quality,
    enforce_first_page_quality_floor,
    is_first_page_quality_offender,
)

_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "discover_first_page_production_corpus_1958.json"
)
WINDOW = 20


def _load_cards() -> list[dict]:
    return json.loads(_FIXTURE.read_text())["cards"]


def _as_feed_items(cards: list[dict]) -> list[dict]:
    """Rebuild feed items from the served rows, stamped the way the server
    stamps them (`_quality_class`, `_quality_ladder_or_bucket`)."""
    items = []
    for card in cards:
        item = {
            "type": card["type"],
            "score": card["score"],
            "_rank_score": card["score"],
            "_sort_time": 0,
            "data": {
                "id": card["id"],
                "name": card["name"],
                "llm_sport_category": card["llm_sport_category"],
                "status": card["status"],
            },
            "_served_rank": card["served_rank"],
        }
        if card["type"] == "futures":
            quality = classify_market_quality(
                market_name=card["name"],
                sport_category=card["llm_sport_category"],
                outcome_names=card["outcome_names"],
            )
            item["_quality_class"] = quality.quality_class
            item["_quality_family_key"] = quality.family_key
            item["_quality_story_key"] = quality.story_key
            item["_quality_ladder_or_bucket"] = quality.is_ladder_or_bucket
        items.append(item)
    return items


def _offender_ranks(items: list[dict], window: int = WINDOW) -> list[int]:
    return [
        idx
        for idx, item in enumerate(items[:window], start=1)
        if is_first_page_quality_offender(item)
    ]


class TestTheCorpusReproducesTheDefect:
    """A fixture that is already clean proves nothing about a cleaner."""

    def test_the_served_page_really_did_fail_both_metrics(self):
        items = _as_feed_items(_load_cards())
        boring = [
            i
            for i in items[:WINDOW]
            if i.get("_quality_class") in ("low_quality", "suppress")
        ]
        ladder = [i for i in items[:WINDOW] if i.get("_quality_ladder_or_bucket")]
        assert boring, "corpus no longer carries a boring card in the top 20"
        assert ladder, "corpus no longer carries a ladder card in the top 20"

    def test_the_ladder_is_the_meta_card_the_sentinel_flagged(self):
        items = _as_feed_items(_load_cards())
        ladders = [
            i["data"]["name"]
            for i in items[:WINDOW]
            if i.get("_quality_ladder_or_bucket")
        ]
        assert any("Meta (META) close above" in name for name in ladders), (
            f"the #1958 specimen is not in the window any more: {ladders}"
        )

    def test_the_per_family_cap_could_never_have_caught_it(self):
        # The mechanism/target mismatch, stated as an assertion: the offending
        # cards have DISTINCT families, so a per-family cap of 1 admits every
        # one of them and the aggregate count is unbounded.
        items = _as_feed_items(_load_cards())
        offenders = [i for i in items[:WINDOW] if is_first_page_quality_offender(i)]
        families = [i.get("_quality_family_key") for i in offenders]
        assert len(set(families)) == len(families), (
            "these offenders share a family, so this corpus no longer "
            "demonstrates why a per-family cap cannot enforce a per-page target"
        )


class TestTheAggregateControlMeetsTheAggregateTarget:
    def test_zero_offenders_remain_in_the_first_page_window(self):
        items = _as_feed_items(_load_cards())
        assert _offender_ranks(items), "precondition: the page starts dirty"

        out, meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)

        assert _offender_ranks(out) == [], (
            "the control's postcondition IS the metric: boring-rate@20 = 0 and "
            f"ladder-rate@20 = 0. Remaining: {_offender_ranks(out)}"
        )
        assert meta["unreplaced"] == 0
        assert meta["demoted"] == meta["offenders_in_window"]

    def test_the_target_is_met_for_the_metric_window_not_just_the_page_slice(self):
        # `boring-rate@20` is counted over 20 cards whatever `limit` the client
        # asked for. Enforcing over a smaller window would pass a page-slice test
        # and still fail the sentinel.
        items = _as_feed_items(_load_cards())
        out, _meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        assert _offender_ranks(out, window=20) == []


class TestTransitionCensus:
    """#1976 style: assert the intended transitions AND the absence of any other."""

    def test_nothing_is_dropped_and_the_page_does_not_shrink(self):
        # Ruling (d): named Alex exclusions remain the ONLY hard-drops. A ladder
        # is demoted, never deleted.
        items = _as_feed_items(_load_cards())
        out, _meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        assert len(out) == len(items)
        assert sorted(id(i) for i in out) == sorted(id(i) for i in items), (
            "the control must be a pure reorder — same objects, same count"
        )

    def test_every_card_that_left_the_window_is_an_offender(self):
        items = _as_feed_items(_load_cards())
        before = {id(i) for i in items[:WINDOW]}
        out, _meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        after = {id(i) for i in out[:WINDOW]}

        left = [i for i in items if id(i) in before - after]
        assert left, "nothing moved — the census would be vacuous"
        unintended = [
            i["data"]["name"] for i in left if not is_first_page_quality_offender(i)
        ]
        assert unintended == [], (
            f"clean cards were demoted off the first page: {unintended}"
        )

    def test_every_card_that_entered_the_window_is_clean(self):
        items = _as_feed_items(_load_cards())
        before = {id(i) for i in items[:WINDOW]}
        out, _meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        after_items = out[:WINDOW]

        entered = [i for i in after_items if id(i) not in before]
        assert entered, "nothing was promoted — the census would be vacuous"
        dirty = [
            i["data"]["name"] for i in entered if is_first_page_quality_offender(i)
        ]
        assert dirty == [], f"the control promoted offenders onto the page: {dirty}"

    def test_the_transition_count_is_exactly_the_offender_count(self):
        items = _as_feed_items(_load_cards())
        offenders = len(_offender_ranks(items))
        before = {id(i) for i in items[:WINDOW]}
        out, meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        after = {id(i) for i in out[:WINDOW]}

        assert len(before - after) == offenders
        assert len(after - before) == offenders
        assert meta["demoted"] == offenders

    def test_clean_cards_keep_their_relative_order(self):
        # A swap, not a re-sort. Anything beyond the swap would silently
        # relitigate `compose_lead`'s prefix contract (C185).
        items = _as_feed_items(_load_cards())
        out, _meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)

        moved = {id(i) for i in items[:WINDOW] if is_first_page_quality_offender(i)}
        before_clean = [
            i["_served_rank"] for i in items[:WINDOW] if id(i) not in moved
        ]
        after_clean = [i["_served_rank"] for i in out[:WINDOW] if id(i) not in moved]
        # The promoted cards are new arrivals; drop them and compare the rest.
        after_survivors = [r for r in after_clean if r in set(before_clean)]
        assert after_survivors == before_clean


class TestItRefusesToEmptyTheSurface:
    """gotcha #43: a cap's guard must assert BOTH directions — the flood stays
    capped AND the adjacent surface stays populated. #1091 is the standing
    lesson about what happens when only the first direction is tested."""

    def test_a_page_of_nothing_but_offenders_keeps_its_length(self):
        items = _as_feed_items(_load_cards())
        for item in items:
            item["_quality_class"] = "low_quality"
        out, meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        assert len(out) == len(items), "a short page is worse than a boring one"
        assert meta["demoted"] == 0
        assert meta["unreplaced"] == meta["offenders_in_window"] > 0

    def test_the_shortfall_is_reported_rather_than_swallowed(self):
        # gotcha #53 / "no silent caps": giving up must not report the same
        # thing as succeeding.
        items = _as_feed_items(_load_cards())
        for item in items:
            item["_quality_class"] = "low_quality"
        _out, meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        assert meta["unreplaced"] > 0
        assert meta["clean_replacements_available"] == 0

    def test_a_clean_page_is_left_completely_alone(self):
        items = _as_feed_items(_load_cards())
        for item in items:
            item["_quality_class"] = "normal"
            item["_quality_ladder_or_bucket"] = False
        out, meta = enforce_first_page_quality_floor(items, first_page_size=WINDOW)
        assert [id(i) for i in out] == [id(i) for i in items]
        assert meta == {
            "offenders_in_window": 0,
            "demoted": 0,
            "unreplaced": 0,
            "clean_replacements_available": len(items) - WINDOW,
        }

    def test_an_empty_feed_does_not_raise(self):
        out, meta = enforce_first_page_quality_floor([], first_page_size=WINDOW)
        assert out == []
        assert meta["offenders_in_window"] == 0


class TestOffenderPredicate:
    @pytest.mark.parametrize(
        "item,expected",
        [
            ({"_quality_class": "normal"}, False),
            ({"_quality_class": "compelling"}, False),
            ({"_quality_class": "low_quality"}, True),
            ({"_quality_class": "suppress"}, True),
            ({"_quality_class": "normal", "_quality_ladder_or_bucket": True}, True),
            # Events and bundles carry no quality stamp and must never be
            # treated as offenders — that is the #1091 direction of this cap.
            ({"type": "event"}, False),
            ({"type": "bundle"}, False),
        ],
    )
    def test_predicate(self, item, expected):
        assert is_first_page_quality_offender(item) is expected

    def test_a_ladder_that_scored_normal_still_counts(self):
        # `ladder-rate@20` is its own metric. A ladder classified `normal`
        # fails it while passing `boring-rate@20`, so the predicate must be the
        # union, not the quality class alone.
        assert is_first_page_quality_offender(
            {"_quality_class": "normal", "_quality_ladder_or_bucket": True}
        )
