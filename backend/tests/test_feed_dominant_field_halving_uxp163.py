"""UX-P163: a no-bid "Other" must not sit in the divisor that scales a whole card.

MEASURED on the deployed build 2026-08-29 (`GET /api/feed?limit=100` plus the
politics, economics, entertainment and sports surfaces — 113 unique futures cards):
market 112903, "Which party will win the House in 2026?", served

    Democratic Party 0.4275 | Republican Party 0.0725 | Other 0.5

while `GET /api/futures/112903` served `0.855 / 0.145 / 1.0` at the same moment.
Discover printed **43%** for a party the book priced at **85.5%** — a 43-point
disagreement between two surfaces showing one market.

THE CHAIN (each step is correct on its own; the defect is the composition):

1. The market holds 9 outcomes. Six are anonymized reserved slots ("Party A".."Party
   F") at 1.0, and `display_rank_order` DROPS them — correctly.
2. A seventh 1.0 row is named "Other". It is not a placeholder, it is a FIELD
   outcome, so `display_rank_order` demotes it to the end instead — also correctly,
   and `test_other_at_100_leaves_the_top_n` pins that contract.
3. Three rows now remain, so "the end" is still inside a `[:3]` card.
4. Those three sum to EXACTLY 2.0 — the inclusive top of `_feed_display_scale`'s
   band — so the divisor became 2.0 and every printed number was halved.

Step 1 is what caused step 4: with the six placeholders still present the sum is
~8.0, above the band, and nothing would have been scaled at all. A filter that makes
a card more honest pulled the card into a scaling regime that made it less so.

THE REVERSE DIRECTION IS ASSERTED AS EXPLICITLY AS THE FIXED ONE. Vig removal on a
genuinely overround field is what `_feed_display_scale` is FOR (38 of the 113 live
cards are scaled, most by 1.06-1.25x), and an "Other" that genuinely carries mass at
0.55 is INFORMATION. Neither may change.
"""

import inspect

import pytest

from app.routes import feed
from app.routes.feed import (
    _apply_card_percents,
    _feed_display_scale,
    _normalize_feed_probabilities,
)
from app.utils.outcome_display import drop_dominant_field_outcomes


class _Outcome:
    """The only attributes the scale + slice read off an ORM row."""

    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability


def _name_of(o):
    return o.name


def _prob_of(o):
    return float(o.current_probability) if o.current_probability else None


def _card(outcomes):
    """Run the serializer's card path over a post-`display_rank_order` list."""
    card_outcomes = drop_dominant_field_outcomes(outcomes, _name_of, _prob_of)
    top = [
        {"name": o.name, "probability": _prob_of(o)} for o in card_outcomes[:3]
    ]
    top = _normalize_feed_probabilities(top, card_outcomes)
    reason = _apply_card_percents(top)
    return top, reason, _feed_display_scale(card_outcomes)


# The specimen, in the order `display_rank_order` hands it over: the six "Party X"
# placeholders already dropped, "Other" already demoted to the end.
def _house_112903():
    return [
        _Outcome("Democratic Party", 0.855),
        _Outcome("Republican Party", 0.145),
        _Outcome("Other", 1.0),
    ]


class TestTheSpecimen:
    def test_the_house_card_prints_the_book_price_not_half_of_it(self):
        top, _reason, scale = _card(_house_112903())

        assert scale == 1.0, "a coherent two-party field must not be scaled at all"
        printed = {o["name"]: o["rendered_percent"] for o in top}
        assert printed == {"Democratic Party": 86, "Republican Party": 14}

    def test_the_pre_fix_arithmetic_is_what_it_claims(self):
        # Guards the DIAGNOSIS, not the fix: if this stops reproducing, the comment
        # above is describing a chain that no longer exists and the fix's reason to
        # be here has changed.
        outcomes = _house_112903()
        assert _feed_display_scale(outcomes) == 2.0
        assert round(0.855 / 2.0, 4) == 0.4275

    def test_other_is_gone_from_the_card_entirely(self):
        # Not merely renumbered. A no-bid ask (bid 0.0000 / ask 1.0000, gotcha
        # #17/#19) rendered as "Other 100%" is the #993 defect verbatim, so leaving
        # it in and only fixing the divisor would trade one visible lie for another.
        top, _reason, _scale = _card(_house_112903())
        assert [o["name"] for o in top] == [
            "Democratic Party",
            "Republican Party",
        ]

    def test_the_two_surfaces_now_agree_on_the_leader(self):
        # `/api/futures/112903` served 0.855; half-up at this resolution is 86.
        top, _reason, _scale = _card(_house_112903())
        detail_leader_percent = int(0.855 * 100 + 0.5)
        assert top[0]["rendered_percent"] == detail_leader_percent == 86


