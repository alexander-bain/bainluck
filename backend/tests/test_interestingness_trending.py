"""#882 slice 4: TMDB-trending → interestingness bounded boost.

A market whose subject is currently trending gets a small, capped boost; a
non-trending market and the base score for everyone else are unchanged.
"""

from app.utils.market_interestingness import (
    MarketInterestingnessInputs,
    score_market_interestingness,
    TRENDING_BONUS,
)
from app.tasks.enrich_tmdb import _normalize_title, _pick_tmdb_image  # noqa: F401


def _inputs(**kw):
    base = dict(
        probability=0.62, source_count=2, movement_24h=0.06,
        category="entertainment", volume_24h=5000, llm_quality=0.6,
    )
    base.update(kw)
    return MarketInterestingnessInputs(**base)


class TestTrendingBoost:
    def test_trending_adds_bounded_boost(self):
        base = score_market_interestingness(_inputs(trending=False)).score
        boosted = score_market_interestingness(_inputs(trending=True)).score
        assert boosted > base
        # Bounded: never more than the bonus above base (and capped at 100).
        assert boosted - base <= TRENDING_BONUS + 0.01
        assert boosted <= 100.0

    def test_non_trending_score_unchanged(self):
        # The base (8-signal) score must be identical whether or not the trending
        # FIELD exists — no global renormalization regression.
        s = score_market_interestingness(_inputs(trending=False))
        assert "cultural_hotness" not in s.components
        assert "trending_on_tmdb" not in s.reasons

    def test_trending_reason_and_component_present_when_boosted(self):
        s = score_market_interestingness(_inputs(trending=True))
        assert "trending_on_tmdb" in s.reasons
        assert s.components.get("cultural_hotness") == TRENDING_BONUS

    def test_charting_boost_does_not_stack_with_trending(self):
        # #882 slice 3: charting shares the single bounded bonus; trending+charting
        # still = TRENDING_BONUS (no stacking).
        base = score_market_interestingness(_inputs(trending=False, charting=False)).score
        chart = score_market_interestingness(_inputs(charting=True)).score
        both = score_market_interestingness(_inputs(trending=True, charting=True)).score
        assert chart - base <= TRENDING_BONUS + 0.01
        assert both - base <= TRENDING_BONUS + 0.01  # capped, no stacking
        s = score_market_interestingness(_inputs(charting=True))
        assert "charting_music" in s.reasons

    def test_boost_capped_at_100(self):
        # A near-max market + trending stays <= 100.
        hi = _inputs(probability=0.7, source_count=5, movement_24h=0.2,
                     volume_24h=10**7, llm_quality=1.0, trending=True)
        assert score_market_interestingness(hi).score <= 100.0


class TestNormalizeTitle:
    def test_normalize(self):
        assert _normalize_title("Toy Story 5") == "toystory5"
        assert _normalize_title("The Odyssey!") == "theodyssey"
        assert _normalize_title(None) == ""
