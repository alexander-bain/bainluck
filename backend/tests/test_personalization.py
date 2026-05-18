"""Tests for personalization scoring module."""

import pytest
from app.utils.personalization import (
    PersonalizationContext,
    PersonalizationResult,
    compute_event_multiplier,
    compute_futures_multiplier,
    _match_sport_affinity,
    FOLLOW_BONUS,
    LOCAL_BONUS,
    ALMA_MATER_BONUS,
    RIVAL_LOSING_BONUS,
    RIVAL_PLAYING_BONUS,
    PINNED_BONUS,
    MINOR_PRO_PENALTY,
    ROSTER_PLAYER_BONUS,
    HIGH_AFFINITY_BONUS,
    LOW_AFFINITY_PENALTY,
    NAH_AFFINITY_PENALTY,
    NAH_AFFINITY_THRESHOLD,
    CATEGORY_INTEREST_MAX_BONUS,
    CATEGORY_DISMISS_MAX_PENALTY,
    CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY,
    CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY,
    FEATURE_INTEREST_MAX_BONUS,
    FEATURE_DISLIKE_MAX_PENALTY,
    MIN_MULTIPLIER,
    MAX_MULTIPLIER,
)


# ============================================================================
# Context helpers
# ============================================================================

def _anonymous_ctx() -> PersonalizationContext:
    """Anonymous (unauthenticated) context."""
    return PersonalizationContext()


def _anonymous_session_ctx(
    discover_category_affinities=None,
    discover_category_negative_counts=None,
    discover_feature_affinities=None,
) -> PersonalizationContext:
    """Anonymous context with session-derived Discover behavior."""
    return PersonalizationContext(
        discover_category_affinities=discover_category_affinities or {},
        discover_category_negative_counts=discover_category_negative_counts or {},
        discover_feature_affinities=discover_feature_affinities or {},
        is_authenticated=False,
    )


def _basic_ctx(
    team_relations=None,
    team_weights=None,
    sport_affinities=None,
    pinned_event_ids=None,
    pinned_futures_ids=None,
    roster_player_names=None,
    discover_category_affinities=None,
    discover_category_negative_counts=None,
    discover_feature_affinities=None,
) -> PersonalizationContext:
    """Authenticated context with optional overrides."""
    return PersonalizationContext(
        team_relations=team_relations or {},
        team_weights=team_weights or {},
        sport_affinities=sport_affinities or {},
        pinned_event_ids=pinned_event_ids or set(),
        pinned_futures_ids=pinned_futures_ids or set(),
        roster_player_names=roster_player_names or set(),
        discover_category_affinities=discover_category_affinities or {},
        discover_category_negative_counts=discover_category_negative_counts or {},
        discover_feature_affinities=discover_feature_affinities or {},
        is_authenticated=True,
    )


# ============================================================================
# Anonymous user tests
# ============================================================================

class TestAnonymousUser:
    """Anonymous users get 1.0x unless there are session Discover signals."""

    def test_anonymous_event_returns_1x(self):
        ctx = _anonymous_ctx()
        result = compute_event_multiplier(ctx, home_team_id=1, away_team_id=2, sport_key="basketball_nba")
        assert result.multiplier == 1.0
        assert not result.is_personalized
        assert result.reasons == []

    def test_anonymous_futures_returns_1x(self):
        ctx = _anonymous_ctx()
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[1, 2, 3])
        assert result.multiplier == 1.0
        assert not result.is_personalized

    def test_anonymous_ignores_everything(self):
        """Even if anonymous context somehow had data, unauthenticated = 1.0x."""
        ctx = PersonalizationContext(
            team_relations={1: {"follow"}},
            sport_affinities={"basketball_nba": 1.0},
            is_authenticated=False,
        )
        result = compute_event_multiplier(ctx, home_team_id=1, away_team_id=2, sport_key="basketball_nba")
        assert result.multiplier == 1.0

    def test_anonymous_session_category_signal_personalizes_futures(self):
        """Anonymous sessions can still get recent Discover category ranking."""
        ctx = _anonymous_session_ctx(discover_category_affinities={"tech": 0.12})
        result = compute_futures_multiplier(ctx, sport_category="tech", outcome_team_ids=[])
        assert result.multiplier == pytest.approx(1.12)
        assert result.is_personalized
        assert "discover_interest:0.12" in result.reasons

    def test_anonymous_session_feature_signal_personalizes_events(self):
        """Anonymous session likes/unlikes can rank matching event features."""
        ctx = _anonymous_session_ctx(discover_feature_affinities={"region:massachusetts": -0.07})
        result = compute_event_multiplier(
            ctx,
            home_team_id=None,
            away_team_id=None,
            sport_key=None,
            feature_tokens=["region:massachusetts"],
        )
        assert result.multiplier == pytest.approx(0.93)
        assert result.is_personalized
        assert "discover_feature_dislike:region:massachusetts:-0.07" in result.reasons


