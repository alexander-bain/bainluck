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
    expired_ladder_rungs,
    infer_market_real_world_end,
    is_probability_extreme,
    is_title_implied_stale,
    outcome_deadline_expired,
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

    def test_us_open_calendar_is_per_sport(self):
        # "US Open" is two different tournaments. Golf's ends in June, tennis's
        # in September, so the SAME title must resolve to a different end date
        # per category — and never borrow the other sport's calendar.
        # (UX-P004 class a: golf previously got NO calendar at all, so the
        # concluded major sat on Discover at live-looking probabilities.)
        golf = infer_market_real_world_end("US Open Winner 2026", "golf", NOW)
        tennis = infer_market_real_world_end("US Open Winner 2026", "tennis", NOW)
        assert golf is not None and tennis is not None
        assert golf[0].month == 6, "golf US Open must use the June calendar"
        assert tennis[0].month == 9, "tennis US Open must use the September calendar"

        # Neither is stale DURING its own tournament...
        assert is_title_implied_stale("US Open Winner 2026", "golf", NOW) is None
        assert is_title_implied_stale("US Open Winner 2026", "tennis", NOW) is None
        # ...but the concluded golf major is stale in August, while the tennis
        # one (still ahead) is not. This is the exact pair that shipped broken.
        august = datetime(2026, 8, 5, 17, 0, tzinfo=timezone.utc)
        assert (
            is_title_implied_stale("US Open Winner 2026", "golf", august)
            == "stale_recurring_event_calendar"
        )
        assert is_title_implied_stale("US Open Winner 2026", "tennis", august) is None

    def test_unrelated_category_us_open_gets_no_calendar(self):
        # The guard must still refuse categories that own neither tournament.
        assert (
            infer_market_real_world_end("US Open Winner 2026", "politics", NOW) is None
        )

    def test_month_year_past_is_stale(self):
        # #883 L2-56: "... in May 2026?" on Jun 11 — the month has ended even
        # though Kalshi's resolution_date is mid-June (settlement lag). This is
        # the class that kept featuring "Rain in LA in Jun 2026?" in July.
        assert is_title_implied_stale(
            "Rain in Los Angeles in May 2026?", "weather", NOW
        ) == "stale_explicit_title_month"

    def test_month_year_current_month_not_stale(self):
        # Jun 2026 on Jun 11 — still current (ends Jun 30).
        assert is_title_implied_stale(
            "Rain in Los Angeles in Jun 2026?", "weather", NOW
        ) is None

    def test_month_year_future_not_stale(self):
        assert is_title_implied_stale(
            "Rain in Los Angeles in Aug 2026?", "weather", NOW
        ) is None
        assert is_title_implied_stale(
            "Rain in Los Angeles in Jun 2027?", "weather", NOW
        ) is None

    def test_year_only_not_stale(self):
        # A season future ("... 2026") must NOT be flagged by the month-year rule.
        assert is_title_implied_stale("NBA Champion 2026", "basketball", NOW) is None

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


# UX-P004 — settled means settled. Each test below pins one production example
# captured in the Item 0 census on 2026-08-05.
AUGUST = datetime(2026, 8, 5, 23, 25, 0, tzinfo=timezone.utc)


class TestConcludedTournamentCalendar:
    """Class (a): a concluded tournament keeps a NULL resolution_date and keeps
    being polled, so neither the date gate nor updated_at staleness ever fires."""

    def test_concluded_world_cup_market_is_stale(self):
        # Production: "World Cup: Nation To Reach Quarterfinals", soccer,
        # resolution_date=None, Argentina still showing 59% on 2026-08-05.
        assert (
            is_title_implied_stale(
                "World Cup: Nation To Reach Quarterfinals", "soccer", AUGUST
            )
            == "stale_recurring_event_calendar"
        )

    def test_future_world_cup_is_protected_by_implied_year(self):
        # Both were on the live feed and MUST survive — the implied-year check
        # returns before the recurring rules are consulted.
        assert (
            is_title_implied_stale("2030 FIFA World Cup Champion", "soccer", AUGUST)
            is None
        )
        assert (
            is_title_implied_stale(
                "2027 FIFA Women's World Cup Champion", "soccer", AUGUST
            )
            is None
        )

    def test_world_cup_rule_is_soccer_only(self):
        # Cricket/rugby world cups run on entirely different calendars.
        assert is_title_implied_stale("Cricket World Cup Winner", "cricket", AUGUST) is None

    def test_concluded_golf_major_is_stale(self):
        assert (
            is_title_implied_stale("US Open Winner", "golf", AUGUST)
            == "stale_recurring_event_calendar"
        )

    def test_golf_major_not_stale_during_its_week(self):
        june = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        assert is_title_implied_stale("US Open Winner", "golf", june) is None


class TestExpiredLadderRungs:
    """Classes (b) + (e): a dated rung that can no longer happen keeps its last
    traded price and renders as a live 1-3% option."""

    def test_past_rung_with_explicit_year_expired(self):
        # Production: "Before Jul 25, 2026" still showing 3% on 2026-08-05.
        assert outcome_deadline_expired("Before Jul 25, 2026", AUGUST) is True

    def test_bare_date_rung_expired(self):
        # Production: Netanyahu card, rung "July 31" still showing 0.67%.
        assert outcome_deadline_expired("July 31", AUGUST) is True

    def test_future_rung_survives(self):
        assert outcome_deadline_expired("Before Jan 1, 2027", AUGUST) is False
        assert outcome_deadline_expired("Before Jan 20, 2029", AUGUST) is False

    def test_undated_rung_survives(self):
        assert outcome_deadline_expired("Yes", AUGUST) is False
        assert outcome_deadline_expired(None, AUGUST) is False

    def test_bare_date_far_in_past_assumed_next_year(self):
        # A bare "December 31" read in January means the COMING December, not a
        # rung that expired 11 months ago.
        january = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("December 31", january) is False

    def test_rung_not_expired_within_grace(self):
        just_after = datetime(2026, 7, 31, 23, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("July 31", just_after) is False

    def test_expired_ladder_rungs_partitions_the_ladder(self):
        rungs = ["Before Jul 25, 2026", "Before Jan 1, 2027", "Yes", None]
        assert expired_ladder_rungs(rungs, AUGUST) == {"Before Jul 25, 2026"}

    def test_ladder_with_no_expired_rungs_is_empty(self):
        assert expired_ladder_rungs(["Before Jan 1, 2027", "Yes"], AUGUST) == set()
