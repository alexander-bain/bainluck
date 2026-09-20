"""UX-1052 item 4 — a date question renders as an ordered timeline, not one number.

THE DEFECT, VERBATIM. Alex, shopping Discover at 1:00pm PT on 2026-09-03:

    "Multi-outcome date questions are unreadable. Discover card 'When will Apple
     release the iPhone 18?' shows one number (15%, 'Before 2027') and a
     sentence that says the same thing twice … Design: outcomes as ordered bars
     (Before Oct · Before 2027 · …) with the leader marked and the mover marked
     … Applies to every date-bucket / multi-outcome futures card, not this one."

THE MECHANISM, from ``GET /api/futures/109349`` on 2026-09-03. The market's four
outcomes are "Before 2027" (15%), "Before October" (6.5%), "Before April" (1%),
"Before July" (1%). Not one of them is a threshold:

  * ``_compact_value_thresholds`` REFUSES a bare year in 2020–2099 without a
    unit, and that refusal is load-bearing — it is what stops "2026-27 Stanley
    Cup® Winner" scoring a rung at 27 and collapsing a 32-team field to one row.
  * A month name carries no number at all.

So ``threshold_points`` came back empty, the market had only two card-eligible
outcomes left after the fabricated-book filter, and the classifier fell through
to ``binary_probability`` — the one-number card Alex was looking at.

A date bucket IS a rung whose axis is time. Parsing it as one puts the question
on the "by WHEN" ladder the design already owns (``threshold_heatmap`` +
``QuantityGroup wideLabels``), in chronological order.

WHAT DECIDES WHETHER THIS SHIPS OR WRECKS DISCOVER is the refusal, again. This
parser runs over every outcome label on the site, and a false positive turns a
candidate field into a fake timeline. ``TestNotADateBucket`` is that arm, and it
carries the specific regression the numeric parser's year guard was written for.
"""

import pytest

from app.utils.discover_card_archetypes import (
    _parse_date_bucket,
    classify_discover_card_archetype,
)


def _iphone_outcomes():
    """The real market, as the feed hands it to the classifier."""
    return [
        {"name": "Before 2027", "probability": 0.15, "movement": -0.02},
        {"name": "Before October", "probability": 0.065, "movement": -0.305},
        {"name": "Before April", "probability": 0.01, "movement": None},
        {"name": "Before July", "probability": 0.01, "movement": None},
    ]


class TestTheIPhoneCardBecomesALadder:
    def test_it_is_no_longer_a_one_number_card(self):
        card = classify_discover_card_archetype(
            name="When will Apple release the iPhone 18?",
            category="tech",
            outcomes=_iphone_outcomes(),
            outcome_count=4,
            group_id="kalshi:KXIPHONERELEASE-IPHONE18",
        )
        assert card["suggested_format"] == "threshold_heatmap"

    def test_every_outcome_gets_a_rung(self):
        card = classify_discover_card_archetype(
            name="When will Apple release the iPhone 18?",
            outcomes=_iphone_outcomes(),
            outcome_count=4,
        )
        assert [p["label"] for p in card["threshold_points"]] == [
            "Before April", "Before July", "Before October", "Before 2027",
        ]

    def test_the_order_is_chronological_which_is_the_whole_point(self):
        # Alex wrote the order himself: "(Before Oct · Before 2027 · …)".
        # A month-only bucket sits in the year BEFORE the first dated one, which
        # is the only reading under which the sequence is a sequence.
        card = classify_discover_card_archetype(
            name="When will Apple release the iPhone 18?",
            outcomes=_iphone_outcomes(),
            outcome_count=4,
        )
        values = [p["value"] for p in card["threshold_points"]]
        assert values == sorted(values)
        # #7403 widened the encoding from YYYYMM to YYYYMMDD so two rungs in one
        # month cannot tie. A bucket that names no day carries day 00, which is
        # why these four are unchanged apart from the two trailing zeroes.
        assert values == [20260400, 20260700, 20261000, 20270100]

    def test_movement_rides_along_so_the_mover_can_be_marked(self):
        # `top_outcomes` is the top THREE, so a rung outside it had no movement
        # to show — and on this card the mover (-30.5 points) is the SECOND
        # bucket. The rung carries its own.
        card = classify_discover_card_archetype(
            name="When will Apple release the iPhone 18?",
            outcomes=_iphone_outcomes(),
            outcome_count=4,
        )
        by_label = {p["label"]: p for p in card["threshold_points"]}
        assert by_label["Before October"]["movement"] == pytest.approx(-0.305)
        assert by_label["Before April"]["movement"] is None

    def test_probabilities_are_carried_not_recomputed(self):
        card = classify_discover_card_archetype(
            name="When will Apple release the iPhone 18?",
            outcomes=_iphone_outcomes(),
            outcome_count=4,
        )
        by_label = {p["label"]: p for p in card["threshold_points"]}
        assert by_label["Before 2027"]["probability"] == 0.15


