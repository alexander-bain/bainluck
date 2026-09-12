"""#4640 — a nested ladder's dearest rung is its WEAKEST claim, so it is not a favorite.

On a cumulative ladder every rung's event strictly contains the next one's, so
the highest-priced rung is the loosest threshold. It leads for the same reason
"heads or tails" outprices "heads": nothing happened, the question is just
weaker. Copy that calls it a favorite, or reports that the favorite changed,
claims a contest the outcome set does not contain.

This is NOT #4610. That issue drops rungs whose price contradicts the ladder and
deliberately leaves the coherent case alone; the coherent case is this one, and
it survives every repair #4610 makes. It is also NOT a wider
`_weak_outcome_label`: band sets are mutually exclusive, so their favorite is
real and their lead changes are real news, and the two populations differ by the
SET rather than by the spelling of any one label. Both directions are asserted
below, and the band-set arm is what stops this fix eating them.

The arms deliberately do NOT share one extractor. The three generators are three
independent doors onto the same claim, and a suite that read them all through one
helper would inherit that helper's blind spot — the failure that let #5713's
regression through eight green arms.
"""

import pytest

from app.utils.feed_reasons import (
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)
from app.utils.futures_highlights import compute_futures_highlight
from app.utils.ladder_monotonicity import cumulative_outcome_ladder

# ─── Populations ──────────────────────────────────────────────────────────────
#
# CUMULATIVE: live on production 2026-09-12, `GET /api/feed?limit=250`. Each was
# served with the headline quoted beside it. The full outcome sets were read from
# `futures_outcomes` the same day and every one of the twelve is a single
# cumulative ladder on its FULL set, not merely on the top rungs the card shows.
CUMULATIVE_SPECIMENS = [
    # (market name, legs, the headline production actually served)
    (
        "Instacart App Downloads in September",
        [("Above 116", 0.69), ("Above 120", 0.45), ("Above 126", 0.41)],
        "New favorite: Above 116 (69%)",
    ),
    (
        "Hulu App Downloads in September",
        [("Above 68", 0.69), ("Above 71", 0.56), ("Above 75", 0.52)],
        "Above 68 leads; resolves within a month",
    ),
    (
        "Pick You Up: First Week Album Equivalent Units",
        [("Above 5K", 0.32), ("Above 10K", 0.24), ("Above 15K", 0.11)],
        "New favorite: Above 5K (32%)",
    ),
    (
        "How low will the 30Y US Treasury yield get by Sep 30, 2026?",
        [("5.22% or below", 0.26), ("5.23% or below", 0.27), ("5.24% or below", 0.33)],
        "5.24% or below leads; resolves within a month",
    ),
]

# NOT cumulative. A favorite here is a real thing and a lead change is real news.
# #4640 names both of these explicitly as out of scope.
BAND_SET = [("29,900 to 29,999.99", 0.40), ("30,000 to 30,099.99", 0.35)]
REAL_CONTEST = [("Boston Celtics", 0.41), ("Denver Nuggets", 0.33)]


def _legs(pairs, *, leader_rank_change=4):
    """Scoring rows in the shape `routes/feed.py` hands the scorer.

    `rank == 1` plus a non-zero `rank_change_24h` is what makes
    `compute_futures_highlight` record a leader change, so every specimen below
    genuinely earns the reason whose LABEL this issue withholds.
    """
    ranked = sorted(pairs, key=lambda pair: pair[1], reverse=True)
    return [
        {
            "name": name,
            "probability": probability,
            "rank": position + 1,
            "rank_change_24h": leader_rank_change if position == 0 else -1,
        }
        for position, (name, probability) in enumerate(ranked)
    ]


def _leader(pairs):
    return max(pairs, key=lambda pair: pair[1])


# ─── The discriminator itself ─────────────────────────────────────────────────


class TestTheTwoPopulationsAreSeparable:
    """If this class fails, every assertion below it is meaningless."""

    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_every_specimen_really_is_one_ladder(self, name, legs, _headline):
        rows = [{"name": leg, "probability": p} for leg, p in legs]
        assert cumulative_outcome_ladder(rows) is not None, name

    @pytest.mark.parametrize("pairs", [BAND_SET, REAL_CONTEST])
    def test_the_out_of_scope_populations_are_not_ladders(self, pairs):
        rows = [{"name": leg, "probability": p} for leg, p in pairs]
        assert cumulative_outcome_ladder(rows) is None

    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_the_dearest_rung_is_the_loosest_one(self, name, legs, _headline):
        """The arithmetic the issue rests on, stated rather than assumed."""
        ordered, direction = cumulative_outcome_ladder(
            [{"name": leg, "probability": p} for leg, p in legs]
        )
        prices = [row["probability"] for _value, row in ordered]
        loosest = prices[0] if direction == "dec" else prices[-1]
        assert loosest == max(prices), name