# ============================================================================
# Team relationship tests (events)
# ============================================================================

class TestEventTeamRelationships:
    """Test team relationship bonuses for events."""

    def test_follow_bonus(self):
        ctx = _basic_ctx(team_relations={10: {"follow"}}, team_weights={10: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS)
        assert result.is_personalized
        assert any("your_team" in r for r in result.reasons)

    def test_follow_bonus_with_weight(self):
        """Weight of 0.5 should halve the follow bonus."""
        ctx = _basic_ctx(team_relations={10: {"follow"}}, team_weights={10: 0.5})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS * 0.5)

    def test_away_team_follow(self):
        """Following the away team should also boost."""
        ctx = _basic_ctx(team_relations={20: {"follow"}}, team_weights={20: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS)

    def test_local_team_bonus(self):
        ctx = _basic_ctx(team_relations={10: {"local"}}, team_weights={10: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + LOCAL_BONUS)
        assert any("local_team" in r for r in result.reasons)

    def test_alma_mater_bonus(self):
        ctx = _basic_ctx(team_relations={10: {"alma_mater"}}, team_weights={10: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_ncaab")
        assert result.multiplier == pytest.approx(1.0 + ALMA_MATER_BONUS)
        assert any("alma_mater" in r for r in result.reasons)

    def test_follow_and_local_stack(self):
        """A team can be both followed AND local — bonuses stack."""
        ctx = _basic_ctx(team_relations={10: {"follow", "local"}}, team_weights={10: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS + LOCAL_BONUS)

    def test_both_teams_followed(self):
        """Following both teams in a game doubles the team bonus."""
        ctx = _basic_ctx(
            team_relations={10: {"follow"}, 20: {"follow"}},
            team_weights={10: 1.0, 20: 1.0},
        )
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + 2 * FOLLOW_BONUS)

    def test_no_matching_teams(self):
        """User follows teams that aren't in this event."""
        ctx = _basic_ctx(team_relations={99: {"follow"}}, team_weights={99: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == 1.0
        assert not result.is_personalized

    def test_none_team_ids(self):
        """Events without team IDs shouldn't crash."""
        ctx = _basic_ctx(team_relations={10: {"follow"}}, team_weights={10: 1.0})
        result = compute_event_multiplier(ctx, home_team_id=None, away_team_id=None, sport_key="basketball_nba")
        assert result.multiplier == 1.0


# ============================================================================
# Rival schadenfreude tests
# ============================================================================

class TestRivalSchadenfreude:
    """Test rival-specific scoring behavior."""

    def test_rival_playing_bonus(self):
        """Rival playing but not losing = smaller bonus."""
        ctx = _basic_ctx(team_relations={20: {"rival"}})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba",
            home_score=None, away_score=None,
        )
        assert result.multiplier == pytest.approx(1.0 + RIVAL_PLAYING_BONUS)
        assert any("rival_playing" in r for r in result.reasons)

    def test_rival_losing_home(self):
        """Home team is rival and losing → schadenfreude boost."""
        ctx = _basic_ctx(team_relations={10: {"rival"}})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba",
            home_score=80, away_score=95,
        )
        assert result.multiplier == pytest.approx(1.0 + RIVAL_LOSING_BONUS)
        assert any("rival_losing" in r for r in result.reasons)

    def test_rival_losing_away(self):
        """Away team is rival and losing → schadenfreude boost."""
        ctx = _basic_ctx(team_relations={20: {"rival"}})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba",
            home_score=95, away_score=80,
        )
        assert result.multiplier == pytest.approx(1.0 + RIVAL_LOSING_BONUS)

    def test_rival_winning_no_schadenfreude(self):
        """Rival winning = just the playing bonus, not losing bonus."""
        ctx = _basic_ctx(team_relations={10: {"rival"}})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba",
            home_score=95, away_score=80,
        )
        assert result.multiplier == pytest.approx(1.0 + RIVAL_PLAYING_BONUS)

    def test_rival_tied_no_schadenfreude(self):
        """Tied game = playing bonus only."""
        ctx = _basic_ctx(team_relations={10: {"rival"}})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba",
            home_score=85, away_score=85,
        )
        assert result.multiplier == pytest.approx(1.0 + RIVAL_PLAYING_BONUS)


# ============================================================================
# Sport affinity tests
# ============================================================================

class TestSportAffinity:
    """Test sport-based score adjustments."""

    def test_high_affinity_boost(self):
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 0.8})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)
        assert any("sport_boost" in r for r in result.reasons)

    def test_low_affinity_suppression(self):
        ctx = _basic_ctx(sport_affinities={"baseball_mlb": 0.1})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="baseball_mlb")
        assert result.multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)
        assert any("sport_suppress" in r for r in result.reasons)

    def test_medium_affinity_no_change(self):
        """Affinity between thresholds = no adjustment."""
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 0.35})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == 1.0

    def test_no_affinity_for_sport(self):
        """Sport not in user's affinities = implicit 'Nah' (suppressed).
        When a user has set sport affinities (completed onboarding) but
        a sport isn't in their preferences, it means they didn't express
        interest — treat as implicit 'Nah'."""
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="icehockey_nhl")
        assert result.multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
        assert "sport_nah" in result.reasons[0]

    def test_empty_affinities(self):
        ctx = _basic_ctx(sport_affinities={})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == 1.0

    def test_zero_affinity_strong_suppress(self):
        """Explicit 0.0 affinity ('Nah') should get strong suppression."""
        ctx = _basic_ctx(sport_affinities={"icehockey_nhl": 0.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="icehockey_nhl")
        assert result.multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
        assert any("sport_nah" in r for r in result.reasons)

    def test_if_wild_affinity_mild_suppress(self):
        """0.1 affinity ('If wild') should get mild suppression, not 'Nah' penalty."""
        ctx = _basic_ctx(sport_affinities={"icehockey_nhl": 0.1})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="icehockey_nhl")
        assert result.multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)
        assert any("sport_suppress" in r for r in result.reasons)

    def test_nah_stronger_than_if_wild(self):
        """'Nah' (0.0) penalty should be stronger than 'If wild' (0.1)."""
        assert NAH_AFFINITY_PENALTY < LOW_AFFINITY_PENALTY


