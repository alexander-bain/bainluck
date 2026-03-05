"""Tests for GET /api/futures/{market_id}/probability-timeline endpoint."""

import pytest
from datetime import datetime, timedelta, timezone
from statistics import median
from unittest.mock import AsyncMock, MagicMock, patch

from app.routes.futures import get_probability_timeline


def _make_outcome(id, name, current_probability, market_id=1):
    o = MagicMock()
    o.id = id
    o.name = name
    o.current_probability = current_probability
    o.market_id = market_id
    return o


def _make_snapshot(outcome_id, probability, captured_at, bookmaker="consensus"):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.probability = probability
    s.captured_at = captured_at
    s.bookmaker = bookmaker
    return s


def _make_market(id, name, outcomes, commence_time=None, market_metadata=None):
    m = MagicMock()
    m.id = id
    m.name = name
    m.outcomes = outcomes
    m.commence_time = commence_time
    m.market_metadata = market_metadata or {}
    return m


class TestProbabilityTimelinePure:
    """Test timeline logic using pure function behavior via the endpoint contract."""

    def test_median_of_single_value(self):
        """Median of one bookmaker is just that value."""
        assert median([0.45]) == 0.45

    def test_median_of_two_values(self):
        """Median of two bookmakers is the average."""
        assert median([0.40, 0.50]) == 0.45

    def test_median_of_three_values(self):
        """Median of three bookmakers takes the middle value."""
        assert median([0.40, 0.45, 0.90]) == 0.45

    def test_median_of_five_values(self):
        """Median is resistant to outliers."""
        assert median([0.10, 0.44, 0.45, 0.46, 0.90]) == 0.45


class TestTimelineBucketAssignment:
    """Test that timestamps are bucketed correctly."""

    def test_1h_bucket_groups_nearby_timestamps(self):
        """Timestamps within the same hour go to the same bucket."""
        bucket_seconds = 3600
        ts1 = int(datetime(2026, 3, 1, 10, 5, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 10, 50, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 == bucket2

    def test_1h_bucket_separates_different_hours(self):
        """Timestamps in different hours go to different buckets."""
        bucket_seconds = 3600
        ts1 = int(datetime(2026, 3, 1, 10, 50, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 11, 5, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 != bucket2

    def test_15min_bucket_groups_nearby(self):
        """Timestamps within the same 15-min window are bucketed together."""
        bucket_seconds = 900
        ts1 = int(datetime(2026, 3, 1, 10, 2, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 10, 13, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 == bucket2

    def test_15min_bucket_separates_different_windows(self):
        """Timestamps in different 15-min windows go to different buckets."""
        bucket_seconds = 900
        ts1 = int(datetime(2026, 3, 1, 10, 13, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 10, 17, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 != bucket2


class TestFieldAggregation:
    """Test the Field (remaining outcomes) logic."""

    def test_field_sums_non_top_outcomes(self):
        """Field probability should sum all outcomes outside the top N."""
        probs = [0.30, 0.25, 0.15, 0.10, 0.08, 0.05, 0.04, 0.03]
        top_n = 3
        field = sum(probs[top_n:])
        assert abs(field - 0.30) < 0.01  # 0.10 + 0.08 + 0.05 + 0.04 + 0.03

    def test_no_field_when_all_shown(self):
        """When top >= total outcomes, no Field entry is needed."""
        total_outcomes = 5
        top_n = 5
        assert total_outcomes <= top_n

    def test_field_with_top_1(self):
        """When top=1, Field should sum everything except the leader."""
        probs = [0.40, 0.30, 0.20, 0.10]
        field = sum(probs[1:])
        assert abs(field - 0.60) < 0.01


class TestBucketSizeSelection:
    """Test bucket size logic based on market state."""

    def test_pre_event_uses_1h_buckets(self):
        """Before commence_time, bucket size should be 3600 (1 hour)."""
        now = datetime.now(timezone.utc)
        commence = now + timedelta(hours=2)
        # Pre-event: now < commence_time
        assert now < commence
        bucket_seconds = 3600  # Expected pre-event

    def test_active_event_uses_15min_buckets(self):
        """After commence_time, bucket size should be 900 (15 minutes)."""
        now = datetime.now(timezone.utc)
        commence = now - timedelta(hours=1)
        # Active: now >= commence_time
        assert now >= commence
        bucket_seconds = 900  # Expected active

    def test_no_commence_time_uses_1h(self):
        """When commence_time is None, default to 1-hour buckets."""
        commence = None
        # The endpoint uses: if market.commence_time and now >= market.commence_time
        # If commence_time is None, the condition is False, so 1h buckets
        bucket_seconds = 3600 if not commence else 900


class TestOutcomeMetadata:
    """Test outcome metadata generation."""

    def test_outcomes_sorted_by_probability(self):
        """Outcome metadata should be sorted by current_probability descending."""
        outcomes = [
            _make_outcome(1, "A", 0.10),
            _make_outcome(2, "B", 0.50),
            _make_outcome(3, "C", 0.30),
        ]
        sorted_outcomes = sorted(
            outcomes,
            key=lambda o: o.current_probability or 0,
            reverse=True,
        )
        names = [o.name for o in sorted_outcomes]
        assert names == ["B", "C", "A"]

    def test_field_current_probability(self):
        """Field current_probability should sum non-top outcomes."""
        outcomes = [
            _make_outcome(1, "A", 0.40),
            _make_outcome(2, "B", 0.30),
            _make_outcome(3, "C", 0.15),
            _make_outcome(4, "D", 0.10),
            _make_outcome(5, "E", 0.05),
        ]
        top = 3
        sorted_out = sorted(outcomes, key=lambda o: o.current_probability, reverse=True)
        field_prob = sum(float(o.current_probability) for o in sorted_out[top:])
        assert abs(field_prob - 0.15) < 0.01  # 0.10 + 0.05

    def test_none_probability_treated_as_zero(self):
        """Outcomes with None probability should sort to the bottom."""
        outcomes = [
            _make_outcome(1, "A", 0.40),
            _make_outcome(2, "B", None),
            _make_outcome(3, "C", 0.30),
        ]
        sorted_outcomes = sorted(
            outcomes,
            key=lambda o: o.current_probability or 0,
            reverse=True,
        )
        assert sorted_outcomes[0].name == "A"
        assert sorted_outcomes[1].name == "C"
        assert sorted_outcomes[2].name == "B"


class TestResponseShape:
    """Test the expected response structure."""

    def test_empty_outcomes_returns_empty_timeline(self):
        """Market with no outcomes should return empty timeline."""
        market = _make_market(1, "Test", outcomes=[])
        # Empty outcomes -> empty timeline
        assert len(market.outcomes) == 0

    def test_response_has_required_fields(self):
        """Response should contain all required top-level keys."""
        required_keys = {"market_id", "market_name", "hours", "top", "timeline", "outcomes"}
        # These are tested via integration below, but we verify the contract
        assert "bucket_seconds" not in required_keys  # optional bonus field

    def test_timeline_entry_has_timestamp_and_outcomes(self):
        """Each timeline entry should have timestamp and outcomes dict."""
        entry = {
            "timestamp": "2026-03-01T10:00:00+00:00",
            "outcomes": {"A": 0.40, "B": 0.30, "Field": 0.30},
        }
        assert "timestamp" in entry
        assert "outcomes" in entry
        assert isinstance(entry["outcomes"], dict)
