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

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.personalization import PersonalizationContext

from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.futures_highlights import compute_futures_highlight
from app.utils.outcome_display import (
    drop_incoherent_ladder_outcomes,
    incoherent_ladder_indexes,
    ladder_treatment_collapsed,
)


# ── the real-serializer harness (CERT-2451) ──────────────────────────────────
#
# Same shape as `test_feed_phantom_midpoint_suppression.py`: real objects rather
# than MagicMocks, because the route reads `market.__dict__` and `o.name`, and a
# frozen clock with no branch on it (gotcha #44 — offset first, never `if`).

_FROZEN_NOW = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)


class _Outcome:
    def __init__(self, id, name, prob):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = prob
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = None
        self.current_yes_ask = None


class _Market:
    def __init__(self, id, name, outcomes, *, group_id=None):
        self.id = id
        self.name = name
        self.source = "kalshi"
        self.external_id = f"kalshi-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "economics"
        self.llm_sport_category = "economics"
        self.market_tier = 1
        self.canonical_market_key = None
        self.group_id = group_id
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250_000
        self.updated_at = _FROZEN_NOW
        self.commence_time = _FROZEN_NOW - timedelta(days=1)
        self.resolution_date = _FROZEN_NOW + timedelta(days=120)
        self.status = "open"
        self.created_at = _FROZEN_NOW - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _ladder_market(market_id, name, pairs, *, group_id=None):
    return _Market(
        market_id,
        name,
        [
            _Outcome(market_id * 10 + n, label, probability)
            for n, (label, probability) in enumerate(pairs)
        ],
        group_id=group_id,
    )


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        result.scalars.return_value = scalars
        result.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve_one_futures_card(market):
    """Run the REAL `_score_futures` over one market and return its card data."""
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db([market]), _FROZEN_NOW, None, PersonalizationContext()
        )
    for item in items:
        if item["type"] == "futures" and item["data"]["id"] == market.id:
            return item["data"]
    return None


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

    def test_a_wholly_incoherent_ladder_is_left_alone_rather_than_arbitrated(self):
        # CERT-2451. Every rung of `.20 / .55 / .70` contradicts every other, so
        # "which one is wrong" has no answer and the survivor would be whichever
        # the tie-break reached. Same argument as `_LADDER_MIN_PRICED_RUNGS`, one
        # step out: refuse to attribute, keep the field, and let the caller
        # refuse the ladder TREATMENT instead.
        rows = _rungs([("Above 10", 0.20), ("Above 20", 0.55), ("Above 30", 0.70)])
        kept = drop_incoherent_ladder_outcomes(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )
        assert [row["name"] for row in kept] == ["Above 10", "Above 20", "Above 30"]
        assert ladder_treatment_collapsed(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )

    def test_the_collapse_question_is_false_for_a_ladder_with_one_bad_rung(self):
        # The boundary from the other side: the Netflix specimen loses one rung
        # and keeps six, so nothing about its treatment changes.
        rows = _rungs(NETFLIX)
        assert not ladder_treatment_collapsed(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )

    def test_the_collapse_question_is_false_for_a_coherent_ladder(self):
        rows = _rungs(NETFLIX_COHERENT)
        assert not ladder_treatment_collapsed(
            rows, lambda r: r["name"], lambda r: r["probability"]
        )


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

    def test_a_ladder_filtered_to_one_rung_is_not_handed_on_as_a_ladder(self):
        # UX-P008 from a new direction: a single surviving rung still classifies
        # as `threshold_heatmap` when the market carries a group key, the
        # frontend needs two rows to draw one, and the card falls through to the
        # plain leader — the whole field disappears. Refuse the treatment.
        card = classify_discover_card_archetype(
            name="Thin ladder",
            category="economics",
            outcomes=[
                {"name": "Above 10", "probability": 0.20},
                {"name": "Above 20", "probability": 0.90},
                {"name": "Above 30", "probability": 0.95},
            ],
            outcome_count=3,
            group_id="kalshi:thin",
        )
        assert card["threshold_points"] == []
        assert card["suggested_format"] != "threshold_heatmap"

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

    def test_every_filter_call_is_preceded_by_the_collapse_question(self):
        # CERT-2451. The drop and the question are a PAIR: the answer is only
        # obtainable before the drop, so a third serializer that copies the drop
        # and not the question ships the exact defect the repair below fixes.
        source = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
        ).read_text()
        assert source.count("ladder_treatment_collapsed(") == source.count(
            "drop_incoherent_ladder_outcomes("
        ) == 2
        assert source.count("ladder_treatment_refused=ladder_refused") == 2