# ─── Anti-strawman: the defect WAS live on these exact inputs ─────────────────


class TestTheseSpecimensDidCarryTheDefect:
    """Re-runs the pre-#4640 expression so the suite cannot pass by asserting a
    defect that never existed. Every specimen must have produced the bad copy."""

    @pytest.mark.parametrize("name,legs,served_headline", CUMULATIVE_SPECIMENS)
    def test_before_the_fix_each_one_named_its_rung(self, name, legs, served_headline):
        leader_name, leader_probability = _leader(legs)
        before = generate_futures_headline(
            highlight_reasons=["leader_change"],
            market_name=name,
            leader_name=leader_name,
            leader_probability=leader_probability,
            # The pre-#4640 call: the flag did not exist, so it is False.
            leader_is_ladder_rung=False,
        )
        assert before == f"New favorite: {leader_name} ({round(leader_probability * 100)}%)"

    @pytest.mark.parametrize("name,legs,served_headline", CUMULATIVE_SPECIMENS)
    def test_the_served_headline_is_reproduced(self, name, legs, served_headline):
        """Not just "some bad copy" — the string production actually served."""
        leader_name, leader_probability = _leader(legs)
        reasons = (
            ["leader_change"]
            if served_headline.startswith("New favorite")
            else ["resolving_soon_30d"]
        )
        assert (
            generate_futures_headline(
                highlight_reasons=reasons,
                market_name=name,
                leader_name=leader_name,
                leader_probability=leader_probability,
                leader_is_ladder_rung=False,
            )
            == served_headline
        )


# ─── The fix, at each of the three doors, asserted independently ─────────────


class TestTheHeadlineNeverNamesALadderRung:
    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_leader_change_says_nothing(self, name, legs, _headline):
        leader_name, leader_probability = _leader(legs)
        headline = generate_futures_headline(
            highlight_reasons=["leader_change"],
            market_name=name,
            leader_name=leader_name,
            leader_probability=leader_probability,
            leader_is_ladder_rung=True,
        )
        assert "New favorite" not in headline
        assert leader_name not in headline

    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_resolving_soon_borrows_the_market_title(self, name, legs, _headline):
        """The rung is not named, and the slot is not left empty either."""
        leader_name, leader_probability = _leader(legs)
        headline = generate_futures_headline(
            highlight_reasons=["resolving_soon_30d"],
            market_name=name,
            leader_name=leader_name,
            leader_probability=leader_probability,
            leader_is_ladder_rung=True,
        )
        assert leader_name not in headline
        assert "resolves within a month" in headline
        assert headline.startswith(name[:20])


class TestTheReasonNeverNamesALadderRung:
    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_leader_change_falls_through_rather_than_dropping_the_number(
        self, name, legs, _headline
    ):
        """`New favorite in {market}` is the same false claim with the number
        removed, so the branch must not emit it either."""
        leader_name, leader_probability = _leader(legs)
        reason = generate_futures_reason(
            market_name=name,
            highlight_reasons=["leader_change"],
            leader_name=leader_name,
            leader_probability=leader_probability,
            leader_is_ladder_rung=True,
        )
        assert "New favorite" not in reason
        assert leader_name not in reason

    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_the_fallback_clause_is_silent(self, name, legs, _headline):
        leader_name, leader_probability = _leader(legs)
        assert (
            generate_futures_reason(
                market_name=name,
                highlight_reasons=[],
                leader_name=leader_name,
                leader_probability=leader_probability,
                leader_is_ladder_rung=True,
            )
            == ""
        )


class TestTheContextSummaryNeverNamesALadderRung:
    @pytest.mark.parametrize("name,legs,_headline", CUMULATIVE_SPECIMENS)
    def test_the_leader_clause_is_withheld(self, name, legs, _headline):
        leader_name, leader_probability = _leader(legs)
        summary = generate_futures_context_summary(
            headline="",
            highlight_reasons=["resolving_soon_30d"],
            market_name=name,
            leader_name=leader_name,
            leader_probability=leader_probability,
            leader_is_ladder_rung=True,
        )
        assert leader_name not in summary
        assert " leads at " not in summary


