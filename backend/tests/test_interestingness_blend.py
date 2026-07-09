"""Tests for interestingness blend in Discover feed scoring.

Validates:
- High interestingness lifts medium highlight scores
- Low interestingness has minimal impact on high highlight scores
- Blend weight 0 = no change (kill switch)
- Missing Redis cache falls back to base score only
- Blend cap prevents interestingness from adding more than 15 points
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInterestingnessBlend:
    """Test the DISPLAY-chain interestingness blend logic in _score_futures.

    L2-79 / #143-follow-up: the display blend was the last home of the #142
    double-scale bug. The cached interestingness ``score`` is 0-100 (the scorer
    normalizes to 0-100; see market_interestingness.score and
    precompute_interestingness which caches ``result.score``), but the display
    chain multiplied it by 100 again (0-10000), so the +15 cap ALWAYS bound and
    every cache-hit card gained a constant +15 display bump. The mirror below
    replicates the CORRECTED math: a direct convex combination of two 0-100
    quantities, matching the ranking chain, with the +15 cap kept as a genuine
    (now rarely-binding) bound and the display clamp at 98 (matching the feed).
    """

    def _make_blend(
        self,
        base_score: float,
        interestingness_score: float,
        blend_weight: float = 0.2,
    ) -> float:
        """Replicate the FIXED display blend logic from _score_futures.

        ``interestingness_score`` is 0-100 (as stored in Redis by the precompute
        task: ``result.score`` from score_market_interestingness). NO ``* 100``.
        """
        if blend_weight <= 0:
            return base_score
        pre_blend = base_score
        blended = base_score * (1 - blend_weight) + interestingness_score * blend_weight
        result = min(blended, pre_blend + 15)
        return max(0, min(98, result))

    def test_high_interestingness_lifts_medium_score(self):
        """Market with high interestingness (80) and medium highlight (40) -> higher."""
        base = 40.0
        interestingness = 80.0  # 0-100 scale
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 40 * 0.8 + 80 * 0.2 = 32 + 16 = 48
        assert blended == pytest.approx(48.0)
        assert blended > base

    def test_low_interestingness_minimal_impact_on_high_score(self):
        """Market with low interestingness (10) and high highlight (80) -> minimal drop."""
        base = 80.0
        interestingness = 10.0  # 0-100 scale
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 80 * 0.8 + 10 * 0.2 = 64 + 2 = 66
        assert blended == pytest.approx(66.0)
        assert blended >= 60

    def test_realistic_score_does_not_saturate_cap(self):
        """Regression for the #142/#143 double-scale bug (L2-79).

        A realistic mid-range 0-100 cached score must NOT push every card to the
        +15 cap. With the old ``* 100`` the blend target was ~score*100
        (0-10000) so ``min(blended, pre_blend + 15)`` ALWAYS returned
        ``pre_blend + 15`` — a constant bump that saturated the feed at 98 and
        defeated the serving filters. The corrected blend barely moves a high
        base with a mid interestingness.
        """
        base = 70.0
        interestingness = 55.0
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 70 * 0.8 + 55 * 0.2 = 56 + 11 = 67 — a small move toward i, not +15.
        assert blended == pytest.approx(67.0)
        assert blended < base + 15  # the cap does NOT bind
        # And the old double-scaled formula would have hit the cap here:
        old_blended = base * 0.8 + (interestingness * 100) * 0.2
        assert min(old_blended, base + 15) == pytest.approx(base + 15)

    def test_low_signal_card_falls_below_serving_floor(self):
        """The <15 serving filter is honest again (L2-79 composition point).

        A floor sports base with near-zero interestingness blends below 15, so
        it is correctly dropped by the ``personalized_score < 15`` filter instead
        of being rescued by the old constant +15 bump (which pushed every
        cache-hit card to base+15, defeating the floor).
        """
        base = 17.0
        interestingness = 3.0  # small but nonzero — enough to trip the old bump
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 17 * 0.8 + 3 * 0.2 = 13.6 + 0.6 = 14.2  -> below the 15 floor
        assert blended == pytest.approx(14.2)
        assert blended < 15
        # Under the OLD bug this same card got base+15 = 32 and wrongly served:
        # 17 * 0.8 + (3 * 100) * 0.2 = 13.6 + 60 = 73.6 -> capped to 32.
        old_blended = min(base * 0.8 + (interestingness * 100) * 0.2, base + 15)
        assert old_blended == pytest.approx(base + 15)
        assert old_blended >= 15

    def test_blend_weight_zero_no_change(self):
        """Kill switch: weight=0 means no interestingness blend."""
        base = 50.0
        interestingness = 90.0
        blended = self._make_blend(base, interestingness, blend_weight=0.0)
        assert blended == base

    def test_blend_cap_prevents_excessive_boost(self):
        """Interestingness cannot add more than 15 points over base."""
        base = 30.0
        interestingness = 100.0  # max interestingness
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 30 * 0.8 + 100 * 0.2 = 24 + 20 = 44
        # But cap is base + 15 = 45, so 44 < 45, no cap applied
        assert blended == pytest.approx(44.0)

        # With a higher weight the cap kicks in
        blended_high_weight = self._make_blend(base, interestingness, blend_weight=0.5)
        # 30 * 0.5 + 100 * 0.5 = 15 + 50 = 65 -> capped to 30+15=45
        assert blended_high_weight == pytest.approx(45.0)

    def test_blend_does_not_exceed_98(self):
        """Blended display score should be clamped to [0, 98] (feed display cap)."""
        base = 95.0
        interestingness = 100.0
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 95 * 0.8 + 100 * 0.2 = 76 + 20 = 96 (cap 95+15=110 does not bind)
        assert blended == pytest.approx(96.0)
        assert blended <= 98

    def test_blend_does_not_go_below_zero(self):
        """Blended score should not go negative."""
        base = 5.0
        interestingness = 0.0
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        assert blended >= 0
        # 5 * 0.8 + 0 * 0.2 = 4
        assert blended == pytest.approx(4.0)

    def test_equal_scores_no_change(self):
        """When interestingness equals base, blend should be ~the same."""
        base = 50.0
        interestingness = 50.0
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        assert blended == pytest.approx(50.0)


class TestDisplayBlendNoDoubleScale:
    """Source-level regression guard: the feed's DISPLAY blend must not re-scale
    the already-0-100 cached interestingness score by 100 (the #142/#143 bug).

    A mirror helper can silently drift from the real inline blend in
    ``_score_futures``; this pins the actual source so the double-scale cannot
    creep back in.
    """

    def test_display_blend_source_has_no_times_100(self):
        import inspect

        import app.routes.feed as feed_mod

        src = inspect.getsource(feed_mod)
        # Strip comments so the guard checks CODE only (the fix comment itself
        # mentions the old ``i_score * 100`` form to explain the bug).
        code_only = "\n".join(
            line.split("#", 1)[0] for line in src.splitlines()
        )
        # The corrected display AND ranking blends both add ``i_score *
        # _interestingness_blend_weight`` with no ``* 100``. The buggy form was
        # ``(i_score * 100) * _interestingness_blend_weight``.
        assert "i_score * 100" not in code_only
        # Sanity: the corrected direct blend term is present.
        assert "i_score * _interestingness_blend_weight" in code_only


class TestInterestingnessRedisIntegration:
    """Test Redis cache loading for interestingness scores."""

    def test_cache_parse_valid_json(self):
        """Valid cached entry is parsed correctly."""
        raw = json.dumps({
            "score": 72.5,
            "reasons": ["fresh", "moving"],
            "computed_at": "2026-05-22T10:00:00+00:00",
        })
        parsed = json.loads(raw)
        assert parsed["score"] == 72.5
        assert "fresh" in parsed["reasons"]

    def test_cache_parse_empty_reasons(self):
        """Cache entry with no reasons works."""
        raw = json.dumps({
            "score": 30.0,
            "reasons": [],
            "computed_at": "2026-05-22T10:00:00+00:00",
        })
        parsed = json.loads(raw)
        assert parsed["score"] == 30.0
        assert parsed["reasons"] == []


class TestGetCachedInterestingness:
    """Test the _get_cached_interestingness helper."""

    def test_returns_none_when_redis_unavailable(self):
        """Graceful fallback when Redis is down."""
        from app.routes.feed import _get_cached_interestingness

        with patch("app.tasks.redis_state.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis down")
            result = _get_cached_interestingness(12345)
            assert result is None

    def test_returns_parsed_entry_when_cached(self):
        """Returns parsed dict when cache hit."""
        from app.routes.feed import _get_cached_interestingness

        cache_data = json.dumps({
            "score": 65.3,
            "reasons": ["multi_source", "resolving_soon"],
            "computed_at": "2026-05-22T10:00:00+00:00",
        })
        mock_r = MagicMock()
        mock_r.get.return_value = cache_data.encode()

        with patch("app.tasks.redis_state.get_redis_client", return_value=mock_r):
            result = _get_cached_interestingness(42)
            assert result is not None
            assert result["score"] == 65.3
            assert "multi_source" in result["reasons"]

    def test_returns_none_when_not_cached(self):
        """Returns None on cache miss."""
        from app.routes.feed import _get_cached_interestingness

        mock_r = MagicMock()
        mock_r.get.return_value = None

        with patch("app.tasks.redis_state.get_redis_client", return_value=mock_r):
            result = _get_cached_interestingness(99999)
            assert result is None


class TestPrecomputeInterestingnessImport:
    """Verify the precompute task module imports cleanly."""

    def test_import_task_module(self):
        from app.tasks.precompute_interestingness import _precompute_interestingness
        assert callable(_precompute_interestingness)

    def test_task_registered(self):
        from app.tasks import celery_app

        registered = set(celery_app.tasks.keys())
        assert "app.tasks.precompute_interestingness" in registered

    def test_beat_schedule_entry(self):
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "precompute-interestingness" in schedule
        entry = schedule["precompute-interestingness"]
        assert entry["task"] == "app.tasks.precompute_interestingness"
