"""Queue 283 Item 3 (#1487) — one visible probability basis per card, at the REAL
card-envelope functions.

C81 ``card-probability-authority/v1``: every visible field of one card (mini-list
``top_outcomes``, the ``discover_card.distribution_outcomes``, the headline/context
leader) must read from ONE post-normalization display basis, so a single outcome
never renders at two probabilities. These tests compose the exact production
functions ``_score_futures`` wires together (``_strip_mixed_binary_meta`` ->
``_feed_display_scale`` -> ``_normalize_feed_probabilities`` /
``_scale_display_probability`` -> ``classify_discover_card_archetype``) and assert
agreement across all surfaces — covering the CPI / NASCAR / AIG / Netanyahu
equivalents and the ordinary-binary + equal-rounded-label cases.
"""

from app.routes.feed import (
    _feed_display_scale,
    _normalize_feed_probabilities,
    _scale_display_probability,
    _strip_mixed_binary_meta,
)
from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.feed_reasons import humanize_outcome_names_for_feed


class _O:
    """Minimal FuturesOutcome stand-in (only the fields the envelope reads)."""

    def __init__(self, oid, name, prob, rank=1, change=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.rank = rank
        self.probability_change_24h = change


def _build_card(outcomes, market_name="Test Market"):
    """Reproduce the real _score_futures visible-probability composition and
    return (top_outcomes, distribution_outcomes, display_leader_prob)."""
    sorted_outcomes = sorted(
        outcomes,
        key=lambda o: float(o.current_probability) if o.current_probability else 0,
        reverse=True,
    )
    card_outcomes = _strip_mixed_binary_meta(sorted_outcomes)
    display_scale = _feed_display_scale(card_outcomes)
    leader_prob = (
        float(card_outcomes[0].current_probability)
        if card_outcomes and card_outcomes[0].current_probability
        else None
    )
    display_leader_prob = _scale_display_probability(leader_prob, display_scale)

    top = [
        {
            "id": o.id,
            "name": o.name,
            "probability": (
                float(o.current_probability) if o.current_probability else None
            ),
            "rank": o.rank,
            "movement": None,
        }
        for o in card_outcomes[:3]
    ]
    top = humanize_outcome_names_for_feed(top, market_name)
    top = _normalize_feed_probabilities(top, card_outcomes)

    all_outcomes_for_card = [
        {
            "name": o.name,
            "probability": _scale_display_probability(
                float(o.current_probability)
                if o.current_probability is not None
                else None,
                display_scale,
            ),
            "movement": None,
        }
        for o in card_outcomes
    ]
    discover_card = classify_discover_card_archetype(
        name=market_name,
        outcomes=all_outcomes_for_card,
        outcome_count=len(card_outcomes),
    )
    return top, discover_card["distribution_outcomes"], display_leader_prob


def _pct(p):
    return round(float(p) * 100)


def _assert_one_basis(top, distribution, display_leader):
    """The leading outcome reads the SAME probability across all three surfaces."""
    top_leader = top[0]["probability"]
    dist_leader = distribution[0]["probability"]
    assert _pct(top_leader) == _pct(dist_leader) == _pct(display_leader)
    # And every outcome present in both arrays agrees by name.
    dist_by_label = {d["label"]: d["probability"] for d in distribution}
    for row in top:
        if row["name"] in dist_by_label and row["probability"] is not None:
            assert _pct(row["probability"]) == _pct(dist_by_label[row["name"]])


def test_independent_binary_cpi_equivalent_single_basis():
    # Two independent-binary outcomes summing to 1.59 -> normalized basis.
    top, dist, leader = _build_card(
        [_O(1, "Exactly -0.2%", 0.88), _O(2, "Other", 0.71)]
    )
    _assert_one_basis(top, dist, leader)
    # Normalized, not raw: 0.88 / 1.59 ~= 0.553.
    assert _pct(leader) == 55


def test_multi_outcome_aig_equivalent_single_basis():
    # An independent-binary field (AIG "three numbers" bug) summing >100%.
    outcomes = [
        _O(1, "Nelly Korda", 0.14),
        _O(2, "B", 0.13),
        _O(3, "C", 0.12),
        _O(4, "D", 0.11),
        _O(5, "E", 0.10),
    ]
    top, dist, leader = _build_card(outcomes)
    _assert_one_basis(top, dist, leader)


def test_ordinary_binary_stays_raw_and_agrees():
    # Mutually-exclusive pair summing <=1.01 -> raw basis, all surfaces raw.
    top, dist, leader = _build_card([_O(1, "A", 0.47), _O(2, "B", 0.32)])
    _assert_one_basis(top, dist, leader)
    assert _pct(leader) == 47


def test_threshold_ladder_not_normalized():
    # Cumulative/threshold outcomes (sum >> 2.0) keep raw meaningful values.
    outcomes = [
        _O(1, "Rank 1+", 0.98),
        _O(2, "Rank 2+", 0.81),
        _O(3, "Rank 3+", 0.60),
        _O(4, "Rank 4+", 0.40),
    ]
    top, dist, leader = _build_card(outcomes)
    _assert_one_basis(top, dist, leader)
    # An 81%/98% ladder leader is NOT flattened to ~33%.
    assert _pct(leader) == 98


def test_equal_rounded_labels_produce_equal_display_probability():
    # 0.184 vs 0.176 both round to 18% -> both surfaces must carry equal values
    # (equal label => equal bar, since bars derive from the same number).
    top, dist, leader = _build_card([_O(1, "A", 0.184), _O(2, "B", 0.176)])
    _assert_one_basis(top, dist, leader)
    dist_by_label = {d["label"]: d["probability"] for d in dist}
    assert _pct(dist_by_label["A"]) == _pct(dist_by_label["B"]) == 18


def test_display_scale_matches_normalize_decision():
    # The scale helper and the historical normalize path must agree exactly so
    # top_outcomes and the distribution cannot drift.
    outcomes = [_O(1, "A", 0.88), _O(2, "B", 0.71)]
    scale = _feed_display_scale(outcomes)
    top = _normalize_feed_probabilities(
        [{"name": "A", "probability": 0.88}, {"name": "B", "probability": 0.71}],
        outcomes,
    )
    assert round(0.88 / scale, 4) == top[0]["probability"]
