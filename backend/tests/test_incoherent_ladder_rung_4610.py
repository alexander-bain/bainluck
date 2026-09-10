"""#4610 — a price that cannot be true is not evidence.

THE SPECIMEN, quoted from production `GET /api/feed?limit=100` on 2026-09-09 at
21:00 PT (market 60481162, admin trace `/api/admin/discover-quality/trace/`):

    Above 52   91.5%      Above 67   94.0%  <- impossible
    Above 58   88.0%      Above 70   41.0%
    Above 61   86.0%      Above 73   33.0%
    Above 64   80.5%      Above 76 / 82  unpriced

"Above 67" is a strict subset of "Above 58", so 94% over 88% is arithmetic that
does not close. The card did not merely draw that bar: the rung carried
`probability_change_24h +0.48`, `rank_change_24h +4` and an opening of 45%, so it
earned `major_movement_24h`, `leader_change`, `rank_shakeup` AND `major_surprise`
— all four of the card's reasons — which composed its headline and caption ("New
favorite: Above 67 (94%)") and carried its raw score to 101, page one at position
20 of 100. Every test below is a rung of that one finding.

THE TREATMENTS ARE PROVEN SEPARABLE FIRST (the CAL-P105 lesson): the coherent
twin of the specimen — same names, same movements, same ranks, one price changed
from 94% to 78% — is asserted to keep the leader change the impossible one loses.
Without that control, a guard that suppressed `leader_change` unconditionally
would pass every other test in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.futures_highlights import compute_futures_highlight
from app.utils.outcome_display import (
    drop_incoherent_ladder_outcomes,
    incoherent_ladder_indexes,
)


def _rungs(pairs):
    return [{"name": name, "probability": probability} for name, probability in pairs]


def _flagged(pairs):
    rows = _rungs(pairs)
    return {
        rows[index]["name"]
        for index in incoherent_ladder_indexes(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )
    }


# The production specimen, priced as served.
NETFLIX = [
    ("Above 52", 0.915),
    ("Above 58", 0.88),
    ("Above 61", 0.86),
    ("Above 64", 0.805),
    ("Above 67", 0.94),
    ("Above 70", 0.41),
    ("Above 73", 0.33),
    ("Above 76", None),
    ("Above 82", None),
]

# Its coherent twin: "Above 67" priced where the ladder says it belongs.
NETFLIX_COHERENT = [
    (name, 0.78 if name == "Above 67" else probability) for name, probability in NETFLIX
]


class TestWhichRungIsTheWrongOne:
    def test_the_netflix_specimen_names_above_67_and_nothing_else(self):
        assert _flagged(NETFLIX) == {"Above 67"}

    def test_its_coherent_twin_names_nothing(self):
        assert _flagged(NETFLIX_COHERENT) == set()

    def test_a_lone_low_rung_is_blamed_not_the_three_that_agree(self):
        # Production shape (Kalshi "Bass Persuades: Album Duration", 2026-09-09,
        # relabelled onto a grammar this law parses). 55 at 2% sits under 60/65/70,
        # which agree with each other and with everything below them. A scan that
        # flags whatever rises above the running floor blames those three and
        # keeps the broken rung as the ladder's definition of the truth.
        assert _flagged(
            [
                ("Above 25", 0.935),
                ("Above 40", 0.73),
                ("Above 50", 0.37),
                ("Above 55", 0.02),
                ("Above 60", 0.24),
                ("Above 65", 0.085),
                ("Above 70", 0.035),
            ]
        ) == {"Above 55"}

    def test_a_rising_ladder_is_read_the_other_way_up(self):
        # "Below N" nests upward: P(Below 60) >= P(Below 50). The dip is the break.
        assert _flagged(
            [
                ("Below 50", 0.10),
                ("Below 60", 0.02),
                ("Below 70", 0.40),
                ("Below 80", 0.85),
            ]
        ) == {"Below 60"}

    def test_two_priced_rungs_name_nobody_because_either_could_be_the_liar(self):
        assert _flagged([("Above 10", 0.30), ("Above 20", 0.90)]) == set()

    def test_a_half_point_dip_is_bid_ask_noise_and_stays_on_the_card(self):
        # Smallest strict reversal in the served population (Qwen, 16.0 -> 16.5).
        assert _flagged(
            [("Above 5.6", 0.16), ("Above 5.7", 0.165), ("Above 5.8", 0.15)]
        ) == set()

    def test_a_three_point_break_is_past_the_tolerance(self):
        assert _flagged(
            [("Above 5.6", 0.16), ("Above 5.7", 0.19), ("Above 5.8", 0.15)]
        ) == {"Above 5.7"}


class TestWhatIsNotALadderIsLeftAlone:
    def test_exclusive_bands_keep_every_row(self):
        # "SOFR for September 9, 2026" — exact bands partition, they do not nest,
        # and a favorite among them is a real thing.
        assert _flagged(
            [
                ("3.60% or Below", 0.025),
                ("Exactly 3.61%", 0.07),
                ("Exactly 3.62%", 0.115),
                ("Exactly 3.63%", 0.155),
                ("Exactly 3.64%", 0.245),
                ("Exactly 3.65%", 0.185),
                ("3.66% or Above", 0.145),
            ]
        ) == set()

    def test_two_comparator_tails_do_not_make_28_bands_a_ladder(self):
        # "Nasdaq-100 price range on Sep 11" — 30 outcomes, two of them tails.
        rows = [("27,999.99 or below", 0.28), ("30,800 or above", 0.01)]
        rows += [
            (f"{29_000 + 100 * n} to {29_099 + 100 * n}.99", 0.4 - 0.01 * n)
            for n in range(8)
        ]
        assert _flagged(rows) == set()

    def test_a_set_pointing_both_ways_is_not_one_ladder(self):
        assert _flagged(
            [("Above 10", 0.90), ("Above 20", 0.95), ("Below 30", 0.40)]
        ) == set()

    def test_named_candidates_are_untouched(self):
        assert _flagged(
            [("Los Angeles Dodgers", 0.30), ("New York Yankees", 0.22), ("Chicago Cubs", 0.9)]
        ) == set()


class TestTheFilterNeverEmpties:
    def test_it_returns_the_input_when_every_rung_is_incoherent(self):
        # Constructed so the longest coherent run cannot be empty; the contract is
        # asserted on the primitive itself, matching `drop_dominant_field_outcomes`.
        rows = _rungs(NETFLIX)
        kept = drop_incoherent_ladder_outcomes(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )
        assert kept and all(row in rows for row in kept)

    def test_it_drops_only_the_named_rung(self):
        rows = _rungs(NETFLIX)
        kept = drop_incoherent_ladder_outcomes(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )
        assert [row["name"] for row in kept] == [
            name for name, _ in NETFLIX if name != "Above 67"
        ]

    def test_an_empty_list_is_not_a_ladder(self):
        assert drop_incoherent_ladder_outcomes([], lambda r: None, lambda r: None) == []


def _scoring_outcomes(pairs):
    """The specimen as `routes/feed.py` hands it to the scorer."""
    movements = {"Above 67": 0.48, "Above 64": 0.145, "Above 61": 0.08, "Above 52": -0.035}
    openings = {"Above 67": 0.45, "Above 64": 0.64, "Above 61": 0.775, "Above 52": 0.95}
    ranked = sorted(
        [pair for pair in pairs if pair[1] is not None],
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [
        {
            "name": name,
            "probability": probability,
            "probability_change_24h": movements.get(name),
            "rank": position + 1,
            "rank_change_24h": 4 if name == "Above 67" else -1,
            "opening_probability": openings.get(name),
        }
        for position, (name, probability) in enumerate(ranked)
    ]


class TestTheCardCannotBeHeadlinedByAnImpossibleRung:
    @pytest.fixture
    def served(self):
        return compute_futures_highlight(
            market_name="Netflix App Downloads in September",
            market_tier=2,
            sport_category="economics",
            outcomes=_scoring_outcomes(NETFLIX),
        )

    @pytest.fixture
    def coherent(self):
        return compute_futures_highlight(
            market_name="Netflix App Downloads in September",
            market_tier=2,
            sport_category="economics",
            outcomes=_scoring_outcomes(NETFLIX_COHERENT),
        )

    def test_the_treatments_separate(self, served, coherent):
        # The control earns the leader change on the same names, movements and
        # ranks. If this ever fails, every assertion below is vacuous.
        assert "leader_change" in coherent.reasons
        assert coherent.primary_reason == "New favorite"

    def test_no_new_favorite(self, served):
        assert "leader_change" not in served.reasons
        assert served.primary_reason != "New favorite"

    def test_the_mover_is_the_real_one(self, served):
        assert served.top_mover_name == "Above 64"
        assert served.top_mover_change == pytest.approx(0.145)

    def test_the_surprise_is_not_the_impossible_rungs_49_points(self, served):
        assert "major_surprise" not in served.reasons

    def test_the_score_it_manufactured_is_gone(self, served, coherent):
        # 101 on production; the impossible rung was worth 20 of it.
        assert served.raw_score == 81.0
        assert coherent.raw_score > served.raw_score


class TestTheLadderIsNotDrawnWithAnImpossibleBar:
    def test_the_rung_is_not_a_row_the_reader_is_shown(self):
        card = classify_discover_card_archetype(
            name="Netflix App Downloads in September",
            category="economics",
            outcomes=[
                {"name": name, "probability": probability} for name, probability in NETFLIX
            ],
            outcome_count=len(NETFLIX),
        )
        labels = [point["label"] for point in card["threshold_points"]]
        assert "Above 67" not in labels
        assert "Above 58" in labels

    def test_the_rest_of_the_ladder_still_draws(self):
        card = classify_discover_card_archetype(
            name="Netflix App Downloads in September",
            category="economics",
            outcomes=[
                {"name": name, "probability": probability} for name, probability in NETFLIX
            ],
            outcome_count=len(NETFLIX),
        )
        assert card["suggested_format"] == "threshold_heatmap"
        assert len(card["threshold_points"]) == len(NETFLIX) - 1

    def test_a_coherent_ladder_keeps_all_of_its_rungs(self):
        card = classify_discover_card_archetype(
            name="Netflix App Downloads in September",
            category="economics",
            outcomes=[
                {"name": name, "probability": probability}
                for name, probability in NETFLIX_COHERENT
            ],
            outcome_count=len(NETFLIX_COHERENT),
        )
        assert len(card["threshold_points"]) == len(NETFLIX_COHERENT)


class TestBothSerializersFilter:
    """#4605's lesson: a rule that lands in one component is not landed.

    `routes/feed.py` builds the same futures card twice — once for Discover and
    once for the sports feed — and each copy owns its own outcome list. A source
    scan rather than a route test because the defect this guards is a THIRD copy
    appearing later with the filter missing, which no test of the two existing
    call paths would notice.
    """

    def test_every_rank_order_call_in_the_feed_is_followed_by_the_ladder_filter(self):
        source = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
        ).read_text()
        assert source.count("display_rank_order(") == source.count(
            "drop_incoherent_ladder_outcomes("
        ) == 2