class TestTheReverseDirection:
    def test_a_field_carrying_real_mass_is_kept_and_printed(self):
        # `_FIELD_DOMINANT_MIN` is 0.9 precisely so a wide-open race keeps its
        # "Other". This is the case the fix must NOT touch.
        outcomes = [
            _Outcome("Other", 0.55),
            _Outcome("Gavin Newsom", 0.22),
            _Outcome("Katie Porter", 0.18),
        ]
        top, _reason, scale = _card(outcomes)
        assert scale == 1.0
        assert [o["name"] for o in top] == ["Other", "Gavin Newsom", "Katie Porter"]

    def test_genuine_vig_removal_still_happens(self):
        # 38 of 113 live cards are scaled and most are this: an overround field whose
        # raw prices legitimately sum past 1.05. Nothing here is a field outcome, so
        # the divisor is untouched by the fix.
        outcomes = [
            _Outcome("Miami (FL)", 0.575),
            _Outcome("Clemson", 0.42),
            _Outcome("Duke", 0.245),
        ]
        top, _reason, scale = _card(outcomes)
        assert scale == pytest.approx(1.24)
        assert top[0]["probability"] == pytest.approx(0.4637, abs=1e-4)

    def test_a_sub_threshold_field_outcome_still_counts_in_the_divisor(self):
        # The drop is keyed on the SAME constant as the demotion. An 0.89 "Other" is
        # demoted by neither and scaled by both.
        outcomes = [
            _Outcome("Alice", 0.6),
            _Outcome("Bob", 0.3),
            _Outcome("Other", 0.89),
        ]
        assert _feed_display_scale(
            drop_dominant_field_outcomes(outcomes, _name_of, _prob_of)
        ) == pytest.approx(1.79)


class TestNeverEmpties:
    def test_an_all_field_market_is_returned_unchanged(self):
        # Same contract as `display_rank_order`: an honest-empty decision belongs to
        # the surface, and a silent zero-outcome card is worse than a labelled one.
        outcomes = [_Outcome("Other", 1.0), _Outcome("The Field", 0.95)]
        kept = drop_dominant_field_outcomes(outcomes, _name_of, _prob_of)
        assert [o.name for o in kept] == ["Other", "The Field"]

    def test_missing_probabilities_do_not_crash(self):
        outcomes = [_Outcome("Other", None), _Outcome("Alice", 0.4)]
        kept = drop_dominant_field_outcomes(outcomes, _name_of, _prob_of)
        assert [o.name for o in kept] == ["Other", "Alice"]


class TestBothSerializersMoved:
    """UX-P162's lesson, applied before it could bite: `FeedCard` and the Discover
    hero both headline this list, and fixing one serializer would have moved the
    disagreement rather than ended it. Source-level, mirroring
    `TestF5FeedUsesSharedPipeline`."""

    @pytest.mark.parametrize(
        "fn_name", ["_score_futures", "_score_sports_mode_futures"]
    )
    def test_the_drop_runs_before_the_scale(self, fn_name):
        src = inspect.getsource(getattr(feed, fn_name))
        assert "drop_dominant_field_outcomes(" in src, fn_name
        # ORDER matters: dropping after the divisor is computed leaves the halving
        # in place and only shortens the list it applies to.
        #
        # Anchored on the CALL SITE, not on the bare name. Both serializers carry a
        # comment naming `_feed_display_scale` above the drop, so a bare-name
        # `str.index` compares against prose and fails on a correct file — the
        # source-level equivalent of asserting an escaped entity instead of the
        # behaviour it stands for.
        assert src.index("drop_dominant_field_outcomes(") < src.index(
            "_display_scale = _feed_display_scale("
        ), f"{fn_name}: the drop must run BEFORE the display scale"

    @pytest.mark.parametrize(
        "fn_name", ["_score_futures", "_score_sports_mode_futures"]
    )
    def test_the_printed_slice_reads_the_dropped_list(self, fn_name):
        # The scale and the slice must agree on WHICH list is the card. Sports mode
        # sliced `sorted_outcomes[:3]` while scaling something else, which is how one
        # outcome ends up rendering two numbers (Queue 283 / #1487).
        src = inspect.getsource(getattr(feed, fn_name))
        assert "sorted_outcomes[:3]" not in src, fn_name
        assert "card_outcomes[:3]" in src, fn_name
