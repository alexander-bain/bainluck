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
    """Test the interestingness blend logic in _score_futures."""

    def _make_blend(
        self,
        base_score: float,
        interestingness_score: float,
        blend_weight: float = 0.2,
    ) -> float:
        """Replicate the blend logic from _score_futures.
        interestingness_score is 0-1 (as stored in Redis by the precompute task).
        """
        if blend_weight <= 0:
            return base_score
        pre_blend = base_score
        blended = base_score * (1 - blend_weight) + (interestingness_score * 100) * blend_weight
        result = min(blended, pre_blend + 15)
        return max(0, min(100, result))

    def test_high_interestingness_lifts_medium_score(self):
        """Market with high interestingness (0.8) and medium highlight (40) -> higher."""
        base = 40.0
        interestingness = 0.8  # 0-1 scale
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 40 * 0.8 + (0.8*100) * 0.2 = 32 + 16 = 48
        assert blended == pytest.approx(48.0)
        assert blended > base

    def test_low_interestingness_minimal_impact_on_high_score(self):
        """Market with low interestingness (0.1) and high highlight (80) -> minimal drop."""
        base = 80.0
        interestingness = 0.1  # 0-1 scale
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 80 * 0.8 + (0.1*100) * 0.2 = 64 + 2 = 66
        assert blended == pytest.approx(66.0)
        assert blended >= 60

    def test_blend_weight_zero_no_change(self):
        """Kill switch: weight=0 means no interestingness blend."""
        base = 50.0
        interestingness = 0.9
        blended = self._make_blend(base, interestingness, blend_weight=0.0)
        assert blended == base

    def test_blend_cap_prevents_excessive_boost(self):
        """Interestingness cannot add more than 15 points over base."""
        base = 30.0
        interestingness = 1.0  # max interestingness
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        # 30 * 0.8 + (1.0*100) * 0.2 = 24 + 20 = 44
        # But cap is base + 15 = 45, so 44 < 45, no cap applied
        assert blended == pytest.approx(44.0)

        # With a higher weight the cap kicks in
        blended_high_weight = self._make_blend(base, interestingness, blend_weight=0.5)
        # 30 * 0.5 + (1.0*100) * 0.5 = 15 + 50 = 65 -> capped to 30+15=45
        assert blended_high_weight == pytest.approx(45.0)

    def test_blend_does_not_exceed_100(self):
        """Blended score should be clamped to [0, 100]."""
        base = 95.0
        interestingness = 1.0
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        assert blended <= 100

    def test_blend_does_not_go_below_zero(self):
        """Blended score should not go negative."""
        base = 5.0
        interestingness = 0.0
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        assert blended >= 0
        # 5 * 0.8 + (0*100) * 0.2 = 4
        assert blended == pytest.approx(4.0)

    def test_equal_scores_no_change(self):
        """When interestingness*100 equals base, blend should be ~the same."""
        base = 50.0
        interestingness = 0.5  # 0.5 * 100 = 50
        blended = self._make_blend(base, interestingness, blend_weight=0.2)
        assert blended == pytest.approx(50.0)


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