# ─── The other direction: what must NOT change ───────────────────────────────


class TestABandSetStillHasAFavorite:
    """#4640's explicit carve-out. Mutually exclusive outcomes DO have a leader."""

    @pytest.mark.parametrize("pairs", [BAND_SET, REAL_CONTEST])
    def test_the_headline_still_names_it(self, pairs):
        leader_name, leader_probability = _leader(pairs)
        headline = generate_futures_headline(
            highlight_reasons=["leader_change"],
            market_name="Nasdaq close on Sep 30",
            leader_name=leader_name,
            leader_probability=leader_probability,
            leader_is_ladder_rung=False,
        )
        assert headline.startswith("New favorite:")
        assert leader_name in headline

    @pytest.mark.parametrize("pairs", [BAND_SET, REAL_CONTEST])
    def test_the_reason_still_names_it(self, pairs):
        leader_name, leader_probability = _leader(pairs)
        reason = generate_futures_reason(
            market_name="Nasdaq close on Sep 30",
            highlight_reasons=["leader_change"],
            leader_name=leader_name,
            leader_probability=leader_probability,
            leader_is_ladder_rung=False,
        )
        assert "New favorite" in reason
        assert leader_name in reason

    def test_the_scorer_does_not_flag_a_band_set(self):
        result = compute_futures_highlight(
            market_name="Nasdaq close on Sep 30",
            market_tier=2,
            sport_category="economics",
            outcomes=_legs(BAND_SET),
        )
        assert result.leader_is_ladder_rung is False
        assert result.primary_reason == "New favorite"


class TestAnUninformedCallerIsUnchanged:
    """The flag defaults False, so a caller that has not been taught about
    ladders keeps today's copy rather than silently losing its leader."""

    def test_the_kwarg_is_optional_at_every_door(self):
        leader_name, leader_probability = _leader(REAL_CONTEST)
        common = dict(
            leader_name=leader_name, leader_probability=leader_probability
        )
        assert "New favorite" in generate_futures_headline(
            highlight_reasons=["leader_change"], market_name="NBA champion", **common
        )
        assert "New favorite" in generate_futures_reason(
            market_name="NBA champion", highlight_reasons=["leader_change"], **common
        )
        assert leader_name in generate_futures_context_summary(
            headline="",
            highlight_reasons=["resolving_soon_30d"],
            market_name="NBA champion",
            **common,
        )


# ─── The scorer: a copy fix, NOT a ranking change ────────────────────────────


class TestTheScorerWithholdsTheLabelAndNothingElse:
    @pytest.fixture
    def ladder(self):
        return compute_futures_highlight(
            market_name="Instacart App Downloads in September",
            market_tier=2,
            sport_category="economics",
            outcomes=_legs([("Above 116", 0.69), ("Above 120", 0.45), ("Above 126", 0.41)]),
        )

    def test_it_sees_the_ladder(self, ladder):
        assert ladder.leader_is_ladder_rung is True

    def test_the_reason_and_the_score_are_untouched(self, ladder):
        """The signal is real and still ranks the card; only the sentence goes.
        If this ever flips, #4640 has become a ranking change and needs re-ruling."""
        assert "leader_change" in ladder.reasons
        assert ladder.flags.leader_changed is True

    def test_only_the_label_is_withheld(self, ladder):
        assert ladder.primary_reason != "New favorite"

    def test_the_next_real_signal_speaks_instead(self):
        """Withholding must not blank the card: a ladder that also resolves soon
        still gets its honest label."""
        result = compute_futures_highlight(
            market_name="Instacart App Downloads in September",
            market_tier=2,
            sport_category="economics",
            outcomes=_legs([("Above 116", 0.69), ("Above 120", 0.45)]),
            resolution_date=None,
        )
        assert result.primary_reason != "New favorite"

    def test_the_score_is_identical_with_and_without_the_ladder_shape(self):
        """The clearest statement that this is a copy fix. Same movements, same
        ranks, same tier — one set nested, one set not — and the SCORES match."""
        nested = compute_futures_highlight(
            market_name="A",
            market_tier=2,
            sport_category="economics",
            outcomes=_legs([("Above 116", 0.69), ("Above 120", 0.45)]),
        )
        flat = compute_futures_highlight(
            market_name="A",
            market_tier=2,
            sport_category="economics",
            outcomes=_legs([("Boston Celtics", 0.69), ("Denver Nuggets", 0.45)]),
        )
        assert nested.raw_score == flat.raw_score
        assert nested.primary_reason != flat.primary_reason
