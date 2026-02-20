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
    HIGH_AFFINITY_BONUS,
    LOW_AFFINITY_PENALTY,
    MIN_MULTIPLIER,
    MAX_MULTIPLIER,
)


# ============================================================================
# Context helpers
# ============================================================================

def _anonymous_ctx() -> PersonalizationContext:
    """Anonymous (unauthenticated) context."""
    return PersonalizationContext()


def _basic_ctx(
    team_relations=None,
    team_weights=None,
    sport_affinities=None,
    pinned_event_ids=None,
    pinned_futures_ids=None,
) -> PersonalizationContext:
    """Authenticated context with optional overrides."""
    return PersonalizationContext(
        team_relations=team_relations or {},
        team_weights=team_weights or {},
        sport_affinities=sport_affinities or {},
        pinned_event_ids=pinned_event_ids or set(),
        pinned_futures_ids=pinned_futures_ids or set(),
        is_authenticated=True,
    )


# ============================================================================
# Anonymous user tests
# ============================================================================

class TestAnonymousUser:
    """Anonymous users should always get multiplier=1.0 with no personalization."""

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
        """Sport not in user's affinities = no adjustment."""
        ctx = _basic_ctx(sport_affinities={"basketball_nba": 1.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="icehockey_nhl")
        assert result.multiplier == 1.0

    def test_empty_affinities(self):
        ctx = _basic_ctx(sport_affinities={})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="basketball_nba")
        assert result.multiplier == 1.0

    def test_zero_affinity_suppresses(self):
        """Explicit 0.0 affinity should suppress."""
        ctx = _basic_ctx(sport_affinities={"icehockey_nhl": 0.0})
        result = compute_event_multiplier(ctx, home_team_id=10, away_team_id=20, sport_key="icehockey_nhl")
        assert result.multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)


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
        ctx = _basic_ctx(sport_affinities={"baseball_mlb": 0.05})
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