class TestParsingDateBuckets:
    @pytest.mark.parametrize("label,expected", [
        # Month granularity — day 0, meaning "this bucket names no day".
        ("Before October", (None, 10, 0)),
        ("Before Oct", (None, 10, 0)),
        ("By December", (None, 12, 0)),
        ("After March", (None, 3, 0)),
        ("Before 2027", (2027, 1, 0)),
        ("By 2030", (2030, 1, 0)),
        ("March 2027", (2027, 3, 0)),
        ("2029 or later", (2029, 1, 0)),
        # #7403 — day granularity, which is how Polymarket writes a "by when?"
        # ladder. No before/by framing, because the day IS the framing.
        ("December 31", (None, 12, 31)),
        ("June 30, 2027", (2027, 6, 30)),
        ("Jan 1", (None, 1, 1)),
        ("December 31st", (None, 12, 31)),
        ("Mar 3, 2026", (2026, 3, 3)),
        ("By December 31", (None, 12, 31)),
        ("Feb 29", (None, 2, 29)),
        ("Feb 29, 2028", (2028, 2, 29)),
    ])
    def test_parsed(self, label, expected):
        assert _parse_date_bucket(label) == expected

    def test_a_ladder_with_no_year_anywhere_still_orders_by_month(self):
        card = classify_discover_card_archetype(
            name="When will the report land?",
            outcomes=[
                {"name": "Before December", "probability": 0.5},
                {"name": "Before March", "probability": 0.2},
                {"name": "Before September", "probability": 0.3},
            ],
            outcome_count=3,
        )
        assert [p["label"] for p in card["threshold_points"]] == [
            "Before March", "Before September", "Before December",
        ]

    def test_a_ladder_of_pure_years_orders_by_year(self):
        card = classify_discover_card_archetype(
            name="When will the mission launch?",
            outcomes=[
                {"name": "Before 2030", "probability": 0.4},
                {"name": "Before 2027", "probability": 0.2},
                {"name": "Before 2028", "probability": 0.3},
            ],
            outcome_count=3,
        )
        # #7403: YYYYMMDD, with day 00 for a bucket that names no day.
        assert [p["value"] for p in card["threshold_points"]] == [
            20270100, 20280100, 20300100,
        ]


class TestNotADateBucket:
    """The refusal arm. Every false positive here would turn a real field into
    a fabricated timeline."""

    @pytest.mark.parametrize("label", [
        "Florida Panthers",
        "Yes",
        "No",
        "Over 2.5 goals",
        "$1.5T-$2.0T",
        "Carlos Alcaraz",
        "October",            # a bare month with no cutoff framing is a LABEL
        "May",                # …and this one is also a common English word
        "Before 1600",        # outside the 1900–2999 window a market can mean
        "Before 12345",       # not a year at all
        "",
        # #7403 — the day arm's own refusals. "<word> <number>" is the single
        # commonest outcome shape on the site, so the month-name lookup and the
        # calendar bound are what keep it from swallowing half of them.
        "Over 2",
        "Top 5",
        "Above 5",
        "Under 10",
        "Tier 3",
        "Group 4",
        "Feb 30",             # a shape, not a date — the month has no 30th
        "February 30",
        "April 31",
        "Dec 32",
        "Feb 29, 2027",       # 2027 is not a leap year, so this day does not exist
    ])
    def test_refused(self, label):
        assert _parse_date_bucket(label) is None

    def test_a_partial_timeline_is_no_timeline(self):
        # One unparseable outcome and the whole date treatment is dropped. A
        # half-placed ladder looks authoritative about rungs it silently lost.
        card = classify_discover_card_archetype(
            name="When will Apple release the iPhone 18?",
            outcomes=_iphone_outcomes() + [{"name": "Never", "probability": 0.2}],
            outcome_count=5,
        )
        assert not any(p.get("source") == "date_bucket" for p in card["threshold_points"])

    def test_the_stanley_cup_field_is_untouched(self):
        # The named regression the year guard exists for: 32 team names must not
        # acquire rungs, and the "2026-27" in the title must not either.
        teams = [
            {"name": n, "probability": 0.11 - i * 0.003}
            for i, n in enumerate([
                "Florida Panthers", "Colorado Avalanche", "Edmonton Oilers",
                "Dallas Stars", "Carolina Hurricanes",
            ])
        ]
        card = classify_discover_card_archetype(
            name="2026-27 Stanley Cup® Finals Winner",
            outcomes=teams,
            outcome_count=32,
        )
        assert card["threshold_points"] == []
        assert card["suggested_format"] == "outcome_distribution"

    def test_a_single_date_outcome_is_not_a_ladder(self):
        card = classify_discover_card_archetype(
            name="Will it ship before October?",
            outcomes=[{"name": "Before October", "probability": 0.4}],
            outcome_count=1,
        )
        assert not any(p.get("source") == "date_bucket" for p in card["threshold_points"])


