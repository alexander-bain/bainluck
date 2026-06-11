"""Tests for the shared market-staleness helper (utils/market_staleness.py).

This module backs the data-quality filtering on all four category routes
(entertainment, politics, weather, economics) and the Discover feed's
title-implied stale-blocker. A market whose title implies the real-world
event is over, whose probability sits at a dead extreme, or whose status is
no longer "open" is dead content and must be excluded from featured sections.

Class-of-issue guard for queue #31 / issue #884: resolved/extreme markets and
title-implied-passed events (e.g. Eurovision after May 31) polluting category
pages.
"""

from datetime import datetime, timezone

from app.utils.market_staleness import (
    PROBABILITY_EXTREME_HIGH,
    PROBABILITY_EXTREME_LOW,
    infer_market_real_world_end,
    is_probability_extreme,
    is_title_implied_stale,
    should_exclude_from_featured,
)

# A fixed "now" so tests are deterministic regardless of the wall clock.
NOW = datetime(2026, 6, 11, 17, 0, 0, tzinfo=timezone.utc)


class TestTitleImpliedStale:
    def test_recurring_event_past_is_stale(self):
        # Eurovision ends May 31 (grace 0); on June 11 it is over.
        assert is_title_implied_stale("Eurovision Winner 2026?", "entertainment", NOW) == (
            "stale_recurring_event_calendar"
        )

    def test_recurring_event_future_year_not_stale(self):
        # A 2027 Eurovision question is a live future market, not stale.
        assert (
            is_title_implied_stale(
                "Which countries will participate in Eurovision Song Contest 2027?",
                "entertainment",
                NOW,
            )
            is None
        )

    def test_explicit_past_date_is_stale(self):
        # Daily chart market dated to a day that has passed.
        assert is_title_implied_stale(
            "Top USA Song on Spotify on May 31, 2026?", "entertainment", NOW
        ) == "stale_explicit_title_date"

    def test_explicit_today_date_within_grace_not_stale(self):
        # Today's daily market is still current (1-day grace).
        assert (
            is_title_implied_stale(
                "Top Artist on Weekly Top Artists USA on Jun 11, 2026?",
                "entertainment",
                NOW,
            )
            is None
        )

    def test_explicit_future_date_not_stale(self):
        assert (
            is_title_implied_stale(
                "#1 on the Billboard Hot 100 for the Week of Jun 20, 2026?",
                "entertainment",
                NOW,
            )
            is None
        )

    def test_us_open_only_stale_for_tennis(self):
        # "US Open" recurring rule is gated to the tennis category to avoid
        # matching golf / unrelated markets.
        assert (
            infer_market_real_world_end("US Open Winner 2026", "golf", NOW) is None
        )
        assert (
            infer_market_real_world_end("US Open Winner 2026", "tennis", NOW)
            is not None
        )

    def test_no_date_no_event_is_not_stale(self):
        assert is_title_implied_stale("Who wins Best Picture?", "entertainment", NOW) is None

    def test_empty_name_is_safe(self):
        assert is_title_implied_stale(None, "entertainment", NOW) is None
        assert is_title_implied_stale("", "entertainment", NOW) is None


class TestProbabilityExtreme:
    def test_high_extreme(self):
        assert is_probability_extreme(0.985) is True
        assert is_probability_extreme(0.999) is True

    def test_low_extreme(self):
        assert is_probability_extreme(0.01) is True
        assert is_probability_extreme(0.0) is True

    def test_boundary_inclusive_of_live_range(self):
        # Exactly at the thresholds is NOT extreme (strict comparison) so
        # legitimate edge markets (e.g. a 0.98 wildcard) survive.
        assert is_probability_extreme(PROBABILITY_EXTREME_LOW) is False
        assert is_probability_extreme(PROBABILITY_EXTREME_HIGH) is False

    def test_mid_range_not_extreme(self):
        assert is_probability_extreme(0.5) is False
        assert is_probability_extreme(0.3) is False

    def test_none_is_not_extreme(self):
        assert is_probability_extreme(None) is False


class TestShouldExcludeFromFeatured:
    def test_resolved_status_excluded(self):
        assert (
            should_exclude_from_featured("Anything", "entertainment", "resolved", 0.5, NOW)
            == "resolved"
        )
        assert (
            should_exclude_from_featured("Anything", "entertainment", "settled", 0.5, NOW)
            == "resolved"
        )

    def test_open_status_passes_status_check(self):
        assert (
            should_exclude_from_featured("Live race", "entertainment", "open", 0.45, NOW)
            is None
        )

    def test_extreme_probability_excluded(self):
        assert (
            should_exclude_from_featured(
                '"Supergirl" Rotten Tomatoes score?', "entertainment", "open", 0.985, NOW
            )
            == "probability_extreme"
        )

    def test_title_stale_excluded(self):
        assert (
            should_exclude_from_featured(
                "Eurovision Winner 2026?", "entertainment", "open", 0.30, NOW
            )
            == "stale_recurring_event_calendar"
        )

    def test_healthy_open_market_not_excluded(self):
        assert (
            should_exclude_from_featured(
                "Who wins Best Picture 2027?", "entertainment", "open", 0.42, NOW
            )
            is None
        )

    def test_status_takes_precedence_over_probability(self):
        # A resolved market is reported as "resolved" even if also extreme.
        assert (
            should_exclude_from_featured("X", "entertainment", "resolved", 0.99, NOW)
            == "resolved"
        )