# ============================================================================
# Pinned item tests
# ============================================================================

class TestPinnedItems:
    """Test pin-based boosting."""

    def test_pinned_event_boost(self):
        ctx = _basic_ctx(pinned_event_ids={42})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba", event_id=42)
        assert result.multiplier == pytest.approx(1.0 + PINNED_BONUS)
        assert any("pinned" in r for r in result.reasons)

    def test_unpinned_event_no_boost(self):
        ctx = _basic_ctx(pinned_event_ids={42})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba", event_id=99)
        assert result.multiplier == 1.0

    def test_pinned_futures_boost(self):
        ctx = _basic_ctx(pinned_futures_ids={55})
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[], futures_market_id=55)
        assert result.multiplier == pytest.approx(1.0 + PINNED_BONUS)

    def test_pinned_event_stacks_with_team(self):
        """Pinned + followed team = both bonuses."""
        ctx = _basic_ctx(
            team_relations={10: {"follow"}},
            team_weights={10: 1.0},
            pinned_event_ids={42},
        )
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba", event_id=42)
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS + PINNED_BONUS)


# ============================================================================
# Multiplier clamping tests
# ============================================================================

class TestMultiplierClamping:
    """Test that multiplier stays within [MIN, MAX] bounds."""

    def test_max_clamping(self):
        """Stacking many bonuses should clamp at MAX_MULTIPLIER."""
        ctx = _basic_ctx(
            team_relations={10: {"follow", "local", "alma_mater"}, 20: {"rival"}},
            team_weights={10: 1.0, 20: 1.0},
            sport_affinities={"basketball_nba": 1.0},
            pinned_event_ids={42},
        )
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba",
            event_id=42, home_score=80, away_score=95,
        )
        assert result.multiplier == MAX_MULTIPLIER  # 2.0
        assert result.is_personalized

    def test_min_clamping(self):
        """Low sport affinity alone should clamp at MIN_MULTIPLIER."""
        ctx = _basic_ctx(sport_affinities={"baseball_mlb": 0.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="baseball_mlb")
        assert result.multiplier >= MIN_MULTIPLIER


# ============================================================================
# Futures personalization tests
# ============================================================================

class TestFuturesPersonalization:
    """Test futures-specific personalization."""

    def test_followed_team_in_outcomes(self):
        ctx = _basic_ctx(team_relations={10: {"follow"}}, team_weights={10: 1.0})
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[10, 20, 30])
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS)
        assert any("your_team_futures" in r for r in result.reasons)

    def test_rival_team_in_outcomes(self):
        ctx = _basic_ctx(team_relations={20: {"rival"}})
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[10, 20, 30])
        assert result.multiplier == pytest.approx(1.0 + RIVAL_PLAYING_BONUS)

    def test_no_matching_teams_in_outcomes(self):
        ctx = _basic_ctx(team_relations={99: {"follow"}}, team_weights={99: 1.0})
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[10, 20, 30])
        assert result.multiplier == 1.0

    def test_futures_sport_affinity(self):
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 0.9})
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[])
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)

    def test_futures_low_sport_affinity(self):
        ctx = _basic_ctx(sport_affinities={"baseball_mlb": 0.1})
        result = compute_futures_multiplier(ctx, sport_category="baseball", outcome_team_ids=[])
        assert result.multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)

    def test_futures_follow_only_counted_once(self):
        """Multiple outcomes from the same followed team shouldn't stack."""
        ctx = _basic_ctx(
            team_relations={10: {"follow"}, 20: {"follow"}},
            team_weights={10: 1.0, 20: 1.0},
        )
        # Two different followed teams in outcomes — follow bonus counted once
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[10, 20, 30])
        # Both teams count since they're different teams, but each only once
        # Actually: the code only flags matched_follow once, so only 1x FOLLOW_BONUS
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS)

    def test_futures_empty_outcome_team_ids(self):
        """Markets with no team links shouldn't crash."""
        ctx = _basic_ctx(team_relations={10: {"follow"}}, team_weights={10: 1.0})
        result = compute_futures_multiplier(ctx, sport_category="basketball", outcome_team_ids=[])
        assert result.multiplier == 1.0
        assert not result.is_personalized


