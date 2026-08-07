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


# UX-P006 / #1567 — the residuals UX-P004 left open. AUGUST_7 is the window in
# which the production specimen below was captured.
AUGUST_7 = datetime(2026, 8, 7, 17, 0, 0, tzinfo=timezone.utc)


class TestDayLessRungsExpire:
    """#1567 item 1: ``_EXPLICIT_MONTH_DAY_RE`` REQUIRES a day, so a rung naming
    only a month or only a year was never inspected and survived forever."""

    # The production specimen, read from futures_outcomes on 2026-08-07:
    # market 109435 "Will the U.S. confirm that aliens exist?", 9 rungs.
    ALIENS_LADDER = [
        "Before Jan 20, 2029",
        "Before 2028",
        "Before 2027",
        "Before November",
        "Before December",
        "Before October",
        "Before September",
        "Before July",
        "Before August",
    ]

    def test_production_aliens_ladder_drops_exactly_the_dead_rungs(self):
        # BOTH directions in one assertion (gotcha #43): the two impossible
        # rungs go, and all seven live ones stay.
        assert expired_ladder_rungs(self.ALIENS_LADDER, AUGUST_7) == {
            "Before July",
            "Before August",
        }

    def test_bare_month_rung_expired(self):
        # The rung named in #1567: 1% on a live card in August.
        assert outcome_deadline_expired("Before July", AUGUST_7) is True

    def test_before_a_month_means_before_it_BEGINS(self):
        # "Before August" read on Aug 7 is already impossible. The same ladder
        # carries "Before 2027"/"Before 2028", where the boundary is
        # unambiguously the START of the named period — so "Before <Month>"
        # ends the last day of the PREVIOUS month, not of the named one.
        assert outcome_deadline_expired("Before August", AUGUST_7) is True
        # ...and it is NOT yet expired on Aug 1, inside the one-day grace.
        aug_1 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("Before August", aug_1) is False

    def test_future_bare_month_rungs_survive(self):
        # The four rungs #1567's acceptance criterion requires to stay.
        for rung in (
            "Before September",
            "Before October",
            "Before November",
            "Before December",
        ):
            assert outcome_deadline_expired(rung, AUGUST_7) is False, rung

    def test_bare_month_with_no_deadline_context_is_ignored(self):
        # A month name is also an ordinary English word. Stripping a rung is
        # the sharp edge — a false positive deletes a LIVE option from a card.
        for rung in ("Trump may resign", "May not run", "2024 champion", "Spain"):
            assert outcome_deadline_expired(rung, AUGUST_7) is False, rung

    def test_after_a_month_is_not_a_deadline(self):
        # "After July" does not become impossible when July ends.
        assert outcome_deadline_expired("After July", AUGUST_7) is False

    def test_whole_name_month_is_a_deadline(self):
        # A rung named just "July" in a "when will X happen?" ladder IS a
        # period, and the period is inclusive — it ends Jul 31.
        assert outcome_deadline_expired("July", AUGUST_7) is True
        assert outcome_deadline_expired("September", AUGUST_7) is False

    def test_ambiguous_prefix_takes_the_conservative_inclusive_end(self):
        # "by July" could mean either boundary; the later one suppresses less.
        assert outcome_deadline_expired("By July", AUGUST_7) is True
        assert outcome_deadline_expired("By August", AUGUST_7) is False

    def test_month_and_year_rung_uses_the_explicit_year(self):
        assert outcome_deadline_expired("Jun 2026", AUGUST_7) is True
        assert outcome_deadline_expired("Before July 2026", AUGUST_7) is True
        assert outcome_deadline_expired("December 2026", AUGUST_7) is False
        assert outcome_deadline_expired("Before July 2027", AUGUST_7) is False

    def test_bare_year_rung(self):
        # Also day-less, also on the aliens ladder.
        assert outcome_deadline_expired("Before 2026", AUGUST_7) is True
        assert outcome_deadline_expired("Before 2027", AUGUST_7) is False
        assert outcome_deadline_expired("In 2025", AUGUST_7) is True
        assert outcome_deadline_expired("2027", AUGUST_7) is False

    def test_bare_month_far_in_past_assumed_next_year(self):
        # Reuses _BARE_DATE_LOOKBACK_DAYS: a bare "December" read in January is
        # the COMING December, not one 11 months stale.
        january = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("Before December", january) is False
        assert outcome_deadline_expired("December", january) is False
        december = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("Before February", december) is False

    def test_month_day_rungs_are_unchanged(self):
        # The pre-existing branch must keep winning over the new day-less ones.
        assert outcome_deadline_expired("Before Jul 25, 2026", AUGUST_7) is True
        assert outcome_deadline_expired("July 31", AUGUST_7) is True
        assert outcome_deadline_expired("September 30", AUGUST_7) is False
        assert outcome_deadline_expired("Before Jan 20, 2029", AUGUST_7) is False

    def test_binary_and_entity_rungs_still_never_expire(self):
        for rung in ("Yes", "No", "France", "Jerome Powell", None, ""):
            assert outcome_deadline_expired(rung, AUGUST_7) is False, rung