# ---------------------------------------------------------------------------
# #7403 — A DAY-GRANULARITY LADDER IS A LADDER.
#
# The month-granularity shapes above are how Kalshi and our own copy write a
# "by when?" question. Polymarket writes the same question in days, with no
# before/by framing at all, and every one of those labels was refused — so the
# cascade fell past the ladder arm to `count >= 4` and drew a ranked FIELD.
#
# Live on production 2026-09-19 23:35 PDT, inside the "Middle East" Discover
# bundle, market 3484764 ("Iran leadership change?"):
#
#     1  June 30, 2027   26%
#     2  December 31     15%
#     3  November 30      9%
#     4  October 31       6%
#     5  Field and 2 more outcomes
#
# Six outcomes summing to 55.5%, strictly nested and monotone in time — the
# definition of a cumulative ladder — ranked 1..4 as if they were rivals, with a
# "Field" row for the rest, directly beneath the card's OWN subtitle "26% chance
# BY June 30, 2027". The sibling member of that same expanded bundle (the Strait
# of Hormuz board) rendered as a proper ladder in the same screenshot, which is
# what makes this a contradiction rather than a preference.


def _iran_outcomes():
    """Market 3484764 as `/api/futures/3484764` served it, 2026-09-19."""
    return [
        {"name": "June 30, 2027", "probability": 0.255},
        {"name": "December 31", "probability": 0.145},
        {"name": "November 30", "probability": 0.085},
        {"name": "October 31", "probability": 0.055},
        {"name": "September 30", "probability": 0.014},
        {"name": "March 13", "probability": 0.001},
    ]


class TestADayGranularityLadderIsALadder:
    def test_the_iran_board_stops_being_a_ranked_field(self):
        card = classify_discover_card_archetype(
            name="Iran leadership change?",
            category="politics",
            outcomes=_iran_outcomes(),
            outcome_count=6,
            group_id="polymarket:255195",
        )
        assert card["suggested_format"] == "threshold_heatmap"
        assert "multi_outcome_distribution" not in card["reasons"]

    def test_every_rung_is_placed_and_none_is_lost(self):
        card = classify_discover_card_archetype(
            name="Iran leadership change?",
            outcomes=_iran_outcomes(),
            outcome_count=6,
        )
        assert len(card["threshold_points"]) == 6
        assert all(p["source"] == "date_bucket" for p in card["threshold_points"])

    def test_the_order_is_chronological_not_by_probability(self):
        # The defect's whole shape: ranked by probability, the board reads
        # 26 / 15 / 9 / 6 and calls the largest window the winner. Read as time,
        # the probabilities rise monotonically, which is what a cumulative
        # ladder looks like and what the reader is owed.
        card = classify_discover_card_archetype(
            name="Iran leadership change?",
            outcomes=_iran_outcomes(),
            outcome_count=6,
        )
        assert [p["label"] for p in card["threshold_points"]] == [
            "March 13", "September 30", "October 31",
            "November 30", "December 31", "June 30, 2027",
        ]
        probabilities = [p["probability"] for p in card["threshold_points"]]
        assert probabilities == sorted(probabilities)

    def test_the_undated_rungs_are_anchored_to_the_year_before_the_dated_one(self):
        # "December 31" carries no year; "June 30, 2027" does. The undated rungs
        # belong to 2026, and the existing anchor rule already says so — this
        # asserts the day arm did not break it.
        card = classify_discover_card_archetype(
            name="Iran leadership change?",
            outcomes=_iran_outcomes(),
            outcome_count=6,
        )
        by_label = {p["label"]: p["value"] for p in card["threshold_points"]}
        assert by_label["December 31"] == 20261231
        assert by_label["June 30, 2027"] == 20270630

    def test_two_rungs_in_one_month_cannot_tie(self):
        # Why the encoding moved to YYYYMMDD. Under YYYYMM these two rungs
        # shared a sort value, so their order was whatever the input order was —
        # an ordering assertion that passes without ever being tested.
        card = classify_discover_card_archetype(
            name="When does the Fed cut?",
            outcomes=[
                {"name": "October 29", "probability": 0.6},
                {"name": "October 8", "probability": 0.2},
                {"name": "October 15", "probability": 0.4},
            ],
            outcome_count=3,
        )
        assert [p["label"] for p in card["threshold_points"]] == [
            "October 8", "October 15", "October 29",
        ]

    def test_a_field_whose_labels_look_like_dates_is_still_a_field(self):
        # The refusal arm at board level: one label that is not a date and the
        # whole day-granularity treatment is dropped, exactly as for months.
        card = classify_discover_card_archetype(
            name="Who leads after the reshuffle?",
            outcomes=_iran_outcomes() + [{"name": "No change", "probability": 0.4}],
            outcome_count=7,
        )
        assert card["threshold_points"] == []
        assert card["suggested_format"] == "outcome_distribution"

    def test_a_numbered_field_does_not_become_a_timeline(self):
        # "<word> <number>" is the shape the day arm had to be threaded past.
        card = classify_discover_card_archetype(
            name="Which tier wins?",
            outcomes=[
                {"name": "Tier 1", "probability": 0.4},
                {"name": "Tier 2", "probability": 0.3},
                {"name": "Tier 3", "probability": 0.2},
                {"name": "Tier 4", "probability": 0.1},
            ],
            outcome_count=4,
        )
        assert not any(
            p.get("source") == "date_bucket" for p in card["threshold_points"]
        )