# ============================================================================
# Sport affinity matching tests
# ============================================================================

class TestSportAffinityMatching:
    """Test the _match_sport_affinity helper for fuzzy category → key matching."""

    def test_basketball_match(self):
        affinities = {"basketball_nba": 0.8, "basketball_ncaab": 0.5}
        assert _match_sport_affinity("basketball", affinities) == 0.8  # Takes highest

    def test_football_match_american(self):
        affinities = {"americanfootball_nfl": 0.9}
        assert _match_sport_affinity("football", affinities) == 0.9

    def test_hockey_match(self):
        affinities = {"icehockey_nhl": 0.7}
        assert _match_sport_affinity("hockey", affinities) == 0.7

    def test_soccer_match(self):
        affinities = {"soccer_epl": 0.4, "soccer_usa_mls": 0.6}
        assert _match_sport_affinity("soccer", affinities) == 0.6

    def test_mma_match(self):
        affinities = {"mma_mixed_martial_arts": 0.5}
        assert _match_sport_affinity("mma", affinities) == 0.5

    def test_no_match(self):
        affinities = {"basketball_nba": 0.8}
        assert _match_sport_affinity("golf", affinities) is None

    def test_empty_category(self):
        assert _match_sport_affinity("", {"basketball_nba": 0.8}) is None

    def test_none_category(self):
        assert _match_sport_affinity(None, {"basketball_nba": 0.8}) is None

    def test_empty_affinities(self):
        assert _match_sport_affinity("basketball", {}) is None

    def test_esports_match(self):
        affinities = {"esports_lol": 0.0, "esports_csgo": 0.0}
        assert _match_sport_affinity("esports", affinities) == 0.0


# ============================================================================
# Combined stacking tests
# ============================================================================

class TestCombinedStacking:
    """Test realistic multi-factor scenarios."""

    def test_celtics_fan_watching_celtics(self):
        """Alex following Celtics, watching them play at home, NBA is high affinity, game is pinned."""
        ctx = _basic_ctx(
            team_relations={10: {"follow", "local"}},  # Celtics: followed + local (Bostonian)
            team_weights={10: 1.0},
            sport_affinities={"basketball_nba": 1.0},
            pinned_event_ids={42},
        )
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba", event_id=42,
        )
        expected = 1.0 + FOLLOW_BONUS + LOCAL_BONUS + HIGH_AFFINITY_BONUS + PINNED_BONUS
        assert result.multiplier == pytest.approx(min(MAX_MULTIPLIER, expected))

    def test_rival_losing_while_low_affinity(self):
        """Rival losing in a sport user doesn't care about — net positive."""
        ctx = _basic_ctx(
            team_relations={20: {"rival"}},
            sport_affinities={"baseball_mlb": 0.1},  # low affinity
        )
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20, sport_key="baseball_mlb",
            home_score=8, away_score=3,  # rival (away) is losing
        )
        expected = 1.0 + RIVAL_LOSING_BONUS + LOW_AFFINITY_PENALTY
        assert result.multiplier == pytest.approx(expected)

    def test_no_preferences_authenticated(self):
        """Logged in but no favorites or affinities = pure 1.0x."""
        ctx = _basic_ctx()
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == 1.0
        assert not result.is_personalized