class TestExpiredRungAtHighProbabilityIsTheAnswer:
    """UX-P006 production census (2026-08-07): widening the parser to day-less
    rungs put 189 rungs across 92 open markets in scope, and 44 of them were
    priced 89-100% — they had already resolved YES. Stripping those hides the
    leader, which is the UX-P005 defect class. Gotcha #43 in its sharpest form:
    the widened suppression must not eat live content."""

    def test_the_month_ladder_winner_is_kept(self):
        # Production m128659 "In which month will SpaceX IPO?" — a mutually
        # exclusive month ladder whose ANSWER is a past month at 99.95%.
        ladder = [
            ("June", 0.9995),
            ("July", 0.0005),
            ("August", 0.0005),
            ("September", 0.0005),
            ("December", 0.0005),
        ]
        expired = expired_ladder_rungs(ladder, AUGUST_7)
        assert "June" not in expired, "stripping the winner would hide the leader"
        assert "July" in expired, "a 0.05% past month IS a ghost rung"

    def test_settled_cumulative_rungs_are_kept(self):
        # Production m108333 "When will a member of Trump's Cabinet leave?" —
        # the event happened, so every "Before <past date>" rung reads 99.5%.
        ladder = [
            ("Before Apr 2026", 0.995),
            ("Before May 2026", 0.995),
            ("Before Jun 2026", 0.995),
            ("Before Sep 2026", 0.995),
        ]
        assert expired_ladder_rungs(ladder, AUGUST_7) == set()

    def test_low_priced_past_rungs_are_still_stripped(self):
        # The census class the issue names: "past-dated options still showing
        # 1-3%". These must keep going.
        ladder = [
            ("Before July", 0.01),
            ("Before August", 0.01),
            ("Before September", 0.015),
            ("Before Jan 20, 2029", 0.225),
        ]
        assert expired_ladder_rungs(ladder, AUGUST_7) == {
            "Before July",
            "Before August",
        }

    def test_threshold_boundary(self):
        assert expired_ladder_rungs([("Before July", 0.49)], AUGUST_7) == {"Before July"}
        assert expired_ladder_rungs([("Before July", 0.5)], AUGUST_7) == set()

    def test_bare_names_still_accepted_without_probabilities(self):
        # Backwards compatibility: the name-only form keeps working.
        assert expired_ladder_rungs(["Before July", "Yes"], AUGUST_7) == {"Before July"}
        assert expired_ladder_rungs([("Before July", None)], AUGUST_7) == {"Before July"}

    def test_ux_p004_specimens_are_not_rescued_by_the_guard(self):
        # The two rungs UX-P004 shipped to strip were both cheap; the guard
        # must not quietly undo that fix.
        assert expired_ladder_rungs([("Before Jul 25, 2026", 0.03)], AUGUST_7) == {
            "Before Jul 25, 2026"
        }
        assert expired_ladder_rungs([("July 31", 0.0067)], AUGUST_7) == {"July 31"}


class TestWorldCupQualifyingKeepsItsOwnCalendar:
    """#1567 item 2: the World Cup rule is year-agnostic by design (it must also
    cover the annual Club World Cup), so it fires in non-tournament years too.
    Qualifying runs into November — latent until the 2030 cycle (2027-2029)."""

    OCTOBER_2027 = datetime(2027, 10, 12, 12, 0, tzinfo=timezone.utc)

    def test_qualifier_market_survives_in_october_of_a_qualifying_year(self):
        for name in (
            "World Cup Qualifying: Will Italy qualify?",
            "FIFA World Cup Qualifiers - CONMEBOL Winner",
            "Will Brazil qualify for the World Cup?",
            "World Cup Qualification: UEFA Group A Winner",
        ):
            assert is_title_implied_stale(name, "soccer", self.OCTOBER_2027) is None, (
                f"{name!r} runs into November and must not take the July "
                "tournament-final calendar"
            )

    def test_qualifier_survives_in_august_too(self):
        # ~Aug 3 is where the (7, 31) + 3-day-grace rule would have bitten.
        assert (
            is_title_implied_stale("World Cup Qualifying Winner", "soccer", AUGUST_7)
            is None
        )

    def test_the_tournament_rule_itself_does_not_regress(self):
        # The UX-P004 production specimen — must still be suppressed.
        assert (
            is_title_implied_stale(
                "World Cup: Nation To Reach Quarterfinals", "soccer", AUGUST_7
            )
            == "stale_recurring_event_calendar"
        )

    def test_future_and_non_soccer_world_cups_still_survive(self):
        assert is_title_implied_stale("2030 FIFA World Cup Champion", "soccer", AUGUST_7) is None
        assert is_title_implied_stale("Cricket World Cup Winner", "cricket", AUGUST_7) is None

    def test_exclusion_is_scoped_to_the_world_cup_rule(self):
        # The generic exclude_pattern field must not leak onto other rules: a
        # golf major with an unrelated title is governed exactly as before.
        assert (
            is_title_implied_stale("US Open Winner", "golf", AUGUST_7)
            == "stale_recurring_event_calendar"
        )
        assert is_title_implied_stale("Eurovision Winner", "entertainment", AUGUST_7) == (
            "stale_recurring_event_calendar"
        )
