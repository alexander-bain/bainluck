"""Tests for futures market highlight scoring."""

from datetime import datetime, timezone, timedelta
import pytest
from app.utils.futures_highlights import (
    compute_futures_highlight,
    is_minor_league_market,
    is_top_tier_soccer_market,
    MAJOR_MOVEMENT_THRESHOLD,
    MODERATE_MOVEMENT_THRESHOLD,
)


class TestComputeFuturesHighlight:
    """Tests for compute_futures_highlight()."""

    def test_empty_market_returns_low_score(self):
        """A market with no data gets a minimal score from its tier."""
        result = compute_futures_highlight()
        assert result.score >= 0
        assert result.score <= 10  # Only tier weight
        assert result.primary_reason is None

    def test_championship_tier_scores_higher(self):
        """Tier 1 (championship) markets score higher than tier 5."""
        tier1 = compute_futures_highlight(market_tier=1)
        tier5 = compute_futures_highlight(market_tier=5)
        assert tier1.score > tier5.score
        assert tier1.flags.is_high_tier is True
        assert tier5.flags.is_high_tier is False

    def test_major_league_bonus(self):
        """Major sport categories get a league bonus."""
        basketball = compute_futures_highlight(sport_category="basketball")
        other = compute_futures_highlight(sport_category="darts")
        assert basketball.score > other.score
        assert basketball.flags.league_tier == 1
        assert other.flags.league_tier == 3

    def test_esports_demoted_below_sports_floor(self):
        """esports is a near-zero-interest category (Alex policy, SEQUENCE 0b1b).

        It must get an explicit base BELOW the sports floor so it never
        out-bases an ordinary sports market (e.g. darts), and at/below crypto.
        """
        from app.utils.futures_highlights import (
            CATEGORY_BASE_SCORES,
            SPORTS_CATEGORY_BASE,
        )
        assert "esports" in CATEGORY_BASE_SCORES
        assert CATEGORY_BASE_SCORES["esports"] <= CATEGORY_BASE_SCORES["crypto"]
        assert CATEGORY_BASE_SCORES["esports"] < SPORTS_CATEGORY_BASE

        esports = compute_futures_highlight(sport_category="esports")
        darts = compute_futures_highlight(sport_category="darts")  # sports floor
        assert esports.score < darts.score
        assert "category_base_esports" in esports.reasons

    def test_major_postseason_path_scores_like_discover_story(self):
        """NBA Finals path markets are strong Discover sports stories."""
        now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        result = compute_futures_highlight(
            market_tier=2,
            sport_category="basketball",
            resolution_date=now + timedelta(days=23),
            now=now,
            market_name="Will Oklahoma City Thunder advance to the 2026 NBA Finals?",
            outcomes=[
                {
                    "name": "Yes",
                    "probability": 0.42,
                    "probability_change_24h": 0.0,
                    "rank": 1,
                    "rank_change_24h": 0,
                    "opening_probability": 0.555,
                }
            ],
        )

        assert result.score >= 65
        assert "sports_postseason_story" in result.reasons

    def test_conference_finals_path_does_not_get_championship_boost(self):
        """The postseason boost is narrow enough not to flood Discover with every round."""
        now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        result = compute_futures_highlight(
            market_tier=2,
            sport_category="basketball",
            resolution_date=now + timedelta(days=16),
            now=now,
            market_name="Will Boston Celtics advance to the Conference Finals in the 2026 NBA Playoffs?",
        )

        assert "sports_postseason_story" not in result.reasons
        assert result.score < 80

    def test_shareable_culture_markets_get_compelling_boost(self):
        result = compute_futures_highlight(
            market_tier=5,
            sport_category="entertainment",
            market_name="Who will be Taylor Swift's bridesmaids?",
        )

        assert result.score >= 60
        assert "compelling_x2" in result.reasons

    def test_major_movement_detected(self):
        """Large 24h probability changes are flagged."""
        outcomes = [
            {"name": "Team A", "probability": 0.30, "probability_change_24h": 0.08,
             "rank": 1, "rank_change_24h": 0, "opening_probability": 0.22},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.has_major_movement is True
        assert "major_movement_24h" in result.reasons
        assert result.top_mover_name == "Team A"

    def test_moderate_movement_detected(self):
        """Moderate 24h probability changes are flagged."""
        outcomes = [
            {"name": "Team A", "probability": 0.25, "probability_change_24h": 0.03,
             "rank": 1, "rank_change_24h": 0, "opening_probability": 0.22},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.has_moderate_movement is True
        assert "moderate_movement_24h" in result.reasons

    def test_leader_change_detected(self):
        """When the #1 rank has changed, it's detected."""
        outcomes = [
            {"name": "Team B", "probability": 0.30, "probability_change_24h": 0.10,
             "rank": 1, "rank_change_24h": 2, "opening_probability": 0.20},
            {"name": "Team A", "probability": 0.28, "probability_change_24h": -0.05,
             "rank": 2, "rank_change_24h": -1, "opening_probability": 0.33},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.leader_changed is True
        assert result.primary_reason == "New favorite"

    def test_rank_shakeup_with_multiple_changes(self):
        """Multiple rank changes in top 5 = shakeup."""
        outcomes = [
            {"name": "A", "probability": 0.30, "probability_change_24h": 0.01,
             "rank": 1, "rank_change_24h": 2, "opening_probability": 0.29},
            {"name": "B", "probability": 0.25, "probability_change_24h": 0.01,
             "rank": 2, "rank_change_24h": -1, "opening_probability": 0.24},
            {"name": "C", "probability": 0.20, "probability_change_24h": 0.01,
             "rank": 3, "rank_change_24h": 1, "opening_probability": 0.19},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.has_rank_shakeup is True

    def test_resolving_soon_7d(self):
        """Markets resolving within 7 days set the flag (scored via the blend)."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        resolution = now + timedelta(days=5)
        result = compute_futures_highlight(resolution_date=resolution, now=now)
        assert result.flags.is_resolving_soon is True
        # #141/Item 2: resolution-proximity's SINGLE HOME is the interestingness
        # blend now, so the additive "resolving_soon_*" reason/score are gone.
        assert "resolving_soon_7d" not in result.reasons
        assert "resolving_soon_30d" not in result.reasons

    def test_resolving_soon_30d(self):
        """Markets resolving within 30 days set the flag (scored via the blend)."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        resolution = now + timedelta(days=20)
        result = compute_futures_highlight(resolution_date=resolution, now=now)
        assert result.flags.is_resolving_soon is True
        assert "resolving_soon_30d" not in result.reasons

    def test_micro_bet_penalty_retained(self):
        """Daily-resolving micro-bets keep the distinct suppression penalty."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        result = compute_futures_highlight(
            resolution_date=now + timedelta(hours=12), now=now
        )
        assert "micro_bet" in result.reasons

    def test_multi_source_flag_no_additive_double_count(self):
        """2+ sources set the flag; the additive bonus is removed (#141/Item 2).

        Source COUNT is scored once, in the interestingness blend. The additive
        term is gone, so the raw highlight score no longer differs by count.
        """
        single = compute_futures_highlight(source_count=1)
        multi = compute_futures_highlight(source_count=3)
        assert multi.flags.has_multi_source is True
        assert single.flags.has_multi_source is False
        assert "multi_source" in multi.reasons
        assert multi.score == single.score  # no additive difference

    def test_source_divergence(self):
        """Sources disagreeing by >5% is flagged (distinct signal, kept additive)."""
        result = compute_futures_highlight(
            source_count=2,
            max_source_divergence=0.08,
        )
        assert result.flags.has_source_divergence is True
        assert "source_divergence" in result.reasons

    def test_high_volume_flag_no_additive_double_count(self):
        """Volume MAGNITUDE sets flags/reasons but no additive score (#141/Item 2).

        24h volume magnitude is scored once, in the interestingness blend.
        """
        no_vol = compute_futures_highlight(market_tier=1)
        high_vol = compute_futures_highlight(market_tier=1, volume_24h=100_000)
        mod_vol = compute_futures_highlight(market_tier=1, volume_24h=10_000)
        low_vol = compute_futures_highlight(market_tier=1, volume_24h=100)
        # Flags + reasons preserved for display/tags
        assert high_vol.flags.has_high_volume is True
        assert low_vol.flags.has_high_volume is False
        assert "high_volume" in high_vol.reasons
        assert "moderate_volume" in mod_vol.reasons
        # But no additive score difference (magnitude lives in the blend)
        assert high_vol.score == mod_vol.score == low_vol.score == no_vol.score

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        # Create a scenario with everything interesting
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        outcomes = [
            {"name": "A", "probability": 0.30, "probability_change_24h": 0.15,
             "rank": 1, "rank_change_24h": 3, "opening_probability": 0.15},
            {"name": "B", "probability": 0.25, "probability_change_24h": -0.10,
             "rank": 2, "rank_change_24h": -2, "opening_probability": 0.35},
            {"name": "C", "probability": 0.20, "probability_change_24h": 0.05,
             "rank": 3, "rank_change_24h": 1, "opening_probability": 0.15},
        ]
        result = compute_futures_highlight(
            market_tier=1,
            sport_category="basketball",
            resolution_date=now + timedelta(days=3),
            outcomes=outcomes,
            source_count=3,
            max_source_divergence=0.10,
            now=now,
        )
        assert result.score <= 100

    def test_combined_scoring(self):
        """Test a realistic championship market scenario."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        outcomes = [
            {"name": "Celtics", "probability": 0.22, "probability_change_24h": -0.05,
             "rank": 1, "rank_change_24h": 0, "opening_probability": 0.27},
            {"name": "Thunder", "probability": 0.18, "probability_change_24h": 0.03,
             "rank": 2, "rank_change_24h": 1, "opening_probability": 0.15},
        ]
        result = compute_futures_highlight(
            market_tier=1,
            sport_category="basketball",
            outcomes=outcomes,
            source_count=2,
            now=now,
        )
        # tier 1 + major league base (movement & multi-source now score via the
        # blend, not additively — #141/Item 2). Flags/reasons still fire.
        assert result.score >= 40
        assert result.flags.has_major_movement is True
        assert result.flags.has_multi_source is True


class TestScoreAnatomy:
    """Uncapped raw_score exposure, curation-before-cap, single election penalty."""

    def test_raw_score_exposed_and_capped_display(self):
        """raw_score keeps the uncapped total; score is capped at 98."""
        result = compute_futures_highlight(market_tier=1)
        assert result.raw_score == result.score  # small score: equal
        # A high-signal card whose raw exceeds 98 keeps the uncapped raw.
        big = compute_futures_highlight(
            market_tier=1,
            sport_category="politics",
            market_name="US presidential election winner",
            curation_score_adj=80,
        )
        assert big.score == 98
        assert big.raw_score > 98

    def test_curation_applied_before_cap(self):
        """curation_score_adj participates in raw_score (not escaping the cap)."""
        base = compute_futures_highlight(market_tier=3, sport_category="tech")
        curated = compute_futures_highlight(
            market_tier=3, sport_category="tech", curation_score_adj=5
        )
        assert curated.raw_score == base.raw_score + 5
        assert "curation_adj:+5" in curated.reasons

    def test_election_penalty_applied_once(self):
        """foreign_local + non_major must not stack into a -60 double penalty."""
        result = compute_futures_highlight(
            sport_category="politics",
            market_name="Who will win the Andalusia regional election?",
        )
        # foreign_local fires; non_major is guarded off so only ONE -30 applies.
        assert "foreign_local_election" in result.reasons
        assert "non_major_election" not in result.reasons


class TestDeterministicFuturesHeadlines:
    """Focused coverage for deterministic futures card explanations."""

    def test_named_negative_mover_drives_highlight_and_headline(self):
        """The biggest absolute mover should keep the named outcome for display."""
        from app.utils.feed_reasons import generate_futures_headline

        result = compute_futures_highlight(
            market_tier=1,
            sport_category="football",
            market_name="NFL MVP",
            outcomes=[
                {
                    "name": "Patrick Mahomes",
                    "probability": 0.18,
                    "probability_change_24h": -0.07,
                    "rank": 2,
                    "rank_change_24h": 0,
                    "opening_probability": 0.24,
                },
                {
                    "name": "Josh Allen",
                    "probability": 0.24,
                    "probability_change_24h": 0.03,
                    "rank": 1,
                    "rank_change_24h": 0,
                    "opening_probability": 0.20,
                },
            ],
        )

        assert result.flags.has_major_movement is True
        assert result.primary_reason == "Big odds movement"
        assert result.top_mover_name == "Patrick Mahomes"
        assert result.top_mover_change == 0.07

        headline = generate_futures_headline(
            result.reasons,
            top_mover_name=result.top_mover_name,
            top_mover_change=-0.07,
        )
        assert headline == "Patrick Mahomes down 7.0 points today"

    def test_binary_yes_mover_is_humanized_before_headline(self):
        """Binary futures should name the subject, not the raw Yes/No side."""
        from app.utils.feed_reasons import (
            generate_futures_headline,
            generate_futures_reason,
            humanize_binary_outcome_name,
        )

        market_name = "Will Anthropic IPO before OpenAI?"
        result = compute_futures_highlight(
            market_tier=3,
            sport_category="tech",
            market_name=market_name,
            outcomes=[
                {
                    "name": "Yes",
                    "probability": 0.56,
                    "probability_change_24h": 0.08,
                    "rank": 1,
                    "rank_change_24h": 0,
                    "opening_probability": 0.48,
                },
                {
                    "name": "No",
                    "probability": 0.44,
                    "probability_change_24h": -0.08,
                    "rank": 2,
                    "rank_change_24h": 0,
                    "opening_probability": 0.52,
                },
            ],
        )

        assert result.top_mover_name == "Yes"
        display_mover = humanize_binary_outcome_name(result.top_mover_name, market_name)
        assert display_mover == "Anthropic"

        headline = generate_futures_headline(
            result.reasons,
            top_mover_name=display_mover,
            top_mover_change=0.08,
        )
        reason = generate_futures_reason(
            market_name,
            result.reasons,
            top_mover_name=display_mover,
            top_mover_change=0.08,
        )
        assert headline == "Anthropic up 8.0 points today"
        assert reason == (
            "Anthropic moved up 8.0 points today in "
            "Will Anthropic IPO before OpenAI?"
        )

    def test_source_disagreement_headline_takes_priority_over_movement(self):
        """Cross-source disagreement should be the deterministic top story."""
        from app.utils.feed_reasons import generate_futures_headline, generate_futures_reason

        result = compute_futures_highlight(
            market_tier=1,
            sport_category="basketball",
            source_count=3,
            max_source_divergence=0.09,
            outcomes=[
                {
                    "name": "Thunder",
                    "probability": 0.31,
                    "probability_change_24h": 0.06,
                    "rank": 1,
                    "rank_change_24h": 0,
                    "opening_probability": 0.25,
                }
            ],
        )

        assert result.flags.has_source_divergence is True
        assert result.flags.has_major_movement is True
        assert result.primary_reason == "Sources disagree"

        headline = generate_futures_headline(
            result.reasons,
            leader_name="Thunder",
            leader_probability=0.31,
            source_count=3,
        )
        reason = generate_futures_reason(
            "NBA Championship",
            result.reasons,
            leader_name="Thunder",
            leader_probability=0.31,
            source_count=3,
        )
        assert headline == "Sources disagree (3)"
        assert reason == "3 sources disagree, but Thunder leads NBA Championship at 31%"

    def test_opening_probability_surprise_gets_named_headline(self):
        """Opening-line surprises should produce specific deterministic copy."""
        from app.utils.feed_reasons import generate_futures_headline, generate_futures_reason

        result = compute_futures_highlight(
            market_tier=3,
            sport_category="tech",
            market_name="Will OpenAI release GPT-5 before July?",
            outcomes=[
                {
                    "name": "Yes",
                    "probability": 0.62,
                    "probability_change_24h": None,
                    "rank": 1,
                    "rank_change_24h": 0,
                    "opening_probability": 0.35,
                }
            ],
        )

        assert "major_surprise" in result.reasons
        assert result.primary_reason == "Big shift from opening"

        headline = generate_futures_headline(
            result.reasons,
            top_surprise_name="OpenAI release",
            top_surprise_change=0.27,
        )
        reason = generate_futures_reason(
            "Will OpenAI release GPT-5 before July?",
            result.reasons,
            top_surprise_name="OpenAI release",
            top_surprise_change=0.27,
        )
        assert headline == "OpenAI release up 27.0 points from opening"
        assert reason == (
            "OpenAI release moved up 27.0 points from opening in "
            "Will OpenAI release GPT-5 before July?"
        )

    def test_past_resolution_penalty_removed(self):
        """#141/Item 3: the dead 'stale_past_resolution' penalty is gone.

        Past-resolution markets are excluded by the feed's SQL/eligibility gates
        before scoring, so the branch never fired. It is removed — a past
        resolution date no longer emits the reason or the -30 penalty.
        """
        now = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
        result = compute_futures_highlight(
            market_tier=5,
            sport_category="weather",
            market_name="Temperature in NYC on May 16",
            resolution_date=now - timedelta(days=1),
            now=now,
        )
        assert "stale_past_resolution" not in result.reasons

    def test_boring_pattern_does_not_get_compelling_or_primary_reason(self):
        """Boring social-count buckets should be flagged without a headline hook."""
        result = compute_futures_highlight(
            market_tier=5,
            sport_category="culture",
            market_name='Will Trump post "tariff" this week on Truth?',
            outcomes=[
                {
                    "name": "Yes",
                    "probability": 0.51,
                    "probability_change_24h": None,
                    "rank": 1,
                    "rank_change_24h": 0,
                    "opening_probability": 0.50,
                }
            ],
        )

        assert "boring_pattern" in result.reasons
        assert not any(reason.startswith("compelling") for reason in result.reasons)
        assert result.primary_reason is None

    def test_non_major_election_gets_foreign_local_penalty(self):
        result = compute_futures_highlight(
            sport_category="politics",
            market_name="Who will win the Andalusia regional election?",
        )

        assert "foreign_local_election" in result.reasons
        assert result.score < 50

    def test_major_election_avoids_foreign_local_penalty(self):
        result = compute_futures_highlight(
            sport_category="politics",
            market_name="Who will win the 2028 US presidential election?",
        )

        assert "foreign_local_election" not in result.reasons


class TestMinorLeagueDetection:
    """Tests for minor league market detection and feed penalty."""

    def test_ahl_detected_as_minor(self):
        """AHL championship futures should be flagged as minor league."""
        assert is_minor_league_market("AHL Calder Cup Winner") is True

    def test_echl_detected_as_minor(self):
        assert is_minor_league_market("ECHL Kelly Cup Winner") is True

    def test_khl_detected_as_minor(self):
        assert is_minor_league_market("KHL Gagarin Cup") is True

    def test_ligue_2_detected_as_minor(self):
        assert is_minor_league_market("Ligue 2 Winner 2025-26") is True

    def test_serie_b_detected_as_minor(self):
        assert is_minor_league_market("Serie B Winner") is True

    def test_efl_championship_detected_as_minor(self):
        """English EFL Championship (tier 2) is minor for our purposes."""
        assert is_minor_league_market("EFL Championship Winner") is True

    def test_g_league_detected_as_minor(self):
        assert is_minor_league_market("NBA G-League Winner") is True

    def test_nhl_not_minor(self):
        """NHL Stanley Cup should NOT be detected as minor."""
        assert is_minor_league_market("NHL Stanley Cup Winner") is False

    def test_nba_championship_not_minor(self):
        assert is_minor_league_market("NBA Championship 2025-26") is False

    def test_nfl_mvp_not_minor(self):
        assert is_minor_league_market("NFL MVP 2025-26") is False

    def test_epl_not_minor(self):
        assert is_minor_league_market("English Premier League Winner") is False

    def test_top_tier_soccer_allowlist(self):
        assert is_top_tier_soccer_market("Premier League winner") is True
        assert is_top_tier_soccer_market("UEFA Champions League winner") is True
        assert is_top_tier_soccer_market("Chilean Primera Division winner") is False

    def test_minor_league_gets_score_penalty(self):
        """Minor league futures should score significantly lower."""
        nhl = compute_futures_highlight(
            market_tier=1, sport_category="hockey",
            market_name="NHL Stanley Cup Winner",
        )
        ahl = compute_futures_highlight(
            market_tier=1, sport_category="hockey",
            market_name="AHL Calder Cup Winner",
        )
        assert nhl.score > ahl.score
        assert "minor_league" in ahl.reasons
        assert "major_league" in nhl.reasons

    def test_minor_league_hockey_loses_major_bonus(self):
        """AHL gets penalty, not major_league bonus, even though hockey is tier 1."""
        result = compute_futures_highlight(
            market_tier=1, sport_category="hockey",
            market_name="AHL Calder Cup Winner",
        )
        assert "major_league" not in result.reasons
        assert "minor_league" in result.reasons
        # category_base_hockey (18.5) + tier_1 (15) + minor penalty (-15) = 18.5
        assert result.score <= 20

    def test_minor_league_below_anonymous_threshold(self):
        """A minor league championship resolving soon should still score low."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        result = compute_futures_highlight(
            market_tier=1,
            sport_category="hockey",
            resolution_date=now + timedelta(days=5),
            source_count=2,
            now=now,
            market_name="AHL Calder Cup Winner",
        )
        # category_base (18.5) + tier 1 (15) + minor penalty (-15) + resolving_soon (15) + multi_source (10) = 43.5
        # Still much lower than NHL championship (55+)
        assert result.score <= 45

    def test_obscure_soccer_gets_penalty_without_minor_pattern(self):
        top_tier = compute_futures_highlight(
            market_tier=1,
            sport_category="soccer",
            market_name="UEFA Champions League Winner",
        )
        obscure = compute_futures_highlight(
            market_tier=1,
            sport_category="soccer",
            market_name="Chilean Primera Division Winner",
        )

        assert "secondary_league" in top_tier.reasons
        assert "obscure_soccer" in obscure.reasons
        assert "secondary_league" not in obscure.reasons
        assert obscure.score < top_tier.score


class TestFeedReasons:
    """Tests for feed reason generation."""

    def test_event_upset_reason(self):
        from app.utils.feed_reasons import generate_event_reason

        reason = generate_event_reason(
            home_team="Lakers",
            away_team="Celtics",
            status="completed",
            highlight_reasons=["upset", "recent_finish"],
            home_score=95,
            away_score=110,
            opening_home_prob=0.65,
        )
        # Away team (Celtics) won → winner_opening_prob = 1 - 0.65 = 0.35
        assert "35%" in reason
        assert "underdog" in reason.lower()

    def test_event_live_close_reason(self):
        from app.utils.feed_reasons import generate_event_reason

        reason = generate_event_reason(
            home_team="Lakers",
            away_team="Celtics",
            status="live",
            highlight_reasons=["live", "very_close"],
            home_probability=0.48,
            away_probability=0.52,
            home_score=88,
            away_score=90,
        )
        assert "even" in reason.lower()

    def test_futures_leader_change_reason(self):
        from app.utils.feed_reasons import generate_futures_reason

        reason = generate_futures_reason(
            market_name="NBA Championship 2025-26",
            highlight_reasons=["leader_change"],
            leader_name="Thunder",
            leader_probability=0.22,
        )
        assert "Thunder" in reason
        assert "favorite" in reason.lower() or "New" in reason

    def test_futures_major_movement_reason(self):
        from app.utils.feed_reasons import generate_futures_reason

        reason = generate_futures_reason(
            market_name="NFL MVP",
            highlight_reasons=["major_movement_24h"],
            top_mover_name="Patrick Mahomes",
            top_mover_change=0.08,
        )
        assert "Mahomes" in reason
        assert "8" in reason  # 8% movement

    def test_futures_fallback_reason(self):
        from app.utils.feed_reasons import generate_futures_reason

        reason = generate_futures_reason(
            market_name="NBA Championship",
            highlight_reasons=[],
            leader_name="Celtics",
            leader_probability=0.22,
        )
        assert "Celtics" in reason
        assert "22%" in reason