# ============================================================================
# Minor pro league suppression tests
# ============================================================================

class TestMinorProSuppression:
    """Test minor pro league suppression for events."""

    def test_minor_pro_no_affinity_suppressed(self):
        """Minor pro league with no team/sport match gets implicit 'Nah' penalty.
        The sport_nah penalty (-0.6) is stronger than minor_pro (-0.2),
        so sport_nah takes precedence when the user has affinities set."""
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 1.0})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="americanfootball_xfl",
        )
        assert result.multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
        assert any("sport_nah" in r for r in result.reasons)

    def test_minor_pro_with_team_follow_not_suppressed(self):
        """Minor pro league with a followed team gets NO penalty."""
        ctx = _basic_ctx(
            team_relations={10: {"follow"}},
            team_weights={10: 1.0},
        )
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="americanfootball_cfl",
        )
        # Follow bonus applied, no minor pro penalty
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS)
        assert not any("minor_pro" in r for r in result.reasons)

    def test_minor_pro_with_sport_affinity_not_suppressed(self):
        """Minor pro league with sport affinity gets NO penalty."""
        ctx = _basic_ctx(sport_affinities={"americanfootball_xfl": 0.8})
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="americanfootball_xfl",
        )
        # Sport boost applied, no minor pro penalty
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)
        assert not any("minor_pro" in r for r in result.reasons)

    def test_non_minor_pro_no_suppression(self):
        """Major pro leagues don't get minor pro penalty."""
        ctx = _basic_ctx()
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="americanfootball_nfl",
        )
        assert result.multiplier == 1.0
        assert not any("minor_pro" in r for r in result.reasons)

    def test_college_league_no_suppression(self):
        """College leagues don't get minor pro penalty."""
        ctx = _basic_ctx()
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="basketball_ncaab",
        )
        assert result.multiplier == 1.0
        assert not any("minor_pro" in r for r in result.reasons)

    def test_minor_pro_cfl(self):
        """CFL gets suppressed when no match."""
        ctx = _basic_ctx()
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="americanfootball_cfl",
        )
        assert result.multiplier == pytest.approx(1.0 + MINOR_PRO_PENALTY)

    def test_minor_pro_ahl(self):
        """AHL gets suppressed when no match."""
        ctx = _basic_ctx()
        result = compute_event_multiplier(
            ctx, home_team_id=10, away_team_id=20,
            sport_key="icehockey_ahl",
        )
        assert result.multiplier == pytest.approx(1.0 + MINOR_PRO_PENALTY)


# ============================================================================
# Roster player matching tests (futures)
# ============================================================================

class TestRosterPlayerMatching:
    """Test roster player matching for futures personalization."""

    def test_roster_player_match_boosts(self):
        """Futures about a player on a followed team's roster gets bonus."""
        ctx = _basic_ctx(roster_player_names={"stefon diggs", "jalen hurts"})
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=["Will Stefon Diggs be suspended?"],
        )
        assert result.multiplier == pytest.approx(1.0 + ROSTER_PLAYER_BONUS)
        assert any("roster_player" in r for r in result.reasons)

    def test_roster_player_case_insensitive(self):
        """Roster matching is case-insensitive."""
        ctx = _basic_ctx(roster_player_names={"patrick mahomes"})
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=["Patrick Mahomes MVP"],
        )
        assert any("roster_player" in r for r in result.reasons)

    def test_roster_player_no_match(self):
        """No roster match = no bonus."""
        ctx = _basic_ctx(roster_player_names={"stefon diggs"})
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=["Tom Brady retirement odds"],
        )
        assert not any("roster_player" in r for r in result.reasons)

    def test_roster_player_stacks_with_team(self):
        """Roster player bonus stacks with team follow bonus."""
        ctx = _basic_ctx(
            team_relations={10: {"follow"}},
            team_weights={10: 1.0},
            roster_player_names={"stefon diggs"},
        )
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[10],
            outcome_names=["Will Stefon Diggs be suspended?"],
        )
        expected = 1.0 + FOLLOW_BONUS + ROSTER_PLAYER_BONUS
        assert result.multiplier == pytest.approx(expected)

    def test_roster_player_empty_names(self):
        """Empty outcome_names = no crash, no bonus."""
        ctx = _basic_ctx(roster_player_names={"stefon diggs"})
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=[],
        )
        assert not any("roster_player" in r for r in result.reasons)

    def test_roster_player_none_names(self):
        """None outcome_names = no crash, no bonus."""
        ctx = _basic_ctx(roster_player_names={"stefon diggs"})
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=None,
        )
        assert not any("roster_player" in r for r in result.reasons)

    def test_roster_player_no_roster_data(self):
        """No roster_player_names in context = no bonus."""
        ctx = _basic_ctx()
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=["Stefon Diggs MVP"],
        )
        assert not any("roster_player" in r for r in result.reasons)

    def test_roster_player_only_first_match(self):
        """Multiple outcomes matching roster = only one bonus."""
        ctx = _basic_ctx(roster_player_names={"stefon diggs", "jalen hurts"})
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            outcome_names=["Stefon Diggs suspension", "Jalen Hurts MVP"],
        )
        # Should only get one ROSTER_PLAYER_BONUS, not two
        assert result.multiplier == pytest.approx(1.0 + ROSTER_PLAYER_BONUS)


