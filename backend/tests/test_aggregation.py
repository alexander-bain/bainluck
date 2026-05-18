"""Tests for the multi-source probability aggregation engine."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.aggregation import (
    TimestampedProb,
    compute_aggregate_probability,
    compute_aggregated_probability,
    compute_current_aggregate,
    _weighted_median,
    _staleness_weight,
    SOURCE_WEIGHTS,
)


BASE_TIME = datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)


def _tp(minutes: float, prob: float) -> TimestampedProb:
    """Helper to create a TimestampedProb."""
    return TimestampedProb(
        timestamp=BASE_TIME + timedelta(minutes=minutes),
        home_probability=prob,
    )


class TestWeightedMedian:
    """Test the weighted median calculation."""

    def test_single_value(self):
        assert _weighted_median([0.5], [1.0]) == 0.5

    def test_equal_weights(self):
        """Equal weights → regular median."""
        result = _weighted_median([0.3, 0.5, 0.7], [1.0, 1.0, 1.0])
        assert result == 0.5

    def test_heavy_weight_on_low(self):
        """Heavy weight on low value should pull median down."""
        result = _weighted_median([0.3, 0.5, 0.7], [10.0, 1.0, 1.0])
        assert result == 0.3

    def test_heavy_weight_on_high(self):
        """Heavy weight on high value should pull median up."""
        result = _weighted_median([0.3, 0.5, 0.7], [1.0, 1.0, 10.0])
        assert result == 0.7

    def test_two_values_heavy_first(self):
        result = _weighted_median([0.4, 0.8], [3.0, 1.0])
        assert result == 0.4

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _weighted_median([], [])

    def test_zero_weights_fallback(self):
        """All zero weights should still return something."""
        result = _weighted_median([0.3, 0.5, 0.7], [0.0, 0.0, 0.0])
        assert result == 0.5  # Falls back to simple median

    def test_outlier_resistance(self):
        """Weighted median should resist outliers."""
        # 3 sources agree at ~0.55, one outlier at 0.90
        result = _weighted_median(
            [0.53, 0.55, 0.57, 0.90],
            [3.0, 1.5, 1.0, 0.8],
        )
        # The 0.90 outlier should NOT pull the median to 0.70+
        assert 0.50 <= result <= 0.60


class TestStalenessWeight:
    """Test staleness decay function."""

    def test_fresh_full_weight(self):
        """0 seconds stale → full weight."""
        assert _staleness_weight(0) == 1.0

    def test_within_grace_period(self):
        """Within 2 min grace → full weight."""
        assert _staleness_weight(60) == 1.0
        assert _staleness_weight(119) == 1.0

    def test_at_grace_boundary(self):
        """Exactly at 2 min → full weight."""
        assert _staleness_weight(120) == 1.0

    def test_decay_midpoint(self):
        """At 3.5 min (210s) → ~50% weight."""
        weight = _staleness_weight(210)
        assert 0.4 <= weight <= 0.6

    def test_fully_stale(self):
        """At 5 min → zero weight."""
        assert _staleness_weight(300) == 0.0

    def test_very_stale(self):
        """Beyond 5 min → zero weight."""
        assert _staleness_weight(600) == 0.0


class TestComputeAggregatedProbability:
    """Test the full time-series aggregation."""

    def test_single_source(self):
        """Single source → aggregate follows it."""
        sources = {
            "betting": [_tp(0, 0.50), _tp(1, 0.55), _tp(2, 0.60)],
        }
        result = compute_aggregated_probability(sources, bucket_seconds=30)
        assert len(result) >= 3
        # First value should be close to 0.50 (smoothing may shift slightly)
        assert abs(result[0].home_probability - 0.50) < 0.01

    def test_two_sources_weighted(self):
        """Betting (weight 3.0) should dominate over Kalshi (weight 0.8)."""
        sources = {
            "betting": [_tp(0, 0.60)],
            "kalshi": [_tp(0, 0.40)],
        }
        result = compute_aggregated_probability(sources, bucket_seconds=30)
        assert len(result) >= 1
        # Weighted median of [0.40 (w=0.8), 0.60 (w=3.0)] → 0.60
        assert result[0].home_probability == pytest.approx(0.60, abs=0.01)

    def test_multiple_sources_median(self):
        """Three sources → weighted median, not mean."""
        sources = {
            "betting": [_tp(0, 0.55)],       # weight 3.0
            "espn": [_tp(0, 0.60)],           # weight 1.5
            "kalshi": [_tp(0, 0.90)],         # weight 0.8 — outlier!
        }
        result = compute_aggregated_probability(sources, bucket_seconds=30)
        assert len(result) >= 1
        # Weighted median should be near betting/ESPN, NOT pulled by Kalshi outlier
        assert result[0].home_probability < 0.70

    def test_stale_source_dropped(self):
        """Source >5 min stale should be ignored."""
        sources = {
            "betting": [_tp(0, 0.50), _tp(10, 0.60)],
            "kalshi": [_tp(0, 0.90)],  # Only has t=0 data, will be stale at t=10
        }
        result = compute_aggregated_probability(sources, bucket_seconds=30)
        # At t=10, Kalshi is 10 min stale → fully dropped
        # The last data point should be moving toward betting's 0.60
        # (smoothing may still carry some of the earlier blended value)
        last = result[-1]
        assert last.home_probability > 0.50

    def test_empty_sources(self):
        result = compute_aggregated_probability({})
        assert result == []

    def test_smoothing_prevents_jumps(self):
        """Exponential smoothing should prevent sudden jumps."""
        sources = {
            "betting": [_tp(0, 0.50), _tp(1, 0.50), _tp(2, 0.80)],
        }
        result = compute_aggregated_probability(sources, bucket_seconds=30)
        # The jump from 0.50 to 0.80 should be smoothed
        # With α=0.3: new = 0.3*0.80 + 0.7*0.50 = 0.59 (not 0.80)
        probs = [r.home_probability for r in result]
        # Check there's no single jump > 0.25 in the sequence
        for i in range(1, len(probs)):
            assert abs(probs[i] - probs[i - 1]) < 0.25


class TestComputeCurrentAggregate:
    """Test real-time single-point aggregation."""

    def test_single_source(self):
        now = BASE_TIME
        result = compute_current_aggregate(
            {"betting": (0.65, now)},
            now,
        )
        assert result == pytest.approx(0.65, abs=0.001)

    def test_weighted_median_used(self):
        now = BASE_TIME
        result = compute_current_aggregate(
            {
                "betting": (0.60, now),     # weight 3.0
                "kalshi": (0.40, now),      # weight 0.8
            },
            now,
        )
        # Weighted median: betting dominates → 0.60
        assert result == pytest.approx(0.60, abs=0.001)

    def test_stale_source_reduced(self):
        now = BASE_TIME
        result = compute_current_aggregate(
            {
                "betting": (0.55, now),
                "kalshi": (0.90, now - timedelta(minutes=6)),  # 6 min stale → dropped
            },
            now,
        )
        # Kalshi should be fully dropped
        assert result == pytest.approx(0.55, abs=0.001)

    def test_no_valid_readings(self):
        now = BASE_TIME
        result = compute_current_aggregate(
            {
                "kalshi": (0.50, now - timedelta(minutes=10)),  # Way too stale
            },
            now,
        )
        assert result is None

    def test_many_sources(self):
        """All 5 main sources with fresh data."""
        now = BASE_TIME
        result = compute_current_aggregate(
            {
                "betting": (0.55, now),       # w=3.0
                "espn": (0.58, now),           # w=1.5
                "stat_model": (0.52, now),     # w=1.0
                "kalshi": (0.56, now),         # w=0.8
                "polymarket": (0.54, now),     # w=0.8
            },
            now,
        )
        # All sources roughly agree around 0.55
        assert 0.52 <= result <= 0.58


class TestComputeAggregateProbability:
    """Test event-model aggregation helper used during serialization."""

    def test_reads_numeric_and_value_wrapped_sources(self):
        event = type("Event", (), {
            "status": "live",
            "win_probability_sources": {
                "betting": 0.60,
                "espn": {"value": 0.54},
                "unknown_source": 0.05,
            },
            "espn_win_prob_home": 0.20,
            "opening_home_probability": 0.10,
        })()

        expected = ((0.60 * SOURCE_WEIGHTS["betting"]) + (0.54 * SOURCE_WEIGHTS["espn"])) / (
            SOURCE_WEIGHTS["betting"] + SOURCE_WEIGHTS["espn"]
        )
        assert compute_aggregate_probability(event) == pytest.approx(expected)

    def test_completed_games_exclude_prediction_markets(self):
        event = type("Event", (), {
            "status": "completed",
            "win_probability_sources": {
                "betting": 1.0,
                "kalshi": 0.55,
                "polymarket": 0.45,
            },
            "espn_win_prob_home": None,
            "opening_home_probability": None,
        })()

        assert compute_aggregate_probability(event) == 1.0

    def test_event_status_argument_overrides_event_status(self):
        event = type("Event", (), {
            "status": "live",
            "win_probability_sources": {
                "betting": 1.0,
                "kalshi": 0.0,
            },
            "espn_win_prob_home": None,
            "opening_home_probability": None,
        })()

        assert compute_aggregate_probability(event, event_status="closed") == 1.0

    def test_falls_back_to_espn_then_opening_probability(self):
        event = type("Event", (), {
            "status": "live",
            "win_probability_sources": {},
            "espn_win_prob_home": 0.42,
            "opening_home_probability": 0.38,
        })()
        assert compute_aggregate_probability(event) == 0.42

        event.espn_win_prob_home = None
        assert compute_aggregate_probability(event) == 0.38

    def test_returns_none_without_any_probability(self):
        event = type("Event", (), {
            "status": "scheduled",
            "win_probability_sources": {"kalshi": {"value": None}},
            "espn_win_prob_home": None,
            "opening_home_probability": None,
        })()

        assert compute_aggregate_probability(event) is None