class TestTheRefusalSurvivesFeedComposition:
    """CERT-2451 — the repair, and the reason a unit test could not see it.

    `TestTheLadderIsNotDrawnWithAnImpossibleBar` hands the classifier the RAW
    ladder, so the classifier finds the contradiction itself and refuses. The
    real feed never does that: `_score_futures` filters `sorted_outcomes` first
    and hands on the survivors, which are coherent by construction. On the
    grader's specimen — `Above 10` .20 / `Above 20` .90 / `Above 30` .95 — the
    survivor is `Above 10` ALONE, the classifier sees a one-rung ladder with a
    group key, re-emits `threshold_heatmap`, and the frontend (which needs two
    rows) falls through past the distribution branch to a plain leader card.
    The field disappears — the UX-P008 failure, arriving through the very fix
    that was meant to prevent it.

    So these drive the REAL serializer end to end.
    """

    @pytest.mark.asyncio
    async def test_real_feed_serializer_refuses_one_survivor_heatmap(self):
        card = await _serve_one_futures_card(
            _ladder_market(
                90001,
                "Thin ladder above ten",
                [("Above 10", 0.20), ("Above 20", 0.55), ("Above 30", 0.70)],
                group_id="kalshi:thin",
            )
        )
        assert card is not None, "the market did not survive scoring at all"
        assert card["discover_card"]["threshold_points"] == []
        assert card["discover_card"]["suggested_format"] != "threshold_heatmap"

    @pytest.mark.asyncio
    async def test_the_field_is_not_what_gets_refused(self):
        # "Refuse the treatment, not the field" — with four outcomes the card
        # falls to the distribution the field deserves, and every surviving rung
        # is still in the payload the reader's card is built from.
        card = await _serve_one_futures_card(
            _ladder_market(
                90002,
                "Thin ladder with a field behind it",
                [
                    ("Above 10", 0.15),
                    ("Above 20", 0.70),
                    ("Above 30", 0.75),
                    ("Above 40", 0.80),
                ],
                group_id="kalshi:thin4",
            )
        )
        assert card is not None
        assert card["discover_card"]["suggested_format"] == "outcome_distribution"
        assert len(card["discover_card"]["distribution_outcomes"]) == 4

    def test_the_seam_itself_carries_the_refusal(self):
        # The end-to-end test above passes for TWO reasons now — the serializer
        # no longer arbitrates a collapsed ladder, so the classifier sees the
        # contradiction itself — and a reason that cannot fail is not a guard.
        # This drives the seam directly: the classifier is handed exactly what a
        # filtering caller would hand it (the lone survivor, which is coherent by
        # construction) and the flag is the only thing that differs.
        survivor = [{"name": "Above 10", "probability": 0.20}]
        refused = classify_discover_card_archetype(
            name="Thin ladder above ten",
            category="economics",
            outcomes=survivor,
            outcome_count=1,
            group_id="kalshi:thin",
            ladder_treatment_refused=True,
        )
        assert refused["threshold_points"] == []
        assert refused["suggested_format"] != "threshold_heatmap"

        # …and WITHOUT the flag the same inputs reproduce the defect CERT-2451
        # named, which is what makes the flag load-bearing rather than decorative.
        unguarded = classify_discover_card_archetype(
            name="Thin ladder above ten",
            category="economics",
            outcomes=survivor,
            outcome_count=1,
            group_id="kalshi:thin",
        )
        assert unguarded["suggested_format"] == "threshold_heatmap"
        assert len(unguarded["threshold_points"]) == 1

    @pytest.mark.asyncio
    async def test_CONTROL_a_coherent_ladder_still_gets_its_heatmap(self):
        # The test that can fail if the repair over-refuses: nothing about a
        # ladder that never contradicted itself may change.
        card = await _serve_one_futures_card(
            _ladder_market(
                90003,
                "Honest ladder above ten",
                [("Above 10", 0.75), ("Above 20", 0.45), ("Above 30", 0.15)],
                group_id="kalshi:honest",
            )
        )
        assert card is not None
        assert card["discover_card"]["suggested_format"] == "threshold_heatmap"
        assert len(card["discover_card"]["threshold_points"]) == 3

    @pytest.mark.asyncio
    async def test_CONTROL_a_ladder_with_two_survivors_keeps_the_treatment(self):
        # The boundary the refusal is drawn at, from the permissive side: two
        # rungs is a ladder the frontend can draw, so the impossible rung is
        # dropped and the treatment stays.
        card = await _serve_one_futures_card(
            _ladder_market(
                90004,
                "Ladder with one bad rung",
                [("Above 10", 0.75), ("Above 20", 0.45), ("Above 30", 0.80)],
                group_id="kalshi:onebad",
            )
        )
        assert card is not None
        assert card["discover_card"]["suggested_format"] == "threshold_heatmap"
        labels = [p["label"] for p in card["discover_card"]["threshold_points"]]
        assert labels == ["Above 10", "Above 20"]