# ============================================================================
# Direct sport_key lookup for futures tests
# ============================================================================

class TestFuturesSportKeyLookup:
    """Test that futures prefers direct sport_key lookup over category substring."""

    def test_direct_sport_key_used(self):
        """When sport_key is provided, use direct lookup."""
        ctx = _basic_ctx(sport_affinities={
            "americanfootball_nfl": 1.0,
            "americanfootball_ncaaf": 0.0,
        })
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            sport_key="americanfootball_nfl",
        )
        # Direct lookup → 1.0 → HIGH_AFFINITY_BONUS
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)

    def test_direct_sport_key_suppresses_college(self):
        """College football market with low college affinity gets suppressed."""
        ctx = _basic_ctx(sport_affinities={
            "americanfootball_nfl": 1.0,
            "americanfootball_ncaaf": 0.1,
        })
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            sport_key="americanfootball_ncaaf",
        )
        # Direct lookup → 0.1 → LOW_AFFINITY_PENALTY
        assert result.multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)

    def test_falls_back_to_category_when_no_sport_key(self):
        """Without sport_key, falls back to category substring matching."""
        ctx = _basic_ctx(sport_affinities={
            "americanfootball_nfl": 1.0,
            "americanfootball_ncaaf": 0.1,
        })
        result = compute_futures_multiplier(
            ctx, sport_category="football",
            outcome_team_ids=[],
            sport_key=None,
        )
        # Category "football" substring matches both — takes max = 1.0
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)

    def test_direct_lookup_with_unknown_key(self):
        """Unknown sport_key falls back to category matching."""
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 0.8})
        result = compute_futures_multiplier(
            ctx, sport_category="basketball",
            outcome_team_ids=[],
            sport_key="basketball_obscure_league",
        )
        # sport_key "basketball_obscure_league" not in affinities
        # Falls back to category "basketball" → matches "basketball_nba" → 0.8
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)


# ============================================================================
# Discover interaction category affinity tests
# ============================================================================

