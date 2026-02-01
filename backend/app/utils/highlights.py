"""
Event highlight scoring and classification.

Computes highlight scores and flags for events based on various factors
like closeness, upset potential, momentum shifts, etc.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal


# League tier definitions (higher tier = more prominent)
LEAGUE_TIERS: dict[str, int] = {
    # Tier 1: Major US leagues
    "basketball_nba": 1,
    "americanfootball_nfl": 1,
    "baseball_mlb": 1,
    "icehockey_nhl": 1,
    # Tier 2: College major + MLS
    "americanfootball_ncaaf": 2,
    "basketball_ncaab": 2,
    "soccer_usa_mls": 2,
    # Tier 3: Everything else
}

# Highlight score weights
WEIGHTS = {
    "live": 30,                    # Being live is inherently interesting
    "close_matchup": 25,           # 40-60% probability
    "very_close": 10,              # 45-55% probability (bonus)
    "favorite_switched": 20,       # Upset potential
    "major_probability_swing": 15, # >15% change from open
    "major_score_swing": 10,       # >20% projected score change
    "starting_soon_3h": 15,        # Starting in <3 hours
    "starting_soon_1h": 10,        # Starting in <1 hour (bonus)
    "tier_1_league": 10,           # Major league bonus
    "tier_2_league": 5,            # College/secondary league bonus
    "recent_finish_upset": 20,     # Recently finished + upset
    "recent_finish": 5,            # Recently finished (24h)
}

# Thresholds
CLOSE_MATCHUP_MIN = 0.40
CLOSE_MATCHUP_MAX = 0.60
VERY_CLOSE_MIN = 0.45
VERY_CLOSE_MAX = 0.55
BLOWOUT_THRESHOLD = 0.85
MAJOR_PROB_SWING = 0.15  # 15% change
MAJOR_SCORE_SWING = 0.20  # 20% change


@dataclass
class EventFlags:
    """Boolean flags describing event characteristics."""
    is_live: bool = False
    is_close_matchup: bool = False
    is_very_close: bool = False
    is_blowout: bool = False
    favorite_switched: bool = False
    probability_swing: Literal["major", "minor", "stable"] = "stable"
    score_swing: Literal["major", "minor", "stable"] = "stable"
    is_starting_soon: bool = False  # <3h
    is_starting_very_soon: bool = False  # <1h
    is_recently_finished: bool = False  # <24h
    is_upset: bool = False  # Closed + favorite switched
    league_tier: int = 3


@dataclass
class HighlightResult:
    """Complete highlight analysis for an event."""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    flags: EventFlags = field(default_factory=EventFlags)
    primary_reason: Optional[str] = None


def get_league_tier(sport_key: Optional[str]) -> int:
    """Get the tier for a league (1=major, 2=secondary, 3=other)."""
    if not sport_key:
        return 3
    return LEAGUE_TIERS.get(sport_key, 3)


def compute_highlight(
    # Event basics
    status: str,
    commence_time: datetime,
    sport_key: Optional[str] = None,
    # Current odds
    current_home_prob: Optional[float] = None,
    current_away_prob: Optional[float] = None,
    current_home_spread: Optional[float] = None,
    current_over_under: Optional[float] = None,
    # Opening odds (for comparison)
    opening_home_prob: Optional[float] = None,
    opening_away_prob: Optional[float] = None,
    opening_home_spread: Optional[float] = None,
    opening_over_under: Optional[float] = None,
    opening_favorite: Optional[str] = None,
    # Timing
    now: Optional[datetime] = None,
) -> HighlightResult:
    """
    Compute highlight score and flags for an event.

    Returns a HighlightResult with:
    - score: 0-100 indicating how "highlight-worthy" the event is
    - reasons: list of reason codes explaining the score
    - flags: EventFlags with boolean characteristics
    - primary_reason: the most important reason for display
    """
    if now is None:
        now = datetime.now(timezone.utc)

    result = HighlightResult()
    flags = result.flags

    # Ensure commence_time is timezone-aware
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)

    # === Time-based flags ===
    time_until_start = (commence_time - now).total_seconds()
    time_since_start = -time_until_start
    hours_until = time_until_start / 3600
    hours_since = time_since_start / 3600

    # Live status
    flags.is_live = status == "live"
    if flags.is_live:
        result.score += WEIGHTS["live"]
        result.reasons.append("live")

    # Starting soon
    if status == "scheduled" and 0 < hours_until <= 3:
        flags.is_starting_soon = True
        result.score += WEIGHTS["starting_soon_3h"]
        result.reasons.append("starting_soon")

        if hours_until <= 1:
            flags.is_starting_very_soon = True
            result.score += WEIGHTS["starting_soon_1h"]
            result.reasons.append("starting_very_soon")

    # Recently finished
    if status in ("completed", "closed") and 0 < hours_since <= 24:
        flags.is_recently_finished = True
        result.score += WEIGHTS["recent_finish"]
        result.reasons.append("recent_finish")

    # === League tier ===
    flags.league_tier = get_league_tier(sport_key)
    if flags.league_tier == 1:
        result.score += WEIGHTS["tier_1_league"]
        result.reasons.append("tier_1")
    elif flags.league_tier == 2:
        result.score += WEIGHTS["tier_2_league"]
        result.reasons.append("tier_2")

    # === Probability-based flags ===
    if current_home_prob is not None:
        # Closeness
        if CLOSE_MATCHUP_MIN <= current_home_prob <= CLOSE_MATCHUP_MAX:
            flags.is_close_matchup = True
            result.score += WEIGHTS["close_matchup"]
            result.reasons.append("close_matchup")

            if VERY_CLOSE_MIN <= current_home_prob <= VERY_CLOSE_MAX:
                flags.is_very_close = True
                result.score += WEIGHTS["very_close"]
                result.reasons.append("very_close")

        # Blowout
        if current_home_prob >= BLOWOUT_THRESHOLD or current_home_prob <= (1 - BLOWOUT_THRESHOLD):
            flags.is_blowout = True
            # Blowouts reduce score (less interesting)
            result.score = max(0, result.score - 15)
            result.reasons.append("blowout")

        # Probability swing from open
        if opening_home_prob is not None:
            prob_change = abs(current_home_prob - opening_home_prob)
            if prob_change >= MAJOR_PROB_SWING:
                flags.probability_swing = "major"
                result.score += WEIGHTS["major_probability_swing"]
                result.reasons.append("major_prob_swing")
            elif prob_change >= 0.08:  # 8% change
                flags.probability_swing = "minor"

        # Favorite switched
        if opening_favorite:
            current_favorite = "home" if current_home_prob > 0.5 else "away" if current_home_prob < 0.5 else "even"
            if opening_favorite != current_favorite and opening_favorite != "even" and current_favorite != "even":
                flags.favorite_switched = True
                result.score += WEIGHTS["favorite_switched"]
                result.reasons.append("favorite_switched")

                # If finished with upset, big bonus
                if flags.is_recently_finished:
                    flags.is_upset = True
                    result.score += WEIGHTS["recent_finish_upset"]
                    result.reasons.append("upset")

    # === Projected score swing ===
    if (current_over_under is not None and opening_over_under is not None
        and opening_over_under > 0):
        score_change_pct = abs(current_over_under - opening_over_under) / opening_over_under
        if score_change_pct >= MAJOR_SCORE_SWING:
            flags.score_swing = "major"
            result.score += WEIGHTS["major_score_swing"]
            result.reasons.append("major_score_swing")
        elif score_change_pct >= 0.10:  # 10% change
            flags.score_swing = "minor"

    # === Cap score at 100 ===
    result.score = min(100, result.score)

    # === Determine primary reason for display ===
    # Priority order for what to show users
    priority_order = [
        ("upset", "Recent upset"),
        ("favorite_switched", "Possible upset"),
        ("very_close", "Coin flip"),
        ("close_matchup", "Close matchup"),
        ("major_prob_swing", "Big line movement"),
        ("live", "Live"),
        ("starting_very_soon", "Starting soon"),
        ("starting_soon", "Starting soon"),
        ("recent_finish", "Recently finished"),
    ]

    for reason_code, display_text in priority_order:
        if reason_code in result.reasons:
            result.primary_reason = display_text
            break

    return result


def get_highlight_label(result: HighlightResult) -> Optional[str]:
    """
    Get a short label for display in the Highlights section.

    Returns None if event shouldn't be highlighted.
    """
    flags = result.flags

    if flags.is_upset:
        return "Recent upset"
    if flags.is_live and flags.favorite_switched:
        return "Upset brewing"
    if flags.is_live and flags.is_very_close:
        return "Coin flip"
    if flags.is_live and flags.is_close_matchup:
        return "Close game"
    if flags.is_live and flags.probability_swing == "major":
        return "Momentum shift"
    if flags.is_starting_very_soon and flags.is_close_matchup:
        return "Close matchup"
    if flags.is_starting_soon and flags.is_close_matchup:
        return "Close matchup"
    if flags.is_live:
        return "Live"

    return None


def should_highlight(result: HighlightResult, min_score: int = 30) -> bool:
    """Determine if an event should appear in the Highlights section."""
    # Always highlight live close games or upsets
    if result.flags.is_live and (result.flags.is_close_matchup or result.flags.favorite_switched):
        return True

    # Always highlight recent upsets
    if result.flags.is_upset:
        return True

    # Otherwise, use score threshold
    return result.score >= min_score
