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
        assert values == [202604, 202607, 202610, 202701]

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
        ("Before October", (None, 10)),
        ("Before Oct", (None, 10)),
        ("By December", (None, 12)),
        ("After March", (None, 3)),
        ("Before 2027", (2027, 1)),
        ("By 2030", (2030, 1)),
        ("March 2027", (2027, 3)),
        ("2029 or later", (2029, 1)),
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
        assert [p["value"] for p in card["threshold_points"]] == [202701, 202801, 203001]


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