class TestDiscoverCategoryAffinity:
    """Recent Discover behavior should add a small bounded category signal."""

    def test_futures_category_interest_boost(self):
        ctx = _basic_ctx(discover_category_affinities={"tech": 0.12})
        result = compute_futures_multiplier(ctx, sport_category="tech", outcome_team_ids=[])
        assert result.multiplier == pytest.approx(1.12)
        assert any("discover_interest" in r for r in result.reasons)

    def test_futures_category_dismiss_penalty(self):
        ctx = _basic_ctx(discover_category_affinities={"politics": -0.1})
        result = compute_futures_multiplier(ctx, sport_category="politics", outcome_team_ids=[])
        assert result.multiplier == pytest.approx(0.9)
        assert any("discover_dismiss" in r for r in result.reasons)

    def test_category_signal_is_capped(self):
        ctx = _basic_ctx(discover_category_affinities={"tech": 9.0, "politics": -9.0})
        tech = compute_futures_multiplier(ctx, sport_category="tech", outcome_team_ids=[])
        politics = compute_futures_multiplier(ctx, sport_category="politics", outcome_team_ids=[])
        assert tech.multiplier == pytest.approx(1.0 + CATEGORY_INTEREST_MAX_BONUS)
        assert politics.multiplier == pytest.approx(1.0 + CATEGORY_DISMISS_MAX_PENALTY)

    def test_five_negative_swipes_escalate_category_penalty(self):
        lower_count_ctx = _basic_ctx(
            discover_category_affinities={"politics": -0.10},
            discover_category_negative_counts={"politics": 4},
        )
        escalated_ctx = _basic_ctx(
            discover_category_affinities={"politics": -0.10},
            discover_category_negative_counts={"politics": 5},
        )

        lower_count = compute_futures_multiplier(
            lower_count_ctx,
            sport_category="politics",
            outcome_team_ids=[],
        )
        escalated = compute_futures_multiplier(
            escalated_ctx,
            sport_category="politics",
            outcome_team_ids=[],
        )

        assert lower_count.multiplier == pytest.approx(0.90)
        assert escalated.multiplier == pytest.approx(
            1.0 + CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY
        )
        assert escalated.multiplier < lower_count.multiplier
        assert escalated.multiplier >= MIN_MULTIPLIER

    def test_eight_negative_swipes_escalate_category_penalty_again(self):
        five_swipe_ctx = _basic_ctx(
            discover_category_affinities={"politics": CATEGORY_DISMISS_MAX_PENALTY},
            discover_category_negative_counts={"politics": 5},
        )
        eight_swipe_ctx = _basic_ctx(
            discover_category_affinities={"politics": CATEGORY_DISMISS_MAX_PENALTY},
            discover_category_negative_counts={"politics": 8},
        )

        five_swipes = compute_futures_multiplier(
            five_swipe_ctx,
            sport_category="politics",
            outcome_team_ids=[],
        )
        eight_swipes = compute_futures_multiplier(
            eight_swipe_ctx,
            sport_category="politics",
            outcome_team_ids=[],
        )

        assert five_swipes.multiplier == pytest.approx(
            1.0 + CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY
        )
        assert eight_swipes.multiplier == pytest.approx(
            1.0 + CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY
        )
        assert eight_swipes.multiplier < five_swipes.multiplier
        assert eight_swipes.multiplier >= MIN_MULTIPLIER

    def test_event_maps_sport_key_to_discover_category(self):
        ctx = _basic_ctx(discover_category_affinities={"basketball": 0.08})
        result = compute_event_multiplier(ctx, home_team_id=None, away_team_id=None, sport_key="basketball_nba")
        assert result.multiplier == pytest.approx(1.08)
        assert any("discover_interest" in r for r in result.reasons)

    def test_event_maps_americanfootball_to_football(self):
        ctx = _basic_ctx(discover_category_affinities={"football": 0.08})
        result = compute_event_multiplier(ctx, home_team_id=None, away_team_id=None, sport_key="americanfootball_nfl")
        assert result.multiplier == pytest.approx(1.08)

    def test_futures_feature_interest_boost(self):
        ctx = _basic_ctx(discover_feature_affinities={"archetype:culture_moment": 0.11})
        result = compute_futures_multiplier(
            ctx,
            sport_category="entertainment",
            outcome_team_ids=[],
            feature_tokens=["archetype:culture_moment"],
        )
        assert result.multiplier == pytest.approx(1.11)
        assert any("discover_feature_interest" in r for r in result.reasons)

    def test_futures_feature_dislike_penalty(self):
        ctx = _basic_ctx(discover_feature_affinities={"format:matchup": -0.08})
        result = compute_futures_multiplier(
            ctx,
            sport_category="soccer",
            outcome_team_ids=[],
            feature_tokens=["format:matchup"],
        )
        assert result.multiplier == pytest.approx(0.92)
        assert any("discover_feature_dislike" in r for r in result.reasons)

    def test_entity_like_boosts_matching_card_only(self):
        ctx = _basic_ctx(discover_feature_affinities={"entity:noah_kahan": 0.10})
        matching = compute_futures_multiplier(
            ctx,
            sport_category="entertainment",
            outcome_team_ids=[],
            feature_tokens=["entity:noah_kahan"],
        )
        unrelated = compute_futures_multiplier(
            ctx,
            sport_category="entertainment",
            outcome_team_ids=[],
            feature_tokens=["entity:taylor_swift"],
        )
        assert matching.multiplier == pytest.approx(1.10)
        assert "discover_feature_interest:entity:noah_kahan:0.10" in matching.reasons
        assert unrelated.multiplier == 1.0
        assert unrelated.reasons == []

    def test_repeated_entity_unlikes_stay_soft_for_followed_team(self):
        ctx = _basic_ctx(
            team_relations={10: {"follow"}},
            team_weights={10: 1.0},
            discover_feature_affinities={"entity:new_york_yankees": -9.0},
        )
        result = compute_futures_multiplier(
            ctx,
            sport_category="baseball",
            outcome_team_ids=[10],
            feature_tokens=["entity:new_york_yankees"],
        )
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS + FEATURE_DISLIKE_MAX_PENALTY)
        assert any("your_team_futures" in r for r in result.reasons)
        assert (
            f"discover_feature_dislike:entity:new_york_yankees:"
            f"{FEATURE_DISLIKE_MAX_PENALTY:.2f}"
        ) in result.reasons

    def test_feature_signal_is_capped(self):
        ctx = _basic_ctx(discover_feature_affinities={
            "topic:elections": 0.09,
            "archetype:public_figure": 0.08,
            "format:matchup": -0.15,
            "topic:social_count": -0.14,
        })
        boosted = compute_futures_multiplier(
            ctx,
            sport_category="politics",
            outcome_team_ids=[],
            feature_tokens=["topic:elections", "archetype:public_figure"],
        )
        downranked = compute_futures_multiplier(
            ctx,
            sport_category="culture",
            outcome_team_ids=[],
            feature_tokens=["format:matchup", "topic:social_count"],
        )
        assert boosted.multiplier == pytest.approx(1.0 + FEATURE_INTEREST_MAX_BONUS)
        assert downranked.multiplier == pytest.approx(1.0 + FEATURE_DISLIKE_MAX_PENALTY)

    def test_feature_values_below_threshold_are_ignored(self):
        ctx = _basic_ctx(discover_feature_affinities={"topic:macro": 0.009})
        result = compute_futures_multiplier(
            ctx,
            sport_category="economics",
            outcome_team_ids=[],
            feature_tokens=["topic:macro"],
        )
        assert result.multiplier == 1.0
        assert result.reasons == []

    def test_regional_feature_interest_boosts_matching_cards(self):
        ctx = _basic_ctx(discover_feature_affinities={
            "region:new_england": 0.09,
            "topic:elections": 0.02,
        })
        result = compute_futures_multiplier(
            ctx,
            sport_category="politics",
            outcome_team_ids=[],
            feature_tokens=["region:new_england", "topic:elections"],
        )
        assert result.multiplier == pytest.approx(1.11)
        assert "discover_feature_interest:region:new_england:0.11" in result.reasons

    def test_regional_feature_soft_downrank_does_not_hide_team_market(self):
        ctx = _basic_ctx(
            team_relations={10: {"follow"}},
            team_weights={10: 1.0},
            discover_feature_affinities={"region:california": -9.0},
        )
        result = compute_futures_multiplier(
            ctx,
            sport_category="baseball",
            outcome_team_ids=[10],
            feature_tokens=["region:california"],
        )
        assert result.multiplier == pytest.approx(1.0 + FOLLOW_BONUS + FEATURE_DISLIKE_MAX_PENALTY)
        assert any("your_team_futures" in r for r in result.reasons)
        assert (
            f"discover_feature_dislike:region:california:"
            f"{FEATURE_DISLIKE_MAX_PENALTY:.2f}"
        ) in result.reasons

    def test_category_soft_downrank_stacks_with_sport_affinity(self):
        ctx = _basic_ctx(
            sport_affinities={"basketball_nba": 1.0},
            discover_category_affinities={"basketball": -0.30},
        )
        result = compute_futures_multiplier(
            ctx,
            sport_category="basketball",
            outcome_team_ids=[],
            sport_key="basketball_nba",
        )
        assert result.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS - 0.30)
        assert any("sport_boost" in r for r in result.reasons)
        assert "discover_dismiss:-0.30" in result.reasons

    def test_category_and_feature_downranks_clamp_at_minimum(self):
        ctx = _basic_ctx(
            sport_affinities={"baseball_mlb": 0.0},
            discover_category_affinities={"baseball": -9.0},
            discover_feature_affinities={"region:california": -9.0},
        )
        result = compute_futures_multiplier(
            ctx,
            sport_category="baseball",
            outcome_team_ids=[],
            sport_key="baseball_mlb",
            feature_tokens=["region:california"],
        )
        assert result.multiplier == MIN_MULTIPLIER
        assert "sport_nah:-0.60" in result.reasons
        assert "discover_dismiss:-0.40" in result.reasons
        assert (
            f"discover_feature_dislike:region:california:"
            f"{FEATURE_DISLIKE_MAX_PENALTY:.2f}"
        ) in result.reasons

    def test_event_category_and_feature_interest_stack_with_team_and_sport(self):
        ctx = _basic_ctx(
            team_relations={10: {"follow"}},
            team_weights={10: 0.5},
            sport_affinities={"americanfootball_nfl": 1.0},
            discover_category_affinities={"football": 0.06},
            discover_feature_affinities={"topic:macro": 0.05},
        )
        result = compute_event_multiplier(
            ctx,
            home_team_id=10,
            away_team_id=20,
            sport_key="americanfootball_nfl",
            feature_tokens=["topic:macro"],
        )
        expected = 1.0 + (FOLLOW_BONUS * 0.5) + HIGH_AFFINITY_BONUS + 0.06 + 0.05
        assert result.multiplier == pytest.approx(expected)
        assert any("your_team" in r for r in result.reasons)
        assert any("sport_boost" in r for r in result.reasons)
        assert "discover_interest:0.06" in result.reasons
        assert "discover_feature_interest:topic:macro:0.05" in result.reasons
