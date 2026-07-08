"""Tests for the de-saturated Discover ordering score (#141 / RANK-1).

Pins:
- Uncapped ranking helpers (quality_score_rank, explanation_score_rank) omit the
  flat display ceilings for ORDERING while keeping additive tiering + weak-hook
  penalties.
- `_rank_key` sorts by the uncapped `_rank_score` when present, falling back to
  the capped display `score`.
- Event demotion keeps `_rank_score` in lockstep with `score`.
"""

from app.routes.feed import _rank_key, _demote_non_exceptional_discover_events
from app.utils.feed_market_quality import (
    apply_explanation_quality_score,
    apply_quality_score,
    classify_market_quality,
    explanation_score_rank,
    quality_score_rank,
)


def _quality(name: str, category: str):
    return classify_market_quality(
        market_name=name,
        sport_category=category,
        outcome_names=["Yes", "No"],
    )


class TestUncappedRankingHelpers:
    def test_quality_rank_omits_display_ceiling(self):
        """A high raw score keeps its magnitude for ordering, not clamped to 95."""
        q = _quality("Will China invade Taiwan in 2026?", "geopolitics")
        display = apply_quality_score(130, q)
        rank = quality_score_rank(130, q)
        # Display is ceilinged; ranking preserves the uncapped magnitude.
        assert display <= 95
        assert rank > display
        assert rank >= 130  # additive adjustment is >= 0 for non-low_quality

    def test_quality_rank_preserves_tier_separation(self):
        """Low-quality still ranks below compelling via the additive penalty."""
        compelling = _quality("Will China invade Taiwan in 2026?", "geopolitics")
        # A narrow numeric ladder bucket classifies low_quality.
        low = _quality("Will BTC close between 60000 and 60100 today?", "crypto")
        # Same raw input; ranking still separates the tiers.
        assert quality_score_rank(90, compelling) > quality_score_rank(90, low)

    def test_explanation_rank_strong_hook_uncapped(self):
        q = _quality("Will China invade Taiwan in 2026?", "geopolitics")
        strong = "China has massed troops near the strait and analysts now put the odds materially higher than last month."
        assert (
            explanation_score_rank(
                120, hook_description=strong, headline="x", quality=q
            )
            == 123
        )

    def test_explanation_rank_weak_hook_penalty_retained(self):
        """Weak-hook cards still get the per-class demotion ceiling for ordering."""
        q = _quality("Will China invade Taiwan in 2026?", "geopolitics")
        # compelling weak-hook ceiling is 93
        capped = explanation_score_rank(
            120, hook_description=None, headline="New favorite", quality=q
        )
        assert capped <= 93


class TestRankKey:
    def test_uses_rank_score_when_present(self):
        a = {"score": 98, "_rank_score": 130.0, "_sort_time": 1}
        b = {"score": 98, "_rank_score": 100.0, "_sort_time": 999}
        # Despite b being newer (higher _sort_time), a wins on rank score.
        assert _rank_key(a) > _rank_key(b)

    def test_falls_back_to_score(self):
        a = {"score": 91, "_sort_time": 1}
        b = {"score": 90, "_sort_time": 999}
        assert _rank_key(a) > _rank_key(b)

    def test_desaturates_recency_tiebreak(self):
        """Two cards tied at display 98 order by signal, not recency."""
        boring_new = {"score": 98, "_rank_score": 98.0, "_sort_time": 10_000}
        strong_old = {"score": 98, "_rank_score": 121.0, "_sort_time": 1}
        ordered = sorted([boring_new, strong_old], key=_rank_key, reverse=True)
        assert ordered[0] is strong_old


class TestDemotionLockstep:
    def test_demotion_caps_rank_score_too(self):
        items = [
            {
                "type": "event",
                "score": 96,
                "_rank_score": 140.0,
                "data": {"status": "live"},
            }
        ]
        _demote_non_exceptional_discover_events(items)
        # Non-exceptional event demoted to 35 on BOTH scores so it cannot
        # dominate futures under the de-saturated sort.
        assert items[0]["score"] == 35
        assert items[0]["_rank_score"] == 35.0
